/** 실행: Vite가 켜진 상태에서 node scripts/test-vocabulary-windows.mjs.
 * Python Playwright의 JS 드라이버 또는 PLAYWRIGHT_MODULE을 사용. API·프로필은 시험 전용.
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const pythonLib = path.join(frontend, '../.venv/lib');
const python = readdirSync(pythonLib).find(name => name.startsWith('python'));
const { _electron } = require(process.env.PLAYWRIGHT_MODULE || path.join(pythonLib, python, 'site-packages/playwright/driver/package'));
const profile = mkdtempSync(path.join(tmpdir(), 'indiebiz-vocab-windows-'));
const app = await _electron.launch({ executablePath: require('electron'),
  args: [path.join(frontend, 'scripts/vocabulary-window-fixture.mjs')],
  env: { ...process.env, NODE_ENV: 'development', VOCAB_TEST_PROFILE: profile } });
const desktop = { folders: {
  store: { name: '단어묶음 저장고', parent: 'desktop', x: 24, y: 24 },
  required: { name: '필수 단어묶음', parent: 'desktop', x: 140, y: 24 },
  trash: { name: '쓰레기통', parent: 'desktop', x: 256, y: 24 },
  'folder-a': { name: '읽기', parent: 'desktop', x: 24, y: 180 },
  'folder-b': { name: '쓰기', parent: 'desktop', x: 140, y: 180 },
}, placements: {
  alpha: { parent: 'folder-a', x: 24, y: 24 }, beta: { parent: 'desktop', x: 256, y: 180 },
} };
const packages = ['alpha', 'beta'].map(id => ({ id, name: id, description: `${id} 설명`, installed: true, preparation: [] }));
const changes = [];
const context = app.context();
context.setDefaultTimeout(15000);
await context.addInitScript(() => {
  if (!location.href.startsWith('http://localhost:5173/')) return;
  localStorage.setItem('indiebiz_has_seen_guide', 'true');
  localStorage.setItem('indiebiz_launcher_mode', 'vocabulary'); // 옛 저장값도 정상 모드로 돌아온다.
});
const errors = [];
context.on('page', page => page.on('pageerror', e => errors.push(e.message)));
await context.routeWebSocket(/8765/, socket => socket.close());
await context.route(/https?:\/\/(127\.0\.0\.1|localhost):8765\//, async route => {
  const request = route.request();
  const url = new URL(request.url());
  let body = {};
  if (url.pathname === '/vocabulary/desktop') {
    if (request.method() === 'POST') {
      const edit = request.postDataJSON(); changes.push(edit);
      if (edit.op === 'move') {
        const entry = desktop.placements[edit.item] || desktop.folders[edit.item];
        Object.assign(entry, { parent: edit.parent, x: edit.x, y: edit.y });
      } else if (edit.op === 'rename') desktop.folders[edit.item].name = edit.name;
      else throw new Error(`시험에 없는 쓰기: ${edit.op}`);
    }
    body = desktop;
  } else if (url.pathname === '/vocabulary') body = { packages, revision: changes.length };
  else if (request.method() !== 'GET') throw new Error(`시험 밖 쓰기: ${url.pathname}`);
  else if (url.pathname === '/projects') body = { projects: [] };
  else if (url.pathname === '/switches') body = { switches: [] };
  else if (url.pathname.includes('trash')) body = { projects: [], switches: [], chat_rooms: [] };
  else if (url.pathname === '/multi-chat/rooms') body = { rooms: [] };
  else if (url.pathname.includes('onboarding')) body = { completed: true };
  await route.fulfill({ json: body });
});
const waitFor = async fn => {
  for (let i = 0; i < 80; i++) { if (await fn()) return; await new Promise(resolve => setTimeout(resolve, 100)); }
  assert.fail('창 상태 변경 시간 초과');
};
const open = async id => {
  await app.evaluate((_, folder) => globalThis.openVocabularyTestWindow('vocabulary', folder), id);
  await waitFor(() => app.windows().some(p => p.url().endsWith(`/vocabulary/${id}`)));
  const page = app.windows().find(p => p.url().endsWith(`/vocabulary/${id}`));
  await page.locator('[data-vocab-canvas]').waitFor();
  return page;
};
try {
  console.log('opening root');
  const root = await open('desktop');
  await root.locator('[data-vocab-icon="folder-a"]').dblclick();
  console.log('opening folders');
  const a = await open('folder-a');
  const b = await open('folder-b');
  const count = app.windows().length;
  await open('folder-a');
  assert.equal(app.windows().length, count, '같은 폴더는 기존 창을 복원해야 함');
  console.log('checking native bounds');
  const native = await app.evaluate(({ BrowserWindow }) => {
    const find = id => BrowserWindow.getAllWindows().find(w => w.webContents.getURL().endsWith(`/vocabulary/${id}`));
    find('desktop').setBounds({ x: 20, y: 60, width: 420, height: 340 });
    find('folder-a').setBounds({ x: 550, y: 60, width: 620, height: 450 });
    return { root: find('desktop').getBounds(), folder: find('folder-a').getBounds(),
      resizable: find('folder-a').isResizable(), parent: find('folder-a').getParentWindow() };
  });
  assert(native.resizable && !native.parent);
  assert(native.folder.x > native.root.x + native.root.width, '런처 바깥으로 이동 가능');
  assert.equal(native.folder.width, 620);
  console.log('moving to desktop');
  await a.locator('[data-vocab-icon="alpha"]').click({ button: 'right' });
  await a.getByRole('menuitem', { name: '바탕으로 꺼내기' }).click();
  await root.locator('[data-vocab-icon="alpha"]').waitFor();
  await waitFor(async () => await a.locator('[data-vocab-icon="alpha"]').count() === 0);

  console.log('native drag');
  // 실제 Chromium 마우스 드래그로 폴더에 넣는다.
  await root.locator('[data-vocab-icon="beta"]').dragTo(root.locator('[data-vocab-icon="folder-b"]'));
  await b.locator('[data-vocab-icon="beta"]').waitFor();
  // 창 간 전달되는 HTML DataTransfer를 실제 dragstart에서 만들어 다른 렌더러에 전달.
  const payload = await b.locator('[data-vocab-icon="beta"]').evaluate(el => {
    const dataTransfer = new DataTransfer();
    el.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer }));
    return dataTransfer.getData('application/x-indiebiz-vocabulary');
  });
  assert.equal(JSON.parse(payload).id, 'beta');
  await a.locator('[data-vocab-canvas]').evaluate((el, payload) => {
    const dataTransfer = new DataTransfer();
    dataTransfer.setData('application/x-indiebiz-vocabulary', payload);
    const rect = el.getBoundingClientRect();
    el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer,
      clientX: rect.left + 30, clientY: rect.top + 30 }));
  }, payload);
  await a.locator('[data-vocab-icon="beta"]').waitFor();
  await waitFor(async () => await b.locator('[data-vocab-icon="beta"]').count() === 0);

  await root.locator('[data-vocab-icon="folder-a"]').click({ button: 'right' });
  await root.getByRole('menuitem', { name: '이름 바꾸기' }).click();
  await root.getByRole('textbox', { name: '폴더 이름' }).fill('읽는 것');
  await root.getByRole('button', { name: '저장', exact: true }).click();
  await a.getByRole('heading', { name: '읽는 것', exact: true }).waitFor();
  assert.equal(await a.title(), '읽는 것');
  await root.screenshot({ path: path.join(tmpdir(), 'indiebiz-vocabulary-root.png') });
  await root.close();
  assert(!a.isClosed() && !b.isClosed(), '바탕 창 닫아도 폴더는 유지');
  await a.getByRole('button', { name: '상위 폴더', exact: true }).click();
  const reopened = await open('desktop');
  await reopened.locator('[data-vocab-icon="alpha"]').waitFor();
  assert.deepEqual(changes.map(e => e.op), ['move', 'move', 'move', 'rename']);
  console.log('launcher menu and web navigation');
  for (const native of [true, false]) {
    const next = app.waitForEvent('window');
    await app.evaluate((_, native) => globalThis.openLauncherTestWindow(native), native);
    const launcher = await next;
    await launcher.getByTitle('모드 전환', { exact: true }).click();
    assert.equal(await launcher.getByRole('button', { name: '내 어휘', exact: true }).count(), 0);
    await launcher.getByTitle('모드 전환', { exact: true }).click();
    await launcher.getByTitle('메뉴', { exact: true }).click();
    const button = launcher.getByRole('button', { name: '내 어휘', exact: true });
    assert.equal(await button.evaluate(el => el.previousElementSibling.textContent.trim()), '설정');
    await launcher.screenshot({ path: path.join(tmpdir(), 'indiebiz-vocabulary-menu.png') });
    await button.click();
    if (native) {
      assert(launcher.url().endsWith('#/'));
      await reopened.getByRole('heading', { name: '내 어휘', exact: true }).waitFor();
    } else {
      await launcher.getByRole('heading', { name: '내 어휘', exact: true }).waitFor();
      await launcher.locator('[data-vocab-icon="folder-a"]').dblclick();
      await launcher.getByRole('heading', { name: '읽는 것', exact: true }).waitFor();
      await launcher.getByRole('button', { name: '뒤로', exact: true }).click();
      await launcher.getByRole('heading', { name: '내 어휘', exact: true }).waitFor();
      await launcher.getByRole('button', { name: '뒤로', exact: true }).click();
      await launcher.getByTitle('모드 전환', { exact: true }).waitFor();
    }
    await launcher.close();
  }
  assert.deepEqual(errors, []);
  console.log('PASS: 독립 창·중복 열기·이동/크기 조절·네이티브 드래그·창 간 동기화·이름 변경·닫기/재열기·메뉴 위치·웹 뒤로가기');
} finally {
  await app.close();
  rmSync(profile, { recursive: true, force: true });
}
