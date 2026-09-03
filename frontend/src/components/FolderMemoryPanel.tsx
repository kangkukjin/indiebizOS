/**
 * FolderMemoryPanel — 시스템 창(탐색 표면)의 "🧠 기억" 판: 지금 보고 있는 폴더의 포식 기억 **문서**.
 *
 * 정본은 문서 하나다(2026-09-03 사용자 판정 "단언이라는 개념은 없어진 것 — 포식 기억 파일만 있다").
 * 단언은 문서의 `## 단언` 절에 사는 줄들이고 DB 는 그 절의 색인일 뿐이므로, 판은 문서만 보여준다:
 *   보기·고치기 = [self:forage]{op:recall, locus} 가 주는 doc(자기 노드 → 조상) 을 [self:read] → 편집 → [self:write] >> [self:forage]{op:sync}
 *   만들기·갱신 = [others:delegate]{scope:system} "가이드 폴더 조사대로" — 관측·판단은 AI 몫
 *   위계        = recall 의 docs_below(더 자세한 하위 문서) · 자기 노드 문서가 없으면 덮는 상위 문서를 보는 중이라고 말한다
 *   사진        = /photo/scan/check — 사진 관리 스캔이 이 폴더를 덮으면 그 사실
 * 능력은 전부 어휘, 이 컴포넌트는 표현만(철칙 0).
 */
import { useCallback, useEffect, useState } from 'react';
import { iblExecuteApp } from '../lib/instrument';

type PhotoScan = { exists: boolean; photo_count?: number; video_count?: number; last_scan?: string | null };
type Recall = { doc?: string | null; docs_below?: string[]; map_count?: number } | null;

