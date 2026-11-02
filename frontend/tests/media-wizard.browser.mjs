// Browser contract test: all media jobs and publication use a mocked Data API.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import {dirname,extname,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const {chromium}=require('/Applications/ChatGPT.app/Contents/Resources/cua_node/lib/node_modules/playwright');
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
let browser;
try{
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const clip=Buffer.from(await page.evaluate(async()=>{
    const canvas=document.createElement('canvas');canvas.width=32;canvas.height=32;canvas.getContext('2d').fillRect(0,0,32,32);
    const stream=canvas.captureStream(10),recorder=new MediaRecorder(stream,{mimeType:'video/webm'}),chunks=[];
    recorder.ondataavailable=event=>chunks.push(event.data);
    const finished=new Promise(resolve=>recorder.onstop=resolve);recorder.start();
    for(let i=0;i<5;i++){canvas.getContext('2d').fillStyle=i%2?'#eee':'#f90';canvas.getContext('2d').fillRect(0,0,32,32);await new Promise(resolve=>setTimeout(resolve,100));}
    recorder.stop();await finished;stream.getTracks().forEach(track=>track.stop());
    return Array.from(new Uint8Array(await new Blob(chunks,{type:'video/webm'}).arrayBuffer()));
  }));
  const jpeg=await readFile(resolve(root,'img/demo-d-desktop.jpg'));
  const shop={shop_id:'D',name:'Nhà Bé Lan',title:'Quạt để bàn',description:'Quạt để bàn',images:['/api/v1/runs/run/assets/original/download'],video:null,attributes:[],stock:5};
  const binding={card_id:'card',expected_brief_version:1,expected_draft_version:1,expected_job_id:'job',expected_content_id:'content'};
  const draft={card_id:'card',brief_version:1,version:1,job_id:'job',content_id:'content',title:'Quạt',description:'Mô tả',input_image:'/api/v1/runs/run/assets/pinned/download',images:[{option:'A',status:'pending',path:null}],video:{status:'pending',path:null},wizard:{stage:'choose_image'}};
  let state={run_id:'run',day:1,step:'content_review',demo_shop:shop,demo_shop_original:shop,busy:false,content_draft:draft};
  const sent=[];
  await page.route('https://shoppilot.test/**',async route=>{
    let pathname=new URL(route.request().url()).pathname;
    if(/^\/(?:demo|proof|night|updated)$/.test(pathname))pathname+='.html';
    const path=resolve(root,'.'+pathname);
    if(!path.startsWith(root+sep))return route.fulfill({status:403});
    try{const data=await readFile(path);return route.fulfill({status:200,contentType:({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.jpg':'image/jpeg','.png':'image/png'})[extname(path)] || 'application/octet-stream',body:data});}
    catch{return route.fulfill({status:404});}
  });
  await page.route('**/api/**',route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    const reply=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if(path==='/api/state')return reply(state);
    if(path==='/api/events')return reply({run_id:'run',events:[],last_seq:0,has_more:false});
    if(path.endsWith('/assets/original/download') || path.endsWith('/assets/pinned/download') || path.endsWith('/assets/generated/download'))return route.fulfill({status:200,contentType:'image/jpeg',body:jpeg});
    if(path.endsWith('/assets/video/download'))return route.fulfill({status:200,contentType:'video/webm',body:clip});
    if(request.method()==='POST'){
      const body=request.postDataJSON();sent.push({path,body,headers:request.headers()});
      if(path==='/api/content/image'){state={...state,content_draft:{...state.content_draft,wizard:{stage:'image_queued',background:body.background,wishes:body.wishes}}};return reply({draft:state.content_draft});}
      if(path==='/api/content/video'){state={...state,content_draft:{...state.content_draft,wizard:{...state.content_draft.wizard,stage:'video_queued',output_type:body.output_type,duration:body.duration}}};return reply({draft:state.content_draft});}
      if(path==='/api/content/apply'){state={...state,step:'day_done',content_draft:null,demo_shop:{...shop,images:['/api/v1/runs/run/assets/generated/download'],video:'/api/v1/runs/run/assets/video/download'}};return reply({listing:state.demo_shop});}
    }
    return reply({error:{message:'Unexpected request'}},404);
  });
  await page.goto('https://shoppilot.test/demo?preview=0');
  await page.getByRole('heading',{name:'Tạo ảnh và video sản phẩm'}).waitFor();
  assert.equal(await page.getByRole('img',{name:'Logo người bán'}).count(),1);
  assert.equal(await page.getByRole('img',{name:'Ảnh sản phẩm hiện có'}).count(),1);
  assert.match(await page.getByRole('img',{name:'Ảnh sản phẩm hiện có'}).getAttribute('src'),/assets\/pinned\/download/);
  assert.equal(await page.locator('.background-choice').count(),4);
  await page.getByRole('slider',{name:'Chọn phong cách nền'}).fill('2');
  assert.equal(await page.getByRole('button',{name:'Studio cao cấp'}).getAttribute('aria-pressed'),'true');
  await page.getByLabel('Mong muốn thêm').fill('Ánh sáng dịu, giữ màu quạt');
  await page.screenshot({path:'/private/tmp/shoppilot-media-wizard-mobile.png',fullPage:true});
  const widths=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:innerWidth}));assert.ok(widths.document<=widths.viewport);
  await page.getByRole('button',{name:'Tiếp tục tạo ảnh'}).click();
  await page.getByText('Đang tạo ảnh theo lựa chọn của chị…').waitFor();
  assert.deepEqual(sent[0].body,{...binding,background:'premium_studio',wishes:'Ánh sáng dịu, giữ màu quạt'});assert.ok(sent[0].headers['idempotency-key']);
  assert.equal(sent.filter(item=>item.path==='/api/content/video').length,0);
  state={...state,content_draft:{...state.content_draft,images:[{option:'A',status:'done',path:'/api/v1/runs/run/assets/generated/download'}],wizard:{...state.content_draft.wizard,stage:'image_ready'}}};
  await page.getByRole('img',{name:'Ảnh sản phẩm mới đã tạo'}).waitFor({timeout:4000});
  assert.equal(await page.getByRole('radio',{name:'20 giây'}).isChecked(),true);
  assert.equal(await page.getByRole('button',{name:'Tạo video'}).isDisabled(),true);
  await page.getByRole('radio',{name:/Chibi 3D/}).check();
  await page.getByRole('radio',{name:'15 giây'}).check();
  await page.getByRole('button',{name:'Tạo video'}).click();
  await page.getByText('Đang tạo video từ ảnh chị đã chọn…').waitFor();
  assert.deepEqual(sent[1].body,{...binding,output_type:'chibi_3d',duration:15});
  state={...state,content_draft:{...state.content_draft,video:{status:'done',path:'/api/v1/runs/run/assets/video/download',review_passed:true,requested_duration_seconds:15,duration_seconds:10,duration_matches_requested:false,short_description:'Một cảnh giới thiệu quạt nhẹ nhàng.'},wizard:{...state.content_draft.wizard,stage:'video_ready'}}};
  await page.getByText('Một cảnh giới thiệu quạt nhẹ nhàng.').waitFor({timeout:4000});
  await page.waitForTimeout(500);
  assert.equal(await page.locator('video.generated-video').count(),1,`generated video could not load (${clip.length} bytes)`);
  assert.match(await page.locator('.media-duration').innerText(),/Đã chọn: 15 giây · Thực tế: 10 giây/);
  assert.match(await page.locator('.media-duration').innerText(),/khác với lựa chọn/);
  const apply=page.getByRole('button',{name:'Sử dụng media'});assert.equal(await apply.isDisabled(),true);
  await page.getByLabel('Tôi đã xem video và đồng ý sử dụng bản này.').check();
  await apply.click();
  await page.waitForURL('**/updated.html?preview=0');
  assert.deepEqual(sent[2].body,{...binding,cover_option:'A',skip_video:false,video_review_ack:true});
  assert.match(await page.locator('#product-hero').getAttribute('src'),/assets\/generated\/download/);
  await page.reload();await page.locator('#product-hero').waitFor();
  assert.match(await page.locator('#product-hero').getAttribute('src'),/assets\/generated\/download/);
  assert.equal(await page.getByRole('button',{name:'Xem video'}).count(),1);
  process.stdout.write('PASS: seller choices drive staged API jobs and persisted listing reload.\n');
}finally{
  await browser?.close();
}
