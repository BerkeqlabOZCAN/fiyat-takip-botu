from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager

import config


_SCHEMA = """
CREATE TABLE IF NOT EXISTS watch (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query       TEXT NOT NULL UNIQUE,
    label       TEXT,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS pin (
    watch_id    INTEGER NOT NULL,
    site        TEXT NOT NULL,
    name        TEXT,
    url         TEXT,
    price       REAL,
    in_stock    INTEGER NOT NULL DEFAULT 1,
    updated_at  INTEGER NOT NULL,
    PRIMARY KEY (watch_id, site),
    FOREIGN KEY (watch_id) REFERENCES watch(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS snapshot (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id    INTEGER NOT NULL,
    site        TEXT NOT NULL,
    url         TEXT,
    price       REAL NOT NULL,
    ts          INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshot_watch ON snapshot(watch_id, site, ts DESC);
CREATE TABLE IF NOT EXISTS setting (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);

-- /temizle icin: sohbette gecen mesajlarin id leri. Telegram bir mesaji
-- ancak id siyle sildirir; gonderdiklerimizi de aldiklarimizi da tutuyoruz.
CREATE TABLE IF NOT EXISTS msglog (
    chat TEXT NOT NULL,
    mid  INTEGER NOT NULL,
    ts   INTEGER NOT NULL,
    PRIMARY KEY (chat, mid)
);


CREATE TABLE IF NOT EXISTS verdict (
    url  TEXT PRIMARY KEY,
    ok   INTEGER NOT NULL,
    ts   INTEGER NOT NULL
);
"""

@contextmanager
def _conn():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.executescript(_SCHEMA)
        # eski veritabanlari icin spec sutunu
        cols = {r["name"] for r in con.execute("PRAGMA table_info(watch)")}
        if "spec" not in cols:
            con.execute("ALTER TABLE watch ADD COLUMN spec TEXT")



# watch

def add_watch(query: str, label: str | None = None,
              spec: str | None = None) -> int:
    now = int(time.time())
    with _conn() as con:
        con.execute(
            "INSERT INTO watch(query, label, active, created_at, spec) "
            "VALUES(?,?,1,?,?) "
            "ON CONFLICT(query) DO UPDATE SET active=1, "
            "  label=COALESCE(excluded.label, label), "
            "  spec=COALESCE(excluded.spec, spec)",
            (query.strip(), label, now, spec),
        )
        row = con.execute("SELECT id FROM watch WHERE query=?", (query.strip(),)).fetchone()
        return row["id"]

def remove_watch(watch_id: int) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM watch WHERE id=?", (watch_id,))
        con.execute("DELETE FROM pin WHERE watch_id=?", (watch_id,))
        con.execute("DELETE FROM snapshot WHERE watch_id=?", (watch_id,))
        return cur.rowcount > 0


def update_query(watch_id: int, query: str, label: str) -> bool:
    try:
        with _conn() as con:
            con.execute("UPDATE watch SET query=?, label=? WHERE id=?",
                        (query.strip(), label, watch_id))
        return True
    except sqlite3.IntegrityError:
        return False


def deactivate_others(keep_id: int) -> int:
    with _conn() as con:
        cur = con.execute("UPDATE watch SET active=0 WHERE id<>? AND active=1",
                          (keep_id,))
        return cur.rowcount


def get_watches(only_active: bool = True) -> list[dict]:
    sql = "SELECT * FROM watch"
    if only_active:
        sql += " WHERE active=1"
    sql += " ORDER BY id"
    with _conn() as con:
        return [dict(r) for r in con.execute(sql)]


def get_watch(watch_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM watch WHERE id=?", (watch_id,)).fetchone()
        return dict(row) if row else None


# pin

def get_pins(watch_id: int) -> dict[str, dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM pin WHERE watch_id=?", (watch_id,))
        return {r["site"]: dict(r) for r in rows}

def upsert_pin(watch_id: int, site: str, name: str, url: str,
               price: float, in_stock: bool) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO pin(watch_id, site, name, url, price, in_stock, updated_at) "
            "VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(watch_id, site) DO UPDATE SET "
            "  name=excluded.name, url=excluded.url, price=excluded.price, "
            "  in_stock=excluded.in_stock, updated_at=excluded.updated_at",
            (watch_id, site, name, url, price, int(in_stock), int(time.time())),
        )

def clear_pin(watch_id: int, site: str) -> None:
    with _conn() as con:
        con.execute("DELETE FROM pin WHERE watch_id=? AND site=?", (watch_id, site))


# snapshot

def add_snapshot(watch_id: int, site: str, url: str, price: float) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO snapshot(watch_id, site, url, price, ts) VALUES(?,?,?,?,?)",
            (watch_id, site, url, price, int(time.time())),
        )


