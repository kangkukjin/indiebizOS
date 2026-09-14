import { useCallback, useEffect, useState } from 'react';
import { Copy, ExternalLink, RefreshCw, Users } from 'lucide-react';
import { ToolWindowFrame } from './ToolWindowFrame';
import { api } from '../lib/api';
import type { VocabularyPackage } from '../lib/api-packages';
import { BACKEND_ORIGIN } from '../lib/backend-origin';
import { openExternalLink } from '../lib/surface-navigation';

type Person = { id: number; name: string; level: number };
type Address = { url: string; warning: string };
type MemberKey = {
  device_id: string; neighbor_id: number; name: string; alias: string;
  level: number | null; revoked: boolean; expired: boolean; approved: boolean;
  linked: boolean; connected: boolean; expires_at: number | null;
  turns_today: number; daily_limit: number;
};
type Overview = {
  address: Address; people: Person[]; keys: MemberKey[];
  daily_turns: number; global_daily_turns: number; notice: string;
};
type Invitation = { key: string; name: string; alias: string; address: Address };
const button = 'inline-flex items-center justify-center gap-1.5 rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm hover:bg-stone-50 disabled:opacity-40';
const input = 'rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm min-w-0';
const panel = 'rounded-xl border border-stone-200 bg-white p-5 space-y-4';

function status(row: MemberKey) {
  if (row.revoked) return '폐기됨';
  if (row.expired) return '만료됨';
  if (!row.linked) return '이웃 연결 없음';
  if (!row.approved) return '잠김';
  return row.connected ? '접속 중' : '사용 가능';
}

