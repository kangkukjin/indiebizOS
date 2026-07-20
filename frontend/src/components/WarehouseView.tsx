/**
 * WarehouseView — 공유창고 런처 표면의 셸. 네 탭:
 *
 * [내 창고] 파인더 모델(warehouse/MinePane) — 레벨 사이드바(0~4+휴지통)·폴더 진입·
 *   경로 바·아이콘/목록 보기·우클릭 메뉴·다중 선택. 드래그앤드롭=물리 복사 투입,
 *   레벨에 드롭=공개 범위 변경. 백엔드: /portal/warehouse-admin/*.
 * [이웃] 창고이웃 등기부 + 변화 피드 + 검색 (warehouse/NeighborsPane, /warehouse-feed/*).
 * [이웃찾기] #IndieNet 발견 노트 수신면 (warehouse/DiscoverPane).
 * [비즈니스] 창고에 진열되는 카탈로그의 저작면 (BusinessInstrumentView).
 *
 * 1500줄 규칙으로 패널을 warehouse/ 로 분리(2026-07-20) — 여기는 헤더·탭 전환만.
 */
import { useCallback, useState } from 'react';
import { Package, ExternalLink, Users, Search, Building2, Globe } from 'lucide-react';
import { runIBL } from './generic/manifest';
import { useRetryingLoad } from '../lib/use-retrying-load';
import { API } from './warehouse/shared';
import { MinePane } from './warehouse/MinePane';
import { NeighborsPane } from './warehouse/NeighborsPane';
import { DiscoverPane } from './warehouse/DiscoverPane';
import { BusinessInstrumentView } from './BusinessInstrumentView';

export function WarehouseView() {
  const [tab, setTab] = useState<'mine' | 'neighbors' | 'discover' | 'business'>(() => {
    const saved = localStorage.getItem('indiebiz_warehouse_tab');
    return saved === 'neighbors' || saved === 'discover' || saved === 'business' ? saved : 'mine';
  });
  // 헤더 장식(제목·공개 주소)용 가벼운 조회 — 내 창고 목록은 MinePane 이 따로 든다.
  const [meta, setMeta] = useState<{ title: string; public_url: string } | null>(null);
  useRetryingLoad(useCallback(async () => {
    const r = await fetch(`${API}/portal/warehouse-admin/list?level=0`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    setMeta({ title: d.title, public_url: d.public_url });
  }, []));

  /* 소개발행 — 공개 인사 프로필 + 공개 창고 주소를 #IndieNet 에 발행 (명함 kind:0 + 발견 노트 kind:1).
     "나를 알리는" 행위라 비즈니스 계기가 아니라 창고 표면에 산다 (2026-07-19 이동). */
  const [introBusy, setIntroBusy] = useState(false);
  const publishIntro = useCallback(async () => {
    if (!window.confirm('공개 인사 프로필과 공개 창고 주소를 #IndieNet 에 발행할까요? (명함 kind:0 + 발견 노트 kind:1)')) return;
    setIntroBusy(true);
    try {
      const r = (await runIBL('[self:business_document]{op: "publish"}')) as Record<string, unknown>;
      const msg = typeof r?.message === 'string' ? r.message
        : r?.error ? String(r.error) : '소개를 발행했어요.';
      window.alert(msg);
    } catch (e) {
      window.alert(`소개발행 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
    setIntroBusy(false);
  }, []);

  return (
    <div className="h-full w-full flex flex-col bg-stone-50">
      {/* 헤더 */}
      <div className="flex items-center gap-2 px-5 py-3 border-b border-stone-200 bg-white shrink-0">
        <Package className="w-5 h-5 text-[#D97706]" />
        <span className="font-semibold text-stone-800">{meta?.title || '공유창고'}</span>
        {meta?.public_url && (
          <button
            className="flex items-center gap-1 text-xs text-stone-400 hover:text-[#D97706] ml-1"
            title="공개 주소 열기"
            onClick={() => (window as any).electron?.openExternal?.(meta.public_url)}
          >
            {meta.public_url.replace(/^https?:\/\//, '')}
            <ExternalLink className="w-3 h-3" />
          </button>
        )}
        {/* 탭 — 내 창고(발신) / 이웃(수신·피드) / 이웃찾기 / 비즈니스 */}
        <div className="flex items-center gap-1 ml-3 p-0.5 rounded-lg bg-stone-100">
          {([['mine', '내 창고', Package], ['neighbors', '이웃', Users], ['discover', '이웃찾기', Search], ['business', '비즈니스', Building2]] as const).map(([key, label, TabIcon]) => (
            <button
              key={key}
              onClick={() => { setTab(key); localStorage.setItem('indiebiz_warehouse_tab', key); }}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs transition-colors ${
                tab === key ? 'bg-white text-[#B45309] shadow-sm font-medium' : 'text-stone-500 hover:text-stone-700'
              }`}
            >
              <TabIcon className="w-3.5 h-3.5" /> {label}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <button
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-[#D97706]/40 text-[#B45309] hover:bg-amber-50 disabled:opacity-50"
          title="나를 알리기 — 공개 인사 프로필과 공개 창고 주소를 #IndieNet 에 발행합니다 (창고이웃을 구하는 첫걸음)"
          disabled={introBusy}
          onClick={publishIntro}
        >
          <Globe className="w-3.5 h-3.5" /> {introBusy ? '발행 중…' : '소개발행'}
        </button>
      </div>

      {tab === 'mine' && <MinePane />}
      {tab === 'neighbors' && <NeighborsPane />}
      {tab === 'discover' && <DiscoverPane />}
      {/* 비즈니스 관리 — 창고에 진열되는 카탈로그(아이템·공개문서·자동응답)의 저작면.
          2026-07-19 런처 모드에서 창고 탭으로 이동: 비즈니스=창고를 채우는 관리 기능. */}
      {tab === 'business' && <div className="flex-1 min-h-0"><BusinessInstrumentView /></div>}
    </div>
  );
}
