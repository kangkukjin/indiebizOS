import { useCallback, useEffect, useRef, useState } from 'react';
import { getBackendOrigin } from '../lib/backend-origin';

type Link = { source_ref: string; label: string; status?: string };
type Event = { source: string; source_record_id: string; kind: string; observed_at: string | null;
  summary: Record<string, unknown>; diagnostics: string[]; observations?: Event[];
  links: { relation?: string; source_record_id?: string }[] };
type Trace = { status: string; reason?: string; partial: boolean; cursor_expired?: boolean;
  identity?: { task_id: string; project: string | null; owner: string | null };
  state?: { task: string; runtime: { status: string }; assessment: string; episodes: { id: number; ended_at: string | null }[] };
  events: Event[]; sources: { source: string; status: string; reason?: string }[];
  diagnostics?: string[]; next_cursor: string | null;
  usage?: { measured: Record<string, number>; records: number; unattributed_records: number };
  links?: { documents: Link[]; evidence: Link[];
    parents: { task_id?: string; run_id?: string }[]; children: { task_id: string; status?: string }[];
    pursuits: { pursuit_id: string; status: string; version: number; turn_state: string }[] } };
type Page = { status: string; reason?: string; text?: string; chars?: number; next_offset?: number | null; next_cursor?: string | null };

const labels: Record<string, string> = { ok: '조회됨', empty: '범위 내 0건', missing: '기록·연결 없음',
  unavailable: '조회 실패', malformed: '형식 오류', partial: '일부 조회', forbidden: '접근 제한',
  running: '실행 관측', completed: '완료', pending: '대기', unknown: '미확인', conflict: '상태 충돌',
  unconfirmed: '실행 여부 미확인', observed: '실행 관측' };
const reasons: Record<string, string> = {
  cursor_expired: '기록이나 상태가 바뀌어 페이지가 만료되었습니다. 새로 조회해 주세요.',
  scope_identity_missing: '프로젝트·자아 연결을 확인할 수 없습니다.',
  scope_lookup_incomplete: '일부 저장소를 읽지 못해 프로젝트·자아를 확정하지 못했습니다.',
  no_task_foreign_key: '대화에 작업 연결 키가 없어 메시지를 연결하지 않았습니다.',
  source_missing: '원본이 없거나 보존 범위를 벗어났습니다.',
  page_budget: '이번 조회 한도에 도달했습니다. 다음 페이지에서 이어집니다.',
  response_not_approved: '현재 응답의 검수 승인을 확인할 수 없습니다.',
  read_budget_or_lock: 'DB 잠금 또는 읽기 시간 한도로 조회하지 못했습니다.',
  invalid_reference: '이 조회 범위에서 사용할 수 없는 참조입니다.',
  access_denied: '이 기록의 읽기 권한이 없습니다.',
};
const label = (v: string) => labels[v] ?? v;
const reason = (v?: string) => v ? reasons[v] ?? v : '';
const button = 'rounded border bg-white px-2 py-1 disabled:opacity-50';

function mergeEvents(old: Event[], incoming: Event[]) {
  const map = new Map<string, Event>();
  for (const row of [...old, ...incoming]) if (!map.has(row.source_record_id)) {
    map.set(row.source_record_id, { ...row, observations: [...(row.observations ?? [])] });
  }
  for (const [id, row] of map) {
    const targetId = row.links.find(l => l.relation === 'observation_of')?.source_record_id;
    const target = targetId ? map.get(targetId) : undefined;
    if (target?.kind === 'side_effect.write' && row.source === 'writes') {
      if (!target.observations?.some(o => o.source_record_id === id)) target.observations?.push(row);
      map.delete(id);
    }
  }
  return [...map.values()];
}

