from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote, urljoin


# verı tipleri

@dataclass
class Offer:
    site: str
    name: str
    url: str
    price: float
    in_stock: bool = True


@dataclass
class Site:
    key: str                       # "vatan"
    label: str                     # "Vatan"
    base: str                      # "https://www.vatanbilgisayar.com"
    engine: str                    # "http" | "pw"
    search: Callable[[str], str]   # anahtar kelıme -> arama URL'i
    # diger sayfalar en ucuz urun 2-3 sayfada olabiliyor
    page: Callable = None
    parser: Callable[[str, str], list] | None = None   # engine="http" icin
    product_re: re.Pattern | None = None               # engine="pw" icin
    price_hint: tuple = ()                             # engine="pw" CSS ipuclari
    enabled: bool = True


# fiyat ayristirma

_NON_PRICE = re.compile(r"[^\d.,]")
_PRICE_TOKEN = re.compile(
    r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?"   # 24.049 / 13.803,26
    r"|\d+,\d{1,2}"                        # 999,90
    r"|\d+\.\d{1,2}"                       # 999.90
    r"|\d{3,}"                             # 15009
)


def parse_price(raw) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None

    s = _NON_PRICE.sub("", str(raw)).strip(" .,")
    if not s:
        return None

    if "," in s:
        # TR formati nokta binlik virgul ondalik
        s = s.replace(".", "").replace(",", ".")
    else:
        parts = s.split(".")
        # nokta binlik de olabilir
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            s = "".join(parts)

    try:
        v = float(s)
    except ValueError:
        return None
    return v if v > 0 else None

def first_price(fragment: str) -> float | None:
    for m in _PRICE_TOKEN.finditer(_strip_tags(fragment)):
        v = parse_price(m.group(0))
        if v and v >= 1:
            return v
    return None

# yardimci

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")



def _strip_tags(s: str) -> str:
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", s))).strip()


def _norm_url(base: str, href: str) -> str:
    return urljoin(base, html.unescape(href.strip()))


_LABEL_ATTR = re.compile(r'(?:title|alt)="([^"]{6,200})"')
# Rozet/ikon gorselleri de alt tasir bunlari urun adi sanmayalim
_LABEL_JUNK = re.compile(r"^[A-Z0-9_\- ]+$|^(?:add-icon|logo|badge)", re.I)


def _best_label(block: str) -> str:
    cands = [
        html.unescape(v).strip()
        for v in _LABEL_ATTR.findall(block)
        if not _LABEL_JUNK.match(v)
    ]
    return max(cands, key=len) if cands else ""



def _name_from_slug(path: str) -> str:
    slug = path.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"-\d{5,}$", "", slug)           # sondaki urun id'sini at
    return slug.replace("-", " ").strip().title()


_OUT_OF_STOCK = ("tukendi", "stokta yok", "satista degil")


def _in_stock(block: str) -> bool:
    low = block.lower().replace("ü", "u").replace("ş", "s").replace("ı", "i")
    return not any(w in low for w in _OUT_OF_STOCK)



# hTTP siteleri parser


def parse_vatan(body: str, base: str) -> list:
    offers = []
    for b in body.split('class="product-list product-list--list-page"')[1:]:
        m = re.search(r'class="product-list-link"\s+href="([^"]+)"', b)
        if not m:
            continue
        mn = re.search(r'product-list__product-name">\s*<h3>(.*?)</h3>', b, re.S)
        mp = re.search(r"product-list__price['\"]>\s*([\d.,]+)", b)
        price = parse_price(mp.group(1)) if mp else None
        if not price:
            continue
        offers.append(Offer(
            site="vatan",
            name=_strip_tags(mn.group(1)) if mn else "",
            url=_norm_url(base, m.group(1)),
            price=price,
            in_stock=_in_stock(b[:4000]),
        ))
    return offers


