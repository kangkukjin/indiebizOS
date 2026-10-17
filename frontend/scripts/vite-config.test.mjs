import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createServer, loadConfigFromFile } from 'vite';

// Use the real application's watcher settings with an isolated file and server.
test('desktop watcher observes a saved source and refreshes Vite module cache', async () => {
  const loaded = await loadConfigFromFile({ command: 'serve', mode: 'development' });
  const watch = loaded.config.server.watch;
  assert.equal(watch.usePolling, process.platform === 'darwin');
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'indiebiz-vite-watch-')));
  const file = path.join(root, 'value.js');
  fs.writeFileSync(file, 'export const value = 1;');
  const server = await createServer({ root, configFile: false, logLevel: 'silent',
    server: { middlewareMode: true, ws: false, watch },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  let timeout;
  try {
    assert.match((await server.transformRequest('/value.js')).code, /value = 1/);
    // Let the watcher establish its baseline before the update.
    await new Promise(resolve => setTimeout(resolve, 1200));
    const changed = new Promise((resolve, reject) => {
      server.watcher.on('change', changed => { if (changed === file) resolve(); });
      timeout = setTimeout(() => reject(new Error('source change was not observed')), 5000);
    });
    fs.writeFileSync(file, 'export const value = 2;');
    await changed;
    // Vite's async watcher handler invalidates after the raw filesystem event.
    for (let i = 0; i < 100 && server.moduleGraph.getModuleById(file)?.transformResult; i++) {
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    assert.match((await server.transformRequest('/value.js')).code, /value = 2/);
  } finally {
    clearTimeout(timeout);
    await server.close();
    fs.rmSync(root, { recursive: true, force: true });
  }
});