const getApiUrl = async () => {
  if (window.electron?.getApiPort) return `http://127.0.0.1:${await window.electron.getApiPort()}`;
  return 'http://127.0.0.1:8765';
};
const q = (s: string) => JSON.stringify(s);
const baseName = (p: string) => p.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || p;
const relDoc = (p: string) => p.replace(/^.*forage_surveys\//, '');
/** 문서 경로에서 그 문서가 덮는 폴더(뿌리) — `<몸>/<경로>/memory.md` 의 경로 부분 */
const docRoot = (p: string) => {
  const parts = relDoc(p).replace(/\/memory\.md$/, '').split('/');
  return parts.length > 1 ? '/' + parts.slice(1).join('/') : parts[0];
};

export function FolderMemoryPanel({ path }: { path: string }) {
  const [docPath, setDocPath] = useState<string | null>(null);
  const [docText, setDocText] = useState('');
  const [docDirty, setDocDirty] = useState(false);
  const [docsBelow, setDocsBelow] = useState<string[]>([]);
  const [photo, setPhoto] = useState<PhotoScan | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [hint, setHint] = useState('');
  const [quickKind, setQuickKind] = useState('identity');
  const [quickLine, setQuickLine] = useState('');

  const load = useCallback(async () => {
    if (!path) return;
    setBusy('불러오는 중'); setMsg(null); setDocDirty(false);
    try {
      const r = (await iblExecuteApp(`[self:forage]{op: "recall", locus: ${q(path)}, limit: 1}`)) as Recall;
      const doc = r?.doc ?? null;
      setDocPath(doc);
      setDocsBelow(r?.docs_below ?? []);
      if (doc) {
        const t = (await iblExecuteApp(`[self:read]{path: ${q(doc)}}`)) as { result?: unknown } | string | null;
        setDocText(typeof t === 'string' ? t : String((t as { result?: unknown })?.result ?? ''));
      } else setDocText('');
      try {
        const api = await getApiUrl();
        const pr = await fetch(`${api}/photo/scan/check?path=${encodeURIComponent(path)}`);
        setPhoto(pr.ok ? await pr.json() : null);
      } catch { setPhoto(null); }
    } catch (e) {
      setMsg(`불러오기 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally { setBusy(null); }
  }, [path]);

  useEffect(() => { load().catch(() => {}); }, [load]);

  const run = async (label: string, code: string, after?: () => Promise<void> | void) => {
    setBusy(label); setMsg(null);
    try {
      const r = (await iblExecuteApp(code)) as { success?: boolean; error?: string; message?: string } | null;
      if (r && r.success === false) setMsg(r.error || r.message || `${label} 실패`);
      else setMsg(`${label} 완료`);
      if (after) await after();
    } catch (e) { setMsg(`${label} 실패: ${e instanceof Error ? e.message : String(e)}`); }
    finally { setBusy(null); }
  };

  const ownNode = !!docPath && docRoot(docPath).replace(/\/+$/, '') === path.replace(/\/+$/, '');

  const saveDoc = () => {
    if (!docPath) return;
    // 문서가 정본 — 저장 뒤 `## 단언` 절을 색인에 맞추고(sync) 다시 읽는다
    run('문서 저장', `[self:write]{path: ${q(docPath)}, content: ${q(docText)}} >> [self:forage]{op: "sync", locus: ${q(path)}}`, async () => { setDocDirty(false); await load(); });
  };

  const build = () => {
    const has = ownNode;
    if (!confirm(has ? 'AI 가 이 폴더를 다시 살펴 기억 문서를 갱신합니다(차이만, 당신이 고친 줄은 보존). 진행할까요?' : 'AI 가 이 폴더를 살펴보고 포식 기억 문서를 만듭니다. 시간이 걸릴 수 있습니다. 진행할까요?')) return;
    const message = `폴더 조사: ${path} 의 포식 기억을 ${has ? '갱신해라(차이만)' : '만들어라'}. 먼저 read_guide 로 가이드 폴더 조사(folder_survey)를 읽고 그대로 한다 — 루트 단언은 territory 로 적어 이 폴더 자기 노드에 문서가 생기게 하고, 그 문서에 산문을 채운다. 이미 문서가 있으면 주인이 고친 줄은 보존한다.${hint.trim() ? ' 주인의 말: ' + hint.trim() : ''}`;
    run('AI 에게 맡기기', `[others:delegate]{scope: "system", message: ${q(message)}, from_agent: "시스템 창 기억판"}`);
  };

  /** 빠른 추가 — 문서의 `## 단언` 절, 이 폴더 heading 아래에 한 줄을 끼워 넣는다(저장은 사용자가). 문서가 정본이므로 문서 텍스트만 고친다. */
  const quickAdd = () => {
    const line = quickLine.trim();
    if (!line || !docPath) return;
    const heading = `### ${path.replace(/\/+$/, '')}`;
    const newLine = `- [${quickKind}] ${line} ‹0.95 · ${new Date().toISOString().slice(0, 10)} · 주인 선언›`;
    let text = docText;
    if (!text.includes('## 단언')) text = text.replace(/(\n## 갱신 기록)|$/, `\n\n## 단언\n${heading}\n${newLine}\n$1`);
    else if (text.includes(heading + '\n')) text = text.replace(heading + '\n', `${heading}\n${newLine}\n`);
    else { const i = text.indexOf('## 단언'); const j = text.indexOf('\n## ', i + 5); const ins = `\n${heading}\n${newLine}\n`; text = j > 0 ? text.slice(0, j) + ins + text.slice(j) : text.trimEnd() + ins; }
    setDocText(text); setDocDirty(true); setQuickLine('');
  };

  return (
    <div className="w-[28rem] border-l border-[#E5E0D8] bg-[#FBF9F5] flex flex-col overflow-hidden text-[#4A4A4A]">
      <div className="px-3 py-2 border-b border-[#E5E0D8] flex items-center gap-2">
        <span className="text-sm font-semibold">🧠 이 폴더의 기억</span>
        <span className="flex-1 truncate text-xs text-[#8B7B6B]" title={path}>{baseName(path)}</span>
        <button onClick={() => load()} disabled={!!busy} className="text-xs px-2 py-1 rounded bg-[#E8E4DC] hover:bg-[#DDD8D0] disabled:opacity-40">새로고침</button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-3 text-sm">
        {(msg || busy) && <div className="text-xs px-2 py-1 rounded bg-[#EFE9DF] text-[#6B5B4F]">{busy ? `${busy}…` : msg}</div>}

        {/* 머리: 어느 문서를 보고 있나 · 하위 문서 · 사진 스캔 */}
        <div className="text-xs text-[#6B5B4F] space-y-1">
          {docPath ? (
            ownNode
              ? <div>📄 이 폴더의 문서 — <span className="font-mono">{relDoc(docPath)}</span></div>
              : <div>📄 이 폴더 자체의 문서는 없음 — 덮는 상위 문서를 보는 중: <span className="font-mono">{relDoc(docPath)}</span></div>
          ) : <div>📄 이 위치를 덮는 문서 없음</div>}
          {docsBelow.length > 0 && <div title={docsBelow.join('\n')}>🌳 더 자세한 하위 문서 {docsBelow.length}개 — {docsBelow.map((d) => baseName(d.replace(/\/memory\.md$/, ''))).join(', ')}</div>}
          {photo?.exists && <div>📷 사진 관리 스캔 있음 — 사진 {photo.photo_count ?? 0}장 · 동영상 {photo.video_count ?? 0}개{photo.last_scan ? ` · ${String(photo.last_scan).slice(0, 16)}` : ''}</div>}
        </div>

        {/* 만들기 / 갱신 */}
        <div className="space-y-1">
          <textarea value={hint} onChange={(e) => setHint(e.target.value)} placeholder="AI 에게 한마디(옵션) — 이 폴더가 무엇인지, 무엇을 찾고 싶은지, 자세히/거칠게" rows={2}
            className="w-full text-xs p-2 rounded border border-[#E5E0D8] bg-white" />
          <button onClick={build} disabled={!!busy} className="w-full text-xs px-2 py-1.5 rounded bg-[#6B5B4F] text-white hover:bg-[#5A4B3F] disabled:opacity-40">
            {ownNode ? '🧠 AI 에게 갱신 맡기기' : '🧠 AI 에게 이 폴더의 기억 만들기 맡기기'}
          </button>
        </div>

        {/* 문서 — 정본. 단언은 `## 단언` 절의 줄들 */}
        {docPath && (
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-[#8B7B6B]">문서 — 고친 줄은 선언이 됩니다. `## 단언` 절의 한 줄이 기억 하나</span>
              <span className="flex-1" />
              <button onClick={saveDoc} disabled={!!busy || !docDirty} className="text-xs px-2 py-1 rounded bg-[#E8E4DC] hover:bg-[#DDD8D0] disabled:opacity-40">저장</button>
            </div>
            <textarea value={docText} onChange={(e) => { setDocText(e.target.value); setDocDirty(true); }} rows={26}
              className="w-full text-xs p-2 rounded border border-[#E5E0D8] bg-white font-mono leading-snug" />
            <div className="flex gap-1 items-center">
              <select value={quickKind} onChange={(e) => setQuickKind(e.target.value)} className="text-xs p-1 rounded border border-[#E5E0D8] bg-white">
                <option value="identity">정체</option><option value="convention">관습</option><option value="dead_branch">죽은 가지</option><option value="substrate">기질</option>
              </select>
              <input value={quickLine} onChange={(e) => setQuickLine(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') quickAdd(); }} placeholder="이 폴더에 한 줄 더하기(문서의 단언 절에 끼워 넣음 — 저장은 위 단추)"
                className="flex-1 text-xs p-1.5 rounded border border-[#E5E0D8] bg-white" />
              <button onClick={quickAdd} disabled={!quickLine.trim()} className="text-xs px-2 py-1 rounded bg-[#E8E4DC] hover:bg-[#DDD8D0] disabled:opacity-40">끼워 넣기</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
