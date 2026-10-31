import {useEffect,useState} from 'react';
import {Icon} from '../components/Icon.jsx';
import {Empty,ErrorPanel,Loading} from '../components/Shell.jsx';
import {LearningComparison,SimpleAgentFlow} from '../components/LearningComparison.jsx';
import {comparisonDays} from '../proofComparison.js';
import {SIMULATION_DAYS} from '../config.js';
import {dec,download,vnd} from '../format.js';
import {readEvents} from '../api.js';
import {readDemoArtifact,demoEvidence} from '../proofArtifact.js';

const valid=value=>value!=null && Number.isFinite(Number(value));
const format=(value,unit)=>!valid(value)?'Chưa có dữ liệu':['đ','VND'].includes(unit)?vnd(value):dec(value,unit==='%'?1:0)+(unit==='%'?'%':'');
function MetricDetails({report}){
  return <div className="proof-grid">{(report.metrics || []).map(metric=>{
    const scale=metric.unit==='%'?100:Math.max(Math.abs(metric.on || 0),Math.abs(metric.off || 0),1);
    return <section className="card proof-card" key={metric.key}><div className="between"><h2>{metric.label_vi}</h2><span className={'pill '+(metric.better==='higher'?'green':'blue')}>{metric.better==='higher'?'Cao hơn là tốt':'Thấp hơn là tốt'}</span></div>{[['off','Không học từ lịch sử'],['on','Có học từ lịch sử']].map(([key,label])=><div className="bar-row" key={key}><div className="bar-meta"><span>{label}</span><strong>{format(metric[key],metric.unit)}</strong></div><div className="bar-track" role="img" aria-label={label+': '+format(metric[key],metric.unit)}><div className={'bar-fill '+(key==='off'?'off':'')} style={{width:(valid(metric[key])?Math.min(100,Math.abs(metric[key])/scale*100):0)+'%'}}/></div></div>)}</section>;
  })}</div>;
}

