"""Day workflow and seller approval. Media and market are injected dependencies."""

from uuid import uuid4
from pathlib import Path
from copy import deepcopy
from app.core.paths import MEDIA_DIR
from app.domain.models.content import ContentDraft
from app.domain.finance import breakeven_roas, profit_per_unit, stop_threshold
from app.domain.models.cards import Card, RuleQuestion, SellerDecision
from app.domain.models.intent import IntentBrief
from app.domain.models.packages import ActivePackage
from app.domain.models.metrics import DayMetrics
from app.domain.policies import MIN_STOCK, REJECT_COOLDOWN_DAYS
from app.domain.validators import brief_side_check, final_check
from app.memory.night import run_night
from app.negotiation.graph import run_negotiation


class WorkflowError(ValueError):
    def __init__(self, code, message_vi, status=409):
        super().__init__(message_vi)
        self.code, self.message_vi, self.status = code, message_vi, status


def _event(session, type, actor, shop_id, text, data):
    return session.log.add(session.run_id,session.day,type,actor,shop_id,text,data)


def confirm_brief(session, request):
    with session.lock:
        if session.step != 'idle' or session.phase_busy:
            raise WorkflowError('INVALID_STATE','Chưa thể xác nhận mục tiêu lúc này.')
        if not isinstance(request,dict) or set(request) != {'intent','goal_vi','allow_ads','ads_daily_cap','content_refresh','duration_days'}:
            raise WorkflowError('DEMO_BRIEF_UNSUPPORTED','Mục tiêu không đúng định dạng demo.',422)
        if (request['intent'] != 'increase_orders' or request['allow_ads'] is not True or
            request['content_refresh'] is not True or request['duration_days'] != 3 or
            not isinstance(request['goal_vi'],str) or not request['goal_vi'].strip() or
            (request['ads_daily_cap'] is not None and (type(request['ads_daily_cap']) is not int or request['ads_daily_cap'] < 0))):
            raise WorkflowError('DEMO_BRIEF_UNSUPPORTED','Demo hiện hỗ trợ mục tiêu tăng đơn.',422)
        brief=IntentBrief(brief_id=uuid4().hex,version=1,shop_id=session.settings.demo_shop,confirmed=True,**request)
        session.brief=brief
        session.step='brief_confirmed'
        _event(session,'intent_confirmed','seller',brief.shop_id,'Đã xác nhận mục tiêu.',{'brief_id':brief.brief_id,'version':brief.version})
        return brief.model_copy(deep=True)


def monitor_active_packages(session):
    expired=[]
    for shop_id,state in session.states.items():
        active=state.active
        if not active:
            continue
        if session.day > active.end_day:
            state.active=None
            state.public.active_voucher_pct=0
            expired.append(shop_id)
            _event(session,'auto_action','system',shop_id,'Gói đã hết hạn.',{'action':'end_package','card_id':active.card_id})
            continue
        if active.ads_paused or not active.package.ads_daily_budget:
            continue
        threshold=active.package.stop_roas_below
        n=active.package.stop_after_days
        recent=[state.metrics.get(day) for day in range(session.day-n,session.day)]
        low=(threshold is not None and len(recent)==n and all(m is not None and m.ads_spend>0 and m.roas is not None and m.roas<threshold for m in recent))
        last=[state.metrics[day] for day in sorted(state.metrics,reverse=True)[:3]]
        average=sum(m.orders for m in last)/len(last) if last else 0
        low_stock=average>0 and state.public.stock<3*average
        if low or low_stock:
            active.ads_paused=True
            reason='ROAS dưới ngưỡng đã duyệt.' if low else 'Tồn kho không đủ cho ba ngày bán.'
            _event(session,'auto_action','system',shop_id,reason,{'action':'pause_ads','card_id':active.card_id})
    return expired


