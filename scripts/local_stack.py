#!/usr/bin/env python3
"""Start, inspect and stop the two owned local demo processes."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'data/runtime/local-stack'
MANIFEST = RUNTIME / 'manifest.json'
MEDIA_HOME = ROOT / 'experiment/data/local'
SERVICES = {'media': (8010, ROOT / 'experiment/.venv/bin/python', ROOT / 'experiment', 'video_api.main:create_app'),
            'app': (8000, ROOT / '.venv/bin/python', ROOT, 'app.main:create_app')}


def process_identity(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart=', '-o', 'command='], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ''


def owns(entry, name):
    if not isinstance(entry, dict) or name not in SERVICES:
        return False
    identity = process_identity(entry.get('pid', 0))
    port, _, _, target = SERVICES[name]
    return bool(identity and identity == entry.get('identity') and target in identity and f'--port {port}' in identity
                and entry.get('root') == str(ROOT) and entry.get('port') == port)


def port_pid(port):
    result = subprocess.run(['lsof', '-nP', '-ti', f'tcp:{port}', '-sTCP:LISTEN'], capture_output=True, text=True)
    return [int(v) for v in result.stdout.split() if v.isdigit()]


def pending_jobs(path, table, statuses=('queued', 'running')):
    if not path.exists():
        return 0
    try:
        with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                return 0
            placeholders = ','.join('?' for _ in statuses)
            return db.execute(f"SELECT count(*) FROM {table} WHERE status IN ({placeholders})", statuses).fetchone()[0]
    except sqlite3.Error:
        raise RuntimeError(f'Không thể kiểm tra hàng đợi {table}') from None


def read_manifest():
    try:
        data = json.loads(MANIFEST.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_manifest(data):
    tmp = MANIFEST.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    os.chmod(tmp, 0o600)
    tmp.replace(MANIFEST)


def fetch(url, token=None):
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    with urlopen(Request(url, headers=headers), timeout=2) as response:
        return response.status, response.read()


def media_token():
    # Settings are loaded inside this process; credentials never appear in argv or output.
    from dotenv import dotenv_values
    return os.environ.get('VIDEO_API_TOKEN') or dotenv_values(ROOT / 'experiment/.env').get('VIDEO_API_TOKEN') or ''


def ready(name):
    try:
        if name == 'media':
            status, raw = fetch('http://127.0.0.1:8010/v1/readiness', media_token())
            result = json.loads(raw)
            return isinstance(result, dict) and status == 200 and result.get('ready') and result.get('storage') == 'local' and result.get('contract_version') == 'growth-media.v1'
        status, raw = fetch('http://127.0.0.1:8000/ready')
        result = json.loads(raw)
        home, html = fetch('http://127.0.0.1:8000/')
        bundle, _ = fetch('http://127.0.0.1:8000/js/app.js')
        return isinstance(result, dict) and status == home == bundle == 200 and result.get('ok') is True and result.get('data') == 'ready' and result.get('worker') == 'ready' and b'<html' in html.lower()
    except (HTTPError, URLError, OSError, ValueError):
        return False


def stop_entry(entry, name):
    if not owns(entry, name):
        return not process_identity(entry.get('pid', 0)) if isinstance(entry, dict) else True
    os.killpg(entry['pid'], signal.SIGTERM)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and owns(entry, name):
        time.sleep(.2)
    return not owns(entry, name)


def launch(name):
    port, python, cwd, target = SERVICES[name]
    args = [str(python), '-m', 'uvicorn', target, '--factory', '--host', '127.0.0.1', '--port', str(port), '--workers', '1', '--no-access-log']
    env = os.environ.copy()
    if name == 'media':
        env.update(STORAGE_BACKEND='local', DATA_DIR=str(MEDIA_HOME), PUBLIC_BASE_URL='http://127.0.0.1:8010', LOCAL_MOTION_ENABLED='false')
    else:
        env.update(PYTHONPATH=str(ROOT / 'data'), GROWTH_DATA_HOME=str(ROOT / 'data/runtime'), GROWTH_CONTENT_MODE='worker', GROWTH_LEARNING_MODE='external', MOCK_API='0')
    with (RUNTIME / f'{name}.log').open('ab') as log:
        process = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    identity = process_identity(process.pid)
    return {'pid':process.pid, 'identity':identity, 'port':port, 'root':str(ROOT)}


def start(manifest):
    for _, python, _, _ in SERVICES.values():
        if not python.is_file():
            raise RuntimeError(f'Thiếu interpreter {python}')
    if not (ROOT / 'frontend/js/app.js').is_file():
        raise RuntimeError('Thiếu frontend/js/app.js; hãy build trước')
    for name, (port, _, _, _) in SERVICES.items():
        listeners = port_pid(port)
        if listeners and not (owns(manifest.get(name), name) and manifest[name]['pid'] in listeners):
            raise RuntimeError(f'Cổng {port} đang được PID {listeners[0]} sử dụng')
    if not owns(manifest.get('media'), 'media') and pending_jobs(MEDIA_HOME / 'jobs.sqlite3', 'jobs'):
        raise RuntimeError('Media có job chưa kết thúc; không tự khởi động provider')
    if not owns(manifest.get('app'), 'app'):
        db = ROOT / 'data/runtime/growth.db'
        if (pending_jobs(db, 'content_jobs') or pending_jobs(db, 'operations')
                or pending_jobs(db, 'learning_handoffs', ('pending', 'running'))):
            raise RuntimeError('Data có công việc chưa kết thúc; kiểm tra trước khi khởi động')
    created = []
    try:
        for name in ('media', 'app'):
            if owns(manifest.get(name), name):
                if not ready(name):
                    raise RuntimeError(f'{name} đã chạy nhưng chưa sẵn sàng')
                continue
            manifest[name] = launch(name)
            created.append(name)
            save_manifest(manifest)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and owns(manifest[name], name) and not ready(name):
                time.sleep(.25)
            if not owns(manifest[name], name) or not ready(name):
                raise RuntimeError(f'{name} chưa sẵn sàng; xem {RUNTIME / (name + ".log")}')
        print('READY http://127.0.0.1:8000/?preview=0 · media 127.0.0.1:8010')
    except Exception:
        for name in reversed(created):
            if stop_entry(manifest[name], name):
                manifest.pop(name, None)
            elif name == 'app':
                break
        save_manifest(manifest)
        raise


def status(manifest):
    for name, (port, _, _, _) in SERVICES.items():
        entry = manifest.get(name)
        if owns(entry, name):
            print(f'{name}: {"READY" if ready(name) else "RUNNING_NOT_READY"} PID {entry["pid"]}')
        elif port_pid(port):
            print(f'{name}: FOREIGN_LISTENER port {port}')
        else:
            print(f'{name}: {"STALE_MANIFEST" if entry else "STOPPED"}')
    from dotenv import dotenv_values
    configured = os.environ.get('DEMO_PRODUCT_IMAGE_PATH') or dotenv_values(ROOT / '.env').get('DEMO_PRODUCT_IMAGE_PATH')
    if not configured or not Path(configured).is_file():
        print('MEDIA_INPUT_MISSING')


def stop(manifest):
    for name in ('app', 'media'):
        entry = manifest.get(name)
        if entry and not stop_entry(entry, name):
            print(f'{name}: vẫn đang chạy PID {entry.get("pid")}; không gửi SIGKILL')
            save_manifest(manifest)
            raise RuntimeError('Một tiến trình chưa dừng; dữ liệu và trạng thái được giữ lại')
        manifest.pop(name, None)
    save_manifest(manifest)
    if manifest:
        raise RuntimeError('Một tiến trình chưa dừng; dữ liệu và trạng thái được giữ lại')
    print('STOPPED')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('start', 'status', 'stop'))
    args = parser.parse_args()
    if args.command == 'status':
        status(read_manifest())
        return 0
    os.umask(0o077)
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (RUNTIME / 'launcher.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest = read_manifest()
        try:
            {'start':start, 'status':status, 'stop':stop}[args.command](manifest)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
