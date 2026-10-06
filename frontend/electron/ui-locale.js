import { app, BrowserWindow, ipcMain, Menu } from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createUI } from '../i18n/runtime.mjs';

const catalog = JSON.parse(fs.readFileSync(new URL('../i18n/catalog.json', import.meta.url), 'utf8'));
let saved = null;
const preference = path.join(app.getPath('userData'), 'ui-locale.json');
try { saved = JSON.parse(fs.readFileSync(preference, 'utf8')).locale; } catch {}
export const nativeUI = createUI(catalog, { localStorage: { getItem: () => saved } });
export const nativeText = source => nativeUI.source('native:ui', source);
export const nativeTitle = (source, suffix = '') => ({ uiTitle: source, suffix });

// Explicit title descriptors leave project names, paths and document titles untouched.
// Electron 의 getAllWindows()/getFocusedWindow() 는 생성자 이름이 정확히 BrowserWindow 인 창만 돌려준다 —
// 상속 클래스로 만들면 언어 전파와 기존 "모든 창" 처리에서 그 창이 통째로 빠진다(실창 검사로 확인).
// 그래서 `new LocalizedWindow(...)` 는 진짜 BrowserWindow 를 돌려주고, 정적 메서드는 그대로 물려받는다.
export function LocalizedWindow(options) {
  const descriptor = options.title?.uiTitle ? options.title : null;
  const title = () => nativeText(descriptor.uiTitle) + (descriptor.suffix ? ` — ${descriptor.suffix}` : '');
  const win = new BrowserWindow(descriptor ? { ...options, title: title() } : options);
  if (options.title) win.on('page-title-updated', event => event.preventDefault());
  if (descriptor) {
    const unsubscribe = nativeUI.subscribe(() => { if (!win.isDestroyed()) win.setTitle(title()); });
    win.once('closed', unsubscribe);
  }
  return win;
}
Object.setPrototypeOf(LocalizedWindow, BrowserWindow);
LocalizedWindow.prototype = BrowserWindow.prototype;
export function nativeMenu(template) {
  return Menu.buildFromTemplate(template.map(item => ({ ...item,
    ...(item.label ? { label: nativeText(item.label) } : {}),
    ...(Array.isArray(item.submenu) ? { submenu: nativeMenu(item.submenu) } : {}),
  })));
}
function trusted(event) {
  const frame = event.senderFrame;
  if (!frame || frame !== event.sender.mainFrame) return false;
  const url = new URL(frame.url);
  if (!app.isPackaged && url.origin === 'http://localhost:5173') return true;
  if (url.protocol !== 'file:') return false;
  return fileURLToPath(url) === fileURLToPath(new URL('../dist/index.html', import.meta.url));
}
export function installUILocale() {
  ipcMain.handle('ui-locale:get', event => trusted(event) ? saved : null);
  ipcMain.handle('ui-locale:set', (event, locale) => {
    if (!trusted(event) || typeof locale !== 'string' || !Object.hasOwn(catalog.languages, locale)) return false;
    fs.mkdirSync(path.dirname(preference), { recursive: true });
    const temp = preference + '.tmp';
    fs.writeFileSync(temp, JSON.stringify({ locale }));
    fs.renameSync(temp, preference);
    saved = locale;
    nativeUI.setLocale(locale);
    for (const win of BrowserWindow.getAllWindows()) {
      if (!win.isDestroyed()) win.webContents.send('ui-locale:changed', locale);
    }
    return true;
  });
}
