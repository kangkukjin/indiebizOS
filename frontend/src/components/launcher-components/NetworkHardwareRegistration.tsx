/** Appliances controlled through their network API; no IndieBiz installation. */
import { useState } from 'react';
import { api } from '../../lib/api';

export function NetworkHardwareRegistration({ onSaved }: { onSaved: () => Promise<void> }) {
  const [fields, setFields] = useState({ alias: '', ip: '', mac: '', broadcast: '', token: '', context: '', index: '', youtube: '111299001912', netflix: '3201907018807' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const field = (key: keyof typeof fields, label: string, placeholder = '') => <label className="block text-[11px] text-stone-600">
    {label}<input aria-label={label} type={key === 'token' ? 'password' : 'text'} value={fields[key]}
      placeholder={placeholder} autoComplete="off" disabled={busy}
      onChange={e => { setFields({ ...fields, [key]: e.target.value }); setSaved(false); }}
      className="mt-1 w-full rounded border border-stone-200 bg-white px-2 py-1 text-xs" />
  </label>;
  const save = async () => {
    setBusy(true); setError(''); setSaved(false);
    try {
      const apps = { ...(fields.youtube.trim() ? { youtube: fields.youtube.trim() } : {}), ...(fields.netflix.trim() ? { netflix: fields.netflix.trim() } : {}) };
      await api.request('/remote-pcs/hardware', { method: 'POST', body: JSON.stringify({
        alias: fields.alias, driver: 'samsung-tizen', context: fields.context,
        connection: { ip: fields.ip.trim(), ...(fields.mac.trim() ? { mac: fields.mac.trim() } : {}),
          ...(fields.broadcast.trim() ? { broadcast: fields.broadcast.trim() } : {}), token: fields.token.trim(), apps,
          ...(fields.index.trim() ? { pc_input_index: Number(fields.index) } : {}) },
      }) });
      setFields({ ...fields, alias: '', ip: '', mac: '', broadcast: '', token: '', context: '', index: '' });
      setSaved(true);
      await onSaved();
    } catch (e) { setError(e instanceof Error ? e.message : '기기를 등록하지 못했습니다.'); }
    finally { setBusy(false); }
  };
  return <details className="mt-3 rounded border border-stone-200 bg-stone-50 px-2.5 py-2">
    <summary className="cursor-pointer font-medium text-stone-700">네트워크 기기 등록 · 삼성 TV</summary>
    <p className="my-2 text-[11px] leading-relaxed text-stone-500">TV에 IndieBiz OS를 설치하지 않아도 됩니다. 이 허브에서 TV 주소에 접근할 수 있어야 합니다. 등록 후 TV 컨트롤 앱에서 연결을 허용하세요.</p>
    <div className="grid grid-cols-2 gap-2">
      {field('alias', '기기 이름', '거실TV')}{field('ip', 'TV IPv4 주소', '192.168.…')}
      {field('mac', 'MAC 주소 · 켜기에 필요')}{field('broadcast', '브로드캐스트 주소 · 켜기에 필요')}
      {field('index', 'PC 입력 위치 · 선택', '1부터 시작')}{field('context', '배치·용도 · 선택', '연결된 PC와 입력 정보')}
    </div>
    <details className="my-2 text-[11px] text-stone-500"><summary className="cursor-pointer">앱 ID·기존 페어링 설정</summary>
      <p className="my-1">앱 ID는 TV 모델에 따라 다를 수 있습니다. 기존 토큰이 없으면 비워 두세요.</p>
      <div className="grid grid-cols-2 gap-2">{field('youtube', '유튜브 앱 ID')}{field('netflix', '넷플릭스 앱 ID')}{field('token', '기존 페어링 토큰 · 선택')}</div>
    </details>
    <button disabled={busy || !fields.alias.trim() || !fields.ip.trim()} onClick={() => void save()}
      className="mt-2 rounded bg-stone-800 px-2 py-1 text-[11px] text-white disabled:opacity-50">{busy ? '등록 중…' : '손발에 등록'}</button>
    {saved && <p role="status" className="mt-2 text-[11px] text-emerald-700">등록했습니다. TV 컨트롤 앱에서 기기를 선택하세요.</p>}
    {error && <p role="alert" className="mt-2 text-[11px] text-red-600">{error}</p>}
  </details>;
}
