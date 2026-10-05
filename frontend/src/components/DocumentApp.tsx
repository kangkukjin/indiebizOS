/**
 * 문서 앱 단독 창(#/documents) — 앱 모드의 문서 계기(data/instruments/document.yaml)를 한 창에 그대로 띄운다.
 * 옛 문서 창(DocumentWorkspace)의 자리를 물려받았다(2026-10-06): 창 진입점(Electron 'documents' 도구 창, 시트 앱의
 * "문서에 표 보고서 만들기")과 브라우저 인수 시험이 이 경로를 쓴다. 화면은 계기 선언 하나가 정본이다.
 */
import { useCallback, useState } from 'react';
import { BACKEND_ORIGIN } from '../lib/backend-origin';
import { useRetryingLoad } from '../lib/use-retrying-load';
import { GenericInstrument, type AppInstrument } from './GenericInstrument';

export function DocumentApp() {
  const [instrument, setInstrument] = useState<AppInstrument | null>(null);
  const [missing, setMissing] = useState(false);
  const load = useCallback(async () => {
    const r = await fetch(`${BACKEND_ORIGIN}/launcher/instruments`);
    if (!r.ok) throw new Error(String(r.status));
    const found = ((await r.json()).instruments as AppInstrument[] || []).find((i) => i.id === 'document') || null;
    setInstrument((prev) => (prev && JSON.stringify(prev) === JSON.stringify(found) ? prev : found));
    setMissing(!found);
  }, []);
  const { retrying } = useRetryingLoad(load);
  return (
    <div className="h-screen w-screen overflow-hidden bg-stone-50">
      {instrument ? <GenericInstrument instrument={instrument} />
        : <p className="p-6 text-sm text-stone-500">{missing ? '문서 앱 선언(document)을 찾지 못했습니다.' : retrying ? '연결 중…' : '문서 앱을 여는 중…'}</p>}
    </div>
  );
}
