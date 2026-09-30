
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time

import catalog
import config
import engine
import store

logger = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"

# ayar anahtarlari (SQLite'ta saklanir)
S_MOD = "notify_mode"       # "dusus" | "hepsi"
S_ARALIK = "interval_min"
S_DURAK = "paused"
S_DURAK_BITIS = "paused_until"

# kurus farklarini atla
DROP_MIN_TL = 50.0
DROP_MIN_PCT = 1.0

# sohbet oturumu kullanici filtre secerken tutulan gecici durum
_ses: dict = {}
_son_ts = 0                 # ayni tarama sonucunu iki kez bildirmemek icin


# yardimci

def _yetkili() -> set:
    ham = config.TELEGRAM_CHAT_ID
    import os
    ham = os.getenv("TELEGRAM_ALLOWED_IDS", ham)
    return {x.strip() for x in ham.split(",") if x.strip()}

def fmt(v: float) -> str:
    s = f"{v:,.2f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")



def esc(s: str) -> str:
    return html.escape(s or "", quote=False)
def _mod() -> str:
    return store.get_setting(S_MOD, "dusus")


def _aralik() -> int:
    try:
        return int(store.get_setting(S_ARALIK, str(config.CHECK_INTERVAL_MINUTES)))
    except ValueError:
        return config.CHECK_INTERVAL_MINUTES



def _durakta() -> bool:
    if store.get_setting(S_DURAK, "0") != "1":
        return False
    bitis = store.get_setting(S_DURAK_BITIS, "0")
    try:
        bitis = float(bitis)
    except ValueError:
        bitis = 0
    if bitis and time.time() >= bitis:       # sureli duraklatma doldu
        store.set_setting(S_DURAK, "0")
        store.set_setting(S_DURAK_BITIS, "0")
        return False
    return True


# Telegram API

async def _call(method: str, **params):
    import httpx
    url = API.format(token=config.TELEGRAM_BOT_TOKEN, method=method)
    try:
        async with httpx.AsyncClient(timeout=75) as c:
            r = await c.post(url, json=params)
    except Exception as e:
        logger.warning("Telegram %s istegi basarisiz: %s", method, e)
        return None
    if r.status_code != 200:
        logger.warning("Telegram %s -> %s %s", method, r.status_code, r.text[:200])
        return None
    return r.json().get("result")


async def gonder(chat_id, text: str, keyboard: dict | None = None):
    p = {"chat_id": chat_id, "text": text[:4090], "parse_mode": "HTML",
         "disable_web_page_preview": True}
    if keyboard:
        p["reply_markup"] = keyboard
    r = await _call("sendMessage", **p)
    if r:
        store.log_message(chat_id, r.get("message_id"))   # /temizle icin
    return r



async def durum_bildir(duraklatildi: bool, kaynak: str = "uygulama"):
    if duraklatildi:
        metin = ("⏸ <b>Takip kapatıldı</b>\n"
                 "Tarama duracak, fiyat bildirimi gelmeyecek.\n"
                 "<i>Kaynak: " + esc(kaynak) + "</i>\n\n"
                 "Açmak için /ac")
    else:
        metin = ("▶ <b>Takip açıldı</b>\n"
                 "Her " + str(_aralik()) + " dakikada bir taranacak.\n"
                 "<i>Kaynak: " + esc(kaynak) + "</i>")

    for chat in _yetkili():
        try:
            await gonder(chat, metin)
        except Exception as e:
            logger.warning("durum bildirimi gonderilemedi (%s): %s", chat, e)
async def duzenle(chat_id, msg_id: int, text: str, keyboard: dict | None = None):
    p = {"chat_id": chat_id, "message_id": msg_id, "text": text[:4090],
         "parse_mode": "HTML", "disable_web_page_preview": True}
    if keyboard:
        p["reply_markup"] = keyboard
    return await _call("editMessageText", **p)

async def _cb_cevap(cb_id: str, note: str = ""):
    # butondaki halkayi kapat
    await _call("answerCallbackQuery", callback_query_id=cb_id, text=note or None)

# menuler

def _ana_klavye(chat: str) -> dict:
    s = _ses[chat]
    cat = catalog.CATEGORIES[s["cat"]]
    satirlar, sira = [], []
    for g in cat.groups:
        n = len(s["sel_by_group"].get(g.k, []))
        etiket = g.l + (f" ({n})" if n else "")
        sira.append({"text": etiket, "callback_data": f"g:{g.k}"})
        if len(sira) == 2:
            satirlar.append(sira)
            sira = []
    if sira:
        satirlar.append(sira)
    satirlar.append([{"text": " ARA", "callback_data": "s"},
                     {"text": " Temizle", "callback_data": "c"}])
    return {"inline_keyboard": satirlar}


def _ana_metin(chat: str) -> str:
    s = _ses[chat]
    cat = catalog.CATEGORIES[s["cat"]]
    t = f" <b>{esc(cat.l)}</b>\n\nFiltre grubunu seç, sonra <b>ARA</b>'ya bas.\n"
    if s.get("model"):
        t += "\n <b>Model:</b> " + esc(s["model"].upper())
    else:
        t += "\n<i>Model yazabilirsin (örn. X8 Pro) — isteğe bağlı.</i>"
    secili = [k for ks in s["sel_by_group"].values() for k in ks]
    if not secili:
        t += "\n<i>Henüz filtre seçilmedi — tüm ürünler taranır.</i>"
    else:
        t += "\n<b>Seçili:</b> " + ", ".join(esc(k) for k in secili)
    return t

def _grup_klavye(chat: str, gkey: str) -> dict:
    s = _ses[chat]
    cat = catalog.CATEGORIES[s["cat"]]
    grup = next(g for g in cat.groups if g.k == gkey)
    secili = set(s["sel_by_group"].get(gkey, []))

    satirlar, sira = [], []
    for o in grup.options:
        etiket = (" " if o.k in secili else "") + o.l
        sira.append({"text": etiket, "callback_data": f"o:{gkey}:{o.k}"})
        if len(sira) == 2:
            satirlar.append(sira)
            sira = []
    if sira:
        satirlar.append(sira)
    satirlar.append([{"text": "⬅ Geri", "callback_data": "m"},
                     {"text": " ARA", "callback_data": "s"}])
    return {"inline_keyboard": satirlar}



# mesaj kurma


