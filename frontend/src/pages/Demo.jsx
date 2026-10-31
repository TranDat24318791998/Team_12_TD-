import {useRef,useState} from 'react';
import {Icon} from '../components/Icon.jsx';
import {Proposal} from '../components/Proposal.jsx';
import {ContentReview} from '../components/ContentReview.jsx';
import {EventFeed} from '../components/EventFeed.jsx';
import {AgentActivity} from '../components/AgentActivity.jsx';
import {Empty,Loading,Progress} from '../components/Shell.jsx';
import {changedFields,pageURL} from '../format.js';
import {scopedEvents} from '../activity.js';

export function DemoPage({run,preview,navigate,onEndDay,onNotice}){
  const {state,events,pending,act,feedError,error}=run;const [note,setNote]=useState('');const message=useRef(null);
  const history=scopedEvents(state,events).filter(event=>event.shop_id===state.demo_shop.shop_id && event.type==='seller_decision');
  const card=state.pending_card;
  async function decide(action,note_vi='',answer=null){
    const body={card_id:card.card_id,action,note_vi};if(answer!==null)body.rule_answer=answer;
    const ok=await act('/api/decision',body);if(ok)setNote('');return ok;
  }
  return <main id="main-content" className="wrap"><div id="steps"><Progress state={state} events={events} pending={pending}/></div><AgentActivity state={state} events={events} preview={preview} error={feedError || error} pending={pending}/><div className="demo-grid">
    <section className="seller-channel" aria-label="Kênh người bán"><div className="channel-heading"><div><h1>Kênh người bán · <span data-shop-name>{state.demo_shop.name}</span></h1><p>Chị quyết định. Trợ lý đồng hành.</p></div><span className="pill orange">Bạn đang là: chủ shop</span></div>
      <div id="chat-content" className="chat-content"><div><div className="message-meta"><span className="avatar">G</span><strong>Trợ lý tăng trưởng</strong><span>· Hôm nay</span></div><div className="bubble">Chào chị, em sẽ cùng agent của shop xem có cách nào giúp sản phẩm được chú ý hơn, trong các giới hạn chị đã đặt.</div></div>
        {history.map(event=><div key={event.seq} className="bubble seller">{event.data?.note_vi || event.text_vi}<div className="tiny" style={{marginTop:5,opacity:.65}}>{event.ts} · {({accept:'Chị đã đồng ý',reject:'Chị đã từ chối',negotiate:'Chị muốn thương lượng thêm'})[event.data?.action] || 'Quyết định của chị'}</div></div>)}
        {state.step==='negotiating' && <div className="bubble"><span className="flex tiny"><Icon name="spark"/>Hai agent đang trao đổi để tìm gói phù hợp cho shop của chị…</span></div>}
        {state.step==='awaiting_decision' && card && <Proposal key={card.card_id} card={card} pending={!!pending} onDecision={decide} onNegotiate={()=>message.current?.focus()}/>}
        {state.step==='content_review' && (state.content_draft?<ContentReview key={state.run_id+':'+state.day+':'+state.content_draft.version} draft={state.content_draft} original={state.demo_shop_original} pending={!!pending} onNotice={onNotice} onRetry={feedback_vi=>act('/api/content/retry',{feedback_vi})} onApply={async cover_option=>{if(await act('/api/content/apply',{cover_option}))navigate('updated.html');}}/>:<Loading text="Đang chuẩn bị nội dung cho chị…"/>)}
        {state.step==='day_done' && <div className="bubble"><strong>Đã ghi nhận lựa chọn của chị.</strong><p style={{marginTop:7}}>Chị có thể kết thúc ngày để xem kết quả và những gì hệ thống ghi nhớ.</p><div className="offer-actions">{changedFields(state.demo_shop,state.demo_shop_original).length>0 && <a className="button secondary" href={pageURL('updated.html',preview)}>Xem trang shop mới <Icon name="arrow"/></a>}<button className="button" data-night disabled={!!pending} onClick={onEndDay}><Icon name="moon"/>Kết thúc ngày</button></div></div>}
        {state.step==='complete' && <div className="bubble"><strong>Đã hoàn tất phiên mô phỏng.</strong><p>Chị có thể xem tổng kết và báo cáo đối chứng.</p><a className="button secondary" href={pageURL('night.html',preview)}>Xem tổng kết cuối cùng</a></div>}
        {['idle','night_done'].includes(state.step) && <><Empty title="Bắt đầu một ngày mới">Về trang shop để bắt đầu ngày tiếp theo.</Empty><a className="button secondary" href={pageURL('index.html',preview)}>Về trang shop</a></>}
      </div>
      <form id="composer" className="composer" hidden={state.step!=='awaiting_decision' || card?.kind==='question'} onSubmit={async event=>{event.preventDefault();if(!note.trim()){message.current?.focus();onNotice('Chị hãy nhập điều muốn điều chỉnh.');return;}await decide('negotiate',note.trim());}}><label htmlFor="seller-message">Chị muốn điều chỉnh gì trong gói đề xuất?</label><div className="composer-row"><textarea id="seller-message" ref={message} rows={1} maxLength={1000} placeholder="Ví dụ: Giảm voucher giúp chị còn 2%…" required value={note} onChange={event=>setNote(event.target.value)} disabled={!!pending}/><button className="button" type="submit" disabled={!!pending} aria-label="Gửi yêu cầu thương lượng">Gửi <Icon name="arrow"/></button></div></form>
    </section><EventFeed state={state} events={events} preview={preview} error={feedError || error}/>
  </div></main>;
}
