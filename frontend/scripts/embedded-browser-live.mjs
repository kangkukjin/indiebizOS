// Real Electron guest + TLS login + local bridge acceptance. Synthetic credentials only.
import { app, BrowserWindow, ipcMain, session } from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import https from 'node:https';
import net from 'node:net';
import assert from 'node:assert/strict';
import { execFileSync, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { startEmbeddedBridge } from '../electron/embedded-browser-bridge.js';
import ts from 'typescript';

const root = fs.mkdtempSync('/tmp/ib-eb-test-');
fs.mkdirSync(path.join(root, 'profile'), { recursive: true });
app.setPath('userData', path.join(root, 'profile'));
let bridge, server, win; let origin; let submissions = 0;
const owner = 'a'.repeat(64);
const secret = 'synthetic-only-password';
const owner2 = 'b'.repeat(64);
const check = (condition, name) => { assert.ok(condition, name); console.log(`PASS ${name}`); };
async function run() {
  execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', path.join(root, 'key'),
    '-out', path.join(root, 'cert'), '-days', '1', '-subj', '/CN=127.0.0.1'], { stdio: 'ignore' });
  server = https.createServer({ key: fs.readFileSync(path.join(root, 'key')), cert: fs.readFileSync(path.join(root, 'cert')) }, (req, res) => {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    if (req.url === '/login' && req.method === 'POST') {
      let body = ''; req.on('data', d => body += d); req.on('end', () => {
        submissions++; const values = new URLSearchParams(body);
        assert.equal(values.get('password'), secret);
        res.writeHead(303, { 'Set-Cookie': 'logged=yes; Secure; HttpOnly; SameSite=Lax', Location: '/mail' }); res.end();
      }); return;
    }
    if (req.url === '/mail' && (req.headers.cookie || '').includes('logged=yes')) {
      res.end('<main><input type="search" aria-label="메일 검색"><h1>받은 편지함</h1><article>합성 메일 본문 123</article><a href="/next?token=hidden">다음</a></main>'); return;
    }
    if (req.url === '/delayed') { res.end('<main id="m">로딩</main><script>setTimeout(()=>m.textContent="동적 문서 완료",250)</script>'); return; }
    if (req.url === '/mfa') { res.end('<input autocomplete="one-time-code" aria-label="인증번호">'); return; }
    if (req.url === '/unsafe') { res.end('<form action="https://example.invalid/login"><input autocomplete="username"><input type="password"><button>로그인</button></form>'); return; }
    if (req.url === '/long') { res.end('<main>' + '가나다 '.repeat(7000) + '</main>'); return; }
    if (req.url === '/frame') { res.end('<main>부모</main><iframe name="child" src="/delayed"></iframe>'); return; }
    res.end('<main><h1>로그인</h1><form action="/login" method="post"><input name="username" autocomplete="username" aria-label="계정"><input name="password" type="password" aria-label="비밀번호"><button>로그인</button></form><button id="replace" onclick="this.outerHTML=\'<button>바뀜</button>\'">교체</button></main>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = `https://127.0.0.1:${server.address().port}`;
  const ses = session.fromPartition('persist:forage');
  ses.setCertificateVerifyProc((request, done) => done(request.hostname === '127.0.0.1' ? 0 : -3));
  win = new BrowserWindow({ show: false, webPreferences: { nodeIntegration: true, contextIsolation: false, webviewTag: true } });
  bridge = startEmbeddedBridge({ basePath: root, runtimePath: root,
    vault: { listAll: () => [{ origin, username: 'test-user' }], getCredential: (url) => { assert.equal(url, origin); return { username: 'test-user', password: secret }; } },
    show: () => {}, changed: () => {
      if (win?.isDestroyed() === false) win.webContents.send('refresh');
    } });
  win.webContents.on('did-attach-webview', (_e, guest) => bridge.tabs.attach(guest));
  ipcMain.handle('list', () => bridge.tabs.ui('list'));
  ipcMain.handle('bind', (event, id, wcId) => {
    assert.equal(event.sender, win.webContents);
    const wc = [...bridge.tabs.guests].find(w => w.id === wcId);
    return bridge.tabs.bind(id, wc);
  });
  const lifecyclePath = new URL('../src/components/forage/embeddedLifecycle.ts', import.meta.url);
  const lifecycleJS = ts.transpileModule(fs.readFileSync(lifecyclePath, 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022},
  }).outputText.replace('export class', 'class');
  const html = `<script>const {ipcRenderer}=require('electron');
    ${lifecycleJS}
    const lifecycle=new EmbeddedTabLifecycle(); window.panelOpen=false; let queue=Promise.resolve();
    ipcRenderer.on('refresh',()=>{queue=queue.then(async()=>{
      const actions=lifecycle.sync(await ipcRenderer.invoke('list'),window.panelOpen);
      for(const id of actions.removed) document.getElementById(id)?.remove();
      if(actions.close) window.panelOpen=false;
      if(actions.show) window.panelOpen=true;
      for(const r of actions.added) {const w=document.createElement('webview'); w.id=r.id;
      w.setAttribute('partition','persist:forage'); w.src=r.url; w.style='width:900px;height:700px';
      w.addEventListener('dom-ready',()=>ipcRenderer.invoke('bind',r.id,w.getWebContentsId()));document.body.append(w);
    }
    document.body.style.display=window.panelOpen?'block':'none';
    });});</script>`;
  await win.loadURL(`data:text/html,${encodeURIComponent(html)}`); await bridge.ready;
  const endpoint = JSON.parse(fs.readFileSync(path.join(root, 'embedded-browser.json')));
  async function call(params, who = owner, id = randomUUID()) {
    const result = await new Promise((resolve, reject) => {
      const sock = net.createConnection(endpoint.socket); let buffer = '';
      sock.on('error', reject); sock.setTimeout(15000, () => { sock.destroy(); reject(new Error('fixture timeout')); });
      sock.on('connect', () => sock.write(JSON.stringify({ ...endpoint, id, owner: who, deadline: Date.now() + 12000, params }) + '\n'));
      sock.on('data', data => { buffer += data; if (buffer.includes('\n')) { sock.end(); resolve(JSON.parse(buffer).result); } });
    });
    assert.ok(!JSON.stringify(result).includes(secret), 'secret redaction'); return result;
  }
  const temporary = await Promise.all([call({op: 'tab', mode: 'new', url: `${origin}/delayed`}),
    call({op: 'tab', mode: 'new', url: `${origin}/delayed`}, owner2)]);
  check(temporary.every(t => t.success), 'concurrent temporary tabs');
  await new Promise(resolve => setTimeout(resolve, 100));
  check(await win.webContents.executeJavaScript('!window.panelOpen && document.querySelectorAll("webview").length===2'),
    'finished calls hide panel without model close and preserve guests');
  const hiddenContent = await call({op: 'content', tab_id: temporary[0].tab_id});
  check(hiddenContent.success, 'follow-up content works in hidden guest');
  check(await win.webContents.executeJavaScript('!window.panelOpen'), 'follow-up does not reopen panel');
  await call({op: 'tab', mode: 'close', tab_id: temporary[0].tab_id});
  await new Promise(resolve => setTimeout(resolve, 100));
  check(await win.webContents.executeJavaScript('!window.panelOpen && document.querySelectorAll("webview").length===1'),
    'closing one task preserves the other hidden guest');
  await call({op: 'tab', mode: 'close', tab_id: temporary[1].tab_id}, owner2);
  await new Promise(resolve => setTimeout(resolve, 100));
  check(await win.webContents.executeJavaScript('!window.panelOpen && !document.querySelector("webview")'),
    'last temporary tab removes guest and closes panel');
  const failed = await call({op: 'tab', mode: 'new', url: 'file:///not-allowed'});
  check(failed.error_code === 'INVALID_URL', 'failed navigation reported');
  await new Promise(resolve => setTimeout(resolve, 100));
  check(await win.webContents.executeJavaScript('!window.panelOpen && !document.querySelector("webview")'),
    'failed creation also hides panel and removes guest');
  await win.webContents.executeJavaScript('window.panelOpen=true');
  const preserved = await call({op: 'tab', mode: 'new', url: `${origin}/delayed`});
  await call({op: 'tab', mode: 'close', tab_id: preserved.tab_id});
  await new Promise(resolve => setTimeout(resolve, 100));
  check(await win.webContents.executeJavaScript('window.panelOpen'), 'preserve already-open user panel');
  let r = await call({ op: 'navigate', url: `${origin}/mail` }); check(r.success, 'create actual guest tab'); const tab = r.tab_id;
  let snap = await call({ op: 'snapshot' }); check(snap.success && snap.elements.length >= 4, 'DOM snapshot refs');
  const submit = snap.elements.find(e => e.role === 'button' && e.name === '로그인').ref;
  const pass = snap.elements.find(e => e.sensitive).ref;
  r = await call({ op: 'type', ref: pass, text: 'should-not-type' }); check(r.error_code === 'USE_AUTH_FOR_PROTECTED_INPUT', 'protect password inputs');
  r = await call({ op: 'auth', mode: 'status' }); check(r.accounts.length === 1 && r.state === 'login_required', 'opaque local account');
  const id = randomUUID(); const login = { op: 'auth', mode: 'login', account_ref: r.accounts[0].account_ref, submit_ref: submit };
  r = await call(login, owner, id); check(r.success && r.submitted, 'fill and submit in main');
  await call(login, owner, id); check(submissions <= 1, 'idempotent submission');
  await new Promise(resolve => setTimeout(resolve, 300));
  r = await call({ op: 'content' }); assert.equal(r.success, true, JSON.stringify(r)); check(r.content.includes('합성 메일 본문 123'), 'read authenticated page');
  check(!JSON.stringify(r.links).includes('hidden'), 'remove token query');
  await call({ op: 'auth', mode: 'resume' });
  r = await call({ op: 'snapshot', tab_id: tab }, owner2); check(r.error_code === 'TAB_NOT_GRANTED', 'other task denied');
  r = await call({ op: 'evaluate', expression: 'document.cookie' }); check(r.error_code === 'UNSUPPORTED_OPERATION', 'no arbitrary credential reads');
  await call({ op: 'navigate', url: `${origin}/delayed` });
  await call({ op: 'wait', text: '동적 문서 완료' });
  r = await call({ op: 'content' }); check(r.content.includes('동적 문서 완료'), 'wait and dynamic DOM read');
  r = await call({ op: 'click', ref: submit }); check(['SNAPSHOT_REQUIRED', 'STALE_REF'].includes(r.error_code), 'stale reference rejected');
  await call({ op: 'navigate', url: `${origin}/frame` });
  r = await call({ op: 'iframe', mode: 'list' }); check(r.frames.length === 1, 'frame inventory');
  await call({ op: 'iframe', mode: 'switch', index: 0 });
  await call({ op: 'wait', text: '동적 문서 완료' });
  r = await call({ op: 'content' }); check(r.content.includes('동적 문서 완료') && !r.content.includes('부모'), 'frame-scoped read');
  bridge.tabs.ui('pause', tab);
  r = await call({ op: 'snapshot' }); check(r.error_code === 'USER_TAKEOVER', 'human takeover');
  await call({ op: 'auth', mode: 'cancel' });
  await call({ op: 'close' });
  check(!win.isDestroyed(), 'close only releases task');
  r = await call({ op: 'navigate', url: `${origin}/mail` }, owner2);
  r = await call({ op: 'content' }, owner2); check(r.content.includes('합성 메일 본문 123'), 'reuse same authenticated partition');
  await call({ op: 'close' }, owner2);
  await call({ op: 'navigate', url: `${origin}/unsafe` });
  snap = await call({ op: 'snapshot' });
  r = await call({ op: 'auth', mode: 'login', submit_ref: snap.elements.find(e => e.role === 'button').ref });
  check(r.error_code === 'AUTH_FORM_ORIGIN_MISMATCH' && submissions === 1, 'cross-origin credential form rejected');
  await call({ op: 'auth', mode: 'cancel' });
  await call({ op: 'navigate', url: `${origin}/mfa` });
  await win.webContents.executeJavaScript('window.panelOpen=false');
  r = await call({ op: 'auth', mode: 'login' }); check(r.state === 'user_action_required', 'MFA handed to user');
  await new Promise(resolve => setTimeout(resolve, 100));
  check(await win.webContents.executeJavaScript('window.panelOpen'), 'authentication handoff shows panel');
  await call({ op: 'auth', mode: 'cancel' });
  await new Promise(resolve => setTimeout(resolve, 100));
  check(await win.webContents.executeJavaScript('!window.panelOpen'), 'cancel authentication hides panel');
  await call({ op: 'navigate', url: `${origin}/long` });
  r = await call({ op: 'content', limit: 500 });
  check(r.truncated && r.next_offset === 500, 'bounded DOM extraction');
  await bridge.tabs.target(owner).wc.executeJavaScript(
    "history.replaceState({}, '', '/changed'); document.title='Changed'; document.querySelector('main').textContent='Changed text'");
  const next = await call({ op: 'content', cursor: r.cursor, offset: r.next_offset, limit: 500 });
  check(next.cursor === r.cursor && next.next_offset === 1000, 'stable content continuation');
  check(next.captured_at === r.captured_at && next.title === r.title, 'cursor preserves capture provenance');
  check(next.url === r.url && next.frame.url === r.frame.url && next.content !== 'Changed text', 'SPA keeps captured frame source');
  await call({ op: 'navigate', url: `${origin}/login` });
  snap = await call({ op: 'snapshot' });
  const replace = snap.elements.find(e => e.name === '교체').ref;
  await call({ op: 'click', ref: replace });
  r = await call({ op: 'click', ref: replace }); check(r.error_code === 'STALE_REF', 'DOM replacement invalidates ref');
  await call({ op: 'navigate', url: `${origin}/login` }); await call({ op: 'snapshot' });
  r = await call({ op: 'click', ref: replace }); check(r.error_code === 'STALE_REF', 'ref cannot alias new document');
  const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
  const client = `import boot_paths
import asyncio, importlib.util, json, os
from types import SimpleNamespace
from pathlib import Path
from ibl_v2_adapters import decode_envelope
root=Path.cwd()
spec=importlib.util.spec_from_file_location('live_browser_handler', root/'data/packages/installed/tools/browser-action/handler.py')
h=importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
ctx=SimpleNamespace(project_path=str(root),agent_id='fixture',task_id='embedded-live-client',tool_name='browser_op')
async def run():
    nav=json.loads(await h.execute({'driver':'embedded','op':'navigate','url':os.environ['FIXTURE_URL']},ctx))
    assert nav['success'], nav
    result=json.loads(await h.execute({'driver':'embedded','op':'content'},ctx))
    assert result['success'] and '합성 메일 본문 123' in result['content'], result
    value, evidence=decode_envelope(result, {'protocol':'legacy-envelope','value_path':''})
    assert value['source_complete'] and '합성 메일 본문 123' in value['content']
    await h.execute({'driver':'embedded','op':'close'},ctx)
    print('PYTHON_HANDLER_OK')
asyncio.run(run())
`;
  const clientResult = await promisify(execFile)(path.join(repo, '.venv/bin/python3'), ['-c', client], {
    cwd: repo, env: { ...process.env, PYTHONPATH: path.join(repo, 'backend'), INDIEBIZ_RUNTIME_STATE_DIR: root, FIXTURE_URL: `${origin}/mail` }, timeout: 45000,
  });
  check(clientResult.stdout.includes('PYTHON_HANDLER_OK'), 'Python handler to Electron authenticated DOM');
  r = await call({ op: 'tab', mode: 'close' }); check(r.success, 'explicit tab close verified');
  r = await call({ op: 'navigate', url: `${origin}/mail` }); check(r.success, 'new target after closed tab');
  console.log(`ACCEPTANCE_OK submissions=${submissions}`);
}
app.whenReady().then(run).then(() => app.exit(0)).catch(e => { console.error(e); app.exit(1); });
app.on('will-quit', () => { bridge?.close(); server?.close(); fs.rmSync(root, { recursive: true, force: true }); });
