import { useCallback, useEffect, useRef, useState } from 'react';
import { Copy, ExternalLink, Laptop, Plus, RefreshCw, X } from 'lucide-react';
import { api } from '../lib/api';
import { openExternalLink } from '../lib/surface-navigation';
import { ToolWindowFrame } from './ToolWindowFrame';

type PCStatus = 'pending' | 'online' | 'offline' | 'disabled' | 'expired' | 'revoked';
type PC = {
  device_id: string; name: string; user_label: string; note: string; enabled: boolean;
  status: PCStatus; created_at: number; expires_at: number | null; last_seen: number | null;
  host: string; os: string; client: string; turns_today: number; tokens_today: number;
  active_tasks: number; daily_limit: number;
};
type Address = { url: string; warning: string };
type Overview = { address: Address; pcs: PC[]; daily_limit: number; global_daily_limit: number };
type Issued = { key: string; alias: string; device_id: string; expires_at: number | null; address: Address };
const statuses: Record<PCStatus, string> = {
  pending: '연결 대기', online: '연결됨', offline: '오프라인', disabled: '사용 중지', expired: '키 만료', revoked: '등록 해제',
};
const button = 'inline-flex items-center justify-center gap-1.5 rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm hover:bg-stone-50 disabled:opacity-40';
const input = 'rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm min-w-0';
const panel = 'rounded-xl border border-stone-200 bg-white p-5';
function date(value: number | null) { return value ? new Date(value * 1000).toLocaleString() : '아직 연결하지 않음'; }

