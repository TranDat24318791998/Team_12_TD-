"""Day-one terminal verdicts through Data + native worker, with fake providers."""

import asyncio
import json

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage
import pytest

from app.core.settings import Settings
from app.runtime.data_worker import DataWorker
from data.growth_data.api import create_app
from data.growth_data.models import DEMO_D_BRIEF
from data.growth_data.service import Principal
from data.growth_data.errors import Fault
from data.growth_data.storage import one
from tests.integration.api.test_data_native import FakeContent, NativeTransport, all_events, headers, tool


COMPLETION_REASON = (
    'Tiến trình thương lượng đã hoàn tất: sàn chấp nhận nguyên gói phản đề xuất của shop. '
    'Các điều khoản phù hợp với brief. Mục tiêu 24 đơn là kỳ vọng, không được bảo đảm.'
)


class TerminalRefereeTransport(NativeTransport):
    def __init__(self, settings, *, action='stop', reason=COMPLETION_REASON, unresolved_terms=None,
                 clarify_action=None, clarification_error=False):
        initial = {'content_refresh': True, 'ads_daily_budget': 45000, 'voucher_pct': 10,
                   'stop_roas_below': 4.0, 'stop_after_days': 2, 'duration_days': 3}
        super().__init__(settings, set(), initial)
        self.action, self.reason = action, reason
        self.unresolved_terms = unresolved_terms or []
        self.clarify_action = clarify_action
        self.clarification_error = clarification_error
        self.clarifications = 0
        self.referee_calls = {}
        self.accepted_context = None

    def invoke_tools(self, messages, **kwargs):
        returned = [m for m in messages if isinstance(m, ToolMessage) and m.name == 'get_referee_context']
        if ':referee:' in kwargs['run_name']:
            self.referee_calls[kwargs['run_name']] = self.referee_calls.get(kwargs['run_name'], 0) + 1
        if ':referee:' in kwargs['run_name'] and returned:
            context = json.loads(returned[-1].content)
            if context['turns'][-1]['action'] == 'accept':
                self.accepted_context = context
                clarification = any(isinstance(m, ToolMessage) and m.name == 'finish_referee' for m in messages)
                if clarification:
                    self.clarifications += 1
                    if self.clarification_error:
                        raise ConnectionError('fake provider unavailable during clarification')
                action = self.clarify_action if clarification and self.clarify_action else self.action
                return AIMessage(content='', tool_calls=[tool('finish_referee', {
                    'action': action, 'reason_vi': self.reason,
                    'evidence_refs': [t['turn_id'] for t in context['turns']],
                    'unresolved_terms': [] if clarification and action=='continue' else self.unresolved_terms, 'next_actor': None,
                    'focused_question': None,
                }, 'clarified' if clarification else 'finish')])
        return super().invoke_tools(messages, **kwargs)


@pytest.fixture
def native_day(tmp_path):
    defaults = {'execution_profile': 'external', 'content_mode': 'worker',
                'learning_mode': 'external', 'driver_config': {'agent_version': 'native'}}
    app = create_app(tmp_path, bootstrap_defaults=defaults)
    service = app.state.service
    settings = Settings(_env_file=None, llm_mode='offline', media_mode='offline')
    worker = DataWorker(service, settings)
    with TestClient(app) as client:
        run = client.get('/api/state').json()['run_id']
        assert client.post('/api/brief/confirm', json=DEMO_D_BRIEF.copy(), headers=headers('brief')).status_code == 200
        yield client, service, worker, run


def finish_day_start(native_day, transport):
    client, service, worker, run = native_day
    worker.llm_factory = lambda run, settings, store: transport if settings.demo_shop == 'D' else NativeTransport(settings, set())
    assert client.post('/api/day/start', json={}, headers=headers('start')).status_code == 202
    with service.store.connect() as c:
        operation = one(c, "SELECT * FROM operations WHERE run_id=? AND kind='start_day'", (run,))
    worker._operation(operation)
    return client.get('/api/state').json(), all_events(client, run)


