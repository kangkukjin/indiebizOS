/** Call window — route `#/media-call/<session_id>`. One session, one engine, one window. */
import { useEffect, useRef, useState } from 'react';
import { Info } from 'lucide-react';
import { useMediaSession } from './use-media-session';
import { StateBanner } from './StateBanner';
import { CallControls } from './CallControls';
import { SessionDetails } from './SessionDetails';
import { IncomingCallPane } from './IncomingCallPane';
import { LevelMeter } from './LevelMeter';
import { PlaybackControlPane, SpeakerSourcePane } from './ExtensionPanes';
import { applySink } from '../../lib/media/devices';

const PURPOSE_LABEL: Record<string, string> = {
  voice_call: '음성 통화', video_call: '영상 통화', camera: '카메라 보기', microphone: '소리 듣기', speaker: '재생음 보내기', playback: '이 장치에서 재생',
};

function MediaSink({ stream, kind, sinkId, onFrames, dimmed }: {
  stream: MediaStream | null; kind: 'audio' | 'video'; sinkId?: string; onFrames?: (ok: boolean) => void; dimmed: boolean;
}) {
  const ref = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    if (el.srcObject !== stream) el.srcObject = stream;
    if (stream) void el.play().catch(() => { /* autoplay with sound may wait for a gesture; the controls are one */ });
  }, [stream]);
  useEffect(() => { void applySink(ref.current, sinkId); }, [sinkId]);
  const common = { ref, autoPlay: true, playsInline: true, onTimeUpdate: () => onFrames?.(!!ref.current && ref.current.videoWidth > 0 && !ref.current.paused) };
  if (kind === 'audio') return <audio {...common} aria-label="상대 소리" />;
  return <video {...common} aria-label="상대 영상" className={`max-h-full max-w-full object-contain transition-opacity ${dimmed ? 'opacity-30 grayscale' : ''}`} />;
}

