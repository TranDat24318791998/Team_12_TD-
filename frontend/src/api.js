import {createPreviewAPI} from './preview.js';
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
  if(path==='/api/decision')return JSON.stringify([...base,state.pending_card?.card_id]);
  if(path.startsWith('/api/content/'))return JSON.stringify([...base,state.content_draft?.version,state.step]);
  return JSON.stringify([...base,state.step,state.last_night?.day]);
}
export function commandFinished(before,after,path){
  if(path==='/api/night')return after.step==='complete' || after.day!==before.day || (after.step==='night_done' && after.last_night?.day===before.day);
  return commandTarget(before,path)!==commandTarget(after,path);
}
export function createClient({preview=false,fetchImpl=globalThis.fetch,storage=globalThis.sessionStorage,now=Date.now,assetRoot}={}){
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
      const response=await fetchImpl(path,{credentials:'same-origin',...options,signal:controller.signal,headers,...(body?{body:JSON.stringify(body)}:{})});
      let result;try{result=await response.json();}catch{throw new Error('Máy chủ chưa trả JSON hợp lệ. Hãy kiểm tra API hoặc mở bản xem trước.');}
      const inProgress=mutating && (response.status===202 || result?.error?.code==='COMMAND_IN_PROGRESS');
      if(mutating && !inProgress && response.status<500 && response.status!==429)intents.delete(fingerprint);
      if(inProgress){const error=new Error('Thao tác đang được máy chủ xử lý. Đang chờ trạng thái mới…');error.pending=true;error.code='COMMAND_IN_PROGRESS';throw error;}
      if(!response.ok || result?.error){const error=new Error(result?.error?.message_vi || result?.error?.message || `Yêu cầu chưa thành công (HTTP ${response.status}).`);error.code=result?.error?.code;error.status=response.status;throw error;}
      return result;
    }catch(error){if(error.name==='AbortError' && !signal?.aborted)throw new Error('Máy chủ phản hồi chậm. Hãy kiểm tra trạng thái trước khi thử lại.');throw error;}
    finally{clearTimeout(timeout);signal?.removeEventListener('abort',abort);}
  }
  return {preview,request};
}
