/**
 * SystemLogViewer — 시스템 로그 뷰어 (조종실 계기, 2026-08-05 시작방식 개편)
 *
 * 아이콘 실행(터미널 없음)에서 잃어버리는 stdout — 부팅 에러·백그라운드 서비스
 * (폴러·펄스)·비에이전트 표면의 500 traceback — 를 보는 창구. 에피소드 메모리는
 * 에이전트 런만 담으므로 이 뷰어가 그 사각을 메운다. 백엔드 /config/system-logs
 * (화이트리스트 tail)를 읽는다. 시스템 컨트롤(모델 기어·손발 스위치)과 같은 자리.
 */
import { useCallback, useEffect, useState } from 'react';
import { ScrollText, Loader2, RotateCw, ChevronDown, ChevronRight } from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8765';

const FILES: { key: string; label: string }[] = [
  { key: 'runtime', label: '백엔드' },
  { key: 'keeper', label: 'keeper' },
  { key: 'tunnel', label: '터널' },
  { key: 'electron', label: 'Electron' },
];

export function SystemLogViewer() {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState('runtime');
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [rows, setRows] = useState<string[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/system-logs?file=${file}&lines=300&errors_only=${errorsOnly}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRows(Array.isArray(data.lines) ? data.lines : []);
      setNote(data.note || null);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '로그를 불러오지 못했습니다');
    } finally {
      setLoading(false);
    }
  }, [file, errorsOnly]);

  useEffect(() => { if (open) load(); }, [open, load]);

  return (
    <div className="rounded-lg border border-stone-200 bg-white/60 text-[12px]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-stone-600 hover:text-stone-800"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <ScrollText size={14} className="shrink-0" />
        <span className="font-medium">시스템 로그</span>
        <span className="ml-auto text-[11px] text-stone-400">부팅·백그라운드 에러 확인</span>
      </button>

      {open && (
        <div className="border-t border-stone-100 px-3 py-2.5">
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            {FILES.map((f) => (
              <button
                key={f.key}
                onClick={() => setFile(f.key)}
                className={`rounded px-2 py-1 text-[11px] border transition ${
                  file === f.key
                    ? 'bg-stone-800 text-white border-stone-800'
                    : 'bg-white/70 border-stone-200 text-stone-600 hover:bg-white'
                }`}
              >
                {f.label}
              </button>
            ))}
            <label className="ml-1 flex items-center gap-1 text-[11px] text-stone-500">
              <input
                type="checkbox"
                checked={errorsOnly}
                onChange={(e) => setErrorsOnly(e.target.checked)}
              />
              에러만
            </label>
            <button
              onClick={load}
              className="ml-auto flex items-center gap-1 rounded border border-stone-200 bg-white/70 px-2 py-1 text-[11px] text-stone-600 hover:bg-white"
            >
              {loading ? <Loader2 size={11} className="animate-spin" /> : <RotateCw size={11} />}
              새로고침
            </button>
          </div>

          {err && <div className="mb-1 text-[11px] text-red-500">{err}</div>}
          {note && <div className="mb-1 text-[11px] text-stone-400">{note}</div>}

          <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all rounded bg-stone-900 px-2.5 py-2 font-mono text-[10.5px] leading-relaxed text-stone-200">
            {rows.length > 0 ? rows.join('\n') : (loading ? '불러오는 중…' : '(비어 있음)')}
          </pre>
        </div>
      )}
    </div>
  );
}
