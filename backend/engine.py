from __future__ import annotations

import asyncio
import logging
import time

import json


import catalog
import config
import store
from fetcher import fetch_site
from match import Query, filter_offers
from verify import pick_verified
from sites import SITES

logger = logging.getLogger(__name__)
# en son hesaplanan sonuc API bunu servis eder
_latest: dict = {"v": 1, "ts": 0, "watches": []}
_lock = asyncio.Lock()


def enabled_sites() -> list:
    kapali = {x for x in store.get_setting("kapali_siteler", "").split(",") if x}
    return [s for s in SITES
            if s.key in config.ENABLED_SITES and s.enabled and s.key not in kapali]


async def search_everywhere(raw_query: str, min_price: float = 0) -> dict[str, list]:
    q = Query(raw_query)
    keywords = q.keywords
    sites = enabled_sites()

    logger.info("Arama: %r -> %s (%d site)", raw_query, keywords,
                len(sites))

    results = await asyncio.gather(
        *(fetch_site(s, keywords) for s in sites), return_exceptions=True
    )

    out: dict[str, list] = {}
    for site, res in zip(sites, results):
        if isinstance(res, Exception):
            logger.warning("%s: %s", site.key, res)
            out[site.key] = []
            continue
        # kategori alt siniri global ayardan once gelır
        taban = max(min_price, config.MIN_PRICE)
        relevant = filter_offers(res, q, taban, config.MAX_PRICE)
        logger.info("  %-12s ham=%-3d alakali=%-3d %s", site.key, len(res),
                    len(relevant),
                    f"en ucuz={relevant[0].price:,.2f} TL" if relevant else "-")
        out[site.key] = relevant
    return out

def _refresh_query(watch: dict) -> tuple:
    spec = watch.get("spec")
    if not spec:
        return watch["query"], (), 0
    try:
        d = json.loads(spec)
        cat = catalog.CATEGORIES.get(d.get("cat"))
        if not cat:
            return watch["query"], (), 0
        built = catalog.build(cat, d.get("sel") or [], d.get("model") or "")
        rules = catalog.page_rules(cat, d.get("sel") or [])
    except Exception as e:
        logger.warning("spec cozulemedi (watch %s): %s", watch.get("id"), e)
        return watch["query"], (), 0
    if built["query"] != watch["query"]:
        if store.update_query(watch["id"], built["query"], built["label"]):
            logger.info("watch %s filtresi guncellendi -> %s",
                        watch["id"], built["query"])
            watch["query"] = built["query"]
            watch["label"] = built["label"]
    return watch["query"], rules, built.get("min_price", 0)


async def run_watch(watch: dict) -> dict:
    # sorguyu her turda secimlerden yeniden kur
    query, page_rules, taban = _refresh_query(watch)
    per_site = await search_everywhere(query, taban)
    old_pins = store.get_pins(watch["id"])

    items = []
    for site in enabled_sites():
        offers = per_site.get(site.key) or []
        if not offers:
            # son fiyati bayat goster
            old = old_pins.get(site.key)
            if old and old.get("price"):
                items.append({
                    "s": site.key, "n": old["name"], "p": round(old["price"], 2),
                    "u": old["url"], "st": int(bool(old["in_stock"])), "old": 1,
                })
            continue

        # ucuzdan pahaliya git urun sayfasindan dogrula
        best = await pick_verified(offers, page_rules)
        if best is None:
            logger.info("  %-12s dogrulamayi gecen urun yok", site.key)
            # elenen urunun eski kaydini gosterme
            store.clear_pin(watch["id"], site.key)
            continue
        store.upsert_pin(watch["id"], site.key, best.name, best.url,
                         best.price, best.in_stock)
        store.add_snapshot(watch["id"], site.key, best.url, best.price)

        # farkli urunlerin fiyatini karsilastirma
        prev = old_pins.get(site.key)
        delta = None
        if prev and prev.get("price") and prev.get("url") == best.url:
            delta = round(best.price - prev["price"], 2)

        # sd +1 stoga girdi -1 tukendi
        sd = None
        if prev and prev.get("url") == best.url:
            onceki = bool(prev.get("in_stock", 1))
            if onceki != best.in_stock:
                sd = 1 if best.in_stock else -1

        items.append({
            "s": site.key,
            "n": best.name[:90],
            "p": round(best.price, 2),
            "u": best.url,
            "st": int(best.in_stock),
            "d": delta,
            "sd": sd,
            "old": 0,
        })
    fresh = [i for i in items if not i["old"]]
    cheapest = min(fresh, key=lambda i: i["p"]) if fresh else None

    return {
        "id": watch["id"],
        "q": watch.get("label") or watch["query"],
        "best": {"s": cheapest["s"], "p": cheapest["p"]} if cheapest else None,
        "items": sorted(items, key=lambda i: i["p"]),
    }

async def run_cycle(wait: bool = False) -> dict:
    # wait=False ise zamanlayici turlari ust uste binmesin
    if _lock.locked() and not wait:
        logger.info("Onceki tur devam ediyor, bu tur atlandi.")
        return _latest

    async with _lock:
        started = time.time()
        watches = store.get_watches(only_active=True)
        if not watches:
            logger.info("Takip listesi bos. /api/watch ile anahtar kelime ekle.")
            payload = {"v": 1, "ts": int(time.time()), "watches": []}
        else:
            results = []
            for w in watches:
                try:
                    results.append(await run_watch(w))
                except Exception as e:
                    logger.error("watch %s hatasi: %s", w["id"], e, exc_info=True)
            payload = {"v": 1, "ts": int(time.time()), "watches": results}

        globals()["_latest"] = payload
        logger.info("Tur bitti (%.1f sn).", time.time() - started)
        return payload


def latest() -> dict:
    return _latest

def slim(payload: dict, watch_id: int | None = None, limit: int = 8) -> dict:
    watches = payload.get("watches", [])
    if watch_id is not None:
        watches = [w for w in watches if w["id"] == watch_id]

    out = {"v": 1, "ts": payload.get("ts", 0), "w": []}
    for w in watches:
        items = []
        for i in w["items"][:limit]:
            it = {"s": i["s"], "n": i["n"][:56], "p": i["p"], "u": i["u"]}
            if not i.get("st", 1):
                it["st"] = 0
            if i.get("old"):
                it["old"] = 1
            if i.get("d"):
                it["d"] = i["d"]
            items.append(it)
        out["w"].append({"q": w["q"][:90], "b": w.get("best"), "i": items})
    return out
