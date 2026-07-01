/**
 * ActionDesktop — 런처의 두 번째 탭 "액션 데스크탑"
 *
 * 스마트폰 홈 화면 구조:
 *   도메인 아이콘(부동산·투자…) → 누르면 그 도메인의 계기들 → 계기를 열면 직접 조작
 *
 * 프로젝트 탭이 '에이전트에게 맡기는' 오토파일럿이라면,
 * 이 탭은 '내가 직접 다이얼을 도는' 수동 운전이다. 같은 도메인의 두 얼굴.
 */
import { useState, useEffect, useMemo, useCallback, type ReactNode } from 'react';
import { DirectionsInstrument } from './DirectionsInstrument';
import { CalendarInstrument } from './CalendarInstrument';
import { NewspaperInstrument } from './NewspaperInstrument';
import { YtMusicInstrument } from './YtMusicInstrument';
import { GenericInstrument, type AppInstrument } from './GenericInstrument';

// 계기는 두 종류 — 인라인으로 펼쳐지는 것(el)과, 누르면 별도 네이티브 창을 띄우는 것(onOpen).
interface Instrument { id: string; icon: string; label: string; el?: ReactNode; onOpen?: () => void; soon?: boolean }
// 도메인도 onOpen을 가질 수 있다 — 계기 화면을 거치지 않고 홈에서 바로 액션을 실행하는 단일 아이콘.
interface Domain { id: string; icon: string; label: string; soon?: boolean; onOpen?: () => void; instruments: Instrument[] }

// ===== 매니페스트 구동 계기 =====
// 진실 소스 = ibl_nodes_src 액션의 app: 블록 → GET /launcher/instruments 자동 파생.
// 여기 명단에 없는 새 계기(app: 블록만 단 액션)는 홈 그리드 끝에 자동 등장한다 —
// 원격 런처와 같은 선언을 같은 어휘로 그린다 (docs/REMOTE_APP_GENERIC_RENDERER_PLAN.md).

// escape hatch: 매니페스트보다 풍부한 데스크탑 전용 컴포넌트가 있으면 그걸 쓴다.
// (도서=대출통계·추천 드릴 / 투자=recharts 차트·3탭 / 라디오=즐겨찾기·볼륨)
const OVERRIDES: Record<string, ReactNode> = {
  ytmusic: <YtMusicInstrument />,       // 다운로드·큐 통합 UI(youtube=mac_only)
};

// 데스크탑 전용 도메인 — 지도·네이티브 창·파일 경로 등 렌더 어휘 밖(영구 escape).
const STATIC_DOMAINS: Domain[] = [
  {
    id: 'realestate', icon: '🏢', label: '부동산',
    instruments: [
      { id: 'realty', icon: '🏢', label: '실거래가' },  // el 은 manifest app: 블록(GenericInstrument)으로 useMemo 에서 주입 — bespoke 은퇴
      { id: 'commercial', icon: '🏪', label: '상권' },  // el 은 manifest 주입 — 동적 업종필터+가게 상세드릴 선언화로 bespoke 은퇴
      { id: 'listing', icon: '🔑', label: '매물', soon: true },
    ],
  },
  // 블로그 노트(Obsidian vault) — IBL 액션이 아니라 obsidian:// 프로토콜로 데스크톱 Obsidian을 띄운다.
  // 진실 소스 vault: ~/Documents/iRepublic-Vault (markdown). shell.openExternal 경유.
  { id: 'obsidian', icon: '💎', label: '블로그(Obsidian)',
    onOpen: () => window.electron?.openExternal?.('obsidian://open?vault=iRepublic-Vault'), instruments: [] },
  {
    id: 'calendar', icon: '📅', label: '일정',
    instruments: [
      { id: 'calendar', icon: '📅', label: '일정 캘린더', el: <CalendarInstrument /> },
    ],
  },
  // 신문 — 디자인은 컴포넌트(NewspaperInstrument), 내용은 [sense:search_gnews] 조합.
  // engines:newspaper 은퇴로 매니페스트 앵커가 없어 STATIC 계기로 등록(구 OVERRIDE 대체).
  {
    id: 'newspaper', icon: '📰', label: '신문',
    instruments: [
      { id: 'newspaper', icon: '📰', label: '신문', el: <NewspaperInstrument /> },
    ],
  },
  {
    id: 'device', icon: '🖥️', label: '내 기기',
    instruments: [
      { id: 'photo', icon: '📷', label: '사진', onOpen: () => window.electron?.openPhotoManagerWindow?.(null) },
      { id: 'files', icon: '🗂️', label: '파일', onOpen: () => window.electron?.openPCManagerWindow?.(null) },
    ],
  },
  // 강의 만들기 — 홈 아이콘 한 번으로 강의 워크스페이스 네이티브 창 열기.
  { id: 'lecture', icon: '🎓', label: '강의 만들기', onOpen: () => window.electron?.openLectureWorkspaceWindow?.(null), instruments: [] },
  {
    id: 'directions', icon: '🛣️', label: '길찾기·CCTV',
    instruments: [
      { id: 'directions', icon: '🛣️', label: '길찾기·CCTV', el: <DirectionsInstrument /> },
    ],
  },
];

