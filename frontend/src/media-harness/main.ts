/**
 * Loopback harness: two MediaEngines in one page wired through the contract's offer/answer/candidate
 * vocabulary (no hub). Proves real decode: the answerer's <video> gets frames (videoWidth > 0, framesDecoded > 0).
 * Driven by scripts/test_media_loopback.py with Chromium's fake camera.
 */
import { MediaEngine, type EngineSignalType } from '../lib/media/engine';
import { SignalSequencer } from '../lib/media/signal';
import type { QualityProfile } from '../lib/media/types';

interface Pair { a: MediaEngine; b: MediaEngine; log: string[]; sequencerA: SignalSequencer; sequencerB: SignalSequencer; frames: unknown[] }

declare global {
  interface Window {
    harness: {
      run(options: { trickle: boolean; profile?: QualityProfile }): Promise<{ generation: number; path: string | null; quality: Record<string, number>; width: number; framesDecoded: number; states: string[]; peerAlive: boolean[] }>;
      restart(): Promise<{ generation: number; state: string; frameGenerations: number[] }>;
      close(): void;
      pair: Pair | null;
    };
  }
}

const status = document.getElementById('status') as HTMLParagraphElement;
const remote = document.getElementById('remote') as HTMLVideoElement;
let current: Pair | null = null;
const say = (text: string) => { status.textContent = text; };

async function framesDecoded(engine: MediaEngine): Promise<number> {
  const report = await engine.pc.getStats();
  let frames = 0;
  report.forEach(s => { if (s.type === 'inbound-rtp' && s.kind === 'video') frames = s.framesDecoded ?? 0; });
  return frames;
}

function waitFor(check: () => boolean, timeoutMs: number, what: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const started = performance.now();
    const tick = () => {
      if (check()) return resolve();
      if (performance.now() - started > timeoutMs) return reject(new Error(`timeout: ${what}`));
      setTimeout(tick, 100);
    };
    tick();
  });
}

async function run({ trickle, profile }: { trickle: boolean; profile?: QualityProfile }) {
  window.harness.close();
  const states: string[] = [];
  const log: string[] = [];
  const frames: unknown[] = [];
  const sequencerA = new SignalSequencer('s'.repeat(32), 'hub', 'device');
  const sequencerB = new SignalSequencer('s'.repeat(32), 'device', 'hub');
  // Deliver A→B and B→A through frames so seq/generation handling is exercised, like the hub would.
  const deliver = (fromSeq: SignalSequencer, toSeq: SignalSequencer, target: () => MediaEngine) =>
    (type: EngineSignalType, payload: Record<string, unknown>, generation: number) => {
      if (generation > fromSeq.generation) fromSeq.adoptGeneration(generation);
      const frame = fromSeq.frame(type, payload);
      frames.push(frame);
      log.push(`${frame.from}->${frame.to} ${type} g${frame.generation} s${frame.seq}`);
      queueMicrotask(() => {
        if (toSeq.accept(frame) !== 'accept') { log.push(`dropped ${type}`); return; }
        void target().receive(type, frame.payload, frame.generation).catch(e => log.push(`error ${type}: ${e}`));
      });
    };
  const a = new MediaEngine({
    trickle, offerer: true, qualityProfile: profile, reconnectS: 15, disconnectGraceMs: 500,
    onSignal: deliver(sequencerA, sequencerB, () => b), onState: s => { states.push(`a:${s}`); say(states.join(' ')); },
  });
  const b: MediaEngine = new MediaEngine({
    trickle, offerer: false, reconnectS: 15,
    onSignal: deliver(sequencerB, sequencerA, () => a), onState: s => { states.push(`b:${s}`); say(states.join(' ')); },
    onTrack: (track, streams) => { remote.srcObject = streams[0] ?? new MediaStream([track]); void remote.play().catch(() => {}); },
  });
  current = { a, b, log, sequencerA, sequencerB, frames };
  window.harness.pair = current;
  const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
  a.addStream(stream, 'speech');  // the answerer's transceiver comes from the offer
  await a.createOffer();
  await waitFor(() => a.state === 'active' && b.state === 'active', 15000, 'both engines active');
  await waitFor(() => remote.videoWidth > 0, 15000, 'remote video has dimensions');
  await waitFor(() => false, 1500, '').catch(() => {});  // let a few frames decode before sampling stats
  const decoded = await framesDecoded(b);
  await b.getQuality();  // first sample seeds the bitrate delta
  await waitFor(() => false, 600, '').catch(() => {});
  const { quality, path } = await b.getQuality();
  await waitFor(() => a.peerAlive && b.peerAlive, 10000, 'liveness channel ping/pong on both sides');
  return { generation: a.generation, path, quality: quality as unknown as Record<string, number>, width: remote.videoWidth, framesDecoded: decoded, states, peerAlive: [a.peerAlive, b.peerAlive] };
}

async function restart() {
  if (!current) throw new Error('no pair');
  const { a, b, frames } = current;
  const before = a.generation;
  await a.restart();
  await waitFor(() => a.generation === before + 1 && a.state === 'active' && b.state === 'active', 15000, 'ICE restart back to active');
  return { generation: a.generation, state: a.state, frameGenerations: (frames as { generation: number }[]).map(f => f.generation) };
}

function close() {
  current?.a.close(); current?.b.close(); current = null; window.harness.pair = null;
}

window.harness = { run, restart, close, pair: null };
say('ready');
