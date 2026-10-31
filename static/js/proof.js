(async()=>{
  'use strict';
  const A=window.App,E=A.escapeHtml;A.initShell();const target=A.$('#proof-content');
  try{
    const report=await A.api('/api/proof');
    A.$('#proof-days').textContent=String(report.days);A.$('#proof-seed').textContent=String(report.seed);
    const format=(value,unit)=>unit==='đ'?A.vnd(value):A.dec(value,unit==='%'?1:0)+(unit==='%'?'%':'');
    target.innerHTML=`${A.preview?'<div class="proof-sample"><strong>Số liệu minh họa giao diện.</strong> Các thanh dưới đây chưa phải kết quả thực nghiệm. Kết quả thật do backend cung cấp sau khi chạy đối chứng.</div>':''}<div class="proof-grid">${(report.metrics || []).map(metric=>{
      const on=Number(metric.on),off=Number(metric.off);const valid=Number.isFinite(on) && Number.isFinite(off);
      const scale=metric.unit==='%'?100:Math.max(Math.abs(on),Math.abs(off),1);const width=value=>valid?Math.max(0,Math.min(100,Math.abs(value)/scale*100)):0;
      return `<section class="card proof-card"><div class="between"><h2>${E(metric.label_vi)}</h2><span class="pill ${metric.better==='higher'?'green':'blue'}">${metric.better==='higher'?'Cao hơn là tốt':'Thấp hơn là tốt'}</span></div><div class="bar-row"><div class="bar-meta"><span>Bộ nhớ bật</span><strong>${format(metric.on,metric.unit)}</strong></div><div class="bar-track" role="img" aria-label="Bộ nhớ bật: ${E(format(metric.on,metric.unit))}"><div class="bar-fill" style="width:${width(on)}%"></div></div></div><div class="bar-row"><div class="bar-meta"><span>Bộ nhớ tắt</span><strong>${format(metric.off,metric.unit)}</strong></div><div class="bar-track" role="img" aria-label="Bộ nhớ tắt: ${E(format(metric.off,metric.unit))}"><div class="bar-fill off" style="width:${width(off)}%"></div></div></div></section>`;
    }).join('')}</div>${!report.metrics?.length?`<div class="card">${A.empty('Chưa có kết quả đối chứng.','Nhóm backend cần cung cấp ProofReport từ lần chạy cùng seed.')}</div>`:''}<p class="proof-note">${E(report.note_vi)}</p><p class="tiny muted" style="margin-top:8px">${A.preview?'Mã bản mẫu':'Mã lần chạy'}: ${E(report.run_on)} / ${E(report.run_off)}</p><div class="bottom-actions"><button class="button outline" data-export-report>${A.icon('download')}Tải báo cáo so sánh</button><button class="button outline" data-export-log>${A.icon('book')}Tải nhật ký phiên</button><button class="button" data-restart>${A.icon('refresh')}Chạy lại từ đầu</button></div>`;
    A.$('[data-restart]').onclick=()=>A.resetDialog();
    A.$('[data-export-report]').onclick=()=>A.download('proof.json',JSON.stringify(report,null,2));
    A.$('[data-export-log]').onclick=e=>A.busy(e.currentTarget,async()=>{const result=await A.api('/api/events?after=0');A.download('events.json',JSON.stringify(result.events,null,2));});
  }catch(error){A.errorBlock(target,error);}
})();
