/**
 * RadioInstrument — 라디오 "계기(instrument)" (앱 모드)
 *
 * 브라우즈는 sense, 재생은 limbs(mpv가 이 PC에서 재생 — HLS 포함). 앱은 리모컨이다.
 *   한국    [sense:korean_radio]{broadcaster?}  → [limbs:radio]{op:play, station_id}
 *   검색    [sense:search_radio]{query}         → [limbs:radio]{op:play, stream_url}
 *   즐겨찾기 [limbs:radio_favorite]{op:list|add|remove}
 *   상태/정지/볼륨  [limbs:player_status] / [limbs:radio]{op:stop} / [limbs:volume]{volume}
 *
 * 스키마 출처: data/ibl_nodes_src/sense.yaml(media), limbs.yaml(media), radio/handler.py
 */
import { useEffect, useRef, useState, useCallback } from 'react';

const IBL_ENDPOINT = 'http://127.0.0.1:8765/ibl/execute';
const PROJECT_ID = '앱모드';

type Tab = 'korean' | 'search' | 'favorite';

interface KStation { station_id: string; name: string; broadcaster?: string; description?: string }
interface GStation { name: string; country?: string; language?: string; tags?: string; codec?: string; bitrate?: number; stream_url: string }
interface Favorite { name: string; stream_url?: string; station_id?: string; added_at?: string }
interface Status { success?: boolean; playing?: boolean; station?: string; station_id?: string; volume?: number; duration?: string; message?: string }

const BROADCASTERS = ['KBS', 'MBC', 'SBS', 'TBS', 'CBS', 'EBS'];
const GENRES = ['kpop', 'jazz', 'classical', 'news', 'lofi', 'rock', 'pop'];

