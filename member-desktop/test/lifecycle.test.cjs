const test = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');

async function boot() {
  const filename = path.join(__dirname, '../main.cjs');
  const realRequire = createRequire(filename);
  const app = new EventEmitter();
  let ready, win, tray, session, finishStop;
  Object.assign(app, {
    requestSingleInstanceLock: () => true,
    setName() {}, getPath: () => '/unused-member-test',
    setAsDefaultProtocolClient() {}, quitCount: 0,
    quit() { this.quitCount++; },
    whenReady: () => ({then(fn) { ready = fn(); }}),
  });
  class Window extends EventEmitter {
    constructor() {
      super(); win = this; this.destroyed = false; this.shown = 0;
      this.webContents = new EventEmitter();
      Object.assign(this.webContents, {
        isDestroyed: () => this.destroyed,
        send: () => this.check(), setWindowOpenHandler() {},
        session: {setPermissionRequestHandler() {}, webRequest: {onBeforeRequest() {}}},
      });
    }
    check() { if (this.destroyed) throw Error('Object has been destroyed'); }
    isDestroyed() { return this.destroyed; }
    show() { this.check(); this.shown++; }
    hide() { this.check(); this.hidden = true; }
    async loadFile() { this.check(); }
  }
  class Session {
    constructor(options) { session = this; this.onExit = options.onExit; }
    async start() {}
    stop() { return new Promise(resolve => { finishStop = resolve; }); }
  }
  const electron = {
    app, BrowserWindow: Window, ipcMain: {handle() {}},
    safeStorage: {}, dialog: {}, shell: {},
    Tray: class extends EventEmitter {
      constructor() { super(); tray = this; }
      setToolTip() {} setContextMenu(menu) { this.menu = menu; }
    },
    Menu: {buildFromTemplate: items => items, setApplicationMenu() {}},
    nativeImage: {createFromDataURL() {}},
  };
  vm.runInNewContext(fs.readFileSync(filename, 'utf8'), {
    __dirname: path.dirname(filename), process: {...process, argv: ['node']}, console, setImmediate,
    setTimeout: () => ({unref() {}}), setInterval: () => ({unref() {}}), clearTimeout() {},
    require(name) {
      if (name === 'electron') return electron;
      if (name === './session.cjs') return {MemberSession: Session};
      if (name === './updates.cjs') return {RuntimeUpdates: class {
        constructor({baseline}) { this.baseline = baseline; }
        recover() { return this.baseline; }
      }};
      return realRequire(name);
    },
  }, {filename});
  await ready;
  return {app, win, tray, session, finishStop: () => finishStop()};
}

test('ordinary close hides the member window; activation opens it again', async () => {
  const {app, win} = await boot();
  let prevented = false;
  win.emit('close', {preventDefault() { prevented = true; }});
  assert.equal(prevented, true);
  assert.equal(win.hidden, true);
  app.emit('activate');
  assert.equal(win.shown, 1);
});

test('late activation, tray clicks and helper exit cannot use a destroyed window', async () => {
  const {app, win, tray, session} = await boot();
  win.destroyed = true;
  assert.doesNotThrow(() => {
    app.emit('activate');
    app.emit('second-instance', {}, []);
    tray.emit('click');
    tray.menu[0].click();
    tray.menu[1].click();
    session.onExit();
  });
});

test('losing the last window terminates the app instead of leaving it stranded', async () => {
  const {app, win, session} = await boot();
  win.destroyed = true;
  win.emit('closed');
  app.emit('window-all-closed');
  assert.equal(app.quitCount, 1);
  assert.doesNotThrow(() => { app.emit('activate'); session.onExit(); });
});

test('activation during graceful shutdown cannot reopen the window', async () => {
  const {app, win, finishStop} = await boot();
  app.emit('before-quit', {preventDefault() {}});
  assert.equal(app.quitCount, 0);
  app.emit('activate');
  assert.equal(win.shown, 0);
  await Promise.resolve();
  finishStop();
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.quitCount, 1);
});

test('an already stopped helper resumes quit after the cancelled native quit unwinds', async () => {
  const {app, session} = await boot();
  session.stop = async () => {};
  app.emit('before-quit', {preventDefault() {}});
  for (let i = 0; i < 8; i++) await Promise.resolve();
  assert.equal(app.quitCount, 0, 'microtasks still run inside the native quit callback');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.quitCount, 1);
});
