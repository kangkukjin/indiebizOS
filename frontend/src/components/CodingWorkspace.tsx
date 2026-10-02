import { useCallback, useEffect, useRef, useState } from 'react';
import { BACKEND_ORIGIN } from '../lib/backend-origin';
import { useRetryingLoad } from '../lib/use-retrying-load';
import './coding-workspace.css';

type Repo = { id: string; path: string; kind: string; existing_changes: string };
type Task = { id: string; repository_id: string; goal: string; workspace: string; active_run: string | null; kind: string };
type Executor = { id: string; provider: string; model: string; ready: boolean; reason: string; path_restriction: string };
type Verification = { id: string; command: string; state: string; fresh: boolean; exit_code: number | null };
type Review = { id: string; paths: string[]; patch: string; fingerprint: string; approved: boolean; verifications: Verification[] };
type Run = { id: string; message: string; response: string; state: string; error?: string; executor: Executor | null };
type Apply = { state: string; commit?: string; error?: string; message?: string };
type Detail = { task: Task; files: string[]; untracked: string[]; runs: Run[]; review: Review | null; apply: Apply | null };
type Event = { sequence: number; type: string; run_id: string; body: Record<string, unknown> };
type OpenFile = { path: string; text: string; fingerprint: string; binary: boolean; truncated: boolean; size: number };

async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`${BACKEND_ORIGIN}/coding${path}`, {
    method, credentials: 'include', headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok) throw new Error(String(value.detail || response.statusText));
  return value as T;
}

const stateLabel: Record<string, string> = {
  running: '실행 중', completed: '완료', failed: '실패', interrupted: '중단', cancelled: '취소',
  commit_pending: '파일 반영됨 · 커밋 재시도 필요', PENDING_APPLY: '반영 대기',
  PENDING_REVIEW: '평가 재개 대기', recovery_required: '복구 필요', passed: '통과',
};