def match_opportunities(session):
    selected=[]; excluded=[]
    trend=session.world.trend
    for shop_id,state in session.states.items():
        reason=None
        if state.public.category!=trend['category'] or trend['growth_7d_pct']<=0: reason='Không có trend phù hợp.'
        elif state.active: reason='Shop đang có gói.'
        elif session.day<state.cooldown_until: reason='Shop đang trong thời gian chờ.'
        elif state.public.stock<MIN_STOCK: reason='Tồn kho dưới 30.'
        elif state.public.listing_quality>=.6 and state.public.search_rank_page<2: reason='Listing chưa cần làm mới.'
        if reason: excluded.append({'shop_id':shop_id,'reason_vi':reason})
        else: selected.append(shop_id)
    _event(session,'opportunity','platform_agent',None,'Đã chọn cơ hội.',
           {'keyword':trend['keyword'],'growth_7d_pct':trend['growth_7d_pct'],'chosen':selected,'excluded':excluded})
    return selected


def _card_from_result(session,result):
    state=session.states[result.shop_id]
    if result.status not in ('agreed','warning_only') or not result.final_package:
        raise WorkflowError('NEGOTIATION_FAILED',result.warning_vi or 'Thương lượng chưa thành công.')
    pkg=result.final_package
    profit=profit_per_unit(state.public,state.private,pkg.voucher_pct,session.world.fees)
    be=breakeven_roas(state.public,state.private,pkg.voucher_pct,session.world.fees)
    display=stop_threshold(be) if pkg.ads_daily_budget and be != float('inf') else None
    return Card(card_id=f'{session.run_id}:{result.shop_id}:{session.day}:{session.negotiation_attempt}',
        shop_id=result.shop_id,day=session.day,kind='offer',package=pkg,forecast=result.forecast,
        profit_after_fees_per_unit=profit,breakeven_roas_display=display,reasons_vi=['Gói đã được hai agent thống nhất.'],
        warnings_vi=[result.warning_vi] if result.warning_vi else [],brief_version=session.brief.version,
        negotiation_id=result.negotiation_id)


def start_day(session):
    with session.lock:
        if session.phase_busy or session.step not in ('brief_confirmed','idle') or not session.brief or not session.brief.confirmed:
            raise WorkflowError('INVALID_STATE','Chưa thể bắt đầu ngày.')
        session.phase_busy=True
    shop_id=session.settings.demo_shop
    try:
        _event(session,'day_start','system',shop_id,'Bắt đầu ngày.',{'day':session.day})
        expired=monitor_active_packages(session)
        selected=match_opportunities(session)
        state=session.states[shop_id]
        prefs=session.memory.prefs_to_ask(shop_id,session.day) if state.active else []
        if prefs:
            pref=prefs[0]
            question=RuleQuestion(pref_id=pref.pref_id,field=pref.field,value=pref.value,
                text_vi='Lần sau ưu tiên ảnh nền sáng?' if pref.field=='content_style' else f'Lần sau giới hạn voucher ở {pref.value}%?')
            card=Card(card_id=f'{session.run_id}:{shop_id}:{session.day}:question:{uuid4().hex[:8]}',
                      shop_id=shop_id,day=session.day,kind='question',brief_version=session.brief.version,rule_question=question)
            with session.lock:
                session.pending_card=card
                try:
                    session.memory.mark_asked(pref.pref_id,session.day)
                except Exception:
                    session.pending_card=None
                    raise
                session.step='awaiting_decision'
            _event(session,'card_sent','system',shop_id,'Cần người bán xác nhận sở thích.',{'card_id':card.card_id})
            return
        if state.active or shop_id not in selected:
            with session.lock: session.step='day_done'
            return
        with session.lock: session.step='negotiating'
        result=run_negotiation(session,shop_id,session.day,'renew' if shop_id in expired else 'propose')
        if result.status not in ('agreed','warning_only'):
            _event(session,'negotiation_failed','system',shop_id,result.warning_vi or 'Thương lượng chưa xong.',{'negotiation_id':result.negotiation_id})
            with session.lock: session.step='brief_confirmed'
            return
        card=_card_from_result(session,result)
        with session.lock:
            session.pending_card=card
            session.step='awaiting_decision'
        _event(session,'card_sent','system',shop_id,'Gửi thẻ đề xuất cho người bán.',
               {'card_id':card.card_id,'negotiation_id':result.negotiation_id,'version':card.version})
    except Exception:
        with session.lock:
            if session.step == 'negotiating': session.step='brief_confirmed'
        raise
    finally:
        with session.lock: session.phase_busy=False