def finish_background_content(native_day):
    client, service, worker, run=native_day
    worker.content_factory=FakeContent
    with service.store.connect() as c:
        jobs=[row['job_id'] for row in c.execute("SELECT job_id FROM content_jobs WHERE run_id=? AND shop_id!='D' AND status='queued'",(run,))]
    for job_id in jobs:
        with service.store.connect() as c:job=service.entity(c,'content_jobs',run,'job_id',job_id)
        asyncio.run(worker._content(job))


@pytest.mark.parametrize('action,reason,terms', [
    ('stop', 'Gói không còn phù hợp; dừng đề xuất này.', ['Shop không còn muốn triển khai.']),
    ('ask_human', 'Dự báo chưa bảo đảm mục tiêu; cần người bán xem xét.', []),
])
def test_initial_failure_surfaces_reason_without_seller_or_content_completion(native_day, action, reason, terms):
    client, service, worker, run = native_day
    transport = TerminalRefereeTransport(worker.settings, action=action, reason=reason, unresolved_terms=terms)
    state, events = finish_day_start(native_day, transport)
    assert state['step'] == 'day_done' and not state['pending_card']
    finished = next(e for e in events if e['type'] == 'negotiation_finished' and e['shop_id'] == 'D')
    assert finished['data']['status'] == 'failed' and finished['data']['referee_action'] == action
    assert not [e for e in events if e['shop_id'] == 'D' and e['type'] in {'seller_decision', 'content_created', 'package_applied'}]
    outcome = state.get('negotiation') or {}
    assert outcome.get('status') == 'failed', 'Initial failure reason is missing from seller state'
    assert outcome['reason_vi'] == reason
    assert outcome['referee_action'] == action
    assert outcome['negotiation_id'] == finished['data']['negotiation_id']
    assert transport.clarifications == 0
    finish_background_content(native_day)
    assert client.post('/api/night',json={'expected_day':1},headers=headers('initial-failure-night')).status_code==202


def test_agreed_stop_is_clarified_then_presents_offer_for_seller_approval(native_day):
    client, service, worker, run = native_day
    transport = TerminalRefereeTransport(worker.settings, clarify_action='continue')
    state, events = finish_day_start(native_day, transport)
    card = state['pending_card']
    assert card is not None, 'Exact accepted package was dropped after referee described normal completion as stop'
    assert state['step'] == 'awaiting_decision'
    assert card['package'] == {'content_refresh': True, 'ads_daily_budget': 45000, 'voucher_pct': 3,
                               'stop_roas_below': 6.5, 'stop_after_days': 2, 'duration_days': 3}
    assert transport.clarifications == 1 and max(transport.referee_calls.values()) <= 3
    final_review = [e for e in events if e['type'] == 'referee_review' and e['shop_id'] == 'D'][-1]
    assert final_review['data']['action'] == 'continue'
    assert state['negotiation']['status'] == 'agreed'
    assert not state['content_draft'] and not state['active_package']
    with service.store.connect() as c:
        assert not one(c, "SELECT decision_id FROM decisions WHERE run_id=? AND shop_id='D'", (run,))
        assert not one(c, "SELECT campaign_id FROM campaigns WHERE run_id=? AND shop_id='D'", (run,))


@pytest.mark.parametrize('provider_error', [False, True])
def test_unresolved_stop_ambiguity_remains_safe_failure(native_day, provider_error):
    client, service, worker, run = native_day
    transport = TerminalRefereeTransport(worker.settings, clarification_error=provider_error)
    state, events = finish_day_start(native_day, transport)
    assert not state['pending_card'] and state['step'] == 'day_done'
    assert state['negotiation']['status'] == 'failed'
    assert state['negotiation']['referee_action'] == 'ask_human'
    assert 'chưa nêu điều khoản' in state['negotiation']['reason_vi']
    assert transport.clarifications == 1 and max(transport.referee_calls.values()) <= 3


