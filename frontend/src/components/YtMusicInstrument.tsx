/**
 * YtMusicInstrument — 유튜브 뮤직 "계기(instrument)" (앱 모드)
 *
 * 두 기능 (둘 다 [limbs:music] op 분기 — yt-dlp + mpv가 이 PC에서 처리):
 *   재생  [sense:search_youtube]{query} 로 검색 → 선택해서 큐에 넣고 재생
 *         play/add/skip/stop/queue. (에이전트가 주문대로 틀던 걸 사람이 직접 고르는 형태)
 *   저장  [limbs:music]{op:download, url, name} → ~/Desktop/{이름}.mp3 로 추출
 *
 * 스키마 출처: data/ibl_nodes_src/sense.yaml(search_youtube), limbs.yaml(music), youtube/handler.py
 */
import { useEffect, useState, useCallback } from 'react';

const IBL_ENDPOINT = 'http://127.0.0.1:8765/ibl/execute';
const PROJECT_ID = '앱모드';

type Tab = 'play' | 'save';

interface Video { video_id: string; title: string; channel?: string; duration?: string }
interface NowPlaying { video_id?: string; title?: string }
interface QueueItem { position: number; video_id: string; title: string; channel?: string; duration?: string }
interface QueueResult { success?: boolean; now_playing?: NowPlaying | null; queue?: QueueItem[]; message?: string }
interface DlResult { success?: boolean; message?: string; error?: string; file?: string; path?: string; filename?: string }

