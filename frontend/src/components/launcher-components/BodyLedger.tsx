/**
 * BodyLedger — 몸 원장 뷰어 (조종실 계기, 2026-08-21)
 *
 * [self:body] 어휘(changes/log/file/writes)의 통화를 사람이 읽는 표면으로 렌더한다.
 * AI 회상 통로로만 살던 몸 변화 이력을 사용자도 직접 본다 — "이 파일 왜/언제 바뀌었나".
 * LimbSwitch 와 같은 부류: 앱이 아니라 시스템의 일부라 조종실에 산다.
 * 쓸모없으면 이 컴포넌트와 ManualMode 의 한 줄만 지우면 깨끗이 사라진다(시험 설치).
 */
import { useCallback, useEffect, useState } from 'react';
import { BookOpen, ChevronDown, ChevronRight, ChevronLeft, Loader2 } from 'lucide-react';
import { api } from '../../lib/api';

const MANUAL_PROJECT_ID = '수동모드';

type Row = Record<string, string | number | undefined>;
type View = 'changes' | 'log' | 'writes';

// /ibl/execute 응답 봉투 중첩 대응 — 키 재귀 탐색 (LimbSwitch 선례)
function deepFind<T = unknown>(obj: unknown, key: string): T | undefined {
  if (!obj || typeof obj !== 'object') return undefined;
  if (key in (obj as Record<string, unknown>)) return (obj as Record<string, T>)[key];
  for (const v of Object.values(obj as Record<string, unknown>)) {
    const hit = deepFind<T>(v, key);
    if (hit !== undefined) return hit;
  }
  return undefined;
}

