import { randomUUID } from 'node:crypto';
import { expression } from './embedded-browser-dom.js';

export const capabilities = ['tab', 'navigate', 'snapshot', 'content', 'click', 'type',
  'press_key', 'select', 'check', 'scroll', 'wait', 'iframe', 'auth', 'close'];
export function fault(code) { return Object.assign(new Error(code), { code }); }
export function checkedURL(value) {
  const u = new URL(value);
  if (!['http:', 'https:', 'about:'].includes(u.protocol) ||
      (u.protocol === 'about:' && u.href !== 'about:blank') || u.username || u.password) throw fault('INVALID_URL');
  return u.href;
}
export function safeURL(value) {
  try { const u = new URL(value); u.search = ''; u.hash = ''; u.username = ''; u.password = ''; return u.href; } catch { return ''; }
}

export class EmbeddedTabs {
  constructor({ show, changed }) {
    this.show = show; this.changed = changed; this.records = new Map(); this.active = new Map();
    this.guests = new Set(); this.queue = Promise.resolve(); this.authOwner = null;
  }
  notice() { this.changed(); }
  attach(wc) {
    this.guests.add(wc);
    wc.on('destroyed', () => {
      this.guests.delete(wc);
      for (const r of this.records.values()) if (r.wc === wc) {
        r.closed = true; r.state = '닫힘';
        if (r.owner && this.active.get(r.owner) === r.id) {
          const parent = this.records.get(r.parent);
          if (parent && !parent.closed) this.active.set(r.owner, parent.id);
          else this.active.delete(r.owner);
        }
        if (this.authOwner === r.owner && !this.active.has(r.owner)) this.authOwner = null;
      }
      this.notice();
    });
    wc.on('before-input-event', () => {
      const r = this.byContents(wc.id);
      if (r?.owner && !r.injecting) this.pause(r);
    });
    wc.on('before-mouse-event', () => { const r = this.byContents(wc.id); if (r?.owner && !r.injecting) this.pause(r); });
    wc.on('did-navigate', () => { const r = this.byContents(wc.id); if (r) { r.frame = null; r.document = null; } });
    wc.on('did-navigate-in-page', () => { const r = this.byContents(wc.id); if (r) r.document = null; });
    wc.on('render-process-gone', () => { const r = this.byContents(wc.id); if (r) this.pause(r); });
    wc.on('did-create-window', popup => {
      this.attach(popup.webContents);
      const parent = this.byContents(wc.id);
      const id = `popup-${randomUUID()}`;
      this.records.set(id, { id, wc: popup.webContents, owner: parent?.owner, parent: parent?.id,
        state: '로그인 창', queue: Promise.resolve(), document: null });
      if (parent?.owner) this.active.set(parent.owner, id);
      this.notice();
    });
  }
  byContents(id) { return [...this.records.values()].find(r => !r.closed && r.wc?.id === id); }
  bind(id, wc) {
    if (!this.guests.has(wc) || wc.isDestroyed()) throw fault('UNREGISTERED_TAB');
    const prior = this.byContents(wc.id);
    if (prior && prior.id !== id) throw fault('TAB_ALREADY_BOUND');
    const r = this.records.get(id) || { id, owner: null, state: '', document: null };
    if (r.closed || (r.wc && r.wc !== wc)) throw fault('TAB_CLOSED');
    r.wc = wc; this.records.set(id, r); this.notice();
    return { tab_id: id, controlled: !!r.owner };
  }
  pause(r) { r.paused = true; r.state = '사용자 조작 중'; r.document = null; this.notice(); }
  ui(action, id) {
    const r = this.records.get(id);
    if (action === 'list') return [...this.records.values()].filter(r => !r.closed).map(r => ({
      id: r.id, url: r.requestURL, pending: !r.wc, state: r.state, controlled: !!r.owner,
    }));
    if (!r) throw fault('TAB_NOT_FOUND');
    if (action === 'pause') this.pause(r);
    if (action === 'share') { r.shared = true; r.paused = false; r.state = 'AI에 맡김'; this.notice(); }
    return { success: true };
  }
  target(owner, id) {
    const r = this.records.get(id || this.active.get(owner));
    if (!r || r.closed || !r.wc || r.wc.isDestroyed()) throw fault('TAB_NOT_FOUND');
    if (r.owner !== owner) {
      if (r.owner || !r.shared) throw fault('TAB_NOT_GRANTED');
      r.owner = owner; r.shared = false;
    }
    this.active.set(owner, r.id);
    return r;
  }
  async create(owner, url, deadline) {
    const id = `ai-${randomUUID()}`;
    // Load blank first: registration must precede all site scripts and password autofill.
    const r = { id, owner, requestURL: 'about:blank', state: 'AI가 여는 중', document: null };
    this.records.set(id, r); this.active.set(owner, id); this.show(); this.notice();
    while (!r.wc && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 40));
    if (!r.wc) { r.closed = true; this.active.delete(owner); this.notice(); throw fault('BROWSER_UI_UNAVAILABLE'); }
    try { await this.navigate(r, { url }, deadline); }
    catch (error) {
      // A failed creation has no returned tab id for the caller to clean up.
      if (!r.paused) { r.closed = true; r.wc.close(); this.active.delete(owner); this.notice(); }
      throw error;
    }
    return r;
  }
  check(r, deadline) {
    if (Date.now() >= deadline) throw fault('DEADLINE_EXCEEDED');
    if (r.closed || r.wc.isDestroyed()) throw fault('TAB_CLOSED');
    if (r.paused) throw fault('USER_TAKEOVER');
  }
  async cdp(r, method, params = {}) {
    if (!r.wc.debugger.isAttached()) {
      r.wc.debugger.attach('1.3');
      if (!r.detachInstalled) {
        r.detachInstalled = true;
        r.wc.debugger.on('detach', () => { r.document = null; r.frame = null; });
      }
    }
    let timer;
    try { return await Promise.race([r.wc.debugger.sendCommand(method, params),
      new Promise((_, reject) => { timer = setTimeout(() => { this.pause(r); reject(fault('BROWSER_TIMEOUT')); }, 10000); })]);
    } finally { clearTimeout(timer); }
  }
  async frames(r) {
    const tree = await this.cdp(r, 'Page.getFrameTree');
    const out = [];
    const walk = (t, main) => { out.push({ id: t.frame.id, name: t.frame.name || '', url: safeURL(t.frame.url), main }); (t.childFrames || []).forEach(c => walk(c, false)); };
    walk(tree.frameTree, true); return out;
  }
  async page(r, op, args = {}) {
    const frames = await this.frames(r);
    const frame = r.frame || frames[0].id;
    if (!frames.some(f => f.id === frame)) throw fault('FRAME_GONE');
    let context;
    try { context = await this.cdp(r, 'Page.createIsolatedWorld', { frameId: frame, worldName: 'indiebiz-browser' }); }
    catch { throw fault('FRAME_UNAVAILABLE'); }
    const result = await this.cdp(r, 'Runtime.evaluate', { contextId: context.executionContextId,
      expression: expression(op, args), returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) {
      const desc = result.exceptionDetails.exception?.description || '';
      const code = desc.match(/Error: ([A-Z_]+)/)?.[1] || 'PAGE_OPERATION_FAILED';
      throw fault(code);
    }
    const data = result.result?.value;
    if (!data) throw fault('PAGE_NOT_READY');
    // Cursor reads describe the captured document, including after SPA navigation.
    data.frame = { id: frame, url: data.url ?? frames.find(f => f.id === frame)?.url };
    if (['snapshot', 'auth_probe'].includes(op)) r.document = data.document_id;
    return data;
  }
  async navigate(r, args, deadline) {
    this.check(r, deadline); r.frame = null; r.document = null; r.executing = true;
    try {
      if (args.mode === 'back') r.wc.navigationHistory.goBack();
      else if (args.mode === 'forward') r.wc.navigationHistory.goForward();
      else {
        let timer;
        try { await Promise.race([r.wc.loadURL(checkedURL(args.url)), new Promise((_, reject) => {
          timer = setTimeout(() => { r.wc.stop(); reject(fault('NAVIGATION_TIMEOUT')); }, Math.max(1, deadline - Date.now()));
        })]); } finally { clearTimeout(timer); }
      }
    } finally { r.executing = false; }
    this.check(r, deadline);
    return { url: safeURL(r.wc.getURL()), title: r.wc.getTitle() };
  }
  async operation(owner, args, deadline, auth) {
    const op = args.op || 'snapshot';
    if (!capabilities.includes(op)) throw fault('UNSUPPORTED_OPERATION');
    if (op === 'tab' && args.mode === 'list') return { tabs: [...this.records.values()]
      .filter(r => !r.closed && (r.owner === owner || (!r.owner && r.shared)))
      .map(r => ({ tab_id: r.id, url: safeURL(r.wc?.getURL()), title: r.wc?.getTitle(), state: r.state })), capabilities };
    if (op === 'close') {
      for (const r of this.records.values()) if (r.owner === owner) { r.owner = null; r.shared = false; r.state = ''; }
      this.active.delete(owner); if (this.authOwner === owner) this.authOwner = null;
      this.notice(); return { released: true };
    }
    const creating = (op === 'tab' && args.mode === 'new') || (op === 'navigate' && !args.tab_id && !this.active.has(owner));
    const r = creating ? await this.create(owner, args.url || 'about:blank', deadline) : this.target(owner, args.tab_id);
    if (op === 'auth' && ['resume', 'cancel'].includes(args.mode)) r.paused = false;
    this.check(r, deadline);
    if (this.authOwner && this.authOwner !== owner) throw fault('AUTH_SESSION_BUSY');
    r.state = ['content', 'snapshot', 'wait'].includes(op) ? 'AI가 읽는 중' : 'AI가 조작 중'; this.notice();
    let data = {};
    r.executing = true;
    try {
      if (creating) data = { url: safeURL(r.wc.getURL()), created: true };
      else if (op === 'navigate') data = await this.navigate(r, args, deadline);
      else if (op === 'tab') {
        if (args.mode === 'close') {
          r.wc.close();
          while (!r.wc.isDestroyed() && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 40));
          if (!r.wc.isDestroyed()) throw fault('TAB_CLOSE_NOT_CONFIRMED');
          r.closed = true;
        }
        else if (args.mode !== 'switch') throw fault('UNSUPPORTED_OPERATION');
      } else if (op === 'auth') data = await auth(r, args, deadline);
      else if (op === 'iframe') {
        const frames = await this.frames(r);
        if (args.mode === 'reset') r.frame = null;
        else if (args.mode === 'switch') {
          const children = frames.filter(f => !f.main);
          const matches = children.filter((f, i) => args.index != null ? i === args.index : args.name ? f.name === args.name : args.url ? f.url.includes(args.url) : false);
          if (matches.length !== 1) throw fault('FRAME_AMBIGUOUS'); r.frame = matches[0].id;
        } else if (args.mode !== 'list') throw fault('UNSUPPORTED_OPERATION');
        r.document = null; data = { frames: frames.filter(f => !f.main) };
      } else if (op === 'press_key') {
        if (!['Enter', 'Tab', 'Escape', 'ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'Space'].includes(args.key)) throw fault('UNSUPPORTED_KEY');
        if (!r.document) throw fault('SNAPSHOT_REQUIRED');
        await this.page(r, 'focus', { ...args, document_id: r.document }); this.check(r, deadline);
        r.injecting = true;
        try { r.wc.sendInputEvent({ type: 'keyDown', keyCode: args.key }); r.wc.sendInputEvent({ type: 'keyUp', keyCode: args.key }); }
        finally { r.injecting = false; }
        data = { verification: 'interaction_only' };
      } else {
        if (args.selector || args.path || args.dialog || (op === 'content' && args.mode && args.mode !== 'text') || (op === 'click' && args.mode && args.mode !== 'single')) throw fault('UNSUPPORTED_OPERATION');
        if (!['snapshot', 'content', 'scroll', 'wait'].includes(op) && !r.document) throw fault('SNAPSHOT_REQUIRED');
        do {
          this.check(r, deadline);
          data = await this.page(r, op, { ...args, document_id: r.document });
          if (op !== 'wait' || data.matched) break;
          await new Promise(resolve => setTimeout(resolve, 100));
        } while (Date.now() < deadline);
        if (op === 'wait' && !data.matched) throw fault('WAIT_TIMEOUT');
      }
      return { ...data, tab_id: r.id, captured_at: data.captured_at || new Date().toISOString() };
    } finally { r.executing = false; if (!r.paused) r.state = r.authWaiting ? '로그인 확인 필요' : 'AI 작업 탭'; this.notice(); }
  }
}
