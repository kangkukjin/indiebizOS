import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter, once } from 'node:events';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { devServerIdentityPlugin } from './dev-server-identity.mjs';
import { probeServer, runDesktop } from './electron-dev.mjs';

const root = fileURLToPath(new URL('..', import.meta.url));
const quiet = { log() {}, signals: new EventEmitter() };

async function freeOrigin() {
  const socket = http.createServer();
  socket.listen(0, '127.0.0.1');
  await once(socket, 'listening');
  const origin = `http://127.0.0.1:${socket.address().port}`;
  await new Promise(resolve => socket.close(resolve));
  return origin;
}

function renderer(origin) {
  return createServer({
    root, configFile: false, logLevel: 'silent', plugins: [devServerIdentityPlugin()],
    server: { host: '127.0.0.1', port: Number(new URL(origin).port), strictPort: true,
      watch: null, ws: false },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
}

const electronExit = code => spawn(process.execPath, ['-e', `process.exit(${code})`]);

test('cold start waits for its renderer and closes it after Electron exits', async () => {
  const origin = await freeOrigin();
  let running;
  const result = await runDesktop({ ...quiet, root, origin,
    createServer: () => renderer(origin), launch() {
      running = probeServer(root, origin);
      return electronExit(0);
    },
  });
  assert.equal(await running, true);
  assert.equal(result, 0);
  assert.equal(await probeServer(root, origin), false);
});

test('existing renderer survives window exit and repeated launches', async () => {
  const origin = await freeOrigin();
  const server = await renderer(origin);
  await server.listen();
  try {
    for (const code of [0, 7, 0]) {
      assert.equal(await runDesktop({ ...quiet, root, origin,
        createServer: () => assert.fail('must not start a second renderer'),
        launch: () => electronExit(code),
      }), code);
      assert.equal(await probeServer(root, origin), true);
    }
  } finally { await server.close(); }
});

test('foreign port occupant is rejected without launching Electron or stopping it', async () => {
  const server = http.createServer((_req, res) => res.end('another app'));
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const origin = `http://127.0.0.1:${server.address().port}`;
  try {
    await assert.rejects(runDesktop({ ...quiet, root, origin,
      createServer: () => assert.fail('must not create server'),
      launch: () => assert.fail('must not open foreign content'),
    }), /unrecognized server/);
    assert.equal(server.listening, true);
  } finally { await new Promise(resolve => server.close(resolve)); }
});

test('same app in another checkout is rejected', async () => {
  const origin = await freeOrigin();
  const server = await renderer(origin);
  await server.listen();
  try {
    await assert.rejects(probeServer(fileURLToPath(new URL('../..', import.meta.url)), origin),
      /unrecognized server/);
  } finally { await server.close(); }
});

test('startup failure cleans owned server without flashing an Electron window', async () => {
  const origin = await freeOrigin();
  let closed = false;
  await assert.rejects(runDesktop({ ...quiet, root, origin,
    createServer: async () => ({
      listen: async () => { throw new Error('catalog failed'); },
      close: async () => { closed = true; },
    }),
    launch: () => assert.fail('must not launch before server readiness'),
  }), /catalog failed/);
  assert.equal(closed, true);
});

test('Electron spawn failure releases the owned renderer', async () => {
  const origin = await freeOrigin();
  await assert.rejects(runDesktop({ ...quiet, root, origin,
    createServer: () => renderer(origin),
    launch: () => spawn('/nonexistent/indiebiz-electron'),
  }), /ENOENT/);
  assert.equal(await probeServer(root, origin), false);
});

test('termination stops the child and releases the owned renderer', async () => {
  const origin = await freeOrigin();
  const signals = new EventEmitter();
  let child;
  const result = await runDesktop({ ...quiet, root, origin, signals,
    createServer: () => renderer(origin), launch() {
      child = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)']);
      child.once('spawn', () => signals.emit('SIGTERM'));
      return child;
    },
  });
  assert.equal(result, 1);
  assert.equal(child.signalCode, 'SIGTERM');
  assert.equal(await probeServer(root, origin), false);
  assert.equal(signals.listenerCount('SIGTERM'), 0);
});

test('port race reuses the winning renderer without closing it', async () => {
  const origin = await freeOrigin();
  const winner = await renderer(origin);
  try {
    assert.equal(await runDesktop({ ...quiet, root, origin,
      createServer: async () => {
        await winner.listen();
        return renderer(origin);
      },
      launch: () => electronExit(0),
    }), 0);
    assert.equal(await probeServer(root, origin), true);
  } finally { await winner.close(); }
});
