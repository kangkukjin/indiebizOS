import { app, BrowserWindow, Menu } from 'electron';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const frontend = fileURLToPath(new URL('..', import.meta.url));
app.setPath('userData', process.env.UI_TEST_PROFILE);
app.whenReady().then(async () => {
const { installUILocale, nativeUI, nativeMenu } = await import('../electron/ui-locale.js');
const { createToolWindow, createFolderWindow } = await import('../electron/windows.js');
installUILocale();
const menu = () => Menu.setApplicationMenu(nativeMenu([{label:'편집',submenu:[{role:'copy',label:'복사'}]}]));
menu(); nativeUI.subscribe(menu);
// Exercise the production window factories against the built renderer, without Vite or the live backend.
BrowserWindow.prototype.loadURL = function(url) {
  const parsed = new URL(url);
  if (parsed.origin !== 'http://localhost:5173') throw new Error('Unexpected fixture URL');
  return this.loadFile(path.join(frontend,'dist/index.html'),{hash:parsed.hash.slice(1)});
};
globalThis.openUITestWindows = () => {
  createToolWindow('guides'); createToolWindow('prompt-composition'); createFolderWindow('test-user','문서');
};
app.on('window-all-closed', () => {});
}).catch(error => { console.error(error); app.exit(1); });
