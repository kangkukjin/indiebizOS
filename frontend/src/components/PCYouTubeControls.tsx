import { useEffect, useRef, useState } from 'react';
import { searchPCVideos, type PCAction, type PCState, type PCVideo } from '../lib/pc-control';

const button = 'rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm disabled:opacity-40 disabled:cursor-not-allowed';

export function PCYouTubeControls({ target, disabled, state, onCommand }: {
  target: string; disabled: boolean; state: PCState | null;
  onCommand: (action: PCAction, args?: Record<string, unknown>) => void;
}) {
  const [query, setQuery] = useState('');
  const [videos, setVideos] = useState<PCVideo[]>([]);
  const [selected, setSelected] = useState('');
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');
  const version = useRef(0);
  useEffect(() => { version.current++; setVideos([]); setSelected(''); setError(''); setSearching(false); }, [target]);
  useEffect(() => () => { version.current++; }, []);
  const search = async () => {
    if (!query.trim() || searching) return;
    const current = ++version.current;
    setSearching(true); setError(''); setVideos([]); setSelected('');
    try {
      const rows = await searchPCVideos(query.trim());
      if (current !== version.current) return;
      setVideos(rows); setSelected(rows[0]?.url || '');
      if (!rows.length) setError('길이를 확인할 수 있는 일반 영상을 찾지 못했습니다. 생방송은 지원하지 않습니다.');
    } catch (e) { if (current === version.current) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (current === version.current) setSearching(false); }
  };
  const video = videos.find(v => v.url === selected);
  const playback = state?.action.startsWith('youtube_') ? state.playback ? [state.playback] : state.tabs || [] : [];
  return <section className="rounded-2xl border border-stone-200 bg-white p-5 space-y-4">
    <h2 className="font-medium">유튜브 재생 교체</h2>
    <p className="text-xs text-stone-500">열린 Chrome·Edge·Brave의 유튜브 탭을 재사용합니다. 다른 유튜브 재생을 멈추고 광고가 끝난 본영상의 재생 진행을 확인합니다. 처음에는 PC에서 유튜브 탭을 한 번 열어 주세요.</p>
    <div className="flex gap-2"><input aria-label="유튜브 검색어" value={query} onChange={e => setQuery(e.target.value)}
      placeholder="비 오는 날 듣는 인디음악" className="flex-1 min-w-0 rounded-xl border border-stone-200 p-3 text-sm" />
      <button className={button} disabled={disabled || searching || !query.trim()} onClick={() => void search()}>{searching ? '검색 중…' : '검색'}</button></div>
    {videos.length > 0 && <select aria-label="교체할 유튜브 영상" value={selected} disabled={disabled} onChange={e => setSelected(e.target.value)} className="w-full rounded-xl border border-stone-200 p-3 text-sm">
      {videos.map(v => <option key={v.url} value={v.url}>{v.title}</option>)}
    </select>}
    <div className="flex flex-wrap gap-2">
      <button className={button} disabled={disabled || !video} onClick={() => video && onCommand('youtube_replace', { ...video, fullscreen: true })}>기존 재생 교체</button>
      <button className={button} disabled={disabled} onClick={() => onCommand('youtube_status')}>재생 상태</button>
      <button className={button} disabled={disabled} onClick={() => onCommand('youtube_stop')}>유튜브 정지</button>
    </div>
    {playback.map((p, i) => <p key={i} className="text-sm text-stone-600">{p.title || '유튜브'} · {p.ad ? '광고' : p.state === 'playing' ? '재생 표시' : p.state === 'paused' ? '일시정지' : '상태 미확인'} · {Math.floor(p.position || 0)} / {Math.floor(p.duration || 0)}초</p>)}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    <p className="text-xs text-stone-500">검사 중 브라우저 창·선택 탭·마우스 위치가 바뀝니다. 광고·로딩 때문에 최대 약 2분이 걸릴 수 있으며, 실패하면 새 탭을 추가하지 않습니다.</p>
  </section>;
}
