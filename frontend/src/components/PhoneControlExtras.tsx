import { useEffect, useRef, useState } from 'react';
import { runPhoneAction, type HardwareOp, type HardwareState } from '../lib/phone-actions';

const button = 'px-3 py-2 rounded-lg border border-stone-200 bg-white text-sm hover:bg-stone-50 disabled:opacity-40 disabled:cursor-not-allowed';
const sensorNames: Record<string, string> = { light: '조도 (lx)', proximity: '근접 (cm)', accelerometer: '가속도 (m/s²)', gyroscope: '자이로 (rad/s)', magnetic_field: '자기장 (µT)', pressure: '기압 (hPa)' };
const yn = (value: boolean | undefined | null) => value == null ? '미확인' : value ? '켜짐' : '꺼짐';

export function PhoneControlExtras({ target, disabled, onBusy }: {
  target: string; disabled: boolean; onBusy: (busy: boolean) => void;
}) {
  const [state, setState] = useState<HardwareState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [sensor, setSensor] = useState('');
  const [reading, setReading] = useState('');
  const [elapsed, setElapsed] = useState<number | null>(null);
  const mounted = useRef(true), flight = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const run = async (op: HardwareOp, args: Record<string, unknown> = {}) => {
    if (!target || disabled || flight.current) return;
    flight.current = true; setBusy(true); onBusy(true); setError(''); setNotice('');
    const start = performance.now();
    try {
      const result = await runPhoneAction(target, op, args);
      if (!mounted.current) return;
      if (result.hardware_control !== undefined) setState(result);
      if (result.reading) setReading(`${sensorNames[result.sensor || ''] || result.sensor}: ${result.reading.values.map(n => n.toFixed(3)).join(', ')} · 정확도 ${result.reading.accuracy}`);
      setNotice((result.message || '처리했습니다.') + (result.verified === false ? ' · 요청은 전달됐으며 실제 변경은 미확인입니다.' : ''));
      setElapsed((performance.now() - start) / 1000);
    } catch (e) {
      if (mounted.current) { setError(e instanceof Error ? e.message : String(e)); setState(null); setReading(''); setElapsed(null); }
    } finally {
      flight.current = false;
      if (mounted.current) { setBusy(false); onBusy(false); }
    }
  };
  const caps = state?.capabilities || {};
  const blocked = disabled || busy || !target;
  const ready = !blocked && state?.hardware_control === 1;
  const canSettings = ready && caps.settings_write;
  return <section className="rounded-2xl border border-stone-200 bg-white p-5 space-y-5" aria-busy={busy}>
    <div className="flex justify-between items-center gap-2">
      <h2 className="font-medium text-stone-900">화면 · 손전등 · 센서</h2>
      <button className="text-sm text-emerald-700 disabled:text-stone-400" disabled={blocked} onClick={() => void run('status')}>기기 상태 조회</button>
    </div>
    {!state && <p className="text-sm text-stone-500">기기 상태를 조회하면 사용할 수 있는 기능이 표시됩니다.</p>}
    {state?.hardware_control === 0 && <p className="text-sm text-amber-700">기본 상태만 지원하는 폰 앱입니다. 새 기능을 사용하려면 폰 앱을 업데이트하세요.</p>}
    {state && <div className="text-sm text-stone-600 space-y-1">
      <p>화면 {yn(state.screen_on)} · 잠금 {state.locked ? '잠김' : state.locked === false ? '해제됨' : '미확인'} · 배터리 {state.battery}%{state.charging ? ' 충전 중' : ''}</p>
      <p>Wi-Fi {yn(state.wifi_enabled)} · 연결 {state.network_transports?.join(', ') || '미확인'} · 절전 {yn(state.power_save)}</p>
    </div>}
    <div className="space-y-2">
      <h3 className="text-sm font-medium">화면 전원</h3>
      <div className="flex flex-wrap gap-2">
        <button className={button} disabled={!ready || !caps.screen_on} onClick={() => void run('screen_on')}>화면 켜기</button>
        <button className={button} disabled={!ready || !caps.screen_off} onClick={() => void run('screen_off')}>화면 끄기 · 잠금</button>
      </div>
      {ready && (!caps.screen_on || !caps.screen_off) && <p className="text-xs text-stone-500">화면 켜기는 다른 앱 위에 표시 권한, 끄기는 폰의 접근성 서비스가 필요합니다.</p>}
    </div>
    <div className="space-y-2">
      <h3 className="text-sm font-medium">밝기{state?.brightness != null && state.brightness >= 0 ? ` · ${Math.round(state.brightness / 255 * 100)}%` : ''}{state?.brightness_auto ? ' · 자동' : ''}</h3>
      <div className="flex flex-wrap gap-2">
        {[25, 50, 75, 100].map(n => <button key={n} className={button} disabled={!canSettings} onClick={() => void run('brightness', { value: Math.round(n / 100 * 255) })}>{n}%</button>)}
        <button className={button} disabled={!canSettings} onClick={() => void run('brightness_auto', { enabled: true })}>자동 밝기</button>
      </div>
      <h3 className="text-sm font-medium pt-2">화면 회전 · {yn(state?.auto_rotate)}</h3>
      <div className="flex flex-wrap gap-2">
        <button className={button} disabled={!canSettings} onClick={() => void run('rotation', { enabled: true })}>자동 회전</button>
        <button className={button} disabled={!canSettings} onClick={() => void run('rotation', { enabled: false })}>현재 방향 고정</button>
      </div>
      <h3 className="text-sm font-medium pt-2">화면 자동 꺼짐{state?.screen_timeout_ms != null ? ` · ${state.screen_timeout_ms / 1000}초` : ''}</h3>
      <div className="flex flex-wrap gap-2">{[30, 60, 120, 300].map(seconds => <button key={seconds} className={button} disabled={!canSettings} onClick={() => void run('timeout', { seconds })}>{seconds < 60 ? `${seconds}초` : `${seconds / 60}분`}</button>)}</div>
      {ready && !caps.settings_write && <div className="text-sm text-amber-700 space-y-2"><p>밝기·회전·자동 꺼짐은 폰에서 시스템 설정 변경을 허용해야 합니다.</p><button className={button} onClick={() => void run('settings_permission')}>폰에서 권한 설정 열기</button></div>}
    </div>
    <div className="space-y-2">
      <h3 className="text-sm font-medium">손전등</h3>
      {state?.torches?.map(torch => <div key={torch.id} className="flex flex-wrap items-center gap-2 text-sm"><span>조명 {torch.id} · {yn(torch.enabled)}</span>
        <button className={button} disabled={!ready || !caps.camera_permission || !torch.available} onClick={() => void run('torch', { camera_id: torch.id, enabled: true })}>켜기</button>
        <button className={button} disabled={!ready || !caps.camera_permission || !torch.available} onClick={() => void run('torch', { camera_id: torch.id, enabled: false })}>끄기</button>
      </div>)}
      {ready && (!caps.camera_permission || !state?.torches?.length) && <p className="text-xs text-stone-500">카메라 권한과 플래시 지원이 필요합니다.</p>}
    </div>
    <div className="space-y-2">
      <h3 className="text-sm font-medium">센서 한 번 읽기</h3>
      <div className="flex gap-2"><select aria-label="센서 선택" value={sensor} disabled={!ready} onChange={e => { setSensor(e.target.value); setReading(''); }} className="min-w-0 flex-1 rounded-lg border border-stone-200 p-2 bg-white text-sm">
        <option value="">센서 선택</option>{state?.sensors?.map(s => <option key={s.id} value={s.id}>{sensorNames[s.id] || s.id}</option>)}
      </select><button className={button} disabled={!ready || !sensor} onClick={() => void run('sensor', { sensor })}>읽기</button></div>
      {reading && <p className="text-sm text-stone-600 tabular-nums">{reading}</p>}
    </div>
    <div aria-live="polite" className="text-sm">{busy ? <p>폰에서 처리 중…</p> : error ? <p role="alert" className="text-red-700">{error}</p> : <p className="text-emerald-800">{notice}{elapsed !== null ? ` (${elapsed.toFixed(1)}초)` : ''}</p>}</div>
  </section>;
}
