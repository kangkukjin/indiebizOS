/** 실제 ChatView: 초안→도구→교정 final(response)→이력 재로드. 모델/실 계정 API 호출 없음. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readdirSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const lib = path.join(frontend, '../.venv/lib');
const python = readdirSync(lib).find(name => name.startsWith('python'));
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(lib, python, 'site-packages/playwright/driver/package'));
const denied = '저는 눈이 없어서 이미지를 볼 수 없습니다.';
const corrected = '이미지를 확인했습니다. 고양이가 있습니다.';
const previous = '이전 대화는 보존합니다.';
const saved = [{ id: 1, is_agent: true, content: previous, timestamp: '2026-09-15T09:00:00' }];
const server = await createServer({ root: frontend,
  cacheDir: 'node_modules/.vite-capability',
  optimizeDeps: { entries: ['src/components/chat/ChatView.tsx'], include: ['react', 'react-dom/client'] },
  server: { host: '127.0.0.1', port: 0, strictPort: false, open: false },
  plugins: [{ name: 'capability-chat-fixture', configureServer(vite) {
    vite.middlewares.use('/__capability_chat', async (_req, res) => {
      const html = await vite.transformIndexHtml('/__capability_chat', `<!doctype html><html><head></head>
        <body><div id="root"></div><script type="module">
        import React from '/node_modules/.vite-capability/deps/react.js';
        import ReactDOM from '/node_modules/.vite-capability/deps/react-dom_client.js';
        import {ChatView} from '/src/components/chat/ChatView.tsx';
        import '/src/index.css';
        ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(ChatView, {
          chatTarget: {type:'agent',projectId:'fixture',agent:{id:'fixture',name:'검증 에이전트',ai:{provider:'deepseek',model:'fixture'}}}
        }));
        </script></body></html>`);
      res.setHeader('Content-Type', 'text/html'); res.end(html);
    });
  } }],
});
let browser;
try {
  await server.listen();
  const port = server.httpServer.address().port;
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1100, height: 800 } });
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', error => { errors.push(error.message); console.error('fixture page:', error.message); });
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.port === String(port)) return route.continue();
    const body = url.pathname.endsWith('/messages') ? { messages: saved.slice().reverse() }
      : /undelivered/.test(url.pathname) ? [] : {};
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body),
      headers: { 'Access-Control-Allow-Origin': '*' } });
  });
  await page.addInitScript(() => {
    window.__sockets = [];
    class FixtureSocket {
      static OPEN = 1;
      readyState = 1;
      constructor() { window.__sockets.push(this); setTimeout(() => this.onopen?.({}), 0); }
      send() {}
      close() { this.readyState = 3; }
    }
    window.WebSocket = FixtureSocket;
    window.__emit = value => window.__sockets.at(-1).onmessage({ data: JSON.stringify(value) });
  });
  await page.goto(`http://127.0.0.1:${port}/__capability_chat`);
  await page.getByText(previous, { exact: true }).waitFor();
  const emit = value => page.evaluate(value => window.__emit(value), value);
  await emit({ type: 'start' });
  await emit({ type: 'stream_chunk', content: denied });
  await page.getByText(denied, { exact: true }).waitFor();
  await emit({ type: 'tool_start', id: 'img', name: 'read_image', input: {} });
  await page.getByText(denied, { exact: true }).waitFor(); // 초안이 별도 말풍선이 된 경로
  await emit({ type: 'tool_result', id: 'img', name: 'read_image', result: '고양이' });
  saved.push({ id: 2, is_agent: true, content: corrected, timestamp: '2026-09-15T09:01:00' });
  await emit({ type: 'response', message_id: 2, content: corrected });
  await page.getByText(corrected, { exact: true }).waitFor();
  assert.equal(await page.getByText(denied, { exact: true }).count(), 0);
  assert.equal(await page.getByText(previous, { exact: true }).count(), 1);
  await emit({ type: 'response', message_id: 2, content: corrected });
  assert.equal(await page.getByText(corrected, { exact: true }).count(), 1);
  await page.reload();
  await page.getByText(corrected, { exact: true }).waitFor();
  assert.equal(await page.getByText(denied, { exact: true }).count(), 0);
  assert.equal(await page.getByText(previous, { exact: true }).count(), 1);
  assert.deepEqual(errors, []);
  const out = path.join(frontend, '../outputs/capability_guard');
  mkdirSync(out, { recursive: true });
  await page.screenshot({ path: path.join(out, 'chat-adopted.png'), fullPage: true });
  console.log('PASS: 실제 ChatView 초안 교체·중복 방지·이력 재로드 일치');
} finally {
  await browser?.close();
  await server.close();
}