def parse_itopya(body: str, base: str) -> list:
    offers = []
    for b in body.split('data-urun-id="')[1:]:
        m = re.search(r'<a class="title" href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        if not m:
            continue
        mp = re.search(r'class="product-price"[^>]*>(.*?)</span>', b, re.S)
        price = first_price(mp.group(1)) if mp else None
        if not price:
            continue
        offers.append(Offer(
            site="itopya",
            name=_strip_tags(m.group(2)),
            url=_norm_url(base, m.group(1)),
            price=price,
            in_stock=_in_stock(b[:4000]),
        ))
    return offers

def parse_incehesap(body: str, base: str) -> list:
    # Incehesap urun verisini data-gaitem icinde tutuyor.
    offers = []
    seen = set()
    for m in re.finditer(r"data-gaitem='(\{.*?\})'", body, re.S):
        try:
            d = json.loads(html.unescape(m.group(1)))
        except Exception:
            continue
        url = (d.get("url") or "").strip()
        price = parse_price(d.get("price"))
        if not url or not price or url in seen:
            continue
        seen.add(url)
        offers.append(Offer(
            site="incehesap",
            name=(d.get("item_name") or "").strip(),
            url=_norm_url(base, url),
            price=price,
        ))
    return offers

def parse_n11(body: str, base: str) -> list:
    offers = []
    seen = set()
    for b in body.split('<a href="/urun/')[1:]:
        mu = re.match(r'([^"]+)"', b)
        if not mu or 'class="product-item"' not in b[:200]:
            continue
        url = _norm_url(base, "/urun/" + mu.group(1))
        if url in seen:
            continue
        # eski fiyati alma
        mp = re.search(r'class="price-currency"[^>]*>([^<]+)<', b)
        price = parse_price(mp.group(1)) if mp else None
        if not price:
            continue
        seen.add(url)
        offers.append(Offer(
            site="n11",
            name=_best_label(b) or _name_from_slug(mu.group(1)),
            url=url,
            price=price,
            in_stock=_in_stock(b[:4000]),
        ))
    return offers


def parse_hepsiburada(body: str, base: str) -> list:
    anchors = [m for m in re.finditer(r"<a\s[^>]*productCardLink[^>]*>", body)]
    offers = []
    seen = set()
    for idx, m in enumerate(anchors):
        tag = m.group(0)
        mh = re.search(r'href="([^"]+)"', tag)
        if not mh:
            continue
        url = _norm_url(base, mh.group(1).split("?")[0])
        if url in seen:
            continue
        end = anchors[idx + 1].start() if idx + 1 < len(anchors) else min(len(body), m.end() + 12000)
        block = body[m.start():end]
        mp = re.search(
            r'data-test-id="final-price-\d+"[^>]*>\s*([\d.]+)'
            r'(?:<span[^>]*>\s*(,\d+))?', block)
        if not mp:
            continue
        price = parse_price((mp.group(1) or "") + (mp.group(2) or ""))
        if not price:
            continue
        mt = re.search(r'title="([^"]+)"', tag)
        seen.add(url)
        offers.append(Offer(
            site="hepsiburada",
            name=html.unescape(mt.group(1)).strip() if mt else _name_from_slug(mh.group(1)),
            url=url,
            price=price,
            in_stock=_in_stock(block[:6000]),
        ))
    return offers


def parse_woocommerce(body: str, base: str, site_key: str) -> list:
    offers = []
    seen = set()
    for b in re.split(r"<li\s+class=\"(?=[^\"]*\btype-product\b)", body)[1:]:
        classes = b[:b.find('"')] if '"' in b else ""
        m = re.search(r'<a\s+href="([^"]+)"[^>]*class="[^"]*woocommerce-LoopProduct-link', b)
        if not m:
            m = re.search(r'<a\s+href="([^"]*/urun/[^"]+)"', b)
        if not m:
            continue
        url = _norm_url(base, m.group(1).split("?")[0])
        if url in seen:
            continue
        # indirimde ins degerini al
        mi = re.search(r"<ins[^>]*>(.*?)</ins>", b, re.S)
        frag = mi.group(1) if mi else b
        mp = re.search(r'class="[^"]*woocommerce-Price-amount[^"]*"[^>]*>(.*?)</span>\s*</span>',
                       frag, re.S) or re.search(
                       r'class="[^"]*woocommerce-Price-amount[^"]*"[^>]*>(.*?)</span>', frag, re.S)
        price = first_price(mp.group(1)) if mp else None
        if not price:
            continue
        mn = re.search(r'class="[^"]*(?:woocommerce-loop-product__title|product-title)[^"]*"[^>]*>(.*?)</', b, re.S)
        if not mn:
            mn = re.search(r'<h[23][^>]*>(.*?)</h[23]>', b, re.S)
        seen.add(url)
        offers.append(Offer(
            site=site_key,
            name=_strip_tags(mn.group(1)) if mn else _name_from_slug(m.group(1)),
            url=url,
            price=price,
            in_stock="outofstock" not in classes,
        ))
    return offers

def parse_gaminggen(body: str, base: str) -> list:
    return parse_woocommerce(body, base, "gaminggen")


# site kaydi
def _q(s: str) -> str:
    return quote(s, safe="")



SITES = [
    Site(
        key="vatan", label="Vatan", base="https://www.vatanbilgisayar.com",
        engine="http",
        search=lambda q: "https://www.vatanbilgisayar.com/arama/%s/" % _q(q),
        page=lambda q, n: "https://www.vatanbilgisayar.com/arama/%s/?page=%d" % (_q(q), n),
        parser=parse_vatan,
    ),
    Site(
        key="itopya", label="Itopya", base="https://www.itopya.com",
        engine="http",
        search=lambda q: "https://www.itopya.com/ara?bul=%s" % _q(q),
        parser=parse_itopya,
    ),
    Site(
        key="incehesap", label="Incehesap", base="https://www.incehesap.com",
        engine="http",
        search=lambda q: "https://www.incehesap.com/q/%s/" % _q(q),
        page=lambda q, n: "https://www.incehesap.com/q/%s/%d/" % (_q(q), n),
        parser=parse_incehesap,
    ),
    Site(
        key="n11", label="n11", base="https://www.n11.com",
        engine="http",
        search=lambda q: "https://www.n11.com/arama?q=%s" % quote(q),
        page=lambda q, n: "https://www.n11.com/arama?q=%s&pg=%d" % (quote(q), n),
        parser=parse_n11,
    ),
    Site(
        key="hepsiburada", label="Hepsiburada", base="https://www.hepsiburada.com",
        engine="http",
        search=lambda q: "https://www.hepsiburada.com/ara?q=%s" % quote(q),
        page=lambda q, n: "https://www.hepsiburada.com/ara?q=%s&sayfa=%d" % (quote(q), n),
        parser=parse_hepsiburada,
    ),
    Site(
        # diger domain park edilmis
        key="gaminggen", label="GamingGen", base="https://www.gaming.gen.tr",
        engine="http",
        search=lambda q: "https://www.gaming.gen.tr/?s=%s&post_type=product" % quote(q),
        page=lambda q, n: "https://www.gaming.gen.tr/?s=%s&post_type=product&paged=%d" % (quote(q), n),
        parser=parse_gaminggen,
    ),
    # SPA / agresif bot korumasi Playwright zorunlu
    Site(
        key="trendyol", label="Trendyol", base="https://www.trendyol.com",
        engine="pw",
        search=lambda q: "https://www.trendyol.com/sr?q=%s" % _q(q),
        page=lambda q, n: "https://www.trendyol.com/sr?q=%s&pi=%d" % (_q(q), n),
        product_re=re.compile(r"-p-\d{3,}"),
        price_hint=(".prc-box-dscntd", ".prc-box-sllng", ".price-item"),
    ),
    Site(
        key="amazon", label="Amazon TR", base="https://www.amazon.com.tr",
        engine="pw",
        search=lambda q: "https://www.amazon.com.tr/s?k=%s" % quote(q),
        page=lambda q, n: "https://www.amazon.com.tr/s?k=%s&page=%d" % (quote(q), n),
        product_re=re.compile(r"/dp/[A-Z0-9]{10}"),
        price_hint=(".a-price .a-offscreen", ".a-price-whole"),
    ),
]

SITES_BY_KEY = {s.key: s for s in SITES}
