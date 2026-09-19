import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../../data/packages/installed/tools/public-files/site/index.html', import.meta.url), 'utf8');
const source = html.slice(html.indexOf('function attachSeekRescue('), html.indexOf('function boot('));

function fixture() {
  let now = 0, nextTimer = 1, current;
  const timers = new Map(), pending = [], elements = new Map();
  class Element {
    listeners = new Map(); style = {}; textContent = ''; value = 0;
    addEventListener(name, fn) {
      if (!this.listeners.has(name)) this.listeners.set(name, new Set());
      this.listeners.get(name).add(fn);
    }
    removeEventListener(name, fn) { this.listeners.get(name)?.delete(fn); }
    dispatchEvent(e) { for (const fn of [...(this.listeners.get(e.type) || [])]) fn(e); }
  }
  class Video extends Element {
    isConnected = true; currentTime = 0.183; readyState = 1; paused = false;
    ended = false; seeking = false; error = null; duration = 100;
    ranges = [[0.083, 312]]; textTracks = []; playCalls = 0; loadCalls = 0;
    buffered = { get length() { return this.owner.ranges.length; }, owner: this,
      start: i => this.ranges[i][0], end: i => this.ranges[i][1] };
    seekable = this.buffered;
    pause() { this.paused = true; }
    play() { this.playCalls++; this.paused = false; return Promise.resolve(); }
    load() { this.loadCalls++; }
    removeAttribute(name) { if (name === 'src') this.src = ''; }
    querySelectorAll() { return []; }
    canPlayType() { return 'probably'; }
  }
  const body = {
    set innerHTML(_) { if (current) current.isConnected = false; current = new Video(); },
    querySelector() { return current; },
  };
  const document = {
    hidden: false,
    querySelectorAll: () => current ? [current] : [],
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, new Element());
      return elements.get(id);
    },
  };
  const context = vm.createContext({
    document, window: {}, navigator: { vendor: '' }, AbortController,
    performance: { now: () => now },
    CustomEvent: class { constructor(type, opts) { this.type = type; this.detail = opts.detail; } },
    setInterval(fn, ms) { const id = nextTimer++; timers.set(id, { fn, ms }); return id; },
    clearInterval(id) { timers.delete(id); },
    setTimeout(fn, ms) { const id = nextTimer++; timers.set(id, { fn, due: now + ms, once: true }); return id; },
    clearTimeout(id) { timers.delete(id); },
    qmode: () => 'auto', mediaUrl: it => `media/${it.title}`, hlsUrl: it => `hls/${it.title}`,
    trackHtml: () => '', fmtTime: n => String(n),
    fetch(url, options) { return new Promise((resolve, reject) => pending.push({ url, options, resolve, reject })); },
  });
  vm.runInContext(source + '\nglobalThis.api={attachPlaybackRecovery,openVideo,releasePlayback};', context);
  return {
    ...context.api, body, document, pending, timers, elements,
    safari() { context.navigator.vendor = 'Apple Computer, Inc.'; },
    enableHls() {
      const instances = [];
      class Hls {
        static Events = { ERROR: 'error' };
        static isSupported() { return true; }
        destroyed = false;
        constructor() { instances.push(this); }
        on(_, fn) { this.onError = fn; }
        loadSource(url) { this.url = url; }
        attachMedia(video) { this.video = video; }
        destroy() { this.destroyed = true; }
      }
      context.Hls = context.window.Hls = Hls;
      return instances;
    },
    video: () => current,
    bareVideo: () => new Video(),
    tick(ms) {
      for (let t = 0; t < ms; t += 500) {
        now += 500;
        for (const [id, timer] of [...timers]) {
          if (!timers.has(id) || (timer.once && now < timer.due)) continue;
          if (timer.once) timers.delete(id);
          timer.fn();
        }
      }
    },
  };
}
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };

test('buffered iPad startup stall recovers with bounded small seeks', () => {
  const f = fixture(), v = f.bareVideo(), moves = [];
  v.addEventListener('playbackrecovery', e => moves.push(e.detail));
  const stop = f.attachPlaybackRecovery(v);
  f.tick(3500);
  assert.equal(v.currentTime, 0.183);
  f.tick(500);
  assert.equal(v.currentTime, 0.583);
  f.tick(30000);
  assert.equal(moves.length, 2);
  assert.ok(v.currentTime < 1);
  assert.equal(v.playCalls, 0, 'seeking must not override playback permission or user pause');
  stop();
  assert.equal(f.timers.size, 0);
});

test('no seeking during pause, background, normal play or network starvation', () => {
  for (const change of [v => v.paused = true,
    v => v.readyState = 4, v => v.ranges = [], v => v.ranges = [[0, 0.3]],
    v => v.ranges = [[15, 30]], v => v.error = { code: 3 },
    (v, f) => f.document.hidden = true]) {
    const f = fixture(), v = f.bareVideo(); change(v, f);
    f.attachPlaybackRecovery(v); f.tick(20000);
    assert.equal(v.currentTime, 0.183);
  }
});

test('a user seek gets time to finish, but a buffered seek cannot hang forever', () => {
  const f = fixture(), v = f.bareVideo();
  f.attachPlaybackRecovery(v);
  v.seeking = true; v.dispatchEvent({ type: 'seeking' });
  f.tick(7500); assert.equal(v.currentTime, 0.183);
  f.tick(500); assert.equal(v.currentTime, 0.583);
});