// 홈 그리드 배치 순서 (static id + 매니페스트 계기 id 혼합).
// 명단에 없는 매니페스트 계기는 끝에 자동 추가 — "새 앱 = app: 블록 1개"의 데스크탑 절반.
const HOME_ORDER = [
  'realestate', 'book', 'obsidian', 'calendar', 'newspaper', 'device', 'launch',
  'lecture', 'invest', 'restaurant', 'directions', 'weather', 'culture', 'radio', 'ytmusic',
];

// STATIC_DOMAINS 안에 이미 들어있는 계기 id — 매니페스트가 같은 id를 줘도 데스크탑 홈에 별도 타일로
// 띄우지 않는다(부동산 도메인 안의 '실거래가'처럼 더 풍부한 전용 컴포넌트로 렌더 중). 원격엔 그대로 노출.
const STATIC_INSTRUMENT_IDS = new Set(STATIC_DOMAINS.flatMap((d) => d.instruments.map((i) => i.id)));

function manifestToDomain(inst: AppInstrument): Domain {
  const el = OVERRIDES[inst.id] ?? <GenericInstrument instrument={inst} />;
  return {
    id: inst.id, icon: inst.icon, label: inst.name,
    instruments: [{ id: inst.id, icon: inst.icon, label: inst.name, el }],
  };
}

