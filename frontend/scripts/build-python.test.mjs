import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { pythonCommand } from './build-python.mjs';

const absent = { platform: 'win32', env: {}, exists: () => false };
test('explicit interpreter and platform venv take priority, including spaces', () => {
  assert.deepEqual(pythonCommand({ ...absent, env: { INDIEBIZ_PYTHON: 'C:\\My Python\\python.exe' } }), ['C:\\My Python\\python.exe']);
  for (const [platform, suffix] of [['win32', '.venv/Scripts/python.exe'], ['darwin', '.venv/bin/python3']]) {
    const expected = path.join('/project', suffix);
    assert.deepEqual(pythonCommand({ ...absent, platform, projectRoot: '/project', exists: file => file === expected }), [expected]);
  }
});

test('Windows without python3 uses Python or the py launcher and rejects broken aliases', () => {
  assert.deepEqual(pythonCommand({ ...absent, probe: () => ({ status: 0 }) }), ['python']);
  const calls = [];
  assert.deepEqual(pythonCommand({ ...absent, probe: (command, args) => {
    calls.push([command, ...args]);
    return command === 'py' ? { status: 0 } : { status: 1 };
  } }), ['py', '-3']);
  assert.equal(calls[1][1], '-3');
  assert.throws(() => pythonCommand({ ...absent, probe: () => ({ error: new Error('ENOENT') }) }), /Python 3 is required/);
});

test('npm wrapper passes arguments, UTF-8 output and failure status through', () => {
  const script = new URL('./build-python.mjs', import.meta.url);
  const run = code => spawnSync(process.execPath, [fileURLToPath(script), '-c', code], { encoding: 'utf8' });
  const success = run('import sys; assert sys.flags.utf8_mode; print("한글 경로")');
  assert.equal(success.status, 0, success.stderr);
  assert.equal(success.stdout.trim(), '한글 경로');
  assert.equal(run('import sys; sys.exit(7)').status, 7);
});