export function CodingWorkspace() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [executors, setExecutors] = useState<Executor[]>([]);
  const [repository, setRepository] = useState('');
  const [taskId, setTaskId] = useState(() => localStorage.getItem('coding-task') || '');
  const [detail, setDetail] = useState<Detail | null>(null);
  const [path, setPath] = useState('');
  const [goal, setGoal] = useState('');
  const [message, setMessage] = useState('');
  const [executor, setExecutor] = useState('system');
  const [command, setCommand] = useState('');
  const [commitMessage, setCommitMessage] = useState('');
  const [file, setFile] = useState<OpenFile | null>(null);
  const [draft, setDraft] = useState('');
  const [tab, setTab] = useState<'diff' | 'file'>('diff');
  const [mobileTab, setMobileTab] = useState('review');
  const [attached, setAttached] = useState(false);
  const [selectionStart, setSelectionStart] = useState(1);
  const [selectionEnd, setSelectionEnd] = useState(100);
  const [selectedNew, setSelectedNew] = useState<string[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const taskRef = useRef(taskId);
  taskRef.current = taskId;
  const cursor = useRef(0);
  const active = !!detail?.task.active_run;

  const load = useCallback(async () => {
    const state = await request<{ repositories: Repo[]; tasks: Task[]; executors: Executor[] }>('/state');
    setRepos(state.repositories); setTasks(state.tasks); setExecutors(state.executors);
    setExecutor(current => state.executors.some(x => x.id === current && x.ready) ? current : state.executors.find(x => x.ready)?.id || '');
  }, []);
  const { retrying } = useRetryingLoad(load, { onFocus: true });
  const refresh = useCallback(async () => {
    if (!taskId) return;
    const value = await request<Detail>(`/tasks/${taskId}`);
    if (taskRef.current === taskId) { setDetail(value); setRepository(value.task.repository_id); }
  }, [taskId]);
  useRetryingLoad(refresh, { enabled: !!taskId, onFocus: true });

  useEffect(() => {
    localStorage.setItem('coding-task', taskId);
    setDetail(null); setFile(null); setAttached(false); setEvents([]); setSelectedNew([]); setMessage(''); setCommand(''); setCommitMessage(''); setError(''); cursor.current = 0;
    if (!taskId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const page = await request<{ items: Event[]; next: number; has_more: boolean }>(`/tasks/${taskId}/events?after=${cursor.current}`);
        if (stopped) return;
        cursor.current = page.next;
        setEvents(old => [...old, ...page.items.filter(e => !old.some(o => o.sequence === e.sequence))].slice(-1000));
        await refresh();
        if (!stopped) timer = setTimeout(tick, page.has_more ? 10 : 1500);
      } catch (e) {
        if (!stopped) { setError(String(e)); timer = setTimeout(tick, 3000); }
      }
    };
    void tick();
    return () => { stopped = true; clearTimeout(timer); };
  }, [taskId, refresh]);

  const act = async (fn: () => Promise<unknown>) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true); setError('');
    try { await fn(); await load(); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { busyRef.current = false; setBusy(false); }
  };
  const openFile = (name: string) => act(async () => {
    const id = taskId;
    const opened = await request<OpenFile>(`/tasks/${id}/file?path=${encodeURIComponent(name)}`);
    if (taskRef.current !== id) return;
    setFile(opened); setDraft(opened.text); setTab('file'); setAttached(false);
  });
  const review = detail?.review;
  const downloadDiff = () => {
    if (!review) return;
    const url = URL.createObjectURL(new Blob([review.patch], { type: 'text/plain' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${review.id}.patch`; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const outputs = events.filter(e => ['command.finished', 'provider.tool_result', 'provider.error'].includes(e.type));

  return <main className="coding-app">
    <header className="coding-header">
      <button onClick={() => { window.location.hash = ''; }}>← 런처</button><strong>코딩</strong>
      <span>변경을 보고, 검증하고, 반영합니다</span>
      {retrying && <span role="status">백엔드 연결 중…</span>}
      <span className="coding-spacer" />
      {active && <button className="coding-danger" onClick={() => void act(() => request(`/tasks/${taskId}/cancel`, 'POST'))}>실행 중단</button>}
    </header>
    {error && <div className="coding-error" role="alert">{error}<button onClick={() => setError('')}>닫기</button></div>}
    <nav className="coding-mobile-tabs">{[['tasks', '과제'], ['review', '변경'], ['chat', '대화']].map(([id, label]) =>
      <button key={id} aria-pressed={mobileTab === id} onClick={() => setMobileTab(id)}>{label}</button>)}</nav>
    <div className={`coding-panels coding-mobile-${mobileTab}`}>
      <aside className="coding-sidebar">
        <h2>저장소</h2>
        <form onSubmit={e => { e.preventDefault(); void act(async () => {
          const repo = await request<Repo>('/repositories', 'POST', { path }); setRepository(repo.id); setPath('');
        }); }}><input aria-label="저장소 경로" value={path} onChange={e => setPath(e.target.value)} placeholder="기존 Git 저장소의 절대경로" />
          <button disabled={busy || !path}>열기</button></form>
        <select aria-label="저장소" value={repository} onChange={e => setRepository(e.target.value)}>
          <option value="">저장소 선택</option>{repos.map(r => <option key={r.id} value={r.id}>{r.path}</option>)}
        </select>
        {repos.find(r => r.id === repository)?.existing_changes && <p className="coding-note">기존 변경이 있습니다. 과제는 HEAD에서 시작하며 기존 변경은 가져오지 않습니다.</p>}
        <h2>과제</h2>
        <form onSubmit={e => { e.preventDefault(); void act(async () => {
          const task = await request<Task>('/tasks', 'POST', { repository_id: repository, goal }); setTaskId(task.id); setGoal('');
        }); }}><textarea aria-label="새 과제 목표" value={goal} onChange={e => setGoal(e.target.value)} placeholder="이번에 바꿀 것과 완료 기준" />
          <button disabled={busy || !repository || !goal}>과제 시작</button></form>
        <div className="coding-task-list">{tasks.map(t => <button key={t.id} disabled={busy} className={t.id === taskId ? 'selected' : ''}
          onClick={() => { setTaskId(t.id); setRepository(t.repository_id); }}>{t.goal}</button>)}</div>
        <h2>파일</h2>
        <div className="coding-file-list">{detail?.files.map(name => <div key={name}>
          {detail.untracked.includes(name) && <input type="checkbox" aria-label={`${name} 검토 포함`} checked={selectedNew.includes(name)}
            onChange={e => setSelectedNew(old => e.target.checked ? [...old, name] : old.filter(n => n !== name))} />}
          <button disabled={busy} onClick={() => void openFile(name)} title={name}>{name}</button>
        </div>)}</div>
        {!!detail?.untracked.length && <p className="coding-note">새 파일은 체크한 항목을 검토에 포함합니다.</p>}
      </aside>
      <section className="coding-center">
        <div className="coding-toolbar"><button aria-pressed={tab === 'diff'} onClick={() => setTab('diff')}>변경 비교</button>
          <button aria-pressed={tab === 'file'} onClick={() => setTab('file')}>파일 원문</button><span className="coding-spacer" />
          <button disabled={!taskId || active || busy} onClick={() => void act(async () => {
            await request(`/tasks/${taskId}/review`, 'POST', { selected: selectedNew }); setTab('diff');
          })}>검토 묶음 갱신</button></div>
        <h1>{detail?.task.goal || '저장소를 열고 개발 과제를 시작하세요'}</h1>
        {detail && <p className="coding-note">작업 공간: {detail.task.workspace}</p>}
        <div className="coding-content">
          {tab === 'diff' ? review ? <>
            <div className="coding-note">{review.paths.length}개 파일 · 검토 {review.fingerprint.slice(0, 12)} <button onClick={downloadDiff}>원문 패치 저장</button></div>
            {review.patch.length > 200000 && <p>큰 diff의 앞부분만 표시합니다. 원문 패치로 전체를 확인하세요.</p>}
            <pre className="coding-diff">{review.patch.slice(0, 200000).split('\n').map((line, i) =>
              <div key={i} className={line.startsWith('+') ? 'added' : line.startsWith('-') ? 'removed' : line.startsWith('@@') ? 'hunk' : ''}>{line || ' '}</div>)}</pre>
            {!review.paths.length && <p>이번 과제에서 변경된 파일이 없습니다.</p>}
          </> : <div className="coding-empty">수정 후 검토 묶음을 갱신하면 시작 시점과의 차이를 볼 수 있습니다.</div>
          : file ? <>
            <div className="coding-toolbar"><strong>{file.path}</strong><span>{file.size.toLocaleString()} B</span>
              <button disabled={active || busy || file.binary || file.truncated || draft === file.text} onClick={() => void act(async () => {
                const saved = await request<OpenFile>(`/tasks/${taskId}/file`, 'PUT', { path: file.path, content: draft, expected: file.fingerprint }); setFile(saved);
              })}>변경 저장</button></div>
            {file.binary ? <p>바이너리 파일입니다. 변경은 원문 패치에 보존됩니다.</p> : <>
              {file.truncated && <p>200KB를 넘는 파일의 일부입니다. 간단 편집으로 저장할 수 없습니다.</p>}
              <textarea className="coding-editor" aria-label="파일 내용" spellCheck={false} readOnly={active || file.truncated} value={draft} onChange={e => setDraft(e.target.value)} />
              <label><input type="checkbox" checked={attached} onChange={e => setAttached(e.target.checked)} /> 다음 지시에 파일 첨부</label>
              <label> 시작 줄 <input type="number" min={1} value={selectionStart} onChange={e => setSelectionStart(Number(e.target.value))} /></label>
              <label> 끝 줄 <input type="number" min={1} value={selectionEnd} onChange={e => setSelectionEnd(Number(e.target.value))} /></label>
            </>}
          </> : <p>왼쪽에서 파일을 선택하세요.</p>}
        </div>
        <section className="coding-verification"><h2>검증과 반영</h2>
          <form onSubmit={e => { e.preventDefault(); void act(() => request(`/tasks/${taskId}/verify`, 'POST', { command, command_id: crypto.randomUUID() })); }}>
            <input aria-label="검증 명령" value={command} onChange={e => setCommand(e.target.value)} placeholder="예: python3 -m pytest tests/test_calc.py" />
            <button disabled={!taskId || active || busy || !command}>검증 실행</button></form>
          {review?.verifications.map(v => <div key={v.id} className="coding-note">{stateLabel[v.state] || v.state} · {v.fresh ? '현재 변경과 일치' : '파일 변경으로 오래됨'} · {v.command}</div>)}
          <div className="coding-toolbar"><input aria-label="커밋 메시지" value={commitMessage} onChange={e => setCommitMessage(e.target.value)} placeholder="커밋 메시지" />
            <button disabled={busy || active || !review?.paths.length} onClick={() => void act(() => request(`/tasks/${taskId}/approve`, 'POST', { review_id: review?.id, fingerprint: review?.fingerprint }))}>검토 완료</button>
            <button className="coding-primary" disabled={busy || active || !review?.approved || !commitMessage} onClick={() => void act(() => request(`/tasks/${taskId}/apply`, 'POST', {
              review_id: review?.id, fingerprint: review?.fingerprint, command_id: `apply-${review?.id}`, message: commitMessage,
            }))}>{detail?.task.kind === 'repair' ? 'RED 적용 예약' : '정본 반영·커밋'}</button></div>
          {detail?.apply && <p role="status">{stateLabel[detail.apply.state] || detail.apply.state} {detail.apply.commit} {detail.apply.error}</p>}
        </section>
        <details className="coding-output" open><summary>실행 출력 · 최근 1,000개 사건</summary>
          {outputs.map(e => <pre key={e.sequence}><button onClick={() => setMessage(old => old + `\n출력 참조 ${e.run_id}/${e.sequence}:\n` + String(e.body.output || e.body.result || e.body.content || '').slice(0, 6000))}>지시에 첨부</button>
            {String(e.body.command || e.body.name || e.type)}{'\n'}{String(e.body.output || e.body.result || e.body.content || '')}</pre>)}
        </details>
      </section>
      <aside className="coding-chat"><h2>AI와 작업</h2>
        <select aria-label="실행자" value={executor} disabled={active} onChange={e => setExecutor(e.target.value)}>
          {executors.map(x => <option key={x.id} value={x.id} disabled={!x.ready}>{x.provider} · {x.model}{x.ready ? '' : ' (사용 불가)'}</option>)}
        </select>{executors.filter(x => !x.ready).map(x => <p key={x.id} className="coding-note">{x.provider}: {x.reason}</p>)}<p className="coding-note">실행이 끝나면 모델을 바꿀 수 있습니다. 파일과 과제 기록은 이어집니다.</p>
        <div className="coding-messages">{detail?.runs.slice().reverse().map(r => <article key={r.id}>
          <p className="coding-user">{r.message}</p><small>{r.executor?.model || '검증 명령'} · {stateLabel[r.state] || r.state}</small>
          <p>{r.response || r.error || '결과를 기다리는 중…'}</p></article>)}</div>
        <form onSubmit={e => { e.preventDefault(); void act(async () => {
          await request(`/tasks/${taskId}/runs`, 'POST', { message, executor, command_id: crypto.randomUUID(),
            selection: attached && file ? { path: file.path, fingerprint: file.fingerprint, start_line: selectionStart, end_line: selectionEnd } : null }); setMessage('');
        }); }}>
          {attached && file && <p className="coding-note">첨부: {file.path} · {selectionStart}–{selectionEnd}줄</p>}
          <textarea aria-label="AI 지시" value={message} onChange={e => setMessage(e.target.value)} placeholder="무엇을 바꾸고 어떻게 확인할까요?" />
          <button className="coding-primary" disabled={!taskId || active || busy || !message || !executors.some(x => x.id === executor && x.ready)}>실행</button>
        </form>
      </aside>
    </div>
  </main>;
}