@pytest.mark.parametrize('action,terms,clarify,expected', [
    ('continue', [], None, 'agreed'),
    ('stop', [], 'continue', 'agreed'),
    ('refocus', ['Cần dự báo cho gói đã chấp nhận.'], 'continue', 'agreed'),
    ('stop', ['Không thống nhất điều khoản triển khai.'], None, 'failed'),
    ('ask_human', [], None, 'failed'),
    ('refocus', ['Cần người bán xác nhận điều kiện bổ sung.'], None, 'failed'),
])
def test_initial_verdict_matrix_uses_exact_accepted_public_forecast(native_day, action, terms, clarify, expected):
    client, service, worker, run = native_day
    transport=TerminalRefereeTransport(worker.settings,action=action,unresolved_terms=terms,clarify_action=clarify)
    state,events=finish_day_start(native_day,transport)
    assert state['negotiation']['status']==expected
    assert bool(state['pending_card']) is (expected=='agreed')
    assert max(transport.referee_calls.values())<=3
    assert transport.accepted_context['forecast_turn_id']==transport.accepted_context['turns'][-1]['turn_id']
    assert transport.accepted_context['forecast'] is not None
    if state['pending_card']:
        assert transport.accepted_context['forecast']==state['pending_card']['forecast']
        assert not state['active_package'] and not state['content_draft']
    elif action=='refocus':
        assert state['negotiation']['referee_action']=='ask_human'


def test_initial_technical_failure_has_reason_and_no_referee_verdict(native_day, monkeypatch):
    import app.runtime.data_worker as runtime
    client, service, worker, run = native_day

    def unavailable(*args, **kwargs):
        raise RuntimeError('fake graph failure')

    monkeypatch.setattr(runtime, 'run_negotiation', unavailable)
    state, events = finish_day_start(native_day, NativeTransport(worker.settings, set()))
    assert not state['pending_card']
    assert state['negotiation']['status'] == 'failed'
    assert state['negotiation']['referee_action'] is None
    assert state['negotiation']['reason_vi'] == 'Tác vụ agent chưa hoàn tất'


def test_successful_day_with_no_eligible_demo_shop_has_no_unknown_attempt(native_day, monkeypatch):
    client, service, worker, run = native_day
    original = service.eligibility

    def ineligible(c, run_id, shop_id):
        return {'eligible': False, 'reason_codes': ['STOCK_LOW']} if shop_id == 'D' else original(c, run_id, shop_id)

    monkeypatch.setattr(service, 'eligibility', ineligible)
    state, events = finish_day_start(native_day, NativeTransport(worker.settings, set()))
    assert state['step'] == 'day_done' and not state['pending_card']
    assert state['negotiation'] is None


def queue_renegotiation(native_day, card, key):
    client, service, worker, run = native_day
    request = {'card_id': card['card_id'], 'expected_card_version': card['version'],
               'expected_brief_version': card['brief_version'], 'action': 'negotiate', 'note_vi': 'giảm thêm được khg'}
    queued = client.post('/api/decision', json=request, headers=headers(key))
    assert queued.status_code == 202, queued.text
    assert client.post('/api/decision', json=request, headers=headers(key)).json() == queued.json()
    with service.store.connect() as c:
        operation = one(c, 'SELECT * FROM operations WHERE run_id=? AND operation_id=?', (run, queued.json()['operation_id']))
    return operation


