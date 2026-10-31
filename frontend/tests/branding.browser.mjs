// Inspect both headers in private headless Chromium using browser-only preview data.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {dirname,extname,join,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const require=createRequire(import.meta.url);
const {chromium}=require('/Applications/ChatGPT.app/Contents/Resources/cua_node/lib/node_modules/playwright');
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const server=createServer(async(req,res)=>{
  const path=resolve(root,'.'+new URL(req.url,'http://local').pathname);
  if(!path.startsWith(root+sep)){res.writeHead(403).end();return;}
  try{const data=await readFile(path);res.writeHead(200,{'content-type':({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png'})[extname(path)] || 'application/octet-stream'}).end(data);}
  catch{res.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base='http://127.0.0.1:'+server.address().port;
let browser;
try{
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  for(const [path,filename] of [['index.html','growth-shoppilot-shop.png'],['demo.html','growth-shoppilot-demo.png']]){
    await page.goto(base+'/'+path+'?preview=1');
    const logo=page.getByRole('link',{name:'ShopPilot AI, trang shop'}).getByRole('img',{name:'ShopPilot AI'});
    await logo.waitFor();
    const rendered=await logo.evaluate(image=>({complete:image.complete,width:image.naturalWidth,height:image.naturalHeight,fit:getComputedStyle(image).objectFit}));
    assert.deepEqual(rendered,{complete:true,width:1536,height:1024,fit:'contain'});
    await page.screenshot({path:join(tmpdir(),filename)});
  }
  await page.setViewportSize({width:390,height:844});
  await page.goto(base+'/demo.html?preview=1');
  const logo=page.getByRole('link',{name:'ShopPilot AI, trang shop'});
  const box=await logo.boundingBox();
  assert.ok(box && box.width>=70 && box.x>=0 && box.x+box.width<=390);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:join(tmpdir(),'growth-shoppilot-mobile.png')});
  process.stdout.write('PASS: supplied logo loads in shop and demo headers, including the compact mobile layout.\n');
}finally{
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
