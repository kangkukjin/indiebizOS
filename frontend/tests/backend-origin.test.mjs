import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveBackendOrigin, getBackendOrigin } from '../src/lib/backend-origin.ts';

test('native/file/development clients keep the local backend', () => {
  assert.equal(resolveBackendOrigin({ protocol: 'file:', origin: 'null' }), 'http://127.0.0.1:8765');
  assert.equal(resolveBackendOrigin({ protocol: 'http:', origin: 'http://localhost:5173' }, true), 'http://127.0.0.1:8765');
  assert.equal(resolveBackendOrigin({ protocol: 'http:', origin: 'http://localhost:5173' }, false, true), 'http://127.0.0.1:8765');
});

test('web clients use the serving origin, including HTTPS and LAN ports', () => {
  for (const origin of ['https://example.invalid', 'http://192.168.1.20:8765']) {
    assert.equal(resolveBackendOrigin({ protocol: new URL(origin).protocol, origin }), origin);
  }
});

test('runtime port lookup preserves the Electron port and handles bridge startup failure', async () => {
  const previous = globalThis.window;
  try {
    globalThis.window = { electron: { getApiPort: async () => 9876 } };
    assert.equal(await getBackendOrigin(), 'http://127.0.0.1:9876');
    globalThis.window.electron.getApiPort = async () => { throw new Error('bridge unavailable'); };
    assert.equal(await getBackendOrigin(), 'http://127.0.0.1:8765');
  } finally {
    if (previous === undefined) delete globalThis.window;
    else globalThis.window = previous;
  }
});


test('the remote document uses secure WebSockets while an ordinary preview stays local', async () => {
  const oldWindow = globalThis.window, oldDocument = globalThis.document;
  try {
    globalThis.window = { location: new URL('https://remote.invalid/launcher/app') };
    globalThis.document = { documentElement: { dataset: { indiebizSurface: 'remote' } } };
    const remote = await import('../src/lib/backend-origin.ts?remote');
    assert.equal(remote.BACKEND_ORIGIN, 'https://remote.invalid');
    assert.equal(remote.WEBSOCKET_ORIGIN, 'wss://remote.invalid');
    assert.equal(remote.IS_WEB_SURFACE, true);
    globalThis.document.documentElement.dataset = {};
    const preview = await import('../src/lib/backend-origin.ts?preview');
    assert.equal(preview.BACKEND_ORIGIN, 'http://127.0.0.1:8765');
    assert.equal(preview.IS_WEB_SURFACE, false);
  } finally {
    if (oldWindow === undefined) delete globalThis.window; else globalThis.window = oldWindow;
    if (oldDocument === undefined) delete globalThis.document; else globalThis.document = oldDocument;
  }
});
