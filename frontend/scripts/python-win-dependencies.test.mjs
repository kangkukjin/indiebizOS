import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { syncDependencies } from './python-win-dependencies.mjs';

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'runtime-deps-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const runtime = join(root, 'build', 'python-win');
  mkdirSync(runtime, { recursive: true }); mkdirSync(join(root, 'backend'));
  writeFileSync(join(runtime, 'python.exe'), 'fixture');
  for (const name of ['core', 'tools']) writeFileSync(join(root, 'backend', `requirements-${name}.txt`), 'first\n');
  return { root, runtime };
}

test('sync targets bundled interpreter and rechecks changed requirements without replacing runtime', t => {
  const { root, runtime } = fixture(t), calls = [];
  const run = (exe, args) => { calls.push([exe, args]); return args.includes('list') ? '[{"name":"first","version":"1"}]' : ''; };
  const first = syncDependencies(root, runtime, { run, platform: 'win32' });
  writeFileSync(join(root, 'backend/requirements-core.txt'), 'second\n');
  const second = syncDependencies(root, runtime, { run, platform: 'win32' });
  assert.notEqual(first.requirements[0].sha256, second.requirements[0].sha256);
  assert.equal(calls.length, 6);
  assert.ok(calls.every(([exe]) => exe === join(runtime, 'python.exe')));
  assert.equal(readFileSync(join(runtime, 'python.exe'), 'utf8'), 'fixture');
  assert.equal(second.status, 'verified');
});

test('failed dependency verification cannot leave a successful receipt', t => {
  const { root, runtime } = fixture(t);
  writeFileSync(join(runtime, 'indiebiz-dependencies.json'), '{"status":"verified"}');
  assert.throws(() => syncDependencies(root, runtime, { platform: 'win32', run: (_, args) => {
    if (args.includes('check')) throw new Error('incompatible distribution'); return '';
  }}), /incompatible/);
  assert.equal(JSON.parse(readFileSync(join(runtime, 'indiebiz-dependencies.json'))).status, 'checking');
  assert.throws(() => syncDependencies(root, runtime, { platform: 'darwin' }), /on Windows/);
});