def test_failed_renegotiations_restore_original_until_seller_approves_at_retry_cap(native_day):
    client, service, worker, run = native_day
    state, _ = finish_day_start(native_day, NativeTransport(worker.settings, set()))
    original = state['pending_card']
    assert original
    transport = TerminalRefereeTransport(worker.settings, action='ask_human', reason='Chưa có điều chỉnh phù hợp.')
    worker.llm_factory = lambda run, settings, store: transport
    for index in range(2):
        previous = state['pending_card']
        operation = queue_renegotiation(native_day, previous, f'renegotiate-{index}')
        pending = client.get('/api/state').json()
        assert pending['step'] == 'negotiating' and not pending['pending_card']
        assert client.post('/api/night', json={'expected_day': 1}, headers=headers(f'pending-night-{index}')).status_code == 409
        worker._operation(operation)
        state = client.get('/api/state').json()
        restored = state['pending_card']
        assert restored is not None, 'Failed renegotiation discarded the original agent-agreed offer'
        assert restored['card_id'] != previous['card_id'] and restored['version'] == 1
        assert restored['proposal_id'] == original['proposal_id']
        assert restored['negotiation_id'] == original['negotiation_id']
        assert restored['package'] == original['package']
        assert restored['proposal_version'] > previous['proposal_version']
        assert restored['forecast'] and restored['forecast']['point'] == original['forecast']['point']
        assert restored['can_negotiate'] is (index == 0) and restored['renegotiations_left'] == 1-index
        outcome = state['renegotiation']
        assert outcome['status'] == 'failed' and outcome['referee_action'] == 'ask_human'
        assert outcome['restoration_status'] == 'restored' and outcome['restored_card_id'] == restored['card_id']
        assert outcome['source_card_id'] == previous['card_id']
        with service.store.connect() as c:
            before=c.execute("SELECT COUNT(*) FROM cards WHERE run_id=? AND shop_id='D'", (run,)).fetchone()[0]
        worker._operation(operation)
        with service.store.connect() as c:
            assert c.execute("SELECT COUNT(*) FROM cards WHERE run_id=? AND shop_id='D'", (run,)).fetchone()[0] == before
        assert client.post('/api/night', json={'expected_day': 1}, headers=headers(f'restored-night-{index}')).status_code == 409
        stale = {'card_id': previous['card_id'], 'expected_card_version': previous['version'],
                 'expected_brief_version': previous['brief_version'], 'action': 'accept'}
        assert client.post('/api/decision', json=stale, headers=headers(f'stale-{index}')).status_code in {404, 409}
    blocked = {'card_id': restored['card_id'], 'expected_card_version': restored['version'],
               'expected_brief_version': restored['brief_version'], 'action': 'negotiate', 'note_vi': 'Giảm nữa'}
    assert client.post('/api/decision', json=blocked, headers=headers('over-cap')).json()['error']['code'] == 'MAX_RENEGOTIATIONS'
    assert client.get('/api/state').json()['pending_card']['card_id'] == restored['card_id']
    with service.store.connect() as c:
        decisions = c.execute("SELECT action,target_version FROM decisions WHERE run_id=? AND target_id=? ORDER BY rowid", (run, original['proposal_id'])).fetchall()
        assert [row['action'] for row in decisions] == ['request_changes', 'request_changes']
        assert len({row['target_version'] for row in decisions}) == 2
        assert c.execute("SELECT COUNT(*) FROM negotiations WHERE run_id=? AND shop_id='D' AND status='failed'", (run,)).fetchone()[0] == 2
        assert c.execute("SELECT COUNT(*) FROM cards WHERE run_id=? AND shop_id='D' AND status='pending'", (run,)).fetchone()[0] == 1
        assert not one(c, "SELECT job_id FROM content_jobs WHERE run_id=? AND shop_id='D'", (run,))
    approved = client.post('/api/decision', json={**blocked, 'action': 'accept', 'note_vi': ''}, headers=headers('accept-original'))
    assert approved.status_code == 200, approved.text
    state = client.get('/api/state').json()
    assert state['step'] == 'content_review' and state['content_draft']['card_id'] == restored['card_id']
    with service.store.connect() as c:
        job = one(c, "SELECT * FROM content_jobs WHERE run_id=? AND shop_id='D'", (run,))
    worker.content_factory = FakeContent
    asyncio.run(worker._content(job))
    draft = client.get('/api/state').json()['content_draft']
    applied = client.post('/api/content/apply', json={
        'card_id': draft['card_id'], 'expected_brief_version': draft['brief_version'],
        'expected_draft_version': draft['version'], 'expected_job_id': draft['job_id'],
        'expected_content_id': draft['content_id'], 'cover_option': 'B', 'skip_video': True,
        'video_review_ack': False,
    }, headers=headers('apply-original'))
    assert applied.status_code == 200, applied.text
    active = client.get('/api/state').json()['active_package']
    assert active['card_id'] == restored['card_id'] and active['package'] == original['package']
    finish_background_content(native_day)
    assert client.post('/api/night',json={'expected_day':1},headers=headers('applied-original-night')).status_code==202