export function ExternalUsersView() {
  const [data, setData] = useState<Overview | null>(null);
  const [packages, setPackages] = useState<VocabularyPackage[]>([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [personId, setPersonId] = useState('');
  const [name, setName] = useState('');
  const [alias, setAlias] = useState('');
  const [ttl, setTtl] = useState('0');
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [showKey, setShowKey] = useState(false);
  const [revokeId, setRevokeId] = useState('');
  const [showInactive, setShowInactive] = useState(false);

  const load = useCallback(async () => {
    const [overview, vocabulary] = await Promise.all([
      api.request<Overview>('/external-users'), api.getVocabulary(),
    ]);
    setData(overview);
    setPackages(vocabulary.packages.filter(p => !!p.member_words?.length));
  }, []);

  const run = async (work: () => Promise<void>) => {
    setBusy(true); setError(''); setMessage('');
    try { await work(); }
    catch (e) { setError(e instanceof Error ? e.message : '처리하지 못했습니다'); }
    finally { setBusy(false); }
  };

  useEffect(() => {
    const refresh = () => { void load().catch(e => setError(String(e))); };
    refresh();
    window.addEventListener('vocabulary-changed', refresh);
    return () => window.removeEventListener('vocabulary-changed', refresh);
  }, [load]);

  const copy = async (value: string) => {
    await navigator.clipboard.writeText(value);
    setMessage('복사했습니다.');
  };
  const issue = async () => {
    setInvitation(null); setShowKey(false);
    const result = await api.request<Invitation>('/external-users/invite', {
      method: 'POST', body: JSON.stringify({ ...(personId ? { neighbor_id: Number(personId) } : { name: name.trim() }), alias, ttl_days: Number(ttl) }),
    });
    setInvitation(result);
    await load();
  };
  const rows = data?.keys.filter(row => showInactive || (!row.revoked && !row.expired)) || [];

  return <ToolWindowFrame title="외부사용자 관리" icon={<Users size={21} className="text-stone-600" />}
    actions={<button className={button} disabled={busy} onClick={() => void run(load)}><RefreshCw size={14} />새로고침</button>}>
    <main className="flex-1 overflow-auto text-stone-700">
      <div className="mx-auto max-w-5xl space-y-5 p-5">
        {error && <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
        {message && <div role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{message}</div>}
        {!data ? <p className="py-8 text-center text-sm">{error ? '새로고침으로 다시 불러올 수 있습니다.' : '관리 정보를 불러오는 중…'}</p> : <>
          <section className={panel}>
            <div><h2 className="font-semibold text-lg">외부사용자 작업 공간</h2>
              <p className="mt-1 text-sm text-stone-500">이 주소와 초대 키를 받은 사람은 브라우저에서 작업 공간을 엽니다.</p></div>
            {data.address.url ? <div className="flex flex-wrap items-center gap-2">
              <input aria-label="외부사용자 페이지 주소" readOnly value={data.address.url} className={`${input} w-full sm:flex-1`} />
              <button className={button} disabled={busy} onClick={() => void run(() => copy(data.address.url))}><Copy size={14} />주소 복사</button>
              <button className={button} onClick={() => openExternalLink(data.address.url)}><ExternalLink size={14} />페이지 열기</button>
            </div> : <p className="text-sm text-amber-800">{data.address.warning}</p>}
            <button className="text-sm underline underline-offset-4" onClick={() => openExternalLink(`${BACKEND_ORIGIN}/m/app`)}>이 기기에서 페이지 확인</button>
          </section>

          <section className={panel}>
            <div><h2 className="font-semibold">사용자 초대</h2><p className="mt-1 text-sm text-stone-500">이름을 입력하고 키를 발급하면 바로 초대할 수 있습니다. 기능별 허가는 필요하지 않습니다.</p></div>
            <form className="flex flex-wrap items-end gap-3" onSubmit={e => { e.preventDefault(); void run(issue); }}>
              <label className="grid w-full sm:flex-1 gap-1 text-xs">사용자<select className={input} value={personId} onChange={e => setPersonId(e.target.value)}>
                <option value="">새 사용자 초대</option>{data.people.map(p => <option key={p.id} value={p.id}>{p.name} · #{p.id}</option>)}
              </select></label>
              {!personId && <label className="grid w-full sm:flex-1 gap-1 text-xs">이름<input className={input} required maxLength={100} value={name} onChange={e => setName(e.target.value)} placeholder="초대할 사람의 이름" /></label>}
              <label className="grid w-full sm:flex-1 gap-1 text-xs">키 이름 (선택)<input className={input} value={alias} maxLength={100} placeholder="예: 민수 노트북" onChange={e => setAlias(e.target.value)} /></label>
              <label className="grid gap-1 text-xs">유효기간<select className={input} value={ttl} onChange={e => setTtl(e.target.value)}><option value="0">무기한</option><option value="7">7일</option><option value="30">30일</option><option value="90">90일</option><option value="365">1년</option></select></label>
              <button className={`${button} !bg-stone-800 !text-white`} disabled={busy || (!personId && !name.trim())}>초대 키 발급</button>
            </form>
            {invitation && <div className="space-y-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4">
              <p className="font-medium">{invitation.name} · {invitation.alias} 키 발급 완료</p>
              <p className="text-xs">키는 이 화면에서만 다시 볼 수 있습니다. 주소와 키를 복사해 보관하세요.</p>
              <div className="flex flex-wrap gap-2"><input aria-label="발급된 초대 키" readOnly type={showKey ? 'text' : 'password'} value={invitation.key} className={`${input} w-full sm:flex-1`} />
                <button className={button} onClick={() => setShowKey(!showKey)}>{showKey ? '키 숨기기' : '키 보기'}</button>
                <button className={button} disabled={busy} onClick={() => void run(() => copy(invitation.key))}>키 복사</button>
                <button className={button} disabled={busy || !invitation.address.url} onClick={() => void run(() => copy(`작업 공간: ${invitation.address.url}\n초대 키: ${invitation.key}\n브라우저에서 주소를 열고 초대 키를 입력하세요.`))}>초대 안내 복사</button>
                <button className={button} onClick={() => setInvitation(null)}>닫기</button>
              </div>
            </div>}
          </section>

          <section className={panel}>
            <div className="flex flex-wrap justify-between gap-2"><h2 className="font-semibold">발급 현황</h2><label className="flex gap-2 text-sm"><input type="checkbox" checked={showInactive} onChange={e => setShowInactive(e.target.checked)} />폐기·만료 포함</label></div>
            <p className="text-xs text-stone-500">오늘 사용량은 사람별 대화 횟수입니다. 같은 사람의 키는 사용량을 공유합니다. 전체 회원 일일 한도: {data.global_daily_turns}회.</p>
            {!rows.length ? <p className="text-sm text-stone-500">표시할 초대 키가 없습니다.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm">
              <thead className="border-b text-xs text-stone-500"><tr>{['사용자 / 키', '상태', '만료일', '오늘 사용', '관리'].map(t => <th key={t} className="pb-3 pr-4 font-medium">{t}</th>)}</tr></thead>
              <tbody>{rows.map(row => <tr key={row.device_id} className="border-b last:border-0">
                <td className="py-3 pr-4"><p className="font-medium">{row.name} <span className="text-xs font-normal text-stone-500">#{row.neighbor_id}</span></p><p className="text-xs text-stone-500">{row.alias}</p></td>
                <td className="pr-4 whitespace-nowrap">{status(row)}</td>
                <td className="pr-4 whitespace-nowrap">{row.expires_at ? new Date(row.expires_at * 1000).toLocaleDateString('ko-KR') : '무기한'}</td>
                <td className="pr-4 whitespace-nowrap">{row.turns_today} / {row.daily_limit}회</td>
                <td className="py-3">{!row.revoked && (revokeId === row.device_id ? <div className="flex flex-wrap gap-2">
                  <button className={`${button} text-red-700`} disabled={busy} onClick={() => void run(async () => {
                    await api.request(`/external-users/keys/${encodeURIComponent(row.device_id)}`, { method: 'DELETE' });
                    setRevokeId(''); setInvitation(null); await load(); setMessage('키를 폐기했습니다. 이 키로는 더 이상 접속할 수 없습니다.');
                  })}>폐기 확인</button><button className={button} disabled={busy} onClick={() => setRevokeId('')}>취소</button>
                </div> : <button className={button} disabled={busy} onClick={() => setRevokeId(row.device_id)}>키 폐기</button>)}</td>
              </tr>)}</tbody>
            </table></div>}
          </section>

          <section className={panel}>
            <div><h2 className="font-semibold">외부사용자 기능</h2><p className="mt-1 text-sm text-stone-500">외부사용자가 쓸 수 있는 기능은 기본으로 모두 제공됩니다. 사람마다 허가할 필요가 없습니다. 아래 설정은 모든 외부사용자에게 공통으로 적용됩니다.</p></div>
            {!packages.length ? <p className="text-sm text-stone-500">회원에게 공개할 수 있는 묶음이 없습니다.</p> : <div className="grid gap-3 sm:grid-cols-2">{packages.map(pkg => <label key={pkg.id} className="flex gap-3 rounded-lg border border-stone-200 p-3">
              <input type="checkbox" aria-label={`${pkg.name} 공개`} className="mt-1" checked={!!pkg.member_active} disabled={busy || !pkg.installed} onChange={e => {
                const active = e.target.checked;
                void run(async () => {
                  const result = await api.setVocabularyActive(pkg.id, active, 'member');
                  if (!result.success) throw new Error(result.message || '공개 설정을 바꾸지 못했습니다');
                  await load(); window.dispatchEvent(new Event('vocabulary-changed'));
                });
              }} />
              <span className="min-w-0"><span className="block text-sm font-medium">{pkg.name}</span><span className="block text-xs text-stone-500">{pkg.member_words?.length}개 기능{!pkg.installed && ' · 내 어휘에서 먼저 깨워 주세요'}</span><span className="mt-1 block text-xs text-stone-500 break-words">{pkg.description}</span></span>
            </label>)}</div>}
            {data.notice && <div className="rounded-lg bg-stone-50 p-3"><h3 className="text-xs font-medium">현재 회원 고지문</h3><p className="mt-1 whitespace-pre-wrap text-sm">{data.notice}</p></div>}
          </section>
        </>}
      </div>
    </main>
  </ToolWindowFrame>;
}