def price_stats(watch_id: int, site: str, days: int = 30) -> dict:
    since = int(time.time()) - days * 86400
    with _conn() as con:
        row = con.execute(
            "SELECT MIN(price) AS lo, MAX(price) AS hi, COUNT(*) AS n "
            "FROM snapshot WHERE watch_id=? AND site=? AND ts>=?",
            (watch_id, site, since),
        ).fetchone()
    return dict(row) if row else {"lo": None, "hi": None, "n": 0}


def prune_snapshots(keep_days: int = 90) -> int:
    cutoff = int(time.time()) - keep_days * 86400
    with _conn() as con:
        return con.execute("DELETE FROM snapshot WHERE ts<?", (cutoff,)).rowcount

# sayfa dogrulama onbellegı


# sutun adi url ama anahtar duz url degil
def get_verdict(key: str, ttl_hours: int) -> bool | None:
    cutoff = int(time.time()) - ttl_hours * 3600
    with _conn() as con:
        row = con.execute("SELECT ok FROM verdict WHERE url=? AND ts>=?",
                          (key, cutoff)).fetchone()
    return bool(row["ok"]) if row else None

def set_verdict(key: str, ok: bool) -> None:
    with _conn() as con:
        con.execute("INSERT INTO verdict(url, ok, ts) VALUES(?,?,?) "
                    "ON CONFLICT(url) DO UPDATE SET ok=excluded.ok, ts=excluded.ts",
                    (key, int(ok), int(time.time())))



# ayarlar

def get_setting(key: str, default: str = "") -> str:
    with _conn() as con:
        row = con.execute("SELECT v FROM setting WHERE k=?", (key,)).fetchone()
    return row["v"] if row else default


def set_setting(key: str, value) -> None:
    with _conn() as con:
        con.execute("INSERT INTO setting(k, v) VALUES(?,?) "
                    "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                    (key, str(value)))



# sohbet mesaj kaydi

def log_message(chat: str, mid: int) -> None:
    if not mid:
        return
    with _conn() as con:
        con.execute("INSERT OR IGNORE INTO msglog(chat, mid, ts) VALUES(?,?,?)",
                    (str(chat), int(mid), int(time.time())))
def get_messages(chat: str, limit: int = 200) -> list:
    with _conn() as con:
        rows = con.execute("SELECT mid FROM msglog WHERE chat=? "
                           "ORDER BY mid DESC LIMIT ?", (str(chat), limit))
        return [r["mid"] for r in rows]

def forget_messages(chat: str, mids: list) -> None:
    if not mids:
        return
    with _conn() as con:
        con.executemany("DELETE FROM msglog WHERE chat=? AND mid=?",
                        [(str(chat), int(m)) for m in mids])

# fiyat analizi


def price_summary(watch_id: int, days: int = 30) -> dict:
    since = int(time.time()) - days * 86400
    with _conn() as con:
        rows = con.execute(
            "SELECT MIN(price) AS dip FROM snapshot "
            "WHERE watch_id=? AND ts>=? GROUP BY ts / 300",   # ~5 dk'lik turlar
            (watch_id, since),
        ).fetchall()
    turlar = [r["dip"] for r in rows if r["dip"]]
    if not turlar:
        return {"n": 0}
    return {
        "n": len(turlar),
        "dip": min(turlar),
        "tepe": max(turlar),
        "ort": sum(turlar) / len(turlar),
        "gun": days,
    }

def all_time_low(watch_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT price, ts, site, url FROM snapshot "
            "WHERE watch_id=? ORDER BY price ASC LIMIT 1",
            (watch_id,),
        ).fetchone()
    return dict(row) if row else None


def site_last_seen(watch_id: int) -> dict:
    with _conn() as con:
        rows = con.execute(
            "SELECT site, MAX(ts) AS ts, COUNT(*) AS n FROM snapshot "
            "WHERE watch_id=? GROUP BY site",
            (watch_id,),
        )
        return {r["site"]: {"ts": r["ts"], "n": r["n"]} for r in rows}


def activate_watch(watch_id: int) -> bool:
    with _conn() as con:
        cur = con.execute("UPDATE watch SET active=1 WHERE id=?", (watch_id,))
        return cur.rowcount > 0



def price_series(watch_id: int, days: int = 30) -> list:
    since = int(time.time()) - days * 86400
    with _conn() as con:
        rows = con.execute(
            "SELECT MIN(ts) AS ts, MIN(price) AS fiyat FROM snapshot "
            "WHERE watch_id=? AND ts>=? GROUP BY ts / 300 ORDER BY ts",
            (watch_id, since),
        ).fetchall()
    return [(r["ts"], r["fiyat"]) for r in rows if r["fiyat"]]


def site_series(watch_id: int, site: str, days: int = 30) -> list:
    since = int(time.time()) - days * 86400
    with _conn() as con:
        rows = con.execute(
            "SELECT MIN(ts) AS ts, MIN(price) AS fiyat FROM snapshot "
            "WHERE watch_id=? AND site=? AND ts>=? GROUP BY ts / 300 ORDER BY ts",
            (watch_id, site, since),
        ).fetchall()
    return [(r["ts"], r["fiyat"]) for r in rows if r["fiyat"]]
