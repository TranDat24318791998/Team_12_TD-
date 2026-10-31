import json
from langchain_core.messages import ToolMessage
from app.core.settings import Settings
from app.domain.models.intent import IntentBrief
from app.domain.policies import DEFAULT_PACKAGE
from app.infrastructure.eventlog import EventLog
from app.memory.night import run_night
from app.negotiation.agents import decide_platform
from app.runtime.session import Session
from tests.fakes.llm import FakeLLM,call
from tests.fakes.market import FakeMarket


def test_learning_receives_public_evidence_before_commit():
    session=Session.new(Settings(_env_file=None,llm_mode='offline'),market=FakeMarket(),log=EventLog())
    session.brief=IntentBrief(brief_id='b',version=1,shop_id='D',intent='increase_orders',goal_vi='Tăng đơn',
        allow_ads=True,ads_daily_cap=None,content_refresh=True,duration_days=3,confirmed=True)
    session.log.add(session.run_id,1,'platform_turn','platform_agent','D','Đề xuất.',{'negotiation_id':'n1','action':'propose'})
    session.settled_days.add(1)
    def finish(messages):
        evidence=json.loads(next(m.content for m in messages if isinstance(m,ToolMessage)))
        assert 'unit_cost' not in json.dumps(evidence) and evidence['valid_negotiation_ids']==['n1']
        return [call('finish_learning',{'ops':[{'op':'ADD','lesson_id':None,'text_vi':'Ưu tiên nội dung rõ ràng.',
            'scope':'strategy','evidence':[evidence['valid_negotiation_ids'][0]]}]},'done')]
    session.llm=FakeLLM([[call('read_learning_evidence',{},'read')],finish])
    summary=run_night(session,1)
    assert len(summary.lesson_ops)==1 and summary.rejected_ops==0
    assert session.memory.list_lessons('strategy')[0].evidence==['n1']
    assert any(e.type=='memory_write' and e.data['source']=='fixture' for e in session.log.since(session.run_id,0))

    # Keep the prompt and fake model behavior fixed; only learned memory changes.
    def platform_choice(memory_enabled):
        session.memory.enabled = memory_enabled
        def choose(messages):
            view = json.loads(next(m.content for m in messages if isinstance(m, ToolMessage) and m.name == 'read_memory'))
            learned = any(item['text_vi'] == 'Ưu tiên nội dung rõ ràng.' for item in view['lessons'])
            package = {**DEFAULT_PACKAGE, 'voucher_pct': 3 if learned else 10}
            return [call('validate_platform_package', {'package': package}, 'check'),
                    call('forecast_package', {'package': package}, 'forecast')]
        def finalize(messages):
            check = json.loads(next(m.content for m in messages if isinstance(m, ToolMessage) and m.name == 'validate_platform_package'))
            return [call('finish_platform', {'action': 'propose', 'package': check['corrected_package'],
                    'message_vi': 'Sàn đề xuất gói.'}, 'finish')]
        session.llm = FakeLLM([[call('get_public_context', {}, 'context'), call('read_memory', {}, 'memory'),
            call('search_campaign_catalog', {'query': ''}, 'catalog')], choose, finalize])
        result = decide_platform(session, 'D', [], None, initial_propose=True)
        assert session.last_agent_source == 'fixture'
        return result.package.voucher_pct
    assert platform_choice(False) == 10
    assert platform_choice(True) == 3
