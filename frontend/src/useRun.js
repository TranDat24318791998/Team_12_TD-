import {commandTarget,commandFinished,readEvents} from './api.js';
import {useCallback,useEffect,useRef,useState} from 'react';

export function useRun(client,{enabled=true,poll=false}={}){
  const [data,setData]=useState({state:null,events:[],error:null,feedError:null,lastSeq:0});
  const [pending,setPending]=useState(null);
  const [actionError,setActionError]=useState(null);
  const snapshot=useRef(data),alive=useRef(false),controller=useRef(null),flight=useRef(null),mutation=useRef(false);
  const refresh=useCallback(async()=>{
    if(flight.current)return flight.current;
    flight.current=(async()=>{
      const before=snapshot.current;
      const signal=controller.current?.signal;
      // Obtain sid through state before reading events on a new browser session.
      const state=await client.request('/api/state',{signal});
      if(!state || typeof state.run_id!=='string' || !state.demo_shop || !state.demo_shop_original)throw new Error('Dữ liệu /api/state chưa đúng hợp đồng giao diện. Hãy kiểm tra adapter ở backend.');
      const sameRun=before.state?.run_id===state.run_id;
      let events=sameRun?before.events:[],lastSeq=sameRun?before.lastSeq:0,feedError=null;
      try{
        const result=await readEvents(client,state.run_id,lastSeq,signal);
        const known=new Set(events.map(event=>event.seq));
        events=[...events,...result.events.filter(event=>event.run_id===state.run_id && !known.has(event.seq))].sort((a,b)=>a.seq-b.seq);
        lastSeq=result.last_seq;
      }catch(error){if(signal?.aborted)throw error;feedError=error.message;}
      const next={state,events,lastSeq,error:null,feedError};snapshot.current=next;
      if(alive.current)setData(next);
      return state;
    })();
    try{return await flight.current;}
    catch(error){if(alive.current && !controller.current?.signal.aborted)setData(previous=>({...previous,error:error.message}));throw error;}
    finally{flight.current=null;}
  },[client]);
  useEffect(()=>{
    alive.current=true;controller.current=new AbortController();let timer;
    async function tick(){
      // Reads remain active during a POST so long-running agent work stays visible.
      // refresh() still shares one read flight; act() still serializes all writes.
      try{await refresh();}catch{/* Error is retained for retry and the connection status. */}
      finally{if(alive.current && poll)timer=setTimeout(tick,1500);}
    }
    if(enabled)tick();
    return()=>{alive.current=false;clearTimeout(timer);controller.current.abort();};
  },[enabled,poll,refresh]);
  const act=useCallback(async(path,body)=>{
    if(mutation.current)return false;
    mutation.current=true;setPending(path);setActionError(null);
    try{
      if(flight.current)await flight.current;
      const before=snapshot.current.state;
      const target=commandTarget(before,path);
      try{await client.request(path,{method:'POST',target,...(body?{body}:{})});}
      catch(error){
        if(!error.pending)throw error;
        if(path==='/api/day/start' && error.operation_id){
          const state=await refresh();
          if(state.run_id!==before.run_id)throw new Error('Phiên đã thay đổi. Hãy kiểm tra trạng thái.');
          return true;
        }
        // Accepted operations keep controls disabled until their exact target advances.
        const deadline=Date.now()+70000;let advanced=false;
        while(alive.current && Date.now()<deadline){
          await new Promise(resolve=>setTimeout(resolve,1500));
          const state=await refresh();
          if(error.operation_id){
            const envelope=await client.request('/api/v1/runs/'+encodeURIComponent(before.run_id)+'/operations/'+encodeURIComponent(error.operation_id));
            const operation=envelope.data || envelope;
            if(['failed','unknown','timed_out'].includes(operation.status))throw new Error(operation.error_code || 'Thao tác chưa hoàn tất; hãy kiểm tra trạng thái.');
            if(['succeeded','completed'].includes(operation.status)){advanced=true;break;}
          }else if(commandFinished(before,state,path)){advanced=true;break;}
        }
        if(alive.current && !advanced)throw new Error('Máy chủ chưa hoàn tất thao tác. Hãy kiểm tra trạng thái trước khi thử lại.');
      }
      if(alive.current)await refresh();
      return true;
    }catch(error){if(alive.current){setActionError(error.message);if(error.status===409)await refresh().catch(()=>{});}return false;}
    finally{mutation.current=false;if(alive.current)setPending(null);}
  },[client,refresh]);
  return {...data,pending,actionError,clearActionError:()=>setActionError(null),refresh,act};
}
