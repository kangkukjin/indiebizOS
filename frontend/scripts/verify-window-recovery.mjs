/** Run with Electron. Uses hidden test windows and a private HTTP server, never the live app. */
import { app, BrowserWindow } from 'electron';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { installDevServerRecovery } from '../electron/window-recovery.js';

app.setPath('userData', mkdtempSync(path.join(tmpdir(), 'indiebiz-window-recovery-')));
const deadline = setTimeout(() => { console.error('RECOVERY_TIMEOUT'); app.exit(1); }, 20000);
let server;
const windows = [];
async function main() {
  try {
    await app.whenReady();
    server = createServer((_req, res) => {
      res.setHeader('Content-Type', 'text/html');
      res.setHeader('Cache-Control', 'no-store');
      res.setHeader('Connection', 'close');
      res.end('<title>Recovered</title><p>ready</p>');
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const port = server.address().port;
    const origin = `http://127.0.0.1:${port}`;
    app.on('browser-window-created', (_event, win) => installDevServerRecovery(win.webContents, { origin }));
    for (const route of ['/', '/#/system-ai']) {
      const win = new BrowserWindow({ show: false });
      windows.push(win);
      await win.loadURL(origin + route);
    }
    console.log('INITIAL_WINDOWS_READY');
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    // Real ERR_CONNECTION_REFUSED in both existing windows and one new window.
    const recoveries = windows.map(win => new Promise(resolve => {
      win.webContents.once('did-navigate', (_event, url) => resolve(url));
    }));
    for (const win of windows) {
      const failed = new Promise(resolve => win.webContents.once('did-fail-load', resolve));
      win.webContents.reloadIgnoringCache();
      await failed;
    }
    const fresh = new BrowserWindow({ show: false });
    windows.push(fresh);
    recoveries.push(new Promise(resolve => fresh.webContents.once('did-navigate', (_event, url) => resolve(url))));
    await fresh.loadURL(origin + '/?fresh=1#/project/demo').catch(() => {});
    console.log('OUTAGE_REPRODUCED');
    // Keep the server down long enough to observe at least one failed retry.
    await new Promise(resolve => setTimeout(resolve, 700));
    await new Promise(resolve => server.listen(port, '127.0.0.1', resolve));
    console.log('SERVER_RESTARTED');
    const recovered = await Promise.all(recoveries);
    assert.deepEqual(recovered, [origin + '/', origin + '/#/system-ai', origin + '/?fresh=1#/project/demo']);
    for (const win of windows) {
      assert.equal(await win.webContents.executeJavaScript('document.title'), 'Recovered');
      win.destroy();
    }
    console.log(JSON.stringify({ result: 'passed', recovered_windows: recovered.length, routes_preserved: true }));
    clearTimeout(deadline);
    await new Promise(resolve => server.close(resolve));
    app.exit(0);
  } catch (error) {
    console.error(error);
    app.exit(1);
  }

}
void main();
