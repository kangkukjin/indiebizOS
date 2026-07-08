/**
 * MessengerInstrumentView — 런처 '연락처' 버튼 / 비즈니스 창 '이웃관리' 버튼이 여는 전용 창.
 *
 * 옛 이웃관리 창(NeighborManagerDialog)·빠른 연락처(ContactsDialog)를 대체한다.
 * 별도 UI를 그리지 않고, 앱모드와 동일한 IBL 메신저 계기(others:messages — 대화 inbox·
 * 스레드·이웃 정보 form·연락처 CRUD·즐겨찾기·삭제)를 GenericInstrument 로 그대로 렌더한다.
 * 단일 진실 소스: /launcher/instruments 매니페스트. 표면(자율주행/수동/앱)과 무관하게
 * 메신저(=이웃관리 CRM)로 바로 진입하는 통로. CommunityInstrumentView 와 같은 패턴.
 */
import { useState, useEffect } from 'react';
import { GenericInstrument, type AppInstrument } from './GenericInstrument';

const IBL_INSTRUMENTS = 'http://127.0.0.1:8765/launcher/instruments';

export function MessengerInstrumentView() {
  const [inst, setInst] = useState<AppInstrument | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch(IBL_INSTRUMENTS)
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return;
        const m = (d.instruments || []).find((i: AppInstrument) => i.id === 'messenger');
        if (m) setInst(m);
        else setError('메신저 계기를 찾을 수 없습니다.');
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
  // 헤더 자체를 드래그 영역으로(hiddenInset 창은 이게 없으면 창을 못 움직임).
  // pl-20 = 좌상단 트래픽 라이트(신호등)와 아이콘이 겹치지 않게 확보.
  return (
    <div className="h-full w-full flex flex-col bg-stone-50">
      <div
        className="flex items-center gap-2 pl-20 pr-5 py-3 border-b border-stone-200 bg-white shrink-0"
        style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}
      >
        <span className="text-lg">{inst.icon}</span>
        <span className="font-semibold text-stone-800">{inst.name}</span>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        <GenericInstrument instrument={inst} />
      </div>
    </div>
  );
}
