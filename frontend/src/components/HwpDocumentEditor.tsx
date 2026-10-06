import { useEffect, useRef, useState, type MutableRefObject, type ReactNode } from 'react';
import type { RhwpDocumentStateV1 } from '@rhwp/editor';
import { BACKEND_ORIGIN } from '../lib/backend-origin';
import { documentCommand, documentRequest, sessionArgs, type Detail, type Session } from '../lib/api-documents';

type Props = { tabs?: ReactNode; detail: Detail; captureRef: MutableRefObject<(() => Promise<Session>) | null>; onChange: (d: Detail) => void; onSaved?: (d: Detail) => void };
type Exported = { data: Uint8Array; state: RhwpDocumentStateV1 };
type Pending = { data: Uint8Array; state: RhwpDocumentStateV1; query: string };
const same = (a: RhwpDocumentStateV1 | null, b: RhwpDocumentStateV1) => a?.documentEpoch === b.documentEpoch && a?.changeSeq === b.changeSeq && a?.documentSha256 === b.documentSha256;

export function HwpDocumentEditor({ tabs, detail, captureRef, onChange, onSaved }: Props) {
  const [tools, setTools] = useState(false);
  const frame = useRef<HTMLIFrameElement>(null);
  const latest = useRef(detail); latest.current = detail;
  const changed = useRef(onChange); changed.current = onChange;
  const [channel] = useState(() => crypto.randomUUID());
  const origin = new URL(BACKEND_ORIGIN || location.origin).origin;
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('로컬 한글 편집기를 불러오는 중…');
  const [filename, setFilename] = useState(detail.document.title.replace(/\.(hwp|hwpx)$/i, '_edited.$1'));
  const [versions, setVersions] = useState<{ id: string; created_at: number }[]>([]);
  const requests = useRef(new Map<string, { resolve: (v: unknown) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }>());
  const lastState = useRef<RhwpDocumentStateV1 | null>(null);
  const pending = useRef<Pending | null>(null);
  const saving = useRef<Promise<Session> | null>(null);
  const saveRequest = useRef<Record<string, unknown> | null>(null);
  const loaded = useRef(false);
  const mounted = useRef(true);
  const acting = useRef(false);
  const actionTask = useRef<Promise<void> | null>(null);
  const saveAction = useRef<() => void>(() => {});
  const rpc = <T,>(op: string, args: unknown = {}): Promise<T> => new Promise((resolve, reject) => {
    const id = crypto.randomUUID();
    const timer = setTimeout(() => { requests.current.delete(id); reject(new Error('한글 편집기 응답 시간이 초과되었습니다')); }, 90000);
    requests.current.set(id, { resolve: value => resolve(value as T), reject, timer });
    frame.current?.contentWindow?.postMessage({ channel, id, op, args }, origin);
  });
  const publish = (session: Session) => {
    const next = { ...latest.current, session }; latest.current = next;
    if (mounted.current) changed.current(next);
  };
  const capture = async (): Promise<Session> => {
    if (!loaded.current) throw new Error('한글 문서를 불러온 뒤 저장하세요');
    if (saving.current) { await saving.current; return capture(); }
    const task = (async () => {
      const d = latest.current;
      if (!d.session) throw new Error('편집 세션이 없습니다');
      if (!pending.current) {
        const state = await rpc<RhwpDocumentStateV1>('state');
        if (same(lastState.current, state)) return d.session;
        const exported = await rpc<Exported>('export', { format: d.document.source_format });
        const values = { ...sessionArgs(d.session), operation_id: crypto.randomUUID() };
        pending.current = { ...exported, query: new URLSearchParams(Object.entries(values).map(([k, v]) => [k, String(v)])).toString() };
      }
      const request = pending.current;
      const response = await fetch(`${BACKEND_ORIGIN}/documents/${d.document.id}/hwp-draft?${request.query}`, {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/octet-stream' },
        body: new Blob([new Uint8Array(request.data)]),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || '한글 초안 저장 실패');
      publish(result.session); lastState.current = request.state; pending.current = null;
      // Never clear the engine recovery draft while a newer edit is present.
      await rpc('ack', { state: request.state });
      if (mounted.current) setMessage('작업 초안 저장됨 · 원본 저장은 별도입니다');
      return result.session as Session;
    })();
    saving.current = task;
    try { return await task; } finally { saving.current = null; }
  };
  const act = async (fn: () => Promise<void>) => {
    if (acting.current) return;
    acting.current = true; setBusy(true); setError('');
    const task = Promise.resolve().then(fn); actionTask.current = task;
    try { await task; } catch (e) { if (mounted.current) setError(String(e)); }
    finally { actionTask.current = null; acting.current = false; if (mounted.current) setBusy(false); }
  };
  const save = () => act(async () => {
    const session = await capture(), d = latest.current;
    saveRequest.current ??= { ...sessionArgs(session), operation_id: crypto.randomUUID(), expected_revision: d.document.revision_id };
    await documentCommand(d.document.id, 'save', saveRequest.current);
    saveRequest.current = null;
    const next = await documentRequest<Detail>(`/${d.document.id}`);
    latest.current = next; changed.current(next);
    onSaved?.(next);
    const state = await rpc<RhwpDocumentStateV1>('state');
    setMessage(same(lastState.current, state) ? '원본 저장됨 · 파일 기록 확인' : '이전 초안은 원본 저장됨 · 새 편집 내용은 미저장');
  });
  saveAction.current = () => { void save(); };

  useEffect(() => {
    mounted.current = true;
    const listener = (event: MessageEvent) => {
      if (event.origin !== origin || event.source !== frame.current?.contentWindow || event.data?.channel !== channel) return;
      if (event.data.event === 'save') { saveAction.current(); return; }
      const request = requests.current.get(event.data.id);
      if (!request) return;
      clearTimeout(request.timer); requests.current.delete(event.data.id);
      if (event.data.error) request.reject(new Error(event.data.error)); else request.resolve(event.data.result);
    };
    window.addEventListener('message', listener);
    // A stable callback uses latest refs across acknowledged session revisions.
    captureRef.current = async () => {
      // A document switch waits for the whole save/restore action and its
      // final detail response, preventing a late response from reopening it.
      if (actionTask.current) await actionTask.current;
      return capture();
    };
    const timer = setInterval(() => {
      if (loaded.current && !acting.current && !saving.current)
        void capture().catch(e => { if (mounted.current) setError(String(e)); });
    }, 4000);
    // 창 닫기를 무조건 막지 않는다 — 한글 문서를 열어 둔 것만으로 창이 닫히지 않았다(Electron 은 묻지 않고 그냥 안 닫는다).
    // 초안은 4초마다 서버에 올라가고, 아직 못 올린 변경이 있으면 RHWP 편집기 자신이 닫기를 붙잡는다(메인 프로세스가 사람에게 묻는다).
    return () => {
      mounted.current = false; loaded.current = false; captureRef.current = null;
      clearInterval(timer); window.removeEventListener('message', listener);
      requests.current.forEach(r => { clearTimeout(r.timer); r.reject(new Error('편집기가 닫혔습니다')); });
      requests.current.clear();
    };
  }, []);

  const load = async () => {
    try {
      const d = latest.current;
      if (!d.session) return;
      const query = new URLSearchParams(Object.entries(sessionArgs(d.session)).map(([k, v]) => [k, String(v)]));
      const response = await fetch(`${BACKEND_ORIGIN}/documents/${d.document.id}/hwp-content?${query}`, { credentials: 'include' });
      if (!response.ok) throw new Error('한글 문서 초안을 불러오지 못했습니다');
      await rpc('load', { data: await response.arrayBuffer(), filename: d.document.title });
      lastState.current = await rpc<RhwpDocumentStateV1>('state');
      if (!mounted.current) return;
      loaded.current = true; setReady(true); setMessage('문서를 열었습니다 · 원본 형식으로 편집합니다');
    } catch (e) { if (mounted.current) setError(String(e)); }
  };
  // 화면에는 편집기와 ⚙ 도구 한 줄만 둔다 — 편집기가 자기 메뉴·저장(Ctrl/Cmd+S → 원본 저장)을 갖고 있으므로
  // 작업 저장·복구·버전·사본·안내는 ⚙ 안에 접는다. 계기 탭(새 문서·열기…)도 같은 패널 맨 위에 선다(tabs).
  return <section aria-label="한글 문서 편집기">
    <div className="document-toolbar">
      <button onClick={() => setTools(v => !v)} aria-expanded={tools}>⚙ 도구</button>
      <p role="status">{busy ? '저장 처리 중…' : message}</p>
    </div>
    {error && <p role="alert">{error}</p>}
    {tools && <>
      {tabs}
    <div className="document-toolbar">
      <button disabled={!ready || busy} onClick={() => void act(async () => { await capture(); })}>작업 저장</button>
      <button disabled={!ready || busy} onClick={() => void save()}>원본 저장</button>
      <button disabled={!ready || busy} onClick={() => void act(async () => {
        const result = await documentCommand<{ detail: Detail; items: { state: string }[] }>(latest.current.document.id, 'recover');
        latest.current = result.detail; changed.current(result.detail); saveRequest.current = null;
        setMessage(result.items.length ? '저장 복구 확인됨 · 현재 초안 유지' : '미완료 저장 없음');
      })}>저장 상태 복구</button>
      <button disabled={!ready || busy} onClick={() => void act(async () => {
        setVersions((await documentRequest<{ items: { id: string; created_at: number }[] }>(`/${detail.document.id}/versions`)).items);
      })}>버전 이력</button>
    </div>
    {!!versions.length && <section aria-label="한글 저장 버전">{versions.map(v => <button key={v.id} disabled={busy} onClick={() => void act(async () => {
      const s = await capture(), d = latest.current;
      await documentCommand(d.document.id, 'restore', { ...sessionArgs(s), operation_id: crypto.randomUUID(), revision_id: v.id });
      changed.current(await documentRequest<Detail>(`/${d.document.id}`));
    })}>{new Date(v.created_at * 1000).toLocaleString()} · 초안으로 복구</button>)}</section>}
    <div className="document-export"><label>사본 파일명<input value={filename} onChange={e => setFilename(e.target.value)} /></label>
      <button disabled={!ready || busy || !filename} onClick={() => void act(async () => {
        const s = await capture(), d = latest.current;
        const result = await documentCommand<{ path: string }>(d.document.id, 'export', { ...sessionArgs(s), operation_id: crypto.randomUUID(), filename });
        setMessage(`사본 저장됨: ${result.path}`);
      })}>사본 저장</button></div>
      <p>HWP/HWPX · 로컬 오픈소스 편집. 대체 글꼴과 복잡한 서식의 쪽 배치는 원본과 다를 수 있습니다.</p>
    <small>RHWP 0.8.6 · MIT · 본 제품은 한컴의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다.</small>
    </>}
    <iframe ref={frame} title="로컬 HWP 편집 화면" onLoad={() => void load()}
      src={`${BACKEND_ORIGIN}/documents/hwp-assets/host.html?channel=${channel}`}
      style={{ width: '100%', height: 'calc(100vh - 64px - var(--app-chrome, 0px))', minHeight: 480, border: '1px solid #e7e5e4', borderRadius: 12 }} />
  </section>;
}
