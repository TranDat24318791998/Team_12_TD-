import httpx
from fastapi.testclient import TestClient
from scripts.sites_gateway import app

def test_gateway_only_forwards_each_browser_cookie(monkeypatch):
 monkeypatch.setenv('SITES_PROXY_TOKEN','x'*48)
 seen=[]
 def upstream(request):
  seen.append(request.headers.get('cookie'))
  class Body(httpx.AsyncByteStream):
   async def __aiter__(self):yield b'{"ok":true}'
  return httpx.Response(200,stream=Body(),headers={'set-cookie':'growth_sid=alice; Path=/; HttpOnly'})
 with TestClient(app) as client:
  app.state.client=httpx.AsyncClient(base_url='http://127.0.0.1:8000',transport=httpx.MockTransport(upstream))
  assert client.get('/api/state').status_code==401
  h={'X-Sites-Proxy-Token':'x'*48}
  assert client.get('/api/state',headers=h).status_code==200
  client.cookies.clear()
  assert client.get('/api/state',headers=h).status_code==200
  assert seen==['','']
  assert client.get('/internal/secrets',headers=h).status_code==404
