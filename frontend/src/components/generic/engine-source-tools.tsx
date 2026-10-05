/* 원문 엔진의 "⚙ 도구" 패널 — 평소엔 접혀 있고, 캔버스의 기본 모양을 건드리지 않는다.
 * 옛 문서 창에만 있던 문서별 기능을 여기로 옮겼다(2026-10-06, docs/DOCUMENT_APP_ON_BINNOTE_PLAN_2026_10_05.md):
 *   사본 저장 · 다른 형식으로 변환 사본 · 저장 버전 되살리기 · 저장 상태 복구 · 미리보기 · 시트 표 넣기/갱신 · 강의 재료 전달.
 * 저장·세션은 엔진(SourceEngine)의 것을 빌려 쓴다 — 여기서 따로 세션을 잡지 않는다. */
import { useEffect, useState } from 'react';
import { documentCommand, documentRequest, sessionArgs, PREVIEWABLE, type Detail, type Proposal, type Snapshot } from '../../lib/api-documents';
import { DocumentReferences } from '../DocumentReferences';

type Fixed = { snapshot: Snapshot; start: number; end: number; text: string; hash: string };
type Version = { id: string; created_at: number };
const CONVERT = ['pdf', 'docx', 'odt', 'rtf', 'html', 'txt', 'epub'];

async function sha256(text: string) {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes), (v) => v.toString(16).padStart(2, '0')).join('');
}

