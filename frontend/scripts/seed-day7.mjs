import {mkdir,writeFile} from 'node:fs/promises';
import {createPreviewAPI} from '../src/preview.js';

// Prepare a complete illustrative session once; the button only reads SQLite.
const entries=new Map();
const storage={getItem:key=>entries.get(key)??null,setItem:(key,value)=>entries.set(key,value)};
let clock=0;
const api=createPreviewAPI({storage,now:()=>clock,makeRunId:()=> 'sample-day7',assetRoot:new URL('https://sample.invalid/img/')});
const command=(path,body)=>api.request(path,{method:'POST',body});
for(let day=1;day<=7;day++){
  await command('/api/day/start');clock+=6000;
  let state=await api.request('/api/state');
  if(state.step==='awaiting_decision'){
    if(day===1){
      await command('/api/decision',{card_id:state.pending_card.card_id,action:'negotiate',note_vi:'Giảm voucher còn 2% giúp chị.'});clock+=3000;
      state=await api.request('/api/state');
    }
    await command('/api/decision',{card_id:state.pending_card.card_id,action:'accept',rule_answer:state.pending_card.rule_question?true:null});
  }
  state=await api.request('/api/state');
  if(state.step==='content_review'){
    if(day===1)await command('/api/content/retry',{feedback_vi:'Nền sáng, ít chữ; giữ đúng màu quạt.'});
    clock+=4000;await command('/api/content/apply',{cover_option:'B'});
  }
  await command('/api/night');
}
const sample={schema_version:1,source:{kind:'sqlite_sample',label_vi:'Dữ liệu mẫu 7 ngày từ database',seed:42},state:await api.request('/api/state'),events:(await api.request('/api/events?after=0')).events,proof:await api.request('/api/proof')};
sample.proof.sample_source=sample.source;
sample.proof.note_vi='Bộ dữ liệu minh họa 7 ngày được lưu và nạp từ SQLite. Hội thoại và chỉ số là dữ liệu mẫu cho trình chiếu, chưa phải kết quả thực nghiệm của agent.';
for(const event of sample.events)event.ts=String(8+Math.floor((event.seq%30)/6)).padStart(2,'0')+':'+String((event.seq%6)*10).padStart(2,'0');
const json=JSON.stringify(sample,null,2).replaceAll('https://sample.invalid/','/');
await mkdir(new URL('../fixtures/',import.meta.url),{recursive:true});
await writeFile(new URL('../fixtures/day7.json',import.meta.url),json+'\n');
console.log(`Prepared ${sample.events.length} events across 7 days for the SQLite presentation fixture.`);
