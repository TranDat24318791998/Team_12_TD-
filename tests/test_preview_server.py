"""The preview's public mock snapshot is persisted and served from SQLite."""

import copy
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from scripts.preview_server import SampleStore, create_server, validate_sample


def sample():
    return {"schema_version": 1, "state": {"run_id": "sample-on", "day": 7, "step": "complete"}, "events": [], "proof": {"days": 7}, "source": {"kind": "sqlite_sample", "label_vi": "Dữ liệu minh họa"}}


class PreviewServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.frontend = self.root / "frontend"
        self.frontend.mkdir()
        self.fixture = self.frontend / "fixtures/day7.json"
        self.fixture.parent.mkdir()
        self.fixture.write_text(json.dumps(sample()), encoding="utf-8")
        self.database = self.root / "runtime/samples.sqlite3"

    def start_server(self):
        server = create_server(frontend=self.frontend, database=self.database, fixture=self.fixture, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def get(self, server, path, method="GET"):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, dict(response.headers), response.read()
        finally:
            connection.close()

    def test_persistence_and_checksum_versioning(self):
        store = SampleStore(self.database)
        original_checksum = store.import_fixture(self.fixture)
        self.assertEqual(SampleStore(self.database).read(), sample())
        self.assertEqual(SampleStore(self.database).import_fixture(self.fixture), original_checksum)
        updated = sample()
        updated["source"]["label_vi"] = "Mẫu cập nhật"
        self.fixture.write_text(json.dumps(updated), encoding="utf-8")
        self.assertNotEqual(store.import_fixture(self.fixture), original_checksum)
        self.assertEqual(SampleStore(self.database).read(), updated)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sample_versions").fetchone()[0], 2)

    def test_invalid_fixture_leaves_saved_sample_unchanged(self):
        store = SampleStore(self.database)
        store.import_fixture(self.fixture)
        for field, value in [("schema_version", 2), ("events", {}), ("proof", {"days": 6}), ("source", {"kind": "live"}), ("state", {"day": 7, "step": "complete"})]:
            invalid = copy.deepcopy(sample())
            invalid[field] = value
            with self.subTest(field=field):
                self.fixture.write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaises(ValueError):
                    store.import_fixture(self.fixture)
                self.assertEqual(store.read(), sample())

    def test_each_http_request_reads_database(self):
        server = self.start_server()
        self.fixture.unlink()
        status, headers, body = self.get(server, "/api/demo/day7")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(json.loads(body), sample())
        updated = sample()
        updated["source"]["label_vi"] = "Đọc lại từ database"
        with sqlite3.connect(self.database) as connection:
            connection.execute("UPDATE sample_versions SET payload_json=?", (json.dumps(updated),))
        self.assertEqual(json.loads(self.get(server, "/api/demo/day7")[2]), updated)
        status, _, body = self.get(server, "/api/demo/day7", "HEAD")
        self.assertEqual((status, body), (200, b""))

    def test_only_built_frontend_assets_are_public(self):
        (self.frontend / "index.html").write_text("<h1>Preview</h1>")
        (self.frontend / "img").mkdir()
        (self.frontend / "img/fan.svg").write_text("<svg/>")
        (self.frontend / "src").mkdir()
        (self.frontend / "src/private.js").write_text("private source")
        secret = self.root / "secret.txt"
        secret.write_text("secret")
        (self.frontend / "img/escape.txt").symlink_to(secret)
        server = self.start_server()
        for path in ("/", "/index.html?preview=1", "/img/fan.svg"):
            with self.subTest(path=path):
                self.assertEqual(self.get(server, path)[0], 200)
        for path in ("/fixtures/day7.json", "/src/private.js", "/img/", "/data/seed.json", "/%2e%2e/secret.txt", "/img/escape.txt", "/api/state"):
            with self.subTest(path=path):
                status, _, body = self.get(server, path)
                self.assertEqual(status, 404)
                self.assertIn("message_vi", json.loads(body)["error"])

    def test_missing_database_sample_has_vietnamese_error(self):
        server = self.start_server()
        with sqlite3.connect(self.database) as connection:
            connection.execute("DELETE FROM active_samples")
        status, headers, body = self.get(server, "/api/demo/day7")
        self.assertEqual(status, 500)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("database", json.loads(body)["error"]["message_vi"])


if __name__ == "__main__":
    unittest.main()
