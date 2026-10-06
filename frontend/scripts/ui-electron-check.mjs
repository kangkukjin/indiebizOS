import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const frontend = fileURLToPath(new URL('..', import.meta.url));
const require = createRequire(import.meta.url);
const lib = path.join(frontend,'../.venv/lib');
const python = readdirSync(lib).find(name => name.startsWith('python'));
const { _electron } = require(process.env.PLAYWRIGHT_MODULE || path.join(lib,python,'site-packages/playwright/driver/package'));
const profile = mkdtempSync(path.join(tmpdir(),'indiebiz-ui-locale-'));
let application;
const waitFor = async fn => {
  for (let i=0;i<100;i++) { if (await fn()) return; await new Promise(resolve => setTimeout(resolve,100)); }
  assert.fail('UI locale propagation timed out');
};
async function start() {
  application = await _electron.launch({timeout:15000,executablePath:require('electron'), args:[path.join(frontend,'scripts/ui-electron-fixture.mjs')],env:{...process.env,UI_TEST_PROFILE:profile}});
  const context = application.context();
  await context.routeWebSocket(/8765/,socket=>socket.close());
  await context.route(/https?:\/\/(localhost|127\.0\.0\.1):8765\//,async route=>{
    const p = new URL(route.request().url()).pathname;
    const data = p.includes('/items') ? {items:[]} : p==='/guides' ? {guides:[]} : p.includes('projects') ? {projects:[]} : {};
    await route.fulfill({json:data});
  });
  await waitFor(() => application.evaluate(() => typeof globalThis.openUITestWindows === 'function'));
  await application.evaluate(() => globalThis.openUITestWindows());
  await waitFor(()=>application.windows().length===3);
  for (const page of application.windows()) await page.waitForLoadState('domcontentloaded');
  return application.windows();
}
async function titles() {
  return application.evaluate(({BrowserWindow,Menu})=>({titles:BrowserWindow.getAllWindows().map(w=>w.getTitle()), menu:Menu.getApplicationMenu().items[0].label}));
}
try {
  let pages = await start();
  await pages[0].evaluate(()=>window.electron.setUILocale('en'));
  await waitFor(async()=> (await titles()).titles.includes('Guides'));
  assert.deepEqual((await titles()).titles.sort(), ['Guides','Prompt Composition','문서'].sort());
  assert.equal((await titles()).menu,'Edit');
  for (const page of pages) await waitFor(()=>page.evaluate(()=>document.documentElement.lang==='en'));
  await application.close(); application=null;
  pages = await start();
  await waitFor(async()=> (await titles()).titles.includes('Guides'));
  for (const page of pages) await waitFor(()=>page.evaluate(()=>document.documentElement.lang==='en'));
  await pages[1].evaluate(()=>window.electron.setUILocale('ko'));
  await waitFor(async()=> (await titles()).titles.includes('가이드 파일'));
  assert.deepEqual((await titles()).titles.sort(), ['가이드 파일','프롬프트 구성','문서'].sort());
  assert.equal((await titles()).menu,'편집');
  for (const page of pages) await waitFor(()=>page.evaluate(()=>document.documentElement.lang==='ko'));
  console.log(JSON.stringify({nativeWindows:3,english:true,restartPersistence:true,propagation:true,koreanReturn:true,userTitlePreserved:true}));
} finally {
  if(application) await application.close();
  rmSync(profile,{recursive:true,force:true});
}
