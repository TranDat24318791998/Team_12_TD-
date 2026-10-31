import test from 'node:test';
import assert from 'node:assert/strict';
import {createClient,selectPreview,commandTarget,commandFinished,readEvents} from '../src/api.js';
import {SIMULATION_DAYS} from '../src/config.js';
import {dec,vnd,mediaURL} from '../src/format.js';
const storage=()=>{const map=new Map();return {getItem:key=>map.get(key)??null,setItem:(key,value)=>map.set(key,String(value))};};
const response=(body,status=200)=>({ok:status>=200 && status<300,status,json:async()=>body});

// Test the same request interface used by all React views, without paid API calls.
test('HTTP mode is API by default; explicit query overrides the saved preview choice',()=>{
  const store=storage();assert.equal(selectPreview({search:'',protocol:'https:'},store),false);
  assert.equal(selectPreview({search:'?preview=1',protocol:'https:'},store),true);
  assert.equal(selectPreview({search:'',protocol:'https:'},store),true);
  assert.equal(selectPreview({search:'?preview=0',protocol:'https:'},store),false);
  assert.equal(selectPreview({search:'',protocol:'file:'},store),true);
});
test('POST JSON carries session credentials and explicit command headers',async()=>{
  let sent;const client=createClient({fetchImpl:async(path,options)=>{sent={path,options};return response({step:'content_review'});}});
  await client.request('/api/decision',{method:'POST',target:'run:card-1',body:{card_id:'D-1',action:'accept'}});
  assert.equal(sent.path,'/api/decision');assert.equal(sent.options.credentials,'same-origin');
  assert.equal(sent.options.headers['Content-Type'],'application/json');assert.ok(sent.options.headers['Idempotency-Key']);assert.ok(sent.options.headers['X-Request-ID']);
  assert.equal(sent.options.headers.Authorization,undefined);assert.deepEqual(JSON.parse(sent.options.body),{card_id:'D-1',action:'accept'});
});
test('unknown network outcome reuses its key; the next deliberate reset receives a new key',async()=>{
  const keys=[];let attempt=0;const client=createClient({fetchImpl:async(path,options)=>{keys.push(options.headers['Idempotency-Key']);if(attempt++===0)throw new Error('Network unavailable');return response({state:{run_id:'new'}});}});
  const options={method:'POST',target:'run-1',body:{memory:true,seed:42}};
  await assert.rejects(client.request('/api/reset',options),/Network unavailable/);
  await client.request('/api/reset',options);await client.request('/api/reset',options);
  assert.equal(keys[0],keys[1]);assert.notEqual(keys[1],keys[2]);
});
test('an unresolved command cannot silently retry with a different body',async()=>{
  let calls=0;const client=createClient({fetchImpl:async()=>{calls++;throw new Error('lost response');}});
  await assert.rejects(client.request('/api/content/retry',{method:'POST',target:'attempt-1',body:{feedback_vi:'Nền sáng'}}));
  await assert.rejects(client.request('/api/content/retry',{method:'POST',target:'attempt-1',body:{feedback_vi:'Nền hồng'}}),/chưa rõ kết quả/);
  assert.equal(calls,1);
});
test('accepted/in-progress and server failures retain idempotency until terminal success',async()=>{
  const keys=[];let index=0;const replies=[response({operation_id:'op'},202),response({error:{code:'COMMAND_IN_PROGRESS',message_vi:'Đang xử lý'}},409),response({error:{code:'UNAVAILABLE',message_vi:'Thử lại sau'}},503),response({next_day:2})];
  const client=createClient({fetchImpl:async(path,options)=>{keys.push(options.headers['Idempotency-Key']);return replies[index++];}});
  const options={method:'POST',target:'day-1'};
  await assert.rejects(client.request('/api/night',options),error=>error.pending===true);
  await assert.rejects(client.request('/api/night',options),error=>error.pending===true);
  await assert.rejects(client.request('/api/night',options),/Thử lại sau/);
  assert.deepEqual(await client.request('/api/night',options),{next_day:2});assert.equal(new Set(keys).size,1);
});
test('terminal version conflicts expose the backend message and allow a new command key',async()=>{
  const keys=[];let attempt=0;const client=createClient({fetchImpl:async(path,options)=>{keys.push(options.headers['Idempotency-Key']);return attempt++?response({step:'day_done'}):response({error:{code:'VERSION_CONFLICT',message:'Thẻ đã thay đổi. Hãy tải lại.'}},409);}});
  const options={method:'POST',target:'card-1',body:{card_id:'D-1',action:'accept'}};
  await assert.rejects(client.request('/api/decision',options),error=>error.code==='VERSION_CONFLICT' && error.message.includes('Thẻ đã thay đổi'));
  await client.request('/api/decision',options);assert.notEqual(keys[0],keys[1]);
});
test('API reads are returned unchanged and network failures do not fall back to fixtures',async()=>{
  const state={run_id:'database-run',demo_shop:{name:'Cửa hàng mới',price:299000}};
  const client=createClient({fetchImpl:async()=>response(state)});assert.deepEqual(await client.request('/api/state'),state);
  const failing=createClient({fetchImpl:async()=>{throw new Error('No database connection');}});await assert.rejects(failing.request('/api/state'),/No database connection/);assert.equal(failing.preview,false);
});
test('command targets bind the current card, content attempt and final-day state',()=>{
  const state={run_id:'run',day:1,step:'content_review',pending_card:{card_id:'D-1'},content_draft:{version:1}};
  assert.notEqual(commandTarget(state,'/api/decision'),commandTarget({...state,pending_card:{card_id:'D-2'}},'/api/decision'));
  assert.notEqual(commandTarget(state,'/api/content/retry'),commandTarget({...state,content_draft:{version:2}},'/api/content/retry'));
  assert.notEqual(commandTarget({...state,day:7,step:'day_done'},'/api/night'),commandTarget({...state,day:7,step:'complete'},'/api/night'));
});
test('preview covers negotiation, approval, retries, feedback confirmation and seven-day completion',async()=>{
  let clock=1000000;const client=createClient({preview:true,storage:storage(),now:()=>clock,assetRoot:new URL('https://demo.test/img/'),fetchImpl:async()=>{throw new Error('Preview must not call a network API');}});
  const read=()=>client.request('/api/state');
  let commandCount=0;const command=(path,body)=>client.request(path,{method:'POST',body,target:String(++commandCount)});
  let state=await read();assert.equal(state.demo_shop.price,175000);assert.equal(state.demo_shop.stock,300);
  assert.equal(state.brief_editable,false);await assert.rejects(command('/api/day/start'),/xác nhận yêu cầu/);
  await assert.rejects(command('/api/brief/confirm',{...state.brief_preset,ads_daily_cap:1}),/đã được cố định/);
  await command('/api/brief/confirm',state.brief_preset);
  await command('/api/day/start');clock+=6000;state=await read();assert.equal(state.pending_card.package.voucher_pct,3);
  await command('/api/decision',{card_id:state.pending_card.card_id,action:'negotiate',note_vi:'Giảm voucher còn 2%.'});clock+=3000;state=await read();assert.equal(state.pending_card.package.voucher_pct,2);
  await command('/api/decision',{card_id:state.pending_card.card_id,action:'accept'});
  await assert.rejects(command('/api/content/apply',{cover_option:'A'}),/ảnh đã tạo xong/);
  clock+=4000;await command('/api/content/retry',{feedback_vi:'Ảnh nền sáng hơn.'});clock+=4000;
  await command('/api/content/retry',{feedback_vi:'Giữ màu quạt.'});clock+=4000;
  await assert.rejects(command('/api/content/retry',{feedback_vi:'Làm lại'}),/3 phiên bản/);
  await command('/api/content/apply',{cover_option:'B'});state=await read();assert.equal(state.demo_shop.active_voucher_pct,2);assert.match(state.demo_shop.images[0],/cover-b.svg/);
  const original=state.demo_shop_original;await command('/api/night');state=await read();assert.equal(state.day,2);assert.equal(state.last_night.day,1);
  await command('/api/day/start');clock+=6000;state=await read();assert.equal(state.pending_card.kind,'question');assert.equal(state.pending_card.package,null);
  await command('/api/decision',{card_id:state.pending_card.card_id,action:'accept',rule_answer:true});
  for(let day=2;day<=SIMULATION_DAYS;day++){
    state=await read();assert.equal(state.day,day);
    if(state.step==='idle'){await command('/api/day/start');clock+=6000;state=await read();}
    if(state.step==='awaiting_decision'){await command('/api/decision',{card_id:state.pending_card.card_id,action:'accept',rule_answer:true});state=await read();}
    if(state.step==='content_review'){clock+=4000;await read();await command('/api/content/apply',{cover_option:'A'});}
    const night=await command('/api/night');assert.equal(night.next_day,day===SIMULATION_DAYS?null:day+1);
  }
  state=await read();assert.equal(state.day,7);assert.equal(state.step,'complete');assert.deepEqual(state.demo_shop_original,original);
  await assert.rejects(command('/api/day/start'),/hoàn tất/);await assert.rejects(command('/api/night'),/Hoàn tất quyết định/);
  const proof=await client.request('/api/proof');assert.equal(proof.days,7);assert.match(proof.note_vi,/minh họa/);
  const events=await client.request('/api/events?after=3');assert.ok(events.events.every(event=>event.seq>3));assert.equal(new Set(events.events.map(event=>event.seq)).size,events.events.length);
});
test('preview rejection/reset does not publish content or create an active package',async()=>{
  let clock=0;const client=createClient({preview:true,storage:storage(),now:()=>clock});
  await client.request('/api/reset',{method:'POST',body:{memory:false}});const initial=await client.request('/api/state');
  await client.request('/api/brief/confirm',{method:'POST',body:initial.brief_preset});
  await client.request('/api/day/start',{method:'POST'});clock+=6000;let state=await client.request('/api/state');
  await client.request('/api/decision',{method:'POST',body:{card_id:state.pending_card.card_id,action:'reject'}});
  await client.request('/api/night',{method:'POST'});state=await client.request('/api/state');
  assert.deepEqual(state.demo_shop,initial.demo_shop);assert.equal(state.active_package,null);assert.equal(state.content_draft,null);assert.deepEqual(state.last_night.lesson_ops,[]);
});
test('formatting preserves missing data and blocks script URLs',()=>{
  assert.equal(vnd(45000),'45.000đ');assert.equal(dec(6.5),'6,5');assert.equal(vnd(null),'—');assert.equal(dec(undefined),'—');
  assert.equal(mediaURL('javascript:alert(1)'), '');assert.equal(mediaURL('/api/v1/asset/download','https://demo.test/'),'https://demo.test/api/v1/asset/download');
});