def sonuc_mesaji(payload: dict) -> str:
    watches = payload.get("watches") or []
    if not watches:
        return " Takip listesi boş. Ne aradığını yaz (örn. <code>ram</code>)."

    parcalar = []
    for w in watches:
        p = [f" <b>{esc(w['q'])}</b>"]
        items = w.get("items") or []
        if not items:
            p.append("Hiçbir sitede eşleşen ürün yok. Filtreleri gevşetmeyi dene.")
            parcalar.append("\n".join(p))
            continue
        for i, it in enumerate(items[:8]):
            isaret = "" if i == 0 else "•"
            satir = f"{isaret} <b>{esc(it['s'])}</b>  {fmt(it['p'])} TL"
            d = it.get("d") or 0
            if d < -0.005:
                satir += f"   {fmt(-d)}"
            elif d > 0.005:
                satir += f"   {fmt(d)}"
            if it.get("old"):
                satir += "  <i>(eski)</i>"
            ad = esc(it["n"][:52])
            p.append(f"{satir}\n   <a href=\"{html.escape(it['u'], quote=True)}\">{ad}</a>")

        if len(items) > 1 and items[1]["p"] > items[0]["p"]:
            fark = items[1]["p"] - items[0]["p"]
            p.append(f"\n İkinci ucuzdan <b>{fmt(fark)} TL</b> daha uygun.")
        parcalar.append("\n".join(p))
    return "\n\n".join(parcalar)


def dusus_mesaji(payload: dict) -> str:
    bloklar = []
    for w in payload.get("watches") or []:
        satirlar = []
        for it in w.get("items") or []:
            d = it.get("d") or 0
            p = it.get("p") or 0
            if p <= 0 or d >= -0.005:
                continue
            dusus = -d
            eski = p + dusus
            yuzde = (dusus / eski * 100.0) if eski else 0
            if dusus < _esik_tl() and yuzde < _esik_pct():
                continue
            satirlar.append(
                f" <b>{esc(it['s'])}</b>\n"
                f"   {fmt(eski)}  →  <b>{fmt(p)} TL</b>\n"
                f"   {fmt(dusus)} TL ucuzladı (%{yuzde:.1f})\n"
                f"   <a href=\"{html.escape(it['u'], quote=True)}\">"
                f"{esc(it['n'][:52])}</a>")
        if satirlar:
            bloklar.append(f" <b>FİYAT DÜŞTÜ</b> \n<i>{esc(w['q'])}</i>\n\n"
                           + "\n\n".join(satirlar))
    return "\n\n".join(bloklar)

# komutlar
YARDIM = (
    "<b>Fiyat Takip Botu</b>\n\n"
    "Ne aradığını yaz: <code>ram</code>, <code>ekran kartı</code>, "
    "<code>işlemci</code>, <code>ssd</code>, <code>monitör</code>\n"
    "Sonra menüden filtreleri seç ve <b>ARA</b>'ya bas.\n\n"

    "<b> Fiyat analizi</b>\n"
    "/gecmis — 30 günün dibi / ortalaması / tepesi\n"
    "/ortalama — şu an ortalamanın altında mı?\n"
    "/enucuz — tüm zamanların en düşüğü\n"
    "/rapor — günlük özet (<code>/rapor 09:00</code> = her sabah)\n\n"

    "<b> Uyarılar</b>\n"
    "/hedef 25000 — bu fiyatın altına inince haber ver\n"
    "/esik 200 — düşüş eşiği (<code>/esik %5</code> de olur)\n"
    "/stok ac — stoktan çıkınca / geri gelince haber ver\n"
    "/sessiz 23:00 08:00 — gece mesaj gönderme\n"
    "/mod dusus | hepsi — sadece indirim mi, her tur mu\n\n"

    "<b> Takip</b>\n"
    "/liste — takipler + son fiyatlar\n"
    "/simdi — hemen tara\n"
    "/duzenle — filtre menüsünü yeniden aç\n"
    "/coklu ac — birden fazla ürünü aynı anda izle\n"
    "/aktif 3 — pasif takibi geri aç\n"
    "/sil 3 — takip sil (<code>/sil hepsi</code>)\n\n"

    "<b> Arama</b>\n"
    "/ara ddr5 32gb -notebook — filtre menüsü olmadan\n"
    "/kategoriler — desteklenen kategoriler\n"
    "/filtreler ram — bir kategorinin tüm filtreleri\n\n"


    "<b> Sistem</b>\n"
    "/siteler — hangi site ne durumda\n"
    "/site kapat trendyol — siteyi devre dışı bırak\n"
    "/sure 10 — kontrol aralığı (dakika)\n"
    "/kapat [saat] · /ac — takibi durdur / başlat\n"
    "/durum · /log · /yedek · /temizle · /yeniden"
)


async def _kategori_baslat(chat: str, metin: str):
    cat = catalog.resolve(metin)
    if not cat:
        t = "Bunu tanıyamadım. Şunlardan birini yaz:\n\n"
        t += "\n".join("• <b>" + esc(c.l) + "</b>" for c in catalog.CATEGORIES.values())
        await gonder(chat, t)
        return

    _ses[chat] = {"cat": cat.k, "sel_by_group": {}, "menu_id": 0}
    r = await gonder(chat, _ana_metin(chat), _ana_klavye(chat))
    if r:
        _ses[chat]["menu_id"] = r["message_id"]

async def _model_yaz(chat: str, metin: str):
    s = _ses[chat]
    if metin.strip() == "-":
        s.pop("model", None)
        if s.get("menu_id"):
            await duzenle(chat, s["menu_id"], _ana_metin(chat), _ana_klavye(chat))
        await gonder(chat, "Model kaldırıldı.")
        return

    kelimeler = catalog.model_kelimeleri(metin)
    if not kelimeler:
        await gonder(chat, "Model olarak okuyamadım. Örnek: <code>X8 Pro</code>")
        return
    s["model"] = " ".join(kelimeler)
    if s.get("menu_id"):
        await duzenle(chat, s["menu_id"], _ana_metin(chat), _ana_klavye(chat))
    await gonder(chat, " Model: <b>" + esc(s["model"].upper()) + "</b>\n"
                       "Değiştirmek için yenisini yaz, kaldırmak için "
                       "<code>-</code> gönder.")

async def _cmd_liste(chat: str):
    watches = store.get_watches(only_active=False)
    if not watches:
        await gonder(chat, "Takip listesi boş. Ne aradığını yaz (örn. <code>ram</code>).")
        return

    p = []
    for w in watches:
        aktif = w["active"] == 1
        bas = "" if aktif else ""
        etiket = esc(w["label"] or w["query"])
        p.append(bas + " <b>#" + str(w["id"]) + "</b> " + etiket +
                 ("" if aktif else "  <i>(pasif)</i>"))
        if aktif:
            pins = [x for x in store.get_pins(w["id"]).values() if x.get("price")]
            for i, x in enumerate(sorted(pins, key=lambda y: y["price"])):
                isaret = "" if i == 0 else "•"
                p.append("   " + isaret + " " + x["site"] + ": " + fmt(x["price"]) + " TL")
        p.append("")

    p.append("⏸ Takip <b>duraklatıldı</b> — /ac" if _durakta()
             else "▶ Takip <b>açık</b> — /kapat ile durdur")
    p.append("Bildirim: <b>" + ("tam liste" if _mod() == "hepsi" else "sadece fiyat düşünce")
             + "</b> · Aralık: <b>" + str(_aralik()) + " dk</b>")
    p.append("Silmek için: <code>/sil 3</code>   Hepsi için: <code>/sil hepsi</code>")
    await gonder(chat, "\n".join(p))



