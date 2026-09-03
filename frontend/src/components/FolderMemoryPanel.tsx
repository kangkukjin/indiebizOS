/**
 * FolderMemoryPanel — PC 관리 창의 "기억" 판: 지금 보고 있는 폴더의 포식 기억.
 *
 * 능력은 전부 어휘, 이 컴포넌트는 표현만(철칙 0):
 *   보기   = [self:forage]{op:recall, locus}   (자기 단언 own · 물려받은 관습 inherit · 자식 골격 child)
 *   빼기   = [self:forage]{op:forget}
 *   선언   = [self:forage]{op:note, provenance=주인 선언}
 *   문서   = 루트 단언이 가리키는 문서(또는 forage_surveys 의 이름 일치) → [self:read] / [self:write]
 *   만들기 = [others:delegate]{scope:system} "가이드 폴더 조사대로 만들어라" — 판단·관측은 AI 몫
 *   사진   = /photo/scan/check — 이 폴더를 사진 관리 스캔이 덮고 있으면 그 사실을 보인다
 * 옛 앱 모드 계기(instruments/folder_survey.yaml)를 이 판으로 흡수(2026-09-03 사용자 판정: 폴더를 고르는 곳에 기억이 붙는다).
 */
import { useCallback, useEffect, useState } from 'react';
import { iblExecuteApp } from '../lib/instrument';

type MapItem = { id: number; kind: string; via?: string; locus: string; claim: string; short?: string; territory?: number; generalizes?: number };
type PhotoScan = { exists: boolean; photo_count?: number; video_count?: number; last_scan?: string | null };

const getApiUrl = async () => {
  if (window.electron?.getApiPort) return `http://127.0.0.1:${await window.electron.getApiPort()}`;
  return 'http://127.0.0.1:8765';
};
const q = (s: string) => JSON.stringify(s);
const baseName = (p: string) => p.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || p;

