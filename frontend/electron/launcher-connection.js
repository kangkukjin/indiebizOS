/** One launcher socket generation, one retry; stale callbacks cannot close its successor. */
export function createLauncherConnection({
  onCommand, WebSocketImpl = globalThis.WebSocket,
  url = 'ws://127.0.0.1:8765/ws/launcher', log = console.log,
  now = Date.now, schedule = setTimeout, cancel = clearTimeout,
  repeat = setInterval, cancelRepeat = clearInterval,
  retryMs = 3000, pingMs = 30000, timeoutMs = 90000,
} = {}) {
  let socket = null;
  let retry = null;
  let heartbeat = null;
  let stopped = true;

  function dispose() {
    const old = socket;
    socket = null;
    if (heartbeat !== null) cancelRepeat(heartbeat);
    heartbeat = null;
    if (!old) return;
    // close() can synchronously emit error (not just close), especially while
    // CONNECTING. Revoke ownership AND every callback before touching transport.
    old.onopen = old.onmessage = old.onerror = old.onclose = null;
    try { old.close(); } catch { /* Already closed or failed to connect. */ }
  }
  function reconnect() {
    if (stopped || retry !== null) return;
    retry = schedule(() => { retry = null; connect(); }, retryMs);
  }
  function drop(current, reason) {
    if (stopped || socket !== current) return;
    dispose();
    log('[Launcher WS] 소켓 폐기:', reason);
    reconnect();
  }
  function connect() {
    if (stopped || socket) return;
    let current;
    try { current = new WebSocketImpl(url); }
    catch {
      log('[Launcher WS] WebSocket 생성 실패, 재시도 예약');
      reconnect(); return;
    }
    socket = current;
    let lastPong = now();
    current.onopen = () => {
      if (stopped || socket !== current) return;
      lastPong = now();
      log('[Launcher WS] 메인 프로세스 연결됨');
    };
    current.onmessage = event => {
      if (stopped || socket !== current) return;
      try {
        const data = JSON.parse(typeof event.data === 'string' ? event.data : event.data.toString());
        if (data.type === 'pong') { lastPong = now(); return; }
        if (data.type === 'launcher_command') onCommand(data.command, data.params);
      } catch {
        log('[Launcher WS] 메시지 처리 실패');
      }
    };
    current.onerror = () => drop(current, 'onerror');
    current.onclose = () => drop(current, 'onclose');
    heartbeat = repeat(() => {
      if (stopped || socket !== current) return;
      if (now() - lastPong >= timeoutMs) { drop(current, '연결 또는 pong 시간 초과'); return; }
      if (current.readyState === 0) return;
      if (current.readyState !== 1) { drop(current, '소켓이 OPEN 이 아님'); return; }
      try { current.send(JSON.stringify({ type: 'ping' })); }
      catch { drop(current, 'ping 전송 실패'); }
    }, pingMs);
  }
  return {
    start() { if (!stopped) return; stopped = false; connect(); },
    stop() {
      stopped = true;
      if (retry !== null) cancel(retry);
      retry = null;
      dispose();
    },
  };
}
