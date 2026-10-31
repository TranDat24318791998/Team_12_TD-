(async()=>{
  'use strict';
  const A=window.App;A.initShell();const target=A.$('#shop-content');
  try{
    const state=await A.api('/api/state');
    target.innerHTML=`<div>${A.product(state.demo_shop)}</div><aside class="sidebar">${A.control(state)}<div id="insights">${A.insight(state)}</div></aside>`;
    A.bindProduct(state.demo_shop);A.bindControl(state);
    try{const {events}=await A.api('/api/events?after=0');A.$('#insights').innerHTML=A.insight(state,events);}catch{/* Listing remains usable when the optional signal feed is unavailable. */}
  }catch(error){A.errorBlock(target,error);}
})();
