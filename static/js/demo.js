(async()=>{
  'use strict';
  const A=window.App;const E=A.escapeHtml;A.initShell({compact:true});
  let renderedSequences=[],feedKey='';
  let state=null,events=[],lastSeq=0,filter='all',signature='',selected='A',selectedVersion=null,timer=null,stopped=false,locked=false,lastStateAt=0;
  const chat=A.$('#chat-content'),feed=A.$('#event-feed'),composer=A.$('#composer');
  const belongs=event=>event.day===state.day && (!event.shop_id || event.shop_id===state.demo_shop.shop_id);
  function packageQuote(p){return p?`<div class="event-package">Nội dung: ${p.content_refresh?'làm mới':'giữ nguyên'} · Quảng cáo: ${A.vnd(p.ads_daily_budget)}/ngày<br>Voucher ${A.dec(p.voucher_pct,0)}% · ${p.duration_days} ngày${p.stop_roas_below!=null?` · Dừng dưới ROAS ${A.dec(p.stop_roas_below)}`:''}</div>`:'';}
  function renderEvents(){
    const atBottom=feed.scrollHeight-feed.scrollTop-feed.clientHeight<70;
    const allowed=event=>filter==='all' || (filter==='negotiation' && ['platform_turn','shop_turn','code_check','card_sent','seller_decision'].includes(event.type)) || (filter==='content' && event.type.startsWith('content_')) || (filter==='memory' && (event.type.startsWith('memory_') || event.type==='night_summary'));
    const visible=events.filter(e=>e.day===state.day && allowed(e));
    const key=state.run_id+':'+state.day+':'+filter;
    const rebuild=key!==feedKey || renderedSequences.some((seq,i)=>visible[i]?.seq!==seq);
    if(rebuild){feed.innerHTML='';renderedSequences=[];feedKey=key;}
    const additions=visible.slice(renderedSequences.length);
    if(additions.length){
      if(!renderedSequences.length)feed.innerHTML='';
      feed.insertAdjacentHTML('beforeend',additions.map(event=>{
      const d=event.data || {};const turn=['platform_turn','shop_turn'].includes(event.type);
      return `<article class="event"><div class="event-meta"><time class="event-time">${E(event.ts)}</time>${A.actorLabel(event.actor)}${turn?`<span class="tiny muted">→</span>${A.actorLabel(event.type==='platform_turn'?'shop_agent':'platform_agent')}`:''}${event.shop_id?`<span class="event-time">${E(event.shop_id)}</span>`:''}</div><p class="event-text">${E(event.text_vi)}</p>${turn?packageQuote(d.package):''}${event.type==='shop_turn' && d.private_note_vi?`<p class="private-note">${A.icon('lock')} Chỉ agent shop thấy: ${E(d.private_note_vi)}</p>`:''}${event.type==='code_check'?(d.checks || []).map(check=>`<p class="event-check ${check.ok?'':'bad'}"><span>${check.ok?'✓ Hợp luật':'✗ Vi phạm'}</span> ${E(check.message_vi)}</p>`).join(''):''}${event.type==='content_job'?`<div class="event-package">${E(d.detail_vi || '')}<br>Trạng thái: ${E(({running:'Đang tạo',done:'Hoàn tất',failed:'Chưa tạo được',cached:'Bản đã lưu',pending:'Đang chờ'})[d.status] || d.status)}</div>`:''}</article>`;
      }).join(''));
    }else if(!visible.length && !feed.querySelector('[data-empty-feed]')){
      feed.innerHTML='<p data-empty-feed class="event-placeholder">Chưa có sự kiện trong nhóm này.</p>';
    }
    renderedSequences=visible.map(e=>e.seq);
    A.$('#event-count').textContent=String(events.filter(e=>e.day===state.day).length);
    if(atBottom)feed.scrollTop=feed.scrollHeight;
  }
  function ruleQuestion(card){if(!card.rule_question)return '';return `<div class="rule-question"><strong>Chị muốn lưu thành sở thích?</strong><p style="margin-top:6px">${E(card.rule_question.text_vi)}</p><div class="rule-options"><label><input type="radio" name="rule-answer" value="true">Có, ghi nhớ giúp chị</label><label><input type="radio" name="rule-answer" value="false">Chưa cần</label></div></div>`;}
  function offer(card){
    if(card.kind==='question')return `<section class="offer-card"><div class="offer-top"><span class="pill blue">Xác nhận sở thích</span><h2 style="margin-top:10px">Trợ lý nhớ góp ý của chị.</h2></div><div class="offer-body"><p style="font-size:12px">${E(card.rule_question?.text_vi || 'Chị muốn giữ sở thích này cho những lần sau?')}</p><p class="tiny muted" style="margin-top:8px">Chỉ trở thành luật cho shop khi chị xác nhận.</p><div class="offer-actions"><button class="button" data-question="true">Có, ghi nhớ giúp chị</button><button class="button secondary" data-question="false">Chưa cần</button></div></div></section>`;
    const p=card.package;if(!p)return A.empty('Chưa có gói đề xuất.');
    return `<section class="offer-card"><div class="offer-top"><div class="between"><span class="eyebrow" style="color:var(--brand)">Dành riêng cho shop của chị</span><span class="pill green">✓ Đã kiểm tra luật</span></div><h2 style="margin-top:10px">Đề xuất gói tăng trưởng · ${p.duration_days} ngày</h2></div><div class="offer-body"><ul class="package-list"><li><span class="package-icon">${A.icon('image')}</span><div><strong>${p.content_refresh?'Làm mới nội dung sản phẩm':'Giữ nội dung hiện tại'}</strong><small>Tiêu đề, mô tả, ảnh bìa · Miễn phí trong demo</small></div></li><li><span class="package-icon">${A.icon('megaphone')}</span><div><strong>${p.ads_daily_budget?`Quảng cáo ${A.vnd(p.ads_daily_budget)}/ngày`:'Không chạy quảng cáo'}</strong><small>${p.ads_daily_budget?`Tối đa ${A.vnd(p.ads_daily_budget*p.duration_days)} cho ${p.duration_days} ngày`:'Giữ nguyên ngân sách quảng cáo'}</small></div></li><li><span class="package-icon">${A.icon('voucher')}</span><div><strong>${p.voucher_pct?`Voucher giảm ${A.dec(p.voucher_pct,0)}%`:'Không áp dụng voucher'}</strong><small>Trong giới hạn chủ shop cho phép</small></div></li>${p.ads_daily_budget && p.stop_roas_below!=null?`<li><span class="package-icon">${A.icon('shield')}</span><div><strong>Tự dừng khi ROAS dưới ${A.dec(p.stop_roas_below)}</strong><small>Nếu thấp hơn ngưỡng trong ${p.stop_after_days} ngày liên tiếp</small></div></li>`:''}</ul>${card.breakeven_roas_display!=null?`<div class="info-box">${A.icon('info')} Sau phí sàn và voucher, quảng cáo của chị cần ROAS khoảng <strong>${A.dec(card.breakeven_roas_display)}</strong> để hòa vốn. Hệ thống theo dõi và dừng theo ngưỡng đã duyệt.</div>`:''}<div class="estimate-grid"><div class="estimate"><span>DỰ KIẾN TRONG ${p.duration_days} NGÀY</span><strong>${card.forecast?`${A.dec(card.forecast.low,0)}–${A.dec(card.forecast.high,0)}`:'—'} <small>đơn</small></strong><small>Dự báo, không phải cam kết</small></div><div class="estimate"><span>LÃI ƯỚC TÍNH SAU PHÍ / ĐƠN</span><strong>${A.vnd(card.profit_after_fees_per_unit)}</strong><small>Chưa trừ chi quảng cáo</small></div></div>${(card.warnings_vi || []).map(text=>`<div class="info-box warn">${E(text)}</div>`).join('')}${(card.notices_vi || []).map(text=>`<p class="tiny muted">${E(text)}</p>`).join('')}<details><summary>Vì sao có đề xuất này?</summary><ul>${(card.reasons_vi || []).map(text=>`<li>${E(text)}</li>`).join('')}</ul></details>${ruleQuestion(card)}<div class="offer-actions"><button class="button" data-decision="accept">Đồng ý ${A.icon('check')}</button><button class="button secondary" data-negotiate>Thương lượng thêm</button><button class="button quiet" data-decision="reject">Từ chối</button></div></div></section>`;
  }
  function content(draft){
    if(selectedVersion!==draft.version){selectedVersion=draft.version;selected=draft.images.find(i=>['done','cached'].includes(i.status))?.option || 'A';}
    const selectedImage=draft.images.find(i=>i.option===selected);const ready=selectedImage && ['done','cached'].includes(selectedImage.status) && selectedImage.path;
    const job=draft.video;const videoReady=job && ['done','cached'].includes(job.status) && job.path;
    return `<section class="content-card"><div class="between"><h2>Nội dung mới cho sản phẩm</h2><span class="pill red">Lần ${draft.version} / 3</span></div><p class="old-title">${E(state.demo_shop_original.title)}</p><h3 class="new-title">${E(draft.title)}</h3><p class="content-description">${E(draft.description)}</p><div class="between" style="margin-bottom:9px"><strong class="tiny">Chọn ảnh bìa chị thích</strong><span class="tiny muted">3 phương án</span></div><div class="cover-options" role="radiogroup" aria-label="Chọn ảnh bìa">${draft.images.map(image=>{const available=['done','cached'].includes(image.status) && image.path;return `<label class="cover-choice"><input type="radio" name="cover-option" value="${E(image.option)}" ${selected===image.option?'checked':''} ${available?'':'disabled'} aria-label="Ảnh bìa ${E(image.option)}">${available?`<img src="${E(A.mediaUrl(image.path))}" alt="Phương án ảnh bìa ${E(image.option)}">`:`<span class="cover-running">${A.icon('image')}${image.status==='failed'?'Chưa tạo được ảnh':'Đang tạo ảnh…'}</span>`}<span class="cover-label"><span>Phương án ${E(image.option)}</span><span>${selected===image.option?'Đã chọn':''}</span></span></label>`;}).join('')}</div><div class="video-preview">${A.icon('video')} ${videoReady?'Video sản phẩm đã sẵn sàng':job?.status==='failed'?'Chưa tạo được video, chị vẫn có thể dùng ảnh.':'Đang tạo video bằng Muse, khoảng 1–2 phút.'}${videoReady?`<video controls preload="metadata" src="${E(A.mediaUrl(job.path))}"></video>`:''}</div>${(draft.checks || []).length?`<p class="tiny muted" style="margin-top:12px">✓ ${draft.checks.map(E).join(' · ')}</p>`:''}<div class="feedback-history">${(draft.feedback_history || []).map(text=>`<span class="pill">${E(text)}</span>`).join('')}</div><label class="feedback-label" for="content-feedback">Góp ý thêm · Còn ${Math.max(0,3-draft.version)} lần làm lại</label><textarea id="content-feedback" class="feedback-input" maxlength="1000" placeholder="Ví dụ: Ảnh nền sáng hơn, giữ rõ màu quạt…" ${draft.version>=3?'disabled':''}></textarea><div class="offer-actions"><button class="button secondary" data-retry ${draft.version>=3?'disabled':''}>${A.icon('refresh')}Làm lại theo góp ý</button><button class="button" data-apply ${ready?'':'disabled'}>Dùng bản này ${A.icon('check')}</button></div></section>`;
  }
  function renderChat(force=false){
    const history=events.filter(e=>belongs(e) && e.type==='seller_decision');
    const next=JSON.stringify([state.step,state.pending_card,state.content_draft,history]);if(next===signature && !force)return;signature=next;
    const feedback=A.$('#content-feedback')?.value || '';const answer=A.$('[name=rule-answer]:checked')?.value;const detailsOpen=A.$('details',chat)?.open;
    const focused=document.activeElement?.id;
    let body=`<div><div class="message-meta"><span class="avatar">G</span><strong>Trợ lý tăng trưởng</strong><span>· Hôm nay</span></div><div class="bubble">Chào chị, em sẽ cùng agent của shop xem có cách nào giúp sản phẩm được chú ý hơn, trong các giới hạn chị đã đặt.</div></div>`;
    body+=history.map(event=>`<div class="bubble seller">${E(event.data?.note_vi || event.text_vi)}<div class="tiny" style="margin-top:5px;opacity:.65">${E(event.ts)} · ${E(({accept:'Chị đã đồng ý',reject:'Chị đã từ chối',negotiate:'Chị muốn thương lượng thêm'})[event.data?.action] || 'Quyết định của chị')}</div></div>`).join('');
    if(state.step==='negotiating')body+=`<div class="bubble"><span class="flex tiny">${A.icon('spark')} Hai agent đang trao đổi để tìm gói phù hợp cho shop của chị…</span></div>`;
    if(state.step==='awaiting_decision' && state.pending_card)body+=offer(state.pending_card);
    if(state.step==='content_review')body+=state.content_draft?content(state.content_draft):'<div class="loading-block">Đang chuẩn bị nội dung cho chị…</div>';
    if(state.step==='day_done')body+=`<div class="bubble"><strong>Đã ghi nhận lựa chọn của chị.</strong><p style="margin-top:7px">${state.content_draft?'Nội dung được chọn đã áp dụng lên sản phẩm.':'Chị có thể kết thúc ngày để xem kết quả và những gì hệ thống ghi nhớ.'}</p><div class="offer-actions">${state.content_draft?`<a class="button secondary" href="${A.pageUrl('updated.html')}">Xem trang shop mới ${A.icon('arrow')}</a>`:''}<button class="button" data-night>${A.icon('moon')}Kết thúc ngày</button></div></div>`;
    if(['idle','night_done'].includes(state.step))body+=A.empty('Bắt đầu một ngày mới',state.last_night?'Ngày trước đã hoàn tất. Về trang shop để bắt đầu ngày tiếp theo.':'Về trang shop và bấm Bắt đầu demo để theo dõi các agent.')+`<a class="button secondary" href="${A.pageUrl()}">Về trang shop</a>`;
    chat.innerHTML=body;
    if(A.$('#content-feedback'))A.$('#content-feedback').value=feedback;
    if(answer){const radio=A.$(`[name=rule-answer][value="${answer}"]`);if(radio)radio.checked=true;}
    if(detailsOpen && A.$('details',chat))A.$('details',chat).open=true;
    if(focused==='content-feedback')A.$('#content-feedback')?.focus({preventScroll:true});
    composer.hidden=state.step!=='awaiting_decision' || state.pending_card?.kind==='question';
    A.$$('[data-decision]').forEach(button=>button.onclick=()=>decide(button,button.dataset.decision));
    A.$$('[data-question]').forEach(button=>button.onclick=()=>decide(button,'accept','',button.dataset.question==='true'));
    A.$('[data-negotiate]')?.addEventListener('click',()=>{A.$('#seller-message').focus();composer.scrollIntoView({behavior:'smooth',block:'nearest'});});
    A.$$('[name=cover-option]').forEach(radio=>radio.onchange=()=>{selected=radio.value;renderChat(true);});
    A.$('[data-retry]')?.addEventListener('click',e=>mutate(e.currentTarget,async()=>{
      const input=A.$('#content-feedback');const value=input.value.trim();if(!value){input.focus();throw new Error('Chị hãy nhập góp ý trước khi làm lại.');}
      await A.api('/api/content/retry',{method:'POST',body:{feedback_vi:value}});input.value='';signature='';
    }));
    A.$('[data-apply]')?.addEventListener('click',e=>mutate(e.currentTarget,async()=>{await A.api('/api/content/apply',{method:'POST',body:{cover_option:selected}});location.href=A.pageUrl('updated.html');}));
    A.bindNight(state);
  }
  async function mutate(button,task){if(locked)return;locked=true;button.disabled=true;A.$$('[data-decision],[data-question],[data-negotiate],[data-retry],[data-apply]').forEach(b=>b.disabled=true);try{await task();await refresh(true);}catch(error){A.toast(error.message,true);}finally{locked=false;if(button.isConnected)button.disabled=false;renderChat(true);}}
  async function decide(button,action,note='',answer){await mutate(button,async()=>{const radio=A.$('[name=rule-answer]:checked');const body={card_id:state.pending_card.card_id,action,note_vi:note};if(answer!==undefined)body.rule_answer=answer;else if(radio)body.rule_answer=radio.value==='true';await A.api('/api/decision',{method:'POST',body});A.$('#seller-message').value='';});}
  composer.addEventListener('submit',e=>{e.preventDefault();const input=A.$('#seller-message');if(!input.value.trim()){input.focus();A.toast('Chị hãy nhập điều muốn điều chỉnh.');return;}decide(A.$('[type=submit]',composer),'negotiate',input.value.trim());});
  A.$$('[data-filter]').forEach(button=>button.onclick=()=>{filter=button.dataset.filter;A.$$('[data-filter]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',b===button);});if(state)renderEvents();});
  A.$('[data-export-events]').onclick=()=>A.download('events-'+(state?.run_id || 'demo')+'.json',JSON.stringify(events,null,2));
  async function refresh(force=false){
    // Establish the server session cookie before issuing parallel requests on a fresh page.
    const initial=!state;
    if(initial){state=await A.api('/api/state');lastStateAt=Date.now();}
    const needState=!initial && (force || state.step!=='content_review' || Date.now()-lastStateAt>=3000);
    const results=await Promise.allSettled([needState?A.api('/api/state'):Promise.resolve(state),A.api('/api/events?after='+lastSeq)]);
    if(results[0].status==='rejected')throw results[0].reason;
    const next=results[0].value;
    if(state && next.run_id!==state.run_id){events=[];lastSeq=0;signature='';state=next;return refresh(true);}
    state=next;A.syncShopContext(state);if(needState)lastStateAt=Date.now();
    if(results[1].status==='fulfilled'){
      const data=results[1].value;const known=new Set(events.map(e=>e.seq));events.push(...data.events.filter(e=>e.run_id===state.run_id && !known.has(e.seq)));events.sort((a,b)=>a.seq-b.seq);lastSeq=data.last_seq;
      A.$('#connection-state').textContent=A.preview?'Dữ liệu mẫu · Không gọi agent thật':'Đang theo dõi sự kiện';
    }else A.$('#connection-state').textContent='Mất kết nối nhật ký · Đang thử lại';
    A.$('[data-day-label]').textContent='NGÀY '+state.day+' / 6';A.$('#steps').innerHTML=A.steps(state);
    A.$('#waiting-label').textContent=({negotiating:'Các agent đang thương lượng…',awaiting_decision:'Đang chờ chủ shop quyết định',content_review:'Đang chờ chủ shop duyệt nội dung',day_done:'Sẵn sàng kết thúc ngày',idle:'Chờ bắt đầu ngày mới',night_done:'Đã tổng kết ngày'})[state.step] || 'Đang chờ…';
    renderEvents();renderChat();A.bindNight(state);
  }
  async function poll(){if(stopped)return;try{if(!locked)await refresh();}catch(error){A.$('#connection-state').textContent='Kết nối gián đoạn · Đang thử lại';}finally{if(!stopped)timer=setTimeout(poll,1500);}}
  window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);});
  try{await refresh(true);timer=setTimeout(poll,1500);}catch(error){A.errorBlock(chat,error);A.$('#connection-state').textContent='Chưa kết nối được dữ liệu';}
})();