async def _cmd_sil(chat: str, arg: str):
    if not arg:
        await gonder(chat, "Kullanım: <code>/sil 3</code> ya da <code>/sil hepsi</code>")
        return
    if arg in ("hepsi", "tumu", "tümü"):
        n = sum(1 for w in store.get_watches(only_active=False)
                if store.remove_watch(w["id"]))
        await gonder(chat, " " + str(n) + " takip silindi.")
        return
    if not arg.isdigit():
        await gonder(chat, "Geçersiz numara. /liste ile bak.")
        return
    ok = store.remove_watch(int(arg))
    await gonder(chat, " #" + arg + " silindi." if ok else "Bulunamadı. /liste")

async def _cmd_durum(chat: str):
    son = engine.latest().get("ts", 0)
    siteler = ", ".join(s.key for s in engine.enabled_sites())
    t = "<b>Sistem durumu</b>\n"
    if son:
        t += "Son tarama: " + str(int(time.time()) - son) + " sn önce\n"
    else:
        t += "Son tarama: henüz yok\n"
    t += ("Takip: " + str(len(store.get_watches())) + " aktif\n"
          + "Aralık: " + str(_aralik()) + " dk\n"
          + "Bildirim: " + ("tam liste" if _mod() == "hepsi" else "sadece fiyat düşünce") + "\n"
          + "Durum: " + ("DURAKLATILDI (/ac)" if _durakta() else "açık") + "\n"
          + "Siteler: " + siteler)
    await gonder(chat, t)

# sohbet temizleme / bakim
async def _sil_mesaj(chat: str, mid: int) -> bool:
    # Telegram 48 saatten eski mesajlari sildirmiyor.
    r = await _call("deleteMessage", chat_id=chat, message_id=mid)
    return r is not None



async def _cmd_temizle(chat: str, arg: str):
    hepsi = arg in ("hepsi", "tumu", "tümü")
    bilinen = store.get_messages(chat, 400 if hepsi else 60)
    if not bilinen:
        await gonder(chat, "Silinecek kayıtlı mesaj yok.")
        return


    silinen = 0
    for mid in bilinen:
        if await _sil_mesaj(chat, mid):
            silinen += 1
    store.forget_messages(chat, bilinen)

    if hepsi:
        # sadece id'sini bildigimiz mesajlari silebiliyoruz
        enYeni = max(bilinen)
        for i in range(1, 200):
            if enYeni - i <= 0:
                break
            if await _sil_mesaj(chat, enYeni - i):
                silinen += 1

    await gonder(chat, " " + str(silinen) + " mesaj silindi.")


async def _cmd_yeniden(chat: str):
    import subprocess
    import sys
    await gonder(chat, " Backend yeniden başlatılıyor… birkaç saniye.")
    try:
        subprocess.Popen([sys.executable, str(config.BASE_DIR / "run.py")],
                         cwd=str(config.BASE_DIR),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                         | getattr(subprocess, "DETACHED_PROCESS", 0))
    except Exception as e:
        await gonder(chat, " Yeniden başlatılamadı: " + esc(str(e)))
        return

    await asyncio.sleep(2)
    logger.info("Yeniden baslatma istendi, bu surec kapaniyor.")
    import os
    os._exit(0)


# ayar anahtarlari
S_HEDEF = "hedef_"          # hedef_<watch_id>
S_ESIK_TL = "esik_tl"
S_ESIK_PCT = "esik_pct"
S_COKLU = "coklu"
S_KAPALI_SITE = "kapali_siteler"



def _esik_tl() -> float:
    try:
        return float(store.get_setting(S_ESIK_TL, str(DROP_MIN_TL)))
    except ValueError:
        return DROP_MIN_TL


def _esik_pct() -> float:
    try:
        return float(store.get_setting(S_ESIK_PCT, str(DROP_MIN_PCT)))
    except ValueError:
        return DROP_MIN_PCT


def _coklu() -> bool:
    # varsayilan acik
    return store.get_setting(S_COKLU, "1") == "1"

def _aktif_watch() -> dict | None:
    ws = store.get_watches()
    return ws[0] if ws else None

# fiyat analizı

async def _cmd_gecmis(chat: str, arg: str):
    ws = store.get_watches()
    if not ws:
        await gonder(chat, "Aktif takip yok.")
        return
    gun = int(arg) if arg.isdigit() and 1 <= int(arg) <= 365 else 30

    p = []
    for w in ws:
        ozet = store.price_summary(w["id"], gun)
        p.append(" <b>" + esc(w["label"] or w["query"]) + "</b>")
        if not ozet.get("n"):
            p.append("   Henüz yeterli ölçüm yok.")
            p.append("")
            continue
        p.append("   Son " + str(gun) + " gün · " + str(ozet["n"]) + " ölçüm")
        p.append("   En düşük: <b>" + fmt(ozet["dip"]) + " TL</b>")
        p.append("   Ortalama: " + fmt(ozet["ort"]) + " TL")
        p.append("   En yüksek: " + fmt(ozet["tepe"]) + " TL")
        dip = store.all_time_low(w["id"])
        if dip:
            gun_once = int((time.time() - dip["ts"]) / 86400)
            ne_zaman = "bugün" if gun_once == 0 else str(gun_once) + " gün önce"
            p.append("   Tüm zamanların dibi: <b>" + fmt(dip["price"]) +
                     " TL</b> (" + dip["site"] + ", " + ne_zaman + ")")
        p.append("")
    await gonder(chat, "\n".join(p))


