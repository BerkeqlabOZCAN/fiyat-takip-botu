from __future__ import annotations

# pythonw ile acilinca stdout/stderr None oluyor
import os as _os
import sys as _sys

HAS_CONSOLE = _sys.stderr is not None
if _sys.stdout is None:
    _sys.stdout = open(_os.devnull, "w")
if _sys.stderr is None:
    _sys.stderr = open(_os.devnull, "w")


import argparse
import asyncio
import logging
import socket
import sys
from logging.handlers import RotatingFileHandler

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

import config
from config import BASE_DIR
import engine
import store
import telegram_bot
from api import app

# konsol varşa ekrana da yaz
_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_handlers = [RotatingFileHandler(BASE_DIR / "backend.log", maxBytes=5 * 1024 * 1024,
                                 backupCount=3, encoding="utf-8")]
if HAS_CONSOLE:
    _handlers.append(logging.StreamHandler(sys.stderr))

logging.basicConfig(level=config.LOG_LEVEL, format=_LOG_FMT, handlers=_handlers)
for noisy in ("httpx", "httpcore", "apscheduler", "uvicorn.access"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger("run")

def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


async def _once(query: str) -> int:
    store.init_db()
    per_site = await engine.search_everywhere(query)
    print()
    print(f"  {'SITE':<14}{'FIYAT':>14}   URUN")
    print("  " + "-" * 92)
    rows = []
    for site_key, offers in per_site.items():
        if offers:
            rows.append((site_key, offers[0]))
    for site_key, o in sorted(rows, key=lambda r: r[1].price):
        print(f"  {site_key:<14}{o.price:>14,.2f}   {o.name[:52]}")
        print(f"  {'':<14}{'':>14}   {o.url}")
    if not rows:
        print("  Hicbir sitede alakali sonuc yok.")
        return 1
    win_site, win = min(rows, key=lambda r: r[1].price)
    print()
    print(f"  EN UYGUN: {win.price:,.2f} TL  ({win_site})")
    return 0


async def _serve() -> None:
    store.init_db()

    scheduler = AsyncIOScheduler()
    # tur sonu bildirimi
    async def tara_ve_bildir():
        payload = await engine.run_cycle()
        await telegram_bot.tur_sonrasi(payload)

    scheduler.add_job(
        tara_ve_bildir,
        trigger=IntervalTrigger(minutes=telegram_bot._aralik()),
        id="price_cycle", replace_existing=True, max_instances=1, coalesce=True,
    )

    # sure degisince yenile
    def _araligi_degistir(dk: int):
        scheduler.reschedule_job("price_cycle", trigger=IntervalTrigger(minutes=dk))
        logger.info("Kontrol araligi %d dakika olarak guncellendi.", dk)


    telegram_bot._zamanlayici_guncelle = _araligi_degistir


    # /rapor <saat> gunluk ozeti zamanlar bos deger isi kaldirir
    def _raporu_ayarla(saat: str):
        try:
            scheduler.remove_job("gunluk_rapor")
        except Exception:
            pass
        if not saat or ":" not in saat:
            logger.info("Gunluk rapor kapali.")
            return
        sa, dk = saat.split(":")
        scheduler.add_job(telegram_bot.gunluk_rapor_gonder,
                          trigger=CronTrigger(hour=int(sa), minute=int(dk)),
                          id="gunluk_rapor", replace_existing=True)
        logger.info("Gunluk rapor her gun %s saatinde.", saat)

    telegram_bot._rapor_zamanla = _raporu_ayarla
    _raporu_ayarla(store.get_setting("rapor_saat", ""))

    scheduler.start()

    ip = lan_ip()
    logger.info("Zamanlayici aktif: her %d dakikada bir tarama.",
                telegram_bot._aralik())
    logger.info("Etkin siteler: %s", ", ".join(s.key for s in engine.enabled_sites()))
    logger.info("API: http://%s:%d", ip, config.API_PORT)
    logger.info("Test: http://%s:%d/api/best", ip, config.API_PORT)
    # acilista bir tur (API'yi bloklamadan)
    tasks = [asyncio.create_task(engine.run_cycle())]
    # telegram dongusu
    tasks.append(asyncio.create_task(telegram_bot.run_bot()))

    server = uvicorn.Server(uvicorn.Config(
        app, host=config.API_HOST, port=config.API_PORT,
        log_level=config.LOG_LEVEL.lower(), access_log=False,
        log_config=None,   # kendi stdout handler ini kurmasin
    ))
    try:
        await server.serve()
    finally:
        scheduler.shutdown(wait=False)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)



def main() -> int:
    ap = argparse.ArgumentParser(description="fiyat takip backend'i")
    ap.add_argument("--once", metavar="SORGU",
                    help="tek seferlik tarama yapip cik (API acmaz)")
    args = ap.parse_args()

    # windows'ta proactor loop kalmali playwright istiyor
    try:
        if args.once:
            return asyncio.run(_once(args.once))
        asyncio.run(_serve())
    except KeyboardInterrupt:
        logger.info("Kapatildi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
