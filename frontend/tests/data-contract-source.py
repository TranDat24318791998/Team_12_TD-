"""Build isolated offline runs and return actual seller HTTP projections for the UI test."""
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.core.settings import Settings
from app.simulation.runner import run
from data.growth_data.api import create_app
from data.growth_data.storage import one


os.environ['LLM_MODE'] = 'offline'
os.environ['MEDIA_MODE'] = 'offline'
os.environ['DEMO_PRODUCT_IMAGE_PATH'] = ''
settings = Settings(_env_file=None, llm_mode='offline', media_mode='offline',
                    demo_shop='D', demo_product_image_path='')
defaults = {'execution_profile': 'external', 'content_mode': 'worker', 'learning_mode': 'external',
            'mode': 'offline', 'driver_config': {'agent_version': 'native'}}
with tempfile.TemporaryDirectory(prefix='growth-ui-contract-') as tmp, contextlib.redirect_stdout(io.StringIO()):
    home = Path(tmp)
    off = run(settings, 1, False, 42, home=home)
    app = create_app(home, content_mode='worker', learning_mode='external', bootstrap_defaults=defaults)
    service = app.state.service
    with service.store.connect() as conn:
        sid = one(conn, 'SELECT session_id FROM runs WHERE run_id=?', (off.run_id,))['session_id']
    on = run(settings, 1, True, 42, home=home, seller_session_id=sid)
    seller = service.authenticate(sid=sid)
    with service.store.connect(write=True) as conn:
        group = service.comparison_attach(conn, seller, {'run_on': on.run_id, 'run_off': off.run_id})['comparison_id']
    with TestClient(app) as client:
        client.cookies.set('growth_sid', sid)
        def get(path):
            response = client.get(path)
            assert response.status_code == 200, (path, response.status_code, response.text)
            return response.json()
        state = get('/api/state')
        pages, cursor = [], 0
        while True:
            page = get(f'/api/events?after={cursor}&run_id={on.run_id}')
            pages.append(page)
            cursor = page['last_seq']
            if not page['has_more']:
                break
        report = get('/api/proof')
        pair = get(f'/api/proof/events?comparison_id={group}')
        # Exercise the real seller capability projection with a safely retryable
        # failure and then an unknown receipt, in this disposable database only.
        with service.store.connect(write=True) as conn:
            conn.execute("UPDATE learning_handoffs SET status='failed',error_code='TEST_FAILURE' WHERE run_id=?", (on.run_id,))
            conn.execute("UPDATE reflection_receipts SET status='failed' WHERE run_id=?", (on.run_id,))
        retryable = get('/api/state')
        with service.store.connect(write=True) as conn:
            conn.execute("UPDATE reflection_receipts SET status='unknown' WHERE run_id=?", (on.run_id,))
        unknown = get('/api/state')
    brief_app = create_app(home/'brief-check', bootstrap_defaults=defaults)
    with TestClient(brief_app) as client:
        initial_response = client.get('/api/state')
        assert initial_response.status_code == 200
        brief_initial = initial_response.json()
        preset = brief_initial['brief_preset']
        assert brief_initial['brief_editable'] is False and brief_initial['brief'] is None
        def confirm(key, body):
            return client.post('/api/brief/confirm', json=body, headers={'X-Request-ID':key,'Idempotency-Key':key})
        assert confirm('bad-goal', {**preset, 'goal_vi':'Mục tiêu bị sửa'}).status_code >= 400
        assert confirm('bad-cap', {**preset, 'ads_daily_cap':1}).status_code >= 400
        assert client.get('/api/state').json()['brief'] is None
        approved = confirm('fixed-preset', preset)
        assert approved.status_code == 200, approved.text
        brief_confirmed = client.get('/api/state').json()
        assert all(brief_confirmed['brief'][key] == value for key,value in preset.items())
    result = {'state': state, 'pages': pages, 'report': report, 'pair': pair,
              'retryable': retryable, 'unknown': unknown, 'brief_initial':brief_initial,
              'brief_confirmed':brief_confirmed}
print(json.dumps(result, ensure_ascii=False))
