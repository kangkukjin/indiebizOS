/** Native VNC client: direct LAN first, client-side Cloudflare TCP fallback. */
import net from 'node:net';
import fs from 'node:fs';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export function desktopProfile(value) {
  const host = value => {
    if (typeof value !== 'string') throw new Error('Invalid desktop host');
    const s = value.trim();
    if (!s || net.isIP(s)) return s;
    if (s.length > 253 || !s.split('.').every(p => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i.test(p))) throw new Error('Invalid desktop host');
    return s.toLowerCase();
  };
  const port = value?.port ?? 5900;
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid desktop port');
  const direct_host = host(value?.direct_host ?? ''), tunnel_host = host(value?.tunnel_host ?? '');
  if (tunnel_host && (net.isIP(tunnel_host) || !tunnel_host.includes('.'))) throw new Error('Invalid Cloudflare hostname');
  return { direct_host, tunnel_host, port };
}

export function vncURL(host, port) {
  return `vnc://${net.isIP(host) === 6 ? `[${host}]` : host}:${port}`;
}

export function probeVNC(host, port, timeout = 2000) {
  return new Promise(resolve => {
    let bytes = Buffer.alloc(0), done = false;
    const socket = net.createConnection({ host, port });
    const finish = ok => { if (!done) { done = true; clearTimeout(timer); socket.destroy(); resolve(ok); } };
    const timer = setTimeout(() => finish(false), timeout);
    socket.on('data', data => {
      bytes = Buffer.concat([bytes, data]);
      if (bytes.length >= 12) finish(/^RFB \d{3}\.\d{3}\n$/.test(bytes.subarray(0, 12).toString('ascii')));
    });
    socket.on('error', () => finish(false));
    socket.on('end', () => finish(false));
  });
}

async function freePort() {
  const server = net.createServer();
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(error => error ? reject(error) : resolve(port));
    });
  });
}

function cloudflared() {
  for (const file of ['/opt/homebrew/bin/cloudflared', '/usr/local/bin/cloudflared']) {
    try { fs.accessSync(file, fs.constants.X_OK); return file; } catch { /* Try next installation. */ }
  }
  return 'cloudflared';
}

export function createDesktopConnector({ openExternal, platform = process.platform, spawnProcess = spawn, probe = probeVNC }) {
  const tunnels = new Map(), children = new Set();
  let stopping = false;
  async function proxy(host) {
    if (tunnels.has(host)) {
      const port = await tunnels.get(host);
      if (!await probe('127.0.0.1', port, 8000)) throw new Error('대상 PC의 화면 공유에 응답이 없습니다.');
      return port;
    }
    if (tunnels.size >= 16) throw new Error('열린 화면 공유 연결이 너무 많습니다. 앱을 다시 열어 연결을 정리하세요.');
    const pending = (async () => {
      const port = await freePort();
      if (stopping) throw new Error('앱이 종료 중입니다.');
      const child = spawnProcess(cloudflared(), ['access', 'tcp', '--hostname', host, '--url', `127.0.0.1:${port}`],
        { stdio: ['ignore', 'ignore', 'pipe'], windowsHide: true });
      children.add(child);
      let exited = false, missing = false;
      // Drain diagnostics without retaining credentials or remote content.
      child.stderr?.on('data', () => {});
      child.once('error', error => { missing = error.code === 'ENOENT'; exited = true; });
      child.once('exit', () => { exited = true; children.delete(child); if (tunnels.get(host) === pending) tunnels.delete(host); });
      try {
        const until = Date.now() + 12000;
        while (!exited && !stopping && Date.now() < until) {
          // Cloudflare's initial WebSocket/TLS handshake can take several seconds.
          if (await probe('127.0.0.1', port, 8000) && !exited && !stopping) return port;
          await new Promise(resolve => setTimeout(resolve, 150));
        }
        throw new Error(missing ? '이 Mac에 cloudflared를 설치한 뒤 다시 연결하세요.'
          : 'Cloudflare 연결을 확인하지 못했습니다. 대상 PC의 화면 공유와 터널 상태를 확인하세요.');
      } catch (error) {
        child.kill(); children.delete(child); throw error;
      }
    })();
    tunnels.set(host, pending);
    try { return await pending; }
    catch (error) { if (tunnels.get(host) === pending) tunnels.delete(host); throw error; }
  }
  return {
    async open(value, route = 'auto') {
      if (platform !== 'darwin') throw new Error('현재 화면 공유 연결은 Mac 데스크톱 앱에서 지원합니다.');
      if (stopping) throw new Error('앱이 종료 중입니다.');
      if (!['auto', 'tunnel'].includes(route)) throw new Error('Invalid desktop route');
      const profile = desktopProfile(value);
      if (route === 'auto' && profile.direct_host && await probe(profile.direct_host, profile.port)) {
        await openExternal(vncURL(profile.direct_host, profile.port));
        return { route: 'direct' };
      }
      if (!profile.tunnel_host) throw new Error('화면 공유에 연결되지 않습니다. 대상 PC의 공유 설정과 접속 주소를 확인하세요.');
      const port = await proxy(profile.tunnel_host);
      await openExternal(vncURL('127.0.0.1', port));
      return { route: 'tunnel' };
    },
    close() { stopping = true; for (const child of children) child.kill(); children.clear(); tunnels.clear(); },
  };
}

export function installRemoteDesktop({ app, ipcMain, shell }) {
  const connector = createDesktopConnector({ openExternal: url => shell.openExternal(url) });
  ipcMain.handle('remote-desktop:open', async (event, device, route) => {
    const frame = event.senderFrame;
    if (!frame || frame !== event.sender.mainFrame) throw new Error('Forbidden');
    const url = new URL(frame.url);
    const trusted = (!app.isPackaged && url.origin === 'http://localhost:5173') ||
      (url.protocol === 'file:' && fileURLToPath(url) === fileURLToPath(new URL('../dist/index.html', import.meta.url)));
    if (!trusted || typeof device !== 'string' || !/^guestpc-[a-f0-9]+$/.test(device)) throw new Error('Forbidden');
    // Fetch the owner's saved profile; an arbitrary renderer cannot choose a network target.
    const response = await fetch(`http://127.0.0.1:8765/remote-pcs/desktop/${device}`, { signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error('화면 공유 설정을 불러오지 못했습니다.');
    return connector.open(await response.json(), route);
  });
  app.on('before-quit', () => connector.close());
}
