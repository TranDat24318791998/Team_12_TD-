import {useEffect,useRef,useState} from 'react';
import {Icon} from './Icon.jsx';
import {CheckSources} from './CheckSources.jsx';
import {actorNames,dec,download,sourceLabel,vnd} from '../format.js';
import {scopedEvents,sellerFeedback} from '../activity.js';
const completedActors={platform:'platform_agent',shop:'shop_agent',content:'content_agent',learning:'memory',referee:'referee'};
export function Actor({actor}){return <span className={'actor '+(Object.hasOwn(actorNames,actor)?actor:'system')}>{actorNames[actor] || actor}</span>;}
export function PackageQuote({value:p}){return p?<div className="event-package">Nội dung: {p.content_refresh?'làm mới':'giữ nguyên'} · Quảng cáo: {vnd(p.ads_daily_budget)}/ngày<br/>Voucher {dec(p.voucher_pct,0)}% · {p.duration_days} ngày{p.stop_roas_below!=null?` · Dừng dưới ROAS ${dec(p.stop_roas_below)}`:''}</div>:null;}
export function EventItem({event}){
  const d=event.data || {};const turn=['platform_turn','shop_turn'].includes(event.type);
  return <article className="event" id={'event-'+event.seq}>
    <div className="event-meta"><time className="event-time">{event.ts}</time><Actor actor={event.type==='agent_completed' && Object.hasOwn(completedActors,d.role)?completedActors[d.role]:event.actor}/>{turn && <><span className="tiny muted">→</span><Actor actor={event.type==='platform_turn'?'shop_agent':'platform_agent'}/></>}{event.shop_id && <span className="event-time">{event.shop_id}</span>}{Number.isInteger(d.round) && <span className="event-round">Vòng {d.round}</span>}</div>
    <p className="event-text">{event.text_vi}</p>{turn && <PackageQuote value={d.package}/>}
    {event.type==='shop_turn' && d.private_note_vi && <p className="private-note"><Icon name="lock"/> Chỉ agent shop thấy: {d.private_note_vi}</p>}
    {event.type==='code_check' && (Array.isArray(d.checks)?d.checks:[]).filter(check=>typeof check?.ok==='boolean').map((check,i)=><div key={i} className={'event-check '+(check.ok?'':'bad')}><span className="event-check-label">{check.ok?'✓ Hợp luật':'✗ Vi phạm'}</span><div>{check.message_vi}<CheckSources sources={check.sources} inline/></div></div>)}
    {event.type==='content_job' && <div className="event-package">{d.detail_vi}<br/>Trạng thái: {({running:'Đang tạo',done:'Hoàn tất',failed:'Chưa tạo được',cached:'Bản đã lưu',pending:'Đang chờ'})[d.status] || d.status}</div>}
    {event.type==='agent_activity' && <p className="event-task-state">{({running:'Đang xử lý',done:'Đã hoàn tất tác vụ',failed:'Tác vụ chưa thành công',stopped:'Đã dừng tác vụ'})[d.status] || 'Đã cập nhật tác vụ'}</p>}
    {event.type==='agent_completed' && <p className="event-task-state">Nguồn thực tế: {sourceLabel(d.source)}{d.error_code && <> · Mã lý do: {d.error_code}</>}</p>}
    {event.type==='referee_review' && <div className="event-package">{({continue:'Tiếp tục trao đổi',refocus:'Cần tập trung lại',ask_human:'Cần hỏi người bán',stop:'Đề nghị dừng'})[d.action] || 'Đã đánh giá'}{d.focused_question && <p>{d.focused_question}</p>}</div>}
  </article>;
}
export function EventFeed({state,events,preview,error}){
  const [filter,setFilter]=useState('all');const feed=useRef(null),follow=useRef(true);
  const dayEvents=scopedEvents(state,events);
  const visible=dayEvents.filter(event=>filter==='all' || (filter==='negotiation' && (['platform_turn','shop_turn','code_check','card_sent','seller_decision','agent_activity','referee_review'].includes(event.type) || (event.type==='agent_completed' && ['platform','shop','referee'].includes(event.data?.role)))) || (filter==='content' && (event.type.startsWith('content_') || (event.type==='agent_completed' && event.data?.role==='content'))) || (filter==='memory' && (event.type.startsWith('memory_') || event.type==='night_summary' || (event.type==='agent_completed' && event.data?.role==='learning'))));
  useEffect(()=>{if(follow.current && feed.current)feed.current.scrollTop=feed.current.scrollHeight;},[visible.length,filter]);
  const feedback=sellerFeedback(state,events);
  const status=feedback.result?.status==='unknown'?'Chưa xác định được kết quả thương lượng':feedback.waiting?'Các agent đang thương lượng…':({negotiating:'Các agent đang thương lượng…',awaiting_decision:'Đang chờ chủ shop quyết định',content_review:'Đang chờ chủ shop duyệt nội dung',day_done:'Sẵn sàng kết thúc ngày',idle:'Chờ bắt đầu ngày mới',night_done:'Đã tổng kết ngày',complete:'Đã hoàn tất phiên mô phỏng'})[state.step] || 'Đang chờ…';
  return <aside className="backstage" aria-label="Hậu trường các agent"><div className="backstage-head"><div className="between"><h2>Hậu trường</h2><span className="event-time"><span id="event-count">{dayEvents.length}</span> sự kiện</span></div><p>Những gì các agent đang làm. Người bán bình thường không thấy phần này.</p></div><div className="filters" role="group" aria-label="Lọc sự kiện">{[['all','Tất cả'],['negotiation','Thương lượng'],['content','Nội dung'],['memory','Bộ nhớ']].map(([value,label])=><button key={value} className={'filter '+(filter===value?'active':'')} data-filter={value} aria-pressed={filter===value} onClick={()=>{setFilter(value);follow.current=true;}}>{label}</button>)}</div><div className="visibility-note"><p><strong>Agent sàn</strong>Thấy dữ liệu công khai của shop.</p><p><strong>Agent shop</strong>Giữ riêng giá vốn và luật của chủ shop.</p></div>
    <div id="event-feed" ref={feed} className="event-feed" tabIndex={0} role="log" aria-label="Nhật ký tương tác của agent" aria-live="polite" aria-relevant="additions text" onScroll={()=>{const el=feed.current;follow.current=el.scrollHeight-el.scrollTop-el.clientHeight<70;}}>{visible.length?visible.map(event=><EventItem key={event.run_id+':'+event.seq} event={event}/>):<p className="event-placeholder">Chưa có sự kiện trong nhóm này.</p>}</div><div className="feed-status"><i className="dot orange"/><span id="waiting-label">{status}</span></div><div className="backstage-foot"><button data-export-events onClick={()=>download('events-'+state.run_id+'.json',JSON.stringify(events,null,2))}>Tải nhật ký sự kiện</button><span className="event-time" id="connection-state" style={{alignSelf:'center'}}>{error?'Kết nối gián đoạn · Đang thử lại':preview?'Dữ liệu mẫu · Không gọi agent thật':'Đang theo dõi sự kiện'}</span></div>
  </aside>;
}
