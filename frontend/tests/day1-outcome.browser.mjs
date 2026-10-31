// Exercise the initial attempt with an isolated fake API, including reload and polling order.
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
  let state={run_id:'run-test',day:1,step:'negotiating',demo_shop:shop,demo_shop_original:shop,mode:'offline',pending_card:null,busy:true,negotiation:{negotiation_id:'n-1',status:'running'}};
  const make=(seq,type,data,text_vi='')=>({seq,type,data,text_vi,actor:type==='referee_review'?'referee':'platform_agent',run_id:'run-test',day:1,shop_id:'D',ts:'12:00'});
  let events=[make(1,'platform_turn',{negotiation_id:'n-1',round:1,action:'accept'},'Agent sàn chấp nhận'),make(2,'referee_review',{negotiation_id:'n-1',round:1,action:'stop'},'Cần xem lại điều kiện.')];
  await page.route('**/api/**',route=>{
    const url=new URL(route.request().url());
    const reply=(status,body)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if(url.pathname==='/api/state')return reply(200,state);
    if(url.pathname==='/api/events'){
      const after=Number(url.searchParams.get('after') || 0);
      return reply(200,{run_id:'run-test',events:events.filter(event=>event.seq>after),last_seq:events.at(-1)?.seq || 0,has_more:false});
    }
    return reply(404,{error:{message_vi:'Không tìm thấy'}});
  });
  await page.goto('http://127.0.0.1:'+server.address().port+'/demo.html?preview=0');
  await page.locator('#chat-content').getByText(/đang trao đổi/).waitFor();
  events.push(make(3,'negotiation_finished',{negotiation_id:'n-1',status:'failed',reason_vi:'Cần xem lại điều kiện.',referee_action:'stop'}));
  await page.waitForTimeout(1800);
  assert.equal(await page.locator('#chat-content [data-night]').count(),0);
  assert.equal(await page.locator('#chat-content').getByText('Đã ghi nhận lựa chọn của chị.').count(),0);
  state={...state,step:'day_done',busy:false,negotiation:{negotiation_id:'n-1',status:'failed',reason_vi:'Cần xem lại điều kiện.',referee_action:'stop'}};
  await page.locator('#chat-content').getByText('Chưa có gói để chị duyệt.').waitFor({timeout:5000});
  assert.equal(await page.locator('#chat-content').getByText('Cần xem lại điều kiện.').count(),1);
  assert.equal(await page.locator('.steps li.skipped').count(),3);
  assert.equal(await page.locator('#chat-content [data-night]').count(),1);
  await page.reload();
  await page.locator('#chat-content').getByText('Chưa có gói để chị duyệt.').waitFor({timeout:5000});
  assert.equal(await page.locator('#chat-content').getByText('Đã ghi nhận lựa chọn của chị.').count(),0);
  state={...state,negotiation:{negotiation_id:'n-1',status:'unknown',reason_vi:'Kết quả chưa rõ.',referee_action:null}};
  await page.locator('#chat-content').getByText('Kết quả chưa rõ.').waitFor({timeout:5000});
  assert.equal(await page.locator('[data-night]').count(),0);
  const card={card_id:'c-1',negotiation_id:'n-1',kind:'offer',package:{content_refresh:false,ads_daily_budget:0,voucher_pct:3,stop_roas_below:null,stop_after_days:null,duration_days:3},forecast:{low:10,high:12},reasons_vi:[],warnings_vi:[]};
  state={...state,step:'awaiting_decision',pending_card:card,negotiation:{negotiation_id:'n-1',status:'agreed'}};
  events.push(make(4,'card_sent',{card_id:'c-1',negotiation_id:'n-1',card}));
  await page.locator('#chat-content [data-decision="accept"]').waitFor({timeout:5000});
  assert.equal(await page.locator('#chat-content').getByText('Chưa có gói để chị duyệt.').count(),0);
  process.stdout.write('PASS: initial terminal stop shows its own reason and skipped steps after reload; unknown stays open; a valid card is available to the seller.\n');
}finally{
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
