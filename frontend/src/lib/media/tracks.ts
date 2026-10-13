/** What this participant sends/receives for a session, and the local capture that follows from it. */
import type { MediaSession, ParticipantRole, QualityProfile, SessionTrack } from './types.ts';
import { audioConstraints, videoConstraints } from './sdp.ts';

export interface TrackPlan {
  sendMic: boolean; sendCamera: boolean; sendPlayback: boolean;
  recvAudio: boolean; recvVideo: boolean;
}

const live = (t: SessionTrack) => t.state !== 'rejected' && t.state !== 'ended';

/** Derive the plan from `session.tracks`; fall back to the purpose when the hub sent no track list yet. */
export function planTracks(session: MediaSession, mine: ParticipantRole): TrackPlan {
  const tracks = (session.tracks ?? []).filter(live);
  if (tracks.length) {
    const out = tracks.filter(t => t.from === mine), inn = tracks.filter(t => t.to === mine);
    return {
      sendMic: out.some(t => t.kind === 'audio' && t.source === 'mic'),
      sendCamera: out.some(t => t.kind === 'video' && (t.source === 'camera' || t.source === 'screen')),
      sendPlayback: out.some(t => t.kind === 'audio' && t.source === 'playback'),
      recvAudio: inn.some(t => t.kind === 'audio'),
      recvVideo: inn.some(t => t.kind === 'video'),
    };
  }
  const hub = mine === 'hub';
  switch (session.purpose) {
    case 'voice_call': return { sendMic: true, sendCamera: false, sendPlayback: false, recvAudio: true, recvVideo: false };
    case 'video_call': return { sendMic: true, sendCamera: true, sendPlayback: false, recvAudio: true, recvVideo: true };
    case 'camera': return { sendMic: false, sendCamera: !hub, sendPlayback: false, recvAudio: hub, recvVideo: hub };
    case 'microphone': return { sendMic: !hub, sendCamera: false, sendPlayback: false, recvAudio: hub, recvVideo: false };
    case 'speaker': return { sendMic: false, sendCamera: false, sendPlayback: hub, recvAudio: !hub, recvVideo: false };
    default: return { sendMic: false, sendCamera: false, sendPlayback: false, recvAudio: false, recvVideo: false };
  }
}

export interface CaptureChoice { microphone?: string; camera?: string; facingMode?: 'user' | 'environment' }

/** getUserMedia for the plan. Never called before the callee accepted (the hook enforces it). */
export async function captureLocal(plan: TrackPlan, choice: CaptureChoice, profile?: QualityProfile): Promise<MediaStream | null> {
  if (!plan.sendMic && !plan.sendCamera) return null;
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) throw new Error('이 환경에서는 카메라·마이크를 쓸 수 없습니다.');
  const constraints: MediaStreamConstraints = {
    audio: plan.sendMic ? audioConstraints('mic', choice.microphone) : false,
    video: plan.sendCamera ? videoConstraints(profile, choice.camera, choice.facingMode) : false,
  };
  try { return await navigator.mediaDevices.getUserMedia(constraints); }
  catch (error) {
    const name = error instanceof DOMException ? error.name : '';
    if (name === 'NotAllowedError' || name === 'SecurityError') throw new Error('카메라·마이크 권한이 거부됐습니다. 시스템 설정에서 IndieBiz 의 접근을 허용해 주세요.');
    if (name === 'NotFoundError' || name === 'OverconstrainedError') throw new Error('사용할 수 있는 카메라·마이크가 없습니다.');
    if (name === 'NotReadableError') throw new Error('다른 프로그램이 카메라·마이크를 쓰고 있습니다.');
    throw error instanceof Error ? error : new Error(String(error));
  }
}

/** Capture an `<audio>` element (local file or URL) as the `playback` track — no voice processing. */
export function capturePlayback(element: HTMLMediaElement): MediaStream {
  const capture = (element as HTMLMediaElement & { captureStream?: () => MediaStream; mozCaptureStream?: () => MediaStream });
  const fn = capture.captureStream ?? capture.mozCaptureStream;
  if (!fn) throw new Error('이 환경에서는 재생음을 보낼 수 없습니다.');
  const stream = fn.call(element);
  for (const track of stream.getAudioTracks()) if ('contentHint' in track) track.contentHint = 'music';
  return stream;
}

export function stopStream(stream: MediaStream | null | undefined): void {
  for (const track of stream?.getTracks() ?? []) track.stop();
}
