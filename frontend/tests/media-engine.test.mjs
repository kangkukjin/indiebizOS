import { test } from 'node:test';
import assert from 'node:assert/strict';
import { extractFingerprint, fingerprintsMatch, qualityFromStats, pathFromStats, orderCodecs, encodingForProfile, waitForGathering, audioConstraints } from '../src/lib/media/sdp.ts';
import { SignalSequencer, isSignalFrame } from '../src/lib/media/signal.ts';
import { planTracks, capturePlayback } from '../src/lib/media/tracks.ts';

const SDP = [
  'v=0', 'o=- 1 2 IN IP4 127.0.0.1', 's=-', 't=0 0',
  'a=fingerprint:sha-256 AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89',
  'm=audio 9 UDP/TLS/RTP/SAVPF 111', 'a=mid:0',
].join('\r\n');

test('fingerprint is extracted from a=fingerprint and compared case-insensitively', () => {
  const fp = extractFingerprint(SDP);
  assert.equal(fp, 'sha-256 AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89');
  assert.equal(extractFingerprint('v=0\r\nm=audio 9 RTP/AVP 0'), '');
  assert.equal(fingerprintsMatch(SDP, fp.toLowerCase()), true);
  assert.equal(fingerprintsMatch(SDP, 'sha-256 00:11'), false);
  assert.equal(fingerprintsMatch(SDP, undefined), true);
});

test('stats report maps to the contract quality shape and path', () => {
  const report = [
    { id: 'T', type: 'transport', selectedCandidatePairId: 'P1' },
    { id: 'P1', type: 'candidate-pair', state: 'succeeded', nominated: true, localCandidateId: 'L', remoteCandidateId: 'R', currentRoundTripTime: 0.042 },
    { id: 'L', type: 'local-candidate', candidateType: 'host' },
    { id: 'R', type: 'remote-candidate', candidateType: 'relay' },
    { id: 'I1', type: 'inbound-rtp', kind: 'video', packetsLost: 5, packetsReceived: 995, bytesReceived: 250000, timestamp: 2000, jitter: 0.012, framesPerSecond: 29.6, frameWidth: 1280, frameHeight: 720, framesDropped: 3 },
    { id: 'I2', type: 'inbound-rtp', kind: 'audio', packetsLost: 0, packetsReceived: 500, bytesReceived: 50000, timestamp: 2000, jitter: 0.004 },
    { id: 'O1', type: 'outbound-rtp', kind: 'video', bytesSent: 100000, timestamp: 2000 },
  ];
  const first = qualityFromStats(report, { bytes: 200000, timestamp: 1000 });
  assert.deepEqual(first.quality, { rtt_ms: 42, loss: 0.003, jitter_ms: 8, bitrate_kbps: 1600, fps: 30, width: 1280, height: 720, dropped: 3 });
  assert.deepEqual(first.sample, { bytes: 400000, timestamp: 2000 });
  assert.equal(pathFromStats(report), 'relay');
  report[3].candidateType = 'srflx';
  assert.equal(pathFromStats(report), 'direct');
  assert.equal(pathFromStats([]), null);
  const noPrevious = qualityFromStats(report);
  assert.equal(noPrevious.quality.bitrate_kbps, 0);
});

test('codec order prefers Opus and H.264/VP8; bitrate cap and downscale follow the profile', () => {
  const audio = orderCodecs('audio', [{ mimeType: 'audio/PCMU' }, { mimeType: 'audio/opus' }, { mimeType: 'audio/red' }]);
  assert.deepEqual(audio.map(c => c.mimeType), ['audio/opus', 'audio/PCMU', 'audio/red']);
  const video = orderCodecs('video', [{ mimeType: 'video/VP9' }, { mimeType: 'video/VP8' }, { mimeType: 'video/rtx' }, { mimeType: 'video/H264' }, { mimeType: 'video/H264', sdpFmtpLine: 'x' }]);
  assert.deepEqual(video.map(c => c.mimeType), ['video/H264', 'video/H264', 'video/VP8', 'video/VP9', 'video/rtx']);
  assert.deepEqual(encodingForProfile({ maxBitrateKbps: 1500, maxFramerate: 30, width: 640 }, 1280), { maxBitrate: 1500000, maxFramerate: 30, scaleResolutionDownBy: 2 });
  assert.deepEqual(encodingForProfile({ maxBitrateKbps: 800 }, 320), { maxBitrate: 800000 });
  assert.deepEqual(encodingForProfile(undefined), {});
  assert.deepEqual(audioConstraints('mic'), { echoCancellation: true, noiseSuppression: true, autoGainControl: true });
  assert.deepEqual(audioConstraints('playback', 'mic-2'), { echoCancellation: false, noiseSuppression: false, autoGainControl: false, deviceId: { exact: 'mic-2' } });
});

