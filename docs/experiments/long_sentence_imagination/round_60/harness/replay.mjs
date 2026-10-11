// Run full IBL through a fresh real Electron guest, separate from the user's app.
import { app, BrowserWindow, ipcMain } from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { startEmbeddedBridge } from '../../../../../frontend/electron/embedded-browser-bridge.js';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../../..');
const temporary = fs.mkdtempSync('/tmp/ib-browser60-');
fs.mkdirSync(path.join(temporary, 'profile'), { recursive: true });
app.setPath('userData', path.join(temporary, 'profile'));
let win, bridge;
app.whenReady().then(async () => {
  win = new BrowserWindow({ show: false, webPreferences: {
    nodeIntegration: true, contextIsolation: false, webviewTag: true,
  } });
  bridge = startEmbeddedBridge({ basePath: repo, runtimePath: temporary,
    vault: { listAll: () => [], getCredential: () => null }, show: () => {},
    changed: () => { if (!win.isDestroyed()) win.webContents.send('refresh'); },
  });
  win.webContents.on('did-attach-webview', (_event, guest) => bridge.tabs.attach(guest));
  ipcMain.handle('list', () => bridge.tabs.ui('list'));
  ipcMain.handle('bind', (_event, id, wcId) => bridge.tabs.bind(id,
    [...bridge.tabs.guests].find(wc => wc.id === wcId)));
  const html = `<script>const {ipcRenderer}=require('electron');const made=new Set();
    ipcRenderer.on('refresh',async()=>{for(const r of await ipcRenderer.invoke('list')) {
      if(!r.pending||made.has(r.id))continue;made.add(r.id);const w=document.createElement('webview');
      w.setAttribute('partition','browser60');w.src=r.url;w.style='width:900px;height:700px';
      w.addEventListener('dom-ready',()=>ipcRenderer.invoke('bind',r.id,w.getWebContentsId()));document.body.append(w);
    }});</script>`;
  await win.loadURL(`data:text/html,${encodeURIComponent(html)}`);
  await bridge.ready;
  const result = await promisify(execFile)(path.join(repo, '.venv/bin/python3'),
    ['docs/experiments/long_sentence_imagination/round_60/harness/replay.py', ...process.argv.slice(2)], {
      cwd: repo, env: { ...process.env, PYTHONPATH: path.join(repo, 'backend'),
        INDIEBIZ_RUNTIME_STATE_DIR: temporary }, timeout: 180000, maxBuffer: 4 * 1024 * 1024,
    });
  console.log(result.stdout);
  if (result.stderr) console.error(result.stderr);
  app.exit(0);
}).catch(error => { console.error(error); app.exit(1); });
app.on('will-quit', () => {
  bridge?.close();
  fs.rmSync(temporary, { recursive: true, force: true });
});
