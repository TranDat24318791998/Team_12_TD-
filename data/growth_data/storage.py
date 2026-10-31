"""SQLite migrations and short atomic command transactions; trusted backend only."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def decode(row):
    if row is None:
        return None
    return {k[:-5] if k.endswith("_json") else k: json.loads(v) if k.endswith("_json") and v is not None else v
            for k, v in dict(row).items()}


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.execute("PRAGMA journal_mode=WAL")
            version = c.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise ValueError("Schema mới hơn service; không tự hạ version")
            if version == 0:
                sql = Path(__file__).with_name("migrations").joinpath("001_initial.sql").read_text()
                c.executescript("BEGIN IMMEDIATE;\n" + sql)
                c.execute("INSERT INTO schema_migrations VALUES(1,?)", (now(),))
                c.execute("PRAGMA user_version=1")

    @contextmanager
    def connect(self, write=False):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()


def one(c, sql, args=()):
    return decode(c.execute(sql, args).fetchone())


def many(c, sql, args=()):
    return [decode(r) for r in c.execute(sql, args).fetchall()]


def insert(c, table, **values):
    # table/column identifiers are supplied only by code, never request parameters.
    values = {k: dumps(v) if k.endswith("_json") and v is not None else v for k, v in values.items()}
    c.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))


def timestamps():
    t = now()
    return {"version": 1, "created_at": t, "updated_at": t}
