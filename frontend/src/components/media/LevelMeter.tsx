/** Audio level meter for a stream (microphone purpose). Uses an AnalyserNode; silent when audio is unavailable. */
import { useEffect, useRef, useState } from 'react';

export function LevelMeter({ stream, label = '소리 크기' }: { stream: MediaStream | null; label?: string }) {
  const [level, setLevel] = useState(0);
  const frame = useRef<number>(0);
  useEffect(() => {
    if (!stream || !stream.getAudioTracks().length || typeof AudioContext === 'undefined') { setLevel(0); return; }
    let context: AudioContext | null = null;
    try {
      context = new AudioContext();
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (const v of data) { const d = (v - 128) / 128; sum += d * d; }
        setLevel(Math.min(1, Math.sqrt(sum / data.length) * 3));
        frame.current = requestAnimationFrame(tick);
      };
      frame.current = requestAnimationFrame(tick);
    } catch { setLevel(0); }
    return () => { cancelAnimationFrame(frame.current); void context?.close().catch(() => {}); };
  }, [stream]);
  return (
    <div className="flex w-64 items-center gap-2" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(level * 100)}>
      <div className="h-3 flex-1 overflow-hidden rounded bg-stone-800">
        <div className={`h-full transition-[width] duration-75 ${level > 0.8 ? 'bg-red-500' : level > 0.4 ? 'bg-amber-400' : 'bg-emerald-500'}`} style={{ width: `${Math.round(level * 100)}%` }} />
      </div>
      <span className="w-10 text-right text-xs text-stone-400">{Math.round(level * 100)}</span>
    </div>
  );
}
