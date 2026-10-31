(() => {
  'use strict';
  const staticRoot=new URL('../',document.currentScript.src);
  const query=new URLSearchParams(location.search);
  const requested=query.get('preview');
  let stored=null;try{stored=sessionStorage.getItem('growth-agents.source');}catch{}
  const preview=requested!==null?requested==='1':(location.protocol==='file:' || stored==='preview');
  try{if(requested!==null)sessionStorage.setItem('growth-agents.source',preview?'preview':'api');}catch{}
  const $=(selector,scope=document)=>scope.querySelector(selector);
  const $$=(selector,scope=document)=>[...scope.querySelectorAll(selector)];
  const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const vnd=value=>value===null || value===undefined || !Number.isFinite(Number(value))?'—':new Intl.NumberFormat('vi-VN',{maximumFractionDigits:0}).format(value)+'đ';
  const dec=(value,digits=1)=>value===null || value===undefined || !Number.isFinite(Number(value))?'—':new Intl.NumberFormat('vi-VN',{minimumFractionDigits:digits,maximumFractionDigits:digits}).format(value);
  const asset=path=>new URL(path,staticRoot).href;
  function safeUrl(value) {
    if(!value)return '';
    try{const url=new URL(value,location.href);return ['http:','https:'].includes(url.protocol) || (location.protocol==='file:' && url.protocol==='file:')?url.href:'';}catch{return '';}
  }
  function mediaUrl(value){if(!value)return ''; if(/^(media|assets|static)\//.test(value) && location.protocol!=='file:')value='/'+value;return safeUrl(value);}
  const pageUrl=(name='index.html')=>{const url=new URL(name,staticRoot);url.searchParams.set('preview',preview?'1':'0');return url.href;};
  const paths={bag:'M5 8h20l2 24H3L5 8Zm5 0V6a5 5 0 0 1 10 0v2',search:'m15 15 5 5M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z',cart:'M2 3h3l3 12h10l3-9H6m3 13h.01M18 19h.01',arrow:'M4 12h16m-6-6 6 6-6 6',chevron:'m9 5 7 7-7 7',spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Zm7-1v4m-2-2h4',trend:'m3 17 6-6 4 4 8-10m-6 0h6v6',shield:'m12 2 8 3v6c0 5-8 10-8 10S4 16 4 11V5l8-3Zm-4 9 3 3 5-5',video:'M3 5h13v14H3V5Zm13 5 5-4v12l-5-4',image:'M3 3h18v18H3V3Zm0 13 5-5 4 4 3-3 6 6M8 7h.01',message:'M21 4H3v13h5l4 4v-4h9V4Z',check:'m4 12 5 5L20 6',close:'m6 6 12 12M6 18 18 6',refresh:'M20 7a9 9 0 1 0 1 8m-1-13v5h-5',lock:'M6 10h12v11H6V10Zm3 0V6a3 3 0 0 1 6 0v4',moon:'M20 15A9 9 0 0 1 9 3a9 9 0 1 0 11 12Z',chart:'M4 3v18h17M8 16v-5m5 5V6m5 10V9',book:'M3 4h7l2 2 2-2h7v16h-7l-2 2-2-2H3V4Zm9 2v16',clock:'M12 7v5l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',download:'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',user:'M17 7a5 5 0 1 1-10 0 5 5 0 0 1 10 0ZM3 22v-2a9 9 0 0 1 18 0v2',heart:'M12 21 3 12a6 6 0 0 1 9-8 6 6 0 0 1 9 8l-9 9Z',megaphone:'m3 9 17-6v18L3 15V9Zm4 7v5h4v-4',voucher:'M3 4h18v5a3 3 0 0 0 0 6v5H3v-5a3 3 0 0 0 0-6V4Zm9 3v10',info:'M12 11v6m0-10h.01m9 5a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z'};
  const icon=(name,extra='')=>`<svg class="icon ${escapeHtml(extra)}" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.info}"></path></svg>`;
  const logo=()=>`<a class="brand" href="${pageUrl()}" aria-label="sàn demo, trang shop"><svg class="bag" viewBox="0 0 30 36" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M5 10h20l2 23H3L5 10ZM10 10V7a5 5 0 0 1 10 0v3"/><path d="M19 16c-5-4-10 2-5 5s3 8-3 5" stroke-width="2" stroke-linecap="round"/></svg><span>sàn<span>·demo</span></span></a>`;
  const actors={platform_agent:'AGENT SÀN',shop_agent:'AGENT SHOP',seller:'NGƯỜI BÁN',code:'CODE KIỂM TRA',memory:'BỘ NHỚ',content_agent:'AGENT NỘI DUNG',system:'HỆ THỐNG',market:'THỊ TRƯỜNG'};
  const actorLabel=actor=>`<span class="actor ${Object.hasOwn(actors,actor)?escapeHtml(actor):'system'}">${escapeHtml(actors[actor] || actor)}</span>`;
  const modeLabel=mode=>({replay:'Phát lại bản chạy thật',live:'Trực tiếp',offline:'Luật cố định'}[mode] || 'Chưa xác định');
  async function api(path,options={}) {
    if(preview)return window.PreviewAPI.request(path,options);
    const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),path==='/api/night'?70000:20000);
    const config={credentials:'same-origin',...options,signal:controller.signal,headers:{Accept:'application/json',...options.headers}};
    if(config.body && typeof config.body!=='string'){config.body=JSON.stringify(config.body);config.headers['Content-Type']='application/json';}
    try{
      const response=await fetch(path,config);let result;
      try{result=await response.json();}catch{throw new Error('Máy chủ chưa trả JSON hợp lệ. Hãy kiểm tra API hoặc mở bản xem trước.');}
      if(!response.ok || result.error)throw new Error(result.error?.message_vi || `Yêu cầu chưa thành công (HTTP ${response.status}).`);
      return result;
    }catch(error){if(error.name==='AbortError')throw new Error('Máy chủ phản hồi chậm. Hãy kiểm tra trạng thái trước khi thử lại.');throw error;}
    finally{clearTimeout(timeout);}
  }
  function toast(message,error=false){let el=$('#toast');if(!el){el=document.createElement('div');el.id='toast';el.setAttribute('role','status');document.body.append(el);}el.className='toast'+(error?' error':'');el.textContent=message;el.hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>{el.hidden=true;},5500);}
  async function busy(button,task){if(button?.disabled)return;if(button)button.disabled=true;try{return await task();}catch(error){toast(error.message,true);}finally{if(button?.isConnected)button.disabled=false;}}
  function errorBlock(target,error){target.innerHTML=`<div class="error-box"><p>${escapeHtml(error.message)}</p><button class="button secondary" data-reload>Thử tải lại</button> <a class="button quiet" href="${new URL('?preview=1',location.href).href}">Mở bản xem trước</a></div>`;target.querySelector('[data-reload]').onclick=()=>location.reload();}
  function empty(title,text=''){return `<div class="empty">${icon('info')}<h3>${escapeHtml(title)}</h3><p>${escapeHtml(text)}</p></div>`;}
  function initShell({compact=false}={}){
    const header=$('[data-header]');
    if(header) header.innerHTML=compact?`<div class="demo-top"><div class="wrap"><div class="flex">${logo()}<span class="demo-day-label mono tiny" data-day-label>CHẾ ĐỘ DEMO</span></div><div class="flex"><a class="button outline" href="${pageUrl()}">Về trang shop</a><button class="button" data-night disabled>${icon('moon')}Kết thúc ngày</button></div></div></div>`:`<header class="market-header"><div class="wrap"><div class="topbar"><div class="topbar-group"><a href="${pageUrl('demo.html')}">Kênh người bán</a><span>OpenAI × Sea Group Hackathon</span></div><div class="topbar-group"><span class="flex">${icon('info')} Dữ liệu mô phỏng</span><a href="${pageUrl('proof.html')}">Khám phá Growth Agents</a></div></div><div class="main-header">${logo()}<div class="search-area"><form class="search" role="search" data-search><label class="sr-only" for="search-input">Tìm sản phẩm</label><input id="search-input" type="search" placeholder="Tìm sản phẩm trong demo"><button aria-label="Tìm kiếm">${icon('search')}</button></form><div class="search-terms" data-search-terms></div></div><button class="cart icon-button" data-cart aria-label="Xem giỏ hàng mô phỏng">${icon('cart')}<span class="cart-count" data-cart-count>0</span></button></div></div></header>`;
    const context=$('[data-context]');if(context)context.innerHTML=`<div class="context-bar"><div class="wrap"><div class="context-name">${icon('spark')}<strong>Growth Agents</strong><span class="pill orange">Trợ lý tăng trưởng cho shop</span></div><div class="context-links">${preview?'<span class="preview-label">BẢN XEM TRƯỚC · DỮ LIỆU MẪU</span>':'<span class="pill blue">Phiên demo mô phỏng</span>'}<a href="${pageUrl('proof.html')}">Xem bằng chứng ${icon('chevron')}</a></div></div></div>`;
    const footer=$('[data-footer]');if(footer)footer.innerHTML=`<footer class="site-footer"><div class="wrap"><span><strong>sàn·demo</strong> &nbsp; Một cửa hàng nhỏ. Thêm cơ hội tăng trưởng.</span><span>Growth Agents · OpenAI × Sea Group Hackathon · ${preview?'Dữ liệu mẫu để xem giao diện':'Sàn thương mại điện tử mô phỏng'}</span></div></footer>`;
    $$('[data-page]').forEach(a=>{a.href=pageUrl(a.dataset.page);});
    $('[data-search]')?.addEventListener('submit',e=>{e.preventDefault();toast('Ô tìm kiếm minh họa. Sản phẩm đang hiển thị được lấy từ phiên demo hiện tại.');});
    $('[data-cart]')?.addEventListener('click',()=>toast('Giỏ hàng mô phỏng. Không phát sinh đơn hàng hay thanh toán.'));
    document.addEventListener('error',event=>{const img=event.target;if(img instanceof HTMLImageElement && !img.dataset.fallback){img.dataset.fallback='1';img.src=asset('img/product-placeholder.svg');img.alt+=' (ảnh minh họa thay thế)';}},true);
  }
  async function resetDialog(onReset=()=>{location.href=pageUrl();}){
    let dialog=$('#reset-dialog');if(dialog)dialog.remove();
    dialog=document.createElement('dialog');dialog.id='reset-dialog';dialog.className='dialog';
    dialog.innerHTML=`<h2>Đặt lại buổi demo?</h2><p>Xóa bộ nhớ và nhật ký của phiên hiện tại, đưa shop về ngày 1. Bạn có thể bắt đầu lại với cùng kịch bản.</p><label><input type="checkbox" name="memory" checked>Bật bộ nhớ cho lần chạy mới</label><div class="dialog-actions"><button class="button quiet" data-cancel>Giữ phiên hiện tại</button><button class="button" data-confirm>Đặt lại dữ liệu</button></div>`;
    document.body.append(dialog);dialog.showModal();$('[data-cancel]',dialog).onclick=()=>dialog.close();
    $('[data-confirm]',dialog).onclick=e=>busy(e.currentTarget,async()=>{const result=await api('/api/reset',{method:'POST',body:{memory:$('[name=memory]',dialog).checked,seed:42}});dialog.close();await onReset(result);});
    dialog.addEventListener('close',()=>dialog.remove(),{once:true});
  }
  let endingDay=false;
  async function endDay(button){
    if(endingDay)return;endingDay=true;
    const controls=$$('[data-night]');controls.forEach(b=>b.disabled=true);
    try{await api('/api/night',{method:'POST'});location.href=pageUrl('night.html');}
    catch(error){toast(error.message,true);controls.forEach(b=>b.disabled=false);}
    finally{endingDay=false;}
  }
  function bindNight(s){$$('[data-night]').forEach(button=>{button.disabled=endingDay || s.step!=='day_done';button.onclick=()=>endDay(button);});}
  function steps(s){const index={idle:0,negotiating:1,awaiting_decision:2,content_review:3,day_done:4,night_done:5}[s.step]??0;return `<ol class="steps" aria-label="Tiến trình demo">${['Phát hiện cơ hội','Hai agent thương lượng','Người bán duyệt','Làm nội dung','Áp dụng','Học ban đêm'].map((text,i)=>`<li class="${i===index?'current':i<index?'done':''}" ${i===index?'aria-current="step"':''}><span class="step-no">${i<index?'✓':i+1}</span>${text}</li>`).join('')}</ol>`;}
  function changedFields(shop,old){return [['title','Tiêu đề'],['description','Mô tả'],['images','Ảnh sản phẩm'],['video','Video'],['active_voucher_pct','Voucher']].filter(([key])=>JSON.stringify(shop[key])!==JSON.stringify(old[key])).map(([key,label])=>({key,label}));}
  const categoryLabel=category=>({quat_mini:'Quạt mini'}[category] || category || 'Chưa có danh mục');
  function colorsFor(shop){
    const attr=(shop.attributes || []).find(text=>/màu\s*:/iu.test(text));
    return attr?attr.split(':').slice(1).join(':').split(/[,;|]/).map(text=>text.trim()).filter(Boolean):[];
  }
  function syncShopContext(state){
    const shop=state.demo_shop;
    $$('[data-shop-name]').forEach(el=>{el.textContent=shop.name;});
    $$('[data-category]').forEach(el=>{el.textContent=categoryLabel(shop.category);});
    $$('[data-product-name]').forEach(el=>{el.textContent=shop.title;});
    const search=$('#search-input');
    if(search && !search.dataset.synced){search.value=shop.title;search.dataset.synced='1';}
    const terms=$('[data-search-terms]');
    if(terms)terms.innerHTML=(shop.attributes || []).slice(0,3).map(text=>`<span>${escapeHtml(text)}</span>`).join('');
    if($('#shop-content'))document.title=`${shop.name} · ${shop.title} | sàn·demo`;
    else if($('.demo-page'))document.title=`Trợ lý tăng trưởng · ${shop.name} | sàn·demo`;
  }
  function product(shop,old=null){
    const changed=old?changedFields(shop,old).map(i=>i.key):[];
    const mark=key=>changed.includes(key)?'<span class="badge-new">Mới</span>':'';
    const images=(shop.images?.length?shop.images:[asset('img/product-placeholder.svg')]).slice(0,4);
    const colors=colorsFor(shop);
    const swatches={'trắng':'#e6e9df','hồng':'#e7bdbd','xanh mint':'#b8d5c2'};
    const colorOptions=colors.length?`<div class="detail-row"><span class="detail-label">Màu sắc</span><div class="color-options" role="group" aria-label="Chọn màu sản phẩm">${colors.map((color,i)=>`<button class="color-chip ${i===0?'active':''}" data-color="${escapeHtml(color)}" aria-pressed="${i===0}"><i class="swatch" style="background:${swatches[color.toLocaleLowerCase('vi-VN')] || '#dedbd8'}"></i>${escapeHtml(color)}</button>`).join('')}</div></div>`:'';
    return `<div class="card"><div class="product-top">
      <div class="gallery"><div class="hero-image">${mark('images')}<span class="image-caption">${escapeHtml(shop.name)}</span><img id="product-hero" src="${escapeHtml(mediaUrl(images[0]))}" alt="${escapeHtml(shop.title)} · ${escapeHtml(shop.name)}" fetchpriority="high"></div>
        <div class="thumbnails">${images.map((src,i)=>`<button class="thumb ${i===0?'active':''}" data-thumb="${escapeHtml(mediaUrl(src))}" aria-label="Xem ảnh sản phẩm ${i+1}" aria-pressed="${i===0}"><img src="${escapeHtml(mediaUrl(src))}" alt="Ảnh sản phẩm ${i+1}"></button>`).join('')}<button class="thumb video-thumb" data-product-video>${icon('video')}<span>${shop.video?'Xem video':'Chưa có video'}</span></button></div>
        <div class="gallery-foot"><span>Ảnh sản phẩm</span><span>${icon('heart')} ${escapeHtml(shop.name)}</span></div>
      </div>
      <section class="product-info" aria-label="Thông tin sản phẩm">
        <h1 class="product-title"><span class="seller-tag">${escapeHtml(shop.name)}</span>${mark('title')}${escapeHtml(shop.title)}</h1>
        <div class="rating-row"><span class="rating"><u>${dec(shop.rating)}</u> <span class="stars" aria-hidden="true">★</span></span><span>Kho: <strong>${dec(shop.stock,0)}</strong></span><span>Dữ liệu giả lập</span></div>
        <div class="price-block"><div class="price">${vnd(shop.price)}</div><div class="price-note">Giá niêm yết của sản phẩm trong mô phỏng</div></div>
        <div class="detail-row"><span class="detail-label">Voucher shop</span><div>${mark('active_voucher_pct')}${shop.active_voucher_pct?`<span class="ticket">${icon('voucher')} Giảm ${dec(shop.active_voucher_pct,0)}%</span>`:'<span class="muted">Chưa có voucher</span>'}</div></div>
        <div class="detail-row"><span class="detail-label">Vận chuyển</span><div class="flex">${icon('shield')}<span>Đơn hàng mô phỏng<br><small class="muted">Không phát sinh giao dịch thực</small></span></div></div>
        ${colorOptions}
        <div class="detail-row"><label class="detail-label" for="quantity">Số lượng</label><div class="quantity"><button data-qty="-1" aria-label="Giảm số lượng">−</button><output id="quantity" aria-live="polite">1</output><button data-qty="1" aria-label="Tăng số lượng">+</button></div></div>
        <div class="buy-actions"><button class="button secondary" data-add-cart>${icon('cart')}Thêm vào giỏ hàng</button><button class="button" data-buy>Mua ngay</button></div>
        <div class="assurance">${icon('shield')}Chủ shop luôn duyệt trước mọi thay đổi.</div>
      </section>
    </div>
    <div class="shop-strip"><div class="avatar" aria-hidden="true">${escapeHtml((shop.name || 'S').trim().slice(0,1).toUpperCase())}</div><div><div class="shop-title">${escapeHtml(shop.name)}</div><span class="tiny muted">Cửa hàng trong mô phỏng</span></div><div class="shop-stats"><div>Chất lượng listing<strong>${dec(shop.listing_quality,2)} / 1</strong></div><div>Trang tìm kiếm<strong>Trang ${dec(shop.search_rank_page,0)}</strong></div><div>Đánh giá<strong>${dec(shop.rating)} / 5</strong></div></div></div></div>
    <section class="card details-card"><h2 class="section-title">CHI TIẾT SẢN PHẨM</h2><dl class="attributes"><dt>Danh mục</dt><dd>${escapeHtml(categoryLabel(shop.category))}</dd><dt>Thuộc tính</dt><dd>${escapeHtml((shop.attributes || []).join(' · '))}</dd><dt>Shop</dt><dd>${escapeHtml(shop.name)}</dd></dl><h2 class="section-title">${mark('description')}MÔ TẢ SẢN PHẨM</h2><p class="description">${escapeHtml(shop.description)}</p></section>`;
  }
  function bindProduct(shop){
    syncShopContext({demo_shop:shop});
    $$('[data-thumb]').forEach(button=>button.onclick=()=>{$('#product-hero').src=button.dataset.thumb;$$('[data-thumb]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',b===button);});});
    $$('[data-color]').forEach(button=>button.onclick=()=>{$$('[data-color]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',b===button);});});
    $$('[data-qty]').forEach(button=>button.onclick=()=>{$('#quantity').value=Math.max(1,Math.min(shop.stock || 1,Number($('#quantity').value)+Number(button.dataset.qty)));});
    $('[data-add-cart]')?.addEventListener('click',()=>{const count=$('[data-cart-count]');if(count)count.textContent=Number(count.textContent)+Number($('#quantity').value);toast('Đã thêm vào giỏ hàng mô phỏng.');});
    $('[data-buy]')?.addEventListener('click',()=>toast('Đây là sản phẩm mô phỏng. Bấm “Bắt đầu demo” để trải nghiệm trợ lý tăng trưởng.'));
    $('[data-product-video]')?.addEventListener('click',()=>{
      if(!shop.video){toast('Sản phẩm chưa có video. Trợ lý có thể đề xuất nội dung mới trong demo.');return;}
      const dialog=document.createElement('dialog');dialog.className='dialog';dialog.innerHTML=`<h2>Video sản phẩm</h2><video controls style="width:100%;max-height:65vh" src="${escapeHtml(mediaUrl(shop.video))}"></video><div class="dialog-actions"><button class="button quiet">Đóng</button></div>`;document.body.append(dialog);dialog.showModal();$('button',dialog).onclick=()=>dialog.close();dialog.addEventListener('close',()=>dialog.remove(),{once:true});
    });
  }
  function control(s,{updated=false,changes=[]}={}){
    const active=s.active_package;const p=active?.package;
    return `<section class="demo-panel"><div class="between"><span class="eyebrow">${updated?'Gói đang chạy':'Bảng điều khiển demo'}</span>${icon('spark')}</div><h2 class="panel-heading">${updated?'Những thay đổi nhỏ.\nCơ hội mới cho shop.':'Bạn là chủ shop.\nQuyết định vẫn ở bạn.'}</h2><p>${updated?'Nội dung đã được áp dụng theo lựa chọn của chị. Theo dõi kết quả để xem hệ thống học được gì.':`Bạn đóng vai chủ shop ${escapeHtml(s.demo_shop.name)}. Trợ lý đề xuất, chị là người quyết định.`}</p><div class="panel-rule"></div><div class="panel-stats"><div><span>Ngày mô phỏng</span><strong>${s.day} / 6</strong></div><div><span>Bộ nhớ</span><strong class="flex"><i class="dot${s.memory_enabled?'':' orange'}"></i>${s.memory_enabled?'Đang bật':'Đang tắt'}</strong></div><div><span>${preview?'Nguồn dữ liệu':'Dữ liệu LLM'}</span><strong>${preview?'Mẫu xem giao diện':modeLabel(s.mode)}</strong></div></div>${updated && p?`<div class="active-list"><div><span>Quảng cáo / ngày</span><strong>${active.ads_paused?'Đã tạm dừng':vnd(p.ads_daily_budget)}</strong></div><div><span>Voucher</span><strong>${dec(p.voucher_pct,0)}%</strong></div><div><span>Ngưỡng dừng ROAS</span><strong>${dec(p.stop_roas_below)}</strong></div><div><span>Thời hạn</span><strong>Ngày ${active.start_day}–${active.end_day}</strong></div></div>`:''}${updated?`<button class="button full" data-night ${s.step!=='day_done'?'disabled':''}>${icon('moon')}Kết thúc ngày</button><a class="button outline full" href="${pageUrl('demo.html')}">Mở lại hậu trường</a>`:`<button class="button full" data-start ${s.day>6?'disabled':''}>${icon('spark')}${s.day>6?'Đã hoàn tất 6 ngày':s.step==='idle' || s.step==='night_done'?'Bắt đầu demo':'Tiếp tục demo'}${icon('arrow')}</button>`}<button class="button outline full" data-reset>${icon('refresh')}Đặt lại dữ liệu</button><div class="panel-foot"><a href="${pageUrl('proof.html')}">Xem bằng chứng sau 6 ngày ${icon('chevron')}</a></div></section>${updated?`<section class="card insight"><h3>Thay đổi đã áp dụng</h3>${changes.length?`<ul class="changes-list">${changes.map(c=>`<li>${escapeHtml(c.label)}</li>`).join('')}</ul>`:'<p class="tiny muted">Chưa có thay đổi trong phiên này.</p>'}</section>`:''}`;
  }
  function insight(s,events=[]){const opportunity=events.findLast?events.findLast(e=>e.type==='opportunity'):events.filter(e=>e.type==='opportunity').at(-1);const growth=opportunity?.data?.growth_7d_pct??null;return `<section class="card insight"><h2 class="insight-heading">${icon('trend')}Tín hiệu agent sàn đang thấy</h2><p class="tiny muted" style="margin-top:14px">${escapeHtml(opportunity?.data?.keyword || s.demo_shop.title)}</p><div class="between" style="margin-top:3px"><div><strong class="trend-number">${growth!==null?'+'+dec(growth,0)+'%':'—'}</strong><p class="tiny muted">${growth!==null?'Mức quan tâm trong 7 ngày':'Chờ tín hiệu thị trường'}</p></div><span class="signal-trend" aria-hidden="true">${icon('trend')}</span></div><div class="insight-grid"><div><small class="muted">Chất lượng listing</small><strong>${dec(s.demo_shop.listing_quality,2)}<small class="muted"> / 1</small></strong></div><div><small class="muted">Vị trí tìm kiếm</small><strong>Trang ${dec(s.demo_shop.search_rank_page,0)}</strong></div></div><p class="tiny muted" style="margin-top:14px">${preview?'Dữ liệu mẫu của kịch bản demo':'Tín hiệu trong thị trường mô phỏng'}</p></section><section class="howto"><h3 style="font-size:12px">Một vòng demo, ba điều dễ thấy</h3><ol><li>Hai agent thương lượng vì lợi ích của shop.</li><li>Chủ shop duyệt từng thay đổi.</li><li>Ngày mai tốt hơn nhờ bộ nhớ.</li></ol></section>`;}
  function bindControl(s){$('[data-reset]')?.addEventListener('click',()=>resetDialog());$('[data-start]')?.addEventListener('click',e=>busy(e.currentTarget,async()=>{if(['idle','night_done'].includes(s.step))await api('/api/day/start',{method:'POST'});location.href=pageUrl('demo.html');}));bindNight(s);}
  function download(name,text,type='application/json'){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  window.App={$, $$,escapeHtml,vnd,dec,asset,safeUrl,mediaUrl,pageUrl,preview,icon,actorLabel,modeLabel,api,toast,busy,errorBlock,empty,initShell,resetDialog,endDay,bindNight,steps,changedFields,syncShopContext,product,bindProduct,control,insight,bindControl,download};
})();
