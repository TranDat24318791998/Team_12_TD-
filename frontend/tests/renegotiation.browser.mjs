// Real React polling and reload against a disposable local API, with no product DB.
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
  const pkg={content_refresh:false,ads_daily_budget:0,voucher_pct:3,stop_roas_below:null,stop_after_days:null,duration_days:3};
  const card={card_id:'c-1',version:1,brief_version:1,negotiation_id:'n-1',kind:'offer',package:pkg,forecast:{low:10,high:12},reasons_vi:[],warnings_vi:[]};
  let state={run_id:'run-test',day:1,step:'awaiting_decision',demo_shop:shop,demo_shop_original:shop,mode:'offline',pending_card:card,busy:false};
  const make=(seq,type,data,text_vi='')=>({seq,type,data,text_vi,actor:type==='seller_decision'?'seller':'system',run_id:'run-test',day:1,shop_id:'D',ts:'12:00'});
  let events=[make(1,'card_sent',{card_id:'c-1',negotiation_id:'n-1',card})],operation='running';
  await page.route('**/api/**',route=>{
    const req=route.request(),url=new URL(req.url());
    const reply=(status,body)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if(url.pathname==='/api/state')return reply(200,state);
    if(url.pathname==='/api/events'){
      const after=Number(url.searchParams.get('after') || 0);
      return reply(200,{run_id:'run-test',events:events.filter(event=>event.seq>after),last_seq:events.length,has_more:false});
    }
    if(url.pathname==='/api/decision'){
      assert.equal(req.postDataJSON().note_vi,'giảm thêm dc khong');
      events.push(make(2,'seller_decision',{card_id:'c-1',action:'negotiate',note_vi:'giảm thêm dc khong'},'Góp ý'));
      return reply(202,{operation_id:'op-1',status:'running'});
    }
    if(url.pathname==='/api/v1/runs/run-test/operations/op-1')return reply(200,{status:operation});
    return reply(404,{error:{message_vi:'Không tìm thấy'}});
  });
  await page.goto('http://127.0.0.1:'+server.address().port+'/demo.html?preview=0');
  await page.locator('#seller-message').fill('giảm thêm dc khong');
  await page.getByRole('button',{name:'Gửi yêu cầu thương lượng'}).click();
  await page.locator('#chat-content').getByText('giảm thêm dc khong').waitFor({timeout:5000});
  await page.locator('#chat-content').getByText(/đang trao đổi/).waitFor();
  assert.equal(await page.locator('#chat-content [data-decision]').count(),0);
  assert.equal(await page.locator('[data-night]').count(),0);
  state={...state,step:'day_done',pending_card:null,renegotiation:{source_card_id:'c-1',negotiation_id:'n-2',status:'running'}};
  await page.waitForTimeout(2000);
  assert.equal(await page.locator('[data-night]').count(),0);
  state={...state,renegotiation:{source_card_id:'c-1',negotiation_id:'n-2',status:'failed',restoration_status:'blocked',restoration_reason_vi:'Gói trước không còn hợp lệ.',referee_action:'ask_human',reason_vi:'Cần người bán xem lại yêu cầu.'}};
  operation='succeeded';
  await page.locator('#chat-content').getByText('Cần người bán xem lại yêu cầu.').waitFor({timeout:6000});
  assert.equal(await page.locator('#chat-content [data-night]').count(),1);
  await page.reload();
  await page.locator('#chat-content').getByText('Cần người bán xem lại yêu cầu.').waitFor({timeout:6000});
  assert.equal(await page.locator('#chat-content').getByText('Đã ghi nhận lựa chọn của chị.').count(),0);
  const nextCard={...card,card_id:'c-2',negotiation_id:'n-2',package:{...pkg,voucher_pct:2}};
  state={...state,step:'awaiting_decision',pending_card:nextCard,renegotiation:{source_card_id:'c-1',negotiation_id:'n-2',status:'agreed',changed:true}};
  events.push(make(3,'card_sent',{card_id:'c-2',negotiation_id:'n-2',card:nextCard}));
  await page.locator('#chat-content').getByText(/gói điều chỉnh để chị xem lại/).waitFor({timeout:6000});
  assert.equal(await page.locator('#chat-content [data-decision="accept"]').count(),1);
  assert.equal(await page.locator('#chat-content [data-night]').count(),0);
  process.stdout.write('PASS: feedback hides stale controls, preserves waiting across poll order, shows the bound terminal reason after reload, and offers the new card for review.\n');
}finally{
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
