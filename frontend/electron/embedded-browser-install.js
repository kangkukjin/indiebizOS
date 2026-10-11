import { app, ipcMain, webContents } from 'electron';
import { startEmbeddedBridge } from './embedded-browser-bridge.js';
import { fault } from './embedded-browser-tabs.js';
import * as vault from './forage-passwords.js';

export function installEmbeddedBrowser(basePath, getWindow) {
  const bridge = startEmbeddedBridge({ basePath, runtimePath: process.env.INDIEBIZ_RUNTIME_STATE_DIR,
    vault, show: () => {
      const win = getWindow(); if (!win || win.isDestroyed()) throw fault('BROWSER_UI_UNAVAILABLE');
      win.show(); win.webContents.send('open-forage-url', '');
    }, changed: () => { const win = getWindow(); if (win && !win.isDestroyed()) win.webContents.send('embedded-browser-changed'); } });
  const trusted = event => {
    const main = getWindow()?.webContents;
    if (!bridge || event.sender !== main || event.senderFrame !== main.mainFrame) throw fault('FORBIDDEN');
  };
  ipcMain.handle('embedded-browser-ui', (event, action, id, contentsId) => {
    trusted(event);
    if (action === 'bind') return bridge.tabs.bind(id, webContents.fromId(contentsId));
    if (!['list', 'share', 'pause'].includes(action)) throw fault('UNSUPPORTED_OPERATION');
    return bridge.tabs.ui(action, id);
  });
  ipcMain.handle('forage-pw-fill', async (event, contentsId, username) => {
    trusted(event);
    const r = bridge.tabs.byContents(contentsId);
    if (!r || r.owner) return { success: false, controlled: !!r?.owner };
    r.paused = false;
    try { return await bridge.auth.run(r, { mode: 'login' }, Date.now() + 10000, username); }
    catch { return { success: false }; }
  });
  app.once('will-quit', () => bridge?.close());
  bridge?.ready.catch(() => console.error('[EmbeddedBrowser] 로컬 연결 시작 실패'));
  return bridge;
}
