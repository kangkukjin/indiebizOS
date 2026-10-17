import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import vm from 'node:vm';
import { build } from 'esbuild';
import { createServer } from 'vite';
import { ownerDisplayPlugin, root } from './owner-display.mjs';

// Exercise Vite's real dependency graph without modifying the user's source files.
test('source and catalog changes invalidate the cached virtual display baseline', async () => {
  const server = await createServer({
    root, configFile: false, logLevel: 'silent', plugins: [ownerDisplayPlugin()],
    server: { middlewareMode: true, watch: null, ws: false },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  try {
    for (const file of ['src/components/launcher-components/LimbSwitch.tsx', 'i18n/catalog.json']) {
      await server.transformRequest('virtual:owner-display');
      const baseline = server.moduleGraph.getModuleById('\0owner-display');
      assert.ok(baseline.transformResult);
      server.watcher.emit('change', path.join(root, file));
      assert.equal(baseline.transformResult, null, file);
      await server.transformRequest('virtual:owner-display');
      assert.ok(baseline.transformResult, 'next request rebuilds the baseline');
    }
  } finally { await server.close(); }
});

async function loadStartup(dev) {
  const result = await build({
    entryPoints: [path.join(root, 'src/lib/owner-display.ts')], bundle: true, write: false,
    format: 'iife', globalName: 'ownerDisplay', define: { 'import.meta.env.DEV': String(dev) },
    plugins: [{ name: 'display-boundaries', setup(build) {
      build.onResolve({ filter: /^(react-dom|virtual:owner-display)$|ChatDisplay$|LauncherDisplay$|i18n\/ui$|backend-origin$/ },
        args => ({ path: args.path, namespace: 'test-boundary' }));
      build.onLoad({ filter: /.*/, namespace: 'test-boundary' }, () => ({ contents: `
        export default {host:'installed-host', version:'installed-version'};
        export const flushSync = fn => fn();
        export const chatDisplay = {}, launcherDisplay = {};
        export const installUiMessages = () => {};
        export const getBackendOrigin = async () => 'http://local.test';
      ` }));
    } }],
  });
  const calls = [], timers = [], buttons = [];
  const context = vm.createContext({
    window: {}, document: { addEventListener() {},
      createElement() { const button = { style: {} }; buttons.push(button); return button; },
      body: { appendChild() {} } },
    localStorage: { getItem() { calls.push('cache'); return null; } },
    setTimeout(fn) { timers.push(fn); }, setInterval(fn) { timers.push(fn); },
    fetch: async () => { calls.push('fetch'); return { ok: true, json: async () => ({host:'other-host',version:'offered-version'}) }; },
  });
  vm.runInContext(result.outputFiles[0].text, context);
  await context.ownerDisplay.startOwnerDisplay();
  return {calls, timers, buttons};
}

test('source mode leaves automatic updates to Vite and never loads a published display', async () => {
  const {calls, timers, buttons} = await loadStartup(true);
  assert.deepEqual(calls, []);
  assert.equal(timers.length, 0);
  assert.equal(buttons.length, 0);
});

test('installed app retains published update checks and rejects incompatible display on click', async () => {
  const {calls, timers, buttons} = await loadStartup(false);
  assert.deepEqual(calls, ['cache']);
  assert.equal(timers.length, 2);
  await timers[0]();
  assert.equal(buttons[0].hidden, false);
  await buttons[0].onclick();
  assert.match(buttons[0].textContent, /실행부가 바뀌었습니다/);
  assert.deepEqual(calls, ['cache', 'fetch']);
});