def _validated_card(session, decision):
    if session.phase_busy or session.step != 'awaiting_decision' or not session.pending_card:
        raise WorkflowError('INVALID_STATE','Không có thẻ đang chờ quyết định.')
    card=session.pending_card
    if (decision.card_id != card.card_id or decision.expected_card_version != card.version or
        decision.expected_brief_version != card.brief_version or card.brief_version != session.brief.version):
        raise WorkflowError('STALE_CARD','Thẻ đã thay đổi; hãy xem lại.')
    return card


def submit_decision(session, decision):
    try:
        decision=SellerDecision.model_validate(decision)
    except ValueError as exc:
        raise WorkflowError('INVALID_DECISION','Quyết định không hợp lệ.',422) from exc
    with session.lock:
        card=_validated_card(session,decision)
        if decision.action == 'edit':
            raise WorkflowError('DEMO_DECISION_UNSUPPORTED','Demo chưa hỗ trợ sửa gói trực tiếp.',422)
        if card.kind == 'question':
            if decision.action not in ('accept','reject') or decision.rule_answer is not (decision.action == 'accept'):
                raise WorkflowError('INVALID_RULE_ANSWER','Chọn Có hoặc Không cho câu hỏi.',422)
            session.memory.answer_pref(card.rule_question.pref_id,decision.rule_answer,session.day)
            _event(session,'seller_decision','seller',card.shop_id,'Người bán trả lời câu hỏi.',
                {'card_id':card.card_id,'action':decision.action,'rule_answer':decision.rule_answer})
            session.pending_card=None; session.step='day_done'
            return session.step
        if decision.rule_answer is not None:
            raise WorkflowError('INVALID_RULE_ANSWER','Thẻ này không có câu hỏi luật.',422)
        if decision.action == 'negotiate':
            if decision.note_vi.strip() != 'Giảm voucher còn 2%':
                raise WorkflowError('DEMO_NOTE_UNSUPPORTED','Demo chỉ hỗ trợ yêu cầu giảm voucher còn 2%.',422)
            key=(card.shop_id,session.day)
            if session.seller_negotiations.get(key,0)>=1:
                raise WorkflowError('NEGOTIATION_LIMIT','Đã hết lượt thương lượng thêm.')
            session.seller_negotiations[key]=1
            session.phase_busy=True
            session.step='negotiating'
        elif decision.action == 'reject':
            _event(session,'seller_decision','seller',card.shop_id,'Người bán từ chối đề xuất.',
                {'card_id':card.card_id,'negotiation_id':card.negotiation_id,'action':'reject'})
            session.states[card.shop_id].cooldown_until=session.day+REJECT_COOLDOWN_DAYS
            session.pending_card=None; session.step='day_done'
            return session.step
        else:
            if card.package.content_refresh and session.content is None:
                raise WorkflowError('CONTENT_UNAVAILABLE','Chưa có adapter nội dung.',503)
            session.phase_busy=True
            session.approved_card_id=card.card_id
    try:
        if decision.action == 'negotiate':
            _event(session,'seller_decision','seller',card.shop_id,'Người bán đề nghị thương lượng thêm.',
                   {'card_id':card.card_id,'negotiation_id':card.negotiation_id,'action':'negotiate'})
            result=run_negotiation(session,card.shop_id,session.day,'propose',owner_note=decision.note_vi)
            if result.status not in ('agreed','warning_only'):
                with session.lock: session.pending_card=None; session.step='brief_confirmed'
                return session.step
            new_card=_card_from_result(session,result)
            with session.lock: session.pending_card=new_card; session.step='awaiting_decision'
            _event(session,'card_sent','system',card.shop_id,'Gửi thẻ điều chỉnh.',
                   {'card_id':new_card.card_id,'negotiation_id':result.negotiation_id,'version':new_card.version})
            return session.step
        if card.package.content_refresh:
            try:
                draft=ContentDraft.model_validate(session.content.start(card.shop_id))
                if (draft.shop_id != card.shop_id or draft.card_id != card.card_id or
                    draft.brief_version != card.brief_version or draft.version != 1):
                    raise WorkflowError('CONTENT_MISMATCH','Adapter trả sai bản nội dung.')
            except Exception:
                with session.lock: session.approved_card_id=None
                raise
            with session.lock: session.content_draft=draft; session.step='content_review'
        else:
            with session.lock:
                activate_approved_package(session,card)
                session.pending_card=None; session.approved_card_id=None; session.step='day_done'
        _event(session,'seller_decision','seller',card.shop_id,'Người bán đã duyệt đề xuất.',
               {'card_id':card.card_id,'negotiation_id':card.negotiation_id,'action':'accept'})
        return session.step
    finally:
        with session.lock: session.phase_busy=False