@pytest.mark.parametrize('invalid,reason', [
    ('rules', 'Voucher vượt luật shop.'),
    ('cost', 'Gói không đạt lãi tối thiểu.'),
    ('stock', 'Tồn kho chưa đủ'),
    ('brief', 'Ngân sách vượt mức công khai.'),
])
def test_invalid_original_offer_is_blocked_with_reason(native_day, invalid, reason):
    client, service, worker, run = native_day
    state, _ = finish_day_start(native_day, NativeTransport(worker.settings, set()))
    original = state['pending_card']
    operation = queue_renegotiation(native_day, original, 'renegotiate-invalid')
    with service.store.connect(write=True) as c:
        if invalid == 'rules':
            c.execute("UPDATE shop_rules SET voucher_max_pct=2 WHERE run_id=? AND shop_id='D'", (run,))
        elif invalid == 'cost':
            c.execute("UPDATE product_costs SET unit_cost_vnd=180000 WHERE run_id=? AND product_id='SP004'", (run,))
        elif invalid == 'stock':
            c.execute("UPDATE inventory SET available_units=29 WHERE run_id=? AND product_id='SP004'", (run,))
        else:
            c.execute("UPDATE runs SET brief_json=json_set(brief_json,'$.ads_daily_cap',40000) WHERE run_id=?", (run,))
    worker.llm_factory = lambda run, settings, store: TerminalRefereeTransport(settings, action='ask_human', reason='Chưa có điều chỉnh phù hợp.')
    worker._operation(operation)
    state = client.get('/api/state').json()
    assert not state['pending_card'] and not state['active_package']
    outcome = state['renegotiation']
    assert outcome['status'] == 'failed' and outcome['restoration_status'] == 'blocked'
    assert outcome['restored_card_id'] is None and reason in outcome['restoration_reason_vi']
    with service.store.connect() as c:
        assert not one(c, "SELECT decision_id FROM decisions WHERE run_id=? AND shop_id='D' AND action='approve'", (run,))
        assert not one(c, "SELECT job_id FROM content_jobs WHERE run_id=? AND shop_id='D'", (run,))
    finish_background_content(native_day)
    assert client.post('/api/night',json={'expected_day':1},headers=headers('blocked-original-night')).status_code==202


def test_restored_offer_can_be_rejected_without_being_resurrected(native_day):
    client, service, worker, run = native_day
    state, _ = finish_day_start(native_day, NativeTransport(worker.settings, set()))
    original = state['pending_card']
    operation = queue_renegotiation(native_day, original, 'renegotiate-reject')
    worker.llm_factory = lambda run, settings, store: TerminalRefereeTransport(settings, action='stop',
        reason='Không có gói điều chỉnh phù hợp.', unresolved_terms=['Không thống nhất điều chỉnh.'])
    worker._operation(operation)
    state = client.get('/api/state').json()
    restored = state['pending_card']
    assert restored and state['renegotiation']['referee_action'] == 'stop'
    response=client.post('/api/decision',json={'card_id':restored['card_id'],'expected_card_version':restored['version'],
        'expected_brief_version':restored['brief_version'],'action':'reject'},headers=headers('reject-restored'))
    assert response.status_code == 200, response.text
    worker._operation(operation)
    state=client.get('/api/state').json()
    assert not state['pending_card'] and state['step']=='day_done'
    with service.store.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM decisions WHERE run_id=? AND shop_id='D' AND action='reject'",(run,)).fetchone()[0]==1
        assert not one(c,"SELECT job_id FROM content_jobs WHERE run_id=? AND shop_id='D'",(run,))
        assert not one(c,"SELECT campaign_id FROM campaigns WHERE run_id=? AND shop_id='D'",(run,))
    finish_background_content(native_day)
    assert client.post('/api/night',json={'expected_day':1},headers=headers('rejected-original-night')).status_code==202


