from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import config
from sites import Offer, Site, first_price, parse_price

logger = logging.getLogger(__name__)

try:
    from curl_cffi import requests as curl_requests
    _HAS_CURL_CFFI = True
except ImportError:  # pragma no cover
    curl_requests = None
    _HAS_CURL_CFFI = False


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}

IMPERSONATE = "chrome"


_http_sem = asyncio.Semaphore(config.MAX_CONCURRENT)
_pw_sem = asyncio.Semaphore(config.PW_MAX_CONCURRENT)


def _get_sync(url: str) -> tuple[int, str]:
    if _HAS_CURL_CFFI:
        r = curl_requests.get(url, impersonate=IMPERSONATE, headers=HEADERS,
                              timeout=config.HTTP_TIMEOUT, allow_redirects=True)
        return r.status_code, r.text

    import httpx  # yedek yol
    with httpx.Client(headers={"User-Agent": UA, **HEADERS},
                      timeout=config.HTTP_TIMEOUT, follow_redirects=True) as c:
        r = c.get(url)
    return r.status_code, r.text

async def fetch_http(site: Site, query: str, url: str = "") -> list:
    url = url or site.search(query)
    async with _http_sem:
        try:
            status, body = await asyncio.to_thread(_get_sync, url)
        except Exception as e:
            logger.warning("%s: istek hatasi (%s)", site.key, e)
            return []

    if status != 200:
        logger.warning("%s: HTTP %s%s", site.key, status,
                       "" if _HAS_CURL_CFFI else " (curl_cffi kurulu degil!)")
        return await fetch_pw(site, query) if config.USE_PLAYWRIGHT else []

    try:
        offers = site.parser(body, site.base)
    except Exception as e:
        logger.error("%s: ayristirma hatasi: %s", site.key, e, exc_info=True)
        return []

    if not offers:
        logger.warning("%s: 0 sonuc (markup degismis olabilir)", site.key)
        _dump(site.key, body)
    return offers


# playwright
_PW_EXTRACT = r"""
(cfg) => {
  const priceRe = /(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+,\d{2})\s*(?:TL|₺)/i;

  const readPrice = (root) => {
    for (const sel of cfg.hints) {
      const el = root.querySelector(sel);
      if (el) {
        const t = (el.textContent || el.getAttribute('content') || '').trim();
        if (t) return t;
      }
    }
    const m = (root.innerText || '').match(priceRe);
    return m ? m[0] : null;
  };

  const cardOf = (a) => {
    let el = a;
    for (let i = 0; i < 6 && el; i++) {
      if (el.innerText && priceRe.test(el.innerText)) return el;
      el = el.parentElement;
    }
    return a;
  };

  const rx = new RegExp(cfg.productRe);
  const seen = new Set();
  const out = [];

  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.href;
    if (!href || !rx.test(href) || seen.has(href.split('?')[0])) continue;

    const card = cardOf(a);
    const raw = readPrice(card);
    if (!raw) continue;

    let name = (a.getAttribute('title') || '').trim();
    if (name.length < 6) {
      const img = card.querySelector('img[alt]');
      if (img) name = (img.getAttribute('alt') || '').trim();
    }
    if (name.length < 6) {
      const h = card.querySelector('h1,h2,h3,h4,[class*=name],[class*=title]');
      if (h) name = (h.textContent || '').trim();
    }
    if (name.length < 6) name = (a.textContent || '').trim();

    const txt = (card.innerText || '').toLowerCase();
    const oos = txt.includes('tükendi') || txt.includes('stokta yok');

    seen.add(href.split('?')[0]);
    out.push({ url: href.split('?')[0], name: name.slice(0, 200), raw, oos });
    if (out.length >= 60) break;
  }
  return out;
}
"""


_HEAVY = ("image", "media", "font")

async def _block_heavy_assets(route) -> None:
    try:
        if route.request.resource_type in _HEAVY:
            await route.abort()
        else:
            await route.continue_()
    except Exception:
        pass