export function MemberPCsView() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [userLabel, setUserLabel] = useState('');
  const [note, setNote] = useState('');
  const [ttl, setTtl] = useState('0');
  const [issued, setIssued] = useState<Issued | null>(null);
  const [showKey, setShowKey] = useState(false);
  const [query, setQuery] = useState('');
  const [showRevoked, setShowRevoked] = useState(false);
  const [confirm, setConfirm] = useState<{ pc: PC; action: 'disable' | 'rotate' | 'revoke' } | null>(null);
  const sequence = useRef(0);
  const load = useCallback(async () => {
    const id = ++sequence.current;
    const result = await api.request<Overview>('/member-pcs');
    if (id === sequence.current) { setData(result); setError(''); }
  }, []);
  useEffect(() => {
    let alive = true;
    const refresh = () => { if (!document.hidden) void load().catch(e => { if (alive) setError(String(e)); }); };
    refresh();
    const timer = window.setInterval(refresh, 15000);
    document.addEventListener('visibilitychange', refresh);
    return () => { alive = false; sequence.current++; clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [load]);
  const run = async (work: () => Promise<void>) => {
    setBusy(true); setError(''); setMessage('');
    try { await work(); } catch (e) { setError(e instanceof Error ? e.message : '처리하지 못했습니다'); }
    finally { setBusy(false); }
  };
  const copy = async (value: string) => { await navigator.clipboard.writeText(value); setMessage('복사했습니다.'); };
  const edit = (pc?: PC) => {
    setEditing(pc?.device_id ?? ''); setName(pc?.name ?? ''); setUserLabel(pc?.user_label ?? '');
    setNote(pc?.note ?? ''); setTtl('0');
  };
  const save = async () => {
    if (editing) {
      await api.request(`/member-pcs/${encodeURIComponent(editing)}`, {
        method: 'PATCH', body: JSON.stringify({ name: name.trim(), user_label: userLabel.trim(), note: note.trim() }),
      });
      setMessage('PC 등록 정보를 저장했습니다.');
    } else {
      const value = await api.request<Issued>('/member-pcs', { method: 'POST',
        body: JSON.stringify({ name: name.trim(), user_label: userLabel.trim(), note: note.trim(), ttl_days: Number(ttl) }),
      });
      setIssued(value); setShowKey(false); setMessage('회원 PC를 등록했습니다. 등록 키로 해당 PC를 연결하세요.');
    }
    setEditing(null); await load();
  };
  const manage = async () => {
    if (!confirm) return;
    const { pc, action } = confirm;
    const path = `/member-pcs/${encodeURIComponent(pc.device_id)}`;
    if (action === 'rotate') {
      const value = await api.request<Issued>(`${path}/key`, { method: 'POST' });
      setIssued(value); setShowKey(false);
    } else {
      await api.request(path, action === 'revoke' ? { method: 'DELETE' } : { method: 'PATCH', body: JSON.stringify({ enabled: false }) });
      if (issued?.device_id === pc.device_id) setIssued(null);
    }
    setConfirm(null); await load();
    setMessage(action === 'rotate' ? '이전 키를 폐기하고 새 키를 발급했습니다.' : action === 'revoke' ? '등록을 해제했습니다. PC의 파일은 삭제하지 않습니다.' : '사용을 중지했습니다. 신규 요청과 명령 전달을 차단했습니다.');
  };
  const pcs = data?.pcs ?? [];
  const rows = pcs.filter(pc => (showRevoked || pc.status !== 'revoked') &&
    `${pc.name} ${pc.user_label} ${pc.host}`.toLowerCase().includes(query.toLowerCase()));

  return <ToolWindowFrame title="회원 PC 관리" icon={<Laptop size={21} className="text-stone-600" />}
    actions={<button className={button} disabled={busy} onClick={() => void run(load)}><RefreshCw size={14} />새로고침</button>}>
    <main className="flex-1 overflow-auto bg-stone-50 text-stone-700"><div className="mx-auto max-w-6xl space-y-5 p-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div><h1 className="text-xl font-semibold">각자의 PC에서 함께 쓰는 IndieBiz</h1>
          <p className="mt-2 text-sm text-stone-500">이웃 명부와 별도로 PC를 등록합니다. 이곳에서는 연결과 사용 현황을 관리합니다.</p></div>
        <button className={`${button} !bg-stone-800 !text-white`} disabled={busy} onClick={() => edit()}><Plus size={16} />PC 등록</button>
      </header>
      {error && <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {message && <div role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{message}</div>}
      {data && <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['등록 PC', pcs.filter(p => p.status !== 'revoked').length], ['연결됨', pcs.filter(p => p.status === 'online').length],
          ['처리 중', pcs.reduce((sum, p) => sum + p.active_tasks, 0)], ['오늘 요청', pcs.reduce((sum, p) => sum + p.turns_today, 0)],
        ].map(([label, value]) => <div key={label} className={panel}><p className="text-xs text-stone-500">{label}</p><p className="mt-2 text-2xl font-semibold">{value}</p></div>)}
      </div>}
      {editing !== null && <section className={panel}>
        <div className="mb-4 flex justify-between"><h2 className="font-semibold">{editing ? 'PC 정보 수정' : '새 회원 PC 등록'}</h2>
          <button aria-label="등록 양식 닫기" disabled={busy} onClick={() => setEditing(null)}><X size={18} /></button></div>
        <form onSubmit={e => { e.preventDefault(); void run(save); }} className="grid gap-4 sm:grid-cols-2">
          <label className="grid gap-1 text-xs">PC 이름<input autoFocus required maxLength={100} className={input} value={name} onChange={e => setName(e.target.value)} placeholder="예: 사무실 노트북" /></label>
          <label className="grid gap-1 text-xs">사용자 표시명 (선택)<input maxLength={100} className={input} value={userLabel} onChange={e => setUserLabel(e.target.value)} placeholder="이웃 명부에 추가되지 않습니다" /></label>
          <label className="grid gap-1 text-xs sm:col-span-2">메모 (선택)<textarea maxLength={1000} className={input} value={note} onChange={e => setNote(e.target.value)} /></label>
          {!editing && <label className="grid gap-1 text-xs">등록 키 유효기간<select className={input} value={ttl} onChange={e => setTtl(e.target.value)}><option value="0">무기한</option><option value="7">7일</option><option value="30">30일</option><option value="90">90일</option><option value="365">1년</option></select></label>}
          <div className="flex items-end gap-2"><button className={`${button} !bg-stone-800 !text-white`} disabled={busy || !name.trim()}>{editing ? '변경 저장' : '등록하고 키 발급'}</button><button type="button" className={button} disabled={busy} onClick={() => setEditing(null)}>취소</button></div>
        </form>
      </section>}
      {issued && <section className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50 p-5">
        <div className="flex justify-between"><h2 className="font-semibold">{issued.alias} 연결 준비</h2><button aria-label="발급 정보 닫기" onClick={() => setIssued(null)}><X size={18} /></button></div>
        <p className="text-sm">이 등록 키는 해당 PC에만 전달하세요. 키를 닫은 뒤에는 다시 볼 수 없으며 재발급할 수 있습니다.</p>
        <div className="flex flex-wrap gap-2"><input aria-label="회원 PC 등록 키" type={showKey ? 'text' : 'password'} readOnly value={issued.key} className={`${input} w-full sm:flex-1`} />
          <button className={button} onClick={() => setShowKey(!showKey)}>{showKey ? '숨기기' : '보기'}</button>
          <button className={button} disabled={busy} onClick={() => void run(() => copy(issued.key))}><Copy size={14} />키 복사</button>
          <button className={button} disabled={busy || !issued.address.url} onClick={() => void run(() => copy(`회원 PC: ${issued.alias}\n접속 주소: ${issued.address.url}\n등록 키: ${issued.key}\n이 키는 해당 PC에서만 사용하세요.`))}>연결 안내 복사</button>
        </div>
        <p className="text-xs text-stone-600">웹 접속은 브라우저 기능을 제공합니다. 실제 로컬 폴더·명령 실행에는 회원용 PC 연결 프로그램이 필요합니다.</p>
      </section>}
      <section className={`${panel} space-y-4`}>
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">등록 현황</h2>
          <div className="flex flex-wrap items-center gap-3"><input aria-label="회원 PC 검색" className={input} value={query} onChange={e => setQuery(e.target.value)} placeholder="PC · 사용자 · 호스트 검색" />
            <label className="flex gap-2 text-xs"><input type="checkbox" checked={showRevoked} onChange={e => setShowRevoked(e.target.checked)} />해제한 PC 포함</label></div></div>
        <p className="text-xs text-stone-500">15초마다 갱신합니다. 사용량은 등록 PC별로 집계합니다. 중앙 전체 일일 한도: {data?.global_daily_limit ?? '—'}회.</p>
        {!data ? <p className="py-8 text-center text-sm">{error ? '새로고침으로 다시 시도하세요.' : '등록 정보를 불러오는 중…'}</p> : !rows.length ? <div className="py-10 text-center"><Laptop className="mx-auto mb-3 text-stone-400" size={30} /><p>{query ? '검색 결과가 없습니다.' : '등록된 회원 PC가 없습니다.'}</p><p className="mt-2 text-sm text-stone-500">PC 등록으로 기기 이름을 정하고 연결 키를 발급하세요.</p></div> :
          <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b text-xs text-stone-500"><tr>{['PC / 사용자', '연결 상태', '최근 접속', '오늘 사용', '관리'].map(label => <th key={label} className="pb-3 pr-4 font-medium">{label}</th>)}</tr></thead>
            <tbody>{rows.map(pc => <tr key={pc.device_id} className="border-b last:border-0">
              <td className="py-4 pr-4 min-w-44"><p className="font-medium">{pc.name}</p><p className="text-xs text-stone-500">{pc.user_label || '사용자 표시명 없음'}</p>{pc.note && <p className="mt-1 max-w-64 break-words text-xs text-stone-500">{pc.note}</p>}<p className="mt-1 text-xs text-stone-400">{pc.device_id}</p></td>
              <td className="pr-4"><span className={`inline-block whitespace-nowrap rounded-full px-2 py-1 text-xs ${pc.status === 'online' ? 'bg-emerald-100 text-emerald-800' : 'bg-stone-100 text-stone-600'}`}>{statuses[pc.status]}</span>
                <p className="mt-2 text-xs text-stone-500">{pc.host || '기기 연결 전'}{pc.os && ` · ${pc.os}`}</p><p className="text-xs text-stone-500">{pc.client === 'web' ? '브라우저' : pc.client === 'native' ? 'PC 연결 프로그램' : ''}</p></td>
              <td className="pr-4 whitespace-nowrap text-xs"><p>{date(pc.last_seen)}</p><p className="mt-2 text-stone-500">{pc.expires_at ? `만료 ${new Date(pc.expires_at * 1000).toLocaleDateString()}` : '만료 없음'}</p></td>
              <td className="pr-4 whitespace-nowrap"><p>{pc.turns_today} / {pc.daily_limit}회</p><p className="mt-1 text-xs text-stone-500">처리 중 {pc.active_tasks}건</p></td>
              <td className="py-3 min-w-40">{pc.status !== 'revoked' && <div className="flex flex-wrap gap-1.5">
                <button className={button} disabled={busy} onClick={() => edit(pc)}>수정</button>
                {pc.enabled ? <button className={button} disabled={busy} onClick={() => setConfirm({ pc, action: 'disable' })}>사용 중지</button> :
                  <button className={button} disabled={busy} onClick={() => void run(async () => { await api.request(`/member-pcs/${encodeURIComponent(pc.device_id)}`, { method: 'PATCH', body: JSON.stringify({ enabled: true }) }); await load(); setMessage('사용을 재개했습니다. 회원 PC에서 다시 연결하세요.'); })}>사용 재개</button>}
                <button className={button} disabled={busy} onClick={() => setConfirm({ pc, action: 'rotate' })}>키 재발급</button>
                <button className={`${button} text-red-700`} disabled={busy} onClick={() => setConfirm({ pc, action: 'revoke' })}>등록 해제</button>
              </div>}</td>
            </tr>)}</tbody></table></div>}
      </section>
      {data && <section className={`${panel} space-y-3`}><h2 className="font-semibold">회원 접속 주소</h2>
        {data.address.url ? <div className="flex flex-wrap gap-2"><input aria-label="회원 접속 주소" readOnly value={data.address.url} className={`${input} w-full sm:flex-1`} /><button className={button} disabled={busy} onClick={() => void run(() => copy(data.address.url))}><Copy size={14} />주소 복사</button><button className={button} onClick={() => openExternalLink(data.address.url)}><ExternalLink size={14} />열기</button></div> : <p className="text-sm text-amber-800">{data.address.warning}</p>}
        <p className="text-xs text-stone-500">기존 이웃 기반 외부사용자와 주인용 원격 PC는 이 목록에 자동으로 편입되지 않습니다.</p>
      </section>}
    </div></main>
    {confirm && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"><section role="dialog" aria-modal="true" aria-labelledby="pc-action-title" className="w-full max-w-md space-y-4 rounded-xl bg-white p-6 shadow-xl">
      <h2 id="pc-action-title" className="font-semibold">{confirm.pc.name} · {confirm.action === 'rotate' ? '키 재발급' : confirm.action === 'revoke' ? '등록 해제' : '사용 중지'}</h2>
      <p className="text-sm text-stone-600">{confirm.action === 'rotate' ? '이전 키는 더 이상 사용할 수 없습니다. 기존 유효기간 설정으로 새 키를 발급하며 해당 PC에서 다시 연결해야 합니다.' : confirm.action === 'revoke' ? '이 PC의 중앙 서비스 이용을 해제합니다. 다시 쓰려면 새로 등록해야 합니다. PC의 파일과 로컬 기록은 삭제하지 않습니다.' : '새 요청과 명령 전달을 막고 중앙의 진행 작업에 중단을 요청합니다. 다시 허용하면 재연결할 수 있습니다.'}</p>
      <p className="text-xs text-stone-500">이미 PC에서 시작된 명령의 즉시 종료는 보장하지 않습니다.</p>
      <div className="flex justify-end gap-2"><button className={button} disabled={busy} onClick={() => setConfirm(null)}>취소</button><button className={`${button} !bg-stone-800 !text-white`} disabled={busy} onClick={() => void run(manage)}>확인</button></div>
    </section></div>}
  </ToolWindowFrame>;
}