test('a night command remains in progress until close and advance have completed',()=>{
  const before={run_id:'run',day:7,step:'day_done',last_night:{day:6}};
  assert.equal(commandFinished(before,{...before,last_night:{day:7}},'/api/night'),false);
  assert.equal(commandFinished(before,{...before,step:'complete',last_night:{day:7}},'/api/night'),true);
  assert.equal(commandFinished({...before,day:1},{...before,day:2,step:'idle'},'/api/night'),true);
});

test('event reader drains hidden-only pages and rejects non-advancing cursors',async()=>{
  const seen=[];const client={request:async path=>{const cursor=Number(new URL(path,'http://local').searchParams.get('after'));seen.push(cursor);return cursor===0?{run_id:'r',events:[],last_seq:100,has_more:true}:{run_id:'r',events:[{seq:101,run_id:'r'}],last_seq:101,has_more:false};}};
  const result=await readEvents(client,'r');assert.deepEqual(seen,[0,100]);assert.equal(result.events[0].seq,101);
  await assert.rejects(readEvents({request:async()=>({run_id:'r',events:[],last_seq:0,has_more:true})},'r'),/không tiến/);
  await assert.rejects(readEvents({request:async()=>({run_id:'other',events:[],last_seq:0,has_more:false})},'r'),/Phiên đã thay đổi/);
});
