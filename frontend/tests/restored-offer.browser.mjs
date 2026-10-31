// Drive restored offers and stale-version recovery in an isolated fake seller API.
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
  const context=await browser.newContext({viewport:{width:1440,height:1400}}),page=await context.newPage();
  const shop={shop_id:'D',name:'Shop kiểm thử',title:'Quạt',description:'Quạt',images:[],attributes:[]};
  const pkg={content_refresh:true,ads_daily_budget:45000,voucher_pct:3,stop_roas_below:6.5,stop_after_days:2,duration_days:3};
  const makeCard=(id,left,version=1)=>({card_id:id,version,brief_version:2,negotiation_id:'n-original',kind:'offer',package:pkg,can_negotiate:left>0,renegotiations_left:left,forecast:{low:18,high:30},reasons_vi:[],warnings_vi:[]});
  const make=(seq,type,data,text_vi='')=>({seq,type,data,text_vi,actor:type==='seller_decision'?'seller':'system',run_id:'run-test',day:1,shop_id:'D',ts:'12:00'});
  let state,events,count,calls,postBodies;
  function reset(){
    const card=makeCard('c-1',2);
    state={run_id:'run-test',day:1,step:'awaiting_decision',demo_shop:shop,demo_shop_original:shop,mode:'offline',pending_card:card,busy:false};
    events=[make(1,'card_sent',{card_id:card.card_id,negotiation_id:card.negotiation_id,card})];count=0;calls=0;postBodies=[];
  }
  reset();
  await page.route('**/api/**',route=>{
    const req=route.request(),url=new URL(req.url());
    const reply=(status,body)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if(url.pathname==='/api/state')return reply(200,state);
    if(url.pathname==='/api/events'){
      const after=Number(url.searchParams.get('after') || 0);
      return reply(200,{run_id:state.run_id,events:events.filter(event=>event.seq>after),last_seq:events.length,has_more:false});
    }
    if(url.pathname==='/api/decision'){
      calls++;const body=req.postDataJSON();postBodies.push(body);
      if(body.card_id!==state.pending_card?.card_id || body.expected_card_version!==state.pending_card?.version || body.expected_brief_version!==state.pending_card?.brief_version)
        return reply(409,{error:{code:'STALE_CARD',message_vi:'Thẻ đã thay đổi.'}});
      const selected=state.pending_card;
      events.push(make(events.length+1,'seller_decision',{target_type:'proposal',card_id:selected.card_id,action:body.action,note_vi:body.note_vi},'Quyết định'));
      if(body.action==='negotiate'){
        count++;const restored=makeCard('c-restored-'+count,2-count);
        state={...state,step:'awaiting_decision',pending_card:restored,renegotiation:{source_card_id:selected.card_id,negotiation_id:'n-failed-'+count,status:'failed',reason_vi:'Chưa thể giảm thêm.',restoration_status:'restored',restored_card_id:restored.card_id}};
        events.push(make(events.length+1,'card_sent',{card_id:restored.card_id,negotiation_id:restored.negotiation_id,card:restored},'Gói trước'));
      }else if(body.action==='accept'){
        state={...state,step:'content_review',pending_card:null,content_draft:{version:1,card_id:selected.card_id,job_id:'job-1',status:'running',title:'Tiêu đề',description:'Mô tả',images:[],video:{status:'running'},feedback_history:[]}};
      }else state={...state,step:'day_done',pending_card:null};
      return reply(200,{step:state.step,card:state.pending_card});
    }
    return reply(404,{error:{message_vi:'Không tìm thấy'}});
  });
  const base='http://127.0.0.1:'+server.address().port+'/demo.html?preview=0';
  async function requestMore(){
    await page.locator('#seller-message').fill('giảm thêm dc khong');
    await page.getByRole('button',{name:'Gửi yêu cầu thương lượng'}).click();
    await page.locator('#chat-content').getByText(/Gói trước vẫn còn hiệu lực/).waitFor({timeout:5000});
    await page.waitForFunction(()=>!document.querySelector('[data-decision="accept"]').disabled);
  }
  await page.goto(base);await requestMore();
  assert.equal(await page.locator('#chat-content [data-night]').count(),0);
  assert.equal(await page.locator('#chat-content [data-decision="accept"]').count(),1);
  assert.match(await page.locator('.offer-card').innerText(),/45\.000đ\/ngày/);
  await page.locator('.offer-card').scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/day1-restored-offer.png'});
  await page.reload();
  await page.locator('#chat-content').getByText(/Gói trước vẫn còn hiệu lực/).waitFor({timeout:5000});
  await requestMore();
  assert.equal(await page.locator('[data-negotiate]').isDisabled(),true);
  assert.equal(await page.locator('#composer').isHidden(),true);
  assert.equal(postBodies.filter(item=>item.action==='negotiate').length,2);
  state={...state,pending_card:{...state.pending_card,version:2}};
  await page.locator('[data-decision="accept"]').click();
  await page.getByRole('alert').getByText(/Thẻ đã thay đổi/).waitFor({timeout:5000});
  await page.waitForFunction(()=>!document.querySelector('[data-decision="accept"]').disabled);
  await page.locator('[data-decision="accept"]').click();
  await page.locator('.content-card').waitFor({timeout:5000});
  assert.equal(postBodies.at(-1).card_id,'c-restored-2');assert.equal(postBodies.at(-1).expected_card_version,2);
  reset();await page.goto(base);await requestMore();
  await page.locator('[data-decision="reject"]').click();
  await page.locator('#chat-content').getByText('Đã ghi nhận lựa chọn của chị.').waitFor({timeout:5000});
  assert.equal(await page.locator('#chat-content [data-night]').count(),1);
  assert.equal(state.step,'day_done');assert.equal(state.content_draft,undefined);
  process.stdout.write('PASS: restored offers survive reload; retry cap, stale-version refresh, accept to content, and reject to day end work with the current card.\n');
}finally{
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
