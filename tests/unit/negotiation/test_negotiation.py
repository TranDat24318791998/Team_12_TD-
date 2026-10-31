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


def test_private_exact_financial_value_never_reaches_public_transcript(monkeypatch):
    import app.negotiation.graph as graph
    from app.domain.finance import breakeven_roas
    from app.domain.models.negotiation import ShopTurn
    from app.domain.validators import clamp_to_rules
    session=make_session(); state=session.states['D']
    secret=str(breakeven_roas(state.public,state.private,3,session.world.fees))
    observed=[]; original=graph.decide_platform
    def platform(*args,**kwargs):
        turns=args[2]
        observed.extend(turn.message_vi for turn in turns)
        return original(*args,**kwargs)
    def shop(sess,shop_id,proposal,*args,**kwargs):
        safe=clamp_to_rules(proposal,state.public,state.private,session.world.fees)
        return ShopTurn(action='counter',package=safe,message_vi=f'Tỷ suất cần là {secret}.',private_note_vi='')
    monkeypatch.setattr(graph,'decide_platform',platform)
    monkeypatch.setattr(graph,'decide_shop',shop)
    result=graph.run_negotiation(session,'D',1,'propose')
    assert result.status=='agreed' and observed
    assert all(secret not in text for text in observed)
    assert secret not in ''.join(event.model_dump_json() for event in session.log.since(session.run_id,0))


def test_brief_constraints_checked_at_tool_graph_and_activation(monkeypatch):
    import pytest
    import app.negotiation.graph as graph
    from app.agents.tools import bind_role_tools,PackageArgs
    from app.domain.models.cards import Card
    from app.domain.models.negotiation import PlatformTurn
    from app.domain.models.packages import Package
    from app.runtime.day import activate_approved_package,WorkflowError
    session=make_session()
    bad=Package(content_refresh=False,ads_daily_budget=45000,voucher_pct=3,stop_roas_below=6.5,stop_after_days=2,duration_days=14)
    tools=bind_role_tools(session,'platform','D')
    checked=tools['validate_platform_package'].execute(PackageArgs(package=bad))
    assert {'BRIEF_CONTENT_MISMATCH','BRIEF_DURATION_MISMATCH'} <= {v.code for v in checked.violations_before}
    assert not checked.ok and checked.corrected_package.content_refresh and checked.corrected_package.duration_days==3
    monkeypatch.setattr(graph,'decide_platform',lambda *args,**kwargs:PlatformTurn(action='propose',package=bad,message_vi='Đề xuất'))
    result=graph.run_negotiation(session,'D',1,'propose')
    assert result.status=='failed' and session.states['D'].active is None
    card=Card(card_id='card',shop_id='D',day=1,kind='offer',package=bad,brief_version=1)
    session.approved_card_id='card'
    with pytest.raises(WorkflowError) as error: activate_approved_package(session,card)
    assert error.value.code=='PACKAGE_INVALID' and session.states['D'].active is None


def test_withdraw_then_refocus_fails_without_calling_shop(monkeypatch):
    import app.negotiation.graph as graph
    from app.domain.models.negotiation import PlatformTurn,RefereeDecision
    from app.runtime.day import start_day
    session=make_session(); session.step='brief_confirmed'
    monkeypatch.setattr(graph,'decide_platform',lambda *args,**kwargs:PlatformTurn(action='withdraw',package=None,message_vi='Dừng'))
    monkeypatch.setattr(graph,'review_turn',lambda brief,turns,**kwargs:RefereeDecision(action='refocus',reason_vi='Làm rõ',
        evidence_refs=[turns[-1].turn_id],unresolved_terms=[],next_actor='shop',focused_question='Có thể tiếp tục?'))
    monkeypatch.setattr(graph,'decide_shop',lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('shop must not run')))
    start_day(session)
    assert session.step=='brief_confirmed' and not session.phase_busy and session.pending_card is None


def test_shop_native_two_percent_counter_stays_on_native_path():
    import json
    from langchain_core.messages import ToolMessage
    from app.domain.models.packages import Package
    from app.domain.policies import DEFAULT_PACKAGE
    from app.negotiation.agents import decide_shop
    from tests.fakes.llm import FakeLLM,call
    session=make_session()
    original=Package(**DEFAULT_PACKAGE)
    candidate=Package(content_refresh=True,ads_daily_budget=45000,voucher_pct=2,stop_roas_below=6.5,stop_after_days=2,duration_days=3)
    def finish(messages):
        checks=[json.loads(m.content) for m in messages if isinstance(m,ToolMessage) and m.name=='evaluate_shop_package']
        assert checks[0]['corrected_package']['voucher_pct']==3
        assert checks[1]['corrected_package']['voucher_pct']==2
        return [call('finish_shop',{'action':'counter','package':checks[1]['corrected_package'],
            'message_vi':'Shop đề xuất voucher 2%.','private_note_vi':''},'done')]
    session.llm=FakeLLM([[call('get_shop_private_context',{},'private'),call('read_memory',{},'memory')],
        [call('evaluate_shop_package',{'package':original.model_dump(mode='json')},'original'),
         call('evaluate_shop_package',{'package':candidate.model_dump(mode='json')},'revised')],finish])
    result=decide_shop(session,'D',original,None,'Giảm voucher còn 2%',negotiation_id='n2')
    assert result.package.voucher_pct==2 and session.last_agent_source=='fixture'
    completed=[e for e in session.log.since(session.run_id,0) if e.type=='agent_completed']
    assert completed[-1].data['source']=='fixture' and completed[-1].data['error_code'] is None


def test_native_platform_bad_brief_falls_back_to_confirmed_brief():
    from app.negotiation.agents import decide_platform
    from tests.fakes.llm import FakeLLM,call
    session=make_session()
    bad={'content_refresh':False,'ads_daily_budget':45000,'voucher_pct':3,'stop_roas_below':6.5,'stop_after_days':2,'duration_days':14}
    session.llm=FakeLLM([[call('get_public_context',{},'context'),call('read_memory',{},'memory'),
        call('search_campaign_catalog',{'query':''},'catalog')],
        [call('validate_platform_package',{'package':bad},'check'),call('forecast_package',{'package':bad},'forecast')],
        [call('finish_platform',{'action':'propose','package':bad,'message_vi':'Đề xuất'},'finish')]])
    result=decide_platform(session,'D',[],None,initial_propose=True)
    assert result.package.content_refresh and result.package.duration_days==3
    assert session.last_agent_source=='offline'
