// Real React checkbox and apply controls against a private fake API.
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
let browser,release,releaseImage;
try{
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const page=await browser.newPage();
  const shop={shop_id:'D',name:'Shop kiểm thử',title:'Quạt',description:'Quạt',images:[],attributes:[]};
  const images=['A','B','C'].map(option=>({option,status:'running',path:null}));
  let state={run_id:'run-test',day:1,step:'content_review',demo_shop:shop,demo_shop_original:shop,busy:true,
    content_draft:{version:1,card_id:'card-1',brief_version:2,job_id:'job-1',content_id:'content-1',status:'running',text_ready:true,title:'Tiêu đề',description:'Mô tả',images,video:{status:'running'},feedback_history:[]}};
  const pixel=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+p6FsAAAAASUVORK5CYII=','base64');
  let posts=[];
  await page.route('**/api/**',route=>{
    const req=route.request(),path=new URL(req.url()).pathname;
    if(path==='/api/state')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(state)});
    if(path==='/api/events')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({run_id:'run-test',events:[],last_seq:0,has_more:false})});
    if(path==='/api/v1/runs/run-test/assets/a/download')return route.fulfill({status:200,contentType:'image/png',body:pixel});
    if(path==='/api/v1/runs/run-test/assets/slow/download')return new Promise(resolve=>{releaseImage=()=>resolve(route.fulfill({status:200,contentType:'image/png',body:pixel}));});
    if(path==='/api/v1/runs/run-test/assets/broken/download')return route.fulfill({status:404,contentType:'text/plain',body:'broken'});
    if(path==='/api/content/apply'){
      posts.push(req.postDataJSON());
      return new Promise(resolve=>{release=()=>{state={...state,step:'day_done',busy:false};resolve(route.fulfill({status:200,contentType:'application/json',body:'{}'}));};});
    }
    return route.fulfill({status:404,contentType:'application/json',body:'{}'});
  });
  await page.goto('http://127.0.0.1:'+server.address().port+'/demo.html?preview=0');
  await page.getByLabel('Dùng ảnh, bỏ qua video').check();
  assert.equal(await page.locator('[data-apply]').isDisabled(),true,'no ready selected image must keep apply disabled');
  await page.getByText('Chị hãy chọn một ảnh đã sẵn sàng.').waitFor();
  const path='/api/v1/runs/run-test/assets/a/download';
  state={...state,content_draft:{...state.content_draft,text_ready:false,images:[{option:'A',status:'done',path,source:'live'},...images.slice(1)]}};
  await page.reload();await page.getByLabel('Dùng ảnh, bỏ qua video').check();
  await page.getByText('Đang chờ nội dung văn bản được kiểm tra.').waitFor();
  assert.equal(await page.locator('[data-apply]').isDisabled(),true,'placeholder text must not publish');
  state={...state,content_draft:{...state.content_draft,text_ready:true,images:[{option:'A',status:'cached',path},...images.slice(1)]}};
  await page.reload();await page.getByLabel('Dùng ảnh, bỏ qua video').check();
  await page.getByText('Chưa thể dùng ảnh này khi tác vụ đang chạy.').waitFor();
  assert.equal(await page.locator('[data-apply]').isDisabled(),true,'cached placeholder must not publish during a job');
  state={...state,content_draft:{...state.content_draft,images:[{option:'A',status:'unknown',path},...images.slice(1)]}};
  await page.reload();await page.getByLabel('Dùng ảnh, bỏ qua video').check();
  assert.equal(await page.locator('[data-apply]').isDisabled(),true,'unknown selected image must not publish');
  state={...state,content_draft:{...state.content_draft,images:[{option:'A',status:'done',path:'/api/v1/runs/run-test/assets/broken/download'},...images.slice(1)]}};
  await page.reload();await page.getByLabel('Dùng ảnh, bỏ qua video').check();
  await page.getByText('Ảnh không khả dụng').waitFor();
  assert.equal(await page.locator('[data-apply]').isDisabled(),true,'corrupt selected image must not publish');
  state={...state,content_draft:{...state.content_draft,status:'succeeded',text_ready:false,images:[{option:'A',status:'cached',path},{option:'B',status:'failed'},{option:'C',status:'failed'}],video:{status:'failed'}}};
  await page.reload();await page.getByLabel('Dùng ảnh, bỏ qua video').check();
  await page.waitForFunction(()=>document.querySelector('[data-apply]') && !document.querySelector('[data-apply]').disabled);
  state={...state,content_draft:{...state.content_draft,status:'running',text_ready:true,video:{status:'running'},images:[{option:'A',status:'done',path:'/api/v1/runs/run-test/assets/slow/download',source:'live'},...images.slice(1)]}};
  await page.goto('http://127.0.0.1:'+server.address().port+'/demo.html?preview=0',{waitUntil:'domcontentloaded'});
  await page.getByRole('img',{name:'Phương án ảnh bìa A'}).waitFor({timeout:4000});
  assert.equal(await page.locator('[data-apply]').isDisabled(),true,'without skip, other media is unresolved');
  await page.getByLabel('Dùng ảnh, bỏ qua video').check();
  assert.equal(await page.locator('[data-apply]').isDisabled(),true,'selected image must finish loading before apply');
  const finishImage=releaseImage;releaseImage=null;finishImage();
  await page.waitForFunction(()=>document.querySelector('[data-apply]') && !document.querySelector('[data-apply]').disabled);
  assert.equal(await page.locator('[data-apply]').isEnabled(),true,'skipping video must permit the verified selected image while other slots run');
  assert.equal(await page.locator('[data-retry]').isDisabled(),true);
  await page.locator('[data-apply]').click();
  await page.waitForFunction(()=>document.querySelector('[data-apply]').disabled);
  assert.equal(posts.length,1);assert.deepEqual(posts[0],{card_id:'card-1',expected_brief_version:2,expected_draft_version:1,expected_job_id:'job-1',expected_content_id:'content-1',cover_option:'A',skip_video:true,video_review_ack:false});
  const finish=release;release=null;finish();
  process.stdout.write('PASS: skipping video enables a verified selected cover during other media work and keeps unready/pending submissions blocked.\n');
}finally{
  releaseImage?.();release?.();await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
