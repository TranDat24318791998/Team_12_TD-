import json
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

import pytest
from app.domain.models import learning, skills, tools
from app.domain.models.learning import (LearningEvidence, MemoryUpdateBatch, NightPublication,
    NightReflectionOutput, NightSnapshot, NightSummary, Preference, ReflectionReceipt, StoreWrite)
from app.infrastructure.store import MemoryStore, StoreConflict
from app.infrastructure.sqlite_store import SqliteKnowledgeStore
from app.memory.skills import canonical_bytes
from data.growth_data.service import DataService


@pytest.fixture(params=['memory', 'sqlite'])
def repository(request, tmp_path):
    if request.param == 'memory':
        return MemoryStore(), 'r1'
    data = DataService(tmp_path)
    principal = data.bootstrap()
    with data.store.connect(write=True) as c:
        run = data.create_run(c, principal, {'simulation_days': 3})
    return SqliteKnowledgeStore(data.store), run['run_id']


def snapshot(run):
    evidence = LearningEvidence(day=1, from_seq=1, through_seq=1, events=[], existing_lessons=[],
                                valid_negotiation_ids=[], knowledge_revision=0)
    derived = MemoryUpdateBatch(day=1, through_seq=1, history=[], preferences=[], calibration=[],
                                lesson_ops=[], valid_negotiation_ids=[])
    values = dict(run_id=run, shop_id='D', category='quat_mini', day=1, expected_revision=0,
                  expected_cursor=0, through_seq=1, evidence=evidence, derived=derived,
                  calibration_summary={'factor':1.0,'points':0,'mape_today':None}, prior_versions=[],
                  base_texts={'platform_offer':'offer','platform_renew':'renew'})
    raw = {k:(v.model_dump(mode='json') if hasattr(v,'model_dump') else v) for k,v in values.items()
           if k not in ('expected_revision','expected_cursor')}
    return NightSnapshot(**values, snapshot_hash=sha256(canonical_bytes(raw)).hexdigest())


def publication(s):
    summary = NightSummary(day=1, history_updates=[], pref_candidates=[], calibration=s.calibration_summary,
                           lesson_ops=[], rejected_ops=0)
    return NightPublication(run_id=s.run_id,shop_id=s.shop_id,day=1,snapshot_hash=s.snapshot_hash,
                            through_seq=1,writes=[],versions=[],summary=summary,rejections=[],source='offline')


def test_wire_examples():
    entries = json.loads(Path('contracts/self_improve/examples.json').read_text())
    for entry in entries:
        model = getattr(skills, entry['model'], None) or getattr(learning, entry['model'], None) or getattr(tools, entry['model'], None)
        assert model is not None, entry['model']
        model.model_validate_json(json.dumps(entry['payload'], ensure_ascii=False))


def test_invalid_wire_examples_are_rejected():
    entries = json.loads(Path('contracts/self_improve/invalid_examples.json').read_text())
    for entry in entries:
        model = getattr(skills,entry['model'],None) or getattr(learning,entry['model'],None) or getattr(tools,entry['model'],None)
        assert model is not None
        with pytest.raises(ValueError):
            model.model_validate_json(json.dumps(entry['payload'],ensure_ascii=False))


def test_atomic_receipts_and_copy(repository):
    store, run = repository
    pref = Preference(pref_id='p1',shop_id='D',field='content_style',value='ảnh nền sáng',
                      status='candidate',evidence_seqs=[1,2])
    good = StoreWrite(namespace=(run,'preferences','D'),key='p1',value=pref)
    bad = StoreWrite(namespace=(run,'preferences','D'),key='wrong',value=pref)
    with pytest.raises(ValueError):
        store.commit_batch([good,bad],run_id=run,expected_revision=0,new_cursor=1,receipt_key='x')
    assert store.metadata(run) == (0,0) and store.get((run,'preferences','D'),'p1') is None
    store.commit_batch([good],run_id=run,expected_revision=0,new_cursor=1,receipt_key='x')
    assert store.commit_batch([good],run_id=run,expected_revision=0,new_cursor=1,receipt_key='x').duplicate
    with pytest.raises(StoreConflict, match='LEGACY_REQUEST_CONFLICT'):
        store.commit_batch([],run_id=run,expected_revision=0,new_cursor=1,receipt_key='x')
    clone = store.get((run,'preferences','D'),'p1')
    clone.evidence_seqs.append(9)
    assert store.get((run,'preferences','D'),'p1').evidence_seqs == [1,2]


def test_night_claim_commit_reopen(repository):
    store, run = repository
    s = snapshot(run)
    assert store.save_night_snapshot(s) == s
    claim = store.claim_reflection(run,1,s.snapshot_hash,'owner')
    assert store.claim_reflection(run,1,s.snapshot_hash,'other').owner_token == 'owner'
    store.finish_reflection(claim.model_copy(update={'status':'completed','output':NightReflectionOutput(), 'source':'offline'}))
    pub = publication(s)
    result = store.commit_night(pub, expected_revision=0, expected_cursor=0)
    assert result.knowledge.store.cursor == 1
    assert store.commit_night(pub, expected_revision=0, expected_cursor=0).knowledge.store.duplicate
    if isinstance(store, SqliteKnowledgeStore):
        store = SqliteKnowledgeStore(store.store)
    assert store.get_night_commit(run,1).summary == pub.summary
    assert store.metadata(run) == (1,1)


