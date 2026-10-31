import {useEffect,useRef,useState} from 'react';
import {CONTENT_ATTEMPTS} from '../config.js';
import {asset,mediaURL} from '../format.js';
import {Icon} from './Icon.jsx';

const backgrounds=[
  {value:'clean_white',label:'Trắng tinh giản',image:'style-clean-white.jpg'},
  {value:'pastel_lifestyle',label:'Pastel nhẹ nhàng',image:'style-pastel-lifestyle.jpg'},
  {value:'premium_studio',label:'Studio cao cấp',image:'style-premium-studio.jpg'},
  {value:'summer_fresh',label:'Mùa hè tươi mát',image:'style-summer-fresh.jpg'},
];

// Only the server's draft stage advances the flow; selecting an option does not start a job.
export function MediaWizard({draft,current,pending,onImage,onVideo,onRetry,onApply}){
  const wizard=draft.wizard;
  const [background,setBackground]=useState(wizard.background || backgrounds[0].value);
  const [wishes,setWishes]=useState(wizard.wishes || '');
  const [character,setCharacter]=useState(null);
  const [duration,setDuration]=useState(20);
  const [ack,setAck]=useState(false);
  const [broken,setBroken]=useState({});
  const carousel=useRef(null);
  const index=Math.max(0,backgrounds.findIndex(item=>item.value===background));
  const image=draft.images?.find(item=>item.option==='A');
  const video=draft.video;
  const imageReady=['done','cached'].includes(image?.status) && !!mediaURL(image?.path) && !broken.image;
  const videoReady=['done','cached'].includes(video?.status) && !!mediaURL(video?.path) && !broken.video;
  const reviewed=video?.visual_review_passed ?? video?.review_passed;
  const source=mediaURL(draft.input_image) || mediaURL(current?.images?.[0]) || asset('demo-d-desktop.jpg');
  const inputReady=!broken['input:'+source];
  const durationMatches=video?.duration_matches_requested===true;
  const requestedDuration=video?.requested_duration_seconds ?? wizard.duration;
  const actualDuration=video?.duration_seconds;
  const durationText=value=>typeof value==='number' && Number.isFinite(value)?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(value)+' giây':'Chưa xác định';
  const needsAck=reviewed!==true || !durationMatches;
  const choose=wizard.stage==='choose_image';
  const imageWaiting=wizard.stage==='image_queued';
  const configureVideo=wizard.stage==='image_ready';
  const videoWaiting=wizard.stage==='video_queued';
  const complete=wizard.stage==='video_ready';
  const failed=wizard.stage==='failed';
  const canRetry=failed && !draft.outcome_unknown && draft.version<CONTENT_ATTEMPTS;
  const showResult=configureVideo || videoWaiting || complete || (failed && imageReady);
  const shownCharacter=videoWaiting?(wizard.output_type || character):character;
  const shownDuration=videoWaiting?(wizard.duration || duration):duration;
  const setStyleOffset=offset=>setBackground(backgrounds[Math.min(backgrounds.length-1,Math.max(0,index+offset))].value);
  useEffect(()=>{
    const track=carousel.current,selected=track?.querySelector('[aria-pressed="true"]');
    if(track && selected)track.scrollTo({left:selected.offsetLeft-track.offsetLeft-(track.clientWidth-selected.clientWidth)/2});
  },[background]);

  return <section className="content-card media-wizard" aria-label="Tạo ảnh và video sản phẩm">
    <div className="media-wizard-header">
      <div><p className="media-kicker">NỘI DUNG CHO SHOP</p><h2>Tạo ảnh và video sản phẩm</h2><p>Chọn phong cách, xem kết quả và duyệt trước khi cập nhật trang shop.</p></div>
      <span className="media-step">{complete?'3':showResult?'2':'1'} / 3</span>
    </div>

    {(choose || imageWaiting) && <>
      <div className="media-section-title"><strong>Ảnh đầu vào</strong><span>Đã có sẵn cho shop</span></div>
      <div className="media-inputs">
        <figure><img src={asset('seller-logo.jpg')} alt="Logo người bán"/><figcaption>Logo người bán</figcaption></figure>
        <figure>{inputReady?<img src={source} alt="Ảnh sản phẩm hiện có" onError={()=>setBroken(value=>({...value,['input:'+source]:true}))}/>:<span className="media-input-unavailable" role="alert">Không tải được ảnh đầu vào</span>}<figcaption>Ảnh sản phẩm hiện có</figcaption></figure>
      </div>
      <div className="media-section-title"><strong>Chọn phong cách nền</strong><span>{index+1} / {backgrounds.length}</span></div>
      <div className="background-carousel" role="group" aria-label="Phong cách nền" ref={carousel}>
        {backgrounds.map(style=><button type="button" key={style.value} className={'background-choice'+(background===style.value?' active':'')} aria-pressed={background===style.value} onClick={()=>setBackground(style.value)} disabled={!choose || pending}>
          <img src={asset(style.image)} alt=""/><span>{style.label}</span>{background===style.value && <i aria-hidden="true"><Icon name="check"/></i>}
        </button>)}
      </div>
      <div className="background-controls">
        <button type="button" className="background-arrow" aria-label="Phong cách trước" onClick={()=>setStyleOffset(-1)} disabled={!choose || pending || index===0}>‹</button>
        <input type="range" min="0" max={backgrounds.length-1} step="1" value={index} aria-label="Chọn phong cách nền" aria-valuetext={backgrounds[index].label} onChange={event=>setBackground(backgrounds[Number(event.target.value)].value)} disabled={!choose || pending}/>
        <button type="button" className="background-arrow" aria-label="Phong cách tiếp theo" onClick={()=>setStyleOffset(1)} disabled={!choose || pending || index===backgrounds.length-1}>›</button>
      </div>
      <label className="media-label" htmlFor="seller-wishes">Mong muốn thêm <span>Không bắt buộc</span></label>
      <textarea id="seller-wishes" className="media-wishes" maxLength={1000} rows={3} placeholder="Ví dụ: Giữ màu quạt, ánh sáng dịu và cảm giác gần gũi…" value={wishes} onChange={event=>setWishes(event.target.value)} disabled={!choose || pending}/>
      {imageWaiting?<p className="media-progress" role="status"><span className="media-spinner"/>Đang tạo ảnh theo lựa chọn của chị…</p>:<button type="button" className="button media-primary" data-generate-image disabled={!!pending || !inputReady} onClick={()=>onImage({background,wishes:wishes.trim()})}>Tiếp tục tạo ảnh <Icon name="arrow"/></button>}
    </>}

    {showResult && <>
      <div className="media-section-title"><strong>Ảnh sản phẩm mới</strong><span>{image?.source || ''}</span></div>
      {imageReady?<div className="generated-image"><img src={mediaURL(image.path)} alt="Ảnh sản phẩm mới đã tạo" onError={()=>setBroken(value=>({...value,image:true}))}/></div>:<p className="media-error" role="alert">Không tải được ảnh sản phẩm mới.</p>}
    </>}

    {(configureVideo || videoWaiting) && <>
      <div className="media-section-title"><strong>Chọn nhân vật cho video</strong><span>Chọn một kiểu</span></div>
      <div className="character-options" role="radiogroup" aria-label="Nhân vật video">
        {[{value:'realistic_human',label:'Người thật',description:'Phong cách chân thực',icon:'user'},{value:'chibi_3d',label:'Chibi 3D',description:'Nhân vật hoạt hình',icon:'spark'}].map(option=><label key={option.value} className={'character-choice'+(shownCharacter===option.value?' active':'')}><input type="radio" name="video-character" value={option.value} checked={shownCharacter===option.value} onChange={()=>setCharacter(option.value)} disabled={!configureVideo || pending}/><span className="character-icon"><Icon name={option.icon}/></span><span><strong>{option.label}</strong><small>{option.description}</small></span></label>)}
      </div>
      <fieldset className="duration-field" disabled={!configureVideo || pending}><legend>Thời lượng video</legend><div className="duration-options">{[5,10,15,20].map(value=><label key={value} className={shownDuration===value?'active':''}><input type="radio" name="video-duration" value={value} checked={shownDuration===value} onChange={()=>setDuration(value)}/>{value} giây</label>)}</div></fieldset>
      {videoWaiting?<p className="media-progress" role="status"><span className="media-spinner"/>Đang tạo video từ ảnh chị đã chọn…</p>:<button type="button" className="button media-primary" data-generate-video disabled={!!pending || !imageReady || !character} onClick={()=>onVideo({output_type:character,duration})}>Tạo video <Icon name="arrow"/></button>}
    </>}

    {complete && <>
      <div className="media-section-title"><strong>Video sản phẩm</strong><span>Sẵn sàng để xem</span></div>
      {videoReady?<video className="generated-video" controls preload="metadata" src={mediaURL(video.path)} onError={()=>setBroken(value=>({...value,video:true}))}/>:<p className="media-error" role="alert">Không tải được video. Hãy kiểm tra lại kết quả trước khi sử dụng.</p>}
      <div className={'media-duration'+(!durationMatches?' warning':'')}><strong>Thời lượng</strong><p>Đã chọn: {durationText(requestedDuration)} · Thực tế: {durationText(actualDuration)}</p>{!durationMatches && <p>{video?.duration_matches_requested===false?'Thời lượng thực tế khác với lựa chọn của chị.':'Chưa xác nhận được thời lượng thực tế.'}</p>}</div>
      {video?.short_description && <div className="media-description"><strong>Mô tả ngắn</strong><p>{video.short_description}</p></div>}
      {(draft.title || draft.description) && <div className="media-description"><strong>Nội dung sản phẩm đề xuất</strong>{draft.title && <p><b>{draft.title}</b></p>}{draft.description && <p>{draft.description}</p>}</div>}
      {(video?.review_notes_vi || video?.review_notes) && <p className="tiny muted media-review-note">{video.review_notes_vi || video.review_notes}</p>}
      {videoReady && needsAck && <label className="media-ack"><input type="checkbox" checked={ack} onChange={event=>setAck(event.target.checked)}/>Tôi đã xem video và đồng ý sử dụng bản này.</label>}
      <button type="button" className="button media-primary" data-use-media disabled={!!pending || !imageReady || !videoReady || (needsAck && !ack)} onClick={()=>onApply('A',{skip_video:false,video_review_ack:ack})}>Sử dụng media <Icon name="check"/></button>
    </>}

    {failed && <div className="media-failure" role="alert"><strong>Chưa hoàn tất tạo media.</strong><p>{draft.outcome_unknown?'Kết quả chưa rõ; cần kiểm tra trạng thái trước khi thử lại.':draft.error_code || 'Vui lòng thử lại khi dịch vụ sẵn sàng.'}</p>{canRetry && <button type="button" className="button secondary" disabled={!!pending} onClick={()=>onRetry(wishes.trim() || 'Thử lại sau khi tạo media chưa thành công.')}>Thử lại từ bước tạo ảnh</button>}</div>}
  </section>;
}
