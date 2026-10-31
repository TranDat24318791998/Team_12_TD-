import json
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.runner import run_agent
from app.domain.models.negotiation import RefereeDecision
from app.negotiation.prompts import REFEREE_SYSTEM


def review_turn(brief_public, turns, *, llm, tools, emit, negotiation_id=None, replay_context=None):
    clarification_needed = False
    ambiguous_action = None

    def validate_output(result):
        nonlocal clarification_needed, ambiguous_action
        if not turns or turns[-1].action!='accept':return None
        terms=any(term.strip() for term in result.unresolved_terms)
        if ((result.action=='stop' and not terms) or result.action=='refocus'
                or (result.action=='continue' and (terms or result.focused_question))):
            clarification_needed = True
            ambiguous_action = result.action
            return ('Sau lượt accept, stop cần nêu điều khoản vướng mắc trong unresolved_terms. '
                    'Nếu hai bên đã thống nhất và chỉ kết thúc thương lượng thành công, chọn continue; '
                    'xóa unresolved_terms và focused_question khi đã giải quyết. '
                    'Dự báo code cho đúng gói đã chấp nhận nằm trong get_referee_context.forecast, '
                    'gắn forecast_turn_id; không cần yêu cầu lại một gói chỉ để lấy dự báo. '
                    'Code sẽ kiểm gói và chờ người bán duyệt. Nếu thực sự không phù hợp, giữ stop và nêu vướng mắc; '
                    'nếu chưa rõ, chọn ask_human. Không cam kết đạt mục tiêu số đơn.')
        return None

    def fallback(dispatch):
        ctx = dispatch('get_referee_context', {})
        refs = [ctx.turns[-1].turn_id] if ctx.turns else []
        if clarification_needed:
            return RefereeDecision(action='ask_human',
                reason_vi=('Trọng tài yêu cầu dừng sau khi hai agent đồng thuận nhưng chưa nêu điều khoản vướng mắc; cần người bán xem xét.'
                           if ambiguous_action=='stop' else 'Trọng tài còn yêu cầu làm rõ sau khi hai agent đồng thuận; cần người bán xem xét.'),
                evidence_refs=refs, unresolved_terms=[], next_actor='seller', focused_question=None)
        if ctx.public_check_codes:
            return RefereeDecision(action='refocus', reason_vi='Đề xuất cần phù hợp mục tiêu đã xác nhận.',
                evidence_refs=refs, unresolved_terms=ctx.public_check_codes, next_actor=None, focused_question='Điều chỉnh gói theo mục tiêu?')
        counters = [t for t in ctx.turns if t.actor == 'shop' and t.action == 'counter']
        if ctx.turns and ctx.turns[-1].action != 'accept' and len(counters) >= 2 and counters[-1].package == counters[-2].package:
            return RefereeDecision(action='stop', reason_vi='Phản đề xuất lặp mà không tiến triển.',
                evidence_refs=refs, unresolved_terms=[], next_actor=None, focused_question=None)
        return RefereeDecision(action='continue', reason_vi='Cuộc thương lượng còn tiến triển.',
            evidence_refs=refs, unresolved_terms=[], next_actor=None, focused_question=None)
    payload = {'brief_id': brief_public.brief_id, 'turn_ids': [t.turn_id for t in turns]}
    return run_agent('referee', llm=llm, tools=tools,
        messages=[SystemMessage(content=REFEREE_SYSTEM), HumanMessage(content=json.dumps(payload,ensure_ascii=False))],
        output_schema=RefereeDecision, fallback=fallback, emit=emit,
        run_name=f'{negotiation_id or brief_public.brief_id}:referee:{len(turns)}',replay_context=replay_context,
        validate_output=validate_output).value
