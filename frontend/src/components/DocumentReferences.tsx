import { useEffect, useState } from 'react';
import { documentCommand, documentRequest, type Detail, type Proposal, type Snapshot } from '../lib/api-documents';

type Selection = { snapshot: Snapshot; start: number; end: number; text: string; hash: string };
type Reference = { id: string; resource_id: string; revision_id: string; linked: boolean;
  selector: { sheet: string; range: string }; provenance: { source_uri: string; calculation_state: string } };

type Props = { detail: Detail; selection: Selection | null; disabled: boolean;
  onProposal: (proposal: Proposal & { replacement: string }) => void };

export function DocumentReferences({ detail, selection, disabled, onProposal }: Props) {
  const [path, setPath] = useState('');
  const [sheet, setSheet] = useState('Sheet1');
  const [range, setRange] = useState('A1:B3');
  const [linked, setLinked] = useState(true);
  const [lecture, setLecture] = useState('');
  const [refs, setRefs] = useState<Reference[]>([]);
  const [message, setMessage] = useState('');
  const [pending, setPending] = useState(false);
  const [delivery, setDelivery] = useState<{ key: string; operation: string } | null>(null);
  const id = detail.document.id;
  const act = async (fn: () => Promise<void>) => {
    if (pending) return;
    setPending(true); setMessage('');
    try { await fn(); } catch (e) { setMessage(String(e)); }
    finally { setPending(false); }
  };
  useEffect(() => {
    let active = true;
    documentRequest<{ items: Reference[] }>(`/${id}/references`)
      .then(r => { if (active) setRefs(r.items); }).catch(e => { if (active) setMessage(String(e)); });
    return () => { active = false; };
  }, [id, detail.session?.session_revision]);

  const propose = async (source: string, revision: string, selectedSheet: string, selectedRange: string, connected: boolean) => {
    if (!selection) throw new Error('보고서에서 넣거나 갱신할 구간을 선택 고정하세요');
    const p = await documentCommand<Proposal & { replacement: string }>(id, 'import-sheet', {
      snapshot_id: selection.snapshot.id, start: selection.start, end: selection.end,
      selected_sha256: selection.hash, resource_id: source, revision_id: revision,
      sheet: selectedSheet, cell_range: selectedRange, linked: connected,
    });
    onProposal(p); setMessage('표 제안을 만들었습니다. 오른쪽에서 확인하고 적용하세요.');
  };
  const importSheet = () => act(async () => {
    const source = await documentRequest<Detail>('/open', 'POST', { path });
    await propose(source.document.id, source.document.revision_id, sheet, range, linked);
  });
  const refresh = (ref: Reference) => act(async () => {
    if (!selection) throw new Error('갱신할 표 구간을 먼저 선택 고정하세요');
    const source = await documentRequest<Detail>(`/${ref.resource_id}`);
    const revision = await documentCommand<{ revision_id: string }>(ref.resource_id, 'refresh-source', {
      expected_revision: source.document.revision_id,
    });
    await propose(ref.resource_id, revision.revision_id, ref.selector.sheet, ref.selector.range, ref.linked);
  });
  const send = () => act(async () => {
    if (!selection || detail.session?.state !== 'saved') throw new Error('원본 저장 후 전달할 구간을 다시 선택 고정하세요');
    const key = JSON.stringify([id, detail.document.revision_id, selection.start, selection.end, lecture]);
    const request = delivery?.key === key ? delivery : { key, operation: crypto.randomUUID() };
    setDelivery(request);
    const result = await documentCommand<{ material: { file: string }; reference: { revision_id: string } }>(id, 'lecture', {
      revision_id: detail.document.revision_id, start: selection.start, end: selection.end, selected_sha256: selection.hash,
      lecture_id: lecture, operation_id: request.operation,
    });
    setMessage(`강의 재료 전달됨: ${result.material.file} · 원본 버전 ${result.reference.revision_id}`);
  });

  return <section aria-label="자료 연결">
    <h3>시트·강의 연결</h3>
    <p>표는 저장된 계산값을 가져옵니다. 수식 캐시의 최신성은 미확인이며 원본 갱신은 직접 선택합니다.</p>
    <label>XLSX 파일 경로<input value={path} onChange={e => setPath(e.target.value)} /></label>
    <label>시트 이름<input value={sheet} onChange={e => setSheet(e.target.value)} /></label>
    <label>셀 범위<input value={range} onChange={e => setRange(e.target.value)} /></label>
    <label><input type="checkbox" checked={linked} onChange={e => setLinked(e.target.checked)} />원본과 연결</label>
    <button disabled={disabled || pending || !selection || !path || !['md', 'markdown'].includes(detail.document.source_format)} onClick={importSheet}>시트 표 제안</button>
    {refs.map(ref => <div key={ref.id}>
      <p>{ref.provenance.source_uri} · {ref.selector.sheet}!{ref.selector.range} · 버전 {ref.revision_id}</p>
      {ref.linked && <><button disabled={disabled || pending} onClick={() => void act(async () => {
        const status = await documentRequest<{ source_changed?: boolean; source_available?: boolean; source_error?: string }>(`/${id}/references/${ref.id}`);
        setMessage(status.source_available === false ? '원본을 확인할 수 없습니다: '+(status.source_error || '이동·삭제·권한을 확인하세요') : status.source_changed ? '원본이 변경됐습니다. 기존 표 유지 또는 선택 갱신이 가능합니다.' : '원본 변경 없음');
      })}>원본 변경 확인</button><button disabled={disabled || pending || !selection} onClick={() => void refresh(ref)}>선택 구간 갱신 제안</button></>}
    </div>)}
    <label>강의 ID<input value={lecture} onChange={e => setLecture(e.target.value)} /></label>
    <button disabled={disabled || pending || !selection || !lecture || detail.session?.state !== 'saved'} onClick={send}>저장된 선택을 강의 재료로</button>
    <p role="status">{pending ? '자료 연결 중…' : message}</p>
  </section>;
}
