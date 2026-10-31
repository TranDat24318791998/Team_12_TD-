"""LangGraph negotiation. Approval and activation remain outside this graph."""

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from app.agents.runner import AgentToolError
from app.agents.tools import bind_role_tools
from app.domain.models.negotiation import NegotiationResult, PublicTurn
from app.domain.policies import MAX_ROUNDS
from app.domain.finance import loss_warning
from app.domain.privacy import leak_guard
from app.domain.validators import brief_side_check, final_check, platform_side_check
from app.negotiation.agents import decide_platform, decide_shop, emit_for, replay_context_for
from app.negotiation.referee import review_turn


class NegotiationState(TypedDict, total=False):
    rounds: int
    turns: list[PublicTurn]
    result: NegotiationResult | None
    route: str
    candidate: object
    last_action: str
    focused_question: str | None


def run_negotiation(session, shop_id, day, kind, owner_note=None, *, negotiation_id=None, platform_context=None):
    if not session.brief or not session.brief.confirmed:
        raise ValueError('confirmed brief required')
    session.negotiation_attempt += 1
    negotiation_id = negotiation_id or f'{session.run_id}:{shop_id}:{day}:{session.negotiation_attempt}'
    shop = session.states[shop_id]
    def fail(state, reason):
        return NegotiationResult(negotiation_id=negotiation_id, shop_id=shop_id, day=day, kind=kind,
            status='failed', rounds=state.get('rounds',0), final_package=None, forecast=None, warning_vi=reason)
    def log(type, actor, text, data):
        session.log.add(session.run_id, day, type, actor, shop_id, text, {'negotiation_id':negotiation_id, **data})
    def platform(state):
        rounds = state.get('rounds', 0) + 1
        turns = state.get('turns', [])
        try:
            turn = decide_platform(session, shop_id, turns, None, negotiation_id=negotiation_id, initial_propose=not turns, focus=state.get('focused_question'), platform_context=platform_context)
            if turn.package and (platform_side_check(turn.package, shop.public) or brief_side_check(turn.package, session.brief)):
                return {'rounds':rounds, 'result':fail({'rounds':rounds}, 'Gói không hợp lệ phía sàn.'), 'route':'end'}
            last_counter = turns[-1].package if turns and turns[-1].actor == 'shop' and turns[-1].action == 'counter' else None
            if turn.action == 'accept' and (last_counter is None or turn.package != last_counter):
                return {'rounds':rounds, 'result':fail({'rounds':rounds}, 'Gói chấp nhận không khớp phản đề xuất.'), 'route':'end'}
            public = PublicTurn(turn_id=f'{negotiation_id}:platform:{rounds}', actor='platform', round=rounds,
                                action=turn.action, package=turn.package, message_vi=turn.message_vi)
            log('platform_turn', 'platform_agent', public.message_vi,
                {'turn_id':public.turn_id,'round':rounds,'action':turn.action,
                 'package':turn.package.model_dump(mode='json') if turn.package else None,'source':session.last_agent_source})
            return {'rounds':rounds, 'turns':turns+[public], 'candidate':turn.package, 'last_action':turn.action, 'focused_question':None, 'route':'review_platform'}
        except AgentToolError:
            return {'rounds':rounds, 'result':fail({'rounds':rounds}, 'Không thể đọc dữ liệu hoặc dự báo.'), 'route':'end'}
    def review(state):
        turns=state['turns']
        try:
            tools=bind_role_tools(session,'referee',shop_id,turns=turns)
            result=review_turn(session.brief,turns,llm=session.llm,tools=tools,emit=emit_for(session,shop_id,'referee',negotiation_id),negotiation_id=negotiation_id,
                               replay_context=replay_context_for(session,'referee',shop_id,negotiation_id=negotiation_id,turns=turns))
        except AgentToolError:
            return {'result':fail(state,'Không thể đánh giá cuộc thương lượng.'), 'route':'end'}
        safe_reason,_=leak_guard(result.reason_vi,shop.public,shop.private,session.world.fees)
        safe_focus,_=leak_guard(result.focused_question or '',shop.public,shop.private,session.world.fees)
        safe_terms=[]
        for term in result.unresolved_terms:
            safe_term,redacted=leak_guard(term,shop.public,shop.private,session.world.fees)
            if not redacted:safe_terms.append(safe_term)
        result=result.model_copy(update={'reason_vi':safe_reason,'focused_question':safe_focus or None,'unresolved_terms':safe_terms})
        log('referee_review','referee',result.reason_vi,{'action':result.action,'evidence_refs':result.evidence_refs,
            'source':session.last_agent_source,'round':turns[-1].round,'unresolved_terms':result.unresolved_terms,
            'next_actor':{'platform':'platform_agent','shop':'shop_agent','seller':'seller'}.get(result.next_actor),
            'focused_question':result.focused_question})
        last=turns[-1]
        if last.action in ('withdraw','reject'):
            return {'result':fail(state,'Một bên từ chối gói.'), 'route':'end'}
        if result.action in ('stop','ask_human'):
            return {'result':fail(state,result.reason_vi), 'route':'end'}
        if result.action == 'refocus':
            last=turns[-1]
            if last.action == 'accept':
                return {'result':fail(state,'Chưa thể chấp nhận khi trọng tài yêu cầu làm rõ.'), 'route':'end'}
            target=result.next_actor or ('shop' if last.actor=='platform' else 'platform')
            if target == 'seller' or target == last.actor or (target == 'platform' and state['rounds'] >= MAX_ROUNDS):
                return {'result':fail(state,result.reason_vi), 'route':'end'}
            return {'route':target, 'focused_question':result.focused_question}
        last=turns[-1]
        if last.action in ('withdraw','reject'):
            return {'result':fail(state,'Một bên từ chối gói.'), 'route':'end'}
        if last.action == 'accept':
            package=last.package
            errors=final_check(package,shop.public,shop.private,session.world.fees) + brief_side_check(package,session.brief)
            log('code_check','code','Kiểm tra gói cuối.',{'ok':not errors,'codes':[e.code for e in errors]})
            if errors:
                return {'result':fail(state,'Gói cuối không đạt kiểm tra.'), 'route':'end'}
            try:
                forecast=session.market.forecast_package(shop.public,package,day,session.settings.seed,
                                                          session.memory.get_calibration(shop.public.category))
            except Exception:
                return {'result':fail(state,'Chưa có adapter dự báo.'), 'route':'end'}
            warning=loss_warning(shop.public,shop.private,session.world.fees) if not package.ads_daily_budget and not package.voucher_pct else None
            return {'result':NegotiationResult(negotiation_id=negotiation_id,shop_id=shop_id,day=day,kind=kind,
                status='warning_only' if warning else 'agreed',rounds=state['rounds'],final_package=package,forecast=forecast,warning_vi=warning),'route':'end'}
        if last.actor=='shop' and state['rounds']>=MAX_ROUNDS:
            return {'result':fail(state,'Đã hết lượt thương lượng.'),'route':'end'}
        return {'route':'shop' if last.actor=='platform' else 'platform'}
    def shop_turn(state):
        turns=state['turns']; proposal=state['candidate']
        try:
            decision=decide_shop(session,shop_id,proposal,None,owner_note,negotiation_id=negotiation_id,turns=turns,focus=state.get('focused_question'))
        except AgentToolError:
            return {'result':fail(state,'Không thể kiểm tra quy tắc shop.'),'route':'end'}
        if decision.action == 'accept' and decision.package != proposal:
            return {'result':fail(state,'Shop chấp nhận sai gói.'),'route':'end'}
        if decision.package and final_check(decision.package,shop.public,shop.private,session.world.fees):
            return {'result':fail(state,'Gói shop chưa hợp lệ.'),'route':'end'}
        safe_message,redacted=leak_guard(decision.message_vi,shop.public,shop.private,session.world.fees)
        public=PublicTurn(turn_id=f'{negotiation_id}:shop:{state["rounds"]}', actor='shop',round=state['rounds'],
                          action=decision.action,package=decision.package,message_vi=safe_message)
        log('shop_turn','shop_agent',public.message_vi,{'turn_id':public.turn_id,'round':state['rounds'],
            'action':public.action,'package':public.package.model_dump(mode='json') if public.package else None,
            'source':session.last_agent_source,'redacted':redacted})
        if decision.package is not None:
            log('code_check','code','Đã kiểm gói shop.',{'ok':True,'codes':[]})
        return {'turns':turns+[public], 'candidate':decision.package, 'last_action':decision.action, 'focused_question':None, 'route':'review_shop'}
    graph=StateGraph(NegotiationState)
    graph.add_node('platform',platform); graph.add_node('shop',shop_turn); graph.add_node('review',review)
    graph.add_edge(START,'platform')
    graph.add_conditional_edges('platform',lambda s:'review' if s['route']=='review_platform' else 'end',{'review':'review','end':END})
    graph.add_conditional_edges('shop',lambda s:'review' if s['route']=='review_shop' else 'end',{'review':'review','end':END})
    graph.add_conditional_edges('review',lambda s:s['route'],{'platform':'platform','shop':'shop','end':END})
    final=graph.compile().invoke({'rounds':0,'turns':[],'result':None,'route':'platform'}, {'recursion_limit':64})
    result=final['result']
    log('negotiation_finished','system','Thương lượng đã kết thúc.',
        {'kind':result.kind,'status':result.status,'rounds':result.rounds,
         'package':result.final_package.model_dump(mode='json') if result.final_package else None})
    return result
