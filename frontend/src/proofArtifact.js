// Keep the persisted pair and its evidence together when selecting or exporting it.
export function readDemoArtifact(value){
  const manifest=value?.manifest,report=value?.report,evidence=value?.evidence;
  if(value?.schema_version!=='demo-proof.v1' || !manifest || !report || !evidence ||
     manifest.source!=='precomputed_offline_simulation' || manifest.provider_eval!=='not_run' ||
     report.source!=='precomputed_offline_simulation' || report.status!=='ready' ||
     manifest.shop_id!=='D' || typeof manifest.comparison_id!=='string' || !manifest.comparison_id ||
     typeof manifest.run_on!=='string' || !manifest.run_on || typeof manifest.run_off!=='string' || !manifest.run_off ||
     manifest.run_on===manifest.run_off || report.run_on!==manifest.run_on || report.run_off!==manifest.run_off ||
     report.seed!==manifest.seed || report.days!==manifest.days || !Array.isArray(evidence.on) || !Array.isArray(evidence.off)){
    throw new Error('Báo cáo mô phỏng đã lưu chưa sẵn sàng hoặc không đúng định dạng.');
  }
  return value;
}

export function demoEvidence(artifact){
  return {schema_version:artifact.schema_version,manifest:artifact.manifest,evidence:artifact.evidence};
}

export async function readProofEvidence(client,report){
  const {comparison_id,run_on,run_off}=report || {};
  if(![comparison_id,run_on,run_off].every(value=>typeof value==='string' && value) || run_on===run_off)throw new Error('Báo cáo chưa có mã đối chứng hợp lệ.');
  const result=await client.request('/api/proof/events?comparison_id='+encodeURIComponent(comparison_id));
  if(result?.comparison_id!==comparison_id || result.run_on!==run_on || result.run_off!==run_off ||
     !['on','off'].every(arm=>Number.isInteger(result.cutoffs?.[arm]) && result.cutoffs[arm]>=0 &&
       Array.isArray(result.evidence?.[arm]) && result.evidence[arm].every(event=>event?.run_id===report['run_'+arm] &&
         Number.isInteger(event.seq) && event.seq>0 && event.seq<=result.cutoffs[arm]))){
    throw new Error('Nhật ký không khớp với báo cáo đối chứng đang xem.');
  }
  return result;
}
