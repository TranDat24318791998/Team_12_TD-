function sourceURL(value){
  if(typeof value!=='string' || !value.trim())return null;
  try{
    const base=globalThis.location?.origin && globalThis.location.origin!=='null'?globalThis.location.origin:'http://localhost';
    const url=new URL(value,base);
    return url.origin===base && ['http:','https:'].includes(url.protocol) && url.pathname.startsWith('/api/')?url.pathname+url.search+url.hash:null;
  }catch{return null;}
}

export function CheckSources({sources,inline=false}){
  const items=Array.isArray(sources)?sources.filter(source=>typeof source?.title_vi==='string' && source.title_vi.trim()):[];
  if(!items.length)return null;
  const list=<ul>{items.map((source,index)=>{
    const url=sourceURL(source.download_url);
    return <li key={index}><div>{url?<a href={url} target="_blank" rel="noopener noreferrer">{source.title_vi}</a>:<span>{source.title_vi}</span>}{source.version!=null && <> · Phiên bản {String(source.version)}</>}{source.excerpt_vi && <p>{source.excerpt_vi}</p>}</div></li>;
  })}</ul>;
  return inline?<div className="check-sources"><strong>Nguồn:</strong>{list}</div>:<details className="check-sources"><summary>Nguồn kiểm tra ({items.length})</summary>{list}</details>;
}
