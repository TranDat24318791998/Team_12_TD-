import json
from langchain_core.messages import HumanMessage, ToolMessage
from app.agents.runner import run_agent
from app.agents.tools import bind_role_tools
from app.domain.models.content import ContentText
from app.negotiation.agents import decide_platform
from app.domain.policies import DEFAULT_PACKAGE
from tests.fakes.llm import FakeLLM, call
from app.core.settings import Settings
from app.domain.models.cards import SellerDecision
from app.domain.models.tools import ContentContext
from app.infrastructure.eventlog import EventLog
from app.infrastructure.llm import LLMClient
from app.runtime.day import apply_reviewed_content, close_day, confirm_brief, start_day, submit_decision
from app.runtime.session import Session
from tests.fakes.content import FakeContent
from tests.fakes.market import FakeMarket


def test_two_day_workflow_learning_and_next_use(tmp_path):
    market=FakeMarket()
    session=Session.new(Settings(_env_file=None,llm_mode='offline'),market=market,log=EventLog())
    session.content=FakeContent(session,tmp_path)
    confirm_brief(session,{'intent':'increase_orders','goal_vi':'Tăng đơn','allow_ads':True,
        'ads_daily_cap':None,'content_refresh':True,'duration_days':3})
    start_day(session)
    card=session.pending_card
    assert session.step=='awaiting_decision' and card.package.voucher_pct==3
    decision=SellerDecision(card_id=card.card_id,expected_card_version=1,expected_brief_version=1,action='accept')
    assert submit_decision(session,decision)=='content_review'
    assert session.states['D'].active is None
    def content_title():
        def finish(messages):
            value=json.loads(next(m.content for m in messages if isinstance(m,ToolMessage)))
            style=value['memory']['confirmed_style_notes']
            return [call('finish_content',{'title':'Quạt nền sáng' if style else 'Quạt mini',
                'description':'Sạc USB','checks':[]},'finish')]
        model=FakeLLM([[call('get_content_context',{},'read')],finish])
        tools=bind_role_tools(session,'content','D',card_id=card.card_id)
        result=run_agent('content',llm=model,tools=tools,messages=[HumanMessage(content='Viết nội dung')],
            output_schema=ContentText,fallback=lambda _:ContentText(title='fallback',description='',checks=[]),
            emit=lambda *_:None,run_name='content-test')
        assert result.source=='fixture'
        return result.value.title
    assert content_title()=='Quạt mini'
    draft=session.content.retry('D','Ảnh nền tối quá, làm nền sáng')
    listing=apply_reviewed_content(session,card.card_id,1,draft.version,'B')
    assert session.states['D'].active.package==card.package
    assert apply_reviewed_content(session,card.card_id,1,draft.version,'B')==listing
    stock_before=session.states['D'].public.stock
    result=close_day(session,1)
    assert close_day(session,1)==result and market.calls==1
    assert session.states['D'].public.stock==stock_before-3
    assert result['summary'].calibration['points']==1
    assert result['summary'].calibration['factor']==1
    assert not session.states['D'].private.rules.content_style_notes
    history=session.memory.platform_view('D','quat_mini').history
    assert len(history)==1 and history[0].approved_package==card.package
    assert history[0].outcome.orders==3
    # Same prompt and model behavior; only the actual memory view changes.
    def platform_choice(memory_enabled):
        def choose(messages):
            view=json.loads(next(m.content for m in messages if isinstance(m,ToolMessage) and m.name=='read_memory'))
            pkg=view['history'][0]['approved_package'] if view['history'] else DEFAULT_PACKAGE
            return [call('validate_platform_package',{'package':pkg},'check'),call('forecast_package',{'package':pkg},'forecast')]
        def finish(messages):
            check=json.loads(next(m.content for m in messages if isinstance(m,ToolMessage) and m.name=='validate_platform_package'))
            return [call('finish_platform',{'action':'propose','package':check['corrected_package'],'message_vi':'Đề xuất.'},'finish')]
        session.memory.enabled=memory_enabled
        session.llm=FakeLLM([[call('get_public_context',{},'context'),call('read_memory',{},'memory'),
            call('search_campaign_catalog',{'query':''},'catalog')],choose,finish])
        return decide_platform(session,'D',[],None,initial_propose=True).package
    assert platform_choice(False).voucher_pct==10
    assert platform_choice(True).voucher_pct==3
    session.llm=LLMClient(session.settings)
    candidates=session.memory.prefs_to_ask('D',2)
    assert len(candidates)==1 and candidates[0].status=='candidate'
    start_day(session)
    question=session.pending_card
    assert question.kind=='question' and session.states['D'].active
    submit_decision(session,SellerDecision(card_id=question.card_id,expected_card_version=question.version,
        expected_brief_version=question.brief_version,action='accept',rule_answer=True))
    assert session.states['D'].private.rules.content_style_notes==['ảnh nền sáng']
    assert session.memory.shop_view('D').preferences[0].status=='confirmed'
    # A future content request is bound to an approved card; the fixture stands in for that later approval.
    session.pending_card=card; session.approved_card_id=card.card_id
    tools=bind_role_tools(session,'content','D',card_id=card.card_id,draft_version=1)
    context=tools['get_content_context'].execute(tools['get_content_context'].args_schema())
    assert isinstance(context,ContentContext) and context.memory.confirmed_style_notes==['ảnh nền sáng']
    assert content_title()=='Quạt nền sáng'
    assert 'unit_cost' not in context.model_dump_json()

    # Day 2 has an outcome but no new negotiation: history remains joined to the first card.
    session.pending_card=None; session.approved_card_id=None
    result2=close_day(session,2)
    history2=session.memory.platform_view('D','quat_mini').history
    assert len(history2)==1 and history2[0].negotiation_id==history[0].negotiation_id
    assert history2[0].version==2 and result2['summary'].calibration['points']==2


