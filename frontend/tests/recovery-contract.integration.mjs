// Backend TestClient and UI rendering share the same disposable failed-attempt state.
import {execFileSync} from 'node:child_process';
import {mkdtemp,rm} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {tmpdir} from 'node:os';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(import.meta.url),esbuild=require('esbuild');
const python=process.env.GROWTH_TEST_PYTHON || resolve(root,'.venv/bin/python');
const data=JSON.parse(execFileSync(python,[resolve(root,'frontend/tests/recovery-contract-source.py')],{cwd:root,encoding:'utf8',maxBuffer:16*1024*1024}));
const temporary=await mkdtemp(join(tmpdir(),'growth-recovery-ui-'));
try{
  const outfile=join(temporary,'contract.mjs');
  await esbuild.build({entryPoints:[resolve(root,'frontend/tests/recovery-contract-render.jsx')],outfile,bundle:true,platform:'node',format:'esm',jsx:'automatic',target:'es2022',banner:{js:"import {createRequire} from 'node:module'; const require=createRequire(import.meta.url);"},define:{'process.env.NODE_ENV':'"production"'},logLevel:'silent'});
  const module=await import(pathToFileURL(outfile).href);
  module.verify(data);
}finally{await rm(temporary,{recursive:true,force:true});}
process.stdout.write('PASS: an actual disposable legacy failure exposes explicit recovery and renders the same original offer after the seller command.\n');
