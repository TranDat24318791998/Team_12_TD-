import json
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.runner import run_agent
from app.domain.models.negotiation import RefereeDecision
from app.negotiation.prompts import REFEREE_SYSTEM


def review_turn(brief_public, turns, *, llm, tools, emit):
    def fallback(dispatch):
        ctx = dispatch('get_referee_context', {})
        refs = [ctx.turns[-1].turn_id] if ctx.turns else []
        if ctx.public_check_codes:
            return RefereeDecision(action='refocus', reason_vi='Đề xuất cần phù hợp mục tiêu đã xác nhận.',
                evidence_refs=refs, unresolved_terms=ctx.public_check_codes, next_actor=None, focused_question='Điều chỉnh gói theo mục tiêu?')
        counters = [t for t in ctx.turns if t.actor == 'shop' and t.action == 'counter']
        if len(counters) >= 2 and counters[-1].package == counters[-2].package:
            return RefereeDecision(action='stop', reason_vi='Phản đề xuất lặp mà không tiến triển.',
                evidence_refs=refs, unresolved_terms=[], next_actor=None, focused_question=None)
        return RefereeDecision(action='continue', reason_vi='Cuộc thương lượng còn tiến triển.',
            evidence_refs=refs, unresolved_terms=[], next_actor=None, focused_question=None)
    payload = {'brief_id': brief_public.brief_id, 'turn_ids': [t.turn_id for t in turns]}
    return run_agent('referee', llm=llm, tools=tools,
        messages=[SystemMessage(content=REFEREE_SYSTEM), HumanMessage(content=json.dumps(payload,ensure_ascii=False))],
        output_schema=RefereeDecision, fallback=fallback, emit=emit,
        run_name=f'{brief_public.brief_id}:referee:{len(turns)}').value
