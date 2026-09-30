from __future__ import annotations


import os
from pathlib import Path


try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).with_name(".env"))
except ImportError:  # python-dotenv yoksa sadece gercek env kullanilir
    pass
BASE_DIR = Path(__file__).parent



def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except ValueError:
        return default



def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")



def _list(key: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(key, default).split(",") if x.strip()]

# http sunucu
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = _int("API_PORT", 8787)
API_TOKEN = os.getenv("API_TOKEN", "").strip()      # bos ise kimlik dogrulama yok
# tarama
CHECK_INTERVAL_MINUTES = _int("CHECK_INTERVAL_MINUTES", 10)
ENABLED_SITES = _list("ENABLED_SITES",
                      "vatan,itopya,incehesap,n11,hepsiburada,gaminggen,trendyol,amazon")
HTTP_TIMEOUT = _int("HTTP_TIMEOUT", 25)
MAX_CONCURRENT = _int("MAX_CONCURRENT", 4)
# az sonuc gelirse sorguyu genislet
RETRY_BROADER = _bool("RETRY_BROADER", True)
MIN_RAW_RESULTS = _int("MIN_RAW_RESULTS", 8)
# en ucuz urun genelde ilk sayfada olmuyor
SEARCH_PAGES = _int("SEARCH_PAGES", 3)
PW_SEARCH_PAGES = _int("PW_SEARCH_PAGES", 2)   # Playwright yavas daha az sayfa

# kazanan urunu kendı sayfasindan dogrula
VERIFY_WINNER = _bool("VERIFY_WINNER", True)
VERIFY_MAX_TRIES = _int("VERIFY_MAX_TRIES", 8)   # ucuzdan kaca kadar bakilsın
VERIFY_TTL_HOURS = _int("VERIFY_TTL_HOURS", 72)  # sonuc onbellegi
VERIFY_CONCURRENCY = _int("VERIFY_CONCURRENCY", 3)
# bundan kisa sayfa bot engeli demek
VERIFY_MIN_PAGE = _int("VERIFY_MIN_PAGE", 15000)
# Playwright
USE_PLAYWRIGHT = _bool("USE_PLAYWRIGHT", True)
PW_HEADLESS = _bool("PW_HEADLESS", True)
PW_TIMEOUT_MS = _int("PW_TIMEOUT_MS", 35000)
PW_MAX_CONCURRENT = _int("PW_MAX_CONCURRENT", 2)
PW_DEBUG_DUMP = _bool("PW_DEBUG_DUMP", True)        # 0 sonuc alinca HTML'i kaydet

# esleme
MIN_PRICE = float(os.getenv("MIN_PRICE", "0") or 0)
MAX_PRICE = float(os.getenv("MAX_PRICE", "0") or 0)  # 0 = sinir yok

# yenıden kesif
REPIN_TOLERANCE_PCT = float(os.getenv("REPIN_TOLERANCE_PCT", "1.0"))


# veritabani
_db = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "tracker.db"))
DB_PATH = _db if _db.is_absolute() else (BASE_DIR / _db)
DEBUG_DIR = BASE_DIR / "data" / "debug"

# telegram
TELEGRAM_COMMANDS = _bool("TELEGRAM_COMMANDS", True)
BACKEND_TELEGRAM = _bool("BACKEND_TELEGRAM", True)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