export function SourceTools({ detail, text, busy, writable, run, draft, pick, replaceFrom, setMessage, preview, setPreview }: {
  detail: Detail; text: string; busy: boolean; writable: boolean;
  run: (fn: () => Promise<void>) => Promise<void>;
  draft: () => Promise<Detail>;                                    // 초안을 올리고 최신 세션을 돌려준다
  pick: () => { start: number; end: number; text: string } | null;  // 캔버스의 지금 선택(서버 주소·원본 줄바꿈)
  replaceFrom: (next: Detail) => void;                             // 서버가 준 본문으로 캔버스를 바꾼다
  setMessage: (m: string) => void;
  preview: boolean; setPreview: (v: boolean) => void;
}) {
  const id = detail.document.id, title = detail.document.title, dot = title.lastIndexOf('.');
  const [versions, setVersions] = useState<Version[] | null>(null);
  const [copyName, setCopyName] = useState(dot > 0 ? `${title.slice(0, dot)}_사본${title.slice(dot)}` : `${title}_사본`);
  const [outFormat, setOutFormat] = useState('pdf');
  // 고정한 선택과 제안은 그때의 글에 묶인다 — 글이 바뀌면 낡은 것이므로 내놓지 않는다.
  const [fixedAt, setFixedAt] = useState<{ value: Fixed; text: string } | null>(null);
  const [proposalAt, setProposalAt] = useState<{ value: Proposal & { replacement: string }; text: string } | null>(null);
  const fixed = fixedAt && fixedAt.text === text ? fixedAt.value : null;
  const proposal = proposalAt && proposalAt.text === text ? proposalAt.value : null;
  const setProposal = (p: (Proposal & { replacement: string }) | null) => setProposalAt(p ? { value: p, text } : null);
  const [links, setLinks] = useState(false);
  useEffect(() => {
    let dead = false;
    documentRequest<{ items: Version[] }>(`/${id}/versions`).then((r) => { if (!dead) setVersions(r.items); }, () => { if (!dead) setVersions([]); });
    return () => { dead = true; };
  }, [id, detail.document.revision_id]);

  const session = async () => {
    const d = await draft();
    if (!d.session) throw new Error('작성 세션이 없습니다');
    return { d, args: { ...sessionArgs(d.session), operation_id: crypto.randomUUID() } };
  };
  const exportCopy = () => void run(async () => {
    const { args } = await session();
    const r = await documentCommand<{ path: string }>(id, 'export', { ...args, filename: copyName });
    setMessage(`사본 저장됨: ${r.path} · 원본은 그대로`);
  });
  const convert = () => void run(async () => {
    const { d } = await session();
    const r = await documentCommand<Detail>(id, 'convert', { ...sessionArgs(d.session!), output_format: outFormat, expected_revision: d.document.revision_id });
    setMessage(`변환 사본을 만들었습니다: ${r.document.source_uri} · 쪽 배치와 서식을 확인하세요`);
  });
  const restore = (revision_id: string) => void run(async () => {
    const { args } = await session();
    await documentCommand(id, 'restore', { ...args, revision_id });
    replaceFrom(await documentRequest<Detail>(`/${id}`));
    setMessage('고른 버전을 작업 초안으로 되살렸습니다 · 원본 저장 전');
  });
  const recover = () => void run(async () => {
    const r = await documentCommand<{ detail: Detail; items: { state: string }[] }>(id, 'recover');
    replaceFrom(r.detail);
    setMessage(r.items.length ? `저장 복구 확인: ${r.items.map((x) => x.state).join(', ')}` : '미완료 저장 없음');
  });
  const fix = () => void run(async () => {
    const sel = pick();
    if (!sel) throw new Error('캔버스에서 구간을 먼저 선택하세요');
    const { d } = await session();
    const snapshot = await documentCommand<Snapshot>(id, 'snapshots', sessionArgs(d.session!));
    setFixedAt({ value: { snapshot, start: sel.start, end: sel.end, text: sel.text, hash: await sha256(sel.text) }, text });
    setProposalAt(null);
  });
  const apply = () => void run(async () => {
    if (!proposal) return;
    const { d, args } = await session();
    const r = await documentCommand<{ session: Detail['session']; text: string }>(id, 'apply', { ...args, proposal_id: proposal.id });
    replaceFrom({ ...d, session: r.session, text: r.text });
    setMessage('제안을 초안에 적용했습니다 · 원본 저장 전');
  });

  const row = 'flex flex-wrap items-center gap-2', hint = 'text-xs text-stone-500 shrink-0', btn = 'px-2.5 py-1 rounded-lg border border-stone-300 hover:border-stone-500 disabled:opacity-40';
  const field = 'px-2 py-1 rounded-lg border border-stone-200';
  return (
    <div className="rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm flex flex-col gap-3">
      <div className={row}>
        <span className={hint}>사본</span>
        <input value={copyName} onChange={(e) => setCopyName(e.target.value)} aria-label="사본 파일명" className={`${field} flex-1 min-w-[10rem]`} />
        <button disabled={busy || !writable || !copyName.trim()} onClick={exportCopy} className={btn}>다른 이름으로 저장</button>
        <select value={outFormat} onChange={(e) => setOutFormat(e.target.value)} aria-label="변환 형식" className={field}>
          {CONVERT.map((f) => <option key={f}>{f}</option>)}
        </select>
        <button disabled={busy || !writable} onClick={convert} className={btn}>이 형식으로 변환 사본</button>
      </div>
      <div className="flex flex-col gap-1">
        <div className={row}>
          <span className={hint}>저장 버전 — 되살리면 작업 초안이 되고, 저장을 눌러야 원본이 바뀝니다</span>
          <div className="flex-1" />
          <button disabled={busy} onClick={recover} className={btn} title="저장 도중 끊긴 작업이 있는지 확인하고 마무리합니다">저장 상태 복구</button>
        </div>
        {versions && versions.length === 0 && <span className="text-xs text-stone-400">아직 저장한 버전이 없습니다</span>}
        {(versions || []).map((v) => (
          <div key={v.id} className="flex items-center gap-2">
            <span className="flex-1 text-stone-700">{new Date(v.created_at * 1000).toLocaleString()}{v.id === detail.document.revision_id ? ' · 현재 원본' : ''}</span>
            {v.id !== detail.document.revision_id && <button disabled={busy || !writable} onClick={() => restore(v.id)} className={btn}>되살리기</button>}
          </div>
        ))}
      </div>
      <div className={row}>
        {PREVIEWABLE.includes(detail.document.source_format) && (
          <label className="flex items-center gap-1.5 text-stone-700"><input type="checkbox" checked={preview} onChange={(e) => setPreview(e.target.checked)} />미리보기</label>
        )}
        <label className="flex items-center gap-1.5 text-stone-700"><input type="checkbox" checked={links} onChange={(e) => setLinks(e.target.checked)} />시트 표·강의 연결</label>
      </div>
      {links && (
        <div className="engine-editor border-t border-stone-100 pt-3">
          <div className={row}>
            <button disabled={busy || !writable} onClick={fix} className={btn}>캔버스 선택 고정</button>
            <span className={hint}>{fixed ? `고정한 선택 ${Array.from(fixed.text).length}자 — 여기에 표를 넣거나 갱신하고, 강의로 보냅니다` : '표를 넣을 자리(또는 갱신할 표, 강의로 보낼 구간)를 캔버스에서 선택한 뒤 누르세요'}</span>
          </div>
          {proposal && (
            <div className="rounded-lg border border-amber-200 bg-amber-50/60 overflow-hidden">
              <div className="max-h-40 overflow-auto px-3 py-2 whitespace-pre-wrap leading-relaxed text-stone-800">{proposal.replacement}</div>
              <div className="flex items-center gap-1.5 px-3 py-1.5 border-t border-amber-100">
                <button disabled={busy} onClick={apply}>제안 적용</button>
                <button disabled={busy} onClick={() => setProposal(null)}>버리기</button>
              </div>
            </div>
          )}
          <DocumentReferences key={id} detail={detail} selection={fixed} disabled={busy || !writable} onProposal={setProposal} />
        </div>
      )}
    </div>
  );
}
