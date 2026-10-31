import test from 'node:test';
import assert from 'node:assert/strict';
import {deriveActivity,journeyProgress,scopedEvents} from '../src/activity.js';

const state={run_id:'run-1',day:1,step:'negotiating',demo_shop:{shop_id:'D'},pending_card:null};
const pkg={content_refresh:true,ads_daily_budget:70000,voucher_pct:10,stop_roas_below:4,stop_after_days:2,duration_days:3};
const counter={...pkg,ads_daily_budget:45000,voucher_pct:3,stop_roas_below:6.5};
const event=(seq,type,data={},extra={})=>({seq,run_id:'run-1',day:1,shop_id:'D',type,actor:type==='platform_turn'?'platform_agent':'shop_agent',text_vi:type,ts:'12:00',data:{negotiation_id:'n-1',...data},...extra});
const proposal=event(1,'platform_turn',{round:1,action:'propose',package:pkg});
const response=event(3,'shop_turn',{round:1,action:'counter',package:counter});
const acceptance=event(5,'platform_turn',{round:2,action:'accept',package:counter});

test('interaction and event log exclude other runs, shops and days, and retain cursor gaps',()=>{
  const events=[event(9,'day_start',{}, {shop_id:null}),response,proposal,event(2,'platform_turn',{package:pkg},{shop_id:'X'}),event(4,'platform_turn',{package:pkg},{run_id:'run-2'}),event(6,'platform_turn',{package:pkg},{day:2})];
  assert.deepEqual(scopedEvents(state,events).map(e=>e.seq),[1,3,9]);
  assert.deepEqual(deriveActivity(state,events).current.map(e=>e.seq),[1,3]);
});

test('legacy completed turns show handoff and package diff without inventing running tasks',()=>{
  const activity=deriveActivity(state,[proposal,response]);
  assert.equal(activity.round,1);assert.equal(activity.maxRounds,3);assert.equal(activity.running,null);
  assert.equal(activity.lastDirection,'to-platform');assert.deepEqual(activity.baseline,pkg);assert.deepEqual(activity.latest,counter);
  assert.match(activity.label,/đã phản hồi/);
});

test('a passing check for an older package is not presented as validation for changed terms',()=>{
  const check=event(2,'code_check',{ok:true,checks:[]},{actor:'code'});
  assert.equal(deriveActivity(state,[proposal,check]).checkMatchesLatest,true);
  assert.equal(deriveActivity(state,[proposal,check,response]).checkMatchesLatest,false);
});

test('agreement is distinct from a seller decision and does not fill all three rounds',()=>{
  const events=[proposal,response,acceptance];
  assert.equal(deriveActivity(state,events).outcome,'agreed');
  const awaiting=deriveActivity({...state,step:'awaiting_decision',pending_card:{kind:'offer',card_id:'c-1'}},events);
  assert.equal(awaiting.outcome,'waiting_seller');assert.equal(awaiting.round,2);assert.match(awaiting.label,/Chờ chủ shop duyệt/);
});

test('new attempt clears old turns/checks immediately; comparison after feedback uses the previous package',()=>{
  const restart=event(6,'seller_decision',{card_id:'c-1',action:'negotiate'});
  const oldCheck=event(4,'code_check',{ok:true});
  const staleState={...state,step:'awaiting_decision',pending_card:{card_id:'c-1',kind:'offer'}};
  const waiting=deriveActivity(staleState,[proposal,response,oldCheck,acceptance,restart]);
  assert.equal(waiting.negotiating,true);assert.equal(waiting.awaiting,false);assert.equal(waiting.round,0);assert.equal(waiting.check,undefined);assert.equal(waiting.latest,null);
  const newTurn=event(8,'shop_turn',{negotiation_id:'n-2',round:1,action:'counter',package:{...counter,voucher_pct:2}});
  const next=deriveActivity(state,[proposal,response,oldCheck,acceptance,restart,newTurn]);
  assert.equal(next.negotiationId,'n-2');assert.equal(next.attempt,2);assert.equal(next.round,1);assert.equal(next.check,undefined);
  assert.deepEqual(next.baseline,counter);assert.equal(next.latest.voucher_pct,2);assert.equal(next.baselineLabel,'Gói trước góp ý');
});

