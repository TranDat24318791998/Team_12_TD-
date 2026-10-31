// Seller-facing projections only. Never use this data as Platform Agent input.
import {MAX_NEGOTIATION_ROUNDS} from './config.js';
const negotiationTypes=new Set(['platform_turn','shop_turn','code_check','referee_review','agent_activity']);
const turnTypes=new Set(['platform_turn','shop_turn']);

export function scopedEvents(state,events=[]){
  return events.filter(event=>event.run_id===state.run_id && event.day===state.day && (!event.shop_id || event.shop_id===state.demo_shop.shop_id)).sort((a,b)=>a.seq-b.seq);
}

export function sellerFeedback(state,events=[]){
  const own=scopedEvents(state,events).filter(event=>event.shop_id===state.demo_shop.shop_id);
  const latest=own.findLast(event=>event.type==='seller_decision' && (!event.data?.target_type || event.data.target_type==='proposal'));
  const feedback=latest?.data?.action==='negotiate'?latest:null;
  let result=state.renegotiation;
  if(feedback && result?.source_card_id!==feedback.data.card_id)result=null;
  if(!feedback && latest){
    const decidedCard=own.findLast(event=>event.type==='card_sent' && (event.data?.card_id || event.data?.card?.card_id)===latest.data?.card_id);
    if(latest.data?.card_id && latest.data.card_id===result?.restored_card_id || decidedCard?.data?.negotiation_id && decidedCard.data.negotiation_id===result?.negotiation_id)result=null;
  }
  const source=feedback?.data?.card_id || result?.source_card_id;
  if(!source || ['idle','night_done','complete','content_review'].includes(state.step))return {waiting:false};
  const card=state.pending_card;
  const cardEvent=own.findLast(event=>event.type==='card_sent' && (event.data?.card_id || event.data?.card?.card_id)===card?.card_id);
  const restored=state.step==='awaiting_decision' && result?.status==='failed' && result.restoration_status==='restored' && card?.card_id && card.card_id===result.restored_card_id;
  if(restored)return {waiting:false,result,card:true,restored:true};
  const newCard=state.step==='awaiting_decision' && card && card.card_id!==source && card.negotiation_id &&
    (result?result.status==='agreed' && card.negotiation_id===result.negotiation_id:
      feedback && cardEvent?.seq>feedback.seq && cardEvent.data?.negotiation_id===card.negotiation_id && card.negotiation_id!==feedback.data.negotiation_id);
  if(newCard)return {waiting:false,result,card:true};
  if(state.step==='day_done' && result?.status==='failed' && result.restoration_status==='blocked')return {waiting:false,result};
  return {waiting:true,result};
}

export function initialNegotiation(state,events=[]){
  if(state.step!=='day_done' || state.pending_card || state.renegotiation)return null;
  const own=scopedEvents(state,events).filter(event=>event.shop_id===state.demo_shop.shop_id);
  if(own.some(event=>event.type==='seller_decision' && event.data?.target_type!=='rule_question'))return null;
  let result=state.negotiation;
  if(!result){
    const latest=own.findLast(event=>negotiationTypes.has(event.type) || event.type==='negotiation_finished');
    if(latest?.type!=='negotiation_finished' || !latest.data?.negotiation_id)return null;
    result=latest.data;
  }
  if(!['queued','running','agreed','failed','unknown'].includes(result.status))return null;
  const review=own.findLast(event=>event.type==='referee_review' && event.data?.negotiation_id===result.negotiation_id && ['stop','ask_human'].includes(event.data?.action));
  const referee_action=Object.hasOwn(result,'referee_action')?result.referee_action:review?.data?.action;
  const reason_vi=result.reason_vi || (referee_action && review?.data?.action===referee_action?review.text_vi:null);
  return {result:{...result,referee_action,reason_vi},waiting:result.status!=='failed'};
}

export function waitingForNegotiation(state,events=[]){
  return sellerFeedback(state,events).waiting || !!initialNegotiation(state,events)?.waiting;
}