async function runBody(op: string, extra: Record<string, unknown> = {}) {
  const parts = Object.entries({ op, ...extra })
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}: ${typeof v === 'string' ? JSON.stringify(v) : v}`)
    .join(', ');
  const res = await api.executeIBL(`[self:body]{${parts}}`, MANUAL_PROJECT_ID);
  return {
    items: deepFind<Row[]>(res, 'items') ?? [],
    text: deepFind<string>(res, 'text') ?? '',
    message: deepFind<string>(res, 'message') ?? '',
  };
}

const VIEWS: { key: View; label: string; hint: string }[] = [
  { key: 'changes', label: '변화', hint: '파일 단위 변화 (미커밋 포함)' },
  { key: 'log', label: '커밋', hint: '커밋 단위 이력 — 무슨 일을 했나' },
  { key: 'writes', label: '쓰기', hint: '런타임 쓰기 원장 (관문 통과분 — 누가·왜)' },
];

export function BodyLedger() {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>('changes');
  const [days, setDays] = useState(7);
  const [rows, setRows] = useState<Row[]>([]);
  const [summary, setSummary] = useState('');
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // 파일 드릴 — 행의 파일을 누르면 그 파일의 일생(op:file)
  const [filePath, setFilePath] = useState<string | null>(null);
  const [fileRows, setFileRows] = useState<Row[]>([]);
  const [fileSummary, setFileSummary] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const out = await runBody(view, { days, limit: 60 });
      setRows(out.items);
      setSummary(out.text || out.message);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '몸 원장을 불러오지 못했습니다');
    } finally {
      setLoading(false);
    }
  }, [view, days]);

  useEffect(() => {
    if (open && !filePath) load();
  }, [open, filePath, load]);

  const drillFile = async (path: string) => {
    setFilePath(path);
    setLoading(true);
    setErr(null);
    try {
      const out = await runBody('file', { path, limit: 60 });
      setFileRows(out.items);
      setFileSummary(out.text || out.message);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '파일 이력을 불러오지 못했습니다');
    } finally {
      setLoading(false);
    }
  };

  const statusColor = (s: string) =>
    s === '미커밋' ? 'bg-amber-100 text-amber-700'
    : s === '추가' ? 'bg-emerald-100 text-emerald-700'
    : s === '삭제' ? 'bg-red-100 text-red-600'
    : s === '이동' ? 'bg-sky-100 text-sky-700'
    : 'bg-stone-100 text-stone-500';

  const fileCell = (r: Row) => {
    const fp = String(r['파일'] ?? '');
    if (!fp) return null;
    return (
      <button
        onClick={() => drillFile(fp)}
        className="min-w-0 truncate text-left font-mono text-[11px] text-stone-700 hover:text-blue-600 hover:underline"
        title={`${fp} — 이 파일의 일생 보기`}
      >
        {fp}
      </button>
    );
  };

  const renderRow = (r: Row, i: number) => {
    if (view === 'log' && !filePath) {
      return (
        <li key={i} className="flex items-center gap-2 rounded border border-stone-100 bg-white px-2 py-1">
          <span className="shrink-0 font-mono text-[10px] text-stone-400">{r['시각']}</span>
          <span className="min-w-0 flex-1 truncate text-stone-700" title={String(r['요지'] ?? '')}>{r['요지']}</span>
          {Number(r['파일수']) > 0 && <span className="shrink-0 text-[10px] text-stone-400">{r['파일수']}파일</span>}
          <span className="shrink-0 font-mono text-[10px] text-stone-300">{r['커밋']}</span>
        </li>
      );
    }
    if (view === 'writes' && !filePath) {
      const who = [r['행위자'], r['출처']].filter(Boolean).join(' · ');
      return (
        <li key={i} className="rounded border border-stone-100 bg-white px-2 py-1">
          <div className="flex items-center gap-2">
            <span className="shrink-0 font-mono text-[10px] text-stone-400">{String(r['시각']).slice(5, 16)}</span>
            {fileCell(r)}
            <span className="ml-auto shrink-0 text-[10px] text-stone-400" title="행위자 · 출처">{who || '(무맥락)'}</span>
          </div>
          {r['요청'] && (
            <div className="mt-0.5 truncate pl-1 text-[10px] text-stone-500" title={String(r['요청'])}>
              ↳ 요청: {r['요청']}
            </div>
          )}
        </li>
      );
    }
    // changes + 파일 일생 공용 (같은 열: 상태·파일·시각·요지)
    return (
      <li key={i} className="flex items-center gap-2 rounded border border-stone-100 bg-white px-2 py-1">
        <span className={`shrink-0 rounded px-1 py-0.5 text-[10px] font-medium ${statusColor(String(r['상태'] ?? ''))}`}>
          {r['상태']}
        </span>
        {filePath ? (
          <span className="shrink-0 font-mono text-[10px] text-stone-400">{r['시각']}</span>
        ) : (
          fileCell(r)
        )}
        <span className="min-w-0 flex-1 truncate text-[11px] text-stone-500" title={String(r['요지'] ?? '')}>{r['요지']}</span>
        {!filePath && <span className="shrink-0 font-mono text-[10px] text-stone-300">{r['시각']}</span>}
        {filePath && r['이전경로'] && (
          <span className="shrink-0 truncate font-mono text-[10px] text-sky-600" title={`이전: ${r['이전경로']}`}>
            ← {r['이전경로']}
          </span>
        )}
      </li>
    );
  };

  const shownRows = filePath ? fileRows : rows;

  return (
    <div className="rounded-lg border border-stone-200 bg-white/60 text-[12px]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-stone-600 hover:text-stone-800"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <BookOpen size={14} className="shrink-0" />
        <span className="font-medium">몸 원장</span>
        <span className="ml-auto text-[11px] text-stone-400">무엇이 · 언제 · 왜 바뀌었나</span>
      </button>

      {open && (
        <div className="border-t border-stone-100 px-3 py-2.5">
          {filePath ? (
            <div className="mb-2 flex items-center gap-2">
              <button
                onClick={() => setFilePath(null)}
                className="flex shrink-0 items-center gap-0.5 rounded border border-stone-200 px-1.5 py-0.5 text-[11px] text-stone-500 hover:text-stone-700"
              >
                <ChevronLeft size={12} /> 목록
              </button>
              <span className="min-w-0 truncate font-mono text-[11px] text-stone-700" title={filePath}>{filePath}</span>
            </div>
          ) : (
            <div className="mb-2 flex items-center gap-1.5">
              {VIEWS.map((v) => (
                <button
                  key={v.key}
                  onClick={() => setView(v.key)}
                  title={v.hint}
                  className={`rounded px-2 py-0.5 text-[11px] ${
                    view === v.key ? 'bg-stone-800 font-medium text-white' : 'text-stone-500 hover:bg-stone-100'
                  }`}
                >
                  {v.label}
                </button>
              ))}
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                className="ml-auto rounded border border-stone-200 px-1 py-0.5 text-[11px] text-stone-500 outline-none"
                title="회상 기간"
              >
                <option value={7}>7일</option>
                <option value={30}>30일</option>
                <option value={90}>90일</option>
              </select>
            </div>
          )}

          {err && <div className="mb-2 rounded bg-red-50 px-2 py-1 text-[11px] text-red-600">{err}</div>}

          {loading ? (
            <div className="flex items-center gap-1.5 py-2 text-stone-400">
              <Loader2 size={13} className="animate-spin" /> 원장을 읽는 중…
            </div>
          ) : (
            <>
              {(filePath ? fileSummary : summary) && (
                <p className="mb-1.5 text-[11px] leading-relaxed text-stone-400">
                  {filePath ? fileSummary : summary}
                </p>
              )}
              {shownRows.length === 0 ? (
                <div className="py-1.5 text-[11px] text-stone-400">이 기간엔 기록이 없습니다.</div>
              ) : (
                <ul className="flex max-h-64 flex-col gap-1 overflow-y-auto pr-0.5">
                  {shownRows.map(renderRow)}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