async def _cmd_ortalama(chat: str):
    ws = store.get_watches()
    if not ws:
        await gonder(chat, "Aktif takip yok.")
        return
    payload = engine.latest()
    p = []
    for w in ws:
        ozet = store.price_summary(w["id"], 30)
        simdi = None
        for pw in payload.get("watches") or []:
            if pw["id"] == w["id"] and pw.get("items"):
                simdi = pw["items"][0]["p"]
                break

        p.append(" <b>" + esc(w["label"] or w["query"]) + "</b>")
        if not ozet.get("n") or simdi is None:
            p.append("   Karşılaştırma için yeterli ölçüm yok.")
            p.append("")
            continue

        ort = ozet["ort"]
        fark = (simdi - ort) / ort * 100 if ort else 0
        p.append("   Şu an: <b>" + fmt(simdi) + " TL</b>")
        p.append("   30 gün ortalaması: " + fmt(ort) + " TL")
        if fark < -0.5:
            p.append("    Ortalamanın <b>%" + ("%.1f" % abs(fark)) + " ALTINDA</b>")
        elif fark > 0.5:
            p.append("    Ortalamanın <b>%" + ("%.1f" % fark) + " ÜSTÜNDE</b>")
        else:
            p.append("    Ortalamayla aynı seviyede")
        if abs(simdi - ozet["dip"]) < 0.01:
            p.append("    <b>Gördüğümüz en düşük fiyat!</b>")
        else:
            p.append("   Dipten farkı: " + fmt(simdi - ozet["dip"]) + " TL")
        p.append("")
    await gonder(chat, "\n".join(p))

async def _cmd_enucuz(chat: str):
    ws = store.get_watches()
    if not ws:
        await gonder(chat, "Aktif takip yok.")
        return
    p = []
    for w in ws:
        dip = store.all_time_low(w["id"])
        p.append(" <b>" + esc(w["label"] or w["query"]) + "</b>")
        if not dip:
            p.append("   Kayıt yok.")
        else:
            gun_once = int((time.time() - dip["ts"]) / 86400)
            ne_zaman = "bugün" if gun_once == 0 else str(gun_once) + " gün önce"
            p.append("   <b>" + fmt(dip["price"]) + " TL</b> — " +
                     dip["site"] + ", " + ne_zaman)
            p.append("   <a href=\"" + html.escape(dip["url"], quote=True) +
                     "\">ürüne git</a>")
        p.append("")
    await gonder(chat, "\n".join(p))


# hedef ve esik

async def _cmd_hedef(chat: str, arg: str):
    w = _aktif_watch()
    if not w:
        await gonder(chat, "Aktif takip yok. Önce bir ürün seç.")
        return
    anahtar = S_HEDEF + str(w["id"])

    if not arg:
        mevcut = store.get_setting(anahtar, "")
        if mevcut:
            await gonder(chat, " Hedef fiyat: <b>" + fmt(float(mevcut)) + " TL</b>\n"
                               "Kaldırmak için: <code>/hedef kapat</code>")
        else:
            await gonder(chat, "Hedef fiyat ayarlı değil.\n"
                               "Ayarlamak için: <code>/hedef 25000</code>")
        return

    if arg in ("kapat", "sil", "yok"):
        store.set_setting(anahtar, "")
        await gonder(chat, " Hedef fiyat kaldırıldı.")
        return

    try:
        hedef = float(arg.replace(".", "").replace(",", "."))
    except ValueError:
        await gonder(chat, "Sayı yaz. Örnek: <code>/hedef 25000</code>")
        return
    if hedef <= 0:
        await gonder(chat, "Geçersiz fiyat.")
        return

    store.set_setting(anahtar, hedef)
    await gonder(chat, " Hedef fiyat <b>" + fmt(hedef) + " TL</b> olarak ayarlandı.\n"
                       "Bu fiyatın altına inince özel uyarı gelecek.")
def _hedef_kontrol(payload: dict) -> str:
    bloklar = []
    for w in payload.get("watches") or []:
        anahtar = S_HEDEF + str(w["id"])
        ham = store.get_setting(anahtar, "")
        if not ham:
            continue
        try:
            hedef = float(ham)
        except ValueError:
            continue
        items = w.get("items") or []
        if not items:
            continue
        en_ucuz = items[0]


        if en_ucuz["p"] > hedef:
            store.set_setting(anahtar + "_vuruldu", "0")
            continue
        if store.get_setting(anahtar + "_vuruldu", "0") == "1":
            continue                       # bu hedef icin zaten yazildi
        store.set_setting(anahtar + "_vuruldu", "1")
        bloklar.append(
            " <b>HEDEF FİYAT YAKALANDI</b>\n"
            "<i>" + esc(w["q"]) + "</i>\n\n"
            "Hedef: " + fmt(hedef) + " TL\n"
            "Şu an: <b>" + fmt(en_ucuz["p"]) + " TL</b>  (" + esc(en_ucuz["s"]) + ")\n"
            "   <a href=\"" + html.escape(en_ucuz["u"], quote=True) + "\">"
            + esc(en_ucuz["n"][:52]) + "</a>")
    return "\n\n".join(bloklar)

async def _cmd_esik(chat: str, arg: str):
    if not arg:
        await gonder(chat, "Düşüş bildirimi eşiği:\n"
                           "   En az <b>" + fmt(_esik_tl()) + " TL</b>"
                           " <i>ya da</i> <b>%" + str(_esik_pct()) + "</b>\n\n"
                           "Değiştir: <code>/esik 200</code> veya <code>/esik %5</code>")
        return
    try:
        if arg.startswith("%"):
            store.set_setting(S_ESIK_PCT, float(arg[1:].replace(",", ".")))
            await gonder(chat, " Yüzde eşiği <b>%" + arg[1:] + "</b> oldu.")
        else:
            store.set_setting(S_ESIK_TL, float(arg.replace(".", "").replace(",", ".")))
            await gonder(chat, " TL eşiği <b>" + arg + " TL</b> oldu.")
    except ValueError:
        await gonder(chat, "Örnek: <code>/esik 200</code> veya <code>/esik %5</code>")

# takip yonetimi

async def _cmd_coklu(chat: str, arg: str):
    if arg in ("ac", "aç", "1", "acik"):
        store.set_setting(S_COKLU, "1")
        await gonder(chat, " <b>Çoklu takip açık</b>\n"
                           "Yeni aramalar eskisini kapatmayacak; birden fazla ürünü "
                           "aynı anda izleyebilirsin.")
    elif arg in ("kapat", "0", "kapali"):
        store.set_setting(S_COKLU, "0")
        await gonder(chat, " <b>Tek takip modu</b>\n"
                           "Yeni arama öncekinin yerine geçecek.")
    else:
        durum = "açık" if _coklu() else "kapalı"
        await gonder(chat, "Çoklu takip: <b>" + durum + "</b>\n\n"
                           "<code>/coklu ac</code> · <code>/coklu kapat</code>")
async def _cmd_aktif(chat: str, arg: str):
    if not arg.isdigit():
        await gonder(chat, "Kullanım: <code>/aktif 3</code>\nNumaraları /liste ile gör.")
        return
    if store.activate_watch(int(arg)):
        if not _coklu():
            store.deactivate_others(int(arg))
        await gonder(chat, "▶ #" + arg + " tekrar aktif.")
        await _cmd_liste(chat)
    else:
        await gonder(chat, "Bulunamadı. /liste")

