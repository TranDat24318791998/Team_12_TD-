import {useEffect,useState} from 'react';
import {Icon} from '../components/Icon.jsx';
import {Empty,ErrorPanel,Loading} from '../components/Shell.jsx';
import {LearningComparison,SimpleAgentFlow} from '../components/LearningComparison.jsx';
import {comparisonDays} from '../proofComparison.js';
import {SIMULATION_DAYS} from '../config.js';
import {dec,download,vnd} from '../format.js';

const valid=value=>value!=null && Number.isFinite(Number(value));
const format=(value,unit)=>!valid(value)?'Chưa có dữ liệu':['đ','VND'].includes(unit)?vnd(value):dec(value,unit==='%'?1:0)+(unit==='%'?'%':'');
function MetricDetails({report}){
  return <div className="proof-grid">{(report.metrics || []).map(metric=>{
    const scale=metric.unit==='%'?100:Math.max(Math.abs(metric.on || 0),Math.abs(metric.off || 0),1);
    return <section className="card proof-card" key={metric.key}><div className="between"><h2>{metric.label_vi}</h2><span className={'pill '+(metric.better==='higher'?'green':'blue')}>{metric.better==='higher'?'Cao hơn là tốt':'Thấp hơn là tốt'}</span></div>{[['off','Không học từ lịch sử'],['on','Có học từ lịch sử']].map(([key,label])=><div className="bar-row" key={key}><div className="bar-meta"><span>{label}</span><strong>{format(metric[key],metric.unit)}</strong></div><div className="bar-track" role="img" aria-label={label+': '+format(metric[key],metric.unit)}><div className={'bar-fill '+(key==='off'?'off':'')} style={{width:(valid(metric[key])?Math.min(100,Math.abs(metric[key])/scale*100):0)+'%'}}/></div></div>)}</section>;
  })}</div>;
}

export function ProofReport({report,preview,onReset,onExport,pending}){
  const days=comparisonDays(report);
  const [selectedDay,setSelectedDay]=useState(2);
  const selected=days.find(row=>row.day===selectedDay) || days[0] || null;
  const horizon=Number.isInteger(report.days)?Math.min(Math.max(report.days,1),SIMULATION_DAYS):SIMULATION_DAYS;
  return <main id="main-content" className="wrap proof-presentation"><header className="proof-heading"><div><div className="eyebrow">HỌC QUA BỘ NHỚ</div><h1>Trợ lý hiểu shop hơn qua từng ngày</h1><p>Cùng yêu cầu, cùng giới hạn. Xem cách phản hồi khi không dùng và có dùng dữ liệu quá khứ.</p></div><div className="proof-source-label">{preview?<span className="pill orange">Hội thoại minh họa</span>:<span className="pill blue">Hội thoại từ lần chạy đối chứng</span>}<span><span id="proof-days">{report.days}</span> ngày · Seed <span id="proof-seed">{report.seed}</span></span>{report.days===6 && <span className="pill orange">Báo cáo tương thích 6 ngày</span>}</div></header>
    <div className="proof-day-toolbar"><div className="proof-day-selector" role="group" aria-label="Chọn ngày so sánh"><span>Xem ngày</span>{Array.from({length:horizon},(_,index)=>index+1).map(day=><button type="button" key={day} data-proof-day={day} aria-pressed={selected?.day===day} disabled={!days.some(row=>row.day===day)} onClick={()=>setSelectedDay(day)}>Ngày {day}</button>)}</div><span className="proof-situation">{selected?.situation_vi || 'Chưa có dữ liệu hội thoại đối chứng'}</span></div>
    <SimpleAgentFlow/>
    <LearningComparison day={selected}/>
    <div className="proof-day-insight" role="status"><Icon name="book"/><span>{selected?.takeaway_vi || 'Backend cần cung cấp hội thoại của hai lần chạy cùng kịch bản để hiển thị so sánh.'}</span></div>
    <div className="proof-metric-strip" aria-label="Chỉ số toàn phiên đối chứng"><div className="metric-strip-label"><strong>Kết quả {report.days} ngày</strong><span>Không học / Có học</span></div>{(report.metrics || []).map(metric=><div className="proof-mini-metric" key={metric.key}><span>{metric.label_vi}</span><p><span>{format(metric.off,metric.unit)}</span><span className="metric-divider">/</span><strong>{format(metric.on,metric.unit)}</strong></p></div>)}</div>
    <div className="proof-bottom-row"><p>{preview?'Số liệu minh họa giao diện. Chưa phải kết quả thực nghiệm.':'Dữ liệu từ hai lần chạy đối chứng đã lưu.'} Học qua bộ nhớ, model không được huấn luyện lại.</p><div className="proof-actions"><button className="button outline" data-export-report onClick={()=>download('proof.json',JSON.stringify(report,null,2))}><Icon name="download"/>Báo cáo</button><button className="button outline" data-export-log onClick={onExport} disabled={pending}><Icon name="book"/>Nhật ký</button><button className="button" data-restart onClick={onReset} disabled={pending}><Icon name="refresh"/>Chạy lại từ đầu</button></div></div>
    <details className="proof-report-details"><summary>Chi tiết chỉ số và nguồn dữ liệu <Icon name="chevron"/></summary><div id="proof-content"><MetricDetails report={report}/>{!report.metrics?.length && <Empty title="Chưa có kết quả đối chứng.">Nhóm backend cần cung cấp ProofReport từ lần chạy cùng seed.</Empty>}<p className="proof-note">{report.note_vi}</p><p className="tiny muted">{preview?'Mã bản mẫu':'Mã lần chạy'}: {report.run_on} / {report.run_off}</p></div></details>
  </main>;
}
export function ProofPage({client,onReset,onNotice,pending}){
  const [report,setReport]=useState(null),[error,setError]=useState(null),[attempt,setAttempt]=useState(0);
  useEffect(()=>{const controller=new AbortController();client.request('/api/proof',{signal:controller.signal}).then(result=>{if(!controller.signal.aborted){setReport(result);setError(null);}}).catch(error=>{if(!controller.signal.aborted)setError(error.message);});return()=>controller.abort();},[client,attempt]);
  async function exportEvents(){try{const data=await client.request('/api/events?after=0');download('events.json',JSON.stringify(data.events,null,2));}catch(error){onNotice(error.message);}}
  if(error)return <main id="main-content" className="wrap pad"><ErrorPanel message={error} onRetry={()=>setAttempt(value=>value+1)}/></main>;
  return report?<ProofReport report={report} preview={client.preview} onReset={onReset} onExport={exportEvents} pending={!!pending}/>:<main id="main-content" className="wrap"><Loading text="Đang tải kết quả đối chứng…"/></main>;
}
