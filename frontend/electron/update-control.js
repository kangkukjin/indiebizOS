/** Local owner update handshake. Close windows normally; never override beforeunload. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';

export function checkUpdateAdmission(root, env = process.env) {
  const file = path.join(root, 'data/runtime/update-maintenance.json');
  if (!fs.existsSync(file)) return;
  const state = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (state.phase === 'starting' && state.token && env.INDIEBIZ_UPDATE_TOKEN === state.token) return;
  throw new Error('Source update in progress; resume its existing plan before starting the app');
}

export function installUpdateControl({ app, BrowserWindow, root, mode }) {
  checkUpdateAdmission(root);
  const directory = path.join(root, 'data/runtime');
  const file = path.join(directory, 'electron-update.json');
  const request = path.join(directory, 'electron-update-request.json');
  fs.mkdirSync(directory, { recursive: true });
  let head = null;
  try { head = execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf8', windowsHide: true }).trim(); }
  catch { /* A source archive can run, but cannot attest a Git update. */ }
  const state = { schema: 1, root: fs.realpathSync(root), pid: process.pid,
    started_at: Date.now() / 1000, nonce: crypto.randomUUID(), mode, ready: false,
    git_head: head };
  const publish = () => {
    const tmp = `${file}.${process.pid}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(state), { mode: 0o600 });
    fs.renameSync(tmp, file);
  };
  publish();
  let handled;
  const poll = () => {
    try {
      const message = JSON.parse(fs.readFileSync(request, 'utf8'));
      if (message.nonce !== state.nonce || message.op !== 'close' || !message.id || message.id === handled) return;
      handled = message.id;
      // Normal window close honors unsaved document handlers. A cancelled close
      // leaves the updater waiting, with no source/dependency changes permitted.
      const windows = BrowserWindow.getAllWindows();
      if (!windows.length) app.quit();
      else for (const window of windows) window.close();
    } catch (error) {
      if (error.code !== 'ENOENT') console.error('[Update] request not accepted:', error.message);
    }
  };
  const timer = setInterval(poll, 500);
  timer.unref();
  app.once('quit', () => {
    clearInterval(timer);
    try {
      if (JSON.parse(fs.readFileSync(file, 'utf8')).nonce === state.nonce) fs.unlinkSync(file);
    } catch { /* Stale receipts are never proof of a live app. */ }
  });
  return { ready() { state.ready = true; publish(); }, poll };
}
