import { useEffect, useRef, useState } from 'react';
import { sheetCommand, type SheetSnapshot } from '../lib/api-spreadsheets';
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
  const [allowStale, setAllowStale] = useState(false);
  const currentId = useRef(detail.document.id);
  currentId.current = detail.document.id;
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
    let sourceArgs: Record<string, unknown>;
    if (source.session) {
      const request = await sheetCommand<{ operation_id: string }>(ref.resource_id, 'request-snapshot', { operation_id: crypto.randomUUID() });
      let captured: SheetSnapshot | undefined;
      for (let attempt = 0; attempt < 60; attempt++) {
        if (currentId.current !== id) return;
        const receipt = await sheetCommand<{ status: string; completed: boolean; result?: { snapshot?: SheetSnapshot; error?: string } }>(ref.resource_id, 'operation-status', { operation_id: request.operation_id });
        if (receipt.completed) { captured = receipt.result?.snapshot; break; }
        if (['failed', 'interrupted'].includes(receipt.status)) throw new Error(receipt.result?.error || '원본 스냅샷 요청이 중단됐습니다');
        await new Promise(resolve => setTimeout(resolve, 500));
      }
      if (!captured) throw new Error('원본 편집창의 스냅샷 완료를 확인하지 못했습니다. 원본 창 연결을 확인하세요');
      sourceArgs = { source_snapshot_id: captured.id };
    } else {
      const revision = await documentCommand<{ revision_id: string }>(ref.resource_id, 'refresh-source', {
        expected_revision: source.document.revision_id,
      });
      sourceArgs = { source_revision_id: revision.revision_id };
    }
    if (currentId.current !== id) return;
    const p = await documentCommand<Proposal & { replacement: string }>(id, 'refresh-sheet', {
      reference_id: ref.id, snapshot_id: selection.snapshot.id, start: selection.start,
      end: selection.end, selected_sha256: selection.hash, allow_stale: allowStale, ...sourceArgs,
    });
    if (currentId.current !== id) return;
    onProposal(p); setMessage('갱신 제안을 만들었습니다. 문서에서 손본 내용과 비교한 뒤 적용하세요.');
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
    <p>새 표는 저장된 계산값을 가져옵니다. 연결 갱신은 열린 시트의 최신 스냅샷을 요청하고 선택한 문서 구간의 변경안을 만듭니다. 적용 전 차이를 검토하세요.</p>
    <label><input type="checkbox" checked={allowStale} onChange={e=>setAllowStale(e.target.checked)}/>갱신에 미확인 계산값 사용</label>
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
