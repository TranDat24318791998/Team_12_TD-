import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createClient} from '../src/api.js';
import {comparisonDays} from '../src/proofComparison.js';

const fixture=JSON.parse(await readFile(new URL('../fixtures/day7.json',import.meta.url),'utf8'));
const storage=()=>{const map=new Map();return {getItem:key=>map.get(key)??null,setItem:(key,value)=>map.set(key,String(value))};};
const reply=(value,status=200)=>({ok:status===200,json:async()=>structuredClone(value)});
const jump=client=>client.request('/api/demo/jump-day7',{method:'POST'});

test('one click imports all seven days from database and survives reloading the client',async()=>{
  const store=storage(),requests=[];
  const client=createClient({preview:true,storage:store,fetchImpl:async(path,options)=>{requests.push({path,options});return reply(fixture);}});
  const before=await client.request('/api/state');
  await jump(client);
  const state=await client.request('/api/state'),events=(await client.request('/api/events?after=0')).events,report=await client.request('/api/proof');
  assert.equal(requests.length,1);assert.equal(requests[0].path,'/api/demo/day7');assert.equal(requests[0].options.cache,'no-store');
  assert.equal(state.day,7);assert.equal(state.step,'complete');assert.equal(state.last_night.day,7);assert.equal(state.live_calls_left,0);
  assert.deepEqual(events.filter(e=>e.type==='night_summary').map(e=>e.day),[1,2,3,4,5,6,7]);
  assert.equal(new Set(events.map(e=>e.seq)).size,events.length);assert.ok(events.every(e=>e.run_id===state.run_id));
  assert.equal(report.sample_source.kind,'sqlite_sample');assert.equal(comparisonDays(report).length,7);assert.match(state.demo_shop.images[0],/^\/img\//);
  assert.equal(JSON.parse(store.getItem('growth-agents.react-preview.v3.before-day7')).state.run_id,before.run_id);
  const reload=createClient({preview:true,storage:store,fetchImpl:async()=>{throw new Error('Reload should use the imported session');}});
  assert.deepEqual(await reload.request('/api/proof'),report);assert.deepEqual(await reload.request('/api/state'),state);
  await assert.rejects(reload.request('/api/day/start',{method:'POST'}),/hoàn tất/);
});
test('repeated jump does not duplicate history; reset returns to a clean day one',async()=>{
  const client=createClient({preview:true,storage:storage(),fetchImpl:async()=>reply(fixture)});
  await jump(client);await jump(client);
  assert.equal((await client.request('/api/events?after=0')).events.length,fixture.events.length);
  await client.request('/api/reset',{method:'POST',body:{memory:true}});
  assert.equal((await client.request('/api/state')).day,1);
  assert.equal((await client.request('/api/events?after=0')).events.length,0);
  assert.equal((await client.request('/api/proof')).sample_source,undefined);
});
test('failed or incomplete database response keeps the current session intact',async()=>{
  const incomplete=structuredClone(fixture);incomplete.events=incomplete.events.filter(e=>e.day!==7);
  for(const fetchImpl of [async()=>reply(incomplete),async()=>reply({error:{message_vi:'Database chưa sẵn sàng'}},503),async()=>{throw new TypeError('fetch failed');}]){
    const store=storage(),client=createClient({preview:true,storage:store,fetchImpl});
    const before=await client.request('/api/state');
    await assert.rejects(jump(client));
    assert.deepEqual(await client.request('/api/state'),before);
    assert.equal(store.getItem('growth-agents.react-preview.v3.before-day7'),null);
  }
});
