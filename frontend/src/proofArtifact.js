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
