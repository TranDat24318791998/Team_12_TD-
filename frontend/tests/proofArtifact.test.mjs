import test from 'node:test';
import assert from 'node:assert/strict';
import {readDemoArtifact,demoEvidence} from '../src/proofArtifact.js';

const artifact=()=>({schema_version:'demo-proof.v1',manifest:{comparison_id:'pair-real',shop_id:'D',run_on:'run-on',run_off:'run-off',seed:42,days:7,source:'precomputed_offline_simulation',provider_eval:'not_run',artifact_sha256:'a'.repeat(64),brief_refs:['brief-on','brief-off']},
  report:{status:'ready',source:'precomputed_offline_simulation',run_on:'run-on',run_off:'run-off',seed:42,days:7,comparison_days:[]},
  evidence:{on:[{run_id:'run-on',seq:3}],off:[{run_id:'run-off',seq:5}]}});

test('saved proof retains its original manifest, runs and paired evidence',()=>{
  const value=artifact();assert.equal(readDemoArtifact(value),value);
  assert.deepEqual(demoEvidence(value),{schema_version:value.schema_version,manifest:value.manifest,evidence:value.evidence});
  assert.equal(value.manifest.run_on,'run-on');assert.equal(value.evidence.off[0].run_id,'run-off');
});
test('incomplete or misleading proof is never treated as a ready saved report',()=>{
  for(const change of [v=>delete v.evidence,v=>v.report.run_on='other',v=>v.manifest.provider_eval='live',v=>v.report.status='pending',v=>v.manifest.source='fixture']){
    const value=artifact();change(value);assert.throws(()=>readDemoArtifact(value),/chưa sẵn sàng/);
  }
});
