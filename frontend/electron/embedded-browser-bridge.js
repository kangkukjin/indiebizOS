import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID, randomBytes, timingSafeEqual } from 'node:crypto';
import { EmbeddedTabs, capabilities, fault } from './embedded-browser-tabs.js';
import { EmbeddedAuth } from './embedded-browser-auth.js';

const MAX_BYTES = 1024 * 1024;
export function startEmbeddedBridge({ basePath, runtimePath, show, changed, vault }) {
  const instance = randomUUID(); const token = randomBytes(32).toString('hex');
  const tabs = new EmbeddedTabs({ show, changed });
  const auth = new EmbeddedAuth(tabs, vault, instance);
  // Windows retains main-only manual autofill even while agent transport is unavailable.
  if (process.platform === 'win32') return { tabs, auth, instance, ready: Promise.resolve(), close() {} };
  const runtime = runtimePath || path.join(basePath, 'data', 'runtime');
  fs.mkdirSync(runtime, { recursive: true, mode: 0o700 });
  const statePath = path.join(runtime, 'embedded-browser.json');
  const dir = fs.mkdtempSync('/tmp/indiebiz-eb-'); fs.chmodSync(dir, 0o700);
  const socketPath = path.join(dir, 'bridge.sock');
  const cache = new Map(); const sockets = new Set();
  const server = net.createServer(socket => {
    sockets.add(socket); socket.on('close', () => sockets.delete(socket)); socket.on('error', () => {});
    socket.setTimeout(60000, () => socket.destroy());
    let buffer = ''; let active = null; let replied = false;
    socket.on('close', () => {
      if (active && !replied) for (const r of tabs.records.values()) {
        if (r.owner === active && r.executing) { tabs.pause(r); r.wc?.stop(); }
      }
    });
    socket.on('data', chunk => {
      buffer += chunk.toString('utf8');
      if (Buffer.byteLength(buffer) > MAX_BYTES) return socket.destroy();
      let end;
      while ((end = buffer.indexOf('\n')) >= 0) {
        const raw = buffer.slice(0, end); buffer = buffer.slice(end + 1);
        let request;
        try { request = JSON.parse(raw); } catch { socket.destroy(); return; }
        const proof = Buffer.from(String(request.token || ''));
        if (proof.length !== token.length || !timingSafeEqual(proof, Buffer.from(token)) || request.instance_id !== instance) { socket.destroy(); return; }
        if (!/^[a-f0-9]{64}$/.test(request.owner || '') || typeof request.id !== 'string' || request.id.length > 100) { socket.destroy(); return; }
        const key = `${request.owner}:${request.id}`;
        const signature = JSON.stringify(request.params);
        const prior = cache.get(key);
        if (prior && prior.signature !== signature) { socket.destroy(); return; }
        if (!prior) {
          const run = async () => {
            try {
              if (socket.destroyed) throw fault('REQUEST_CANCELLED');
              active = request.owner;
              const deadline = Math.min(Number(request.deadline) || 0, Date.now() + 45000);
              if (deadline <= Date.now()) throw fault('DEADLINE_EXCEEDED');
              const result = request.params?.op === 'status' ? { capabilities } :
                await tabs.operation(request.owner, request.params || {}, deadline, (r, a, d) => auth.run(r, a, d));
              return { success: true, driver: 'embedded', session_owner: request.owner, ...auth.redact(result) };
            } catch (e) {
              // Never serialize Chromium exception text: it can contain submitted secrets or URLs.
              return { success: false, driver: 'embedded', error_code: /^[A-Z_]+$/.test(e.code || '') ? e.code : 'BROWSER_OPERATION_FAILED',
                outcome_unknown: !['snapshot', 'content', 'status', 'tab'].includes(request.params?.op),
                error: '내장 브라우저 작업을 완료하지 못했습니다. 상태를 확인한 후 이어가세요.' };
            }
          };
          const promise = tabs.queue.then(run, run); tabs.queue = promise.then(() => {});
          cache.set(key, { signature, promise });
          promise.finally(() => { if (cache.size > 256) cache.delete(cache.keys().next().value); });
        }
        cache.get(key).promise.then(result => {
          replied = true;
          if (!socket.destroyed) socket.end(JSON.stringify({ id: request.id, result }) + '\n');
        });
      }
    });
  });
  const ready = new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(socketPath, () => {
      fs.chmodSync(socketPath, 0o600);
      const temporary = `${statePath}.${instance}`;
      fs.writeFileSync(temporary, JSON.stringify({ version: 1, instance_id: instance, token, socket: socketPath }), { mode: 0o600 });
      fs.renameSync(temporary, statePath); resolve();
    });
  });
  return { tabs, auth, ready, instance,
    close() {
      for (const socket of sockets) socket.destroy(); server.close();
      try { if (JSON.parse(fs.readFileSync(statePath)).instance_id === instance) fs.unlinkSync(statePath); } catch { /* already gone */ }
      try { fs.rmSync(dir, { recursive: true, force: true }); } catch { /* server cleanup */ }
    },
  };
}
