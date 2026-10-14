import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { usesDevServer } from './renderer-mode.js';
import { installMediaCall, trustedMediaOrigin } from './media-call.js';
import { trustedDesktopFrame } from './remote-desktop.js';
import { EventEmitter } from 'node:events';

test('source development, source preview and packaged renderer modes are distinct', () => {
  assert.equal(usesDevServer({ isPackaged: false }, ['electron', '.']), true);
  assert.equal(usesDevServer({ isPackaged: false }, ['electron', '.', '--preview']), false);
  assert.equal(usesDevServer({ isPackaged: true }, []), false);
  const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url)));
  assert.match(pkg.scripts['electron:preview'], /electron \. --preview$/);
  assert.doesNotMatch(pkg.scripts['electron:dev'], /--preview/);
});

test('preview opens built auxiliary UI and does not trust the development origin', async () => {
  process.argv.push('--preview');
  const app = { isPackaged: false };
  const opened = [];
  class Window extends EventEmitter {
    constructor() { super(); this.webContents = new EventEmitter();
      this.webContents.setIgnoreMenuShortcuts = () => {};
      this.webContents.setWindowOpenHandler = () => {}; }
    setMenu() {}
    async loadURL() { assert.fail('preview must not contact a Vite server'); }
    async loadFile(file, options) { opened.push({ file, options }); }
  }
  try {
    assert.equal(trustedMediaOrigin(app, 'http://localhost:5173/'), false);
    const frame = { url: 'http://localhost:5173/' };
    assert.equal(trustedDesktopFrame(app, { senderFrame: frame, sender: { mainFrame: frame } }), false);
    const control = installMediaCall({ app, BrowserWindow: Window, ipcMain: { handle() {} } });
    await control.open('a'.repeat(32));
    assert.match(opened[0].file, /dist\/index\.html$/);
    assert.equal(opened[0].options.hash, '/media-call/' + 'a'.repeat(32));
  } finally { process.argv.pop(); }
});
