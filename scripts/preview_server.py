"""Local frontend preview with a public day-seven sample stored in SQLite.

This server is deliberately separate from the application/data-service runtime.
It serves only built frontend assets and an explicitly synthetic, public fixture.
"""

import argparse
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
PAGES = {"index.html", "demo.html", "updated.html", "night.html", "proof.html"}
ASSET_SUFFIXES = {".css", ".js", ".txt", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2"}


def validate_sample(value):
    """Reject incomplete snapshots before replacing the saved public sample."""
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Mẫu ngày 7 cần schema_version=1.")
    state, events, proof, source = (value.get(key) for key in ("state", "events", "proof", "source"))
    if not isinstance(state, dict) or state.get("day") != 7 or state.get("step") != "complete" or not isinstance(state.get("run_id"), str) or not state["run_id"]:
        raise ValueError("Mẫu phải có phiên hoàn tất ngày 7.")
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise ValueError("Nhật ký mẫu phải là danh sách sự kiện.")
    if not isinstance(proof, dict) or proof.get("days") != 7:
        raise ValueError("Báo cáo mẫu phải bao gồm 7 ngày.")
    if not isinstance(source, dict) or source.get("kind") != "sqlite_sample":
        raise ValueError("Mẫu phải ghi rõ nguồn sqlite_sample.")
    return value


class SampleStore:
    def __init__(self, database):
        self.path = Path(database).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS sample_versions (
                    checksum TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS active_samples (
                    name TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL REFERENCES sample_versions(checksum)
                );
            """)

    def import_fixture(self, fixture):
        value = validate_sample(json.loads(Path(fixture).read_text(encoding="utf-8")))
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        checksum = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT OR IGNORE INTO sample_versions(checksum,payload_json) VALUES (?,?)", (checksum, payload))
            connection.execute("INSERT INTO active_samples(name,checksum) VALUES ('day7',?) ON CONFLICT(name) DO UPDATE SET checksum=excluded.checksum", (checksum,))
        return checksum

    def read(self):
        # A fresh read for every request, never a process-level fixture cache.
        with sqlite3.connect(self.path) as connection:
            row = connection.execute("SELECT v.payload_json FROM active_samples a JOIN sample_versions v ON v.checksum=a.checksum WHERE a.name='day7'").fetchone()
        if row is None:
            raise ValueError("Chưa có dữ liệu mẫu ngày 7 trong database.")
        return validate_sample(json.loads(row[0]))


def create_server(*, frontend=ROOT / "frontend", database=ROOT / "runs/preview/samples.sqlite3", fixture=None, host="127.0.0.1", port=8765):
    frontend = Path(frontend).resolve()
    store = SampleStore(database)
    store.import_fixture(fixture or frontend / "fixtures/day7.json")

    class PreviewHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(frontend), **kwargs)

        def json_response(self, status, value, *, head=False):
            payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if not head:
                self.wfile.write(payload)

        def allowed_static(self, path):
            decoded = unquote(path)
            parts = decoded.lstrip("/").split("/")
            if ".." in parts or "\\" in decoded or "\x00" in decoded:
                return False
            relative = decoded.lstrip("/") or "index.html"
            candidate = (frontend / relative).resolve()
            if not candidate.is_relative_to(frontend) or not candidate.is_file():
                return False
            return relative in PAGES or (parts[0] in {"css", "js", "img"} and candidate.suffix.lower() in ASSET_SUFFIXES)

        def respond(self, *, head=False):
            path = urlsplit(self.path).path
            if path == "/api/demo/day7":
                try:
                    value = store.read()
                except (ValueError, OSError, sqlite3.Error):
                    self.json_response(500, {"error": {"message_vi": "Không đọc được dữ liệu mẫu ngày 7 từ database. Hãy khởi động lại bản xem trước."}}, head=head)
                    return
                self.json_response(200, value, head=head)
            elif not self.allowed_static(path):
                self.json_response(404, {"error": {"message_vi": "Không tìm thấy tài nguyên trong bản xem trước."}}, head=head)
            elif head:
                super().do_HEAD()
            else:
                super().do_GET()

        def do_GET(self):
            self.respond()

        def do_HEAD(self):
            self.respond(head=True)

    server = ThreadingHTTPServer((host, port), PreviewHandler)
    server.sample_store = store
    return server


def main():
    parser = argparse.ArgumentParser(description="Bản xem trước frontend với mẫu ngày 7 từ SQLite")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--database", type=Path, default=ROOT / "runs/preview/samples.sqlite3")
    parser.add_argument("--fixture", type=Path, default=ROOT / "frontend/fixtures/day7.json")
    args = parser.parse_args()
    try:
        server = create_server(port=args.port, database=args.database, fixture=args.fixture)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"Không khởi động được bản xem trước: {error}\n")
    print(f"Preview: http://127.0.0.1:{server.server_port}/?preview=1", flush=True)
    print(f"SQLite sample: {server.sample_store.path}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
