import { useCallback, useEffect, useState } from 'react';
import { researchCall } from './api';
import { runIBL } from '../generic/manifest';

type Evidence = { evidence_id: string; version_ref: string; extraction_revision: number; locator: string; quote: string };
type Resolution = { disposition: string; rationale: string; objections: { evidence_id: string; rationale: string }[] };
type Question = { question_id: string; revision: number; text: string; scope: string; provisional_answer: string;
  supporting: Evidence[]; contradicting: Evidence[]; gaps: string[]; next_probes: string[];
  status: string; resolution: Resolution | null; origin?: string; created_at?: string };
const blank = (): Question => ({ question_id: '', revision: 0, text: '', scope: '', provisional_answer: '', supporting: [],
  contradicting: [], gaps: [], next_probes: [], status: 'open', resolution: null });
const field = 'w-full rounded border border-[#D5CBBB] bg-white p-2 text-sm';
const button = 'px-3 py-2 rounded border border-[#D5CBBB] text-sm disabled:opacity-40';

export function ResearchQuestions({ project, thread, onBack }: { project: string; thread: string; onBack: () => void }) {
  const [items, setItems] = useState<Question[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [draft, setDraft] = useState<Question | null>(null);
  const [history, setHistory] = useState<Question[]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState('');
  const [sourceNext, setSourceNext] = useState<{ ref: Evidence; cursor: string } | null>(null);
  const [gapText, setGapText] = useState('');
  const [probeText, setProbeText] = useState('');
  const [saved, setSaved] = useState('');
  const call = useCallback((params: Record<string, unknown>) => researchCall(project, 'thread_messages', {
    thread_ref: thread, questions_only: true, ...params,
  }), [project, thread]);
  const load = useCallback(async (next?: string) => {
    const result = await call({ cursor: next || '0', limit: 30 });
    setItems(old => next ? [...old, ...(result.items as Question[])] : result.items as Question[]);
    setCursor(result.next_cursor as string | null);
  }, [call]);
  useEffect(() => { void load().catch(e => setError(String(e))); }, [load]);
  const select = (q: Question) => {
    setDraft(structuredClone(q)); setGapText(q.gaps.join('\n')); setProbeText(q.next_probes.join('\n'));
    setHistory([]); setHistoryCursor(null); setSource(''); setSourceNext(null); setError(''); setSaved('');
  };
  const patch = (value: Partial<Question>) => setDraft(q => q ? { ...q, ...value } : q);
  const save = async () => {
    if (!draft) return;
    setBusy(true); setError(''); setSaved('');
    try {
      const { question_id, revision, text, scope, provisional_answer, supporting, contradicting, resolution } = draft;
      const change = { ...(question_id ? { question_id } : {}), expected_revision: revision, text, scope,
        provisional_answer, supporting, contradicting, gaps: gapText.split('\n').map(s => s.trim()).filter(Boolean),
        next_probes: probeText.split('\n').map(s => s.trim()).filter(Boolean), resolution };
      const result = await researchCall(project, 'thread_update', { thread_ref: thread, questions: [change] });
      select((result.items as Question[])[0]); await load(); setSaved('저장했습니다.');
    } catch (e) { setError(`${String(e)} · 작성 중인 내용은 유지됩니다. 충돌한 경우 최신 기록을 읽고 비교해 주세요.`); }
    finally { setBusy(false); }
  };
  const readHistory = async (next?: string) => {
    if (!draft?.question_id) return;
    try {
      const result = await call({ question_id: draft.question_id, question_history: true, cursor: next || '0', limit: 20 });
      setHistory(old => next ? [...old, ...(result.items as Question[])] : result.items as Question[]);
      setHistoryCursor(result.next_cursor as string | null);
    } catch (e) { setError(String(e)); }
  };
  const readSource = async (ref: Evidence, cursor = '0') => {
    try {
      const inputs = { project_ref: project, thread_ref: thread, version_ref: ref.version_ref, extraction_revision: ref.extraction_revision, cursor };
      const result = await runIBL({ code: '[self:notebook]{op:"read",project_ref:$project_ref,thread_ref:$thread_ref,version_ref:$version_ref,extraction_revision:$extraction_revision,cursor:$cursor}',
        edition: 2, inputs, declared_inputs: Object.keys(inputs) });
      if (result.error || result.success === false) throw new Error(String(result.error || '원문 조회 실패'));
      setSource(String(result.text || JSON.stringify(result.items, null, 2)));
      setSourceNext(result.next_cursor ? { ref, cursor: String(result.next_cursor) } : null);
    } catch (e) { setError(String(e)); }
  };
  return <section className="flex flex-col flex-1 min-h-0 bg-[#F7F4EE]">
    <header className="flex items-center justify-between p-4 border-b border-[#E5DFD5]">
      <h2 className="font-medium">연구 질문</h2><button className={button} onClick={onBack}>대화로 돌아가기</button>
    </header>
    <div className="overflow-auto p-4 space-y-4">
      <p className="text-sm text-gray-600">이 대화의 질문과 잠정 답변입니다. 종결은 연구 판단의 기록이며 사실 인증이 아닙니다.</p>
      {error && <p role="alert" className="text-red-700 whitespace-pre-wrap">{error}</p>}
      {saved && <p role="status">{saved}</p>}
      <div className="flex gap-2"><button className={button} disabled={busy} onClick={() => select(blank())}>질문 추가</button>
        <button className={button} onClick={() => void load().catch(e => setError(String(e)))}>목록 새로고침</button></div>
      {!items.length && <p className="text-sm">아직 저장된 연구 질문이 없습니다.</p>}
      {items.map(q => <button key={q.question_id} disabled={busy} className="block w-full text-left p-3 rounded border border-[#D5CBBB]" onClick={() => select(q)}>
        <span className="text-xs text-gray-500">{q.status === 'open' ? '열림' : '종결'} · 판본 {q.revision}</span><p>{q.text}</p>
      </button>)}
      {cursor && <button className={button} onClick={() => void load(cursor).catch(e => setError(String(e)))}>질문 더 보기</button>}
      {draft && <fieldset disabled={busy} className="space-y-3 border-t border-[#D5CBBB] pt-4">
        <label className="block">질문<input className={field} maxLength={1000} value={draft.text} onChange={e => patch({ text: e.target.value, resolution: null })} /></label>
        <label className="block">범위<input className={field} maxLength={1000} value={draft.scope} onChange={e => patch({ scope: e.target.value, resolution: null })} /></label>
        <label className="block">잠정 답변<textarea className={field} rows={4} maxLength={4000} value={draft.provisional_answer} onChange={e => patch({ provisional_answer: e.target.value, resolution: null })} /></label>
        <label className="block">남은 확인 사항 · 한 줄에 하나<textarea className={field} value={gapText} onChange={e => { setGapText(e.target.value); patch({ resolution: null }); }} /></label>
        <label className="block">다음 조사 · 한 줄에 하나<textarea className={field} value={probeText} onChange={e => { setProbeText(e.target.value); patch({ resolution: null }); }} /></label>
        {(['supporting', 'contradicting'] as const).map(role => <div key={role}><h3 className="font-medium">{role === 'supporting' ? '지지 근거' : '반박 근거'}</h3>
          {!draft[role].length && <p className="text-sm text-gray-500">연결된 근거가 없습니다. 대화에서 자료를 읽고 이 질문에 연결하도록 요청할 수 있습니다.</p>}
          {draft[role].map(ref => <blockquote key={ref.evidence_id} className="border-l-2 pl-3 my-2 whitespace-pre-wrap">
            {ref.quote}<div className="text-xs text-gray-500">{ref.locator} · 추출 판본 {ref.extraction_revision}</div>
            <button className={button} onClick={() => void readSource(ref)}>보존 원문 읽기</button>
          </blockquote>)}
        </div>)}
        <label className="block">질문 상태<select className={field} value={draft.resolution?.disposition || ''} onChange={e => patch({ resolution: e.target.value ? {
          disposition: e.target.value, rationale: '', objections: draft.contradicting.map(r => ({ evidence_id: r.evidence_id, rationale: '' })),
        } : null })}><option value="">열림</option><option value="answered">답변으로 종결</option><option value="withdrawn">질문 철회</option><option value="out_of_scope">범위 밖</option></select></label>
        {draft.resolution && <><label className="block">종결 이유<textarea className={field} value={draft.resolution.rationale} onChange={e => patch({ resolution: { ...draft.resolution!, rationale: e.target.value } })} /></label>
          {draft.resolution.disposition === 'answered' && draft.resolution.objections.map((item, index) => <label className="block" key={item.evidence_id}>
            반박 검토: {draft.contradicting.find(r => r.evidence_id === item.evidence_id)?.quote}
            <textarea className={field} value={item.rationale} onChange={e => patch({ resolution: { ...draft.resolution!, objections: draft.resolution!.objections.map((r, i) => i === index ? { ...r, rationale: e.target.value } : r) } })} />
          </label>)}</>}
        <div className="flex gap-2"><button className={button} onClick={() => void save()}>{busy ? '저장 중…' : '저장'}</button>
          {draft.question_id && <button className={button} onClick={() => void readHistory()}>최신 기록·변경 이력 비교</button>}</div>
      </fieldset>}
      {history.map(q => <details key={q.revision} className="border rounded p-3"><summary>판본 {q.revision} · {q.origin === 'agent' ? 'AI' : '사용자'} · {q.created_at}</summary>
        <p>{q.text} · {q.scope}</p><p className="whitespace-pre-wrap">{q.provisional_answer}</p>
        <p>남은 확인: {q.gaps.join(' / ') || '없음'}</p><p>다음 조사: {q.next_probes.join(' / ') || '없음'}</p>
        {[...q.supporting.map(r => ({ ...r, label: '지지' })), ...q.contradicting.map(r => ({ ...r, label: '반박' }))].map(r => <p key={r.evidence_id}>{r.label}: {r.quote} ({r.locator})</p>)}
        <p>종결: {q.resolution ? `${q.resolution.disposition} · ${q.resolution.rationale}` : '열림'}</p>
        {q.resolution?.objections.map(r => <p key={r.evidence_id}>반박 검토: {r.rationale}</p>)}
        <button className={button} disabled={busy} onClick={() => { if (window.confirm('작성 중인 내용을 이 판본으로 교체할까요?')) select(q); }}>편집기에 불러오기</button>
      </details>)}
      {historyCursor && <button className={button} onClick={() => void readHistory(historyCursor)}>이력 더 보기</button>}
      {source && <section className="border rounded p-3"><h3>보존 원문 · 현재 페이지</h3><p className="whitespace-pre-wrap text-sm">{source}</p>{sourceNext && <button className={button} onClick={() => void readSource(sourceNext.ref, sourceNext.cursor)}>다음 부분 읽기</button>}<button className={button} onClick={() => { setSource(''); setSourceNext(null); }}>닫기</button></section>}
    </div>
  </section>;
}