def _forecast_snapshots(session, card):
    if session.market is None:
        raise WorkflowError('MARKET_UNAVAILABLE','Chưa có adapter dự báo.',503)
    state=session.states[card.shop_id]
    return session.market.build_forecast_snapshots(state.public,card.package,session.day,session.settings.seed,
                                                    session.memory.get_calibration(state.public.category))


def activate_approved_package(session, card, *, snapshots=None):
    if session.approved_card_id != card.card_id or not card.package:
        raise WorkflowError('APPROVAL_REQUIRED','Cần người bán duyệt đúng thẻ.')
    state=session.states[card.shop_id]
    if final_check(card.package,state.public,state.private,session.world.fees) or brief_side_check(card.package,session.brief):
        raise WorkflowError('PACKAGE_INVALID','Gói không còn hợp lệ.')
    snapshots=_forecast_snapshots(session,card) if snapshots is None else snapshots
    active=ActivePackage(package=card.package,start_day=session.day,end_day=session.day+card.package.duration_days-1,
                         ads_paused=False,card_id=card.card_id)
    for snapshot in snapshots: session.forecast_snapshots[(card.shop_id,snapshot.target_day)]=snapshot
    state.active=active
    state.public.active_voucher_pct=card.package.voucher_pct
    session.active_negotiations[card.card_id]=card.negotiation_id
    _event(session,'package_applied','system',card.shop_id,'Đã kích hoạt gói được duyệt.',
        {'card_id':card.card_id,'negotiation_id':card.negotiation_id,'package':card.package.model_dump(mode='json')})
    return active


def _local_media_exists(session, path):
    if not path:
        return False
    if path.startswith('/media/'):
        candidate=(MEDIA_DIR / path.removeprefix('/media/')).resolve()
    else:
        candidate=Path(path).resolve()
    if getattr(session.content, 'source', None) != 'fixture':
        allowed=[(MEDIA_DIR / session.run_id).resolve(),(MEDIA_DIR / 'replay').resolve()]
        if not any(candidate.is_relative_to(base) for base in allowed):
            return False
    return candidate.is_file()


