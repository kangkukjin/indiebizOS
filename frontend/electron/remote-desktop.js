import { usesDevServer } from './renderer-mode.js';
/** A registered helper owns capture and input; the cockpit opens only its viewer. */
import { fileURLToPath } from 'node:url';
import path from 'node:path';

export function trustedDesktopFrame(app, event) {
  const frame = event.senderFrame;
  if (!frame || frame !== event.sender.mainFrame) return false;
  let url;
  try { url = new URL(frame.url); } catch { return false; }
  return (usesDevServer(app) && url.origin === 'http://localhost:5173') ||
    (url.protocol === 'file:' && fileURLToPath(url) === fileURLToPath(new URL('../dist/index.html', import.meta.url)));
}

export function installRemoteDesktop({ app, ipcMain, BrowserWindow }) {
  const windows = new Map();
  ipcMain.handle('remote-desktop:open', async (event, device) => {
    if (!trustedDesktopFrame(app, event) || typeof device !== 'string' || !/^guestpc-[a-f0-9]+$/.test(device)) throw new Error('Forbidden');
    const old = windows.get(device);
    if (old && !old.isDestroyed()) { old.show(); old.focus(); return { route: 'helper' }; }
    const response = await fetch('http://127.0.0.1:8765/remote-pcs', { signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error('원격 PC 목록을 불러오지 못했습니다.');
    const pc = (await response.json()).items?.find(item => item.device_id === device && !item.revoked && item.registration?.state === 'active');
    if (!pc) throw new Error('등록된 PC를 찾을 수 없습니다.');
    if (!pc.registration.capabilities?.desktop_stream) throw new Error('이 PC의 헬퍼를 교체한 뒤 화면 공유를 다시 여세요.');
    // Recheck after the asynchronous lookup to avoid duplicate windows on double click.
    const existing = windows.get(device);
    if (existing && !existing.isDestroyed()) { existing.focus(); return { route: 'helper' }; }
    const win = new BrowserWindow({ width: 1280, height: 850, minWidth: 640, minHeight: 480,
      title: `${pc.alias} · 화면 공유`, autoHideMenuBar: true,
      webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true,
        preload: path.join(fileURLToPath(new URL('.', import.meta.url)), 'preload.js') } });
    windows.set(device, win);
    win.setMenu(null);
    win.webContents.setIgnoreMenuShortcuts(true);
    win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    win.webContents.on('will-navigate', event => event.preventDefault());
    win.on('closed', () => windows.delete(device));
    const hash = `/remote-screen/${device}`;
    if (usesDevServer(app)) await win.loadURL(`http://localhost:5173/#${hash}`);
    else await win.loadFile(fileURLToPath(new URL('../dist/index.html', import.meta.url)), { hash });
    return { route: 'helper' };
  });
}