async def _cmd_duzenle(chat: str, arg: str):
    ws = store.get_watches(only_active=False)
    hedef = None
    if arg.isdigit():
        hedef = next((w for w in ws if w["id"] == int(arg)), None)
    else:
        hedef = next((w for w in ws if w["active"] == 1), None)


    if not hedef:
        await gonder(chat, "Takip bulunamadı. /liste")
        return
    if not hedef.get("spec"):
        await gonder(chat, "Bu takip serbest sorguyla kurulmuş, filtre menüsü yok.\n"
                           "<code>" + esc(hedef["query"]) + "</code>")
        return

    d = json.loads(hedef["spec"])
    cat = catalog.CATEGORIES.get(d.get("cat"))
    if not cat:
        await gonder(chat, "Kategori tanınmadı.")
        return

    by_group: dict = {}
    for key in d.get("sel") or []:
        for g in cat.groups:
            if any(o.k == key for o in g.options):
                by_group.setdefault(g.k, []).append(key)
                break

    _ses[chat] = {"cat": cat.k, "sel_by_group": by_group, "menu_id": 0}
    r = await gonder(chat, _ana_metin(chat), _ana_klavye(chat))
    if r:
        _ses[chat]["menu_id"] = r["message_id"]


# serbest arama


async def _cmd_ara(chat: str, arg: str):
    if not arg:
        await gonder(chat,
            "Serbest arama — filtre menüsü olmadan:\n\n"
            "<code>/ara ddr5 32gb 6000 -notebook</code>\n\n"
            "<b>Yazım</b>\n"
            "• boşlukla ayrılan kelimelerin <b>hepsi</b> geçmeli\n"
            "• <code>-kelime</code> → geçenleri ele\n"
            "• <code>(a|b)</code> → en az biri geçmeli\n"
            "• <code>\"iki kelime\"</code> → bu metin sitelere gönderilir")
        return

    await gonder(chat, "⏳ 8 sitede aranıyor…")
    wid = store.add_watch(arg, "Serbest: " + arg[:60])
    if not _coklu():
        store.deactivate_others(wid)
    payload = await engine.run_cycle(wait=True)
    await gonder(chat, sonuc_mesaji(payload))

async def _cmd_kategoriler(chat: str):
    p = ["<b>Desteklenen kategoriler</b>\n"]
    for c in catalog.CATEGORIES.values():
        gruplar = ", ".join(g.l for g in c.groups)
        p.append("• <b>" + esc(c.l) + "</b>")
        p.append("   yaz: <code>" + esc(c.aliases[0]) + "</code>")
        p.append("   filtreler: " + esc(gruplar))
        p.append("")
    p.append("Katalog dışı arama için: <code>/ara ...</code>")
    await gonder(chat, "\n".join(p))

# siteler

async def _cmd_siteler(chat: str):
    payload = engine.latest()
    bulunan: dict = {}
    for w in payload.get("watches") or []:
        for it in w.get("items") or []:
            bulunan[it["s"]] = it

    kapali = set(x for x in store.get_setting(S_KAPALI_SITE, "").split(",") if x)
    p = ["<b>Siteler</b>\n"]
    for s in engine.enabled_sites():
        it = bulunan.get(s.key)
        motor = "Chrome" if s.engine == "pw" else "hızlı"
        if s.key in kapali:
            p.append(" <b>" + s.key + "</b> — kapalı (" + motor + ")")
        elif it:
            eski = " <i>(eski)</i>" if it.get("old") else ""
            p.append(" <b>" + s.key + "</b> — " + fmt(it["p"]) + " TL" + eski
                     + "  <i>" + motor + "</i>")
        else:
            p.append(" <b>" + s.key + "</b> — son turda eşleşme yok  <i>"
                     + motor + "</i>")
    p.append("\nKapatmak: <code>/site kapat trendyol</code>")
    p.append("Açmak: <code>/site ac trendyol</code>")
    p.append("<i>Chrome ile çalışanlar turu ~20 sn uzatıyor.</i>")
    await gonder(chat, "\n".join(p))

async def _cmd_site(chat: str, arg: str):
    parca = arg.split()
    if len(parca) != 2 or parca[0] not in ("ac", "aç", "kapat"):
        await gonder(chat, "Kullanım: <code>/site kapat trendyol</code>")
        return
    islem, key = parca[0], parca[1].lower()

    from sites import SITES_BY_KEY
    if key not in SITES_BY_KEY:
        await gonder(chat, "Bilinmeyen site. /siteler ile bak.")
        return

    kapali = set(x for x in store.get_setting(S_KAPALI_SITE, "").split(",") if x)
    if islem == "kapat":
        kapali.add(key)
        mesaj = " <b>" + key + "</b> kapatıldı."
    else:
        kapali.discard(key)
        mesaj = " <b>" + key + "</b> açıldı."
    store.set_setting(S_KAPALI_SITE, ",".join(sorted(kapali)))
    await gonder(chat, mesaj + "\nSonraki turdan itibaren geçerli.")

# sessiz saatler / stok / LOG / yedek / rapor


S_SESSIZ_BAS = "sessiz_bas"      # "23:00"
S_SESSIZ_BIT = "sessiz_bit"      # "08:00"
S_STOK = "stok_uyari"            # "1" -> stok degisiminde haber ver
S_RAPOR = "rapor_saat"           # "09:00" -> gunluk ozet saati "" -> kapali



def _sessiz_saatte() -> bool:
    bas = store.get_setting(S_SESSIZ_BAS, "")
    bit = store.get_setting(S_SESSIZ_BIT, "")
    if not bas or not bit:
        return False
    try:
        sb, sd = [int(x) for x in bas.split(":")]
        eb, ed = [int(x) for x in bit.split(":")]
    except ValueError:
        return False

    simdi = time.localtime()
    dk = simdi.tm_hour * 60 + simdi.tm_min
    basdk, bitdk = sb * 60 + sd, eb * 60 + ed
    if basdk <= bitdk:
        return basdk <= dk < bitdk
    return dk >= basdk or dk < bitdk       # gece yarisini asiyor
