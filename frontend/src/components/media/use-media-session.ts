/**
 * useMediaSession — one call window's state machine: control socket + WebRTC engine + local capture.
 * Rules it enforces: no getUserMedia before the callee accepts; local hang-up/mute win over remote commands;
 * `reconnecting` is surfaced separately so a frozen frame never looks live.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../lib/api';
import { MediaEngine, type EngineState } from '../../lib/media/engine';
import { MediaSessionClient, localRole, remoteParticipant } from '../../lib/media/session-client';
import { captureLocal, capturePlayback, planTracks, stopStream, type TrackPlan } from '../../lib/media/tracks';
import { listDevices, loadChoice, nextCamera, rememberChoice, resolveChoice, type DeviceChoice, type DeviceList } from '../../lib/media/devices';
import { videoConstraints } from '../../lib/media/sdp';
import type { MediaPath, MediaSession, OfferPayload, Quality, QualityProfile, SessionState, SignalFrame } from '../../lib/media/types';
import { EMPTY_QUALITY } from '../../lib/media/types';

export type UiState = SessionState | 'loading' | 'error';
const PC_PROFILE: QualityProfile = { maxBitrateKbps: 1500, maxFramerate: 30, width: 1280, height: 720 };

/** 허브 정책(data/media_policy.yaml)의 프로필은 snake_case(fps, max_bitrate_kbps) — 엔진 키로 옮긴다. */
function profileFromSession(session: MediaSession): QualityProfile | null {
  const raw = (session as MediaSession & { quality_profile?: Record<string, unknown> }).quality_profile;
  if (!raw || typeof raw !== 'object') return null;
  const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : undefined);
  const out: QualityProfile = {
    maxBitrateKbps: num(raw.max_bitrate_kbps) ?? num(raw.maxBitrateKbps),
    maxFramerate: num(raw.fps) ?? num(raw.maxFramerate),
    width: num(raw.width),
    height: num(raw.height),
  };
  return out.maxBitrateKbps || out.maxFramerate || out.width ? out : null;
}
const MEDIA_STATES: ReadonlySet<SessionState> = new Set(['accepted', 'authorized', 'connecting', 'active', 'reconnecting']);

export interface MediaSessionView {
  session: MediaSession | null;
  uiState: UiState;
  error: string | null;
  engineState: EngineState | 'none';
  path: MediaPath;
  quality: Quality;
  remoteStream: MediaStream | null;
  localStream: MediaStream | null;
  plan: TrackPlan | null;
  isCallee: boolean;
  isHub: boolean;
  remoteName: string;
  micMuted: boolean;
  cameraOff: boolean;
  devices: DeviceList;
  choice: DeviceChoice;
  socketOpen: boolean;
  endReason: string;
  accept: () => Promise<void>;
  reject: () => Promise<void>;
  hangUp: (reason?: string) => Promise<void>;
  toggleMic: () => void;
  toggleCamera: () => void;
  switchCamera: () => Promise<void>;
  chooseDevice: (kind: 'camera' | 'microphone' | 'speaker', id: string) => Promise<void>;
  update: (changes: Record<string, unknown>) => Promise<void>;
  /** Speaker purpose: start sending the given `<audio>` element as the playback track. */
  sendPlayback: (element: HTMLMediaElement) => Promise<void>;
}

