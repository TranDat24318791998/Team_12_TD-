"""Agent sàn/shop và fallback dùng cùng tool đã ràng buộc quyền."""

import json
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.runner import run_agent
from app.agents.tools import bind_role_tools
from app.domain.models.negotiation import PlatformTurn, ShopTurn
from app.domain.formatting import dec, vnd
from app.domain.models.packages import Package
from app.domain.policies import DEFAULT_PACKAGE
from app.domain.privacy import leak_guard
from app.negotiation.prompts import PLATFORM_SYSTEM, SHOP_SYSTEM


def emit_for(session, shop_id, role, negotiation_id):
    def emit(type, data):
        safe = {k: v for k, v in data.items() if k in {'role', 'tool_name', 'tool_call_id', 'requested_by', 'status', 'source', 'error_code', 'invocation_id', 'record_refs'}}
        safe['negotiation_id'] = negotiation_id
        if type == 'agent_completed': session.last_agent_source = safe.get('source', 'offline')
        session.log.add(session.run_id, session.day, type, role, shop_id,
                        'Agent xử lý dữ liệu theo quyền.', safe)
    return emit


def decide_platform(session, shop_id, turns, memory_view, *, negotiation_id='negotiation', initial_propose=False, focus=None):
    invocation_id = f'{negotiation_id}:platform:{len(turns)}'
    tools = bind_role_tools(session, 'platform', shop_id, turns=turns, initial_propose=initial_propose, invocation_id=invocation_id)
    latest_shop = turns[-1] if turns and turns[-1].actor == 'shop' and turns[-1].action == 'counter' else None
    def fallback(dispatch):
        dispatch('get_public_context', {})
        memory = dispatch('read_memory', {})
        if initial_propose:
            dispatch('search_campaign_catalog', {'query': ''})
        if latest_shop and latest_shop.package:
            original = latest_shop.package
            action = 'accept'
        else:
            history = next((record for record in memory.history if record.approved_package), None)
            original = history.approved_package if history else Package.model_validate(DEFAULT_PACKAGE)
            action = 'propose'
        check = dispatch('validate_platform_package', {'package': original.model_dump(mode='json')})
        if not check.corrected_package or check.violations_after:
            return PlatformTurn(action='withdraw', package=None, message_vi='Chưa có gói phù hợp với mục tiêu công khai.')
        package = check.corrected_package
        if package != original: action = 'propose'
        dispatch('forecast_package', {'package': package.model_dump(mode='json')})
        return PlatformTurn(action=action, package=package, message_vi=('Sàn đồng ý với phản đề xuất.' if action == 'accept' else 'Sàn đề xuất gói tăng trưởng phù hợp mục tiêu.'))
    initial = {'brief': session.brief.model_dump(mode='json'), 'turns': [t.model_dump(mode='json') for t in turns], 'shop_id':shop_id, 'refocus_vi':focus}
    run = run_agent('platform', llm=session.llm, tools=tools,
        messages=[SystemMessage(content=PLATFORM_SYSTEM), HumanMessage(content=json.dumps(initial,ensure_ascii=False))],
        output_schema=PlatformTurn, fallback=fallback, emit=emit_for(session, shop_id, 'platform', negotiation_id),
        run_name=invocation_id)
    session.last_agent_source = run.source
    state = session.states[shop_id]
    message, _ = leak_guard(run.value.message_vi, state.public, state.private, session.world.fees)
    return run.value.model_copy(update={'message_vi': message})


def decide_shop(session, shop_id, proposal, memory_view, owner_note, *, negotiation_id='negotiation', turns=(), focus=None):
    invocation_id = f'{negotiation_id}:shop:{len(turns)}'
    tools = bind_role_tools(session, 'shop', shop_id, proposal=proposal, turns=turns, invocation_id=invocation_id)
    state = session.states[shop_id]
    def fallback(dispatch):
        dispatch('get_shop_private_context', {})
        dispatch('read_memory', {})
        check = dispatch('evaluate_shop_package', {'package': proposal.model_dump(mode='json')})
        safe = check.corrected_package
        if safe is None or check.violations_after:
            return ShopTurn(action='reject', package=None, message_vi='Shop chưa thể nhận gói này.', private_note_vi='')
        if owner_note and '2%' in owner_note and safe.voucher_pct > 2:
            values = safe.model_dump(); values['voucher_pct'] = 2
            revised = Package.model_validate(values)
            check = dispatch('evaluate_shop_package', {'package': revised.model_dump(mode='json')})
            safe = check.corrected_package
            if safe is None or check.violations_after:
                return ShopTurn(action='reject', package=None, message_vi='Shop chưa thể nhận gói này.', private_note_vi='')
        action = 'accept' if safe == proposal else 'counter'
        return ShopTurn(action=action, package=safe, message_vi=(
            'Shop đồng ý với gói.' if action == 'accept' else
            f'Shop đề xuất ngân sách {vnd(safe.ads_daily_budget)}/ngày, voucher {safe.voucher_pct}%'
            + (f' và ngưỡng dừng {dec(safe.stop_roas_below)}.' if safe.stop_roas_below is not None else '.')),
            private_note_vi='Đã kiểm tra giới hạn shop.')
    initial = {'proposal': proposal.model_dump(mode='json'), 'owner_note': owner_note or '', 'shop_id':shop_id, 'refocus_vi':focus}
    run = run_agent('shop', llm=session.llm, tools=tools,
        messages=[SystemMessage(content=SHOP_SYSTEM), HumanMessage(content=json.dumps(initial,ensure_ascii=False))],
        output_schema=ShopTurn, fallback=fallback, emit=emit_for(session, shop_id, 'shop', negotiation_id),
        run_name=invocation_id)
    message, _ = leak_guard(run.value.message_vi, state.public, state.private, session.world.fees)
    session.last_agent_source = run.source
    return run.value.model_copy(update={'message_vi': message})
