import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { installRemoteDesktop, trustedDesktopFrame } from './remote-desktop.js';

const app = { isPackaged: false };
const event = (url = 'http://localhost:5173/') => { const frame = { url }; return { senderFrame: frame, sender: { mainFrame: frame } }; };

test('only the application main frame may open a desktop', async () => {
  let handler;
  installRemoteDesktop({ app, ipcMain: { handle(_name, fn) { handler = fn; } } });
  for (const url of ['https://attacker.example/', 'http://localhost:5173.attacker.example', 'http://localhost:8765/']) {
    await assert.rejects(handler(event(url), 'guestpc-abc'), /Forbidden/);
  }
  assert.equal(trustedDesktopFrame(app, { ...event(), sender: { mainFrame: {} } }), false);
  await assert.rejects(handler(event(), 'guestpc-abc/../../'), /Forbidden/);
});

test('all OS use an isolated viewer, double clicks reuse it, old helpers explain update', async () => {
  const original = globalThis.fetch;
  let handler, capability = true, os = 'windows';
  const created = [];
  class Window extends EventEmitter {
    constructor(options) { super(); this.options = options; this.webContents = new EventEmitter(); this.webContents.setIgnoreMenuShortcuts = () => {};
      this.webContents.setWindowOpenHandler = fn => { this.popup = fn; }; created.push(this); }
    setMenu() {} isDestroyed() { return false; } show() {} focus() { this.focused = true; }
    async loadURL(url) { this.url = url; }
  }
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ items: [{ device_id: 'guestpc-abc', alias: 'PC', registration: { state: 'active', capabilities: { desktop_stream: capability, os } } }] }) });
  try {
    installRemoteDesktop({ app, BrowserWindow: Window, ipcMain: { handle(_name, fn) { handler = fn; } } });
    for (os of ['windows', 'linux', 'darwin']) {
      await Promise.all([handler(event(), 'guestpc-abc'), handler(event(), 'guestpc-abc')]);
      const win = created.at(-1);
      assert.match(win.url, /#\/remote-screen\/guestpc-abc$/);
      assert.equal(win.options.webPreferences.nodeIntegration, false);
      assert.equal(win.options.webPreferences.sandbox, true);
      assert.deepEqual(win.popup(), { action: 'deny' });
      assert.equal(created.length, ['windows', 'linux', 'darwin'].indexOf(os) + 1);
      win.emit('closed');
    }
    capability = false;
    await assert.rejects(handler(event(), 'guestpc-abc'), /헬퍼를 교체/);
    assert.equal(created.length, 3);
  } finally { globalThis.fetch = original; }
});