test('real playback progress allows recovery of a later small buffer gap', () => {
  const f = fixture(), v = f.bareVideo();
  f.attachPlaybackRecovery(v); f.tick(8000);
  v.currentTime = 20; v.readyState = 4; f.tick(500);
  v.readyState = 2; v.ranges = [[20.1, 30]]; f.tick(4000);
  assert.equal(v.currentTime, 20.6);
  v.isConnected = false; f.tick(500);
  assert.equal(f.timers.size, 0);
});

test('closing cancels native HLS and stale results cannot revive old video', async () => {
  const f = fixture();
  f.openVideo(f.body, { title: 'old' });
  const old = f.video(), oldRequest = f.pending[0];
  assert.equal(f.elements.get('lbSeekBar').listeners.get('change').size, 1);
  f.releasePlayback();
  assert.equal(old.paused, true);
  assert.equal(old.src, '');
  assert.equal(old.loadCalls, 1);
  assert.equal(old.listeners.get('loadedmetadata').size, 0);
  assert.equal(old.listeners.get('timeupdate').size, 0);
  assert.equal(oldRequest.options.signal.aborted, true);
  assert.equal(f.elements.get('lbSeekBar').listeners.get('change').size, 0);
  assert.equal(f.timers.size, 0);
  f.openVideo(f.body, { title: 'new' });
  oldRequest.resolve({ ok: true }); await flush();
  assert.equal(old.playCalls, 0);
  f.pending[1].resolve({ ok: true }); await flush();
  assert.equal(f.video().src, 'hls/new');
  assert.equal(f.elements.get('lbSeekBar').listeners.get('change').size, 1);
});

test('native decode error falls back once; repeated errors never reload-loop', async () => {
  const f = fixture();
  f.openVideo(f.body, { title: 'movie' });
  f.pending[0].resolve({ ok: true }); await flush();
  const v = f.video();
  v.dispatchEvent({ type: 'error' });
  assert.equal(v.src, 'media/movie');
  assert.equal(v.loadCalls, 1);
  v.dispatchEvent({ type: 'error' });
  assert.equal(v.loadCalls, 1);
  f.releasePlayback();
  assert.equal(v.listeners.get('error').size, 0);
});

test('late hls.js errors cannot destroy the next video player', () => {
  const f = fixture(), players = f.enableHls();
  f.openVideo(f.body, { title: 'old' });
  f.releasePlayback();
  f.openVideo(f.body, { title: 'new' });
  players[0].onError(null, { fatal: true });
  assert.equal(players[0].destroyed, true);
  assert.equal(players[1].destroyed, false);
  assert.equal(f.video().loadCalls, 0);
  players[1].onError(null, { fatal: true });
  assert.equal(players[1].destroyed, true);
  assert.equal(f.video().src, 'media/new');
  players[1].onError(null, { fatal: true });
  assert.equal(f.video().loadCalls, 1);
});

test('Safari waits for completed HLS instead of switching to unsupported live MP4', async () => {
  const f = fixture(); f.safari(); const players = f.enableHls();
  f.openVideo(f.body, { title: 'movie' });
  players[0].onError(null, { fatal: true });
  assert.equal(f.video().src, '');
  assert.match(f.elements.get('lbCap').textContent, /준비/);
  f.pending[0].resolve({ ok: false, status: 404 }); await flush();
  f.tick(3000);
  f.pending[1].resolve({ ok: true }); await flush();
  assert.equal(players.length, 2);
  assert.equal(players[1].url, 'hls/movie');
  assert.notEqual(f.video().src, 'media/movie');
  f.video().dispatchEvent({ type: 'playing' });
  assert.equal(f.elements.get('lbCap').textContent, 'movie');
  // 준비 완료 후에도 해석할 수 없는 영상은 무한 재시도하지 않는다.
  players[1].onError(null, { fatal: true });
  assert.match(f.elements.get('lbCap').textContent, /재생하지 못/);
  assert.equal(players.length, 2);
});

test('closing while preparing cancels requests and prevents a stale HLS restart', async () => {
  const f = fixture(); f.safari(); const players = f.enableHls();
  f.openVideo(f.body, { title: 'movie' }); players[0].onError(null, { fatal: true });
  const r = f.pending[0]; f.releasePlayback();
  assert.equal(r.options.signal.aborted, true);
  assert.equal(f.timers.size, 0);
  r.resolve({ ok: true }); await flush(); f.tick(30000);
  assert.equal(players.length, 1);
});

test('preparation requests time out and stop after a bounded number of checks', async () => {
  const f = fixture(); f.safari(); const players = f.enableHls();
  f.openVideo(f.body, { title: 'movie' }); players[0].onError(null, { fatal: true });
  f.tick(8000);
  assert.equal(f.pending[0].options.signal.aborted, true);
  f.pending[0].reject(new Error('timeout')); await flush(); f.tick(3000);
  for (let i = 1; i < 40; i++) {
    f.pending[i].resolve({ ok: false, status: 404 }); await flush(); f.tick(3000);
  }
  assert.equal(f.pending.length, 40);
  assert.match(f.elements.get('lbCap').textContent, /재생하지 못/);
  f.releasePlayback(); assert.equal(f.timers.size, 0);
});
