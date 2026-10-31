// Show a verified slot while the other images and video are still running.
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
  const images=['A','B','C'].map(option=>({option,status:'running',path:null}));
  let state={run_id:'run-test',day:1,step:'content_review',demo_shop:shop,demo_shop_original:shop,busy:true,
    content_draft:{version:1,card_id:'card',job_id:'job',status:'running',title:'Tiêu đề',description:'Mô tả',images,video:{status:'running'},feedback_history:[]}};
  const pixel=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+p6FsAAAAASUVORK5CYII=','base64');
  await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/state')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(state)});
    if(path==='/api/events')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({run_id:'run-test',events:[],last_seq:0,has_more:false})});
    if(path==='/api/v1/runs/run-test/assets/a/download')return route.fulfill({status:200,contentType:'image/png',body:pixel});
    return route.fulfill({status:404,contentType:'application/json',body:'{}'});
  });
  await page.goto('http://127.0.0.1:'+server.address().port+'/demo.html?preview=0');
  await page.locator('.cover-running').first().waitFor();
  state={...state,content_draft:{...state.content_draft,images:[{option:'A',status:'done',path:'/api/v1/runs/run-test/assets/a/download',source:'live'},...images.slice(1)]}};
  await page.getByRole('img',{name:'Phương án ảnh bìa A'}).waitFor({timeout:2600});
  assert.equal(await page.locator('.cover-running').count(),2);
  assert.equal(await page.locator('[data-apply]').isDisabled(),true);
  process.stdout.write('PASS: a verified image appears on the next state poll while other media remains in progress.\n');
}finally{
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
