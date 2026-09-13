// 실제 창 생성기·preload만 사용한다. main.js의 백엔드·예약작업 수명은 시작하지 않는다.
import { app, BrowserWindow, ipcMain } from 'electron';
import { createToolWindow, registerToolWindowIPC } from '../electron/windows.js';
import { fileURLToPath } from 'node:url';
app.setPath('userData', process.env.VOCAB_TEST_PROFILE);
app.whenReady().then(() => {
  registerToolWindowIPC();
  ipcMain.handle('get-api-port', () => 8765);
  globalThis.openVocabularyTestWindow = createToolWindow;
  globalThis.openLauncherTestWindow = (native) => {
    const win = new BrowserWindow({ width: 1100, height: 800,
      webPreferences: { preload: native ? fileURLToPath(new URL('../electron/preload.js', import.meta.url)) : undefined } });
    win.loadURL('http://localhost:5173/#/');
  };
  new BrowserWindow({ show: false }).loadURL('about:blank');
});
