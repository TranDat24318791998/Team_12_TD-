import {SIMULATION_DAYS} from '../config.js';
import {useEffect,useRef,useState} from 'react';
import {Icon} from './Icon.jsx';
import {pageURL,modeLabel} from '../format.js';
import {journeyProgress} from '../activity.js';

export function Logo({preview}){return <a className="brand" href={pageURL('index.html',preview)} aria-label="sàn demo, trang shop"><svg className="bag" viewBox="0 0 30 36" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M5 10h20l2 23H3L5 10ZM10 10V7a5 5 0 0 1 10 0v3"/><path d="M19 16c-5-4-10 2-5 5s3 8-3 5" strokeWidth="2" strokeLinecap="round"/></svg><span>sàn<span>·demo</span></span></a>;}
export function Shell({preview,state,compact=false,comparison=false,pending,onEndDay,onNotice,cart=0,children}){
  const shop=state?.demo_shop;
  const [query,setQuery]=useState('');
  useEffect(()=>{if(shop)setQuery(shop.title);},[shop?.title]);
  return <>
    <a className="sr-only" href="#main-content">Đi tới nội dung chính</a>
    {compact?<header className="demo-top"><div className="wrap"><div className="flex"><Logo preview={preview}/><span className="demo-day-label mono tiny" data-day-label>{comparison?'ĐỐI CHỨNG BỘ NHỚ':state?`NGÀY ${state.day} / ${SIMULATION_DAYS}`:'CHẾ ĐỘ DEMO'}</span></div><div className="flex"><a className="button outline" href={pageURL('index.html',preview)}>Về trang shop</a>{comparison?<a className="button" href={pageURL('demo.html',preview)}><Icon name="message"/>Xem luồng agent</a>:<button className="button" data-night disabled={!!pending || state?.step!=='day_done'} onClick={onEndDay}><Icon name="moon"/>Kết thúc ngày</button>}</div></div></header>:<header className="market-header"><div className="wrap"><div className="topbar"><div className="topbar-group"><a href={pageURL('demo.html',preview)}>Kênh người bán</a><span>OpenAI × Sea Group Hackathon</span></div><div className="topbar-group"><span className="flex"><Icon name="info"/>Dữ liệu mô phỏng</span><a href={pageURL('proof.html',preview)}>Khám phá Growth Agents</a></div></div><div className="main-header"><Logo preview={preview}/><div className="search-area"><form className="search" role="search" onSubmit={event=>{event.preventDefault();onNotice('Ô tìm kiếm minh họa. Sản phẩm được lấy từ phiên demo hiện tại.');}}><label className="sr-only" htmlFor="search-input">Tìm sản phẩm</label><input id="search-input" type="search" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Tìm sản phẩm trong demo"/><button aria-label="Tìm kiếm"><Icon name="search"/></button></form><div className="search-terms">{(shop?.attributes || []).slice(0,3).map(text=><span key={text}>{text}</span>)}</div></div><button className="cart icon-button" data-cart aria-label="Xem giỏ hàng mô phỏng" onClick={()=>onNotice('Giỏ hàng mô phỏng. Không phát sinh đơn hàng hay thanh toán.')}><Icon name="cart"/><span className="cart-count" data-cart-count>{cart}</span></button></div></div></header>}
    <div className="context-bar"><div className="wrap"><div className="context-name"><Icon name="spark"/><strong>Growth Agents</strong><span className="pill orange">Trợ lý tăng trưởng cho shop</span></div><div className="context-links">{preview?<span className="preview-label">BẢN XEM TRƯỚC · DỮ LIỆU MẪU</span>:<span className="pill blue">Phiên demo mô phỏng</span>}<a href={pageURL('proof.html',preview)}>Xem bằng chứng <Icon name="chevron"/></a></div></div></div>
    {children}
    <footer className="site-footer"><div className="wrap"><span><strong>sàn·demo</strong> &nbsp; Một cửa hàng nhỏ. Thêm cơ hội tăng trưởng.</span><span>Growth Agents · OpenAI × Sea Group Hackathon · {preview?'Dữ liệu mẫu để xem giao diện':'Sàn thương mại điện tử mô phỏng'}</span></div></footer>
  </>;
}
export function Loading({text='Đang tải dữ liệu…'}){return <div className="loading-block" role="status">{text}</div>;}
export function Empty({title,children}){return <div className="empty"><Icon name="info"/><h3>{title}</h3>{children && <p>{children}</p>}</div>;}
export function ErrorPanel({message,onRetry}){const previewURL=new URL(globalThis.location?.href || 'http://localhost/');previewURL.searchParams.set('preview','1');return <div className="error-box" role="alert"><p>{message}</p><button className="button secondary" onClick={onRetry}>Thử tải lại</button> <a className="button quiet" href={previewURL.href}>Mở bản xem trước</a></div>;}
export function ResetDialog({open,onClose,onReset,pending,error}){
  const ref=useRef(null);const [memory,setMemory]=useState(true);
  useEffect(()=>{const dialog=ref.current;if(open){if(!dialog.open)dialog.showModal();}else if(dialog.open)dialog.close();},[open]);
  return <dialog id="reset-dialog" ref={ref} className="dialog" aria-labelledby="reset-title" onCancel={onClose} onClose={onClose}>
    <h2 id="reset-title">Đặt lại buổi demo?</h2><p>Xóa bộ nhớ và nhật ký của phiên hiện tại, đưa shop về ngày 1. Bạn có thể bắt đầu lại với cùng kịch bản.</p>
    <label><input name="memory" type="checkbox" checked={memory} onChange={event=>setMemory(event.target.checked)}/>Bật bộ nhớ cho lần chạy mới</label>
    {error && <p className="error-box" role="alert">{error}</p>}<div className="dialog-actions"><button className="button quiet" data-cancel onClick={onClose} disabled={pending}>Giữ phiên hiện tại</button><button className="button" data-confirm onClick={()=>onReset(memory)} disabled={pending}>{pending?'Đang đặt lại…':'Đặt lại dữ liệu'}</button></div>
  </dialog>;
}
export function Progress({step,state,events=[],pending}){
  const {current,skipped}=state?journeyProgress(state,events,pending):{current:({idle:0,negotiating:1,awaiting_decision:2,content_review:3,day_done:4,night_done:6,complete:6}[step] ?? 0),skipped:new Set()};
  return <ol className="steps" aria-label="Tiến trình demo">{['Phát hiện cơ hội','Hai agent thương lượng','Người bán duyệt','Làm nội dung','Áp dụng','Học ban đêm'].map((name,i)=><li key={name} className={skipped.has(i)?'skipped':i===current?'current':i<current?'done':''} aria-current={!skipped.has(i) && i===current?'step':undefined}><span className="step-no">{skipped.has(i)?'–':i<current?'✓':i+1}</span>{name}{skipped.has(i) && <span className="sr-only">: Bỏ qua</span>}</li>)}</ol>;
}
export function Connection({state,preview}){return <span className="tiny muted">{preview?'Mẫu xem giao diện':modeLabel(state?.mode)}</span>;}