def test_unknown_restart_does_not_restore_original_or_reissue_attempt(native_day):
    client, service, worker, run = native_day
    state, _ = finish_day_start(native_day, NativeTransport(worker.settings, set()))
    operation = queue_renegotiation(native_day, state['pending_card'], 'renegotiate-unknown')
    principal=Principal('native_orchestrator','orchestrator',None,(run,),('*',))
    with service.store.connect(write=True) as c:
        operation=service.operation_claim(c,principal,run,operation['operation_id'],{'expected_version':operation['version']})
        runtime=service.entity(c,'shop_runtime',run,'shop_id','D')
    body={'day':1,'kind':'propose','expected_shop_version':runtime['version'],
          'source_card_id':operation['result']['source_card_id'],'owner_note_vi':'Giảm thêm'}
    negotiation=service.command(principal,run,'native/negotiation',operation['operation_id']+':D',body,
        lambda c:service.new_negotiation(c,principal,run,'D',body))
    worker._recover()
    state=client.get('/api/state').json()
    assert not state['pending_card']
    assert state['renegotiation']['status']=='unknown'
    assert state['renegotiation']['restoration_status'] is None
    assert state['negotiation']['status']=='unknown'
    with service.store.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM negotiations WHERE run_id=? AND shop_id='D'",(run,)).fetchone()[0]==2
        assert not one(c,"SELECT seq FROM events WHERE run_id=? AND type='offer_restored'",(run,))
        assert not one(c,"SELECT call_id FROM llm_call_reservations WHERE run_id=?",(run,))


def test_legacy_failed_attempt_restores_only_on_explicit_versioned_seller_command(native_day, monkeypatch):
    client, service, worker, run = native_day
    state, _ = finish_day_start(native_day, NativeTransport(worker.settings, set()))
    original=state['pending_card']
    operation=queue_renegotiation(native_day,original,'legacy-failed')
    worker.llm_factory=lambda run, settings, store: TerminalRefereeTransport(settings,action='ask_human',reason='Chưa có gói điều chỉnh.')
    with monkeypatch.context() as old_code:
        old_code.setattr(service,'restore_negotiation_offer',lambda c,r,op,**kwargs:op['result'])
        worker._operation(operation)
    state=client.get('/api/state').json()
    assert not state['pending_card'] and state['renegotiation']['status']=='failed'
    outcome=state['renegotiation']
    assert outcome.get('restoration_allowed') is True, 'Legacy failed adjustment has no explicit way to restore its original offer'
    finish_background_content(native_day)
    night=client.post('/api/night',json={'expected_day':1},headers=headers('legacy-premature-night'))
    assert night.status_code==409 and night.json()['error']['code']=='OFFER_REVIEW_REQUIRED',night.text
    simulator=Principal('fixture_simulator','simulator',None,(run,),('D',))
    with service.store.connect(write=True) as c:
        inventory=service.entity(c,'inventory',run,'product_id','SP004')
        with pytest.raises(Fault,match='đề xuất gốc') as blocked:
            service.settle(c,simulator,run,'D',{'day':1,'expected_inventory_version':inventory['version']})
        assert blocked.value.code=='OFFER_REVIEW_REQUIRED'
    body={'operation_id':outcome['operation_id'],'expected_operation_version':outcome['operation_version'],
          'source_card_id':outcome['source_card_id'],'expected_source_card_version':outcome['source_card_version'],
          'expected_brief_version':state['brief']['version'],'expected_day':state['day']}
    assert client.post('/api/negotiation/restore',json={**body,'expected_operation_version':1},headers=headers('stale-restore')).status_code==409
    response=client.post('/api/negotiation/restore',json=body,headers=headers('restore-old'))
    assert response.status_code==200,response.text
    assert response.json()['restoration_status']=='restored'
    assert client.post('/api/negotiation/restore',json=body,headers=headers('restore-old')).json()==response.json()
    assert client.post('/api/negotiation/restore',json=body,headers=headers('restore-new-key')).status_code==409
    state=client.get('/api/state').json()
    assert state['pending_card']['card_id']==response.json()['restored_card_id']
    assert state['pending_card']['proposal_id']==original['proposal_id']
    assert state['renegotiation']['restoration_allowed'] is False
    with service.store.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM negotiations WHERE run_id=? AND shop_id='D'",(run,)).fetchone()[0]==2
        assert c.execute("SELECT COUNT(*) FROM cards WHERE run_id=? AND shop_id='D' AND status='pending'",(run,)).fetchone()[0]==1
        assert not one(c,"SELECT call_id FROM llm_call_reservations WHERE run_id=?",(run,))
