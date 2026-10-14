/** Extension-purpose layouts: speaker (send a local audio source) and playback (drive the target player). */
import { useEffect, useRef, useState } from 'react';
import { Pause, Play } from 'lucide-react';
import type { SessionContent } from '../../lib/media/types';

/** Speaker purpose: explicitly choose playback or live microphone before opening the input. */
export function SpeakerSourcePane({ sending, disabled = false, video = false, onSource, onMicrophone }: {
  sending: boolean; disabled?: boolean; video?: boolean;
  onSource: (element: HTMLMediaElement) => void; onMicrophone?: () => void;
}) {
  const [source, setSource] = useState<'playback' | 'mic'>('playback');
  const locked = sending || disabled;
  const audio = useRef<HTMLMediaElement>(null);
  const [url, setUrl] = useState('');
  const [name, setName] = useState('');
  const [sourceError, setSourceError] = useState('');
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  useEffect(() => () => { if (objectUrl) URL.revokeObjectURL(objectUrl); }, [objectUrl]);
  const load = (src: string, label: string) => {
    const el = audio.current; if (!el) return;
    setSourceError(''); el.src = src; setName(label);
    void el.play().catch(() => { /* autoplay may need the user's click on the element */ });
  };
  return (
    <section aria-label="재생음 보내기" className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-white">
      <p className="text-sm text-stone-300">{video ? '이 PC에서 재생하는 영상과 소리를 장치로 보냅니다. 폰에서 미디어 화면을 열어 주세요.' : '이 PC의 소리를 장치의 스피커로 보냅니다.'}</p>
      {!video && <div role="group" aria-label="보낼 소리 선택" className="flex gap-2">
        <button className={`rounded border px-3 py-2 disabled:opacity-40 ${source === 'playback' ? 'border-emerald-400 bg-emerald-900' : 'border-white/20'}`} aria-pressed={source === 'playback'} disabled={locked} onClick={() => setSource('playback')}>파일·주소</button>
        <button className={`rounded border px-3 py-2 disabled:opacity-40 ${source === 'mic' ? 'border-emerald-400 bg-emerald-900' : 'border-white/20'}`} aria-pressed={source === 'mic'} disabled={locked} onClick={() => { audio.current?.pause(); setName(''); setSource('mic'); }}>마이크 입력</button>
      </div>}
      {source === 'mic' ? <>
        <p className="text-sm text-stone-300">이 PC의 마이크에 말하면 장치의 스피커에서 실시간으로 들립니다.</p>
        <button className="rounded bg-emerald-600 px-4 py-2 text-sm disabled:opacity-40" disabled={locked} onClick={onMicrophone}>
          {sending ? '마이크 소리 보내는 중' : '마이크 소리 보내기'}
        </button>
        <p className="text-xs text-stone-400">보내기를 누르면 마이크 권한을 요청합니다. 아래에서 음소거하거나 종료할 수 있습니다.</p>
      </> : <>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <label className="cursor-pointer rounded border border-white/20 px-3 py-1.5 text-sm hover:bg-white/10">
          파일 고르기
          <input type="file" disabled={locked} accept={video ? "video/*" : "audio/*,video/*"} className="hidden" onChange={e => {
            const file = e.target.files?.[0]; if (!file) return;
            const next = URL.createObjectURL(file);
            setObjectUrl(previous => { if (previous) URL.revokeObjectURL(previous); return next; });
            load(next, file.name);
          }} />
        </label>
        <input className="w-72 rounded border border-white/20 bg-stone-900 px-2 py-1.5 text-sm" placeholder="또는 주소(URL)" aria-label="재생 주소" disabled={locked} value={url} onChange={e => setUrl(e.target.value)} />
        <button className="rounded border border-white/20 px-3 py-1.5 text-sm hover:bg-white/10 disabled:opacity-40" disabled={locked || !url.trim()} onClick={() => load(url.trim(), url.trim())}>불러오기</button>
      </div>
      {video ? <video ref={audio as React.RefObject<HTMLVideoElement>} crossOrigin="anonymous" onError={() => setSourceError('파일을 재생할 수 없습니다. 코덱이나 URL의 접근·CORS 허용 여부를 확인해 주세요.')} controls muted playsInline className="max-h-72 w-full" aria-label="보낼 영상" />
        : <audio ref={audio as React.RefObject<HTMLAudioElement>} crossOrigin="anonymous" onError={() => setSourceError('파일을 재생할 수 없습니다. 코덱이나 URL의 접근·CORS 허용 여부를 확인해 주세요.')} controls muted className="w-96" aria-label="보낼 소리" />}
      {sourceError && <p role="alert" className="text-sm text-red-300">{sourceError}</p>}
      {name && <p className="max-w-md truncate text-xs text-stone-400">{name}</p>}
      <button className="rounded bg-emerald-600 px-4 py-2 text-sm hover:bg-emerald-500 disabled:opacity-40" disabled={!name || locked}
        onClick={() => { if (audio.current) onSource(audio.current); }}>
        {sending ? '보내는 중' : video ? '이 영상을 장치로 보내기' : '이 소리를 장치로 보내기'}
      </button>
      <p className="text-[11px] text-stone-500">여기서는 소리가 나지 않고 장치에서만 납니다. 통화용 잡음 억제는 적용하지 않습니다.</p>
      </>}
    </section>
  );
}