export function ProofReport({report,preview,onReset,onExport,onExportReport,manifest,pending,initialDay=2}){
  const days=comparisonDays(report);
  const [selectedDay,setSelectedDay]=useState(initialDay);
  const selected=days.find(row=>row.day===selectedDay) || days[0] || null;
  const horizon=Number.isInteger(report.days)?Math.min(Math.max(report.days,1),SIMULATION_DAYS):SIMULATION_DAYS;
  const sample=preview || ['fixture','reference','reference_offline'].includes(report.source) || report.execution_profile==='reference';
  const precomputed=report.source==='precomputed_offline_simulation';
  return <main id="main-content" className="wrap proof-presentation"><header className="proof-heading"><div><h1>Trợ lý hiểu shop hơn qua từng ngày</h1><p>Cùng yêu cầu, cùng giới hạn. So sánh phản hồi khi không dùng và có dùng dữ liệu quá khứ.</p></div><div className="proof-source-label">{precomputed?<span className="pill orange">Mô phỏng ngoại tuyến đã chạy · Chưa đánh giá provider</span>:sample?<span className="pill orange">{report.sample_source?.kind==='sqlite_sample'?'Đã nạp 7 ngày từ database · Dữ liệu mẫu':'Hội thoại minh họa'}</span>:<span className="pill blue">{days.length?'Hội thoại từ lần chạy đối chứng':'Chưa có hội thoại đối chứng'}</span>}<span><span id="proof-days">{report.days}</span> ngày · Seed <span id="proof-seed">{report.seed}</span></span>{report.days===6 && <span className="pill orange">Báo cáo tương thích 6 ngày</span>}</div></header>
    <div className="proof-day-toolbar"><div className="proof-day-selector" role="group" aria-label="Chọn ngày so sánh"><span>Xem ngày</span>{Array.from({length:horizon},(_,index)=>index+1).map(day=><button type="button" key={day} data-proof-day={day} aria-pressed={selected?.day===day} disabled={!days.some(row=>row.day===day)} onClick={()=>setSelectedDay(day)}>Ngày {day}</button>)}</div><span className="proof-situation">{selected?.situation_vi || 'Chưa có dữ liệu hội thoại đối chứng'}</span></div>
    <SimpleAgentFlow/>
    <LearningComparison day={selected}/>
    <div className="proof-day-insight" role="status"><Icon name="book"/><span>{selected?.takeaway_vi || 'Backend cần cung cấp hội thoại của hai lần chạy cùng kịch bản để hiển thị so sánh.'}</span></div>
    <div className="proof-bottom-row"><p>{precomputed?'Hai lần mô phỏng đã được tính sẵn; chưa chạy đánh giá provider.':sample?'Số liệu minh họa giao diện. Chưa phải kết quả thực nghiệm.':'Dữ liệu từ hai lần chạy đối chứng đã lưu.'} Học qua bộ nhớ, model không được huấn luyện lại.</p><div className="proof-actions"><button className="button outline" data-export-report onClick={onExportReport || (()=>download('proof.json',JSON.stringify(report,null,2)))}><Icon name="download"/>Báo cáo</button><button className="button outline" data-export-log onClick={onExport} disabled={pending}><Icon name="book"/>Nhật ký</button><button className="button" data-restart onClick={onReset} disabled={pending}><Icon name="refresh"/>{precomputed?'Bắt đầu phiên demo mới':'Chạy lại từ đầu'}</button></div></div>
    <details className="proof-report-details"><summary>Chi tiết chỉ số và nguồn dữ liệu <Icon name="chevron"/></summary><div id="proof-content"><MetricDetails report={report}/>{!report.metrics?.length && <Empty title="Chưa có kết quả đối chứng.">Nhóm backend cần cung cấp ProofReport từ lần chạy cùng seed.</Empty>}<p className="proof-note">{report.note_vi}</p><p className="tiny muted">{preview?'Mã bản mẫu':'Mã lần chạy'}: {report.run_on} / {report.run_off}</p>{manifest && <p className="tiny muted">Mã đối chứng: {manifest.comparison_id} · Kiểm tra provider: {manifest.provider_eval} · SHA-256: {manifest.artifact_sha256}</p>}</div></details>
  </main>;
}
export function ProofPage({client,onReset,onNotice,pending}){
  const [source,setSource]=useState('current'),[payload,setPayload]=useState(null),[error,setError]=useState(null),[attempt,setAttempt]=useState(0);
  useEffect(()=>{const controller=new AbortController(),signal=controller.signal,path=source==='demo'?'/api/proof/demo':'/api/proof';setPayload(null);setError(null);(async()=>{let result;try{result=await client.request(path,{signal});}catch(error){if(error.status!==401 || client.preview)throw error;await client.request('/api/state',{signal});result=await client.request(path,{signal});}if(!signal.aborted){if(source==='demo')setPayload(readDemoArtifact(result));else{if(['not_ready','pending'].includes(result.status))throw new Error(result.reason_vi || 'Báo cáo đối chứng chưa sẵn sàng.');setPayload({report:result});}}})().catch(error=>{if(!signal.aborted)setError(error.message);});return()=>controller.abort();},[client,source,attempt]);
  async function exportEvents(){try{if(source==='demo'){download('evidence-demo.json',JSON.stringify(demoEvidence(payload),null,2));return;}const state=await client.request('/api/state');const data=await readEvents(client,state.run_id);download('events.json',JSON.stringify(data.events,null,2));}catch(error){onNotice(error.message);}}
  function exportReport(){download(source==='demo'?'proof-demo.json':'proof.json',JSON.stringify(source==='demo'?payload:payload.report,null,2));}
  function selectSource(next){if(next!==source){setPayload(null);setError(null);setSource(next);}}
  const requestedDay=Number(new URLSearchParams(globalThis.location?.search || '').get('day'));
  const initialDay=Number.isInteger(requestedDay) && requestedDay>=1 && requestedDay<=SIMULATION_DAYS?requestedDay:2;
  return <><div className="wrap pad" role="group" aria-label="Nguồn báo cáo"><button className="button outline" type="button" aria-pressed={source==='current'} onClick={()=>selectSource('current')}>Phiên hiện tại</button> <button className="button outline" type="button" aria-pressed={source==='demo'} onClick={()=>selectSource('demo')}>Báo cáo mô phỏng đã chạy</button></div>{error?<main id="main-content" className="wrap pad"><ErrorPanel message={error} showPreview={source!=='demo'} onRetry={()=>setAttempt(value=>value+1)}/></main>:payload?<ProofReport key={source} report={payload.report} manifest={payload.manifest} preview={client.preview && source==='current'} initialDay={initialDay} onReset={onReset} onExport={exportEvents} onExportReport={exportReport} pending={!!pending}/>:<main id="main-content" className="wrap"><Loading text="Đang tải kết quả đối chứng…"/></main>}</>;
}
