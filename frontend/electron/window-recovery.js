/** Recover app windows when Vite restarts during a live repair. */
export function installDevServerRecovery(contents, {
  origin = 'http://localhost:5173',
  schedule = setTimeout,
  cancel = clearTimeout,
} = {}) {
  let timer = null;
  let attempt = 0;
  let target = null;
  const transient = new Set([-100, -101, -102, -106, -118]);
  const isLocal = url => {
    try { return new URL(url).origin === origin; } catch { return false; }
  };
  const stop = () => {
    if (timer !== null) cancel(timer);
    timer = null;
  };
  const onStart = (_event, url, _inPlace, mainFrame) => {
    if (!mainFrame) return;
    stop();
    if (url !== target) attempt = 0;
    target = url;
  };
  const onFail = (_event, code, _description, url, mainFrame) => {
    if (!mainFrame || !transient.has(code) || !isLocal(url)
        || contents.isDestroyed() || (target !== null && target !== url)) return;
    target = url;
    if (timer !== null) return;
    // Retry only a failed top-level app navigation, preserving its hash/query.
    // No healthy page, external site, iframe, or aborted navigation is reloaded.
    timer = schedule(() => {
      timer = null;
      if (!contents.isDestroyed() && target === url) {
        void contents.loadURL(url).catch(() => {}); // did-fail-load schedules the next try.
      }
    }, Math.min(500 * 2 ** Math.min(attempt++, 4), 5000));
  };
  const onNavigate = (_event, url) => {
    if (isLocal(url)) {
      stop();
      attempt = 0;
    }
  };
  const dispose = () => {
    stop();
    contents.removeListener('did-start-navigation', onStart);
    contents.removeListener('did-fail-load', onFail);
    contents.removeListener('did-navigate', onNavigate);
    contents.removeListener('destroyed', dispose);
  };
  contents.on('did-start-navigation', onStart);
  contents.on('did-fail-load', onFail);
  contents.on('did-navigate', onNavigate);
  contents.once('destroyed', dispose);
  return dispose;
}
