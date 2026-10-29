// Real native teardown regression. Isolated profile, local pages, no live backend.
const { app, BrowserWindow } = require('electron');
const assert = require('node:assert/strict');
const http = require('node:http');
app.setPath('userData', process.env.CRASH_TEST_PROFILE);
app.commandLine.appendSwitch('js-flags', '--expose-gc');
app.on('window-all-closed', () => {});
const cycles = Number(process.env.CRASH_TEST_CYCLES || 40);
assert.ok(Number.isInteger(cycles) && cycles > 0 && cycles <= 1000);
const server = http.createServer((req, res) => {
  const reply = () => {
    res.setHeader('Content-Type', 'text/html');
    res.end('<html><body><h1>Fixture content</h1><input aria-label="Name">' +
      '<button onclick="document.querySelector(\'h1\').textContent=\'Clicked\'">Act</button>' +
      (req.url.startsWith('/child') ? '' : '<iframe name="child" src="/child"></iframe>') + '</body></html>');
  };
  if (req.url.startsWith('/slow')) setTimeout(reply, 100).unref();
  else reply();
});
app.whenReady().then(async () => {
  const { EmbeddedTabs } = await import('../electron/embedded-browser-tabs.js');
  const tabs = new EmbeddedTabs({ show() {}, changed() {} });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  let host, guest;
  for (let i = 0; i < cycles; i++) {
    if (!host || host.isDestroyed()) {
      host = new BrowserWindow({ show: false, webPreferences: {
        webviewTag: true, nodeIntegration: false, contextIsolation: true,
      } });
      host.webContents.on('did-attach-webview', (_e, wc) => { guest = wc; tabs.attach(wc); });
      await host.loadURL('data:text/html,<html><body></body></html>');
    }
    await host.webContents.executeJavaScript(`new Promise(resolve => {
      const w = document.createElement('webview'); w.src = '${origin}/?${i}';
      w.style='width:500px;height:300px';
      // dom-ready precedes child-frame loads; wait for the full fixture before
      // asserting iframe content (especially under the parallel pytest load).
      w.addEventListener('did-finish-load', () => resolve(true), {once:true}); document.body.append(w);
    })`);
    const id = `tab-${i}`; tabs.bind(id, guest);
    const r = tabs.records.get(id); r.owner = 'fixture'; tabs.active.set('fixture', id);
    const snapshot = await tabs.page(r, 'snapshot');
    assert.ok(snapshot.elements.some(e => e.name === 'Act'));
    const button = snapshot.elements.find(e => e.name === 'Act').ref;
    await tabs.page(r, 'click', { ref: button, document_id: snapshot.document_id });
    assert.match((await tabs.page(r, 'content')).content, /Clicked/);
    const frames = await tabs.frames(r);
    r.frame = frames.find(f => !f.main).id;
    assert.match((await tabs.page(r, 'content')).content, /Fixture content/);
    r.frame = null;
    // Keep the attached debugger across RenderFrameHost swaps, then destroy.
    await guest.loadURL(`${origin}/next?${i}`);
    assert.match((await tabs.page(r, 'content')).content, /Fixture content/);
    const destroyed = new Promise(resolve => guest.once('destroyed', resolve));
    let pending;
    if (i % 4 === 0) {
      pending = assert.rejects(tabs.cdp(r, 'Runtime.evaluate', {
        expression: 'new Promise(() => {})', awaitPromise: true,
      }));
      await host.webContents.executeJavaScript('document.body.replaceChildren()');
    } else if (i % 4 === 1) {
      await tabs.operation('fixture', { op: 'tab', mode: 'close' }, Date.now() + 5000);
    } else if (i % 4 === 2) {
      pending = guest.loadURL(`${origin}/slow?${i}`).catch(() => {});
      await host.webContents.executeJavaScript('document.body.replaceChildren()');
    } else host.destroy();
    await destroyed;
    await pending;
    if (!host.isDestroyed()) await host.webContents.executeJavaScript('document.body.replaceChildren()');
    global.gc?.();
    await new Promise(resolve => setTimeout(resolve, 10));
    assert.equal(tabs.records.size, 0); assert.equal(tabs.guests.size, 0);
    assert.equal(tabs.active.size, 0);
  }
  if (!host.isDestroyed()) host.destroy();
  server.closeAllConnections(); server.close();
  console.log(JSON.stringify({ electron: process.versions.electron, cycles,
    snapshot: true, click: true, iframe: true, navigation: true,
    pendingCommandRemoval: true, ownedClose: true, navigatingRemoval: true, hostClose: true }));
  app.exit(0);
}).catch(error => { console.error(error); app.exit(1); });
setTimeout(() => app.exit(2), 120000).unref();
