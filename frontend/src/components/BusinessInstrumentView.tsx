/**
 * BusinessInstrumentView — 런처 '비즈니스' 버튼이 여는 전용 창(#/business).
 *
 * 옛 비즈니스 관리 창(BusinessManager)을 대체한다. 별도 UI를 그리지 않고,
 * 앱모드와 동일한 IBL 비즈니스 계기(self:business/business_item/business_document/
 * work_guideline + others:auto_response 토글)를 GenericInstrument 로 그대로 렌더한다.
 * 4탭: 비즈니스(목록+상세 — 정보 form·아이템) / 공개문서 / 근무지침 / 자동응답.
 * 단일 진실 소스: /launcher/instruments 매니페스트. 메신저·커뮤니티와 같은 패턴.
 */
import { useState, useEffect } from 'react';
import { GenericInstrument, type AppInstrument } from './GenericInstrument';

const IBL_INSTRUMENTS = 'http://127.0.0.1:8765/launcher/instruments';

export function BusinessInstrumentView() {
  const [inst, setInst] = useState<AppInstrument | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch(IBL_INSTRUMENTS)
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return;
        const b = (d.instruments || []).find((i: AppInstrument) => i.id === 'business');
        if (b) setInst(b);
        else setError('비즈니스 계기를 찾을 수 없습니다.');
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => { alive = false; };
  }, []);

  if (error) return <div className="h-full w-full flex items-center justify-center text-sm text-stone-500 bg-stone-50">{error}</div>;
  if (!inst) return (
    <div className="h-full w-full flex items-center justify-center bg-stone-50">
      <div className="w-6 h-6 border-2 border-stone-200 border-t-stone-600 rounded-full animate-spin" />
    </div>
  );
  return (
    <div className="h-full w-full flex flex-col bg-stone-50">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-stone-200 bg-white shrink-0">
        <span className="text-lg">{inst.icon}</span>
        <span className="font-semibold text-stone-800">{inst.name}</span>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        <GenericInstrument instrument={inst} />
      </div>
    </div>
  );
}