test('signal frames carry increasing seq per generation and stale frames are dropped', () => {
  let clock = 1000;
  const s = new SignalSequencer('abc', 'hub', 'device', 0, () => clock);
  const a = s.frame('offer', { sdp: 'x', fingerprint: 'y' });
  const b = s.frame('keepalive', {});
  assert.equal(a.v, 1); assert.equal(a.from, 'hub'); assert.equal(a.to, 'device');
  assert.deepEqual([a.generation, a.seq, b.generation, b.seq], [0, 1, 0, 2]);
  assert.equal(a.expires_at, 1060);
  assert.equal(s.bumpGeneration(), 1);
  const c = s.frame('offer', { sdp: 'z', fingerprint: 'w' });
  assert.deepEqual([c.generation, c.seq], [1, 1]);
  assert.ok(isSignalFrame(c));
  assert.equal(isSignalFrame({ type: 'session', session: {} }), false);

  const incoming = (generation, seq, extra = {}) => ({ v: 1, session_id: 'abc', msg_id: `m${generation}-${seq}`, from: 'device', to: 'hub', generation, seq, type: 'candidate', payload: {}, ...extra });
  assert.equal(s.accept(incoming(1, 1)), 'accept');
  assert.equal(s.accept(incoming(1, 1)), 'duplicate');
  assert.equal(s.accept(incoming(1, 3)), 'accept');
  assert.equal(s.accept(incoming(1, 2)), 'stale_seq');
  assert.equal(s.accept(incoming(0, 9)), 'stale_generation');
  assert.equal(s.accept(incoming(1, 4, { expires_at: 999 })), 'expired');
  assert.equal(s.accept(incoming(1, 4, { session_id: 'other' })), 'other_session');
  assert.equal(s.accept(incoming(2, 1)), 'accept');
  assert.equal(s.generation, 2, 'a newer remote generation moves ours forward');
  assert.equal(s.frame('answer', {}).seq, 1);
});

test('early candidates are buffered per generation and older generations are discarded', () => {
  const s = new SignalSequencer('abc', 'callee', 'caller');
  s.bufferCandidate(0, { candidate: 'old' });
  s.bufferCandidate(1, { candidate: 'a' });
  s.bufferCandidate(1, { candidate: 'b' });
  assert.deepEqual(s.drainCandidates(1).map(c => c.candidate), ['a', 'b']);
  assert.deepEqual(s.drainCandidates(0), []);
  assert.deepEqual(s.drainCandidates(1), []);
});

test('non-trickle mode waits for ICE gathering to complete and times out honestly', async () => {
  const listeners = new Set();
  const pc = { iceGatheringState: 'gathering', addEventListener: (_t, fn) => listeners.add(fn), removeEventListener: (_t, fn) => listeners.delete(fn) };
  const pending = waitForGathering(pc, 1000);
  pc.iceGatheringState = 'complete';
  for (const fn of listeners) fn();
  assert.equal(await pending, 'complete');
  assert.equal(listeners.size, 0);
  assert.equal(await waitForGathering({ ...pc, iceGatheringState: 'complete' }), 'complete');
  assert.equal(await waitForGathering({ ...pc, iceGatheringState: 'gathering' }, 10), 'timeout');
});

test('track plan follows session tracks for this role, with purpose fallback', () => {
  const session = {
    kind: 'extension', purpose: 'camera', participants: [{ role: 'hub', user: { id: 'self' }, device: { id: 'local' } }, { role: 'device', user: { id: 'self' }, device: { id: 'guestpc-1' } }],
    tracks: [{ id: 'v0', kind: 'video', source: 'camera', from: 'device', to: 'hub', state: 'requested' }, { id: 'a0', kind: 'audio', source: 'mic', from: 'device', to: 'hub', state: 'rejected' }],
  };
  assert.deepEqual(planTracks(session, 'hub'), { sendMic: false, sendCamera: false, sendPlayback: false, recvAudio: false, recvVideo: true });
  assert.deepEqual(planTracks({ ...session, tracks: [] }, 'hub'), { sendMic: false, sendCamera: false, sendPlayback: false, recvAudio: true, recvVideo: true });
  assert.deepEqual(planTracks({ kind: 'call', purpose: 'voice_call', participants: [], tracks: [] }, 'callee'), { sendMic: true, sendCamera: false, sendPlayback: false, recvAudio: true, recvVideo: false });
  assert.deepEqual(planTracks({ kind: 'extension', purpose: 'speaker', participants: [], tracks: [] }, 'hub'), { sendMic: false, sendCamera: false, sendPlayback: true, recvAudio: false, recvVideo: false });
});


test('video playback sends rendered media without opening camera or microphone', () => {
  const session = { purpose: 'playback', tracks: [
    { kind: 'video', source: 'playback', from: 'hub', to: 'device', state: 'requested' },
    { kind: 'audio', source: 'playback', from: 'hub', to: 'device', state: 'requested' },
  ] };
  assert.deepEqual(planTracks(session, 'hub'), { sendMic: false, sendCamera: false, sendPlayback: true, recvAudio: false, recvVideo: false });
  assert.equal(planTracks(session, 'device').recvVideo, true);
  let stopped = false;
  const v = { stop() { stopped = true; } };
  const a = { contentHint: '' };
  let videos = [v];
  const stream = { getAudioTracks: () => [a], getVideoTracks: () => videos, getTracks: () => [...videos, a], removeTrack() { videos = []; } };
  assert.equal(capturePlayback({ captureStream: () => stream }, true), stream);
  assert.equal(stopped, false);
  assert.equal(a.contentHint, 'music');
  capturePlayback({ captureStream: () => stream }, false);
  assert.equal(stopped, true, 'speaker-only session must not accidentally transmit video');
  assert.equal(videos.length, 0);
});