async def _cmd_sessiz(chat: str, arg: str):
    if arg in ("kapat", "sil", "yok"):
        store.set_setting(S_SESSIZ_BAS, "")
        store.set_setting(S_SESSIZ_BIT, "")
        await gonder(chat, " Sessiz saat kapatıldı, bildirimler her saat gelir.")
        return

    if not arg:
        bas = store.get_setting(S_SESSIZ_BAS, "")
        bit = store.get_setting(S_SESSIZ_BIT, "")
        if bas and bit:
            durum = " (şu an sessiz)" if _sessiz_saatte() else ""
            await gonder(chat, " Sessiz saat: <b>" + bas + " – " + bit + "</b>"
                               + durum + "\n\nKapatmak: <code>/sessiz kapat</code>")
        else:
            await gonder(chat, "Sessiz saat ayarlı değil.\n"
                               "Ayarlamak: <code>/sessiz 23:00 08:00</code>")
        return

    parca = arg.split()
    if len(parca) != 2:
        await gonder(chat, "Kullanım: <code>/sessiz 23:00 08:00</code>")
        return
    for p in parca:
        if ":" not in p or not p.replace(":", "").isdigit():
            await gonder(chat, "Saat biçimi: <code>23:00</code>")
            return
    store.set_setting(S_SESSIZ_BAS, parca[0])
    store.set_setting(S_SESSIZ_BIT, parca[1])
    await gonder(chat, " Sessiz saat <b>" + parca[0] + " – " + parca[1] +
                       "</b> olarak ayarlandı.\n"
                       "<i>Bu aralıkta tarama sürer ama mesaj gelmez.</i>")


async def _cmd_stok(chat: str, arg: str):
    if arg in ("ac", "aç", "1"):
        store.set_setting(S_STOK, "1")
        await gonder(chat, " Stok uyarısı <b>açık</b>.\n"
                           "Takip ettiğin ürün stoktan çıkarsa ya da geri gelirse "
                           "haber vereceğim.")
    elif arg in ("kapat", "0"):
        store.set_setting(S_STOK, "0")
        await gonder(chat, " Stok uyarısı kapatıldı.")
    else:
        durum = "açık" if store.get_setting(S_STOK, "0") == "1" else "kapalı"
        await gonder(chat, "Stok uyarısı: <b>" + durum + "</b>\n\n"
                           "<code>/stok ac</code> · <code>/stok kapat</code>")

def stok_mesaji(payload: dict) -> str:
    if store.get_setting(S_STOK, "0") != "1":
        return ""
    bloklar = []
    for w in payload.get("watches") or []:
        satirlar = []
        for it in w.get("items") or []:
            sd = it.get("sd")
            if not sd:
                continue
            if sd > 0:
                satirlar.append(" <b>" + esc(it["s"]) + "</b> — STOĞA GİRDİ  "
                                + fmt(it["p"]) + " TL\n   <a href=\""
                                + html.escape(it["u"], quote=True) + "\">"
                                + esc(it["n"][:52]) + "</a>")
            else:
                satirlar.append(" <b>" + esc(it["s"]) + "</b> — tükendi  "
                                + esc(it["n"][:52]))
        if satirlar:
            bloklar.append(" <b>STOK DEĞİŞİMİ</b>\n<i>" + esc(w["q"]) + "</i>\n\n"
                           + "\n\n".join(satirlar))
    return "\n\n".join(bloklar)



# log / yedek

def _gizle(metin: str) -> str:
    tok = config.TELEGRAM_BOT_TOKEN
    if tok and tok in metin:
        metin = metin.replace(tok, "***TOKEN***")
    # bot tokenini de yakala
    return re.sub(r"bot\d+:[A-Za-z0-9_\-]+", "bot***", metin)


async def _cmd_log(chat: str, arg: str):
    n = int(arg) if arg.isdigit() and 1 <= int(arg) <= 100 else 25
    yol = config.BASE_DIR / "backend.log"
    if not yol.exists():
        await gonder(chat, "Log dosyası yok.")
        return
    try:
        satirlar = yol.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        await gonder(chat, "Log okunamadı: " + esc(str(e)[:100]))
        return

    onemli = [s for s in satirlar
              if "WARNING" in s or "ERROR" in s or "Traceback" in s][-n:]
    if not onemli:
        await gonder(chat, " Son loglarda uyarı/hata yok.\n"
                           "<i>Toplam " + str(len(satirlar)) + " satır.</i>")
        return

    # zaman damgasi ve modul adini kirp ekrana sigsin
    kisa = []
    for s in onemli:
        s = _gizle(s)
        parca = s.split("] ", 1)
        kisa.append(parca[1] if len(parca) > 1 else s)
    metin = " <b>Son " + str(len(kisa)) + " uyarı/hata</b>\n<pre>" \
            + esc("\n".join(kisa)[-3300:]) + "</pre>"
    await gonder(chat, metin)

