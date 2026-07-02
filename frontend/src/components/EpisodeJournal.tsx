/**
 * EpisodeJournal — 주행기록계 (계기판)
 *
 * 지난 자율주행/시스템AI 에피소드를 한 줄씩 보여준다(요청·판단·해마점수·평가·소요).
 * 각 행의 "분석" 스위치 → 시스템 AI 창이 그 주행의 전체 로그를 받아 분석하고,
 * 거기서 곧바로 고칠 것을 명령할 수 있다(수동적 상태판 → 능동적 수리대).
 */
import { useEffect, useState, useCallback } from 'react';
import { Activity, RotateCw, Loader2, Check, AlertTriangle, Zap, Brain, Gauge, Microscope, ChevronDown, ChevronRight } from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8765';

interface EpisodeRow {
  id: number;
  started_at: string;
  agent: string | null;
  user_message: string | null;
  total_ms: number | null;
  hippocampus_score: number | null;
  unconscious_decision: string | null;
  execution_rounds: number | null;
  evaluation_result: string | null;
}

function relTime(iso: string | null): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (isNaN(t)) return '';
  const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (sec < 60) return `${sec}초 전`;
  if (sec < 3600) return `${Math.floor(sec / 60)}분 전`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}시간 전`;
  return `${Math.floor(sec / 86400)}일 전`;
}

function DecisionBadge({ d }: { d: string | null }) {
  const meta = d === 'THINK'
    ? { label: '숙고', Icon: Brain, cls: 'text-sky-700 bg-sky-50' }
    : d === 'EXECUTE'
    ? { label: '실행', Icon: Gauge, cls: 'text-amber-700 bg-amber-50' }
    : d
    ? { label: d, Icon: Zap, cls: 'text-stone-600 bg-stone-100' }
    : null;
  if (!meta) return null;
  const { Icon } = meta;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded ${meta.cls}`}>
      <Icon size={10} /> {meta.label}
    </span>
  );
}

