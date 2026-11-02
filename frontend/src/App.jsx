import {useEffect,useState} from 'react';
import {Shell,Loading,ErrorPanel,ResetDialog} from './components/Shell.jsx';
import {ShopPage} from './pages/Shop.jsx';
import {DemoPage} from './pages/Demo.jsx';
import {NightPage} from './pages/Night.jsx';
import {ProofPage} from './pages/Proof.jsx';
import {pageURL} from './format.js';
import {useRun} from './useRun.js';
import {waitingForNegotiation} from './activity.js';

const pages=new Set(['index.html','demo.html','updated.html','night.html','proof.html']);
export function resolvePage(location=globalThis.location,body=globalThis.document?.body){
  const segment=(location?.pathname || '').split('/').filter(Boolean).at(-1) || '';
  const normalized=segment.endsWith('.html')?segment:`${segment}.html`;
  if(pages.has(normalized))return normalized;
  const bodyPage=body?.dataset?.page;
  return pages.has(bodyPage)?bodyPage:'index.html';
}

export function App({client,page=resolvePage()}){
  const demo=page==='demo.html',proof=page==='proof.html';
  const run=useRun(client,{enabled:!proof,poll:true});
  const busy=run.pending || run.state?.busy;
  const [reset,setReset]=useState(false),[notice,setNotice]=useState(''),[cart,setCart]=useState(0);
  const navigate=name=>{globalThis.location.href=pageURL(name,client.preview);};
  useEffect(()=>{document.body.classList.toggle('demo-page',demo);document.body.classList.toggle('proof-page',proof);},[demo,proof]);
  useEffect(()=>{if(proof)document.title='Học qua bộ nhớ · Growth Agents';},[proof]);
  useEffect(()=>{if(run.state?.demo_shop)document.title=run.state.demo_shop.name+' · ShopPilot AI';},[run.state?.demo_shop?.name]);
  useEffect(()=>{if(!notice)return;const timer=setTimeout(()=>setNotice(''),5500);return()=>clearTimeout(timer);},[notice]);
  async function endDay(){if(run.state?.step==='day_done' && !waitingForNegotiation(run.state,run.events) && await run.act('/api/night',{expected_day:run.state.day}))navigate('night.html');}
  async function jumpToDay7(){
    if(await run.act('/api/demo/jump-day7'))navigate('proof.html?day=7');
  }
  let view;
  if(proof)view=<ProofPage client={client} onReset={()=>setReset(true)} onNotice={setNotice} pending={run.pending}/>;
  else if(!run.state)view=<main id="main-content" className="wrap pad">{run.error?<ErrorPanel message={run.error} onRetry={()=>run.refresh().catch(()=>{})}/>:<Loading/>}</main>;
  else if(demo)view=<DemoPage run={run} preview={client.preview} navigate={navigate} onEndDay={endDay} onNotice={setNotice}/>;
  else if(page==='night.html')view=<NightPage run={run} preview={client.preview}/>;
  else view=<ShopPage run={run} preview={client.preview} updated={page==='updated.html'} onReset={()=>setReset(true)} onEndDay={endDay} onNotice={setNotice} onAddCart={count=>{setCart(value=>value+count);setNotice('Đã thêm vào giỏ hàng mô phỏng.');}} navigate={navigate}/>;
  return <><Shell preview={client.preview} state={run.state} events={run.events} compact={demo || proof} comparison={proof} pending={busy} onEndDay={endDay} onJumpToDay7={jumpToDay7} onNotice={setNotice} cart={cart}>{view}</Shell><ResetDialog open={reset} onClose={()=>setReset(false)} onReset={async memory=>{if(await run.act('/api/reset',{memory,seed:42}))navigate('index.html');}} pending={!!busy} error={run.actionError}/>{(notice || run.actionError) && <div className={'toast '+(run.actionError?'error':'')} role={run.actionError?'alert':'status'}>{run.actionError || notice}{run.actionError && <button className="icon-button" aria-label="Đóng thông báo" onClick={run.clearActionError}>×</button>}</div>}</>;
}
