import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { ModelTierSettings } from './ModelTierSettings';
import { ModelGearLever } from './launcher-components/ModelGearLever';
import type { SystemAISettings } from './launcher-components/types';

type Models = Record<string, SystemAISettings>;
export function MemberModelSettings() {
  const [models, setModels] = useState<Models | null>(null);
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [revision, setRevision] = useState(0);
  const load = async () => {
    setError('');
    try { setModels((await api.request<{models: Models}>('/member-pcs/models')).models); }
    catch (e) { setError(String(e)); }
  };
  useEffect(() => { void load(); }, []);
  const save = async () => {
    setBusy(true); setError(''); setSaved(false);
    try {
      const result = await api.request<{models: Models}>('/member-pcs/models', {method: 'PUT', body: JSON.stringify({models})});
      setModels(result.models); setSaved(true); setRevision(v => v + 1);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };
  return <section className="rounded-xl border border-stone-200 bg-white p-5 space-y-4">
    <div><h2 className="font-semibold">회원 공통 모델 설정</h2>
      <p className="mt-2 text-sm text-stone-500">모든 회원 PC에 적용합니다. 처음에는 중앙 PC 설정을 가져오며, 이후에는 회원 모델과 기어를 별도로 저장합니다. 변경은 다음 요청부터 적용됩니다.</p></div>
    <ModelGearLever member revision={revision} />
    <details className="rounded-lg border border-stone-200 p-4">
      <summary className="cursor-pointer text-sm font-semibold">회원 모델 설정 · 경량 / 중급 / 고급</summary>
      <p className="my-4 text-xs text-stone-500">AI 제공자·모델은 회원 전용입니다. 제공자별 API 키와 CLI 로그인은 중앙 PC와 함께 사용하며, 새 API 키를 저장하면 해당 제공자의 공통 키를 교체합니다.</p>
      {error && <p role="alert" className="my-3 text-sm text-red-700">{error}</p>}
      {!models ? <button className="text-sm underline" onClick={() => void load()}>모델 설정 불러오기</button> : <>
        <fieldset disabled={busy} className="min-w-0 grid gap-6 lg:grid-cols-3">
          {['경량', '중급', '고급'].map(tier => <ModelTierSettings key={tier} member title={tier}
            description={tier === '경량' ? '분류·평가·백그라운드에 권장합니다.' : tier === '중급' ? '균형 기어의 실행·의식에 권장합니다.' : '최대 기어의 실행·의식에 권장합니다.'}
            settings={models[tier]} showApiKey={!!visibleKeys[tier]}
            onSettingsChange={value => { setModels(prev => prev ? {...prev, [tier]: value} : prev); setSaved(false); }}
            onToggleApiKey={() => setVisibleKeys(prev => ({...prev, [tier]: !prev[tier]}))} />)}
        </fieldset>
        <div className="mt-5 flex items-center gap-3"><button className="rounded-lg bg-stone-800 px-4 py-2 text-sm text-white disabled:opacity-40" disabled={busy} onClick={() => void save()}>{busy ? '저장 중…' : '회원 모델 설정 저장'}</button>
          {saved && <span role="status" className="text-sm text-emerald-700">저장했습니다. 다음 회원 요청부터 적용합니다.</span>}</div>
      </>}
    </details>
  </section>;
}
