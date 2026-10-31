// An optional public deployment setting, never a credential. Empty means same origin.
export function configuredApiBase(){
  return typeof globalThis.SHOPPILOT_API_BASE_URL==='string'?globalThis.SHOPPILOT_API_BASE_URL.trim():'';
}

export function resolveApiPath(path,base=configuredApiBase()){
  if(!base || !/^\/(?:api|media)(?:\/|\?|$)/.test(path))return path;
  try{
    const url=new URL(base,globalThis.location?.href || 'http://localhost/');
    if(!['http:','https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash)return path;
    return url.href.replace(/\/+$/,'')+path;
  }catch{return path;}
}
