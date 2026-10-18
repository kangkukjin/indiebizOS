import { useCallback, useEffect, useRef, useState } from 'react';
import { PhoneControlExtras } from './PhoneControlExtras';
import { Battery, RefreshCw, Smartphone, Volume2, VolumeX, Undo2, Vibrate } from 'lucide-react';
import { controlPhone, listControlPhones, type PhoneCommand, type PhoneState, type PhoneTarget, type PhoneStream } from '../lib/phone-control';

const button = 'px-4 py-3 rounded-xl border border-stone-200 bg-white text-sm text-stone-700 hover:bg-stone-50 disabled:opacity-40 disabled:cursor-not-allowed transition';

/** One explicit target per request; no models, code generation, or automatic mutation retries. */
export function PhoneControlInstrument() {
  const [phones, setPhones] = useState<PhoneTarget[]>([]);
  const [selected, setSelected] = useState('');
  const [stream, setStream] = useState<PhoneStream>('music');
  const streamRef = useRef<PhoneStream>('music');
  const [state, setState] = useState<PhoneState | null>(null);
  const [draft, setDraft] = useState(0);
  const [busy, setBusy] = useState(false);
  const [extrasBusy, setExtrasBusy] = useState(false);
  const [listing, setListing] = useState(false);
  const [error, setError] = useState('');
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [notice, setNotice] = useState('');
  const mounted = useRef(true);
  const target = useRef('');
  const inFlight = useRef(false);
  const listingFlight = useRef(false);
  const revision = useRef(0);
  const phone = phones.find(p => p.id === selected);
  const available = !!phone?.connected && !!phone?.ready;

  const refreshPhones = useCallback(async () => {
    if (listingFlight.current) return;
    listingFlight.current = true;
    setListing(true);
    try {
      const next = await listControlPhones();
      if (!mounted.current) return;
      setPhones(next);
      const current = next.find(p => p.id === target.current);
      if (target.current && (!current?.connected || !current.ready)) {
        revision.current++;
        setState(null); setNotice(''); setElapsed(null);
        setError(current ? '선택한 폰의 연결 또는 실행 준비 상태를 확인해 주세요.' : '선택한 폰의 등록이 변경됐습니다. 다시 선택해 주세요.');
        if (!current) { target.current = ''; setSelected(''); }
      }
    } catch (e) {
      if (mounted.current) {
        revision.current++; setPhones([]); setState(null); setNotice(''); setElapsed(null);
        setError(String(e instanceof Error ? e.message : e));
      }
    } finally {
      listingFlight.current = false;
      if (mounted.current) setListing(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void refreshPhones();
    return () => { mounted.current = false; revision.current++; };
  }, [refreshPhones]);

  const execute = useCallback(async (id: string, op: PhoneCommand, value?: number) => {
    if (!id || inFlight.current) return;
    inFlight.current = true;
    const version = ++revision.current;
    setBusy(true); setError(''); setNotice('');
    const started = performance.now();
    try {
      const result = await controlPhone(id, op, value, streamRef.current);
      if (!mounted.current || target.current !== id || revision.current !== version) return;
      setState(result); setDraft(result.actual); setNotice(result.message);
      setElapsed((performance.now() - started) / 1000);
    } catch (e) {
      if (!mounted.current || target.current !== id || revision.current !== version) return;
      setError(String(e instanceof Error ? e.message : e));
      // A missing reply may follow a successful side effect. Require fresh observation.
      setState(null); setElapsed(null);
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }, []);

  const choose = (id: string) => {
    if (inFlight.current || extrasBusy) return;
    target.current = id; revision.current++;
    setSelected(id); setState(null); setError(''); setNotice(''); setElapsed(null);
    const next = phones.find(p => p.id === id);
    if (next?.connected && next.ready) void execute(id, 'status');
  };
  const change = (op: PhoneCommand, value?: number) => {
    if (available && state && !busy && !extrasBusy) void execute(selected, op, value);
  };
  const disabled = busy || extrasBusy || !available || !state || state.fixed;

  return <div className="h-full overflow-auto bg-stone-50">
    <div className="max-w-2xl mx-auto p-5 sm:p-8 space-y-5">
      <header className="flex items-center gap-3">
        <span className="p-3 rounded-2xl bg-emerald-100 text-emerald-800"><Smartphone size={25} /></span>
        <div><h1 className="text-xl font-semibold text-stone-900">폰 컨트롤</h1>
          <p className="text-sm text-stone-500 mt-1">폰을 선택하고 바로 조절하세요.</p></div>
      </header>

      <section className="rounded-2xl border border-stone-200 bg-white p-5 space-y-3">
        <label htmlFor="phone-control-target" className="text-sm font-medium text-stone-700">제어할 폰</label>
        <div className="flex gap-2">
          <select id="phone-control-target" value={selected} disabled={busy || extrasBusy || listing}
            onChange={e => choose(e.target.value)} className="min-w-0 flex-1 rounded-xl border border-stone-200 p-3 text-stone-900 bg-white">
            <option value="">폰을 선택해 주세요</option>
            {phones.map(p => <option key={p.id} value={p.id} disabled={!p.connected || !p.ready}>
              {p.name}{!p.connected ? ' · 연결 안 됨' : p.paused ? ' · 실행 중지' : !p.ready ? ' · Python 실행 준비 필요' : ' · 연결됨'}
            </option>)}
          </select>
          <button className={button} disabled={busy || extrasBusy || listing} onClick={() => void refreshPhones()} aria-label="폰 목록 새로고침" title="폰 목록 새로고침">
            <RefreshCw size={17} className={listing ? 'animate-spin' : ''} />
          </button>
        </div>
        {!listing && !phones.length && <p className="text-sm text-stone-500">등록된 안드로이드폰이 없습니다. 폰 앱을 연결한 뒤 목록을 새로고침하세요.</p>}
        {state && <div className="flex flex-wrap justify-between gap-2 text-xs text-stone-500">
          <span>{state.model} · Android {state.android}</span>
          <span className="flex items-center gap-1"><Battery size={15} />{state.battery >= 0 ? `${state.battery}%` : '배터리 정보 없음'}</span>
        </div>}
      </section>

      <section className="rounded-2xl border border-stone-200 bg-white p-5 sm:p-6 space-y-5" aria-busy={busy}>
        <div className="flex justify-between items-center">
          <h2 className="font-medium text-stone-900 flex items-center gap-2"><Volume2 size={20} />음량</h2>
          <button className="text-sm text-emerald-700 disabled:text-stone-400" disabled={busy || extrasBusy || !available}
            onClick={() => void execute(selected, 'status')}>상태 새로고침</button>
        </div>
        <select aria-label="음량 종류" value={stream} disabled={busy || extrasBusy || !available} className="w-full rounded-xl border border-stone-200 p-2 text-sm bg-white"
          onChange={e => { const next = e.target.value as PhoneStream; streamRef.current = next; setStream(next); setState(null); void execute(selected, 'status'); }}>
          <option value="music">미디어</option><option value="alarm">알람</option><option value="ring">벨소리</option><option value="notification">알림</option>
        </select>
        <div className="text-center py-2">
          <div className="text-5xl font-semibold tracking-tight text-stone-900 tabular-nums">{state ? state.actual : '—'}
            <span className="text-lg font-normal text-stone-400">{state ? ` / ${state.max}` : ''}</span>
          </div>
          <p className="text-sm text-stone-500 mt-2">{state ? `현재 ${state.percent}% · ${phone?.name}` : selected ? '상태를 확인하면 조절할 수 있습니다.' : '먼저 제어할 폰을 선택하세요.'}</p>
        </div>
        <label className="block space-y-2">
          <span className="text-sm text-stone-600">설정할 음량 {state ? `${draft}단계` : ''}</span>
          <input aria-label="설정할 미디어 음량" type="range" min={0} max={state?.max || 1} step={1}
            value={draft} disabled={disabled} onChange={e => setDraft(Number(e.target.value))}
            className="w-full accent-emerald-700 disabled:opacity-40" />
        </label>
        <button className="w-full py-3 rounded-xl bg-emerald-800 text-white hover:bg-emerald-900 disabled:opacity-40"
          disabled={disabled || draft === state?.actual} onClick={() => change('set', draft)}>선택한 음량 적용</button>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <button className={button} disabled={disabled || state?.actual === 0} onClick={() => change('step', -1)}>− 한 단계</button>
          <button className={button} disabled={disabled || state?.actual === state?.max} onClick={() => change('step', 1)}>＋ 한 단계</button>
          <button className={button} disabled={disabled || state?.actual === 0} onClick={() => change('half')}>절반으로</button>
          <button className={`${button} flex justify-center items-center gap-1`} disabled={disabled || state?.actual === 0} onClick={() => change('mute')}><VolumeX size={16} />음소거</button>
        </div>
        <button className={`${button} w-full flex justify-center items-center gap-2`} disabled={disabled || !state?.can_restore} onClick={() => change('restore')}>
          <Undo2 size={16} />이전 값 복원{state?.can_restore ? ` · ${state.previous}단계` : ''}
        </button>
        <p className="text-xs text-stone-500 leading-relaxed">절반은 음량 단계를 기준으로 내림합니다. 복원은 이 앱의 마지막 변경을 되돌립니다. 다른 곳에서 음량을 바꾸면 복원을 중단합니다.</p>
        {state?.fixed && <p className="text-sm text-amber-700">현재 출력 장치는 음량이 고정되어 있습니다.</p>}
      </section>

      <PhoneControlExtras key={selected} target={selected} disabled={!available || busy || listing} onBusy={setExtrasBusy} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <button className={`${button} flex items-center gap-2`} disabled={busy || extrasBusy || !available || !state?.has_vibrator} onClick={() => change('vibrate')}><Vibrate size={17} />짧은 진동</button>
        <span className="text-xs text-stone-500">{elapsed !== null ? `${elapsed.toFixed(1)}초 · ` : ''}AI 호출 없음</span>
      </div>
      <div aria-live="polite" className="text-sm min-h-6">
        {busy ? <p className="text-stone-600">{phone?.name}에서 처리 중…</p> : error ? <p role="alert" className="rounded-xl bg-red-50 p-3 text-red-800">{error}</p> : <p className="text-emerald-800">{notice}</p>}
      </div>
    </div>
  </div>;
}