export function useMediaSession(sessionId: string): MediaSessionView {
  const client = useRef<MediaSessionClient | null>(null);
  const engine = useRef<MediaEngine | null>(null);
  const local = useRef<MediaStream | null>(null);
  const pendingOffer = useRef<{ payload: OfferPayload; generation: number } | null>(null);
  const earlySignals = useRef<SignalFrame[]>([]);
  const appliedOffer = useRef('');
  const planRef = useRef<TrackPlan | null>(null);
  const starting = useRef(false);
  const [session, setSession] = useState<MediaSession | null>(null);
  const [uiState, setUiState] = useState<UiState>('loading');
  const [error, setError] = useState<string | null>(null);
  const [engineState, setEngineState] = useState<EngineState | 'none'>('none');
  const [path, setPath] = useState<MediaPath>(null);
  const [quality, setQuality] = useState<Quality>(EMPTY_QUALITY);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [micMuted, setMicMuted] = useState(false);
  const [cameraOff, setCameraOff] = useState(false);
  const [devices, setDevices] = useState<DeviceList>({ cameras: [], microphones: [], speakers: [] });
  const [choice, setChoice] = useState<DeviceChoice>(() => loadChoice());
  const [socketOpen, setSocketOpen] = useState(false);
  const [endReason, setEndReason] = useState('');

  const mine = session ? localRole(session) : null;
  const isCallee = mine === 'callee';
  const isHub = mine === 'hub';

  const teardown = useCallback(() => {
    engine.current?.close(); engine.current = null;
    stopStream(local.current); local.current = null;
    setLocalStream(null); setRemoteStream(null);
  }, []);

  const fail = useCallback((message: string) => { setError(message); setUiState('error'); }, []);

  /** Build the engine for the current session (offerer creates the offer; answerer applies a pending one). */
  const startEngine = useCallback(async (current: MediaSession, extraStream?: MediaStream) => {
    if (engine.current || starting.current) return;
    starting.current = true;
    try {
      const role = localRole(current);
      const plan = planTracks(current, role);
      planRef.current = plan;
      const profile = profileFromSession(current) ?? PC_PROFILE;
      const isOfferer = role === 'caller' || role === 'hub';
      let stream = extraStream ?? null;
      if (!stream) stream = await captureLocal(plan, { microphone: choice.microphone, camera: choice.camera }, profile);
      if (plan.sendPlayback && !extraStream) { starting.current = false; return; }  // speaker purpose waits for a source
      const eng = new MediaEngine({
        iceServers: current.ice_servers ?? [],
        refreshIceServers: async () => (await api.request<{ ice_servers: RTCIceServer[] }>(`/media/ice-config?session_id=${encodeURIComponent(current.session_id)}`)).ice_servers,
        trickle: current.signaling?.route !== 'nostr',
        reconnectS: current.lease?.reconnect_s ?? 30,
        qualityProfile: profile,
        offerer: isOfferer,
        generation: current.generation ?? 0,
        onSignal: (type, payload, generation) => {
          const c = client.current; if (!c) return;
          if (generation > c.generation) c.sequencer?.adoptGeneration(generation);
          c.send(type, payload);
        },
        onState: (state, detail) => {
          setEngineState(state);
          const c = client.current;
          if (state === 'active' || state === 'reconnecting' || state === 'connecting') c?.send('state', { state, path: null, quality: EMPTY_QUALITY }, 'hub');
          if (state === 'failed') { void hangUpRef.current(detail || 'connectivity_failed'); }
        },
        onTrack: (track, streams) => {
          const incoming = streams[0] ?? new MediaStream([track]);
          setRemoteStream(previous => (previous && previous.id === incoming.id ? previous : incoming));
        },
      });
      engine.current = eng;
      if (stream) { eng.addStream(stream, plan.sendPlayback ? 'music' : 'speech'); local.current = stream; setLocalStream(stream); }
      // Only the offerer declares receive-only slots; the answerer's transceivers come from the offer itself.
      if (isOfferer && plan.recvAudio && !stream?.getAudioTracks().length) eng.addReceiver('audio');
      if (isOfferer && plan.recvVideo && !stream?.getVideoTracks().length) eng.addReceiver('video');
      setEngineState(eng.state);
      if (isOfferer) await eng.createOffer();
      else if (pendingOffer.current) {
        const p = pendingOffer.current; pendingOffer.current = null;
        appliedOffer.current = `${p.generation}:${p.payload.sdp}`;
        await eng.receive('offer', { ...p.payload }, p.generation);
      }
      for (const frame of earlySignals.current.splice(0)) await eng.receive(frame.type as 'candidate' | 'candidates_done' | 'answer', frame.payload, frame.generation);
    } catch (e) {
      fail(e instanceof Error ? e.message : '미디어를 시작하지 못했습니다.');
      teardown();
    } finally { starting.current = false; }
  }, [choice.camera, choice.microphone, fail, teardown]);

  const hangUp = useCallback(async (reason = 'local_end') => {
    teardown();
    setEndReason(reason);
    setUiState('ended');
    await client.current?.end(reason);
  }, [teardown]);
  const hangUpRef = useRef(hangUp);
  hangUpRef.current = hangUp;

  const onSession = useCallback((s: MediaSession) => {
    setSession(s);
    if (s.state === 'ended') { teardown(); setEndReason(s.end_reason || s.error?.message || ''); setUiState('ended'); return; }
    setUiState(s.state);
    if (s.pending_offer && !pendingOffer.current && !engine.current) {
      pendingOffer.current = { payload: s.pending_offer, generation: s.generation ?? 0 };
    }
    const role = localRole(s);
    const offererNow = role === 'caller' || role === 'hub';
    // Caller/hub start capture as soon as the hub accepted our request; callee only after our own accept.
    const ready = s.delivery !== 'content' && (MEDIA_STATES.has(s.state) || (offererNow && role === 'caller' && (s.state === 'inviting' || s.state === 'ringing')));
    if (ready && !engine.current) void startEngine(s);
  }, [startEngine, teardown]);

  const onSignal = useCallback((frame: SignalFrame) => {
    const eng = engine.current;
    switch (frame.type) {
      case 'offer': {
        const key = `${frame.generation}:${String(frame.payload.sdp)}`;
        if (key === appliedOffer.current) break;
        if (eng) appliedOffer.current = key;
        if (eng) void eng.receive('offer', frame.payload, frame.generation).catch(e => fail(e instanceof Error ? e.message : '협상 실패'));
        else pendingOffer.current = { payload: frame.payload as unknown as OfferPayload, generation: frame.generation };
        break;
      }
      case 'answer': case 'candidate': case 'candidates_done': case 'renegotiate':
        if (eng) void eng.receive(frame.type, frame.payload, frame.generation).catch(() => { /* stale negotiation */ });
        else if (earlySignals.current.length < 128) earlySignals.current.push(frame);
        break;
      case 'end':
        teardown(); setEndReason(String((frame.payload as { reason?: string }).reason ?? 'remote_end')); setUiState('ended');
        break;
      case 'state': {
        const p = frame.payload as { path?: MediaPath; quality?: Quality };
        if (p.path !== undefined && !eng) setPath(p.path);
        if (p.quality && !eng) setQuality(p.quality);
        break;
      }
      default: break;
    }
  }, [fail, teardown]);

  useEffect(() => {
    const c = new MediaSessionClient(sessionId, {
      onSession, onSignal, onSocket: setSocketOpen,
      onError: e => fail(e.message || e.code),
      // Calls: the hub renews the lease only on peer_alive proven over the DTLS DataChannel (design §14).
      keepalivePayload: () => (engine.current ? { peer_alive: engine.current.peerAlive } : {}),
    });
    client.current = c;
    c.connect().catch(e => fail(e instanceof Error ? e.message : '세션을 불러오지 못했습니다.'));
    void listDevices().then(list => { setDevices(list); setChoice(previous => resolveChoice(list, previous)); });
    const onDevices = () => { void listDevices().then(setDevices); };
    navigator.mediaDevices?.addEventListener?.('devicechange', onDevices);
    const onHide = () => { void hangUpRef.current('window_closed'); };
    window.addEventListener('pagehide', onHide);
    return () => {
      window.removeEventListener('pagehide', onHide);
      navigator.mediaDevices?.removeEventListener?.('devicechange', onDevices);
      teardown(); c.dispose(); client.current = null;
    };
    // The session id is the only identity of this window; handlers are stable per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // Quality sampling + state report to the hub (contract §3 `state`).
  useEffect(() => {
    const timer = setInterval(() => {
      const eng = engine.current; if (!eng || eng.state === 'closed') return;
      void eng.getQuality().then(({ quality: q, path: p }) => {
        setQuality(q); setPath(p);
        client.current?.send('state', { state: eng.state === 'active' ? 'active' : eng.state, path: p, quality: q }, 'hub');
      });
    }, 2000);
    return () => clearInterval(timer);
  }, []);

  const accept = useCallback(async () => {
    const c = client.current; if (!c) return;
    try { const s = await c.accept('local'); if (!engine.current) await startEngine(s); }
    catch (e) { fail(e instanceof Error ? e.message : '수락하지 못했습니다.'); }
  }, [fail, startEngine]);

  const reject = useCallback(async () => {
    try { await client.current?.reject('rejected'); } catch (e) { fail(e instanceof Error ? e.message : '거절하지 못했습니다.'); }
    setEndReason('rejected'); setUiState('ended');
  }, [fail]);

  const toggleMic = useCallback(() => {
    setMicMuted(previous => { const next = !previous; engine.current?.setEnabled('audio', !next); return next; });
  }, []);
  const toggleCamera = useCallback(() => {
    setCameraOff(previous => { const next = !previous; engine.current?.setEnabled('video', !next); return next; });
  }, []);

  const chooseDevice = useCallback(async (kind: 'camera' | 'microphone' | 'speaker', id: string) => {
    setChoice(rememberChoice(kind, id));
    const eng = engine.current; if (!eng || kind === 'speaker') return;
    try {
      const constraints: MediaStreamConstraints = kind === 'camera'
        ? { video: videoConstraints(PC_PROFILE, id) } : { audio: { deviceId: { exact: id }, echoCancellation: true, noiseSuppression: true, autoGainControl: true } };
      const fresh = await navigator.mediaDevices.getUserMedia(constraints);
      const track = kind === 'camera' ? fresh.getVideoTracks()[0] : fresh.getAudioTracks()[0];
      if (!track) return;
      track.enabled = kind === 'camera' ? !cameraOff : !micMuted;
      const old = local.current;
      await eng.replaceTrack(kind === 'camera' ? 'video' : 'audio', track);
      const stream = new MediaStream([...(old?.getTracks().filter(t => t.kind !== track.kind) ?? []), track]);
      old?.getTracks().filter(t => t.kind === track.kind).forEach(t => t.stop());
      local.current = stream; setLocalStream(stream);
    } catch (e) { setError(e instanceof Error ? e.message : '장치를 바꾸지 못했습니다.'); }
  }, [cameraOff, micMuted]);

  const switchCamera = useCallback(async () => {
    const current = local.current?.getVideoTracks()[0]?.getSettings().deviceId ?? choice.camera;
    const next = nextCamera(devices, current);
    if (next) await chooseDevice('camera', next);
  }, [choice.camera, chooseDevice, devices]);

  const update = useCallback(async (changes: Record<string, unknown>) => {
    const c = client.current; const s = c?.session; if (!c || !s) return;
    try { await c.update(s.revision, changes); }
    catch (e) { setError(e instanceof Error ? e.message : '변경을 보내지 못했습니다.'); }
  }, []);

  const sendPlayback = useCallback(async (element: HTMLMediaElement) => {
    const s = client.current?.session; if (!s) return;
    try {
      const stream = capturePlayback(element);
      if (engine.current) { const track = stream.getAudioTracks()[0]; if (track) await engine.current.replaceTrack('audio', track); local.current = stream; setLocalStream(stream); }
      else await startEngine(s, stream);
    } catch (e) { fail(e instanceof Error ? e.message : '재생음을 보내지 못했습니다.'); }
  }, [fail, startEngine]);

  return {
    session, uiState, error, engineState, path, quality, remoteStream, localStream, plan: planRef.current,
    isCallee, isHub, remoteName: session ? (remoteParticipant(session)?.user?.name || remoteParticipant(session)?.device?.name || remoteParticipant(session)?.user?.id || '') : '',
    micMuted, cameraOff, devices, choice, socketOpen, endReason,
    accept, reject, hangUp, toggleMic, toggleCamera, switchCamera, chooseDevice, update, sendPlayback,
  };
}
