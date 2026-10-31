import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { delimiter } from 'node:path';
const require = createRequire(import.meta.url);
const esbuild = require('esbuild');
const root = fileURLToPath(new URL('.', import.meta.url));
const tests = process.argv.includes('--tests');
const options = {
  absWorkingDir: root,
  entryPoints: [tests ? 'tests/components.test.jsx' : 'src/main.jsx'],
  outfile: tests ? '.test-build/components.test.mjs' : 'js/app.js',
  bundle: true, jsx: 'automatic', target: 'es2022',
  platform: tests ? 'node' : 'browser', format: 'esm',
  minify: !tests, legalComments: 'linked',
  nodePaths: (process.env.NODE_PATH || '').split(delimiter).filter(Boolean),
  define: { 'process.env.NODE_ENV': '"production"' },
  ...(tests?{banner:{js:"import {createRequire} from 'node:module';const require=createRequire(import.meta.url);"}}:{}),
  logLevel: 'info',
};
if (process.argv.includes('--watch')) {
  const context = await esbuild.context(options);
  await context.watch();
} else {
  await esbuild.build(options);
  if(tests)await esbuild.build({...options,entryPoints:['tests/useRun.browser.jsx'],outfile:'.test-build/useRun.browser.js',platform:'browser',banner:{}});
}