test('only explicit running telemetry lights a node and subsequent results clear it',()=>{
  const task=event(2,'agent_activity',{task_id:'t-1',round:1,phase:'response',status:'running',label_vi:'Agent shop đang xem gói'});
  assert.equal(deriveActivity(state,[proposal,task]).running.actor,'shop_agent');
  assert.equal(deriveActivity(state,[proposal,task,response]).running,null);
  const snapshot={negotiation_id:'n-1',task_id:'t-1',round:1,phase:'response',status:'running',actor:'shop_agent',label_vi:'Đang xử lý',updated_seq:2};
  assert.equal(deriveActivity({...state,agent_activity:snapshot},[proposal,response]).running,null);
  assert.equal(deriveActivity({...state,agent_activity:{...snapshot,updated_seq:4}},[proposal,response]).running.actor,'shop_agent');
  assert.equal(deriveActivity({...state,step:'awaiting_decision',agent_activity:{...snapshot,updated_seq:4}},[proposal,response]).running,null);
});

test('old task terminal results cannot replace a newer task in the same negotiation',()=>{
  const old=event(2,'agent_activity',{task_id:'old-task',round:1,phase:'response',status:'running'});
  const running=event(4,'agent_activity',{task_id:'new-task',round:2,phase:'proposal',status:'running',label_vi:'Lượt mới'},{actor:'platform_agent'});
  const late=event(5,'agent_activity',{task_id:'old-task',round:1,phase:'response',status:'done'});
  assert.equal(deriveActivity(state,[proposal,old,response,running,late]).running.task_id,'new-task');
  const oldAttemptResult=event(9,'agent_activity',{task_id:'old-task',round:1,phase:'response',status:'done'});
  const restart=event(6,'seller_decision',{card_id:'c-1',action:'negotiate'});
  const fresh=event(7,'agent_activity',{negotiation_id:'n-2',task_id:'fresh',round:1,phase:'response',status:'running'});
  assert.equal(deriveActivity(state,[proposal,old,response,restart,fresh,oldAttemptResult]).negotiationId,'n-2');
});

test('referee and code have independent evidence; no fit and failures do not become approval',()=>{
  const check=event(2,'code_check',{ok:false,checks:[{ok:false,message_vi:'Chưa đạt'}]},{actor:'code'});
  const referee=event(4,'referee_review',{action:'refocus',focused_question:'Điều khoản nào cần sửa?'},{actor:'referee'});
  const activity=deriveActivity(state,[proposal,check,response,referee]);
  assert.equal(activity.check.data.ok,false);assert.equal(activity.referee.data.action,'refocus');
  assert.equal(deriveActivity(state,[proposal,event(5,'shop_turn',{round:1,action:'reject',package:null})]).outcome,'no_fit');
  assert.match(deriveActivity({...state,step:'day_done'},[proposal,event(5,'shop_turn',{round:1,action:'reject',package:null})]).label,/Chưa tìm được gói phù hợp/);
  assert.equal(deriveActivity(state,[proposal,event(5,'agent_activity',{task_id:'t',phase:'response',round:1,status:'failed'})]).outcome,'failed');
});

test('question-only cards skip negotiation; rejection skips content/apply; final day has no current step',()=>{
  const question={...state,step:'awaiting_decision',pending_card:{card_id:'q',kind:'question',package:null}};
  assert.equal(deriveActivity(question,[]).question,true);assert.match(deriveActivity(question,[]).label,/xác nhận sở thích/);
  assert.deepEqual([...journeyProgress(question,[]).skipped],[0,1]);
  const questionEvents=[event(1,'card_sent',{card:question.pending_card}),event(2,'seller_decision',{card_id:'q',action:'accept'})];
  const answered=deriveActivity({...state,step:'day_done'},questionEvents);
  assert.equal(answered.question,true);assert.match(answered.label,/câu trả lời về sở thích/);
  const rejected=event(7,'seller_decision',{card_id:'c-1',action:'reject'});
  assert.equal(deriveActivity({...state,step:'day_done'},[proposal,rejected]).outcome,'rejected');
  assert.deepEqual([...journeyProgress({...state,step:'day_done'},[proposal,rejected]).skipped],[3,4]);
  assert.equal(journeyProgress({...state,step:'complete'},[]).current,6);
  assert.equal(journeyProgress({...state,step:'day_done'},[],'/api/night').current,5);
});
