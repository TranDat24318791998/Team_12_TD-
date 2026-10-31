from app.core.settings import Settings
from app.domain.models.intent import IntentBrief
from app.infrastructure.eventlog import EventLog
from app.negotiation.graph import run_negotiation
from app.runtime.session import Session
from tests.fakes.market import FakeMarket


def make_session():
    session=Session.new(Settings(_env_file=None,llm_mode='offline'),market=FakeMarket(),log=EventLog())
    session.brief=IntentBrief(brief_id='b1',version=1,shop_id='D',intent='increase_orders',goal_vi='Tăng đơn',
        allow_ads=True,ads_daily_cap=None,content_refresh=True,duration_days=3,confirmed=True)
    return session


def test_d_offline_negotiation_calls_tools_and_keeps_private_separate():
    session=make_session()
    result=run_negotiation(session,'D',1,'propose')
    assert result.status=='agreed' and result.rounds==2
    assert (result.final_package.ads_daily_budget,result.final_package.voucher_pct,result.final_package.stop_roas_below)==(45000,3,6.5)
    assert session.states['D'].active is None
    events=session.log.since(session.run_id,0)
    assert sum(e.type=='referee_review' for e in events)==3
    assert any(e.type=='tool_called' and e.data['tool_name']=='evaluate_shop_package' for e in events)
    public=' '.join(e.model_dump_json() for e in events)
    assert '115000' not in public and '18000' not in public and 'private_note' not in public
    assert all(e.data.get('requested_by')!='model' for e in events if e.type=='tool_called')


def test_shop_native_tool_result_is_private_and_drives_safe_counter():
    import json
    from langchain_core.messages import ToolMessage
    from app.domain.models.packages import Package
    from app.domain.policies import DEFAULT_PACKAGE
    from app.negotiation.agents import decide_shop
    from tests.fakes.llm import FakeLLM, call
    session=make_session()
    def finish(messages):
        result=json.loads(next(m.content for m in messages if isinstance(m,ToolMessage) and m.name=='evaluate_shop_package'))
        return [call('finish_shop',{'action':'counter','package':result['corrected_package'],
            'message_vi':'Giá vốn 115.000đ, cần phản đề xuất.', 'private_note_vi':'PRIVATE_SENTINEL'},'done')]
    session.llm=FakeLLM([[call('get_shop_private_context',{},'private'),call('read_memory',{},'memory')],
        [call('evaluate_shop_package',{'package':DEFAULT_PACKAGE},'evaluate')],finish])
    result=decide_shop(session,'D',Package(**DEFAULT_PACKAGE),None,'',negotiation_id='n1')
    assert result.action=='counter' and result.package.voucher_pct==3
    assert '115.000' not in result.message_vi
    messages=session.llm.requests[1][0]
    assert any('115000' in m.content for m in messages if isinstance(m,ToolMessage))
    exported=' '.join(e.model_dump_json() for e in session.log.since(session.run_id,0))
    assert '115000' not in exported and 'PRIVATE_SENTINEL' not in exported


def test_shop_b_loses_at_baseline_and_returns_content_warning():
    session=Session.new(Settings(_env_file=None,llm_mode='offline',demo_shop='B'),market=FakeMarket(),log=EventLog())
    session.brief=IntentBrief(brief_id='b2',version=1,shop_id='B',intent='increase_orders',goal_vi='Tăng đơn',
        allow_ads=True,ads_daily_cap=None,content_refresh=True,duration_days=3,confirmed=True)
    result=run_negotiation(session,'B',1,'propose')
    assert result.status=='warning_only' and result.warning_vi
    assert result.final_package.content_refresh and result.final_package.ads_daily_budget==0
    assert result.final_package.voucher_pct==0


def test_referee_refocus_reaches_next_actor_without_exceeding_rounds(monkeypatch):
    import app.negotiation.graph as graph
    from app.domain.models.negotiation import RefereeDecision
    session=make_session()
    seen=[]
    original=graph.decide_shop
    def spy(*args,**kwargs):
        seen.append(kwargs.get('focus'))
        return original(*args,**kwargs)
    def referee(brief,turns,**kwargs):
        first=len(turns)==1
        return RefereeDecision(action='refocus' if first else 'continue',reason_vi='Đúng mục tiêu.',
            evidence_refs=[turns[-1].turn_id],unresolved_terms=[],next_actor='shop' if first else None,
            focused_question='Cần xem lại ngân sách?' if first else None)
    monkeypatch.setattr(graph,'decide_shop',spy)
    monkeypatch.setattr(graph,'review_turn',referee)
    result=graph.run_negotiation(session,'D',1,'propose')
    assert result.status=='agreed' and result.rounds<=3
    assert seen[0]=='Cần xem lại ngân sách?'
