import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { EmbeddedTabs } from './embedded-browser-tabs.js';

function fixture() {
  const events = [];
  const session = new EventEmitter();
  let attached = false, destroyed = false, pending;
  session.isAttached = () => attached;
  session.attach = () => { attached = true; events.push('attach'); };
  session.detach = () => {
    attached = false; events.push('detach');
    pending?.(new Error('target closed')); pending = null;
    session.emit('detach');
  };
  session.sendCommand = async method => method === 'pending'
    ? new Promise((_resolve, reject) => { pending = reject; }) : { ok: true };
  const wc = new EventEmitter();
  Object.assign(wc, { id: 1, debugger: session, setWindowOpenHandler() {},
    isDestroyed: () => destroyed,
    close() { events.push('close'); destroyed = true; wc.emit('destroyed'); },
  });
  const tabs = new EmbeddedTabs({ show() {}, changed() {} });
  tabs.attach(wc); tabs.bind('a', wc);
  const r = tabs.records.get('a'); r.owner = 'owner'; tabs.active.set('owner', 'a');
  return { tabs, r, wc, session, events };
}

test('owned tab close detaches first and releases closed records and listeners', async () => {
  const f = fixture(); await f.tabs.cdp(f.r, 'ready');
  await f.tabs.operation('owner', { op: 'tab', mode: 'close' }, Date.now() + 1000);
  assert.deepEqual(f.events, ['attach', 'detach', 'close']);
  assert.equal(f.tabs.records.size, 0); assert.equal(f.tabs.guests.size, 0);
  assert.equal(f.tabs.active.size, 0); assert.equal(f.r.debuggerSession, null);
  assert.equal(f.session.listenerCount('detach'), 0);
  await assert.rejects(f.tabs.cdp(f.r, 'late'), { code: 'TAB_CLOSED' });
});

test('user removal rejects pending commands and invalidates frame and document', async () => {
  const f = fixture(); f.r.document = 'doc'; f.r.frame = 'frame';
  const pending = f.tabs.cdp(f.r, 'pending');
  f.wc.close();
  await assert.rejects(pending, /target closed/);
  assert.equal(f.r.document, null); assert.equal(f.r.frame, null);
  assert.equal(f.tabs.records.size, 0); assert.equal(f.session.listenerCount('detach'), 0);
});

test('releasing AI control detaches but preserves tab and can reattach when shared', async () => {
  const f = fixture(); await f.tabs.cdp(f.r, 'ready');
  await f.tabs.operation('owner', { op: 'close' }, Date.now() + 1000);
  assert.equal(f.wc.isDestroyed(), false); assert.equal(f.tabs.records.size, 1);
  assert.equal(f.r.owner, null); assert.equal(f.session.isAttached(), false);
  f.tabs.ui('share', 'a'); assert.equal(f.tabs.target('next', 'a'), f.r);
  await f.tabs.cdp(f.r, 'again');
  assert.equal(f.session.isAttached(), true); assert.equal(f.session.listenerCount('detach'), 1);
  f.wc.close();
});


test('native replacement navigation keeps ERR_ABORTED even with empty Electron code', async () => {
  const tabs = new EmbeddedTabs({changed() {}, show() {}});
  const r = {wc: {isDestroyed: () => false, loadURL: async () => {throw Object.assign(new Error('aborted'), {errno: -3, code: ''});}}};
  await assert.rejects(tabs.navigate(r, {url: 'https://www.google.com/search?q=test'}, Date.now()+1000),
    {code: 'ERR_ABORTED'});
});