export function ExecutionTraceDetail({ episodeId }: { episodeId: number }) {
  const [trace, setTrace] = useState<Trace | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [doc, setDoc] = useState<{ link: Link; page: Page } | null>(null);
  const [docBusy, setDocBusy] = useState(false);
  const generation = useRef(0);
  const docGeneration = useRef(0);
  const load = useCallback(async (cursor: string | null = null) => {
    const request = ++generation.current;
    setBusy(true); setError('');
    if (!cursor) { setTrace(null); setDoc(null); ++docGeneration.current; setDocBusy(false); }
    try {
      const res = await fetch(`${await getBackendOrigin()}/world-pulse/episodes/${episodeId}/trace`, {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cursor, limit: 50 }),
      });
      const page: Trace = await res.json();
      if (request !== generation.current) return;
      if (!res.ok || !page.identity || page.cursor_expired) {
        setError(reason(page.reason) || (page.cursor_expired ? reasons.cursor_expired : `조회 실패 (${res.status})`));
        if (page.cursor_expired) setTrace(old => old ? { ...old, next_cursor: null } : old);
        return;
      }
      setTrace(old => cursor && old ? { ...page, events: mergeEvents(old.events, page.events),
        sources: [...new Map([...old.sources, ...page.sources].map(s => [s.source, s])).values()],
        diagnostics: [...new Set([...(old.diagnostics ?? []), ...(page.diagnostics ?? [])])],
        links: page.links && old.links ? { ...page.links,
          evidence: [...new Map([...old.links.evidence, ...page.links.evidence].map(l => [l.source_ref, l])).values()] } : page.links,
      } : { ...page, events: mergeEvents([], page.events) });
    } catch { if (request === generation.current) setError('기록을 불러오지 못했습니다. 연결을 확인하고 다시 조회해 주세요.'); }
    finally { if (request === generation.current) setBusy(false); }
  }, [episodeId]);
  const invalidate = useCallback(() => { ++generation.current; ++docGeneration.current; }, []);
  useEffect(() => { void load(); return invalidate; }, [load, invalidate]);

  const read = async (link: Link, previous?: Page) => {
    const request = ++docGeneration.current;
    setDocBusy(true);
    if (!previous) setDoc({ link, page: { status: 'loading' } });
    try {
      const res = await fetch(`${await getBackendOrigin()}/world-pulse/episodes/${episodeId}/trace/document`, {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_ref: link.source_ref, offset: previous?.next_offset ?? 0,
          cursor: previous?.next_cursor ?? null, limit: 12000 }),
      });
      const page: Page = await res.json();
      if (request === docGeneration.current) setDoc({ link,
        page: previous && page.status === 'ok' ? { ...page, text: (previous.text ?? '') + (page.text ?? '') } : page });
    } catch { if (request === docGeneration.current) setDoc({ link, page: { status: 'unavailable', reason: '네트워크 연결을 확인해 주세요.' } }); }
    finally { if (request === docGeneration.current) setDocBusy(false); }
  };
  return <section aria-label="통합 실행 기록" className="space-y-3 p-3 text-xs text-stone-700">
    <div className="flex items-center justify-between gap-2"><b>작업의 사건 · 상태 · 비용 · 증거</b>
      <button className={button} disabled={busy} onClick={() => void load()}>새로 조회</button></div>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {busy && !trace && <p>원장 조회 중…</p>}
    {trace?.identity && <>
      <p className="break-all text-stone-500">{trace.identity.project ?? '프로젝트 미확인'} · {trace.identity.owner ?? '자아 미확인'} · {trace.identity.task_id || '작업 ID 없음'}</p>
      <div className="flex flex-wrap gap-2 rounded bg-white p-2">
        <span>DB: {label(trace.state?.task ?? 'unknown')}</span><span>현재 실행: {label(trace.state?.runtime.status ?? 'unknown')}</span>
        <span>에피소드 종료 기록: {trace.state?.episodes.filter(e => e.ended_at).length ?? 0}건</span>
        <span className={trace.state?.assessment === 'conflict' ? 'font-bold text-red-700' : 'text-stone-500'}>{label(trace.state?.assessment ?? 'unknown')}</span>
      </div>
      <div className="space-y-1 rounded bg-white p-2"><b>기록된 청구 토큰 · {trace.usage?.records ?? 0}건</b>
        <p>입력 {trace.usage?.measured.input?.toLocaleString() ?? '미측정'} · 출력 {trace.usage?.measured.output?.toLocaleString() ?? '미측정'}</p>
        <p className="text-stone-500">캐시 읽기 {trace.usage?.measured.cache_read?.toLocaleString() ?? '미측정'} · 캐시 생성 {trace.usage?.measured.cache_create?.toLocaleString() ?? '미측정'}</p>
        <p className="text-[11px] text-stone-500">{trace.next_cursor ? '현재 페이지까지의 합계입니다. ' : ''}누적 응답 관측과 작업대 요약은 합산하지 않습니다. 전체 청구액은 미확인입니다.</p>
        {!!trace.usage?.unattributed_records && <p>호출 신원 없는 사용량: {trace.usage.unattributed_records}건</p>}
      </div>
      {trace.partial && <p className="text-amber-800">일부 기록이나 연결이 불완전합니다. 조회의 부분성은 작업의 실패 판정과 별개입니다.</p>}
      <details><summary className="cursor-pointer font-medium">출처별 조회 상태</summary>
        <ul className="mt-2 space-y-1">{trace.sources.map(s => <li key={s.source} className="break-all">{s.source} · {label(s.status)}{s.reason ? ` — ${reason(s.reason)}` : ''}</li>)}</ul>
        <ul className="mt-2 space-y-1 text-stone-500">{trace.diagnostics?.map(d => <li key={d}>{reason(d)}</li>)}</ul>
      </details>
      {trace.links && <details><summary className="cursor-pointer font-medium">부모 · 자식 · 과제 연결</summary>
        <div className="mt-2 space-y-1 break-all">
          {trace.links.parents.map((p, i) => <p key={`p${i}`}>부모: {p.task_id ?? p.run_id}</p>)}
          {trace.links.children.map(c => <p key={c.task_id}>자식: {c.task_id} · {label(c.status ?? 'unknown')}</p>)}
          {trace.links.pursuits.map(p => <p key={p.pursuit_id}>과제: {p.pursuit_id} · {p.status} · v{p.version} · 턴 {p.turn_state}</p>)}
          {!trace.links.parents.length && !trace.links.children.length && !trace.links.pursuits.length && <p>명시된 연결이 없습니다.</p>}
        </div></details>}
      <div className="space-y-2"><b>원문 페이지</b>
        <p className="text-[11px] text-stone-500">직접 열어 읽습니다. 이 조회는 검수 읽기 범위나 승인 상태를 변경하지 않습니다.</p>
        <div className="flex flex-wrap gap-1">{(trace.links?.documents ?? []).map(l =>
          <button key={l.source_ref} className={button} disabled={docBusy} onClick={() => void read(l)}>{l.label}</button>)}</div>
        {!!trace.links?.evidence.length && <details>
          <summary className="cursor-pointer">도구·검수 증거 {trace.links.evidence.length}개</summary>
          <div className="mt-2 max-h-48 overflow-auto space-y-1">{trace.links.evidence.map((l, i) =>
            <button key={`${l.source_ref}:${i}`} className={`${button} block w-full text-left`} disabled={docBusy} onClick={() => void read(l)}>
              {i + 1}. {{input: '도구 입력', result: '도구 결과', evidence: '검수 근거', response: '응답 후보'}[l.label] ?? l.label}
              {l.status && l.status !== 'ok' ? ` · ${label(l.status)}` : ''}
            </button>)}</div>
        </details>}
        {doc && <div className="space-y-2 rounded border bg-white p-2"><b>{doc.link.label}{doc.page.chars !== undefined ? ` · ${doc.page.chars.toLocaleString()}자` : ''}</b>
          {doc.page.status === 'ok' ? <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words text-[11px]">{doc.page.text || '(빈 원문)'}</pre>
            : doc.page.status !== 'loading' && <p role="alert">{label(doc.page.status)} · {reason(doc.page.reason)}</p>}
          {docBusy && <p>원문 읽는 중…</p>}
          {doc.page.next_offset != null && <button className={button} disabled={docBusy} onClick={() => void read(doc.link, doc.page)}>원문 다음 페이지</button>}
        </div>}
      </div>
      <div className="space-y-1"><b>사건 {trace.events.length}건</b>
        <p className="text-[11px] text-stone-500">출처별 기록 순서입니다. 서로 다른 원장의 전역 인과 순서는 보장하지 않습니다.</p>
        {!trace.events.length && <p>현재 페이지에서 조회된 사건이 없습니다. 출처 상태를 확인해 주세요.</p>}
        <div className="max-h-96 divide-y overflow-auto rounded border bg-white">{trace.events.map(e => <details key={e.source_record_id} className="p-2">
          <summary className="cursor-pointer break-all"><span className="font-mono">{e.kind}</span> <span className="text-stone-400">· {e.source}{e.observations?.length ? ` + ${e.observations.length}개 관측` : ''}</span></summary>
          <div className="mt-1 space-y-1 break-all text-[11px]"><p className="text-stone-400">{e.source_record_id} · {e.observed_at ?? '시각의 시간대 미확인'}</p>
            {Object.entries(e.summary).map(([k, v]) => <p key={k}>{k}: {String(v)}</p>)}
            {e.observations?.map(o => <p key={o.source_record_id}>추가 출처: {o.source_record_id}</p>)}
            {e.diagnostics.map(d => <p key={d} className="text-amber-800">{d}</p>)}
          </div></details>)}</div>
      </div>
      {trace.next_cursor && <button className={button} disabled={busy} onClick={() => void load(trace.next_cursor)}>{busy ? '조회 중…' : '사건 다음 페이지'}</button>}
    </>}
  </section>;
}