async def _cmd_yedek(chat: str):
    import httpx
    yol = config.DB_PATH
    if not yol.exists():
        await gonder(chat, "Veritabanı bulunamadı.")
        return
    boyut = yol.stat().st_size
    if boyut > 45 * 1024 * 1024:
        await gonder(chat, "Veritabanı çok büyük (" + str(boyut // 1024 // 1024)
                           + " MB). Telegram sınırı 50 MB.")
        return

    url = API.format(token=config.TELEGRAM_BOT_TOKEN, method="sendDocument")
    aciklama = (" Veritabanı yedeği\n"
                + str(len(store.get_watches(only_active=False))) + " takip · "
                + str(boyut // 1024) + " KB\n"
                "<i>Fiyat geçmişi ve ayarlar. Token içermez.</i>")
    try:
        with open(yol, "rb") as f:
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(url,
                                 data={"chat_id": str(chat), "caption": aciklama,
                                       "parse_mode": "HTML"},
                                 files={"document": ("tracker.db", f.read(),
                                                     "application/octet-stream")})
        if r.status_code != 200:
            await gonder(chat, " Yedek gönderilemedi: " + esc(r.text[:120]))
    except Exception as e:
        await gonder(chat, " Yedek gönderilemedi: " + esc(str(e)[:120]))
# rapor

def rapor_metni() -> str:
    ws = store.get_watches()
    if not ws:
        return " <b>Günlük özet</b>\n\nAktif takip yok."

    payload = engine.latest()
    p = [" <b>Günlük özet</b>\n"]
    for w in ws:
        simdi = None
        for pw in payload.get("watches") or []:
            if pw["id"] == w["id"] and pw.get("items"):
                simdi = pw["items"][0]
                break

        p.append("<b>" + esc(w["label"] or w["query"]) + "</b>")
        if not simdi:
            p.append("   Son turda sonuç yok.")
            p.append("")
            continue

        gun = store.price_summary(w["id"], 1)
        ay = store.price_summary(w["id"], 30)
        p.append("   Şu an: <b>" + fmt(simdi["p"]) + " TL</b> (" + simdi["s"] + ")")
        if gun.get("n", 0) > 1:
            fark = simdi["p"] - gun["tepe"]
            ok = "" if fark < 0 else ("" if fark > 0 else "")
            p.append("   24 saat: " + ok + " " + fmt(abs(fark)) + " TL"
                     + "  (dip " + fmt(gun["dip"]) + ")")
        if ay.get("n", 0) > 1:
            konum = (simdi["p"] - ay["ort"]) / ay["ort"] * 100 if ay["ort"] else 0
            nerede = ("ortalamanın %" + ("%.1f" % abs(konum))
                      + (" altında" if konum < 0 else " üstünde"))
            p.append("   30 gün: dip " + fmt(ay["dip"]) + " · " + nerede)
        p.append("   <a href=\"" + html.escape(simdi["u"], quote=True) + "\">"
                 + esc(simdi["n"][:48]) + "</a>")
        p.append("")
    return "\n".join(p)

async def _cmd_rapor(chat: str, arg: str):
    if arg in ("kapat", "sil"):
        store.set_setting(S_RAPOR, "")
        _rapor_guncelle("")
        await gonder(chat, " Günlük özet kapatıldı.")
        return
    if arg and ":" in arg:
        store.set_setting(S_RAPOR, arg)
        _rapor_guncelle(arg)
        await gonder(chat, " Günlük özet her gün <b>" + arg + "</b> saatinde gelecek.")
        return
    if arg:
        await gonder(chat, "Kullanım: <code>/rapor 09:00</code> · <code>/rapor kapat</code>")
        return
    await gonder(chat, rapor_metni())


# run.py doldurur rapor saatini zamanlayiciya yansitir
_rapor_zamanla = None


def _rapor_guncelle(saat: str):
    if _rapor_zamanla:
        _rapor_zamanla(saat)



async def gunluk_rapor_gonder():
    for chat in _yetkili():
        await gonder(chat, rapor_metni())


# filtreler


async def _cmd_filtreler(chat: str, arg: str):
    cat = catalog.resolve(arg) if arg else None
    if not cat:
        await gonder(chat, "Hangi kategori? Örnek: <code>/filtreler ram</code>\n"
                           "Liste için /kategoriler")
        return
    p = [" <b>" + esc(cat.l) + " filtreleri</b>\n"]
    for g in cat.groups:
        tip = "çoklu seçim" if g.multi else "tek seçim"
        p.append("<b>" + esc(g.l) + "</b>  <i>(" + tip + ")</i>")
        p.append("   " + esc(" · ".join(o.l for o in g.options)))
        p.append("")
    await gonder(chat, "\n".join(p))

async def _metin_isle(chat: str, metin: str):
    parca = metin.split(maxsplit=1)
    cmd = parca[0].split("@")[0].lower()
    arg = parca[1].strip() if len(parca) > 1 else ""

    if cmd in ("/start", "/yardim", "/help"):
        await gonder(chat, YARDIM)

    elif cmd == "/liste":
        await _cmd_liste(chat)

    elif cmd == "/simdi":
        if not store.get_watches():
            await gonder(chat, "Önce bir ürün seç. Örnek: <code>ram</code>")
            return
        await gonder(chat, "⏳ 8 sitede aranıyor…")
        payload = await engine.run_cycle(wait=True)
        await gonder(chat, sonuc_mesaji(payload))

    elif cmd == "/sil":
        await _cmd_sil(chat, arg)

    elif cmd == "/mod":
        if arg in ("hepsi", "liste"):
            store.set_setting(S_MOD, "hepsi")
            await gonder(chat, " <b>Tam liste modu</b>\nHer turda bütün liste gelecek.")
        elif arg in ("dusus", "düşüş", "sessiz"):
            store.set_setting(S_MOD, "dusus")
            await gonder(chat, " <b>Sessiz mod</b>\nArtık sadece <b>fiyat düştüğünde</b> "
                               "mesaj gelecek. Listeyi görmek için /simdi.")
        else:
            simdiki = "tam liste" if _mod() == "hepsi" else "sadece fiyat düşünce"
            await gonder(chat, "Şu anki mod: <b>" + simdiki + "</b>\n\n"
                               "<code>/mod dusus</code> · <code>/mod hepsi</code>")

    elif cmd == "/sure":
        if not arg:
            await gonder(chat, "Kontrol aralığı: <b>" + str(_aralik()) + " dakika</b>\n"
                               "Değiştirmek için: <code>/sure 15</code> (2–1440)")
            return
        try:
            dk = int(arg)
        except ValueError:
            dk = 0
        if not (2 <= dk <= 1440):
            await gonder(chat, "2 ile 1440 dakika arasında bir değer yaz.")
            return
        store.set_setting(S_ARALIK, dk)
        _yeniden_zamanla(dk)
        await gonder(chat, "⏱ Kontrol aralığı <b>" + str(dk) + " dakika</b> olarak ayarlandı.")

    elif cmd in ("/kapat", "/dur"):
        store.set_setting(S_DURAK, "1")
        saat = int(arg) if arg.isdigit() else 0
        if 0 < saat <= 168:
            store.set_setting(S_DURAK_BITIS, time.time() + saat * 3600)
            await gonder(chat, " Takip <b>durduruldu</b>.\n" + str(saat) +
                               " saat sonra kendiliğinden açılacak. Erken açmak için /ac")
        else:
            store.set_setting(S_DURAK_BITIS, "0")
            await gonder(chat, " Takip <b>durduruldu</b>. Mesaj gelmeyecek.\n"
                               "/ac ile açarsın.\n\nSüreli: <code>/kapat 5</code> (5 saat)")

    elif cmd in ("/ac", "/aç", "/devam"):
        store.set_setting(S_DURAK, "0")
        store.set_setting(S_DURAK_BITIS, "0")
        await gonder(chat, "▶ Takip yeniden açıldı.")

    elif cmd == "/gecmis":
        await _cmd_gecmis(chat, arg)

    elif cmd in ("/ortalama", "/ort"):
        await _cmd_ortalama(chat)

    elif cmd == "/enucuz":
        await _cmd_enucuz(chat)

    elif cmd == "/hedef":
        await _cmd_hedef(chat, arg)


    elif cmd == "/esik":
        await _cmd_esik(chat, arg)

    elif cmd == "/coklu":
        await _cmd_coklu(chat, arg)

    elif cmd == "/aktif":
        await _cmd_aktif(chat, arg)

    elif cmd == "/duzenle":
        await _cmd_duzenle(chat, arg)
    elif cmd == "/ara":
        await _cmd_ara(chat, arg)


    elif cmd in ("/kategoriler", "/kategori"):
        await _cmd_kategoriler(chat)

    elif cmd == "/siteler":
        await _cmd_siteler(chat)

    elif cmd == "/site":
        await _cmd_site(chat, arg)
    elif cmd == "/sessiz":
        await _cmd_sessiz(chat, arg)
    elif cmd == "/stok":
        await _cmd_stok(chat, arg)

    elif cmd == "/rapor":
        await _cmd_rapor(chat, arg)

    elif cmd == "/filtreler":
        await _cmd_filtreler(chat, arg)


    elif cmd == "/log":
        await _cmd_log(chat, arg)

    elif cmd == "/yedek":
        await _cmd_yedek(chat)

    elif cmd == "/temizle":
        await _cmd_temizle(chat, arg)
    elif cmd == "/yeniden":
        await _cmd_yeniden(chat)

    elif cmd == "/durum":
        await _cmd_durum(chat)

    elif cmd.startswith("/"):
        await gonder(chat, "Bilinmeyen komut. /yardim")

    else:
        # menu acikken yazilan metin kategori degilse model
        if chat in _ses and not catalog.resolve(metin):
            await _model_yaz(chat, metin)
        else:
            await _kategori_baslat(chat, metin)
# butonlar

async def _buton_isle(chat: str, cb_id: str, data: str, msg_id: int):
    await _cb_cevap(cb_id)

    if chat not in _ses:
        await gonder(chat, "Oturum sıfırlandı. Ne aradığını tekrar yaz "
                           "(örn. <code>ram</code>).")
        return
    s = _ses[chat]
    s["menu_id"] = msg_id
    cat = catalog.CATEGORIES[s["cat"]]

    if data == "m":
        await duzenle(chat, msg_id, _ana_metin(chat), _ana_klavye(chat))

    elif data == "c":
        s["sel_by_group"] = {}
        await duzenle(chat, msg_id, _ana_metin(chat), _ana_klavye(chat))

    elif data.startswith("g:"):
        gkey = data[2:]
        grup = next((g for g in cat.groups if g.k == gkey), None)
        if not grup:
            return
        t = (" <b>" + esc(cat.l) + "</b> › <b>" + esc(grup.l) + "</b>\n\n"
             + ("Birden fazla seçebilirsin." if grup.multi else "Tek seçim yapabilirsin."))
        await duzenle(chat, msg_id, t, _grup_klavye(chat, gkey))

    elif data.startswith("o:"):
        _, gkey, okey = data.split(":", 2)
        grup = next((g for g in cat.groups if g.k == gkey), None)
        if not grup:
            return
        secili = s["sel_by_group"].setdefault(gkey, [])
        if okey in secili:
            secili.remove(okey)
        else:
            if not grup.multi:
                secili.clear()          # tek secimlik grupta yenisi eskinin yerine
            secili.append(okey)
        t = (" <b>" + esc(cat.l) + "</b> › <b>" + esc(grup.l) + "</b>\n\n"
             + ("Birden fazla seçebilirsin." if grup.multi else "Tek seçim yapabilirsin."))
        await duzenle(chat, msg_id, t, _grup_klavye(chat, gkey))
    elif data == "s":
        await _ara(chat)


async def _ara(chat: str):
    s = _ses.get(chat)
    if not s:
        return
    sel = [k for ks in s["sel_by_group"].values() for k in ks]
    cat = catalog.CATEGORIES[s["cat"]]
    model = s.get("model", "")
    built = catalog.build(cat, sel, model)

    await gonder(chat, "⏳ 8 sitede aranıyor, yaklaşık yarım dakika…")

    wid = store.add_watch(built["query"], built["label"],
                          json.dumps({"cat": cat.k, "sel": sel,
                                      "model": model}))
    if not _coklu():                 # coklu modda onceki takipler kalsin
        store.deactivate_others(wid)


    payload = await engine.run_cycle(wait=True)
    await gonder(chat, sonuc_mesaji(payload))

    simdiki = "tam liste" if _mod() == "hepsi" else "sadece fiyat düşünce"
    await gonder(chat, " Takibe alındı. Her " + str(_aralik()) +
                       " dakikada bir kontrol edilecek.\nBildirim: <b>" +
                       simdiki + "</b> (/mod)")
    _ses.pop(chat, None)


# periyodik bildirım

# run py burayi doldurur
_zamanlayici_guncelle = None

def _yeniden_zamanla(dk: int):
    if _zamanlayici_guncelle:
        _zamanlayici_guncelle(dk)



async def tur_sonrasi(payload: dict):
    global _son_ts
    ts = payload.get("ts", 0)
    if ts == _son_ts:                      # ayni sonucu iki kez bildirme
        return
    _son_ts = ts

    if _sessiz_saatte():
        logger.info("Sessiz saatteyiz, bildirim atlandi.")
        return

    if _durakta():
        logger.info("Takip duraklatildi, bildirim atlandi.")
        return

    hedefler = _yetkili()
    if not hedefler:
        return

    hedefler_mesaji = _hedef_kontrol(payload)

    dusus = dusus_mesaji(payload)
    stok = stok_mesaji(payload)
    for chat in hedefler:
        if hedefler_mesaji:
            await gonder(chat, hedefler_mesaji)
        if dusus:
            await gonder(chat, dusus)
        if stok:
            await gonder(chat, stok)
        if _mod() == "hepsi":
            await gonder(chat, sonuc_mesaji(payload))

    if not dusus and _mod() != "hepsi":
        logger.info("Dusus yok, sessiz mod -- mesaj atilmadi.")


# ana dongu

async def run_bot():
    if not config.TELEGRAM_BOT_TOKEN or not _yetkili():
        logger.warning("Telegram kapali: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID eksik.")
        return

    logger.info("Telegram botu acik. Yetkili sohbetler: %s",
                ", ".join(sorted(_yetkili())))
    offset = None
    while True:
        try:
            updates = await _call("getUpdates", offset=offset, timeout=50,
                                  allowed_updates=["message", "callback_query"])
            for u in updates or []:
                offset = u["update_id"] + 1
                if "message" in u:
                    m = u["message"]
                    chat = str(m.get("chat", {}).get("id", ""))
                    if chat not in _yetkili():
                        logger.info("Yetkisiz chat_id: %s", chat)
                        continue
                    store.log_message(chat, m.get("message_id"))
                    metin = (m.get("text") or "").strip()
                    if metin:
                        logger.info("Telegram mesaj: %s", metin)
                        await _metin_isle(chat, metin)
                elif "callback_query" in u:
                    cq = u["callback_query"]
                    chat = str(cq.get("message", {}).get("chat", {}).get("id", ""))
                    if chat not in _yetkili():
                        continue
                    await _buton_isle(chat, cq["id"], cq.get("data", ""),
                                      cq["message"]["message_id"])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Telegram dongu hatasi: %s", e)
            await asyncio.sleep(5)