async def fetch_pw(site: Site, query: str, url: str = "") -> list:
    if not config.USE_PLAYWRIGHT:
        return []
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("%s: playwright kurulu degil (pip install playwright && "
                     "python -m playwright install chromium)", site.key)
        return []


    url = url or site.search(query)
    async with _pw_sem:
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=config.PW_HEADLESS,
                    args=["--disable-blink-features=AutomationControlled",
                          "--no-sandbox", "--disable-dev-shm-usage"],
                )
                ctx = await browser.new_context(
                    user_agent=UA, locale="tr-TR", timezone_id="Europe/Istanbul",
                    viewport={"width": 1366, "height": 900},
                    extra_http_headers={"Accept-Language": "tr-TR,tr;q=0.9"},
                )
                await ctx.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                )
                page = await ctx.new_page()
                await page.route("**/*", _block_heavy_assets)
                await page.goto(url, wait_until="domcontentloaded",
                                timeout=config.PW_TIMEOUT_MS)
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                await page.wait_for_timeout(1200)

                raw_items = await page.evaluate(_PW_EXTRACT, {
                    "productRe": site.product_re.pattern if site.product_re else ".",
                    "hints": list(site.price_hint),
                })
                html_text = await page.content() if not raw_items else ""
                await ctx.close()
                await browser.close()
        except Exception as e:
            logger.warning("%s: Playwright hatasi (%s)", site.key, e)
            return []

    offers = []
    for it in raw_items or []:
        price = parse_price(it.get("raw")) or first_price(it.get("raw") or "")
        if not price:
            continue
        offers.append(Offer(
            site=site.key,
            name=(it.get("name") or "").strip(),
            url=it["url"],
            price=price,
            in_stock=not it.get("oos"),
        ))
    if not offers:
        logger.warning("%s: Playwright 0 sonuc dondurdu", site.key)
        _dump(site.key, html_text)
    return offers



# ortak

def query_variants(keywords: str) -> list:
    kw = keywords.strip()
    tokens = kw.split()
    out = [kw]
    if len(tokens) > 1:
        out.append(" ".join(reversed(tokens)))
        out.append(tokens[0])
    return out


async def _fetch_once(site: Site, keywords: str) -> list:
    max_pages = config.PW_SEARCH_PAGES if site.engine == "pw" else config.SEARCH_PAGES
    offers: list = []
    seen: set = set()

    for pageno in range(1, max_pages + 1):
        if pageno > 1 and not site.page:
            break                      # site sayfalamayi desteklemıyor
        url = "" if pageno == 1 else site.page(keywords, pageno)

        got = (await fetch_http(site, keywords, url) if site.engine == "http"
               else await fetch_pw(site, keywords, url))

        fresh = 0
        for o in got:
            k = o.url.split("?")[0]
            if k not in seen:
                seen.add(k)
                offers.append(o)
                fresh += 1
        # ayni sayfada dur
        if fresh == 0:
            break

    return offers

async def fetch_site(site: Site, query: str) -> list:
    merged: list = []
    seen: set = set()

    for i, variant in enumerate(query_variants(query)):
        if i and not config.RETRY_BROADER:
            break
        offers = await _fetch_once(site, variant)
        for o in offers:
            key = o.url.split("?")[0]
            if key not in seen:
                seen.add(key)
                merged.append(o)
        if len(merged) >= config.MIN_RAW_RESULTS:
            break
        if i:
            logger.info("%s: '%s' ile %d sonuc, sorgu genisletiliyor",
                        site.key, variant, len(merged))

    return merged


def _dump(key: str, body: str) -> None:
    if not config.PW_DEBUG_DUMP or not body:
        return
    try:
        config.DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = config.DEBUG_DIR / f"{key}-{stamp}.html"
        path.write_text(body, encoding="utf-8", errors="replace")
        logger.info("%s: HTML kaydedildi -> %s", key, path)
    except Exception:
        pass



async def fetch_page_html(url: str) -> str:
    if not config.USE_PLAYWRIGHT:
        return ""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ""

    async with _pw_sem:
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=config.PW_HEADLESS,
                    args=["--disable-blink-features=AutomationControlled",
                          "--no-sandbox", "--disable-dev-shm-usage"])
                ctx = await browser.new_context(
                    user_agent=UA, locale="tr-TR", timezone_id="Europe/Istanbul",
                    viewport={"width": 1366, "height": 900})
                page = await ctx.new_page()
                await page.route("**/*", _block_heavy_assets)
                await page.goto(url, wait_until="domcontentloaded",
                                timeout=config.PW_TIMEOUT_MS)
                await page.wait_for_timeout(800)
                body = await page.content()
                await ctx.close()
                await browser.close()
                return body
        except Exception as e:
            logger.debug("sayfa alinamadi (%s): %s", url[:60], e)
            return ""
