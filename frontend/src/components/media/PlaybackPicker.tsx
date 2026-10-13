/** '이 장치에서 재생' picker: a local file path or a URL plus a start position → playback (content) session. */
import { useState } from 'react';
import { startPlayback } from './CallButtons';

export function PlaybackPicker({ deviceId, deviceName, onClose, onError }: {
  deviceId: string; deviceName: string; onClose: () => void; onError: (message: string) => void;
}) {
  const [mode, setMode] = useState<'path' | 'url'>('path');
  const [value, setValue] = useState('');
  const [position, setPosition] = useState('0');
  const [busy, setBusy] = useState(false);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const text = value.trim();
    if (!text) return;
    const seconds = Number(position);
    setBusy(true);
    try {
      await startPlayback(deviceId, { [mode]: text, position_s: Number.isFinite(seconds) && seconds >= 0 ? seconds : 0 });
      onClose();
    } catch (e) { onError(e instanceof Error ? e.message : '재생을 시작하지 못했습니다.'); }
    finally { setBusy(false); }
  };
  const pickFile = async () => {
    const picked = await window.electron?.selectFile?.({ title: '재생할 파일' }).catch(() => null);
    if (typeof picked === 'string' && picked) { setMode('path'); setValue(picked); }
  };
  return (
    <form onSubmit={e => void submit(e)} className="mt-1 rounded border border-stone-200 bg-stone-50 p-2 text-[11px] text-stone-600" aria-label={`${deviceName} 에서 재생`}>
      <div className="mb-1 flex items-center gap-2 font-medium">{deviceName} 에서 재생
        <button type="button" className="ml-auto text-stone-400" onClick={onClose}>닫기</button>
      </div>
      <div className="flex gap-2">
        <label className="flex items-center gap-1"><input type="radio" checked={mode === 'path'} onChange={() => setMode('path')} /> 파일 경로</label>
        <label className="flex items-center gap-1"><input type="radio" checked={mode === 'url'} onChange={() => setMode('url')} /> 주소(URL)</label>
      </div>
      <div className="mt-1 flex gap-1">
        <input className="min-w-0 flex-1 rounded border border-stone-200 px-2 py-1" value={value} onChange={e => setValue(e.target.value)}
          placeholder={mode === 'path' ? '/경로/음악.mp3' : 'https://…'} aria-label={mode === 'path' ? '파일 경로' : '주소'} />
        {mode === 'path' && window.electron?.selectFile && <button type="button" className="rounded border border-stone-200 px-2" onClick={() => void pickFile()}>찾기</button>}
      </div>
      <div className="mt-1 flex items-center gap-2">
        <label className="flex items-center gap-1">시작 위치(초)
          <input className="w-16 rounded border border-stone-200 px-1 py-0.5" value={position} onChange={e => setPosition(e.target.value)} aria-label="시작 위치(초)" />
        </label>
        <button className="ml-auto rounded bg-stone-800 px-2 py-1 text-white disabled:opacity-50" disabled={busy || !value.trim()}>{busy ? '보내는 중…' : '장치에서 재생'}</button>
      </div>
      <p className="mt-1 text-stone-400">파일은 세션 동안만 장치가 읽을 수 있는 참조로 전달됩니다. 장치가 재생을 확인하기 전에는 원본을 멈추지 않습니다.</p>
    </form>
  );
}