function EvalBadge({ r }: { r: string | null }) {
  if (!r) return null;
  const achieved = r === 'ACHIEVED';
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded ${
      achieved ? 'text-emerald-700 bg-emerald-50' : 'text-red-700 bg-red-50'
    }`}>
      {achieved ? <Check size={10} /> : <AlertTriangle size={10} />}
      {achieved ? '달성' : '미달'}
    </span>
  );
}

export function EpisodeJournal() {
  const [open, setOpen] = useState(false);   // 기본 접힘 — 버튼 누르면 펼침
  const [rows, setRows] = useState<EpisodeRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  // 사용자 명령을 누르면 그 주행의 실행기억(전체 로그)을 인라인으로 펼친다. 한 번에 하나.
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [logs, setLogs] = useState<Record<number, { status: 'loading' | 'ok' | 'error'; text?: string }>>({});

  const toggleLog = useCallback((id: number) => {
    const willExpand = expandedId !== id;
    setExpandedId(willExpand ? id : null);
    // 펼치는 순간, 아직 못 받았거나 실패했던 로그만 (다시) 가져온다 — 전체 로그를 그대로 보여준다.
    if (willExpand && (!logs[id] || logs[id].status === 'error')) {
      setLogs((p) => ({ ...p, [id]: { status: 'loading' } }));
      fetch(`${API_BASE}/xray/episodes/${id}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
        .then((data) => setLogs((p) => ({ ...p, [id]: { status: 'ok', text: data.log || '' } })))
        .catch(() => setLogs((p) => ({ ...p, [id]: { status: 'error' } })));
    }
  }, [expandedId, logs]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/world-pulse/episodes?limit=20`);
      const data = await res.json();
      setRows(data.episodes || []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // 펼칠 때 첫 1회만 조회(지연 로드) — 접혀 있을 땐 호출 안 함
  useEffect(() => { if (open && rows === null) load(); }, [open, rows, load]);

  const canAnalyze = typeof window !== 'undefined' && !!window.electron?.openSystemAIWindow;
  const analyze = (id: number) => {
    // 렌더러끼리 localStorage로 전달 — 시스템 AI 창(SystemAIView)이 읽어 자동 분석.
    // 메인 프로세스를 안 거쳐서 Electron 재시작 없이 HMR로 바로 작동한다.
    try {
      localStorage.setItem('indiebiz_analyze_episode', JSON.stringify({ id, ts: Date.now() }));
    } catch { /* noop */ }
    window.electron?.openSystemAIWindow?.();
  };

  return (
    <div className="rounded-xl border border-stone-200 bg-white/70 p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <button
          onClick={() => setOpen((v) => !v)}
          className="text-sm font-semibold text-stone-700 flex items-center gap-1.5 hover:text-stone-900 transition"
          aria-expanded={open}
        >
          <Activity size={14} /> 주행기록
          <ChevronDown size={14} className={`text-stone-400 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
        {open && (
          <button
            onClick={load}
            disabled={loading}
            title="새로고침"
            className="px-2.5 py-1 rounded-lg text-xs flex items-center gap-1.5 border border-stone-200 bg-white text-stone-600 hover:bg-stone-50 disabled:opacity-50 transition"
          >
            {loading ? <Loader2 size={12} className="animate-spin" /> : <RotateCw size={12} />}
            새로고침
          </button>
        )}
      </div>

      {open && rows === null && (
        <div className="text-xs text-stone-400 flex items-center gap-1.5">
          <Loader2 size={12} className="animate-spin" /> 기록 불러오는 중…
        </div>
      )}
      {open && rows !== null && rows.length === 0 && (
        <div className="text-xs text-stone-400">아직 기록된 주행이 없습니다.</div>
      )}

      <div className={`space-y-1.5 ${open ? '' : 'hidden'}`}>
        {(rows ?? []).map((ep) => {
          const expanded = expandedId === ep.id;
          const logState = logs[ep.id];
          return (
          <div key={ep.id} className="py-1.5 border-b border-stone-100 last:border-0">
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <button
                  onClick={() => toggleLog(ep.id)}
                  title="이 주행의 실행기억(전체 로그)을 그대로 펼쳐 봅니다"
                  aria-expanded={expanded}
                  className="w-full text-left text-[13px] text-stone-700 hover:text-stone-900 flex items-center gap-1 group"
                >
                  <ChevronRight size={12} className={`shrink-0 text-stone-400 transition-transform ${expanded ? 'rotate-90' : ''}`} />
                  <span className="truncate group-hover:underline decoration-dotted underline-offset-2">{ep.user_message || '(요청 없음)'}</span>
                </button>
                <div className="flex flex-wrap items-center gap-1.5 mt-1 pl-4 text-[10px] text-stone-400">
                  <span>{relTime(ep.started_at)}</span>
                  {ep.agent && <span>· {ep.agent}</span>}
                  {ep.hippocampus_score != null && (
                    <span title="해마 연상 확신도">· 확신 {Math.round(ep.hippocampus_score * 100)}%</span>
                  )}
                  {ep.execution_rounds != null && ep.execution_rounds > 1 && (
                    <span>· {ep.execution_rounds}라운드</span>
                  )}
                  {ep.total_ms != null && <span>· {(ep.total_ms / 1000).toFixed(1)}초</span>}
                  <DecisionBadge d={ep.unconscious_decision} />
                  <EvalBadge r={ep.evaluation_result} />
                </div>
              </div>
              {canAnalyze && (
                <button
                  onClick={() => analyze(ep.id)}
                  title="이 주행을 시스템 AI로 분석 — 잘된 점·문제점·고칠 것"
                  className="shrink-0 px-2.5 py-1 rounded-lg text-[11px] flex items-center gap-1 border border-stone-200 bg-white text-stone-600 hover:bg-stone-800 hover:text-white hover:border-stone-800 transition"
                >
                  <Microscope size={12} /> 분석
                </button>
              )}
            </div>
            {expanded && (
              <div className="mt-2 ml-4 rounded-lg border border-stone-200 bg-stone-50/80 overflow-hidden">
                {(!logState || logState.status === 'loading') && (
                  <div className="px-3 py-2 text-[11px] text-stone-400 flex items-center gap-1.5">
                    <Loader2 size={12} className="animate-spin" /> 실행기억 불러오는 중…
                  </div>
                )}
                {logState?.status === 'error' && (
                  <div className="px-3 py-2 text-[11px] text-red-500">기록을 불러오지 못했습니다 (로그가 만료됐을 수 있습니다).</div>
                )}
                {logState?.status === 'ok' && (
                  <pre className="max-h-96 overflow-auto px-3 py-2 text-[11px] leading-relaxed text-stone-700 font-mono whitespace-pre-wrap break-words">{logState.text || '(로그가 비어 있습니다)'}</pre>
                )}
              </div>
            )}
          </div>
          );
        })}
      </div>
    </div>
  );
}
