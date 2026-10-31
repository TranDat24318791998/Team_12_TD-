(async()=>{
  'use strict';
  const A=window.App;A.initShell();const target=A.$('#shop-content');
  try{
    const state=await A.api('/api/state');const changes=A.changedFields(state.demo_shop,state.demo_shop_original);let old=false;
    A.$('#update-label').textContent=changes.length?`Đã áp dụng ${changes.length} thay đổi do trợ lý đề xuất, chủ shop đã duyệt.`:'Chưa có thay đổi được áp dụng trong phiên này.';
    function render(){const shop=old?state.demo_shop_original:state.demo_shop;target.innerHTML=`<div>${A.product(shop,old?null:state.demo_shop_original)}</div><aside class="sidebar">${A.control(state,{updated:true,changes})}</aside>`;A.bindProduct(shop);A.bindControl(state);}
    render();A.$('[data-toggle-original]').onclick=e=>{old=!old;e.currentTarget.textContent=old?'Xem bản hiện tại':'Xem bản cũ';e.currentTarget.setAttribute('aria-pressed',old);render();};
  }catch(error){A.errorBlock(target,error);}
})();
