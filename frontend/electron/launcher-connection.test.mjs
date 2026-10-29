import test from 'node:test';
import assert from 'node:assert/strict';
import { createLauncherConnection } from './launcher-connection.js';

function fixture() {
  let time = 0;
  const sockets = [], timers = new Map(), intervals = new Map(), commands = [], logs = [];
  let seq = 0;
  class Socket {
    readyState = 0;
    sent = [];
    closes = 0;
    constructor() { sockets.push(this); }
    close() {
      this.closes++;
      assert.ok(this.closes < 3, 'recursive close');
      this.onerror?.(); // Undici can emit this synchronously during CONNECTING close.
      this.onclose?.();
      this.readyState = 3;
    }
    send(data) { this.sent.push(JSON.parse(data)); }
    open() { this.readyState = 1; this.onopen?.(); }
    message(data) { this.onmessage?.({ data: JSON.stringify(data) }); }
  }
  const connection = createLauncherConnection({ WebSocketImpl: Socket,
    onCommand: (...args) => commands.push(args), log: (...args) => logs.push(args),
    now: () => time, schedule: fn => { timers.set(++seq, fn); return seq; },
    cancel: id => timers.delete(id), repeat: fn => { intervals.set(++seq, fn); return seq; },
    cancelRepeat: id => intervals.delete(id),
  });
  const retry = () => {
    assert.equal(timers.size, 1);
    const [id, fn] = [...timers][0]; timers.delete(id); fn();
  };
  const tick = ms => { time += ms; for (const fn of [...intervals.values()]) fn(); };
  return { connection, sockets, timers, intervals, commands, logs, retry, tick };
}

test('error while connecting closes once, schedules once and ignores stale callbacks', () => {
  const f = fixture(); f.connection.start(); f.connection.start();
  assert.equal(f.sockets.length, 1);
  const old = f.sockets[0];
  const stale = [old.onerror, old.onclose, old.onopen];
  const message = old.onmessage;
  old.onerror();
  assert.equal(old.closes, 1); assert.equal(f.logs.length, 1);
  assert.equal(f.intervals.size, 0); assert.equal(f.timers.size, 1);
  f.retry(); const current = f.sockets[1]; current.open();
  stale.forEach(fn => fn());
  message({ data: JSON.stringify({ type: 'launcher_command', command: 'stale' }) });
  assert.equal(current.closes, 0); assert.equal(f.timers.size, 0);
  assert.equal(f.commands.length, 0); assert.equal(f.intervals.size, 1);
  current.message({ type: 'launcher_command', command: 'open', params: { id: 1 } });
  assert.deepEqual(f.commands, [['open', { id: 1 }]]);
  f.connection.stop();
});

test('offline retry rate stays bounded over repeated failures and stops on quit', () => {
  const f = fixture(); f.connection.start();
  for (let i = 0; i < 100; i++) { f.sockets.at(-1).onerror(); f.retry(); }
  assert.equal(f.sockets.length, 101); assert.equal(f.logs.length, 100);
  f.sockets.at(-1).onerror();
  f.connection.stop(); f.connection.stop();
  assert.equal(f.timers.size, 0); assert.equal(f.intervals.size, 0);
  assert.ok(f.sockets.every(s => s.closes === 1));
});

test('connecting and half-open sockets expire, pong keeps a healthy connection alive', () => {
  const f = fixture(); f.connection.start();
  f.tick(30000); assert.equal(f.sockets[0].closes, 0);
  f.tick(60000); assert.equal(f.sockets[0].closes, 1);
  f.retry(); const s = f.sockets[1]; s.open();
  for (let i = 0; i < 10; i++) { f.tick(30000); s.message({ type: 'pong' }); }
  assert.equal(s.closes, 0); assert.equal(s.sent.length, 10);
  f.tick(90000); assert.equal(s.closes, 1);
  f.connection.stop();
});

test('send failure and shutdown revoke callbacks before closing', () => {
  const f = fixture(); f.connection.start();
  const s = f.sockets[0]; s.open(); s.send = () => { throw new Error('offline'); };
  f.tick(30000); assert.equal(s.closes, 1); assert.equal(f.timers.size, 1);
  f.retry(); const next = f.sockets[1]; const staleError = next.onerror;
  f.connection.stop(); staleError();
  assert.equal(next.closes, 1); assert.equal(f.timers.size, 0);
});