def test_budget_concurrent_and_no_regrant(repository):
    store, run = repository
    with ThreadPoolExecutor(max_workers=8) as pool:
        reservations = list(pool.map(lambda n: store.reserve_llm_call(run, str(n), 2), range(8)))
    assert sum(r.granted for r in reservations) == 2
    granted = next(str(i) for i,r in enumerate(reservations) if r.granted)
    assert store.reserve_llm_call(run,granted,2).reason == 'already_reserved'
    assert store.llm_calls_used(run) == 2
    with pytest.raises(StoreConflict,match='BUDGET_LIMIT_CONFLICT'):
        store.reserve_llm_call(run,'new',3)


def test_sqlite_external_transaction_rolls_back(tmp_path):
    data = DataService(tmp_path); principal = data.bootstrap()
    with data.store.connect(write=True) as c:
        run = data.create_run(c,principal,{'simulation_days':3})['run_id']
    store = SqliteKnowledgeStore(data.store); s = snapshot(run)
    store.save_night_snapshot(s)
    claim = store.claim_reflection(run,1,s.snapshot_hash,'owner')
    store.finish_reflection(claim.model_copy(update={'status':'completed','output':NightReflectionOutput(), 'source':'offline'}))
    with pytest.raises(RuntimeError):
        with data.store.connect(write=True) as c:
            store.commit_night_tx(c,publication(s),expected_revision=0,expected_cursor=0)
            raise RuntimeError('fault after publication')
    reopened = SqliteKnowledgeStore(data.store)
    assert reopened.get_night_commit(run,1) is None and reopened.metadata(run) == (0,0)
    assert reopened.get_reflection(run,1).status == 'completed'


def test_recover_reserved_and_terminal_conflict(repository):
    store, run = repository
    s = snapshot(run); store.save_night_snapshot(s)
    claim = store.claim_reflection(run,1,s.snapshot_hash,'one')
    assert store.recover_reserved_reflections(run)==1
    recovered = store.get_reflection(run,1)
    assert recovered.status=='unknown' and recovered.error_code=='PROCESS_RESTART'
    with pytest.raises(StoreConflict,match='REFLECTION_RESULT_CONFLICT'):
        store.finish_reflection(claim.model_copy(update={'status':'completed','output':NightReflectionOutput(), 'source':'offline'}))


def test_preference_confirmation_is_in_external_transaction(tmp_path):
    from data.growth_data.service import Principal
    data = DataService(tmp_path); principal = data.bootstrap()
    with data.store.connect(write=True) as c:
        run = data.create_run(c,principal,{'simulation_days':3,'execution_profile':'external',
            'driver_config':{'agent_version':'native'}})['run_id']
    store = SqliteKnowledgeStore(data.store); data.knowledge_callbacks=store
    pref = Preference(pref_id='pref',shop_id='D',field='content_style',value='ảnh nền sáng',
                      status='candidate',evidence_seqs=[1])
    store.put((run,'preferences','D'),'pref',pref)
    actor=Principal('worker','orchestrator',None,(run,),('D',))
    with data.store.connect(write=True) as c:
        rules,version=data.rules(c,run,'D')
        question=data.question(c,actor,run,'D',{'external_pref_id':'pref','field':'content_style',
            'value':'ảnh nền sáng','text_vi':'Dùng nền sáng?','based_on_rules_version':version})
        card=data.make_card(c,run,'D',1,question=question)
    assert store.get((run,'preferences','D'),'pref').status=='asked'
    original=store.record_preference_answer_tx
    def fault(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('fault after rules and preference')
    store.record_preference_answer_tx=fault
    body={'target_type':'rule_question','target_id':question['question_id'],'target_version':1,'action':'approve','rule_answer':True}
    with pytest.raises(RuntimeError):
        with data.store.connect(write=True) as c:
            data.decision(c,principal,run,body)
    assert store.get((run,'preferences','D'),'pref').status=='asked'
    with data.store.connect() as c:
        assert data.rules(c,run,'D')[1]==version
        assert not c.execute('SELECT 1 FROM decisions WHERE run_id=? AND target_id=?',(run,question['question_id'])).fetchone()
    store.record_preference_answer_tx=original
    with data.store.connect(write=True) as c:
        decision=data.decision(c,principal,run,body)
        duplicate=original(c,run_id=run,shop_id='D',pref_id='pref',question_id=question['question_id'],
                           decision_id=decision['decision_id'],yes=True,day=1)
        assert duplicate.duplicate
        with pytest.raises((StoreConflict,ValueError)):
            original(c,run_id=run,shop_id='D',pref_id='pref',question_id=question['question_id'],
                     decision_id=decision['decision_id'],yes=False,day=1)
    assert store.get((run,'preferences','D'),'pref').status=='confirmed'
    with data.store.connect() as c:
        assert data.rules(c,run,'D')[1]==version+1


def test_concurrent_reflection_claim_has_one_owner(repository):
    store, run=repository
    s=snapshot(run); store.save_night_snapshot(s)
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims=list(pool.map(lambda i:store.claim_reflection(run,1,s.snapshot_hash,f'owner-{i}'),range(8)))
    assert len({c.owner_token for c in claims})==1
    assert all(c.status=='reserved' for c in claims)
