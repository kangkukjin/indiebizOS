/** Media call windows: one sandboxed BrowserWindow per session at `#/media-call/<session_id>`. */
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { trustedDesktopFrame } from './remote-desktop.js';

export const SESSION_ID = /^[a-f0-9]{16,64}$/;
const DIST_INDEX = new URL('../dist/index.html', import.meta.url);

/** Origins whose pages may use camera/microphone/display capture (contract: only our own windows). */
export function trustedMediaOrigin(app, url, backendOrigin = 'http://127.0.0.1:8765') {
  let parsed;
  try { parsed = new URL(url); } catch { return false; }
  if (parsed.protocol === 'file:') { try { return fileURLToPath(parsed) === fileURLToPath(DIST_INDEX); } catch { return false; } }
  if (!app.isPackaged && parsed.origin === 'http://localhost:5173') return true;
  return parsed.origin === backendOrigin;
}

/** session.setPermissionRequestHandler body: media/display-capture only for our windows; others keep `fallback`. */
export function mediaPermissionDecision(app, permission, requestingUrl, fallback = true, backendOrigin) {
  if (permission === 'media' || permission === 'display-capture' || permission === 'mediaKeySystem') {
    return trustedMediaOrigin(app, requestingUrl, backendOrigin);
  }
  return fallback;
}

export function installMediaCall({ app, ipcMain, BrowserWindow }) {
  const windows = new Map();
  async function open(sessionId) {
    if (typeof sessionId !== 'string' || !SESSION_ID.test(sessionId)) throw new Error('Forbidden');
    const existing = windows.get(sessionId);
    if (existing && !existing.isDestroyed()) { existing.show(); existing.focus(); return { opened: false }; }
    const win = new BrowserWindow({ width: 960, height: 680, minWidth: 520, minHeight: 420,
      title: '통화', autoHideMenuBar: true, backgroundColor: '#0c0a09',
      webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true,
        preload: path.join(fileURLToPath(new URL('.', import.meta.url)), 'preload.js') } });
    windows.set(sessionId, win);
    win.setMenu(null);
    win.webContents.setIgnoreMenuShortcuts(true);
    win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    win.webContents.on('will-navigate', event => event.preventDefault());
    win.on('closed', () => { if (windows.get(sessionId) === win) windows.delete(sessionId); });
    const hash = `/media-call/${sessionId}`;
    if (!app.isPackaged) await win.loadURL(`http://localhost:5173/#${hash}`);
    else await win.loadFile(fileURLToPath(DIST_INDEX), { hash });
    return { opened: true };
  }
  ipcMain.handle('media-call:open', async (event, sessionId) => {
    if (!trustedDesktopFrame(app, event)) throw new Error('Forbidden');
    return open(sessionId);
  });
  return { open, windows };
}
