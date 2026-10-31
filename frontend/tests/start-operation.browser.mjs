// Real React interaction in a private headless browser against a fake local API.
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
const base='http://127.0.0.1:'+server.address().port;
let browser;
try{
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const shop={shop_id:'D',name:'Shop kiểm thử',category:'quat_mini',price:175000,stock:300,rating:4.6,
              title:'Quạt để bàn',description:'Một quạt',images:[],attributes:[],listing_quality:.5,search_rank_page:1};
  const initial=()=>({run_id:'run-test',day:1,step:'idle',brief:{confirmed:true},demo_shop:shop,demo_shop_original:shop,
    mode:'offline',memory_enabled:true,simulation_days:7,pending_card:null,content_draft:null,active_package:null,busy:false});
  const event={seq:1,run_id:'run-test',day:1,shop_id:'D',ts:'09:00',type:'agent_activity',actor:'platform_agent',
    text_vi:'Agent đang kiểm thử',data:{negotiation_id:'neg-1',task_id:'task-1',round:1,phase:'proposal',status:'running',label_vi:'Agent đang kiểm thử'}};
  const context=await browser.newContext();
  const page=await context.newPage();
  let state=initial(),posts=0,rejectStart=false;
  await page.route('**/api/**',async route=>{
    const req=route.request(),url=new URL(req.url());
    const reply=(status,body)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if(url.pathname==='/api/state')return reply(200,state);
    if(url.pathname==='/api/events'){
      const after=Number(url.searchParams.get('after') || 0);
      return reply(200,{run_id:state.run_id,events:posts && after<1?[event]:[],last_seq:posts?1:0,has_more:false});
    }
    if(url.pathname==='/api/day/start' && req.method()==='POST'){
      posts++;
      assert.ok(req.headers()['idempotency-key']);
      if(rejectStart)return reply(409,{error:{code:'BRIEF_REQUIRED',message_vi:'Cần xác nhận mục tiêu'}});
      state={...state,step:'negotiating',busy:true,active_operation:{operation_id:'op-1',status:'running'}};
      return reply(202,{day:1,step:'negotiating',operation_id:'op-1',status:'running'});
    }
    return reply(404,{error:{code:'NOT_FOUND',message_vi:'Không tìm thấy'}});
  });
  await page.goto(base+'/index.html?preview=0');
  await page.locator('[data-start]').click();
  await page.waitForURL('**/demo.html?preview=0',{timeout:5000});
  await page.locator('#event-feed').getByText('Agent đang kiểm thử').waitFor({timeout:5000});
  assert.equal(posts,1);
  assert.equal(state.active_operation.status,'running');
  state={...state,step:'day_done',busy:false,active_operation:{operation_id:'op-1',status:'failed',error_code:'TEST_OPERATION_FAILED'}};
  await page.getByRole('alert').getByText(/TEST_OPERATION_FAILED/).waitFor({timeout:5000});
  assert.equal(posts,1);
  state=initial();posts=0;rejectStart=true;
  await page.goto(base+'/index.html?preview=0');
  await page.locator('[data-start]').click();
  await page.getByRole('alert').getByText(/Cần xác nhận mục tiêu/).waitFor({timeout:5000});
  assert.match(page.url(),/index\.html/);
  assert.equal(posts,1);
  await context.close();
  process.stdout.write('PASS: accepted start opens Demo while running, streams events and reports failure; rejected start stays on Shop.\n');
}finally{
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