def apply_reviewed_content(session, card_id, brief_version, draft_version, cover_option, skip_video=False):
    if type(skip_video) is not bool or type(brief_version) is not int or type(draft_version) is not int or cover_option not in ('A','B','C'):
        raise WorkflowError('INVALID_APPLY', 'Lựa chọn nội dung không hợp lệ.', 422)
    with session.lock:
        key=(card_id,draft_version); receipt=session.apply_receipts.get(key)
        payload=(brief_version,cover_option,skip_video)
        if receipt:
            if receipt['payload'] != payload:
                raise WorkflowError('APPLY_CONFLICT','Bản này đã được áp dụng với lựa chọn khác.')
            return receipt['listing'].model_copy(deep=True)
        card=session.pending_card; draft=session.content_draft
        if (session.phase_busy or session.step != 'content_review' or not card or not draft or
            card.card_id != card_id or session.approved_card_id != card_id or card.brief_version != brief_version or
            draft.card_id != card_id or draft.brief_version != brief_version or draft.version != draft_version):
            raise WorkflowError('STALE_DRAFT','Bản nội dung đã thay đổi; hãy xem lại.')
        cover=next((image for image in draft.images if image.option==cover_option),None)
        if not cover or cover.status not in ('done','cached') or not _local_media_exists(session, cover.path):
            raise WorkflowError('COVER_NOT_READY','Ảnh đã chọn chưa sẵn sàng.')
        if (draft.video.status not in ('done','cached') or not _local_media_exists(session, draft.video.path)) and not skip_video:
            raise WorkflowError('VIDEO_NOT_READY','Video chưa sẵn sàng; chọn bỏ qua nếu muốn tiếp tục.')
        state=session.states[card.shop_id]
        if final_check(card.package,state.public,state.private,session.world.fees) or brief_side_check(card.package,session.brief):
            raise WorkflowError('PACKAGE_INVALID','Gói không còn hợp lệ.')
        snapshots=_forecast_snapshots(session,card)
        listing=session.content.apply(card.shop_id,cover_option,skip_video=skip_video)
        activate_approved_package(session,card,snapshots=snapshots)
        session.apply_receipts[key]={'payload':payload,'listing':listing.model_copy(deep=True)}
        session.content_draft=None; session.pending_card=None; session.approved_card_id=None; session.step='day_done'
        return listing.model_copy(deep=True)


def close_day(session, expected_day):
    if type(expected_day) is not int or expected_day < 1:
        raise WorkflowError('INVALID_DAY', 'Ngày không hợp lệ.', 422)
    with session.lock:
        if expected_day in session.night_receipts:
            return session.night_receipts[expected_day]
        if session.phase_busy or session.day != expected_day or session.step != 'day_done' or session.content_draft:
            raise WorkflowError('INVALID_STATE','Chưa thể kết thúc ngày.')
        if session.market is None:
            raise WorkflowError('MARKET_UNAVAILABLE','Chưa có adapter thị trường.',503)
        session.phase_busy=True
    try:
        if expected_day not in session.settled_days:
            previous_states=deepcopy(session.states)
            try:
                raw_metrics=session.market.simulate_day(session,expected_day)
                if not isinstance(raw_metrics, dict):
                    raise ValueError('market must return per-shop metrics')
                metrics={}
                for shop_id,value in raw_metrics.items():
                    result=DayMetrics.model_validate(value)
                    if shop_id not in session.states or result.shop_id != shop_id or result.day != expected_day:
                        raise ValueError('market returned metrics for another shop or day')
                    metrics[shop_id]=result
                for shop_id,result in metrics.items():
                    session.states[shop_id].metrics[expected_day]=result
            except Exception:
                session.states=previous_states
                raise
            # Preserve the successful settlement before an event sink can fail.
            session.settlement_metrics[expected_day]=deepcopy(metrics)
            session.settled_days.add(expected_day)
        metrics=session.settlement_metrics[expected_day]
        for shop_id,result in metrics.items():
            settlement_key=f'{expected_day}:{shop_id}'
            already_logged=any(e.type=='market_result' and e.data.get('settlement_key')==settlement_key
                               for e in session.log.since(session.run_id,0))
            if already_logged:
                continue
            active=session.states[shop_id].active
            card_id=active.card_id if active else None
            snapshot=session.forecast_snapshots.get((shop_id,expected_day))
            _event(session,'market_result','market',shop_id,'Đã có kết quả thị trường.',
                {'settlement_key':settlement_key,'card_id':card_id,'negotiation_id':session.active_negotiations.get(card_id),
                 'prediction_id':snapshot.prediction_id if snapshot else None,'metrics':result.model_dump(mode='json'),
                 'source':getattr(session.market,'source','adapter')})
        summary=run_night(session,expected_day)
        with session.lock:
            next_day=expected_day+1 if expected_day<session.simulation_days else None
            session.day=next_day if next_day is not None else expected_day
            session.step='idle' if next_day is not None else 'complete'
            receipt={'summary':summary,'next_day':next_day}
            session.night_receipts[expected_day]=receipt
            session.last_night=summary
            return receipt
    finally:
        with session.lock: session.phase_busy=False
