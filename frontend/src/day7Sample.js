import {SIMULATION_DAYS} from './config.js';

// This endpoint reads a public presentation fixture from the local SQLite store.
// It never starts agents, approves a live card, or substitutes for API-mode data.
export async function loadDay7Sample(fetchImpl,signal){
  const controller=new AbortController(),abort=()=>controller.abort();
  if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
  const timeout=setTimeout(abort,15000);
  try{
  const response=await fetchImpl('/api/demo/day7',{signal:controller.signal,cache:'no-store',credentials:'same-origin',headers:{Accept:'application/json'}});
  let sample;
  try{sample=await response.json();}catch{throw new Error('Chưa kết nối database mẫu. Hãy chạy scripts/preview_server.py rồi thử lại.');}
  if(!response.ok)throw new Error(sample?.error?.message_vi || 'Chưa tải được dữ liệu ngày 7 từ database.');
  if(sample?.schema_version!==1 || sample.source?.kind!=='sqlite_sample' || sample.state?.day!==SIMULATION_DAYS || sample.state?.step!=='complete' || sample.proof?.days!==SIMULATION_DAYS || !Array.isArray(sample.events) || !sample.state.demo_shop || !sample.state.demo_shop_original)throw new Error('Bộ dữ liệu mẫu ngày 7 chưa đúng định dạng.');
  const nights=new Set(sample.events.filter(event=>event.run_id===sample.state.run_id && event.type==='night_summary').map(event=>event.day));
  if(nights.size!==SIMULATION_DAYS || !Array.from({length:SIMULATION_DAYS},(_,i)=>i+1).every(day=>nights.has(day)))throw new Error('Database chưa có đủ tổng kết của 7 ngày.');
  return sample;
  }catch(error){
    if(error.name==='AbortError' && !signal?.aborted)throw new Error('Database phản hồi chậm. Phiên hiện tại được giữ nguyên, bạn có thể thử lại.');
    if(error instanceof TypeError)throw new Error('Không kết nối được database mẫu. Hãy kiểm tra máy chủ rồi thử lại.');
    throw error;
  }finally{clearTimeout(timeout);signal?.removeEventListener('abort',abort);}
}
