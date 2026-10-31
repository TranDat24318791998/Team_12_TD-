// Private headless interaction against a fake API, including actual download contents.
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
  const page=await browser.newPage({acceptDownloads:true});
  const artifact={schema_version:'demo-proof.v1',manifest:{comparison_id:'saved-pair',shop_id:'D',run_on:'saved-on',run_off:'saved-off',
      seed:42,days:7,source:'precomputed_offline_simulation',provider_eval:'not_run',artifact_sha256:'a'.repeat(64),brief_refs:['brief-on','brief-off']},
    report:{status:'ready',source:'precomputed_offline_simulation',run_on:'saved-on',run_off:'saved-off',seed:42,days:7,metrics:[],comparison_days:[]},
    evidence:{on:[{run_id:'saved-on',seq:21,text_vi:'Bằng chứng bật'}],off:[{run_id:'saved-off',seq:17,text_vi:'Bằng chứng tắt'}]}};
  const requests=[];let missing=false,authenticated=false;
  await page.route('**/api/**',async route=>{
    const url=new URL(route.request().url());requests.push(url.pathname);
    const reply=(status,body)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if(url.pathname==='/api/state'){authenticated=true;return reply(200,{run_id:'session-run'});}
    if(url.pathname==='/api/proof' || url.pathname==='/api/proof/demo'){
      if(!authenticated)return reply(401,{error:{code:'UNAUTHENTICATED',message_vi:'Cần tạo phiên'}});
      if(url.pathname==='/api/proof')return reply(409,{error:{code:'PROOF_NOT_READY',message_vi:'Phiên hiện tại chưa sẵn sàng'}});
      return missing?reply(404,{error:{code:'PROOF_NOT_READY',message_vi:'Báo cáo đã lưu chưa sẵn sàng'}}):reply(200,artifact);
    }
    return reply(500,{error:{code:'UNEXPECTED',message_vi:'Không được đọc nhật ký phiên hiện tại'}});
  });
  await page.goto(base+'/proof.html?preview=0');
  await page.getByRole('alert').getByText(/Phiên hiện tại chưa sẵn sàng/).waitFor();
  assert.deepEqual(requests.slice(0,3),['/api/proof','/api/state','/api/proof']);
  await page.getByRole('button',{name:'Báo cáo mô phỏng đã chạy'}).click();
  await page.getByText('Mô phỏng ngoại tuyến đã chạy · Chưa đánh giá provider').waitFor();
  assert.equal(await page.getByRole('button',{name:'Báo cáo mô phỏng đã chạy'}).getAttribute('aria-pressed'),'true');
  assert.equal(await page.locator('[data-restart]').innerText(),'Bắt đầu phiên demo mới');
  let [download]=await Promise.all([page.waitForEvent('download'),page.locator('[data-export-report]').click()]);
  assert.deepEqual(JSON.parse(await readFile(await download.path(),'utf8')),artifact);
  [download]=await Promise.all([page.waitForEvent('download'),page.locator('[data-export-log]').click()]);
  assert.deepEqual(JSON.parse(await readFile(await download.path(),'utf8')),
                   {schema_version:artifact.schema_version,manifest:artifact.manifest,evidence:artifact.evidence});
  assert.equal(requests.filter(path=>path==='/api/state').length,1);
  assert.equal(requests.includes('/api/events'),false);
  await page.getByRole('button',{name:'Phiên hiện tại'}).click();
  await page.getByRole('alert').getByText(/Phiên hiện tại chưa sẵn sàng/).waitFor();
  missing=true;authenticated=false;
  await page.getByRole('button',{name:'Báo cáo mô phỏng đã chạy'}).click();
  await page.getByRole('alert').getByText(/Báo cáo đã lưu chưa sẵn sàng/).waitFor();
  assert.equal(requests.filter(path=>path==='/api/state').length,2);
  assert.deepEqual(requests.slice(-3),['/api/proof/demo','/api/state','/api/proof/demo']);
  assert.equal(await page.getByRole('link',{name:'Mở bản xem trước'}).count(),0);
  assert.equal(await page.locator('[data-export-report]').count(),0);
  process.stdout.write('PASS: saved proof is explicitly selected and labeled; both downloads retain its own evidence; missing proof never falls back.\n');
}finally{
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