export function ActionDesktop() {
  const [domainId, setDomainId] = useState<string | null>(null);
  const [instrumentId, setInstrumentId] = useState<string | null>(null);
  const [manifest, setManifest] = useState<AppInstrument[]>([]);

  // 매니페스트 로드 — app: 블록 변경(계기/어휘)을 앱 재시작 없이 반영하기 위해 재호출 가능하게 함.
  // 백엔드 /launcher/instruments 는 ibl_nodes.yaml mtime 캐시라 변경 없으면 재fetch 비용 거의 없음.
  const loadManifest = useCallback(() => {
    fetch('http://127.0.0.1:8765/launcher/instruments')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => setManifest(d.instruments || []))
      .catch(() => { /* 백엔드 미기동 시 static 도메인만 표시 */ });
  }, []);

  // 마운트(앱 탭 진입 = remount) 시 + 창 포커스 복귀 시 재fetch — 다른 창에서 IBL 어휘 편집 후 돌아오면 갱신.
  useEffect(() => {
    loadManifest();
    window.addEventListener('focus', loadManifest);
    return () => window.removeEventListener('focus', loadManifest);
  }, [loadManifest]);

  const DOMAINS = useMemo<Domain[]>(() => {
    const byId = new Map<string, Domain>();
    STATIC_DOMAINS.forEach((d) => byId.set(d.id, d));
    // STATIC_DOMAINS가 이미 품은 계기(예: 부동산 안의 realty)는 매니페스트로 덮어쓰지 않는다
    const shown = manifest.filter((i) => !STATIC_INSTRUMENT_IDS.has(i.id));
    shown.forEach((inst) => byId.set(inst.id, manifestToDomain(inst)));
    // realty·commercial: 부동산 도메인 안에서 선언형(manifest app: 블록 → GenericInstrument)으로 렌더한다.
    // bespoke RealtyInstrument·CommercialInstrument 은퇴 → 맥·폰·원격이 단일 선언을 공유(드리프트 근절).
    const realestate = byId.get('realestate');
    if (realestate) {
      const manById = new Map(manifest.map((i) => [i.id, i]));
      byId.set('realestate', {
        ...realestate,
        instruments: realestate.instruments.map((ins) => {
          const inst = manById.get(ins.id);
          return inst ? { ...ins, el: <GenericInstrument instrument={inst} /> } : ins;
        }),
      });
    }
    const ordered = HOME_ORDER.map((id) => byId.get(id)).filter((d): d is Domain => !!d);
    const extras = shown.filter((i) => !HOME_ORDER.includes(i.id)).map(manifestToDomain);
    return [...ordered, ...extras];
  }, [manifest]);

  const domain = DOMAINS.find((d) => d.id === domainId) || null;
  const instrument = domain?.instruments.find((i) => i.id === instrumentId) || null;

  // 레벨 2: 계기 열림 → 직접 조작
  if (domain && instrument?.el) {
    return (
      <div className="absolute inset-0 flex flex-col">
        <BackBar onBack={() => setInstrumentId(null)}
          crumbs={[domain.label, instrument.label]} />
        <div className="flex-1 min-h-0">{instrument.el}</div>
      </div>
    );
  }

  // 레벨 1: 도메인 열림 → 그 도메인의 계기들
  if (domain) {
    return (
      <div className="absolute inset-0 flex flex-col">
        <BackBar onBack={() => setDomainId(null)} crumbs={[domain.label]} />
        <div className="flex-1 overflow-auto p-8">
          {domain.instruments.length === 0 ? (
            <Empty label={`${domain.label} 계기는 곧 추가됩니다`} />
          ) : (
            <Grid>
              {domain.instruments.map((ins) => (
                <IconTile key={ins.id} icon={ins.icon} label={ins.label} soon={ins.soon}
                  onClick={() => {
                    if (ins.soon) return;
                    if (ins.onOpen) ins.onOpen();        // 별도 네이티브 창 띄우기
                    else if (ins.el) setInstrumentId(ins.id); // 인라인 계기 펼치기
                  }} />
              ))}
            </Grid>
          )}
        </div>
      </div>
    );
  }

  // 레벨 0: 도메인 홈 (스마트폰 화면)
  return (
    <div className="absolute inset-0 overflow-auto p-8">
      <Grid>
        {DOMAINS.map((d) => (
          <IconTile key={d.id} icon={d.icon} label={d.label} soon={d.soon}
            onClick={() => {
              if (d.soon) return;
              if (d.onOpen) d.onOpen();      // 홈에서 바로 액션 실행
              else setDomainId(d.id);        // 도메인 → 계기 화면으로
            }} />
        ))}
      </Grid>
    </div>
  );
}

function Grid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-6 max-w-3xl mx-auto">{children}</div>;
}

function IconTile({ icon, label, soon, onClick }: { icon: string; label: string; soon?: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} disabled={soon}
      className={`flex flex-col items-center gap-2 group ${soon ? 'opacity-40 cursor-default' : 'cursor-pointer'}`}>
      <div className={`w-16 h-16 rounded-2xl bg-white shadow-sm border border-stone-200 flex items-center justify-center text-3xl transition ${soon ? '' : 'group-hover:shadow-md group-hover:-translate-y-0.5'}`}>
        {icon}
      </div>
      <span className="text-xs text-stone-600 text-center">{label}{soon && <span className="block text-[10px] text-stone-400">곧</span>}</span>
    </button>
  );
}

function BackBar({ onBack, crumbs }: { onBack: () => void; crumbs: string[] }) {
  return (
    <div className="shrink-0 flex items-center gap-2 px-5 py-2 text-sm">
      <button onClick={onBack} className="px-2 py-1 rounded-lg text-stone-500 hover:bg-stone-100">‹ 뒤로</button>
      <span className="text-stone-300">/</span>
      {crumbs.map((c, i) => (
        <span key={i} className={i === crumbs.length - 1 ? 'text-stone-800 font-medium' : 'text-stone-400'}>
          {c}{i < crumbs.length - 1 && <span className="text-stone-300 mx-1">/</span>}
        </span>
      ))}
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return <div className="h-full flex items-center justify-center text-stone-400 text-sm">{label}</div>;
}
