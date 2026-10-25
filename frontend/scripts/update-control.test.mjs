import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { EventEmitter } from 'node:events';
import { execFileSync } from 'node:child_process';
import { checkUpdateAdmission, installUpdateControl } from '../electron/update-control.js';

function fixture(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'indiebiz-update-')));
  execFileSync('git', ['init', root], { stdio: 'ignore' });
  execFileSync('git', ['-C', root, '-c', 'user.name=test', '-c', 'user.email=test@example.invalid',
    'commit', '--allow-empty', '-m', 'fixture'], { stdio: 'ignore' });
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

test('maintenance admission needs the matching start token and phase', t => {
  const root = fixture(t);
  checkUpdateAdmission(root, {});
  const file = path.join(root, 'data/runtime/update-maintenance.json');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify({ phase: 'stopped', token: 'x' }));
  assert.throws(() => checkUpdateAdmission(root, { INDIEBIZ_UPDATE_TOKEN: 'x' }));
  fs.writeFileSync(file, JSON.stringify({ phase: 'starting', token: 'x' }));
  assert.throws(() => checkUpdateAdmission(root, { INDIEBIZ_UPDATE_TOKEN: 'other' }));
  checkUpdateAdmission(root, { INDIEBIZ_UPDATE_TOKEN: 'x' });
});

test('wrong-instance close is ignored and unsaved-window cancellation is honored', t => {
  const root = fixture(t);
  const app = new EventEmitter();
  let quit = 0, closed = 0;
  app.quit = () => { quit++; };
  // A window that declines close remains alive. No destroy / force-close API exists here.
  const control = installUpdateControl({ app, root, mode: 'dev',
    BrowserWindow: { getAllWindows: () => [{ close() { closed++; } }] } });
  t.after(() => app.emit('quit'));
  const file = path.join(root, 'data/runtime/electron-update.json');
  const request = path.join(root, 'data/runtime/electron-update-request.json');
  const receipt = JSON.parse(fs.readFileSync(file));
  assert.equal(receipt.ready, false);
  control.ready();
  assert.equal(JSON.parse(fs.readFileSync(file)).ready, true);
  fs.writeFileSync(request, JSON.stringify({ op: 'close', nonce: 'stale', id: 'one' }));
  control.poll();
  assert.equal(closed, 0);
  fs.writeFileSync(request, JSON.stringify({ op: 'close', nonce: receipt.nonce, id: 'two' }));
  control.poll(); control.poll();
  assert.equal(closed, 1);
  assert.equal(quit, 0);
  assert.equal(JSON.parse(fs.readFileSync(file)).nonce, receipt.nonce);
});
