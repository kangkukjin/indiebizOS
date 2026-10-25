/** Start the renderer before Electron; only close a server owned by this invocation. */
import { spawn } from 'node:child_process';
import { realpathSync } from 'node:fs';
import http from 'node:http';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { identityPath } from './dev-server-identity.mjs';
import { checkUpdateAdmission } from '../electron/update-control.js';

const frontendRoot = realpathSync(fileURLToPath(new URL('..', import.meta.url)));
const require = createRequire(import.meta.url);

export function probeServer(root, origin = 'http://localhost:5173') {
  return new Promise((resolve, reject) => {
    const request = http.get(new URL(identityPath, origin), { agent: false }, response => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', chunk => {
        body += chunk;
        if (body.length > 8192) request.destroy(new Error('Invalid renderer identity'));
      });
      response.on('error', reject);
      response.on('end', () => {
        try {
          const identity = JSON.parse(body);
          if (response.statusCode === 200 && identity.app === 'indiebiz-os'
              && identity.root === realpathSync(root)) return resolve(true);
        } catch { /* An unrelated HTTP server is not a renderer. */ }
        reject(new Error(`${origin} is occupied by an unrecognized server; no processes were stopped.`));
      });
    });
    request.setTimeout(2000, () => request.destroy(new Error('Renderer identity check timed out')));
    request.on('error', error => {
      if (error.code === 'ECONNREFUSED') resolve(false);
      else reject(error);
    });
  });
}

async function createRenderer(root) {
  const { createServer } = await import('vite');
  return createServer({ root });
}

function launchElectron(root) {
  return spawn(require('electron'), ['.'], { cwd: root, stdio: 'inherit' });
}

export async function runDesktop({
  root = frontendRoot, origin = 'http://localhost:5173',
  createServer = createRenderer, launch = launchElectron,
  signals = process, log = console.log,
} = {}) {
  checkUpdateAdmission(path.dirname(root));
  let server;
  let child;
  let stopped = false;
  const stop = () => {
    stopped = true;
    child?.kill('SIGTERM');
  };
  signals.on('SIGINT', stop);
  signals.on('SIGTERM', stop);
  try {
    if (await probeServer(root, origin)) {
      log('[Desktop] Reusing this checkout\'s renderer server');
    } else {
      server = await createServer(root);
      if (stopped) return 130;
      try {
        await server.listen();
      } catch (error) {
        // Another launch may have acquired the port while this one was preparing.
        await server.close();
        server = undefined;
        if (!/EADDRINUSE|already in use/.test(`${error.code} ${error.message}`)
            || !await probeServer(root, origin)) throw error;
        log('[Desktop] Reusing renderer started by another launch');
      }
      if (!await probeServer(root, origin)) throw new Error('Renderer did not become ready');
    }
    if (stopped) return 130;
    // Vite startup (including catalog generation) must succeed before opening a window.
    child = launch(root);
    return await new Promise((resolve, reject) => {
      child.once('error', reject);
      child.once('exit', (code, signal) => resolve(code ?? (signal ? 1 : 0)));
    });
  } finally {
    signals.removeListener('SIGINT', stop);
    signals.removeListener('SIGTERM', stop);
    await server?.close();
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.exitCode = await runDesktop(); }
  catch (error) {
    console.error('[Desktop] Startup failed:', error.message);
    process.exitCode = 1;
  }
}
