// Explicit legacy recovery against a disposable fake API; loading never mutates state.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {dirname,extname,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const {chromium}=require('/Applications/ChatGPT.app/Contents/Resources/cua_node/lib/node_modules/playwright');
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const server=createServer(async(req,res)=>{
  const path=resolve(root,'.'+new URL(req.url,'http://local').pathname);
  if(!path.startsWith(root+sep)){res.writeHead(403).end();return;}
  try{const data=await readFile(path);res.writeHead(200,{'content-type':({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'})[extname(path)] || 'application/octet-stream'}).end(data);}
  catch{res.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try{
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const page=await browser.newPage();
  const shop={shop_id:'D',name:'Shop kiểm thử',title:'Quạt',description:'Quạt',images:[],attributes:[]};
  const card={card_id:'c-restored',version:1,brief_version:2,negotiation_id:'n-original',kind:'offer',package:{content_refresh:true,ads_daily_budget:45000,voucher_pct:3,stop_roas_below:6.5,stop_after_days:2,duration_days:3},can_negotiate:true,forecast:{low:18,high:30},reasons_vi:[],warnings_vi:[]};
  const make=(seq,type,data)=>({seq,type,data,text_vi:'Góp ý',actor:'seller',run_id:'run-test',day:1,shop_id:'D',ts:'12:00'});
  let events=[make(1,'seller_decision',{target_type:'proposal',card_id:'c-old',action:'negotiate',note_vi:'giảm thêm'})];
  const original={run_id:'run-test',day:1,step:'day_done',demo_shop:shop,demo_shop_original:shop,mode:'offline',brief:{version:2},pending_card:null,busy:false,renegotiation:{source_card_id:'c-old',source_card_version:3,operation_id:'op-1',operation_version:4,negotiation_id:'n-failed',status:'failed',reason_vi:'Chưa có điều chỉnh phù hợp.',restoration_allowed:true,restoration_status:null}};
  let state=structuredClone(original),posts=[],blocked=false;
  await page.route('**/api/**',route=>{
    const req=route.request(),url=new URL(req.url());
    const reply=(status,body)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if(url.pathname==='/api/state')return reply(200,state);
    if(url.pathname==='/api/events'){
      const after=Number(url.searchParams.get('after') || 0);
      return reply(200,{run_id:'run-test',events:events.filter(event=>event.seq>after),last_seq:events.length,has_more:false});
    }
    if(url.pathname==='/api/negotiation/restore' && req.method()==='POST'){
      const body=req.postDataJSON();posts.push(body);assert.ok(req.headers()['idempotency-key']);
      if(body.expected_operation_version!==state.renegotiation.operation_version)return reply(409,{error:{code:'VERSION_CONFLICT',message_vi:'Trạng thái đã thay đổi.'}});
      assert.deepEqual(body,{operation_id:'op-1',expected_operation_version:5,source_card_id:'c-old',expected_source_card_version:3,expected_brief_version:2,expected_day:1});
      const restoration_status=blocked?'blocked':'restored';
      const result={restoration_status,restored_card_id:blocked?null:card.card_id,restoration_reason_vi:blocked?'Gói trước không còn hợp lệ.':''};
      state={...state,step:blocked?'day_done':'awaiting_decision',pending_card:blocked?null:card,renegotiation:{...state.renegotiation,...result,restoration_allowed:false}};
      if(!blocked)events.push(make(2,'card_sent',{card_id:card.card_id,negotiation_id:card.negotiation_id,card}));
      return reply(200,result);
    }
    return reply(404,{error:{message_vi:'Không tìm thấy'}});
  });
  const url='http://127.0.0.1:'+server.address().port+'/demo.html?preview=0';
  await page.goto(url);await page.getByRole('button',{name:'Xem lại gói trước'}).waitFor();
  await page.reload();await page.getByRole('button',{name:'Xem lại gói trước'}).waitFor();
  assert.equal(posts.length,0);assert.equal(await page.locator('[data-night]').count(),0);
  state={...state,renegotiation:{...state.renegotiation,operation_version:5}};
  await page.getByRole('button',{name:'Xem lại gói trước'}).click();
  await page.getByRole('alert').getByText(/Trạng thái đã thay đổi/).waitFor({timeout:5000});
  await page.waitForFunction(()=>!document.querySelector('.bubble .button.secondary').disabled);
  await page.getByRole('button',{name:'Xem lại gói trước'}).click();
  await page.locator('#chat-content').getByText(/Gói trước vẫn còn hiệu lực/).waitFor({timeout:5000});
  assert.equal(await page.locator('#chat-content [data-decision="accept"]').count(),1);assert.equal(await page.locator('[data-night]').count(),0);
  state={...structuredClone(original),renegotiation:{...original.renegotiation,operation_version:5}};events=[events[0]];blocked=true;
  await page.goto(url);await page.getByRole('button',{name:'Xem lại gói trước'}).click();
  await page.locator('#chat-content').getByText('Gói trước không còn hợp lệ.').waitFor({timeout:5000});
  assert.equal(await page.locator('#chat-content [data-decision="accept"]').count(),0);assert.equal(await page.locator('#chat-content [data-night]').count(),1);
  process.stdout.write('PASS: legacy recovery is explicit, version bound and refreshes after conflict; invalid old offers show a blocked reason.\n');
}finally{
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
