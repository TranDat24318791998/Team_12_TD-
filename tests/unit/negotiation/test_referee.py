from app.agents.tools import BoundTool, EmptyArgs
from app.domain.models.negotiation import PublicTurn
from app.domain.models.packages import Package
from app.domain.models.tools import RefereeContext
from app.negotiation.referee import review_turn
from tests.fakes.llm import FakeLLM
from tests.unit.negotiation.test_negotiation import make_session


def test_offline_referee_recognizes_exact_accept_after_repeated_counters():
    session = make_session()
    package = Package(content_refresh=True, ads_daily_budget=45000, voucher_pct=3,
                      stop_roas_below=6.5, stop_after_days=2, duration_days=3)
    turns = [PublicTurn(turn_id=f'shop-{index}', actor='shop', round=index,
                        action='counter', package=package, message_vi='Đề xuất gói an toàn.') for index in (1, 2)]
    turns.append(PublicTurn(turn_id='platform-3', actor='platform', round=3,
                            action='accept', package=package, message_vi='Chấp nhận nguyên gói.'))
    context = RefereeContext(brief=session.brief, turns=turns, public_check_codes=[])
    tools = {'get_referee_context': BoundTool(EmptyArgs, lambda _: context, RefereeContext)}
    result = review_turn(session.brief, turns, llm=FakeLLM([ConnectionError('fixture')]),
                         tools=tools, emit=lambda *_: None)
    assert result.action == 'continue'


def test_offline_referee_still_stops_on_repeated_unaccepted_counter():
    session = make_session()
    package = Package(content_refresh=True, ads_daily_budget=45000, voucher_pct=3,
                      stop_roas_below=6.5, stop_after_days=2, duration_days=3)
    turns = [PublicTurn(turn_id=f'shop-{index}', actor='shop', round=index,
                        action='counter', package=package, message_vi='Giữ nguyên phản đề xuất.') for index in (1, 2)]
    context = RefereeContext(brief=session.brief, turns=turns, public_check_codes=[])
    tools = {'get_referee_context': BoundTool(EmptyArgs, lambda _: context, RefereeContext)}
    result = review_turn(session.brief, turns, llm=FakeLLM([ConnectionError('fixture')]),
                         tools=tools, emit=lambda *_: None)
    assert result.action == 'stop'
