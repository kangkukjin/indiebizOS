import test from 'node:test';
import assert from 'node:assert/strict';
import net from 'node:net';
import { EventEmitter } from 'node:events';
import { desktopProfile, probeVNC, vncURL, createDesktopConnector, installRemoteDesktop } from './remote-desktop.js';

test('profiles cannot inject arguments, credentials or executable URLs', () => {
  for (const host of ['--help', 'mac.local/path', 'vnc://mac.local', 'user:pass@host', 'mac\n.local', 'a'.repeat(254)]) {
    assert.throws(() => desktopProfile({ direct_host: host }));
  }
  for (const port of [0, -1, 65536, true, '5900']) assert.throws(() => desktopProfile({ port }));
  assert.throws(() => desktopProfile({ tunnel_host: '127.0.0.1' }));
  assert.equal(vncURL('::1', 5900), 'vnc://[::1]:5900');
});

test('VNC probe validates a fragmented protocol greeting, not just an open TCP port', async () => {
  let greeting = true;
  const server = net.createServer(socket => {
    socket.on('error', () => {});
    socket.write(greeting ? 'RFB 003.' : 'HTTP/1.1');
    setTimeout(() => socket.end(greeting ? '008\n' : ' 200 OK\n'), 5);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    assert.equal(await probeVNC('127.0.0.1', server.address().port), true);
    greeting = false;
    assert.equal(await probeVNC('127.0.0.1', server.address().port), false);
  } finally { await new Promise(resolve => server.close(resolve)); }
});

test('direct connection does not spawn a tunnel; OS receives only a VNC URL', async () => {
  const opened = [];
  const c = createDesktopConnector({ platform: 'darwin', openExternal: async url => opened.push(url),
    probe: async () => true, spawnProcess: () => { throw new Error('unexpected spawn'); } });
  assert.deepEqual(await c.open({ direct_host: 'mac.local', tunnel_host: 'remote.example.com' }), { route: 'direct' });
  assert.deepEqual(opened, ['vnc://mac.local:5900']); c.close();
  await assert.rejects(c.open({ direct_host: 'mac.local' }));
});

test('fallback uses one loopback Cloudflare process and cleans it up on shutdown', async () => {
  const spawned = [], opened = [];
  const child = new EventEmitter(); child.stderr = new EventEmitter(); let killed = 0;
  child.kill = () => { killed++; child.emit('exit', 0); };
  const c = createDesktopConnector({ platform: 'darwin', openExternal: async url => opened.push(url),
    probe: async host => host === '127.0.0.1', spawnProcess: (...args) => { spawned.push(args); return child; } });
  const profile = { direct_host: 'mac.local', tunnel_host: 'remote.example.com' };
  assert.equal((await c.open(profile)).route, 'tunnel');
  await c.open(profile, 'tunnel');
  assert.equal(spawned.length, 1);
  assert.deepEqual(spawned[0][1].slice(0, 4), ['access', 'tcp', '--hostname', 'remote.example.com']);
  assert.match(spawned[0][1][5], /^127\.0\.0\.1:\d+$/);
  assert.equal(opened[0], opened[1]);
  c.close(); assert.equal(killed, 1);
});

test('tunnel startup tolerates a delayed upstream VNC greeting', async () => {
  const opened = [];
  const server = net.createServer(socket => {
    socket.on('error', () => {});
    const timer = setTimeout(() => socket.end('RFB 003.889\n'), 1800);
    socket.on('close', () => clearTimeout(timer));
  });
  const c = createDesktopConnector({ platform: 'darwin', openExternal: async url => opened.push(url),
    spawnProcess: (_command, args) => {
      const port = Number(args.at(-1).split(':').at(-1));
      server.listen(port, '127.0.0.1');
      const child = new EventEmitter(); child.stderr = new EventEmitter();
      child.kill = () => { server.close(); child.emit('exit', 0); };
      return child;
    } });
  try {
    assert.equal((await c.open({ tunnel_host: 'remote.example.com' }, 'tunnel')).route, 'tunnel');
    assert.match(opened[0], /^vnc:\/\/127\.0\.0\.1:\d+$/);
  } finally { c.close(); }
});

test('failed transport does not open the OS client or leave a child running', async () => {
  let killed = 0, opened = 0;
  const c = createDesktopConnector({ platform: 'darwin', openExternal: async () => opened++, probe: async () => false,
    spawnProcess: () => {
      const child = new EventEmitter(); child.stderr = new EventEmitter(); child.kill = () => killed++;
      setImmediate(() => child.emit('error', Object.assign(new Error('missing'), { code: 'ENOENT' })));
      return child;
    } });
  await assert.rejects(c.open({ tunnel_host: 'remote.example.com' }), /cloudflared/);
  assert.equal(killed, 1); assert.equal(opened, 0); c.close();
});

test('remote web frames cannot call the native connector', async () => {
  let handler;
  installRemoteDesktop({ app: { isPackaged: false, on() {} }, shell: {},
    ipcMain: { handle(_name, fn) { handler = fn; } } });
  const frame = { url: 'https://attacker.example/' };
  await assert.rejects(handler({ senderFrame: frame, sender: { mainFrame: frame } }, 'guestpc-abc'), /Forbidden/);
});
