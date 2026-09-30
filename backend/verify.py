from __future__ import annotations

import asyncio
import hashlib
import logging
import re

import config
import store
from match import normalize

logger = logging.getLogger(__name__)

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma no cover
    curl_requests = None

_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_ANYTAG = re.compile(r"<[^>]+>")
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}
_sem = asyncio.Semaphore(config.VERIFY_CONCURRENCY)

# amazon her seferinde farkli ref ekliyor cache tutmuyordu
_REF_SEG = re.compile(r"/ref=[^/?#]*", re.I)
_TRACK_PARAM = re.compile(r"(?:^|&)(?:utm_[^=&]*|srsltid|sr|qid|th|psc)=[^&]*", re.I)



def _canon(url: str) -> str:
    base, _, query = url.partition("?")
    base = _REF_SEG.sub("", base).rstrip("/")
    query = _TRACK_PARAM.sub("", query.split("#")[0]).strip("&")
    return base + ("?" + query if query else "")



def _cache_key(url: str, phrases: tuple) -> str:
    h = hashlib.sha1("|".join(sorted(phrases)).encode("utf-8")).hexdigest()[:10]
    return _canon(url) + "#" + h


def _page_text(html_body: str) -> str:
    body = _TAG.sub(" ", html_body)
    return normalize(_ANYTAG.sub(" ", body))

def _fetch_sync(url: str) -> str:
    if curl_requests is None:
        return ""
    r = curl_requests.get(url, impersonate="chrome", headers=HEADERS,
                          timeout=config.HTTP_TIMEOUT, allow_redirects=True)
    return r.text if r.status_code == 200 else ""

async def check(url: str, phrases: tuple) -> bool:
    if not phrases or not url:
        return True
    key = _cache_key(url, phrases)
    cached = store.get_verdict(key, config.VERIFY_TTL_HOURS)
    if cached is not None:
        return cached

    async with _sem:
        try:
            body = await asyncio.to_thread(_fetch_sync, url)
        except Exception as e:
            logger.debug("dogrulama cekilemedi (%s): %s", url[:60], e)
            return True

    if len(body) < config.VERIFY_MIN_PAGE:
        # amazon icin ikinci deneme
        from fetcher import fetch_page_html
        body = await fetch_page_html(url)

    if len(body) < config.VERIFY_MIN_PAGE:
        # sayfa alinamadi ada guveniyoruz
        logger.info("dogrulanamadi (sayfa alinamadi), ad filtresine guveniliyor: %s",
                    url[:80])
        return True

    text = _page_text(body)
    hit = next((p for p in phrases if p in text), None)
    ok = hit is None
    if not ok:
        logger.info("elendi (sayfa dogrulamasi: '%s') %s", hit, url[:80])

    store.set_verdict(key, ok)
    return ok



async def pick_verified(offers: list, phrases: tuple):
    if not offers:
        return None
    if not phrases or not config.VERIFY_WINNER:
        return offers[0]


    for offer in offers[: config.VERIFY_MAX_TRIES]:
        if await check(offer.url, phrases):
            return offer

    # hicbiri gecmediyse bos don
    return None
