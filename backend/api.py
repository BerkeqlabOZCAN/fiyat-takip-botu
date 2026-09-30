from __future__ import annotations

import asyncio
import logging

from fastapi import Depends, FastAPI, HTTPException, Query as Q, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import json

import catalog
import config
import engine
import store

logger = logging.getLogger(__name__)

app = FastAPI(title="Fiyat Takip", docs_url="/docs")



async def require_token(request: Request) -> None:
    if not config.API_TOKEN:
        return
    supplied = request.headers.get("x-token") or request.query_params.get("token")
    if supplied != config.API_TOKEN:
        raise HTTPException(status_code=401, detail="gecersiz token")

class WatchIn(BaseModel):
    query: str | None = None
    label: str | None = None
    cat: str | None = None
    sel: list[str] = []
    # model adi (X8 Pro gibi) zorunlu kelime oluyor
    model: str | None = None
    # yeni arama eskisinin yerıne mi gecsin
    replace: bool = True

# katalog

@app.get("/api/resolve", dependencies=[Depends(require_token)])
async def resolve_category(q: str):
    cat = catalog.resolve(q)
    if not cat:
        return {"c": None, "cats": [{"k": c.k, "l": c.l}
                                    for c in catalog.CATEGORIES.values()]}
    return {"c": cat.k, "l": cat.l, "g": catalog.groups_meta(cat)}

@app.get("/api/opts", dependencies=[Depends(require_token)])
async def group_options(c: str, g: str):
    cat = catalog.CATEGORIES.get(c)
    if not cat:
        raise HTTPException(404, "kategori yok")
    return {"c": c, "g": g, "o": catalog.options_meta(cat, g)}



@app.get("/api/preview", dependencies=[Depends(require_token)])
async def preview(c: str, sel: str = "", model: str = ""):
    cat = catalog.CATEGORIES.get(c)
    if not cat:
        raise HTTPException(404, "kategori yok")
    keys = [s for s in sel.split(",") if s]
    return catalog.build(cat, keys, model)

@app.get("/api/health")
async def health():
    return {"ok": True, "ts": engine.latest().get("ts", 0),
            "watches": len(store.get_watches())}

@app.get("/api/best", dependencies=[Depends(require_token)])
async def best(watch: int | None = Q(default=None), limit: int = Q(default=8, ge=1, le=20)):
    payload = engine.slim(engine.latest(), watch_id=watch, limit=limit)
    # Content-Length'i kucuk tutmak icin bosluksuz serilestir
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})



@app.get("/api/full", dependencies=[Depends(require_token)])
async def full():
    return engine.latest()


@app.get("/api/watch", dependencies=[Depends(require_token)])
async def list_watches():
    out = []
    for w in store.get_watches(only_active=False):
        pins = store.get_pins(w["id"])
        w["pins"] = pins
        # ucuzdan pahaliya sirala
        w["pins_sorted"] = [
            {"s": p["site"], "p": round(p["price"], 2),
             "n": (p["name"] or "")[:60], "u": p["url"]}
            for p in sorted((x for x in pins.values() if x.get("price")),
                            key=lambda x: x["price"])
        ]
        out.append(w)
    return out


@app.post("/api/watch", dependencies=[Depends(require_token)])
async def create_watch(body: WatchIn):
    query, label = body.query, body.label
    spec = None

    # kategori + secilen filtreler
    if body.cat:
        cat = catalog.CATEGORIES.get(body.cat)
        if not cat:
            raise HTTPException(404, "kategori yok")
        built = catalog.build(cat, body.sel, body.model or "")
        query, label = built["query"], label or built["label"]
        # secimleri sakla sorgu sonradan yeniden kurulabilsin
        spec = json.dumps({"cat": body.cat, "sel": body.sel,
                           "model": body.model or ""})
    if not query or not query.strip():
        raise HTTPException(400, "query ya da cat verilmeli")

    wid = store.add_watch(query, label, spec)
    if body.replace:
        n = store.deactivate_others(wid)
        if n:
            logger.info("%d onceki takip pasiflestirildi", n)

    # tarama bitmeden donersek liste bos gorunuyor
    await engine.run_cycle(wait=True)
    return {"id": wid, "query": query.strip(), "label": label}


@app.delete("/api/watch/{watch_id}", dependencies=[Depends(require_token)])
async def delete_watch(watch_id: int):
    if not store.remove_watch(watch_id):
        raise HTTPException(404, "bulunamadi")
    return {"deleted": watch_id}


@app.post("/api/refresh", dependencies=[Depends(require_token)])
async def refresh():
    payload = await engine.run_cycle()
    return {"ok": True, "ts": payload["ts"],
            "watches": len(payload.get("watches", []))}


@app.get("/api/history", dependencies=[Depends(require_token)])
async def history(watch: int, site: str, days: int = 30):
    return store.price_stats(watch, site, days)