export function CallWindow({ sessionId }: { sessionId: string }) {
  const m = useMediaSession(sessionId);
  const [details, setDetails] = useState(false);
  const [remoteFrames, setRemoteFrames] = useState(false);
  const [busy, setBusy] = useState(false);
  const localVideo = useRef<HTMLVideoElement>(null);
  const session = m.session;
  const purpose = session?.purpose;
  const dimmed = m.uiState === 'reconnecting' || m.engineState === 'reconnecting';
  const ended = m.uiState === 'ended' || m.uiState === 'error';
  const ringingCallee = !!session && m.isCallee && (session.state === 'ringing' || session.state === 'inviting');
  const showVideo = purpose === 'video_call' || purpose === 'camera';
  const hasRemoteVideo = !!m.remoteStream?.getVideoTracks().length;

  useEffect(() => {
    const el = localVideo.current; if (!el) return;
    const stream = m.localStream && m.localStream.getVideoTracks().length ? m.localStream : null;
    if (el.srcObject !== stream) el.srcObject = stream;
    if (stream) void el.play().catch(() => {});
  }, [m.localStream]);

  useEffect(() => {
    document.title = `${m.remoteName || '…'} · ${purpose ? PURPOSE_LABEL[purpose] ?? purpose : '미디어'}`;
  }, [m.remoteName, purpose]);

  useEffect(() => { if (ended) setRemoteFrames(false); }, [ended]);

  const close = async () => { if (!ended) await m.hangUp('local_end'); window.close(); };
  const hangUp = () => { void m.hangUp('local_end'); };
  const act = async (fn: () => Promise<void>) => { setBusy(true); try { await fn(); } finally { setBusy(false); } };

  let stage: React.ReactNode;
  if (ringingCallee && session) {
    stage = <IncomingCallPane session={session} busy={busy} onAccept={() => void act(m.accept)} onReject={() => void act(m.reject)} />;
  } else if (purpose === 'playback' || session?.delivery === 'content') {
    stage = <PlaybackControlPane content={session?.content} disabled={ended || busy} onUpdate={changes => void act(() => m.update(changes))} />;
  } else if (purpose === 'speaker' && m.isHub) {
    stage = <div className="flex flex-1 flex-col">
      <SpeakerSourcePane sending={!!m.localStream} onSource={el => void m.sendPlayback(el)} />
      {m.localStream && <div className="flex justify-center pb-4"><LevelMeter stream={m.localStream} label="보내는 소리" /></div>}
    </div>;
  } else if (purpose === 'microphone' && m.isHub) {
    stage = <div className="flex flex-1 flex-col items-center justify-center gap-4">
      <MediaSink stream={m.remoteStream} kind="audio" sinkId={m.choice.speaker} dimmed={dimmed} />
      <p className="text-sm text-stone-300">{m.remoteName} 의 마이크</p>
      <LevelMeter stream={dimmed ? null : m.remoteStream} />
    </div>;
  } else if (showVideo) {
    stage = <>
      <MediaSink stream={m.remoteStream} kind={hasRemoteVideo ? 'video' : 'audio'} sinkId={m.choice.speaker} onFrames={setRemoteFrames} dimmed={dimmed} />
      {!hasRemoteVideo && <div className="absolute text-sm text-stone-400">{m.engineState === 'active' ? '상대 영상이 아직 없습니다' : ''}</div>}
    </>;
  } else {
    stage = <div className="flex flex-col items-center gap-3">
      <MediaSink stream={m.remoteStream} kind="audio" sinkId={m.choice.speaker} dimmed={dimmed} />
      <div className="flex h-28 w-28 items-center justify-center rounded-full bg-stone-800 text-4xl">{(m.remoteName || '?').slice(0, 1).toUpperCase()}</div>
      <p className="text-lg">{m.remoteName}</p>
      <LevelMeter stream={dimmed ? null : m.remoteStream} label="상대 소리 크기" />
    </div>;
  }

  return (
    <main className="flex h-screen flex-col bg-stone-950 text-white">
      <header className="flex shrink-0 items-center gap-3 border-b border-white/10 px-4 py-2 text-sm">
        <strong className="truncate">{purpose ? PURPOSE_LABEL[purpose] ?? purpose : '미디어 세션'}</strong>
        <span className="truncate text-stone-400">{m.remoteName}</span>
        <span className="flex-1" />
        {m.path && <span className="rounded-full border border-white/20 px-2 py-0.5 text-[11px] text-stone-300">{m.path === 'relay' ? '중계' : '직접'}</span>}
        <button className="flex items-center gap-1 rounded border border-white/20 px-2 py-1 text-xs" aria-pressed={details} onClick={() => setDetails(v => !v)}>
          <Info size={13} /> 상세
        </button>
        <button className="rounded border border-white/20 px-2 py-1 text-xs" onClick={() => void close()}>닫기</button>
      </header>
      <div className="flex min-h-0 flex-1">
        <section className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden" aria-busy={dimmed}>
          {stage}
          {m.localStream && m.localStream.getVideoTracks().length > 0 && !ringingCallee && (
            <video ref={localVideo} muted autoPlay playsInline aria-label="내 카메라 미리보기"
              className={`absolute bottom-3 right-3 h-28 w-40 rounded border border-white/20 bg-black object-cover ${m.cameraOff ? 'opacity-30' : ''}`} />
          )}
          <div className="pointer-events-none absolute inset-x-0 top-3 flex justify-center">
            <StateBanner state={m.uiState} session={session} error={m.error} endReason={m.endReason} onRetry={() => window.close()} />
          </div>
        </section>
        {details && <SessionDetails session={session} path={m.path} quality={m.quality} engineState={m.engineState} socketOpen={m.socketOpen} remoteFrames={remoteFrames} onClose={() => setDetails(false)} />}
      </div>
      {!ringingCallee && !ended && (
        <CallControls plan={m.plan} micMuted={m.micMuted} cameraOff={m.cameraOff} devices={m.devices} choice={m.choice}
          disabled={m.engineState === 'none'} onMic={m.toggleMic} onCamera={m.toggleCamera} onSwitchCamera={() => void m.switchCamera()}
          onDevice={(kind, id) => void m.chooseDevice(kind, id)} onHangUp={hangUp} />
      )}
    </main>
  );
}
