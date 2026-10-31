import {useState} from 'react';
import {Icon} from './Icon.jsx';
import {asset,categoryLabel,changedFields,colorsFor,dec,mediaURL,vnd} from '../format.js';

export function Product({shop,original,onAddCart,onNotice}){
  const images=(shop.images?.length?shop.images:[asset('product-placeholder.svg')]).slice(0,4);
  const displayURL=value=>mediaURL(value) || asset('product-placeholder.svg');
  const [imageIndex,setImageIndex]=useState(0),[color,setColor]=useState(null),[quantity,setQuantity]=useState(1),[showVideo,setShowVideo]=useState(false);
  const changes=original?changedFields(shop,original).map(change=>change.key):[];
  const mark=key=>changes.includes(key)?<span className="badge-new">Mới</span>:null;
  const colors=colorsFor(shop);const swatches={'trắng':'#e6e9df','hồng':'#e7bdbd','xanh mint':'#b8d5c2'};
  const fallback=event=>{if(!event.currentTarget.dataset.fallback){event.currentTarget.dataset.fallback='1';event.currentTarget.src=asset('product-placeholder.svg');event.currentTarget.alt+=' (ảnh thay thế)';}};
  return <>
    <div className="card"><div className="product-top">
      <div className="gallery"><div className="hero-image">{mark('images')}<span className="image-caption">{shop.name}</span><img id="product-hero" key={displayURL(images[imageIndex] || images[0])} src={displayURL(images[imageIndex] || images[0])} alt={`${shop.title} · ${shop.name}`} fetchPriority="high" onError={fallback}/></div>
        <div className="thumbnails">{images.map((src,i)=><button key={src+i} className={'thumb '+(i===imageIndex?'active':'')} data-thumb={displayURL(src)} onClick={()=>setImageIndex(i)} aria-label={'Xem ảnh sản phẩm '+(i+1)} aria-pressed={i===imageIndex}><img src={displayURL(src)} alt={'Ảnh sản phẩm '+(i+1)} onError={fallback}/></button>)}<button className="thumb video-thumb" data-product-video onClick={()=>shop.video?setShowVideo(!showVideo):onNotice('Sản phẩm chưa có video.')}><Icon name="video"/><span>{shop.video?'Xem video':'Chưa có video'}</span></button></div>
        {showVideo && shop.video && <video controls src={mediaURL(shop.video)} style={{width:'100%',marginTop:12}}/>}
        <div className="gallery-foot"><span>Ảnh sản phẩm</span><span><Icon name="heart"/> {shop.name}</span></div>
      </div>
      <section className="product-info" aria-label="Thông tin sản phẩm"><h1 className="product-title"><span className="seller-tag">{shop.name}</span>{mark('title')}{shop.title}</h1>
        <div className="rating-row"><span className="rating"><u>{dec(shop.rating)}</u><span className="stars" aria-hidden="true">★</span></span><span>Kho: <strong>{dec(shop.stock,0)}</strong></span><span>Dữ liệu giả lập</span></div>
        <div className="price-block"><div className="price">{vnd(shop.price)}</div><div className="price-note">Giá niêm yết của sản phẩm trong mô phỏng</div></div>
        <div className="detail-row"><span className="detail-label">Voucher shop</span><div>{mark('active_voucher_pct')}{shop.active_voucher_pct?<span className="ticket"><Icon name="voucher"/>Giảm {dec(shop.active_voucher_pct,0)}%</span>:<span className="muted">Chưa có voucher</span>}</div></div>
        <div className="detail-row"><span className="detail-label">Vận chuyển</span><div className="flex"><Icon name="shield"/><span>Đơn hàng mô phỏng<br/><small className="muted">Không phát sinh giao dịch thực</small></span></div></div>
        {colors.length>0 && <div className="detail-row"><span className="detail-label">Màu sắc</span><div className="color-options" role="group" aria-label="Chọn màu sản phẩm">{colors.map((value,i)=><button key={value} className={'color-chip '+((color || colors[0])===value?'active':'')} data-color={value} aria-pressed={(color || colors[0])===value} onClick={()=>setColor(value)}><i className="swatch" style={{background:swatches[value.toLocaleLowerCase('vi-VN')] || '#dedbd8'}}/>{value}</button>)}</div></div>}
        <div className="detail-row"><label className="detail-label" htmlFor="quantity">Số lượng</label><div className="quantity"><button data-qty="-1" aria-label="Giảm số lượng" onClick={()=>setQuantity(Math.max(1,quantity-1))}>−</button><output id="quantity" aria-live="polite">{quantity}</output><button data-qty="1" aria-label="Tăng số lượng" onClick={()=>setQuantity(Math.min(shop.stock || 1,quantity+1))}>+</button></div></div>
        <div className="buy-actions"><button className="button secondary" data-add-cart disabled={!shop.stock} onClick={()=>onAddCart(quantity)}><Icon name="cart"/>Thêm vào giỏ hàng</button><button className="button" data-buy disabled={!shop.stock} onClick={()=>onNotice('Đây là sản phẩm mô phỏng. Bấm “Bắt đầu demo” để trải nghiệm trợ lý tăng trưởng.')}>Mua ngay</button></div><div className="assurance"><Icon name="shield"/>Chủ shop luôn duyệt trước mọi thay đổi.</div>
      </section>
    </div><div className="shop-strip">{shop.shop_id==='D'?<img className="shop-logo" src={asset('shoppilot-ai.png')} alt="Logo ShopPilot AI"/>:<div className="avatar" aria-hidden="true">{(shop.name || 'S').trim().slice(0,1).toUpperCase()}</div>}<div><div className="shop-title">{shop.name}</div><span className="tiny muted">Cửa hàng trong mô phỏng</span></div><div className="shop-stats"><div>Chất lượng listing<strong>{dec(shop.listing_quality,2)} / 1</strong></div><div>Trang tìm kiếm<strong>Trang {dec(shop.search_rank_page,0)}</strong></div><div>Đánh giá<strong>{dec(shop.rating)} / 5</strong></div></div></div></div>
    <section className="card details-card"><h2 className="section-title">CHI TIẾT SẢN PHẨM</h2><dl className="attributes"><dt>Danh mục</dt><dd>{categoryLabel(shop.category)}</dd><dt>Thuộc tính</dt><dd>{(shop.attributes || []).join(' · ')}</dd><dt>Shop</dt><dd>{shop.name}</dd></dl><h2 className="section-title">{mark('description')}MÔ TẢ SẢN PHẨM</h2><p className="description">{shop.description}</p></section>
  </>;
}