function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** Playback purpose (content delivery): the target reports position/paused; controls go through `update`. */
export function PlaybackControlPane({ content, disabled, onUpdate }: {
  content: SessionContent | null | undefined; disabled: boolean; onUpdate: (changes: Record<string, unknown>) => void;
}) {
  const [seek, setSeek] = useState('');
  const paused = content?.paused ?? true;
  const position = content?.position_s ?? 0;
  const volume = content?.volume ?? 80;
  return (
    <section aria-label="장치 재생 제어" className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-white">
      <p className="text-sm text-stone-300">장치에서 재생 중인 콘텐츠</p>
      <p className="max-w-md truncate text-xs text-stone-400">{content?.url || content?.path || content?.ref || '아직 보고된 콘텐츠가 없습니다'}</p>
      <p className="text-3xl tabular-nums">{clock(position)}{content?.duration_s ? ` / ${clock(content.duration_s)}` : ''}</p>
      <p className="text-xs text-stone-400">{content?.playing ? '장치가 재생을 확인했습니다' : paused ? '일시정지' : '재생 요청됨 · 장치 확인 대기'}</p>
      <div className="flex items-center gap-3">
        <button className="flex h-12 w-12 items-center justify-center rounded-full bg-white/10 hover:bg-white/20 disabled:opacity-40" disabled={disabled}
          aria-label={paused ? '재생' : '일시정지'} onClick={() => onUpdate({ content: { paused: !paused } })}>
          {paused ? <Play size={20} /> : <Pause size={20} />}
        </button>
        <label className="flex items-center gap-2 text-xs text-stone-300">볼륨
          <input type="range" min={0} max={100} value={volume} disabled={disabled} aria-label="볼륨" onChange={e => onUpdate({ content: { volume: Number(e.target.value) } })} />
          <span className="w-8 tabular-nums">{volume}</span>
        </label>
      </div>
      <form className="flex items-center gap-2 text-xs" onSubmit={e => { e.preventDefault(); const n = Number(seek); if (Number.isFinite(n) && n >= 0) onUpdate({ content: { position_s: n } }); }}>
        <input className="w-24 rounded border border-white/20 bg-stone-900 px-2 py-1" placeholder="초" aria-label="이동할 위치(초)" value={seek} onChange={e => setSeek(e.target.value)} />
        <button className="rounded border border-white/20 px-3 py-1 hover:bg-white/10 disabled:opacity-40" disabled={disabled}>위치 이동</button>
      </form>
      <p className="text-[11px] text-stone-500">원본 재생은 장치가 재생을 확인한 뒤에 직접 멈추세요. 이 창은 원본을 멈추지 않습니다.</p>
    </section>
  );
}
