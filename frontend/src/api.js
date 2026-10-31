import {createPreviewAPI} from './preview.js';
import {configuredApiBase,resolveApiPath} from './runtime.js';
export function selectPreview(location,storage){
  const query=new URLSearchParams(location.search).get('preview');
  let saved=null;try{saved=storage?.getItem('growth-agents.source');}catch{}
  const preview=query!==null?query==='1':location.protocol==='file:' || saved==='preview';
  try{if(query!==null)storage?.setItem('growth-agents.source',preview?'preview':'api');}catch{}
  return preview;
}
const newKey=()=>globalThis.crypto.randomUUID?.() || Array.from(globalThis.crypto.getRandomValues(new Uint32Array(4)),value=>value.toString(16)).join('-');
export function commandTarget(state,path){
  if(!state)return 'bootstrap';
  const base=[state.run_id,state.day];
  if(path==='/api/reset')return state.run_id;
  if(path==='/api/decision')return JSON.stringify([...base,state.pending_card?.card_id,state.pending_card?.version,state.pending_card?.brief_version]);
  if(path.startsWith('/api/content/')){const d=state.content_draft;return JSON.stringify([...base,d?.card_id,d?.brief_version,d?.version,d?.job_id,d?.content_id,...(['/api/content/image','/api/content/video'].includes(path)?[d?.wizard?.stage]:[])]);}
  return JSON.stringify([...base,state.step,state.last_night?.day]);
}
export function commandFinished(before,after,path){
  if(path==='/api/night')return after.step==='complete' || after.day!==before.day || (after.step==='night_done' && after.last_night?.day===before.day);
  return commandTarget(before,path)!==commandTarget(after,path);
}
export function createClient({preview=false,fetchImpl=globalThis.fetch,storage=globalThis.sessionStorage,now=Date.now,assetRoot,apiBase=configuredApiBase()}={}){
  const sample=preview?createPreviewAPI({storage,now,assetRoot,fetchImpl}):null;
  const intents=new Map();
  async function request(path,{body,signal,target='',...options}={}){
    const method=(options.method || 'GET').toUpperCase();
    const mutating=!['GET','HEAD'].includes(method);
    const fingerprint=method+':'+path+':'+target;
    const serialized=JSON.stringify(body??null);
    let intent;
    if(mutating){
      intent=intents.get(fingerprint);
      if(intent && intent.body!==serialized)throw new Error('Thao tác trước chưa rõ kết quả. Hãy tải lại trạng thái trước khi gửi nội dung khác.');
      if(!intent){intent={key:newKey(),body:serialized};intents.set(fingerprint,intent);}
    }
    const headers={Accept:'application/json',...(body?{'Content-Type':'application/json'}:{}),...options.headers,...(mutating?{'Idempotency-Key':intent.key,'X-Request-ID':newKey()}:{})};
    if(sample){try{const result=await sample.request(path,{...options,headers,body,signal});if(mutating)intents.delete(fingerprint);return result;}catch(error){if(mutating)intents.delete(fingerprint);throw error;}}
    const controller=new AbortController();const abort=()=>controller.abort();
    if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
    const timeout=setTimeout(abort,path==='/api/night'?70000:20000);
    try{
      const requestPath=resolveApiPath(path,apiBase);
      const response=await fetchImpl(requestPath,{credentials:requestPath===path?'same-origin':'include',...options,signal:controller.signal,headers,...(body?{body:JSON.stringify(body)}:{})});
      let result;try{result=await response.json();}catch{throw new Error('Máy chủ chưa trả JSON hợp lệ. Hãy kiểm tra API hoặc mở bản xem trước.');}
      const inProgress=mutating && (response.status===202 || result?.error?.code==='COMMAND_IN_PROGRESS');
      if(mutating && !inProgress && response.status<500 && response.status!==429)intents.delete(fingerprint);
      if(inProgress){const error=new Error('Thao tác đang được máy chủ xử lý. Đang chờ trạng thái mới…');error.pending=true;error.code='COMMAND_IN_PROGRESS';error.operation_id=result?.operation_id;error.operation_status=result?.status;throw error;}
      if(!response.ok || result?.error){const error=new Error(result?.error?.message_vi || result?.error?.message || `Yêu cầu chưa thành công (HTTP ${response.status}).`);error.code=result?.error?.code;error.status=response.status;throw error;}
      return result;
    }catch(error){if(error.name==='AbortError' && !signal?.aborted)throw new Error('Máy chủ phản hồi chậm. Hãy kiểm tra trạng thái trước khi thử lại.');throw error;}
    finally{clearTimeout(timeout);signal?.removeEventListener('abort',abort);}
  }
  return {preview,request};
}

export async function readEvents(client,runId,after=0,signal){
  let cursor=after,events=[];
  while(true){
    const result=await client.request('/api/events?after='+cursor+'&run_id='+encodeURIComponent(runId),{signal});
    if(result.run_id && result.run_id!==runId)throw new Error('Phiên đã thay đổi. Hãy tải lại trạng thái.');
    if(!Number.isInteger(result.last_seq) || result.last_seq<cursor)throw new Error('Con trỏ sự kiện không hợp lệ.');
    events.push(...result.events.filter(event=>event.run_id===runId));
    if(!result.has_more)return {events,last_seq:result.last_seq};
    if(result.last_seq===cursor)throw new Error('Con trỏ sự kiện không tiến.');
    cursor=result.last_seq;
  }
}
