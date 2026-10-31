import test from 'node:test';
import assert from 'node:assert/strict';
import {comparisonDays} from '../src/proofComparison.js';
import {previewComparisonDays} from '../src/previewComparison.js';

const report=()=>({days:7,run_on:'preview-on',run_off:'preview-off',comparison_days:previewComparisonDays()});

test('preview compares the same day-one dialogue and only past evidence on later days',()=>{
  const days=comparisonDays(report());
  assert.equal(days.length,7);
  assert.deepEqual(days[0].off.messages.map(m=>m.text_vi),days[0].on.messages.map(m=>m.text_vi));
  assert.equal(days[0].on.memory_used.length,0);
  assert.ok(days.every(day=>day.off.memory_used.length===0 && day.on.memory_used.every(source=>source.source_day<day.day)));
  assert.equal(days[1].request_vi,'Làm ảnh bìa mới cho mẫu quạt này giúp chị nhé.');
  assert.match(days[1].on.messages[0].text_vi,/Em nhớ/);
});
test('legacy reports do not receive fictional conversations',()=>{
  assert.deepEqual(comparisonDays({days:7,run_on:'real-on',run_off:'real-off'}),[]);
  assert.deepEqual(comparisonDays({...report(),run_on:'real-on'}),[]);
  assert.deepEqual(comparisonDays({...report(),run_on:'preview-off'}),[]);
});
test('wrong run, future memory and memory in the control arm are excluded',()=>{
  for(const change of [day=>{day.on.run_id='another-run';},day=>{day.on.memory_used[0].source_day=2;},day=>{day.on.memory_used[0].run_id='another-run';},day=>{day.off.memory_used=[{source_day:1}];}]){
    const data=report();change(data.comparison_days[1]);
    assert.equal(comparisonDays(data).some(day=>day.day===2),false);
  }
});
test('duplicate days and ambiguous messages are not silently presented as evidence',()=>{
  const data=report();data.comparison_days.push(structuredClone(data.comparison_days[1]));
  assert.equal(comparisonDays(data).some(day=>day.day===2),false);
  const only=report();only.comparison_days[1].on.messages.push({...only.comparison_days[1].on.messages[0]});
  only.comparison_days[1].off.messages.push({id:'raw',actor:'private_reasoning',text_vi:'Do not expose'});
  const second=comparisonDays(only)[1];assert.equal(second.on.messages.length,1);assert.equal(second.off.messages.length,2);
  only.comparison_days[1].on.result_vi={unexpected:'object'};only.comparison_days[1].takeaway_vi=[];
  const safe=comparisonDays(only)[1];assert.equal(safe.on.result_vi,'');assert.equal(safe.takeaway_vi,'');
});
