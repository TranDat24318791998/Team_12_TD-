import {CONTENT_ATTEMPTS} from '../config.js';
import {useState} from 'react';
import {Icon} from './Icon.jsx';
import {asset,mediaURL} from '../format.js';

export function ContentReview({draft,original,pending,onRetry,onApply,onNotice}){
  const [selected,setSelected]=useState(()=>draft.images.find(image=>['done','cached'].includes(image.status))?.option || 'A');
  const [feedback,setFeedback]=useState('');
  const ready=draft.images.some(image=>image.option===selected && ['done','cached'].includes(image.status) && mediaURL(image.path));
  const video=draft.video;const videoReady=video && ['done','cached'].includes(video.status) && mediaURL(video.path);
  async function retry(){if(!feedback.trim()){onNotice('Chị hãy nhập góp ý trước khi làm lại.');return;}await onRetry(feedback.trim());}
  return <section className="content-card"><div className="between"><h2>Nội dung mới cho sản phẩm</h2><span className="pill red">Lần {draft.version} / {CONTENT_ATTEMPTS}</span></div><p className="old-title">{original.title}</p><h3 className="new-title">{draft.title}</h3><p className="content-description">{draft.description}</p><div className="between" style={{marginBottom:9}}><strong className="tiny">Chọn ảnh bìa chị thích</strong><span className="tiny muted">{draft.images.length} phương án</span></div>
    <div className="cover-options" role="radiogroup" aria-label="Chọn ảnh bìa">{draft.images.map(image=>{const available=['done','cached'].includes(image.status) && mediaURL(image.path);return <label className="cover-choice" key={image.option}><input type="radio" name="cover-option" value={image.option} checked={selected===image.option} onChange={()=>setSelected(image.option)} disabled={!available || pending} aria-label={'Ảnh bìa '+image.option}/>{available?<img src={mediaURL(image.path)} alt={'Phương án ảnh bìa '+image.option} onError={event=>{if(!event.currentTarget.dataset.fallback){event.currentTarget.dataset.fallback='1';event.currentTarget.src=asset('product-placeholder.svg');}}}/>:<span className="cover-running"><Icon name="image"/>{image.status==='failed'?'Chưa tạo được ảnh':'Đang tạo ảnh…'}</span>}<span className="cover-label"><span>Phương án {image.option}</span><span>{selected===image.option?'Đã chọn':''}</span></span></label>;})}</div>
    <div className="video-preview"><Icon name="video"/> {videoReady?'Video sản phẩm đã sẵn sàng':video?.status==='failed'?'Chưa tạo được video, chị vẫn có thể dùng ảnh.':'Đang tạo video bằng Muse, khoảng 1–2 phút.'}{videoReady && <video controls preload="metadata" src={mediaURL(video.path)}/>}</div>
    {!!draft.checks?.length && <p className="tiny muted" style={{marginTop:12}}>✓ {draft.checks.join(' · ')}</p>}<div className="feedback-history">{(draft.feedback_history || []).map((text,i)=><span className="pill" key={i}>{text}</span>)}</div>
    <label className="feedback-label" htmlFor="content-feedback">Góp ý thêm · Còn {Math.max(0,CONTENT_ATTEMPTS-draft.version)} lần làm lại</label><textarea id="content-feedback" className="feedback-input" maxLength={1000} placeholder="Ví dụ: Ảnh nền sáng hơn, giữ rõ màu quạt…" disabled={draft.version>=CONTENT_ATTEMPTS || pending} value={feedback} onChange={event=>setFeedback(event.target.value)}/>
    <div className="offer-actions"><button className="button secondary" data-retry disabled={pending || draft.version>=CONTENT_ATTEMPTS} onClick={retry}><Icon name="refresh"/>Làm lại theo góp ý</button><button className="button" data-apply disabled={pending || !ready} onClick={()=>onApply(selected)}>Dùng bản này <Icon name="check"/></button></div>
  </section>;
}