def test_content_role_uses_runner_and_rejects_unverified_claims(tmp_path):
    from app.agents.content import generate_content
    session=Session.new(Settings(_env_file=None,llm_mode='offline'),market=FakeMarket(),log=EventLog())
    session.content=FakeContent(session,tmp_path)
    confirm_brief(session,{'intent':'increase_orders','goal_vi':'Tăng đơn','allow_ads':True,
        'ads_daily_cap':None,'content_refresh':True,'duration_days':3})
    start_day(session); card=session.pending_card
    submit_decision(session,SellerDecision(card_id=card.card_id,expected_card_version=1,expected_brief_version=1,action='accept'))
    # Unverified warranty claim is not present in the tool's fact set, so output falls back.
    session.llm=FakeLLM([[call('get_content_context',{},'read')],
        [call('finish_content',{'title':'Quạt bảo hành','description':'Sạc USB','checks':[]},'finish')]])
    result=generate_content(session,'D',card_id=card.card_id,draft_version=1)
    assert result.source=='offline' and 'bảo hành' not in result.value.title.casefold()
    assert any('seed:shop:D' in check for check in result.value.checks)


def test_user_feedback_is_not_promoted_to_verified_product_fact(tmp_path):
    from app.agents.content import generate_content
    session=Session.new(Settings(_env_file=None,llm_mode='offline'),market=FakeMarket(),log=EventLog())
    session.content=FakeContent(session,tmp_path)
    confirm_brief(session,{'intent':'increase_orders','goal_vi':'Tăng đơn','allow_ads':True,
        'ads_daily_cap':None,'content_refresh':True,'duration_days':3})
    start_day(session); card=session.pending_card
    submit_decision(session,SellerDecision(card_id=card.card_id,expected_card_version=1,expected_brief_version=1,action='accept'))
    session.llm=FakeLLM([[call('get_content_context',{},'read')],
        [call('finish_content',{'title':'Quạt chống nước','description':'Sạc USB','checks':[]},'finish')]])
    result=generate_content(session,'D',card_id=card.card_id,draft_version=1,feedback_history=['Thêm chống nước'])
    assert result.source=='offline' and 'chống nước' not in result.value.title.casefold()
