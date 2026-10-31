import sqlite3
import json
import sys
from pathlib import Path

import pytest

from scripts import local_stack


def test_reused_pid_is_not_signalled(monkeypatch):
    entry={'pid':123, 'port':8000, 'root':str(local_stack.ROOT), 'identity':'old process'}
    monkeypatch.setattr(local_stack, 'process_identity', lambda pid: 'new unrelated process')
    signals=[]
    monkeypatch.setattr(local_stack.os, 'killpg', lambda *args: signals.append(args))
    assert local_stack.stop_entry(entry, 'app') is False
    assert signals == []


def test_pending_job_check_is_read_only(tmp_path):
    db=tmp_path/'jobs.sqlite3'
    with sqlite3.connect(db) as connection:
        connection.execute('CREATE TABLE jobs(status TEXT)')
        connection.executemany('INSERT INTO jobs VALUES(?)', [('queued',),('running',),('done',)])
    assert local_stack.pending_jobs(db,'jobs') == 2
    assert local_stack.pending_jobs(tmp_path/'absent.db','jobs') == 0
    assert not (tmp_path/'absent.db').exists()


def test_status_reports_unready_worker(monkeypatch, capsys):
    import dotenv
    monkeypatch.setattr(dotenv, 'dotenv_values', lambda *args: {})
    monkeypatch.delenv('DEMO_PRODUCT_IMAGE_PATH', raising=False)
    monkeypatch.setattr(local_stack, 'owns', lambda entry, name: name == 'app')
    monkeypatch.setattr(local_stack, 'port_pid', lambda port: [])
    def fetch(url, token=None):
        if url.endswith('/ready'):
            return 200, json.dumps({'ok':False,'data':'ready','worker':'unavailable'}).encode()
        if url.endswith('/'):
            return 200, b'<html></html>'
        return 200, b'javascript'
    monkeypatch.setattr(local_stack, 'fetch', fetch)
    assert not local_stack.ready('app')
    local_stack.status({'app':{'pid':123}})
    assert 'app: RUNNING_NOT_READY PID 123' in capsys.readouterr().out


@pytest.mark.parametrize('status', ['pending', 'running'])
def test_pending_learning_blocks_start_without_launching(tmp_path, monkeypatch, status):
    db=tmp_path/'data/runtime/growth.db';db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as connection:
        connection.execute('CREATE TABLE learning_handoffs(status TEXT)')
        connection.executemany('INSERT INTO learning_handoffs VALUES(?)', [(status,),('completed',),('failed',)])
    bundle=tmp_path/'frontend/js/app.js';bundle.parent.mkdir(parents=True);bundle.write_text('fixture')
    python=Path(sys.executable)
    monkeypatch.setattr(local_stack,'ROOT',tmp_path)
    monkeypatch.setattr(local_stack,'MEDIA_HOME',tmp_path/'media')
    monkeypatch.setattr(local_stack,'SERVICES',{'media':(8010,python,tmp_path,'media'), 'app':(8000,python,tmp_path,'app')})
    monkeypatch.setattr(local_stack,'port_pid',lambda port: [])
    monkeypatch.setattr(local_stack,'owns',lambda entry,name: False)
    launches=[];monkeypatch.setattr(local_stack,'launch',lambda name: launches.append(name))
    assert local_stack.pending_jobs(db,'learning_handoffs',('pending','running'))==1
    with pytest.raises(RuntimeError,match='chưa kết thúc'):
        local_stack.start({})
    assert launches==[]


def test_stop_keeps_media_running_when_app_does_not_drain(monkeypatch):
    manifest={'app':{'pid':11},'media':{'pid':22}}
    attempts=[];saved=[]
    monkeypatch.setattr(local_stack,'stop_entry',lambda entry,name: attempts.append(name) or name!='app')
    monkeypatch.setattr(local_stack,'save_manifest',lambda value: saved.append(dict(value)))
    with pytest.raises(RuntimeError,match='chưa dừng'):
        local_stack.stop(manifest)
    assert attempts==['app'] and manifest['media']['pid']==22
    assert saved==[manifest]
