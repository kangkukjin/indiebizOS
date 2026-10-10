import { useEffect, useState } from 'react';
import { ArrowLeft, Download, Pencil } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { researchCall } from './api';

type Revision = { id: number; body: string; origin: string; created_at: string };
type DocumentData = { notes: string; revision: number; perspective_history: Revision[] };

/** 기존 대화 메모와 수정 이력을 읽는 문서 표면. 모델·대화 실행은 공통 경로를 따른다. */
export function ResearchPerspective({ project, thread, title, onBack, onChange }: {
  project: string; thread: string; title: string; onBack: () => void; onChange: () => void;
}) {
  const [document, setDocument] = useState<DocumentData | null>(null);
  const [draft, setDraft] = useState('');
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const load = async () => {
    const result = await researchCall(project, 'thread_messages', { thread_ref: thread, limit: 1 });
    return result as unknown as DocumentData;
  };
  useEffect(() => {
    let alive = true;
    void researchCall(project, 'thread_messages', { thread_ref: thread, limit: 1 })
      .then(result => { if (alive) setDocument(result as unknown as DocumentData); })
      .catch(e => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [project, thread]);
  const save = async () => {
    if (!document) return;
    setBusy(true); setError('');
    try {
      await researchCall(project, 'thread_update', { thread_ref: thread, notes: draft, expected_revision: document.revision });
      setDocument(await load()); setEditing(false); onChange();
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };
  const refresh = async () => {
    setBusy(true); setError('');
    try { setDocument(await load()); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([document?.notes || ''], { type: 'text/markdown;charset=utf-8' }));
    const link = window.document.createElement('a');
    link.href = url; link.download = `${title}-사용자의 관점.md`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <div className="flex flex-col flex-1 min-h-0">
    <header className="h-14 shrink-0 px-4 flex items-center justify-between gap-3 border-b border-[#E5DFD5] bg-[#EAE4DA]">
      <span className="font-medium truncate">{title} · 사용자의 관점</span>
      <button disabled={busy} onClick={onBack} className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-[#DDD5C8] text-sm"><ArrowLeft size={17} />대화로 돌아가기</button>
    </header>
    <div className="flex-1 min-h-0 overflow-auto p-5">
      <p className="text-sm text-[#8B7D6B] mb-4">대화에서 드러난 주장과 판단 기준을 에이전트가 정리합니다. 직접 고친 내용도 다음 대화에 전달됩니다.</p>
      {error && <p role="alert" className="text-sm text-red-600 mb-3">{error}</p>}
      {!document ? <p className="text-sm">문서를 불러오는 중입니다.</p> : editing ? <>
        <textarea aria-label="사용자의 관점 문서" value={draft} onChange={e => setDraft(e.target.value)} maxLength={12000}
          className="w-full min-h-80 p-4 rounded-lg border border-[#E5DFD5] bg-white outline-none focus:border-[#D97706] text-sm leading-7" />
        <div className="flex items-center gap-3 mt-3 text-sm">
          <button disabled={busy} onClick={() => void save()} className="px-4 py-2 rounded-lg bg-[#D97706] text-white disabled:opacity-50">저장</button>
          <button disabled={busy} onClick={() => setEditing(false)}>취소</button>
          <span className="text-[#8B7D6B]">{draft.length.toLocaleString()} / 12,000</span>
        </div>
        <p className="text-xs text-[#8B7D6B] mt-3">동시에 문서가 바뀌면 저장을 멈춥니다. 초안을 복사한 뒤 취소하고 최신 문서를 다시 불러와 주세요.</p>
      </> : <>
        <div className="flex gap-3 text-sm mb-4">
          <button onClick={() => { setDraft(document.notes); setEditing(true); }} className="inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-[#EAE4DA]"><Pencil size={15} />수정</button>
          <button disabled={busy} onClick={() => void refresh()} className="px-2 py-1 rounded hover:bg-[#EAE4DA]">새로고침</button>
          <button disabled={!document.notes} onClick={download} className="inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-[#EAE4DA] disabled:opacity-40"><Download size={15} />문서 저장</button>
        </div>
        {document.notes ? <article className="prose prose-sm max-w-none text-[#4A4035]"><ReactMarkdown remarkPlugins={[remarkGfm]}>{document.notes}</ReactMarkdown></article>
          : <p className="text-sm text-[#8B7D6B] py-8">아직 정리된 관점이 없습니다. 대화를 이어가면 에이전트가 사용자 발언을 바탕으로 작성합니다.</p>}
        {!!document.perspective_history?.length && <details className="mt-8 border-t border-[#E5DFD5] pt-4 text-sm">
          <summary className="cursor-pointer text-[#8B7D6B]">수정 이력</summary>
          {document.perspective_history.map(item => <details key={item.id} className="mt-3">
            <summary className="cursor-pointer">{new Date(item.created_at).toLocaleString()} · {item.origin === 'agent' ? '에이전트 정리' : '사용자 수정'}</summary>
            <pre className="whitespace-pre-wrap break-words text-xs p-3 bg-white/60 rounded mt-2">{item.body || '(빈 문서)'}</pre>
          </details>)}
        </details>}
      </>}
    </div>
  </div>;
}
