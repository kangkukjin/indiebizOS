import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';

const require = createRequire(import.meta.url);
test('native window entry loads shared navigation in the actual Electron ESM runtime', () => {
  const root = mkdtempSync(join(tmpdir(), 'indiebiz-window-import-'));
  try {
    const entry = join(root, 'entry.mjs');
    writeFileSync(entry, `import {app} from 'electron';
app.setPath('userData', ${JSON.stringify(join(root, 'profile'))});
app.whenReady().then(async () => {
try {
  const windows = await import(${JSON.stringify(new URL('./windows.js', import.meta.url).href)});
  if (typeof windows.registerToolWindowIPC !== 'function') throw Error('window entry missing');
  windows.registerToolWindowIPC();
  console.log('WINDOW_ENTRY_READY');
  app.exit(0);
} catch (error) { console.error(error); app.exit(1); }
});
`);
    const env = { ...process.env };
    delete env.ELECTRON_RUN_AS_NODE;
    const result = spawnSync(require('electron'), [entry], { env, encoding: 'utf8', timeout: 30000 });
    assert.equal(result.status, 0, String(result.error || '') + result.stdout + result.stderr);
    assert.match(result.stdout, /WINDOW_ENTRY_READY/);
  } finally { rmSync(root, { recursive: true, force: true }); }
});