const watchUrl = (id: string) => `https://www.youtube.com/watch?v=${id}`;
// 파일명에 부적합한 문자 제거
const safeName = (s: string) => s.replace(/[\\/:*?"<>|]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 80);

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

export function YtMusicInstrument() {
  const [tab, setTab] = useState<Tab>('play');

  // 재생
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Video[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [queue, setQueue] = useState<QueueResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 저장
  const [dlUrl, setDlUrl] = useState('');
  const [dlName, setDlName] = useState('');
  const [dlLoading, setDlLoading] = useState(false);
  const [dlResult, setDlResult] = useState<DlResult | null>(null);

  // ----- 큐 폴링 -----
  const refreshQueue = useCallback(async () => {
    const q = await runIBL<QueueResult>('[limbs:music]{op: "queue"}');
    setQueue(q);
  }, []);
  useEffect(() => {
    if (tab !== 'play') return;
    refreshQueue();
    const id = setInterval(refreshQueue, 4000);
    return () => clearInterval(id);
  }, [tab, refreshQueue]);

  // ----- 검색 -----
  const search = useCallback(async () => {
    const q = query.trim();
    if (!q) return;
    setSearching(true); setError(null); setResults(null);
    // search_youtube 는 단일통화 이행 후 결과를 `items` 로 반환한다(옛 `results` 아님 — 2026-06-28 수정).
    const r = await runIBL<{ items?: Video[] }>(`[sense:search_youtube]{query: "${esc(q)}", count: 15}`);
    setSearching(false);
    if (r.error) setError(r.error); else setResults(r.items || []);
  }, [query]);

  // ----- 재생 컨트롤 (mpv가 이 PC에서 재생) -----
  const ctrl = useCallback(async (code: string) => {
    setBusy(true); setError(null);
    const r = await runIBL(code);
    setBusy(false);
    if (r.success === false) setError(r.error || (r as { message?: string }).message || '작업에 실패했습니다.');
    setTimeout(refreshQueue, 900);
  }, [refreshQueue]);

  const playNow = (v: Video) => ctrl(`[limbs:music]{op: "play", query: "${watchUrl(v.video_id)}"}`);
  const addQueue = (v: Video) => ctrl(`[limbs:music]{op: "add", query: "${watchUrl(v.video_id)}"}`);

  // 검색 결과 → 저장 탭으로 보내기 (URL/이름 채움)
  const toSave = (v: Video) => { setDlUrl(watchUrl(v.video_id)); setDlName(safeName(v.title)); setDlResult(null); setTab('save'); };

  // ----- 저장 (mp3 다운로드) -----
  const download = useCallback(async () => {
    const url = dlUrl.trim(), name = dlName.trim();
    if (!url) { setDlResult({ success: false, error: 'URL을 입력하세요.' }); return; }
    setDlLoading(true); setDlResult(null);
    const r = await runIBL<DlResult>(`[limbs:music]{op: "download", url: "${esc(url)}"${name ? `, name: "${esc(name)}"` : ''}}`);
    setDlLoading(false);
    setDlResult(r);
  }, [dlUrl, dlName]);

  const now = queue?.now_playing;
  const list = queue?.queue || [];

  return (
    <div className="h-full flex flex-col bg-[#FAFAF8] text-stone-800">
      {/* 탭 */}
      <div className="shrink-0 flex gap-1 px-5 pt-4">
        {([['play', '재생'], ['save', '저장']] as [Tab, string][]).map(([t, label]) => (
          <button key={t} onClick={() => { setTab(t); setError(null); }}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition ${
              tab === t ? 'bg-stone-800 text-white' : 'bg-white text-stone-500 border border-stone-200 hover:bg-stone-50'
            }`}>
            {label}
          </button>
        ))}
      </div>

      {/* ===== 재생 ===== */}
      {tab === 'play' && (
        <>
          <div className="shrink-0 px-5 pt-3 pb-2 flex gap-2">
            <input value={query} onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.nativeEvent.isComposing && search()}
              placeholder="노래·아티스트 검색 (예: newjeans, 아이유 밤편지)"
              className="flex-1 px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
            <button onClick={search}
              className="px-4 py-2 rounded-xl bg-stone-800 text-white text-sm hover:bg-stone-700">검색</button>
          </div>

          <div className="flex-1 min-h-0 overflow-auto px-5 pb-4">
            {searching && <div className="py-10 text-center text-stone-400 text-sm">검색 중…</div>}
            {error && !searching && <div className="py-3 text-center text-rose-500 text-sm">{error}</div>}
            <div className="max-w-2xl mx-auto space-y-1.5">
              {results && results.map((v) => (
                <div key={v.video_id} className="flex items-center gap-3 px-4 py-2.5 rounded-xl bg-white border border-stone-200">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium truncate">{v.title}</div>
                    <div className="text-[11px] text-stone-400 truncate">{[v.channel, v.duration].filter(Boolean).join(' · ')}</div>
                  </div>
                  <button onClick={() => playNow(v)} disabled={busy} title="바로 재생"
                    className="shrink-0 w-8 h-8 rounded-full bg-stone-800 text-white flex items-center justify-center hover:bg-stone-700 disabled:opacity-50">▶</button>
                  <button onClick={() => addQueue(v)} disabled={busy} title="큐에 추가"
                    className="shrink-0 w-8 h-8 rounded-full bg-white border border-stone-300 text-stone-600 flex items-center justify-center hover:bg-stone-50 disabled:opacity-50">＋</button>
                  <button onClick={() => toSave(v)} title="MP3로 저장"
                    className="shrink-0 px-2 h-8 rounded-lg text-xs text-stone-400 hover:bg-stone-100 hover:text-stone-700">저장</button>
                </div>
              ))}
              {results && results.length === 0 && !searching && (
                <div className="py-12 text-center text-stone-400 text-sm">검색 결과가 없습니다.</div>
              )}
              {!results && !searching && (
                <div className="py-12 text-center text-stone-400 text-sm">노래를 검색해 ▶ 재생하거나 ＋ 큐에 담아보세요.</div>
              )}
            </div>
          </div>

          {/* 재생 바 + 큐 */}
          {(now || list.length > 0) && (
            <div className="shrink-0 border-t border-stone-200 bg-white px-5 py-3">
              <div className="flex items-center gap-3">
                <div className="w-2 h-2 rounded-full bg-rose-500 animate-pulse shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">{now?.title || '재생 대기'}</div>
                  <div className="text-[11px] text-stone-400">대기열 {list.length}곡</div>
                </div>
                <button onClick={() => ctrl('[limbs:music]{op: "skip"}')} disabled={busy}
                  className="px-3 py-1.5 rounded-lg bg-white border border-stone-300 text-stone-600 text-sm hover:bg-stone-50 disabled:opacity-50">스킵 ⏭</button>
                <button onClick={() => ctrl('[limbs:music]{op: "stop"}')} disabled={busy}
                  className="px-3 py-1.5 rounded-lg bg-stone-800 text-white text-sm hover:bg-stone-700 disabled:opacity-50">정지</button>
              </div>
              {list.length > 0 && (
                <div className="mt-2 max-h-28 overflow-auto space-y-1">
                  {list.map((q) => (
                    <div key={q.position} className="flex items-center gap-2 text-xs text-stone-500">
                      <span className="text-stone-300 w-4 text-right">{q.position}</span>
                      <span className="truncate flex-1">{q.title}</span>
                      <span className="text-stone-300">{q.duration}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* ===== 저장 ===== */}
      {tab === 'save' && (
        <div className="flex-1 min-h-0 overflow-auto px-5 pt-3 pb-6">
          <div className="max-w-xl mx-auto space-y-3">
            <div>
              <label className="text-xs text-stone-500">유튜브 주소 (URL)</label>
              <input value={dlUrl} onChange={(e) => setDlUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
                className="mt-1 w-full px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
            </div>
            <div>
              <label className="text-xs text-stone-500">파일 이름 (비우면 자동)</label>
              <input value={dlName} onChange={(e) => setDlName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !e.nativeEvent.isComposing && download()}
                placeholder="예: 아이유 - 밤편지"
                className="mt-1 w-full px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
            </div>
            <button onClick={download} disabled={dlLoading || !dlUrl.trim()}
              className="w-full py-2.5 rounded-xl bg-stone-800 text-white text-sm hover:bg-stone-700 disabled:opacity-50">
              {dlLoading ? '다운로드 중… (수십 초 걸릴 수 있어요)' : 'MP3로 저장'}
            </button>
            <p className="text-[11px] text-stone-400">바탕화면(~/Desktop)에 <code>{dlName ? safeName(dlName) : '파일이름'}.mp3</code> 로 저장됩니다.</p>

            {dlResult && (
              <div className={`rounded-xl border px-4 py-3 text-sm ${dlResult.success ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-rose-200 bg-rose-50 text-rose-600'}`}>
                {dlResult.success ? '✅ 저장 완료' : '⚠️ 저장 실패'}
                <div className="text-xs mt-1 text-stone-500 break-all">
                  {dlResult.file || dlResult.path || dlResult.filename || dlResult.message || dlResult.error}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
