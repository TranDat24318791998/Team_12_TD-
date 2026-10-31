// Browser regression: real React effects, a delayed write, and a fake local API.
import {createRoot} from 'react-dom/client';
import {useRun} from '../src/useRun.js';

const output=document.getElementById('hook-result');
const mount=document.getElementById('hook-root');
const button=document.getElementById('hook-run');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const waitFor=async condition=>{const end=Date.now()+6500;while(Date.now()<end){if(condition())return;await pause(40);}throw new Error('Hết thời gian chờ React cập nhật');};

button.addEventListener('click',async()=>{
  button.disabled=true;output.textContent='Đang kiểm tra polling khi POST chưa trả về…';
  const shop={shop_id:'D',name:'Shop kiểm thử',images:[]};
  let state={run_id:'hook-run',day:1,step:'awaiting_decision',demo_shop:shop,demo_shop_original:shop,pending_card:{card_id:'c-1'}};
  let eventList=[],postCalls=0,readCalls=0,activeReads=0,maxReads=0,observed,release;
  const client={async request(path,options={}){
    if(options.method==='POST'){
      postCalls++;
      return new Promise(resolve=>{release=()=>resolve({step:'negotiating'});});
    }
    readCalls++;activeReads++;maxReads=Math.max(maxReads,activeReads);
    await pause(25);activeReads--;
    if(path==='/api/state')return structuredClone(state);
    const after=Number(new URL(path,'http://test.local').searchParams.get('after') || 0);
    return {events:structuredClone(eventList.filter(event=>event.seq>after)),last_seq:eventList.length?4:0};
  }};
  function Probe(){observed=useRun(client,{poll:true});return <p>{observed.state?.step || 'Đang tải'} · {observed.events.length} sự kiện · {observed.pending || 'không có lệnh'}</p>;}
  const root=createRoot(mount);
  try{
    root.render(<Probe/>);await waitFor(()=>observed?.state);
    const command=observed.act('/api/decision',{card_id:'c-1',action:'negotiate'});
    await waitFor(()=>postCalls===1);
    state={...state,step:'negotiating',pending_card:null};
    eventList=[{seq:3,run_id:'hook-run',day:1,shop_id:'D',type:'agent_activity',actor:'shop_agent',text_vi:'Agent shop đang xử lý',data:{negotiation_id:'attempt-2',round:1,task_id:'t',phase:'response',status:'running',label_vi:'Đang xử lý'}}];
    await waitFor(()=>observed.state.step==='negotiating' && observed.events.length===1);
    if(!observed.pending)throw new Error('POST phải còn pending trong lúc state/events đã cập nhật');
    if(await observed.act('/api/decision',{card_id:'c-1',action:'negotiate'})!==false || postCalls!==1)throw new Error('Hai write bị chạy chồng');
    await observed.refresh();
    if(observed.events.length!==1 || maxReads!==1)throw new Error('Polling đọc chồng hoặc nhân đôi sự kiện');
    release();await command;await waitFor(()=>!observed.pending);
    root.unmount();await pause(100);const afterUnmount=readCalls;await pause(1700);
    if(readCalls!==afterUnmount)throw new Error('Polling vẫn chạy sau unmount');
    output.textContent='PASS: state/events cập nhật khi POST còn pending; write không chồng; read không chồng; event không lặp; polling dừng khi unmount.';
    output.dataset.result='pass';
  }catch(error){root.unmount();release?.();output.textContent='FAIL: '+error.message;output.dataset.result='fail';}
  finally{button.disabled=false;}
});
