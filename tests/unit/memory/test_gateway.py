import pytest
from app.core.settings import Settings
from app.domain.models.intent import IntentBrief
from app.domain.models.learning import LessonOp, MemoryUpdateBatch, Preference
from app.infrastructure.eventlog import EventLog
from app.runtime.session import Session
from tests.fakes.market import FakeMarket


def setup_session(memory_enabled=True):
    session=Session.new(Settings(_env_file=None,llm_mode='offline'),memory_enabled=memory_enabled,market=FakeMarket(),log=EventLog())
    session.brief=IntentBrief(brief_id='b',version=1,shop_id='D',intent='increase_orders',goal_vi='Tăng đơn',
        allow_ads=True,ads_daily_cap=None,content_refresh=True,duration_days=3,confirmed=True)
    return session


def commit_ops(session,day,ops,negotiation_id):
    session.day=day
    session.log.add(session.run_id,day,'platform_turn','platform_agent','D','Đề xuất.',
                    {'negotiation_id':negotiation_id,'action':'propose'})
    snapshot=session.memory.freeze_learning_evidence(day)
    batch=MemoryUpdateBatch(day=day,through_seq=snapshot.through_seq,history=[],preferences=[],calibration=[],
                            lesson_ops=ops,valid_negotiation_ids=['forged-by-caller'])
    return session.memory.commit_memory_updates(batch,expected_revision=session.knowledge_revision,expected_cursor=session.memory_cursor)


def test_lesson_operations_reject_invalid_evidence_and_preserve_good_ops():
    session=setup_session()
    add=LessonOp(op='ADD',lesson_id=None,text_vi='Ưu tiên nội dung rõ ràng.',scope='strategy',evidence=['n1'])
    forged=LessonOp(op='ADD',lesson_id=None,text_vi='Tăng giá bán.',scope='strategy',evidence=['not-real'])
    result=commit_ops(session,1,[add,forged],'n1')
    assert result.rejected_ops==1 and len(result.accepted_lesson_ops)==1
    lesson=session.memory.list_lessons('strategy')[0]
    assert (lesson.score,lesson.version)==(2,1)
    for day,action,text,score in [(2,'UPVOTE','Ưu tiên nội dung rõ ràng.',3),
                                   (3,'EDIT','Ưu tiên hình rõ ràng.',4),
                                   (4,'DOWNVOTE','Ưu tiên hình rõ ràng.',3)]:
        op=LessonOp(op=action,lesson_id=lesson.lesson_id,text_vi=text,scope='strategy',evidence=[f'n{day}'])
        result=commit_ops(session,day,[op],f'n{day}')
        assert result.rejected_ops==0
        lesson=session.memory.list_lessons('strategy')[0]
        assert lesson.score==score and lesson.version==day
    for day in (5,6,7):
        op=LessonOp(op='DOWNVOTE',lesson_id=lesson.lesson_id,text_vi=lesson.text_vi,scope='strategy',evidence=[f'n{day}'])
        commit_ops(session,day,[op],f'n{day}')
    assert session.memory.list_lessons('strategy')==[]


def test_memory_disabled_retains_rules_and_private_view_stays_scoped():
    session=setup_session(memory_enabled=False)
    view=session.memory.shop_view('D')
    assert view.rules.ads_daily_max==45000 and view.preferences==[]
    public=session.memory.platform_view('D','quat_mini')
    assert public.history==public.lessons==[] and public.calibration is None
    assert 'ads_daily_max' not in public.model_dump_json()


def test_cross_shop_preference_evidence_cannot_be_committed():
    session=setup_session()
    event=session.log.add(session.run_id,1,'content_job','seller','A','Góp ý',{'feedback_vi':'nền sáng'})
    snapshot=session.memory.freeze_learning_evidence(1)
    pref=Preference(pref_id='f',shop_id='A',field='content_style',value='ảnh nền sáng',status='candidate',evidence_seqs=[event.seq])
    batch=MemoryUpdateBatch(day=1,through_seq=snapshot.through_seq,history=[],preferences=[pref],calibration=[],lesson_ops=[],valid_negotiation_ids=[])
    with pytest.raises(ValueError):
        session.memory.commit_memory_updates(batch,expected_revision=0,expected_cursor=0)
    assert session.knowledge_revision==0


def test_shop_a_voucher_preference_requires_seller_confirmation():
    from app.domain.models.cards import Card, RuleQuestion
    from app.domain.models.packages import Package
    from app.domain.policies import DEFAULT_PACKAGE
    from app.memory.night import run_night
    session=Session.new(Settings(_env_file=None,llm_mode='offline',demo_shop='A'),market=FakeMarket(),log=EventLog())
    session.brief=IntentBrief(brief_id='a',version=1,shop_id='A',intent='increase_orders',goal_vi='Tăng đơn',
        allow_ads=True,ads_daily_cap=None,content_refresh=True,duration_days=3,confirmed=True)
    values=Package(**DEFAULT_PACKAGE).model_dump(); values['voucher_pct']=5
    session.log.add(session.run_id,1,'seller_decision','seller','A','Người bán sửa gói.',
        {'negotiation_id':'fixture-a','edited_package':values,'action':'edit'})
    session.settled_days.add(1)
    run_night(session,1)
    pref=session.memory.prefs_to_ask('A',2)[0]
    assert pref.field=='voucher_max_pct' and pref.value=='5'
    assert session.states['A'].private.rules.voucher_max_pct==10
    session.day=2
    session.pending_card=Card(card_id='q-a',shop_id='A',day=2,kind='question',brief_version=1,
        rule_question=RuleQuestion(pref_id=pref.pref_id,field=pref.field,value=pref.value,text_vi='Giới hạn voucher?'))
    session.memory.mark_asked(pref.pref_id,2)
    session.memory.answer_pref(pref.pref_id,True,2)
    session.memory.answer_pref(pref.pref_id,True,2)
    assert session.states['A'].private.rules.voucher_max_pct==5 and session.rules_version==2


def test_reject_preference_preserves_rules_and_silences_fourteen_days():
    from app.domain.models.cards import Card, RuleQuestion
    session=setup_session()
    event=session.log.add(session.run_id,1,'content_job','seller','D','Feedback',{'feedback_vi':'nền sáng'})
    pref=Preference(pref_id='p1',shop_id='D',field='content_style',value='ảnh nền sáng',status='candidate',evidence_seqs=[event.seq])
    session.store.put((session.run_id,'preferences','D'),pref.pref_id,pref)
    session.pending_card=Card(card_id='q',shop_id='D',day=2,kind='question',brief_version=1,
        rule_question=RuleQuestion(pref_id='p1',field='content_style',value='ảnh nền sáng',text_vi='Ưu tiên nền sáng?'))
    session.memory.mark_asked('p1',2)
    session.memory.answer_pref('p1',False,2)
    assert session.states['D'].private.rules.content_style_notes==[] and session.rules_version==1
    assert not session.memory.prefs_to_ask('D',15)
    assert session.memory.prefs_to_ask('D',16)[0].status=='declined'