export function deriveActivity(state,events=[]){
  const dayEvents=scopedEvents(state,events);
  const own=dayEvents.filter(event=>event.shop_id===state.demo_shop.shop_id);
  const restart=own.findLast(event=>event.type==='seller_decision' && event.data?.action==='negotiate');
  const boundary=restart?.seq ?? 0;
  const previousIds=new Set(own.filter(event=>event.seq<=boundary).map(event=>event.data?.negotiation_id).filter(Boolean));
  const candidates=own.filter(event=>negotiationTypes.has(event.type) && event.data?.negotiation_id && event.seq>boundary && !previousIds.has(event.data.negotiation_id));
  const snapshot=state.agent_activity;
  const validSnapshot=snapshot && typeof snapshot.negotiation_id==='string' && Number.isInteger(snapshot.updated_seq) && snapshot.updated_seq>boundary && !previousIds.has(snapshot.negotiation_id);
  const newest=candidates.at(-1);
  const candidateIds=[...new Set(candidates.map(event=>event.data.negotiation_id))];
  const newestId=candidateIds.at(-1);
  const negotiationId=validSnapshot && (snapshot.negotiation_id===newestId || (!candidateIds.includes(snapshot.negotiation_id) && (!newest || snapshot.updated_seq>=newest.seq)))?snapshot.negotiation_id:newestId;
  const current=candidates.filter(event=>event.data.negotiation_id===negotiationId);
  const turns=current.filter(event=>turnTypes.has(event.type));
  const platform=turns.findLast(event=>event.type==='platform_turn');
  const shop=turns.findLast(event=>event.type==='shop_turn');
  const lastTurn=turns.at(-1);
  const check=current.findLast(event=>event.type==='code_check' && typeof event.data?.ok==='boolean');
  const referee=current.findLast(event=>event.type==='referee_review');
  const semantic=current.filter(event=>event.type!=='agent_activity').at(-1);
  const tasks=current.filter(event=>event.type==='agent_activity').map(event=>({...event.data,actor:event.actor,updated_seq:event.seq}));
  if(validSnapshot && snapshot.negotiation_id===negotiationId)tasks.push(snapshot);
  const taskGroups=new Map();
  for(const update of tasks.sort((a,b)=>a.updated_seq-b.updated_seq)){
    if(!update.task_id)continue;
    const previous=taskGroups.get(update.task_id);
    // A terminal result from an older task must not clear a newer in-flight task.
    // A duplicated running event cannot reopen a terminal task with the same ID.
    if(previous && previous.status!=='running' && update.status==='running')continue;
    taskGroups.set(update.task_id,{...update,started_seq:previous?.started_seq ?? update.updated_seq});
  }
  const task=[...taskGroups.values()].sort((a,b)=>a.started_seq-b.started_seq).at(-1);
  const currentTask=task && task.updated_seq>=(semantic?.seq ?? 0)?task:null;
  const cardEvent=own.findLast(event=>event.type==='card_sent');
  // A decision event may arrive one poll before its StateView. Do not revive the old card.
  const feedback=sellerFeedback(state,events);
  const initialResult=initialNegotiation(state,events);
  const awaiting=state.step==='awaiting_decision' && !feedback.waiting;
  const negotiating=state.step==='negotiating' || feedback.waiting || !!initialResult?.waiting;
  const question=!negotiating && (state.pending_card || cardEvent?.data?.card)?.kind==='question';
  const decision=own.findLast(event=>event.type==='seller_decision' && event.seq>(lastTurn?.seq ?? boundary));
  const outcome=awaiting?'waiting_seller':initialResult?.result.status==='failed'?(initialResult.result.referee_action==='stop'?'stopped':'failed'):decision?.data.action==='reject'?'rejected':decision && ['accept','edit'].includes(decision.data.action)?'approved':lastTurn?.data.action==='withdraw' || lastTurn?.data.action==='reject'?'no_fit':currentTask?.status==='failed'?'failed':currentTask?.status==='stopped'?'stopped':lastTurn?.data.action==='accept'?'agreed':negotiating?'negotiating':'idle';
  const running=negotiating && feedback.result?.status!=='unknown' && initialResult?.result.status!=='unknown' && currentTask?.status==='running' && ['platform_agent','shop_agent','code','referee'].includes(currentTask.actor) && !['no_fit','stopped'].includes(outcome)?currentTask:null;
  const round=Math.max(0,...turns.map(event=>Number.isInteger(event.data.round)?event.data.round:0),Number.isInteger(currentTask?.round)?currentTask.round:0);
  const ids=[...new Set(own.filter(event=>negotiationTypes.has(event.type)).map(event=>event.data?.negotiation_id).filter(Boolean))];
  if(negotiationId && !ids.includes(negotiationId))ids.push(negotiationId);
  const packages=turns.filter(event=>event.data.package);
  const previous=own.findLast(event=>turnTypes.has(event.type) && event.seq<boundary && event.data?.package);
  const initial=packages.find(event=>event.type==='platform_turn' && event.data.action==='propose');
  const baseline=initial?.data.package || previous?.data.package || packages[0]?.data.package || null;
  const latest=packages.at(-1)?.data.package || null;
  const checkedPackage=check?packages.findLast(event=>event.seq<check.seq)?.data.package:null;
  const packageKeys=['content_refresh','ads_daily_budget','voucher_pct','stop_roas_below','stop_after_days','duration_days'];
  const checkMatchesLatest=!!checkedPackage && !!latest && packageKeys.every(key=>checkedPackage[key]===latest[key]);
  let label='Chờ bắt đầu ngày mới';
  if(negotiating)label=running?.label_vi || (outcome==='agreed'?'Hai agent đã đồng thuận · Chờ kiểm tra cuối':outcome==='no_fit'?'Chưa tìm được gói phù hợp':outcome==='failed'?'Tác vụ chưa thành công':outcome==='stopped'?'Đã dừng thương lượng':lastTurn?.type==='shop_turn'?'Agent shop đã phản hồi · Chờ lượt tiếp theo':lastTurn?'Agent sàn đã gửi gói · Chờ phản hồi':'Đang chờ sự kiện thương lượng');
  if(awaiting)label=question?'Chờ chủ shop xác nhận sở thích':'Hai agent đã thống nhất · Chờ chủ shop duyệt';
  if(outcome==='no_fit')label='Chưa tìm được gói phù hợp · Đã kết thúc thương lượng';
  if(outcome==='failed')label='Tác vụ chưa thành công';
  if(outcome==='stopped')label='Đã dừng thương lượng';
  if(outcome==='rejected')label='Chủ shop đã từ chối · Không áp dụng gói này';
  if(outcome==='approved')label=question?'Đã ghi nhận câu trả lời về sở thích':state.step==='content_review'?'Chủ shop đã duyệt gói · Đang ở bước nội dung':'Đã ghi nhận quyết định của chủ shop';
  if(initialResult?.result.status==='failed')label=initialResult.result.referee_action==='stop'?'Trọng tài đã dừng thương lượng · Chưa có gói để chị duyệt':initialResult.result.referee_action==='ask_human'?'Trọng tài yêu cầu làm rõ · Chưa có gói để chị duyệt':'Chưa có gói để chị duyệt';
  if(initialResult?.result.status==='agreed')label='Đang chờ thẻ đề xuất để chị duyệt';
  if(initialResult?.result.status==='unknown')label='Chưa xác định được kết quả thương lượng';
  if(feedback.waiting && feedback.result?.status==='failed')label=feedback.result.restoration_allowed?'Chờ chị kiểm tra lại gói trước':'Chưa thể kiểm tra lại gói trước';
  if(feedback.result?.status==='unknown')label='Chưa xác định được kết quả thương lượng';
  if(state.step==='complete')label='Đã hoàn tất phiên mô phỏng';
  const lastDirection=lastTurn?.type==='shop_turn'?'to-platform':lastTurn?'to-shop':'waiting';
  const stage=awaiting?4:running?.phase==='proposal'?1:running?.phase==='validation'?2:running?.phase==='response' || running?.phase==='referee'?3:semantic?.type==='code_check'?2:semantic?.type==='shop_turn' || semantic?.type==='referee_review'?3:platform?1:0;
  return {dayEvents,current,negotiationId,attempt:negotiationId?ids.indexOf(negotiationId)+1:null,round,maxRounds:MAX_NEGOTIATION_ROUNDS,platform,shop,check,checkMatchesLatest,referee,running,outcome,awaiting,question,negotiating,label,lastDirection,stage,baseline,latest,baselineLabel:!initial && previous?'Gói trước góp ý':'Đề xuất đầu'};
}

