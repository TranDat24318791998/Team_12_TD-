// Verify skip-video on the current staged wizard using a private fake Data API.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import {dirname,extname,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const {chromium}=require('/Applications/ChatGPT.app/Contents/Resources/cua_node/lib/node_modules/playwright');
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
let browser,release,releaseImage;
try{
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const page=await browser.newPage();
  const jpeg=await readFile(resolve(root,'img/demo-d-desktop.jpg'));
  const shop={shop_id:'D',name:'Shop kiểm thử',title:'Quạt',description:'Quạt',images:[],attributes:[]};
  const binding={card_id:'card-1',expected_brief_version:2,expected_draft_version:1,expected_job_id:'job-1',expected_content_id:'content-1'};
  const image={option:'A',status:'done',source:'live',path:'/api/v1/runs/run-test/assets/a/download'};
  let state={run_id:'run-test',day:1,step:'content_review',demo_shop:shop,demo_shop_original:shop,busy:false,
    content_draft:{version:1,card_id:'card-1',brief_version:2,job_id:'job-1',content_id:'content-1',status:'succeeded',text_ready:true,title:'Tiêu đề đã kiểm tra',description:'Mô tả đã kiểm tra',images:[image],video:{status:'pending'},wizard:{stage:'image_ready'},feedback_history:[]}};
  const sent=[];
  await page.route('https://shoppilot.test/**',async route=>{
    const path=resolve(root,'.'+new URL(route.request().url()).pathname);
    if(!path.startsWith(root+sep))return route.fulfill({status:403});
    try{const data=await readFile(path);return route.fulfill({status:200,contentType:({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.jpg':'image/jpeg','.png':'image/png'})[extname(path)] || 'application/octet-stream',body:data});}
    catch{return route.fulfill({status:404});}
  });
  await page.route('**/api/**',route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    const reply=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if(path==='/api/state')return reply(state);
    if(path==='/api/events')return reply({run_id:'run-test',events:[],last_seq:0,has_more:false});
    if(path==='/api/v1/runs/run-test/assets/a/download')return route.fulfill({status:200,contentType:'image/jpeg',body:jpeg});
    if(path==='/api/v1/runs/run-test/assets/slow/download')return new Promise(resolve=>{releaseImage=()=>resolve(route.fulfill({status:200,contentType:'image/jpeg',body:jpeg}));});
    if(path==='/api/v1/runs/run-test/assets/broken/download')return route.fulfill({status:404,contentType:'text/plain',body:'broken'});
    if(path==='/api/content/apply'){
      sent.push({body:request.postDataJSON(),headers:request.headers()});
      return new Promise(resolve=>{release=()=>{state={...state,step:'day_done',content_draft:null};resolve(reply({listing:state.demo_shop}));};});
    }
    return reply({error:{message_vi:'Không tìm thấy'}},404);
  });
  const url='https://shoppilot.test/demo.html?preview=0';
  await page.goto(url);await page.getByRole('img',{name:'Ảnh sản phẩm mới đã tạo'}).waitFor();
  assert.equal(await page.getByLabel('Dùng ảnh, bỏ qua video').count(),1,'image_ready must offer explicit skip');
  const apply=page.getByRole('button',{name:'Dùng bản này'});
  assert.equal(await apply.isDisabled(),true,'unchecked skip must not apply');
  for(const [name,changes] of [
    ['unvalidated text',{text_ready:false}],
    ['cached placeholder',{images:[{...image,status:'cached'}]}],
    ['non-live image',{images:[{...image,source:'cached'}]}],
    ['unknown image',{images:[{...image,status:'unknown'}]}],
    ['missing path',{images:[{...image,path:null}]}],
    ['corrupt image',{images:[{...image,path:'/api/v1/runs/run-test/assets/broken/download'}]}]
  ]){
    state={...state,content_draft:{...state.content_draft,text_ready:true,images:[image],...changes}};
    await page.goto(url);await page.getByLabel('Dùng ảnh, bỏ qua video').check();
    if(name==='corrupt image')await page.getByText('Không tải được ảnh sản phẩm mới.').waitFor();
    assert.equal(await apply.isDisabled(),true,name+' must not enable apply');
  }
  state={...state,content_draft:{...state.content_draft,text_ready:true,images:[{...image,path:'/api/v1/runs/run-test/assets/slow/download'}]}};
  await page.goto(url,{waitUntil:'domcontentloaded'});await page.getByLabel('Dùng ảnh, bỏ qua video').check();
  await page.locator('.generated-image img').waitFor({state:'attached'});
  assert.equal(await apply.isDisabled(),true,'image must load before apply');
  for(let i=0;!releaseImage && i<100;i++)await page.waitForTimeout(20);
  assert.ok(releaseImage,'the image request must be in flight');
  const finishImage=releaseImage;releaseImage=null;finishImage();
  await page.waitForFunction(()=>document.querySelector('[data-skip-media]') && !document.querySelector('[data-skip-media]').disabled);
  assert.match(await page.locator('.media-description').innerText(),/Tiêu đề đã kiểm tra/);
  await apply.click();await page.waitForFunction(()=>document.querySelector('[data-skip-media]').disabled);
  assert.equal(sent.length,1);assert.deepEqual(sent[0].body,{...binding,cover_option:'A',skip_video:true,video_review_ack:false});assert.ok(sent[0].headers['idempotency-key']);
  const finish=release;release=null;finish();await page.waitForURL('**/updated.html?preview=0');
  state={...state,step:'content_review',busy:true,content_draft:{version:1,card_id:'card-1',brief_version:2,job_id:'job-1',content_id:'content-1',status:'running',text_ready:true,title:'Tiêu đề đã kiểm tra',description:'Mô tả đã kiểm tra',images:[image],video:{status:'running'},wizard:{stage:'video_queued'},feedback_history:[]}};
  await page.goto(url);await page.getByLabel('Dùng ảnh, bỏ qua video').check();
  await page.waitForFunction(()=>document.querySelector('[data-skip-media]') && !document.querySelector('[data-skip-media]').disabled);
  assert.equal(await page.getByText('Đang tạo video từ ảnh chị đã chọn…').count(),1);
  await page.getByRole('button',{name:'Dùng bản này'}).click();
  assert.equal(sent.length,2);assert.deepEqual(sent[1].body,{...binding,cover_option:'A',skip_video:true,video_review_ack:false});
  const finishVideo=release;release=null;finishVideo();
  for(const stage of ['video_ready','failed']){
    state={...state,step:'content_review',busy:false,content_draft:{version:1,card_id:'card-1',brief_version:2,job_id:'job-1',content_id:'content-1',status:stage==='failed'?'failed':'succeeded',text_ready:true,title:'Tiêu đề đã kiểm tra',description:'Mô tả đã kiểm tra',images:[image],video:{status:'failed'},wizard:{stage},feedback_history:[]}};
    await page.goto(url);await page.getByLabel('Dùng ảnh, bỏ qua video').check();
    await page.waitForFunction(()=>document.querySelector('[data-skip-media]') && !document.querySelector('[data-skip-media]').disabled);
    if(stage==='video_ready')assert.equal(await page.locator('[data-use-media]').isDisabled(),true);
    await apply.click();assert.deepEqual(sent.at(-1).body,{...binding,cover_option:'A',skip_video:true,video_review_ack:false});
    const finishStage=release;release=null;finishStage();await page.waitForURL('**/updated.html?preview=0');
  }
  process.stdout.write('PASS: staged wizard skips video at image-ready, video-running, video-ready and failed-video stages only with verified loaded image and validated text.\n');
}finally{
  releaseImage?.();release?.();await browser?.close();
}
