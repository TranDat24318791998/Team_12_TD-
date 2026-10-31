"""Token-protected tunnel entrypoint for owner-private Sites frontend. Core stays local."""
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from dotenv import dotenv_values
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,StreamingResponse
ROOT=Path(__file__).resolve().parents[1]

@asynccontextmanager
async def lifespan(app):
 config=dotenv_values(ROOT/'.env')
 app.state.token=os.environ.get('SITES_PROXY_TOKEN') or config.get('SITES_PROXY_TOKEN','')
 if len(app.state.token)<32:raise RuntimeError('Configure SITES_PROXY_TOKEN locally')
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=90,follow_redirects=False) as client:
  app.state.client=client
  yield

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
@app.api_route('/{path:path}',methods=['GET','HEAD','POST','PUT','PATCH','DELETE'])
async def forward(path:str,request:Request):
 token=request.headers.get('x-sites-proxy-token','')
 if not hmac.compare_digest(token,app.state.token):return JSONResponse({'error':{'message_vi':'Không có quyền truy cập'}},status_code=401)
 if not(path.startswith('api/') or path.startswith('media/')):return JSONResponse({'error':{'message_vi':'Không tìm thấy route'}},status_code=404)
 headers={k:v for k,v in request.headers.items() if k.lower() in ('content-type','cookie','range','if-none-match','idempotency-key','x-request-id')}
 # Explicit empty header prevents httpx's client cookie jar from leaking another browser session.
 headers['cookie']=request.headers.get('cookie','')
 url='/'+path+('?' + request.url.query if request.url.query else '')
 try:
  upstream=await app.state.client.send(app.state.client.build_request(request.method,url,headers=headers,content=await request.body()),stream=True)
 except httpx.HTTPError:return JSONResponse({'error':{'message_vi':'Backend chưa sẵn sàng'}},status_code=502)
 async def stream():
  try:
   async for chunk in upstream.aiter_raw():yield chunk
  finally:await upstream.aclose()
 response=StreamingResponse(stream(),status_code=upstream.status_code)
 response.raw_headers=[(k,v) for k,v in upstream.headers.raw if k.lower() not in (b'transfer-encoding',b'connection')]
 return response