export function FolderMemoryPanel({ path }: { path: string }) {
  const [items, setItems] = useState<MapItem[]>([]);
  const [docPath, setDocPath] = useState<string | null>(null);
  const [docText, setDocText] = useState('');
  const [docDirty, setDocDirty] = useState(false);
  const [photo, setPhoto] = useState<PhotoScan | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [hint, setHint] = useState('');
  const [kind, setKind] = useState('identity');
  const [claim, setClaim] = useState('');
  const [gen, setGen] = useState(false);

  const load = useCallback(async () => {
    if (!path) return;
    setBusy('불러오는 중'); setMsg(null); setDocDirty(false);
    try {
      const r = (await iblExecuteApp(`[self:forage]{op: "recall", locus: ${q(path)}, limit: 40}`)) as { map?: MapItem[]; doc?: string | null } | null;
      const map = r?.map ?? [];
      setItems(map);
      // 문서(정본): 회상이 이 위치를 덮는 문서 경로(doc)를 준다 — 없으면 옛 규칙(루트 단언·이름 일치)
      let doc: string | null = r?.doc ?? null;
      for (const m of doc ? [] : map) {
        if (m.via && m.via !== 'own') continue;   // 조상(inherit)·자식(child) 단언이 가리키는 문서는 이 폴더 것이 아니다
        const hit = m.claim.match(/(\S*forage_surveys\/[^\s'"`)]+\.md)/);
        if (hit) { doc = hit[1]; break; }
      }
      if (!doc) {
        // 예비 규칙: 문서 파일 이름(확장자 뺀 것)이 폴더 이름 또는 경로 슬러그와 **정확히** 같을 때만.
        // 부분 일치는 금물 — 워크스페이스 경로에 든 "Desktop" 이 바탕화면에서 다른 폴더 문서를 잡았다(2026-09-03 사용자 신고).
        const f = (await iblExecuteApp(`[self:file_find]{pattern: "*.md", path: "~workspace/data/forage_surveys"}`)) as { items?: { title?: string; url?: string }[] } | null;
        const name = baseName(path);
        const slug = path.replace(/^[\\/]+/, '').replace(/[\\/]+/g, '_');
        const stem = (u: string) => (u.split(/[\\/]/).pop() || '').replace(/\.md$/i, '');
        const cand = (f?.items ?? []).find((it) => { const st = stem(it.url || it.title || ''); return st === name || st === slug; });
        doc = cand?.url ?? null;
      }
      setDocPath(doc);
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

  const forget = (m: MapItem) => {
    if (!confirm('이 단언을 지울까요?')) return;
    run('빼기', `[self:forage]{op: "forget", id: ${m.id}, table: "forage_map"}`, load);
  };
  const declare = () => {
    if (!claim.trim()) return;
    run('선언 저장', `[self:forage]{op: "note", layer: "map", locus: ${q(path)}, kind: ${q(kind)}, claim: ${q(claim.trim())}, generalizes: ${gen ? 'true' : 'false'}, confidence: 0.95, provenance: {observed: ["주인 선언(PC 관리 창)"]}}`,
      async () => { setClaim(''); await load(); });
  };
  const saveDoc = () => {
    if (!docPath) return;
    // 문서가 정본 — 저장 뒤 `## 단언` 절을 색인에 맞추고(sync) 다시 읽는다
    run('문서 저장', `[self:write]{path: ${q(docPath)}, content: ${q(docText)}} >> [self:forage]{op: "sync", locus: ${q(path)}}`, async () => { setDocDirty(false); await load(); });
  };
  const build = () => {
    const has = !!docPath || items.length > 0;
    if (!confirm(has ? 'AI 가 이 폴더를 다시 살펴 기억을 갱신합니다(차이만, 당신이 고친 줄은 보존). 진행할까요?' : 'AI 가 이 폴더를 살펴보고 포식 기억(단언 + 문서)을 만듭니다. 시간이 걸릴 수 있습니다. 진행할까요?')) return;
    const message = `폴더 조사: ${path} 의 포식 기억을 ${has ? '갱신해라(차이만)' : '만들어라'}. 먼저 read_guide 로 가이드 폴더 조사(folder_survey)를 읽고 그대로 한다 — 단언은 self:forage note 로, 문서는 그 가이드가 정한 자리에. 이미 문서가 있으면 주인이 고친 줄은 보존한다.${hint.trim() ? ' 주인의 말: ' + hint.trim() : ''}`;
    run('AI 에게 맡기기', `[others:delegate]{scope: "system", message: ${q(message)}, from_agent: "PC관리 기억판"}`);
  };

  const viaLabel: Record<string, string> = { own: '이 폴더', inherit: '상위에서', child: '하위 폴더', match: '일치', all: '' };

  return (
    <div className="w-96 border-l border-[#E5E0D8] bg-[#FBF9F5] flex flex-col overflow-hidden text-[#4A4A4A]">
      <div className="px-3 py-2 border-b border-[#E5E0D8] flex items-center gap-2">
        <span className="text-sm font-semibold">🧠 이 폴더의 기억</span>
        <span className="flex-1 truncate text-xs text-[#8B7B6B]" title={path}>{baseName(path)}</span>
        <button onClick={() => load()} disabled={!!busy} className="text-xs px-2 py-1 rounded bg-[#E8E4DC] hover:bg-[#DDD8D0] disabled:opacity-40">새로고침</button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-4 text-sm">
        {msg && <div className="text-xs px-2 py-1 rounded bg-[#EFE9DF] text-[#6B5B4F]">{busy ? `${busy}…` : msg}</div>}
        {busy && !msg && <div className="text-xs text-[#8B7B6B]">{busy}…</div>}

        {/* 머리: 문서·사진 스캔 */}
        <div className="text-xs text-[#6B5B4F] space-y-1">
          <div>{docPath ? `📄 문서 있음 — ${baseName(docPath)}` : '📄 문서 없음'}</div>
          {photo?.exists && <div>📷 사진 관리 스캔 있음 — 사진 {photo.photo_count ?? 0}장 · 동영상 {photo.video_count ?? 0}개{photo.last_scan ? ` · ${String(photo.last_scan).slice(0, 16)}` : ''}</div>}
        </div>

        {/* 만들기 / 갱신 */}
        <div className="space-y-1">
          <textarea value={hint} onChange={(e) => setHint(e.target.value)} placeholder="AI 에게 한마디(옵션) — 이 폴더가 무엇인지, 무엇을 찾고 싶은지" rows={2}
            className="w-full text-xs p-2 rounded border border-[#E5E0D8] bg-white" />
          <button onClick={build} disabled={!!busy} className="w-full text-xs px-2 py-1.5 rounded bg-[#6B5B4F] text-white hover:bg-[#5A4B3F] disabled:opacity-40">
            {docPath || items.length ? '🧠 AI 에게 갱신 맡기기' : '🧠 AI 에게 기억 만들기 맡기기'}
          </button>
        </div>

        {/* 단언 목록 */}
        <div>
          <div className="text-xs font-semibold text-[#8B7B6B] mb-1">단언 {items.length}건</div>
          {items.length === 0 ? (
            <div className="text-xs text-[#A0A0A0]">아직 적힌 기억이 없습니다.</div>
          ) : (
            <ul className="space-y-1">
              {items.map((m) => (
                <li key={m.id} className="rounded bg-white border border-[#EEE9E1] px-2 py-1.5">
                  <div className="flex items-center gap-1 text-[11px] text-[#8B7B6B]">
                    <span className="px-1 rounded bg-[#EFE9DF]">{m.kind}</span>
                    {m.via && viaLabel[m.via] && <span>{viaLabel[m.via]}</span>}
                    {m.via !== 'own' && m.via !== 'match' && <span className="truncate" title={m.locus}>{baseName(m.locus)}</span>}
                    {!!m.territory && <span title="영토 앵커">⚑</span>}
                    <span className="flex-1" />
                    <button onClick={() => forget(m)} className="text-[11px] text-[#A0A0A0] hover:text-red-500">빼기</button>
                  </div>
                  <div className="text-xs mt-0.5 whitespace-pre-wrap">{m.via === 'child' ? (m.short || m.claim) : m.claim}</div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* 주인 선언 */}
        <div className="space-y-1">
          <div className="text-xs font-semibold text-[#8B7B6B]">주인 선언 추가 — AI 가 못 보는 것(연상 기준·예외·취향)</div>
          <div className="flex gap-1">
            <select value={kind} onChange={(e) => setKind(e.target.value)} className="text-xs p-1 rounded border border-[#E5E0D8] bg-white">
              <option value="identity">정체</option><option value="convention">관습</option><option value="dead_branch">죽은 가지</option><option value="substrate">기질</option>
            </select>
            <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={gen} onChange={(e) => setGen(e.target.checked)} />하위 폴더에도</label>
          </div>
          <textarea value={claim} onChange={(e) => setClaim(e.target.value)} placeholder="한 줄 단언" rows={2} className="w-full text-xs p-2 rounded border border-[#E5E0D8] bg-white" />
          <button onClick={declare} disabled={!!busy || !claim.trim()} className="text-xs px-2 py-1 rounded bg-[#E8E4DC] hover:bg-[#DDD8D0] disabled:opacity-40">선언 저장</button>
        </div>

        {/* 문서 */}
        {docPath && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-[#8B7B6B]">문서 — 고친 줄은 선언이 됩니다</div>
            <textarea value={docText} onChange={(e) => { setDocText(e.target.value); setDocDirty(true); }} rows={14}
              className="w-full text-xs p-2 rounded border border-[#E5E0D8] bg-white font-mono" />
            <button onClick={saveDoc} disabled={!!busy || !docDirty} className="text-xs px-2 py-1 rounded bg-[#E8E4DC] hover:bg-[#DDD8D0] disabled:opacity-40">문서 저장</button>
          </div>
        )}
      </div>
    </div>
  );
}
