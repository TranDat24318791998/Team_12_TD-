import json
import sqlite3
import time
from pathlib import Path
from uuid import uuid4


class Conflict(Exception):
    pass


class QueueFull(Exception):
    pass


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        (root / 'assets').mkdir(exist_ok=True)
        (root / 'jobs').mkdir(exist_ok=True)
        self.db = root / 'jobs.sqlite3'
        with self.connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS assets
                (id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL,
                 path TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs
                (id TEXT PRIMARY KEY, owner TEXT NOT NULL, idem TEXT NOT NULL,
                 fingerprint TEXT NOT NULL, request TEXT NOT NULL, status TEXT NOT NULL,
                 stage TEXT NOT NULL, result TEXT, error TEXT, created REAL NOT NULL,
                 updated REAL NOT NULL, UNIQUE(owner, idem));
            ''')

    def connect(self):
        conn = sqlite3.connect(self.db, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def add_asset(self, asset_id, owner, kind, path):
        with self.connect() as conn:
            conn.execute('INSERT INTO assets VALUES (?,?,?,?,?)',
                         (asset_id, owner, kind, str(path), time.time()))

    def asset(self, asset_id, owner):
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM assets WHERE id=? AND owner=?', (asset_id, owner)).fetchone()
        return dict(row) if row else None

    def existing(self, owner, idem):
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM jobs WHERE owner=? AND idem=?', (owner, idem)).fetchone()
        return dict(row) if row else None

    def create(self, owner, idem, fingerprint, request, limit):
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            old = conn.execute('SELECT * FROM jobs WHERE owner=? AND idem=?', (owner, idem)).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise Conflict('Idempotency-Key đã dùng cho yêu cầu khác')
                return dict(old), False
            pending = conn.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            if pending >= limit:
                raise QueueFull('Hàng đợi đầy, thử lại sau')
            job_id, now = uuid4().hex, time.time()
            conn.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                         (job_id, owner, idem, fingerprint, json.dumps(request, ensure_ascii=False),
                          'queued', 'queued', None, None, now, now))
            row = conn.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            return dict(row), True

    def job(self, job_id, owner=None):
        with self.connect() as conn:
            sql = 'SELECT * FROM jobs WHERE id=?'
            params = [job_id]
            if owner is not None:
                sql += ' AND owner=?'
                params.append(owner)
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def jobs(self, owner, limit=20):
        with self.connect() as conn:
            rows = conn.execute('SELECT * FROM jobs WHERE owner=? ORDER BY created DESC LIMIT ?',
                                (owner, limit)).fetchall()
        return [dict(row) for row in rows]

    def claim(self):
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                conn.execute("UPDATE jobs SET status='running',stage='starting',updated=? WHERE id=?",
                             (time.time(), row['id']))
            return dict(row) if row else None

    def update(self, job_id, *, status=None, stage=None, result=None, error=None):
        fields, params = ['updated=?'], [time.time()]
        for key, value in [('status', status), ('stage', stage), ('result', result), ('error', error)]:
            if value is not None:
                fields.append(f'{key}=?')
                params.append(json.dumps(value, ensure_ascii=False) if key == 'result' else value)
        with self.connect() as conn:
            conn.execute(f"UPDATE jobs SET {','.join(fields)} WHERE id=?", [*params, job_id])

    def recover(self):
        # Do not silently repeat paid calls after a process crash.
        with self.connect() as conn:
            conn.execute("UPDATE jobs SET status='failed',stage='interrupted',error=?,updated=? WHERE status='running'",
                         ('Worker đã dừng giữa chừng. Kiểm tra kết quả trước khi tạo yêu cầu mới.', time.time()))
