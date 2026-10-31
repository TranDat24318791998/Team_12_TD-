import {CONTENT_ATTEMPTS} from '../config.js';
import {useState} from 'react';
import {Icon} from './Icon.jsx';
import {mediaURL} from '../format.js';

export function ContentReview({draft,original,pending,onRetry,onApply,onNotice}){
  const [selected,setSelected]=useState(()=>draft.images.find(image=>['done','cached'].includes(image.status))?.option || 'A');
  const [feedback,setFeedback]=useState(''),[skip,setSkip]=useState(false),[ack,setAck]=useState(false),[broken,setBroken]=useState({});
  const available=image=>['done','cached'].includes(image.status) && mediaURL(image.path) && !broken[image.option+':'+image.path];
  const ready=draft.images.some(image=>image.option===selected && available(image));
  const video=draft.video,videoReady=video && ['done','cached'].includes(video.status) && mediaURL(video.path) && !broken['video:'+video.path];
  const reviewed=video?.visual_review_passed ?? video?.review_passed;
  const unresolved=['queued','running'].includes(draft.status) || draft.images.some(image=>['queued','reserved','pending','running','unknown'].includes(image.status)) || ['queued','reserved','pending','running','unknown'].includes(video?.status) || draft.outcome_unknown;
  async function retry(){if(!feedback.trim()){onNotice('Chị hãy nhập góp ý trước khi làm lại.');return;}if(await onRetry(feedback.trim()))setFeedback('');}
  return <section className="content-card"><div className="between"><h2>Nội dung mới cho sản phẩm</h2><span className="pill red">Lần {draft.version} / {CONTENT_ATTEMPTS}</span></div><p className="old-title">{original.title}</p><h3 className="new-title">{draft.title}</h3><p className="content-description">{draft.description}</p><div className="between" style={{marginBottom:9}}><strong className="tiny">Chọn ảnh bìa chị thích</strong><span className="tiny muted">{draft.images.length} phương án</span></div>
    <div className="cover-options" role="radiogroup" aria-label="Chọn ảnh bìa">{draft.images.map(image=><label className="cover-choice" key={image.option}><input type="radio" name="cover-option" value={image.option} checked={selected===image.option} onChange={()=>setSelected(image.option)} disabled={!available(image) || pending} aria-label={'Ảnh bìa '+image.option}/>{available(image)?<img src={mediaURL(image.path)} alt={'Phương án ảnh bìa '+image.option} onError={()=>setBroken(value=>({...value,[image.option+':'+image.path]:true}))}/>:<span className="cover-running"><Icon name="image"/>{image.status==='failed' || broken[image.option+':'+image.path]?'Ảnh không khả dụng':'Đang tạo ảnh…'}</span>}<span className="cover-label"><span>Phương án {image.option} · {image.source || image.status}</span><span>{selected===image.option?'Đã chọn':''}</span></span>{image.error && <span className="tiny">{image.error}</span>}</label>)}</div>
    <div className="video-preview"><Icon name="video"/> {videoReady?'Video sản phẩm đã sẵn sàng':video?.status==='failed'?'Chưa tạo được video, chị có thể chọn bỏ qua.':'Video chưa sẵn sàng.'}{videoReady && <video controls preload="metadata" src={mediaURL(video.path)} onError={()=>setBroken(value=>({...value,['video:'+video.path]:true}))}/>}<p className="tiny">Nguồn: {video?.source || video?.status || 'chưa có'}{(video?.review_notes_vi || video?.review_notes) && ' · '+(video.review_notes_vi || video.review_notes)}</p>
      <label><input type="checkbox" checked={skip} onChange={event=>setSkip(event.target.checked)}/> Dùng ảnh, bỏ qua video</label>
      {videoReady && reviewed!==true && !skip && <label><input type="checkbox" checked={ack} onChange={event=>setAck(event.target.checked)}/> Tôi đã xem và chấp nhận video chưa được kiểm tra đạt</label>}
    </div>
    {draft.error_code && <p className="tiny" role="alert">{draft.error_code==='MEDIA_INPUT_MISSING'?'Chưa có ảnh sản phẩm nguồn được xác nhận.':draft.error_code==='MEDIA_OFFLINE'?'Dịch vụ tạo media đang tắt.':'Chưa hoàn tất media: '+draft.error_code}</p>}{draft.outcome_unknown && <p className="tiny" role="alert">Kết quả tạo media chưa rõ; cần kiểm tra trước khi làm lại.</p>}
    {!!draft.checks?.length && <p className="tiny muted" style={{marginTop:12}}>✓ {draft.checks.join(' · ')}</p>}<div className="feedback-history">{(draft.feedback_history || []).map((text,i)=><span className="pill" key={i}>{text}</span>)}</div>
    <label className="feedback-label" htmlFor="content-feedback">Góp ý thêm · Còn {Math.max(0,CONTENT_ATTEMPTS-draft.version)} lần làm lại</label><textarea id="content-feedback" className="feedback-input" maxLength={1000} placeholder="Ví dụ: Ảnh nền sáng hơn" disabled={draft.version>=CONTENT_ATTEMPTS || pending} value={feedback} onChange={event=>setFeedback(event.target.value)}/><button type="button" className="button quiet" disabled={pending} onClick={()=>setFeedback('Ảnh nền sáng hơn')}>Ảnh nền sáng hơn</button>
    {unresolved && <p className="tiny muted">Đang chờ kết quả media; chưa thể làm lại.</p>}
    <div className="offer-actions"><button className="button secondary" data-retry disabled={pending || unresolved || draft.version>=CONTENT_ATTEMPTS} onClick={retry}><Icon name="refresh"/>Làm lại theo góp ý</button><button className="button" data-apply disabled={pending || unresolved || !ready || !(skip || videoReady && (reviewed===true || ack))} onClick={()=>onApply(selected,{skip_video:skip,video_review_ack:ack})}>Dùng bản này <Icon name="check"/></button></div>
  </section>;
}
