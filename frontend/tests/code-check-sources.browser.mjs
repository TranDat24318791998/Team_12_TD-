// Render a historical check in an isolated browser and follow its document link.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {dirname,extname,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const require=createRequire(import.meta.url);
const {chromium}=require('/Applications/ChatGPT.app/Contents/Resources/cua_node/lib/node_modules/playwright');
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const rule={kind:'shop_rules',title_vi:'Quy tắc shop',version:1,excerpt_vi:'Voucher tối đa 8%.'};
const cost={kind:'product_cost',title_vi:'Giá vốn sản phẩm',version:1};
const fees={kind:'fee_policy',title_vi:'Chính sách phí áp dụng',version:'demo-fees-v1'};
const guide={kind:'reference_document',title_vi:'Tài liệu tham khảo phí giả lập',version:1,download_url:'/api/v1/runs/run-test/knowledge/documents/fee_calculation_guide_demo?version=1'};
const calc={kind:'calculation',title_vi:'Điều kiện dừng theo hòa vốn trong code',excerpt_vi:'Ngưỡng dừng không thấp hơn ROAS hòa vốn.'};
const checks=[
  {ok:false,message_vi:'Voucher vượt luật shop.',sources:[rule]},
  {ok:true,message_vi:'Quyền chạy quảng cáo phù hợp.',sources:[rule]},
  {ok:true,message_vi:'Ngân sách trong giới hạn shop.',sources:[rule]},
  {ok:true,message_vi:'Tồn kho đáp ứng điều kiện quảng cáo.',sources:[{title_vi:'Tồn kho',version:1},{title_vi:'Điều kiện tồn kho trong code'}]},
  {ok:false,message_vi:'Gói không đạt lãi tối thiểu.',sources:[rule,cost,fees,guide]},
  {ok:true,message_vi:'Gói không gây lỗ theo phép tính.',sources:[cost,fees,guide]},
  {ok:false,message_vi:'Gói vượt ngưỡng hòa vốn.',sources:[rule,cost,fees,guide]},
  {ok:false,message_vi:'Ngưỡng dừng chưa bảo vệ shop.',sources:[cost,fees,guide,calc]}
];
const fixture={run_id:'run-test',day:1,seq:24,type:'code_check',actor:'code',shop_id:'D',text_vi:'Code kiểm tra luật shop',ts:'10:00',data:{checks}};
const event=process.env.CHECK_EVENT_FILE?JSON.parse(await readFile(process.env.CHECK_EVENT_FILE,'utf8')):fixture;
const screenshot=process.env.CHECK_SCREENSHOT || '/tmp/growth-code-check-event.png';
const documentURL=event.data.checks.flatMap(check=>check.sources || []).find(source=>source.download_url)?.download_url;
assert.ok(documentURL,'fixture must include a document reference');
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
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
  const shop={shop_id:event.shop_id,name:'Shop kiểm thử',title:'Sản phẩm',description:'Sản phẩm',images:[],attributes:[]};
  const state={run_id:event.run_id,day:event.day,step:'negotiating',demo_shop:shop,demo_shop_original:shop,mode:'offline',busy:false};
  const legacy={...event,seq:event.seq+1,text_vi:'Kiểm tra cũ',data:{checks:[{ok:true,message_vi:'Không có nguồn'}]}};
  await context.route('**/api/**',route=>{
    const url=new URL(route.request().url());
    const reply=(status,body)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if(url.pathname==='/api/state')return reply(200,state);
    if(url.pathname==='/api/events'){
      const after=Number(url.searchParams.get('after') || 0);
      return reply(200,{run_id:event.run_id,events:[event,legacy].filter(item=>item.seq>after),last_seq:legacy.seq,has_more:false});
    }
    if(url.pathname+url.search===documentURL)return reply(200,{document_version:1,title:'Tài liệu tham khảo phí giả lập'});
    return reply(404,{error:{message_vi:'Không tìm thấy'}});
  });
  await page.goto('http://127.0.0.1:'+server.address().port+'/demo.html?preview=0');
  const historical=page.locator('#event-'+event.seq),rows=historical.locator('.event-check');
  await historical.waitFor();
  assert.equal(await rows.count(),8);
  for(let i=0;i<8;i++){
    assert.equal(await rows.nth(i).locator('.check-sources li').count(),event.data.checks[i].sources.length);
    const first=rows.nth(i).locator('.check-sources li').first();
    assert.ok((await first.innerText()).includes(event.data.checks[i].sources[0].title_vi));
    assert.equal(await first.evaluate(el=>!!el.closest('details:not([open])')),false);
  }
  assert.equal(await page.locator('#event-'+legacy.seq+' .check-sources').count(),0);
  const link=historical.getByRole('link',{name:'Tài liệu tham khảo phí giả lập'}).first();
  assert.equal(await link.getAttribute('href'),documentURL);
  await link.scrollIntoViewIfNeeded();
  const colors=await link.evaluate(el=>({link:getComputedStyle(el).color,text:getComputedStyle(el.closest('.check-sources')).color,excerpt:getComputedStyle(document.querySelector('.event-check .check-sources p')).color,background:getComputedStyle(el.closest('.backstage')).backgroundColor}));
  const rgb=value=>value.match(/\d+/g).slice(0,3).map(Number);
  const luminance=value=>rgb(value).map(c=>{c/=255;return c<=0.04045?c/12.92:((c+0.055)/1.055)**2.4;}).reduce((sum,c,i)=>sum+c*[0.2126,0.7152,0.0722][i],0);
  const contrast=(a,b)=>{const x=luminance(a),y=luminance(b);return (Math.max(x,y)+0.05)/(Math.min(x,y)+0.05);};
  for(const key of ['link','text','excerpt'])assert.ok(contrast(colors[key],colors.background)>=4.5,`${key} has insufficient contrast: ${JSON.stringify(colors)}`);
  await page.screenshot({path:screenshot});
  const popupPromise=page.waitForEvent('popup');
  await link.click();
  const popup=await popupPromise;
  await popup.waitForLoadState();
  assert.equal(new URL(popup.url()).pathname+new URL(popup.url()).search,documentURL);
  assert.match(await popup.locator('body').innerText(),/Tài liệu tham khảo phí giả lập/);
  process.stdout.write(`PASS: all eight historical checks show their own sources; text and links meet contrast; the supplied document link opens; old checks stay uncited. Screenshot: ${screenshot}\n`);
}finally{
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
