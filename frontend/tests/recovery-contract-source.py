"""Create and recover an old failed attempt in a disposable database with fake models."""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.core.settings import Settings
from app.runtime.data_worker import DataWorker
from data.growth_data.api import create_app
from data.growth_data.models import DEMO_D_BRIEF
from tests.integration.api.test_data_native import NativeTransport, all_events, headers
from tests.integration.api.test_day_one_outcome import TerminalRefereeTransport, finish_day_start, queue_renegotiation

with tempfile.TemporaryDirectory(prefix='growth-recovery-ui-') as tmp, contextlib.redirect_stdout(io.StringIO()):
    defaults={'execution_profile':'external','content_mode':'worker','learning_mode':'external','driver_config':{'agent_version':'native'}}
    app=create_app(Path(tmp),bootstrap_defaults=defaults)
    service=app.state.service
    settings=Settings(_env_file=None,llm_mode='offline',media_mode='offline')
    worker=DataWorker(service,settings)
    with TestClient(app) as client:
        run=client.get('/api/state').json()['run_id']
        assert client.post('/api/brief/confirm',json=DEMO_D_BRIEF.copy(),headers=headers('brief')).status_code==200
        native_day=(client,service,worker,run)
        state,_=finish_day_start(native_day,NativeTransport(settings,set()))
        original=state['pending_card']
        operation=queue_renegotiation(native_day,original,'legacy-feedback')
        worker.llm_factory=lambda run,settings,store: TerminalRefereeTransport(settings,action='ask_human',reason='Chưa có gói điều chỉnh.')
        with patch.object(service,'restore_negotiation_offer',lambda c,r,op,**kwargs:op['result']):
            worker._operation(operation)
        before=client.get('/api/state').json()
        events_before=all_events(client,run)
        outcome=before['renegotiation']
        assert outcome['restoration_allowed'] is True
        body={'operation_id':outcome['operation_id'],'expected_operation_version':outcome['operation_version'],
              'source_card_id':outcome['source_card_id'],'expected_source_card_version':outcome['source_card_version'],
              'expected_brief_version':before['brief']['version'],'expected_day':before['day']}
        response=client.post('/api/negotiation/restore',json=body,headers=headers('restore-old'))
        assert response.status_code==200,response.text
        after=client.get('/api/state').json()
        events_after=all_events(client,run)
        result={'before':before,'events_before':events_before,'after':after,'events_after':events_after,'original':original,'response':response.json()}
print(json.dumps(result,ensure_ascii=False))
