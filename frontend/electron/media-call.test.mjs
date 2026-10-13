import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { fileURLToPath } from 'node:url';
import { installMediaCall, mediaPermissionDecision, trustedMediaOrigin, SESSION_ID } from './media-call.js';

const app = { isPackaged: false };
const event = (url = 'http://localhost:5173/') => { const frame = { url }; return { senderFrame: frame, sender: { mainFrame: frame } }; };
const distIndex = 'file://' + fileURLToPath(new URL('../dist/index.html', import.meta.url));

test('media permissions are granted only to our own windows; other permissions keep the fallback', () => {
  for (const url of ['http://localhost:5173/#/media-call/abc', distIndex, 'http://127.0.0.1:8765/launcher/app']) {
    assert.equal(trustedMediaOrigin(app, url), true, url);
    assert.equal(mediaPermissionDecision(app, 'media', url, false), true, url);
  }
  for (const url of ['https://example.invalid/', 'http://localhost:5173.attacker.invalid/', 'file:///tmp/other.html', 'not a url']) {
    assert.equal(trustedMediaOrigin(app, url), false, url);
    assert.equal(mediaPermissionDecision(app, 'media', url, true), false, url);
    assert.equal(mediaPermissionDecision(app, 'display-capture', url, true), false, url);
  }
  assert.equal(trustedMediaOrigin({ isPackaged: true }, 'http://localhost:5173/'), false, 'dev server is not trusted when packaged');
  assert.equal(mediaPermissionDecision(app, 'notifications', 'https://example.invalid/', true), true);
  assert.equal(mediaPermissionDecision(app, 'geolocation', 'https://example.invalid/', false), false);
});

test('one window per session, re-opens focus the existing window, foreign frames and bad ids are refused', async () => {
  let handler;
  const created = [];
  class Window extends EventEmitter {
    constructor(options) { super(); this.options = options; this.webContents = new EventEmitter(); this.webContents.setIgnoreMenuShortcuts = () => {};
      this.webContents.setWindowOpenHandler = fn => { this.popup = fn; }; created.push(this); }
    setMenu() {} isDestroyed() { return false; } show() {} focus() { this.focused = true; }
    async loadURL(url) { this.url = url; }
  }
  const control = installMediaCall({ app, BrowserWindow: Window, ipcMain: { handle(_name, fn) { handler = fn; } } });
  const sid = 'a'.repeat(32);
  assert.ok(SESSION_ID.test(sid));
  await assert.rejects(handler(event('https://attacker.invalid/'), sid), /Forbidden/);
  await assert.rejects(handler(event(), 'not-hex/../x'), /Forbidden/);
  await assert.rejects(control.open(''), /Forbidden/);
  assert.deepEqual(await handler(event(), sid), { opened: true });
  const win = created.at(-1);
  assert.match(win.url, /#\/media-call\/a{32}$/);
  assert.equal(win.options.webPreferences.sandbox, true);
  assert.equal(win.options.webPreferences.contextIsolation, true);
  assert.equal(win.options.webPreferences.nodeIntegration, false);
  assert.deepEqual(win.popup(), { action: 'deny' });
  assert.deepEqual(await control.open(sid), { opened: false });
  assert.equal(win.focused, true);
  assert.equal(created.length, 1);
  await control.open('b'.repeat(32));
  assert.equal(created.length, 2);
  win.emit('closed');
  assert.deepEqual(await control.open(sid), { opened: true });
  assert.equal(created.length, 3);
});
