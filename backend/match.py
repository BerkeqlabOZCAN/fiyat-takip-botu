from __future__ import annotations
import re
import unicodedata

_TR_MAP = str.maketrans({
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
})
def normalize(s: str) -> str:
    s = (s or "").translate(_TR_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()



class Query:

    # siteye gidecek kelime sayisi
    SITE_TERMS = 2
    def __init__(self, raw: str):
        self.raw = raw.strip()
        self.required: list[str] = []
        self.excluded: list[str] = []
        self.any_of: list[list[str]] = []
        self.site_query: str = ""

        for token in re.findall(r'"[^"]*"|\([^)]*\)|\S+', self.raw):
            if token.startswith('"') and token.endswith('"') and len(token) > 2:
                self.site_query = token[1:-1].strip()
            elif token.startswith("(") and token.endswith(")"):
                alts = [normalize(a) for a in token[1:-1].split("|")]
                alts = [a for a in alts if a]
                if alts:
                    self.any_of.append(alts)
            elif token.startswith("-") and len(token) > 1:
                n = normalize(token[1:])
                if n:
                    self.excluded.append(n)
            else:
                n = normalize(token)
                if n:
                    self.required.append(n)


    @property
    def keywords(self) -> str:
        if self.site_query:
            return self.site_query
        parts = self.required[: self.SITE_TERMS]
        if not parts:
            for alts in self.any_of[: self.SITE_TERMS]:
                parts.append(alts[0])
        return " ".join(parts) or self.raw
    def matches(self, name: str) -> bool:
        n = " " + normalize(name) + " "
        if any(w in n for w in self.excluded):
            return False
        if not all(w in n for w in self.required):
            return False
        for alts in self.any_of:
            if not any(a in n for a in alts):
                return False
        return True

    def __repr__(self) -> str:
        return (f"Query(required={self.required}, excluded={self.excluded}, "
                f"any_of={self.any_of})")



def filter_offers(offers: list, query: Query,
                  min_price: float = 0, max_price: float = 0) -> list:
    out = []
    for o in offers:
        if not o.price or not o.in_stock:
            continue
        if min_price and o.price < min_price:
            continue
        if max_price and o.price > max_price:
            continue
        if not query.matches(o.name):
            continue
        out.append(o)
    return sorted(out, key=lambda o: o.price)