async function runIBL<T = Record<string, unknown>>(code: string): Promise<T & { success?: boolean; error?: string }> {
  try {
    const res = await fetch(IBL_ENDPOINT, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, project_id: PROJECT_ID }),
    });
    return await res.json();
  } catch {
    return { success: false, error: '서버에 연결할 수 없습니다.' } as T & { success?: boolean; error?: string };
  }
}
const esc = (s: string) => s.replace(/"/g, '');

export function RadioInstrument() {
  const [tab, setTab] = useState<Tab>('korean');
  const [broadcaster, setBroadcaster] = useState('');     // '' = 전체
  const [korean, setKorean] = useState<KStation[] | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<GStation[] | null>(null);
  const [favorites, setFavorites] = useState<Favorite[] | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [volume, setVolume] = useState(70);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false); // 재생/정지 중복 클릭 방지

  // ----- 상태 폴링 (재생 바) -----
  const refreshStatus = useCallback(async () => {
    const s = await runIBL<Status>('[limbs:player_status]{}');
    setStatus(s);
    if (s.playing && typeof s.volume === 'number') setVolume(s.volume);
  }, []);
  useEffect(() => {
    refreshStatus();
    const id = setInterval(refreshStatus, 4000);
    return () => clearInterval(id);
  }, [refreshStatus]);

  // ----- 로더 -----
  const loadKorean = useCallback(async (bc: string) => {
    setLoading(true); setError(null); setKorean(null);
    const r = await runIBL<{ stations?: KStation[] }>(`[sense:korean_radio]{${bc ? `broadcaster: "${bc}"` : ''}}`);
    setLoading(false);
    if (r.error) setError(r.error); else setKorean(r.stations || []);
  }, []);

  const loadSearch = useCallback(async (q: string) => {
    if (!q.trim()) return;
    setLoading(true); setError(null); setResults(null);
    const r = await runIBL<{ stations?: GStation[] }>(`[sense:search_radio]{query: "${esc(q.trim())}", limit: 30}`);
    setLoading(false);
    if (r.error) setError(r.error); else setResults(r.stations || []);
  }, []);

  const loadFavorites = useCallback(async () => {
    setLoading(true); setError(null); setFavorites(null);
    const r = await runIBL<{ favorites?: Favorite[] }>('[limbs:radio_favorite]{op: "list"}');
    setLoading(false);
    if (r.error) setError(r.error); else setFavorites(r.favorites || []);
  }, []);

  // 탭 진입 시 로드
  useEffect(() => {
    if (tab === 'korean' && !korean) loadKorean(broadcaster);
    if (tab === 'favorite') loadFavorites();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  // ----- 컨트롤 (실제 PC에서 mpv 재생) -----
  const play = useCallback(async (params: string) => {
    setBusy(true); setError(null);
    const r = await runIBL(`[limbs:radio]{op: "play", ${params}, volume: ${volume}}`);
    setBusy(false);
    if (r.success === false) setError(r.error || '재생에 실패했습니다.');
    setTimeout(refreshStatus, 900);
  }, [volume, refreshStatus]);

  const stop = useCallback(async () => {
    setBusy(true);
    await runIBL('[limbs:radio]{op: "stop"}');
    setBusy(false);
    setTimeout(refreshStatus, 400);
  }, [refreshStatus]);

  const commitVolume = useCallback(async (v: number) => {
    if (!status?.playing) return;
    await runIBL(`[limbs:volume]{volume: ${v}}`);
    setTimeout(refreshStatus, 600);
  }, [status?.playing, refreshStatus]);

  const addFavorite = useCallback(async () => {
    await runIBL('[limbs:radio_favorite]{op: "add"}'); // 현재 재생 채널 자동 등록
    if (tab === 'favorite') loadFavorites();
  }, [tab, loadFavorites]);

  const removeFavorite = useCallback(async (name: string) => {
    await runIBL(`[limbs:radio_favorite]{op: "remove", name: "${esc(name)}"}`);
    loadFavorites();
  }, [loadFavorites]);

  const pickBroadcaster = (bc: string) => { setBroadcaster(bc); loadKorean(bc); };

  return (
    <div className="h-full flex flex-col bg-[#FAFAF8] text-stone-800">
      {/* 탭 */}
      <div className="shrink-0 flex gap-1 px-5 pt-4">
        {([['korean', '한국'], ['search', '검색'], ['favorite', '즐겨찾기']] as [Tab, string][]).map(([t, label]) => (
          <button key={t} onClick={() => { setTab(t); setError(null); }}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition ${
              tab === t ? 'bg-stone-800 text-white' : 'bg-white text-stone-500 border border-stone-200 hover:bg-stone-50'
            }`}>
            {label}
          </button>
        ))}
      </div>

      {/* 필터/검색 */}
      <div className="shrink-0 px-5 pt-3 pb-2">
        {tab === 'korean' && (
          <div className="flex flex-wrap gap-1.5">
            <Chip label="전체" active={broadcaster === ''} onClick={() => pickBroadcaster('')} />
            {BROADCASTERS.map((b) => <Chip key={b} label={b} active={broadcaster === b} onClick={() => pickBroadcaster(b)} />)}
          </div>
        )}
        {tab === 'search' && (
          <>
            <div className="flex gap-2">
              <input value={query} onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadSearch(query)}
                placeholder="장르·방송국·키워드 (예: jazz, lofi, classical)"
                className="flex-1 px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
              <button onClick={() => loadSearch(query)}
                className="px-4 py-2 rounded-xl bg-stone-800 text-white text-sm hover:bg-stone-700">검색</button>
            </div>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {GENRES.map((g) => <Chip key={g} label={g} active={false} onClick={() => { setQuery(g); loadSearch(g); }} />)}
            </div>
          </>
        )}
      </div>

      {/* 본문 */}
      <div className="flex-1 min-h-0 overflow-auto px-5 pb-4">
        {loading && <div className="py-10 text-center text-stone-400 text-sm">불러오는 중…</div>}
        {error && !loading && <div className="py-4 text-center text-rose-500 text-sm">{error}</div>}

        <div className="max-w-2xl mx-auto space-y-1.5">
          {tab === 'korean' && korean && !loading && korean.map((s) => (
            <StationRow key={s.station_id} title={s.name} sub={`${s.broadcaster || ''}${s.description ? ' · ' + s.description : ''}`}
              active={status?.playing === true && status.station === s.name}
              onPlay={() => play(`station_id: "${esc(s.station_id)}"`)} busy={busy} />
          ))}

          {tab === 'search' && results && !loading && (
            results.length === 0 ? <Empty /> : results.map((s, i) => (
              <StationRow key={`${s.name}-${i}`} title={s.name}
                sub={[s.country, s.tags, s.bitrate ? `${s.bitrate}kbps` : ''].filter(Boolean).join(' · ')}
                active={status?.playing === true && status.station === s.name}
                onPlay={() => play(`stream_url: "${esc(s.stream_url)}", name: "${esc(s.name)}"`)} busy={busy} />
            ))
          )}

          {tab === 'favorite' && favorites && !loading && (
            favorites.length === 0 ? <div className="py-12 text-center text-stone-400 text-sm">즐겨찾기가 없습니다. 재생 중 ♡ 를 누르면 추가됩니다.</div>
              : favorites.map((f, i) => (
                <StationRow key={`${f.name}-${i}`} title={f.name} sub={f.added_at}
                  active={status?.playing === true && status.station === f.name}
                  onPlay={() => play(f.station_id ? `station_id: "${esc(f.station_id)}"` : `stream_url: "${esc(f.stream_url || '')}", name: "${esc(f.name)}"`)}
                  onRemove={() => removeFavorite(f.name)} busy={busy} />
              ))
          )}
        </div>
      </div>

      {/* 재생 바 (now playing) */}
      {status?.playing && (
        <div className="shrink-0 border-t border-stone-200 bg-white px-5 py-3 flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-rose-500 animate-pulse shrink-0" />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium truncate">{status.station}</div>
            <div className="text-[11px] text-stone-400">재생 중 · {status.duration}</div>
          </div>
          <button onClick={addFavorite} title="즐겨찾기 추가"
            className="px-2 py-1 rounded-lg text-stone-400 hover:bg-stone-100 hover:text-rose-500">♡</button>
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-stone-400">🔊</span>
            <input type="range" min={0} max={100} value={volume}
              onChange={(e) => setVolume(Number(e.target.value))}
              onMouseUp={(e) => commitVolume(Number((e.target as HTMLInputElement).value))}
              onTouchEnd={(e) => commitVolume(Number((e.target as HTMLInputElement).value))}
              className="w-24 accent-stone-700" />
          </div>
          <button onClick={stop} disabled={busy}
            className="px-3 py-1.5 rounded-lg bg-stone-800 text-white text-sm hover:bg-stone-700 disabled:opacity-50">정지</button>
        </div>
      )}
    </div>
  );
}

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`px-2.5 py-1 rounded-full text-xs border ${
        active ? 'bg-stone-800 text-white border-stone-800' : 'bg-white border-stone-200 text-stone-600 hover:bg-stone-50'
      }`}>
      {label}
    </button>
  );
}

function StationRow({ title, sub, active, onPlay, onRemove, busy }: {
  title: string; sub?: string; active?: boolean; onPlay: () => void; onRemove?: () => void; busy?: boolean;
}) {
  return (
    <div className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl border ${active ? 'border-rose-300 bg-rose-50/40' : 'border-stone-200 bg-white'}`}>
      <button onClick={onPlay} disabled={busy} title="재생"
        className="shrink-0 w-8 h-8 rounded-full bg-stone-800 text-white flex items-center justify-center hover:bg-stone-700 disabled:opacity-50">
        {active ? '♪' : '▶'}
      </button>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium truncate">{title}</div>
        {sub && <div className="text-[11px] text-stone-400 truncate">{sub}</div>}
      </div>
      {onRemove && (
        <button onClick={onRemove} title="삭제" className="shrink-0 text-stone-300 hover:text-rose-500 text-sm">✕</button>
      )}
    </div>
  );
}

function Empty() {
  return <div className="py-12 text-center text-stone-400 text-sm">검색 결과가 없습니다.</div>;
}