export function journeyProgress(state,events=[],pending){
  const dayEvents=scopedEvents(state,events);
  const initial=initialNegotiation(state,events);
  const current=pending==='/api/night'?5:waitingForNegotiation(state,events)?1:({idle:0,negotiating:1,awaiting_decision:2,content_review:3,day_done:4,night_done:6,complete:6}[state.step] ?? 0);
  const lastCard=state.pending_card || dayEvents.findLast(event=>event.type==='card_sent')?.data?.card;
  const decision=dayEvents.findLast(event=>event.type==='seller_decision');
  const noFit=deriveActivity(state,events).outcome==='no_fit';
  const declined=decision?.data?.action==='reject';
  const question=lastCard?.kind==='question';
  const skipped=new Set();
  if(initial?.result.status==='failed'){skipped.add(2);skipped.add(3);skipped.add(4);}
  if(sellerFeedback(state,events).result?.restoration_status==='blocked'){skipped.add(2);skipped.add(3);skipped.add(4);}
  if(question && !dayEvents.some(event=>turnTypes.has(event.type))){skipped.add(0);skipped.add(1);}
  if((declined || noFit || question) && current>=4){skipped.add(3);skipped.add(4);}
  if(lastCard?.package?.content_refresh===false && current>=3)skipped.add(3);
  return {current,skipped};
}