class SettingsIn(BaseModel):
    mod: str | None = None            # "dusus" | "hepsi"
    aralik: int | None = None         # dakika
    esik_tl: float | None = None
    esik_pct: float | None = None
    coklu: bool | None = None
    stok: bool | None = None
    sessiz_bas: str | None = None     # "23:00" ("" -> kapali)
    sessiz_bit: str | None = None
    rapor: str | None = None          # "09:00" ("" -> kapali)
    duraklat: bool | None = None
    kapali_siteler: list[str] | None = None

@app.get("/api/settings", dependencies=[Depends(require_token)])
async def get_settings():
    import telegram_bot as tb
    return {
        "mod": store.get_setting(tb.S_MOD, "dusus"),
        "aralik": tb._aralik(),
        "esik_tl": tb._esik_tl(),
        "esik_pct": tb._esik_pct(),
        "coklu": store.get_setting(tb.S_COKLU, "1") == "1",
        "stok": store.get_setting(tb.S_STOK, "0") == "1",
        "sessiz_bas": store.get_setting(tb.S_SESSIZ_BAS, ""),
        "sessiz_bit": store.get_setting(tb.S_SESSIZ_BIT, ""),
        "rapor": store.get_setting(tb.S_RAPOR, ""),
        "duraklat": store.get_setting(tb.S_DURAK, "0") == "1",
        "kapali_siteler": [x for x in
                           store.get_setting(tb.S_KAPALI_SITE, "").split(",") if x],
        "tum_siteler": [s.key for s in engine.enabled_sites()],
    }



@app.post("/api/settings", dependencies=[Depends(require_token)])
async def set_settings(body: SettingsIn):
    import telegram_bot as tb

    if body.mod in ("dusus", "hepsi"):
        store.set_setting(tb.S_MOD, body.mod)
    if body.aralik and 2 <= body.aralik <= 1440:
        store.set_setting(tb.S_ARALIK, body.aralik)
        tb._yeniden_zamanla(body.aralik)      # zamanlayiciyi da guncelle
    if body.esik_tl is not None and body.esik_tl >= 0:
        store.set_setting(tb.S_ESIK_TL, body.esik_tl)
    if body.esik_pct is not None and body.esik_pct >= 0:
        store.set_setting(tb.S_ESIK_PCT, body.esik_pct)
    if body.coklu is not None:
        store.set_setting(tb.S_COKLU, "1" if body.coklu else "0")
    if body.stok is not None:
        store.set_setting(tb.S_STOK, "1" if body.stok else "0")
    if body.sessiz_bas is not None:
        store.set_setting(tb.S_SESSIZ_BAS, body.sessiz_bas)
    if body.sessiz_bit is not None:
        store.set_setting(tb.S_SESSIZ_BIT, body.sessiz_bit)
    if body.rapor is not None:
        store.set_setting(tb.S_RAPOR, body.rapor)
        tb._rapor_guncelle(body.rapor)
    if body.duraklat is not None:
        onceki = store.get_setting(tb.S_DURAK, "0") == "1"
        store.set_setting(tb.S_DURAK, "1" if body.duraklat else "0")
        if not body.duraklat:
            store.set_setting(tb.S_DURAK_BITIS, "0")
        if onceki != bool(body.duraklat):
            # sadece durum degistiyse haber ver
            asyncio.create_task(
                tb.durum_bildir(bool(body.duraklat), "api"))
    if body.kapali_siteler is not None:
        store.set_setting(tb.S_KAPALI_SITE, ",".join(sorted(body.kapali_siteler)))

    return await get_settings()



@app.get("/api/seri", dependencies=[Depends(require_token)])
async def price_series(watch: int, days: int = 30):
    return {
        "seri": [{"ts": t, "p": p} for t, p in store.price_series(watch, days)],
        "ozet": store.price_summary(watch, days),
        "dip": store.all_time_low(watch),
    }

@app.get("/api/hedef", dependencies=[Depends(require_token)])
async def get_target(watch: int):
    import telegram_bot as tb
    ham = store.get_setting(tb.S_HEDEF + str(watch), "")
    return {"watch": watch, "hedef": float(ham) if ham else None}

@app.post("/api/hedef", dependencies=[Depends(require_token)])
async def set_target(watch: int, hedef: float | None = None):
    import telegram_bot as tb
    anahtar = tb.S_HEDEF + str(watch)
    store.set_setting(anahtar, "" if hedef in (None, 0) else hedef)
    store.set_setting(anahtar + "_vuruldu", "0")
    return {"watch": watch, "hedef": hedef}

@app.post("/api/aktif/{watch_id}", dependencies=[Depends(require_token)])
async def activate(watch_id: int):
    if not store.activate_watch(watch_id):
        raise HTTPException(404, "bulunamadi")
    import telegram_bot as tb
    if store.get_setting(tb.S_COKLU, "1") != "1":
        store.deactivate_others(watch_id)
    return {"ok": True, "id": watch_id}



@app.get("/api/kategoriler", dependencies=[Depends(require_token)])
async def categories():
    return [{"k": c.k, "l": c.l,
             "g": [{"k": g.k, "l": g.l, "m": int(g.multi),
                    "o": [{"k": o.k, "l": o.l} for o in g.options]}
                   for g in c.groups]}
            for c in catalog.CATEGORIES.values()]
