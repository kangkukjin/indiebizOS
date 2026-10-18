import { useCallback, useEffect, useRef, useState } from 'react';
import { Monitor, RefreshCw, Volume2, VolumeX, Globe, LockKeyhole, Camera } from 'lucide-react';
import { capturePC, controlPC, listControlPCs, type PCAction, type PCPlatform, type PCState, type PCTarget } from '../lib/pc-control';

const button = 'rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700 hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-40';
const panel = 'rounded-2xl border border-stone-200 bg-white p-5 space-y-4';

export function PCControlInstrument({ platform }: { platform: PCPlatform }) {
  const [targets, setTargets] = useState<PCTarget[]>([]);
  const [selected, setSelected] = useState('');
  const [state, setState] = useState<PCState | null>(null);
  const [deviceId, setDeviceId] = useState('');
  const [draft, setDraft] = useState(0);
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [listing, setListing] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [screen, setScreen] = useState('');
  const [screenAt, setScreenAt] = useState('');
  const targetRef = useRef(''), deviceRef = useRef('');
  const mounted = useRef(false), flight = useRef(false), listFlight = useRef(false), revision = useRef(0);
  const target = targets.find(item => item.id === selected);
  const ready = !!target?.ready && !!target.connected;
  const device = state?.devices?.find(item => item.id === deviceId);
  const title = platform === 'darwin' ? '맥 컨트롤' : 'Windows 컨트롤';

  const refresh = useCallback(async () => {
    if (listFlight.current || flight.current) return;
    listFlight.current = true; setListing(true);
    try {
      const next = await listControlPCs(platform);
      if (!mounted.current) return;
      setTargets(next);
      const current = next.find(item => item.id === targetRef.current);
      if (targetRef.current && (!current?.ready || !current.connected)) {
        revision.current++; setState(null); setScreen(''); setNotice('');
        setError('선택한 PC의 연결 또는 실행 준비 상태가 바뀌었습니다.');
        if (!current) { targetRef.current = ''; setSelected(''); }
      }
    } catch (e) {
      if (mounted.current) {
        setTargets([]); setState(null); setScreen('');
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      listFlight.current = false; if (mounted.current) setListing(false);
    }
  }, [platform]);

  useEffect(() => {
    mounted.current = true; void refresh();
    return () => { mounted.current = false; revision.current++; };
  }, [refresh]);

  const execute = async (id: string, action: PCAction | 'screen', args: Record<string, unknown> = {}) => {
    if (flight.current || !id) return;
    flight.current = true;
    const version = ++revision.current, started = performance.now();
    setBusy(true); setError(''); setNotice(''); setElapsed(null);
    try {
      if (action === 'screen') {
        const image = await capturePC(id);
        if (!mounted.current || targetRef.current !== id || revision.current !== version) return;
        setScreen(image); setScreenAt(new Date().toLocaleTimeString()); setNotice('요청 시점의 원격 화면입니다.');
      } else {
        const next = await controlPC(id, platform, action, args);
        if (!mounted.current || targetRef.current !== id || revision.current !== version) return;
        setState(previous => ({ ...previous, ...next, devices: next.devices ?? previous?.devices }));
        if (next.devices) {
          const output = next.devices.find(item => item.id === deviceRef.current) ??
            (deviceRef.current ? undefined : next.devices.find(item => item.default || item.is_default) ?? next.devices[0]);
          deviceRef.current = output?.id || ''; setDeviceId(deviceRef.current); setDraft(output?.volume ?? 0);
        }
        setNotice(next.message);
      }
      setElapsed((performance.now() - started) / 1000);
    } catch (e) {
      if (!mounted.current || targetRef.current !== id || revision.current !== version) return;
      setError(e instanceof Error ? e.message : String(e));
      if (action === 'screen') setScreen(''); else setState(null);
    } finally {
      flight.current = false; if (mounted.current) setBusy(false);
    }
  };

  const choose = (id: string) => {
    if (flight.current) return;
    revision.current++; targetRef.current = id; deviceRef.current = '';
    setSelected(id); setDeviceId(''); setState(null); setScreen(''); setError(''); setNotice(''); setElapsed(null);
    if (targets.some(item => item.id === id && item.ready && item.connected)) void execute(id, 'status');
  };
  const change = (action: PCAction, args: Record<string, unknown> = {}) => {
    if (ready && !busy && !listing) void execute(selected, action, args);
  };
  const disabled = busy || listing || !ready;

  return <div className="h-full overflow-auto bg-stone-50">
    <div className="max-w-3xl mx-auto p-5 sm:p-8 space-y-5">
      <header className="flex items-center gap-3">
        <span className="p-3 rounded-2xl bg-blue-100 text-blue-800"><Monitor size={26} /></span>
        <div><h1 className="text-xl font-semibold text-stone-900">{title}</h1>
          <p className="text-sm text-stone-500 mt-1">PC를 선택하고 상태와 소리를 바로 조절하세요.</p></div>
      </header>
      <section className={panel}>
        <label htmlFor="pc-control-target" className="text-sm font-medium text-stone-700">제어할 PC</label>
        <div className="flex gap-2">
          <select id="pc-control-target" value={selected} disabled={busy || listing} onChange={e => choose(e.target.value)}
            className="flex-1 min-w-0 rounded-xl border border-stone-200 bg-white p-3">
            <option value="">PC를 선택해 주세요</option>
            {targets.map(item => <option key={item.id} value={item.id} disabled={!item.connected || !item.ready}>
              {item.name}{!item.connected ? ' · 연결 안 됨' : !item.ready ? ' · 실행 중지 또는 헬퍼 확인 필요' : item.local ? ' · 본체' : ' · 원격'}
            </option>)}
          </select>
          <button className={button} disabled={busy || listing} onClick={() => void refresh()} aria-label="PC 목록 새로고침"><RefreshCw size={18} className={listing ? 'animate-spin' : ''} /></button>
        </div>
        {!listing && !targets.length && <p className="text-sm text-stone-500">이 OS의 등록된 PC가 없습니다. 손발에 PC를 연결한 뒤 새로고침하세요.</p>}
        {state && <div className="flex flex-wrap justify-between gap-2 text-xs text-stone-500">
          <span>{state.hostname} · {platform === 'darwin' ? 'macOS' : 'Windows'} {state.os_version}</span>
          <span>관측 {new Date(state.observed_at).toLocaleTimeString()}</span>
        </div>}
      </section>
      <section className={panel} aria-busy={busy}>
        <div className="flex items-center justify-between"><h2 className="font-medium flex items-center gap-2"><Volume2 size={20} />출력 장치와 음량</h2>
          <button disabled={disabled} onClick={() => change('status')} className="text-sm text-blue-700 disabled:opacity-40">상태 새로고침</button></div>
        <select aria-label="제어할 출력 장치" value={deviceId} disabled={disabled || !state?.devices?.length}
          onChange={e => { deviceRef.current = e.target.value; setDeviceId(e.target.value); setDraft(state?.devices?.find(item => item.id === e.target.value)?.volume ?? 0); }}
          className="w-full rounded-xl border border-stone-200 p-3 bg-white">
          <option value="">출력 장치를 선택해 주세요</option>
          {state?.devices?.map(item => <option key={item.id} value={item.id}>{item.name}{item.default || item.is_default ? ' · 기본 출력' : ''}</option>)}
        </select>
        <p className="text-xs text-stone-500">선택한 장치의 음량을 조절합니다. 기본 출력 장치를 바꾸지는 않습니다.</p>
        <div className="text-center py-3"><span className="text-5xl font-semibold tabular-nums">{device?.volume ?? '—'}</span><span className="text-stone-400 ml-1">%</span>
          <p className="text-sm text-stone-500 mt-2">{device ? device.muted === true ? '음소거 켜짐' : device.muted === false ? '음소거 꺼짐' : '음소거 상태 미지원' : '상태를 조회하고 출력 장치를 선택하세요.'}</p></div>
        <label className="block text-sm text-stone-600">설정할 음량 {draft}%
          <input type="range" min={0} max={100} step={1} value={draft} disabled={disabled || !device?.can_set_volume}
            onChange={e => setDraft(Number(e.target.value))} className="w-full mt-3 accent-blue-700" /></label>
        <button className="w-full rounded-xl bg-blue-800 py-3 text-white disabled:opacity-40" disabled={disabled || !device?.can_set_volume || draft === device.volume}
          onClick={() => change('volume', { device_id: deviceId, value: draft })}>선택한 음량 적용</button>
        <div className="grid grid-cols-2 gap-2">
          <button className={button} disabled={disabled || !device?.can_mute || device.muted === true} onClick={() => change('mute', { device_id: deviceId, enabled: true })}><VolumeX className="inline mr-1" size={16} />음소거</button>
          <button className={button} disabled={disabled || !device?.can_mute || device.muted === false} onClick={() => change('mute', { device_id: deviceId, enabled: false })}><Volume2 className="inline mr-1" size={16} />음소거 해제</button>
        </div>
        {device && !device.can_set_volume && <p className="text-sm text-amber-700">이 장치는 OS 음량 조절을 제공하지 않습니다. 외부 장치의 리모컨을 사용하세요.</p>}
        {state?.audio_error && <p className="text-sm text-amber-700">오디오 조회: {state.audio_error}</p>}
      </section>
      <section className={panel}>
        <h2 className="font-medium flex items-center gap-2"><Globe size={20} />웹 주소 열기</h2>
        <div className="flex flex-col sm:flex-row gap-2"><input aria-label="열 웹 주소" value={url} onChange={e => setUrl(e.target.value)} disabled={busy}
          type="url" placeholder="https://…" className="flex-1 min-w-0 rounded-xl border border-stone-200 p-3 text-sm" />
          <button className={button} disabled={disabled || !url.trim()} onClick={() => change('open_url', { url: url.trim() })}>선택한 PC에서 열기</button></div>
        <p className="text-xs text-stone-500">일반 웹페이지를 기본 브라우저로 엽니다. 유튜브 영상은 중복 재생을 막기 위해 여기서 열지 않습니다. 자동 재생 교체는 아직 지원하지 않습니다.</p>
      </section>
      <section className={panel}>
        <div className="flex flex-wrap gap-2">
          <button className={button} disabled={disabled || target?.local} onClick={() => void execute(selected, 'screen')}><Camera className="inline mr-1" size={17} />원격 화면 확인</button>
          <button className={button} disabled={disabled || !state?.can_lock} onClick={() => change('lock')}><LockKeyhole className="inline mr-1" size={17} />선택한 PC 화면 잠금</button>
        </div>
        <p className="text-xs text-stone-500">화면 잠금 뒤에는 해당 PC에서 로그인해야 합니다. 잠금은 종료나 절전과 다릅니다.</p>
        {state && !state.can_lock && <p className="text-xs text-stone-500">이 PC에서 지원하는 잠금 명령을 찾지 못했습니다. PC에서 직접 잠가 주세요.</p>}
        {screen && <figure><img src={screen} alt={`${target?.name} 원격 화면`} className="w-full rounded-xl border border-stone-200" /><figcaption className="text-xs text-stone-500 mt-2">{screenAt}에 가져온 화면 · 실시간 영상 아님</figcaption></figure>}
      </section>
      <div aria-live="polite" className="text-sm min-h-8">
        {busy ? <p className="text-blue-700">{target?.name}에서 처리 중…</p> : error ? <p className="text-red-700">{error}</p> : <p className="text-stone-600">{notice}</p>}
        <p className="text-xs text-stone-400 mt-2">{elapsed !== null ? `${elapsed.toFixed(1)}초 · ` : ''}AI 호출 없음</p>
      </div>
    </div>
  </div>;
}
