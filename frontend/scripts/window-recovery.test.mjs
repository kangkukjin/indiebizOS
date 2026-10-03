import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import test from 'node:test';
import { installDevServerRecovery } from '../electron/window-recovery.js';

function fixture() {
  const wc = new EventEmitter();
  const jobs = new Map(), loads = [];
  let id = 0;
  wc.isDestroyed = () => false;
  wc.loadURL = async url => { loads.push(url); wc.emit('did-start-navigation', {}, url, false, true); };
  const dispose = installDevServerRecovery(wc, {
    schedule: (fn, ms) => { jobs.set(++id, { fn, ms }); return id; },
    cancel: key => jobs.delete(key),
  });
  const fail = (url, code = -102, main = true) => wc.emit('did-fail-load', {}, code, 'failed', url, main);
  const tick = () => { const [key, job] = jobs.entries().next().value; jobs.delete(key); job.fn(); };
  return { wc, jobs, loads, dispose, fail, tick };
}

test('server outage retries with backoff, keeps route, and stops after recovery', () => {
  const f = fixture(), url = 'http://localhost:5173/?view=chat#/system-ai';
  f.wc.emit('did-start-navigation', {}, url, false, true);
  f.fail(url); f.fail(url);
  assert.equal(f.jobs.size, 1);
  assert.equal([...f.jobs.values()][0].ms, 500);
  // Error documents also finish loading; this must not cancel recovery.
  f.wc.emit('did-finish-load');
  f.tick();
  assert.deepEqual(f.loads, [url]);
  f.fail(url);
  assert.equal([...f.jobs.values()][0].ms, 1000);
  f.tick();
  f.wc.emit('did-navigate', {}, url);
  assert.equal(f.jobs.size, 0);
  f.fail(url);
  assert.equal([...f.jobs.values()][0].ms, 500);
  f.dispose();
});

test('external pages, child frames, cancellations and permanent errors never retry', () => {
  const f = fixture();
  f.fail('https://example.org');
  f.fail('http://localhost:5173/', -102, false);
  f.fail('http://localhost:5173/', -3);
  f.fail('http://localhost:5173/', -200);
  assert.equal(f.jobs.size, 0);
});

test('new navigation and closed windows cancel pending recovery and stale failures', () => {
  const f = fixture(), url = 'http://localhost:5173/';
  f.fail(url);
  f.wc.emit('did-start-navigation', {}, 'https://example.org', false, true);
  f.fail(url);
  assert.equal(f.jobs.size, 0);
  f.wc.emit('did-start-navigation', {}, url, false, true);
  f.fail(url);
  f.wc.emit('destroyed');
  assert.equal(f.jobs.size, 0);
  assert.equal(f.wc.listenerCount('did-fail-load'), 0);
});
