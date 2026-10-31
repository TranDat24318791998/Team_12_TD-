export const vnd=value=>value==null || !Number.isFinite(Number(value))?'—':new Intl.NumberFormat('vi-VN',{maximumFractionDigits:0}).format(value)+'đ';
export const dec=(value,digits=1)=>value==null || !Number.isFinite(Number(value))?'—':new Intl.NumberFormat('vi-VN',{minimumFractionDigits:digits,maximumFractionDigits:digits}).format(value);
export const baseURL=new URL('../',import.meta.url);
export const asset=name=>new URL('img/'+name,baseURL).href;
export function mediaURL(value,base=globalThis.location?.href || 'http://localhost/'){
  if(!value)return '';
  try{
    if(/^(media|assets)\//.test(value))value='/'+value;
    const url=new URL(value,base);
    return ['http:','https:'].includes(url.protocol) || (base.startsWith('file:') && url.protocol==='file:')?url.href:'';
  }catch{return '';}
}
export function pageURL(name,preview){const url=new URL(name,baseURL);url.searchParams.set('preview',preview?'1':'0');return url.href;}
export const modeLabel=mode=>({live:'Trực tiếp',replay:'Phát lại',offline:'Luật cố định'}[mode] || 'Chưa xác định');
export const sourceLabel=source=>{const labels={live:'Trực tiếp từ LLM',replay:'Phát lại',offline:'Ngoại tuyến (quy tắc dự phòng)',fixture:'Mẫu thử',skipped:'Đã bỏ qua'};return typeof source==='string' && source?(Object.hasOwn(labels,source)?labels[source]:source):'Chưa có dữ liệu';};
export const categoryLabel=category=>({quat_mini:'Quạt mini'}[category] || category || 'Chưa có danh mục');
export function colorsFor(shop){const attr=(shop.attributes || []).find(text=>/màu\s*:/iu.test(text));return attr?attr.split(':').slice(1).join(':').split(/[,;|]/).map(text=>text.trim()).filter(Boolean):[];}
export function changedFields(shop,original){return [['title','Tiêu đề'],['description','Mô tả'],['images','Ảnh sản phẩm'],['video','Video'],['active_voucher_pct','Voucher']].filter(([key])=>JSON.stringify(shop[key])!==JSON.stringify(original[key])).map(([key,label])=>({key,label}));}
export function download(name,value,type='application/json'){const url=URL.createObjectURL(new Blob([value],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export const actorNames={platform_agent:'AGENT SÀN',shop_agent:'AGENT SHOP',referee:'TRỌNG TÀI',seller:'NGƯỜI BÁN',code:'CODE KIỂM TRA',memory:'BỘ NHỚ',content_agent:'AGENT NỘI DUNG',system:'HỆ THỐNG',market:'THỊ TRƯỜNG'};
