/**
 * ActionDesktop — 런처의 "앱" 표면 (앱모드)
 *
 * 스마트폰 홈 화면 구조:
 *   도메인 아이콘(부동산·투자…) → 누르면 그 도메인의 계기들 → 계기를 열면 직접 조작
 *
 * 2026-07-05: 자율주행 데스크탑의 개인화(자유 배치·휴지통·폴더)를 앱모드에 이식.
 *   - 자유 배치: 아이콘을 끌어 원하는 곳에 둔다 (DraggableIcon 재사용)
 *   - 앱저장소: 전체 카탈로그에서 골라 홈에 추가 (removed 에서 뺌)
 *   - 휴지통: 홈에서 빼서 앱저장소로 되돌림 + 앱이 쌓은 데이터 초기화 (soft reset)
 *   - 폴더: 아이콘을 폴더로 끌어 정리
 * 상태 = 백엔드 launcher_app_layout.json (data/lib api.getAppLayout/saveAppLayout).
 * 카탈로그(무엇이 존재하나)와 레이아웃(어떻게 배치했나)의 분리 — 새 app: 블록은
 * 홈에 자동 등장(기존 불변식 보존), 사용자는 그 위에서 배치/정리/제거.
 */
import { useState, useEffect, useMemo, useCallback, useRef, type ReactNode } from 'react';
import { Plus, Package, LayoutGrid, Trash2, ArrowUpFromLine, ArrowDownFromLine } from 'lucide-react';
import { DirectionsInstrument } from './DirectionsInstrument';
import { NewspaperInstrument } from './NewspaperInstrument';
import { BinNote } from './BinNote';
import { YtMusicInstrument } from './YtMusicInstrument';
import { GenericInstrument, type AppInstrument } from './GenericInstrument';
import { DraggableIcon } from './launcher-components/DraggableIcon';
import { api } from '../lib/api';
import type { AppLayout } from '../types';

// 계기는 두 종류 — 인라인으로 펼쳐지는 것(el)과, 누르면 별도 네이티브 창을 띄우는 것(onOpen).
interface Instrument { id: string; icon: string; label: string; el?: ReactNode; onOpen?: () => void; soon?: boolean }
// 도메인은 코드 안에서 관련 계기를 묶는 *선언 구조*일 뿐 — 런타임엔 평탄화되어 각 계기가
// 독립 최상위 앱이 된다(도메인→계기 2단 진입 폐지, 그룹핑은 사용자 폴더가 담당).
interface Domain { id: string; icon: string; label: string; soon?: boolean; onOpen?: () => void; instruments: Instrument[] }
// 평탄한 앱 = 계기 하나(홈 아이콘 하나). 계기와 같은 모양.
type App = Instrument;

// ===== 매니페스트 구동 계기 =====
// 진실 소스 = ibl_nodes_src 액션의 app: 블록 → GET /launcher/instruments 자동 파생.

// escape hatch: 매니페스트보다 풍부한 데스크탑 전용 컴포넌트가 있으면 그걸 쓴다.
const OVERRIDES: Record<string, ReactNode> = {
  ytmusic: <YtMusicInstrument />,       // 다운로드·큐 통합 UI(youtube=mac_only)
};

// 데스크탑 전용 도메인 — 지도·네이티브 창·파일 경로 등 렌더 어휘 밖(영구 escape).
const STATIC_DOMAINS: Domain[] = [
  {
    id: 'realestate', icon: '🏢', label: '부동산',
    instruments: [
      { id: 'realty', icon: '🏢', label: '실거래가' },  // el 은 manifest app: 블록(GenericInstrument)으로 useMemo 에서 주입
      { id: 'commercial', icon: '🏪', label: '상권' },  // el 은 manifest 주입
      { id: 'listing', icon: '🔑', label: '매물', soon: true },
    ],
  },
  { id: 'obsidian', icon: '💎', label: '블로그(Obsidian)',
    onOpen: () => window.electron?.openExternal?.('obsidian://open?vault=iRepublic-Vault'), instruments: [] },
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
  { id: 'lecture', icon: '🎓', label: '강의 만들기', onOpen: () => window.electron?.openLectureWorkspaceWindow?.(null), instruments: [] },
  {
    id: 'binnote', icon: '📝', label: '빈노트',
    instruments: [
      { id: 'binnote', icon: '📝', label: '빈노트', el: <BinNote /> },  // 인라인 계기 — 메인 창 안에서 열리고 BackBar로 나간다
    ],
  },
  {
    id: 'directions', icon: '🛣️', label: '길찾기·CCTV',
    instruments: [
      { id: 'directions', icon: '🛣️', label: '길찾기·CCTV', el: <DirectionsInstrument /> },
    ],
  },
];

// 홈 그리드 기본 배치 순서 (평탄화된 앱 id 기준 — 사용자 레이아웃이 없는 첫 실행/신규 앱의 자동 자리).
const HOME_ORDER = [
  'realty', 'commercial', 'book', 'obsidian', 'calendar', 'newspaper', 'photo', 'files', 'launch',
  'lecture', 'binnote', 'invest', 'restaurant', 'directions', 'weather', 'culture', 'radio', 'ytmusic',
];

// STATIC 도메인을 평탄한 앱 목록으로 — instruments 있으면 각각을 앱으로, 없으면(onOpen 도메인)
// 도메인 자체를 앱으로. soon(placeholder)은 뺀다. el 미지정 static 계기는 매니페스트 app: 블록에서 주입.
function staticAppsFrom(manById: Map<string, AppInstrument>): App[] {
  return STATIC_DOMAINS.flatMap((d) =>
    d.instruments.length === 0
      ? [{ id: d.id, icon: d.icon, label: d.label, onOpen: d.onOpen }]
      : d.instruments
          .filter((ins) => !ins.soon)
          .map((ins) => {
            const inst = manById.get(ins.id);
            return {
              id: ins.id, icon: ins.icon, label: ins.label, onOpen: ins.onOpen,
              el: ins.el ?? (inst ? <GenericInstrument instrument={inst} /> : undefined),
            };
          })
  );
}

function manifestToApp(inst: AppInstrument): App {
  return { id: inst.id, icon: inst.icon, label: inst.name, el: OVERRIDES[inst.id] ?? <GenericInstrument instrument={inst} /> };
}

// 자유 배치 자동 자리 — 사용자가 아직 안 옮긴(위치 미저장) 아이콘의 격자 위치.
const GRID_X0 = 28, GRID_Y0 = 28, GRID_DX = 104, GRID_DY = 116, GRID_COLS = 7;
function autoPos(index: number): [number, number] {
  return [GRID_X0 + (index % GRID_COLS) * GRID_DX, GRID_Y0 + Math.floor(index / GRID_COLS) * GRID_DY];
}

const EMPTY_LAYOUT: AppLayout = { version: 1, positions: {}, folders: {}, membership: {}, removed: [], uninstalled: [], promoted: [] };

// 런처 모드 선택기가 승격된 앱의 아이콘·라벨을 알 수 있도록 static 앱 메타를 내보낸다(평탄화된 id 기준).
// (매니페스트 앱은 런처가 /launcher/instruments 로 직접 파싱 — 여기선 코드-정의 static 만)
export const STATIC_APP_META = STATIC_DOMAINS.flatMap((d) =>
  d.instruments.length === 0
    ? [{ id: d.id, icon: d.icon, label: d.label }]
    : d.instruments.filter((i) => !i.soon).map((i) => ({ id: i.id, icon: i.icon, label: i.label }))
);

// openAppId: 런처 모드 선택기의 승격 앱에서 넘어온 딥링크 대상. 마운트/변경 시 그 앱을 바로 연다.
export function ActionDesktop({ openAppId }: { openAppId?: string | null } = {}) {
  // 레벨2로 열린 앱 id(인라인 el). null = 홈. 도메인→계기 2단이 없어져 단일 상태로 충분.
  const [openId, setOpenId] = useState<string | null>(null);
  const [manifest, setManifest] = useState<AppInstrument[]>([]);
  const [layout, setLayout] = useState<AppLayout>(EMPTY_LAYOUT);
  const [storeOpen, setStoreOpen] = useState(false);
  const [openFolderId, setOpenFolderId] = useState<string | null>(null);

  // 드래그 히트테스트 상태 (제거는 우클릭 메뉴로 이관 — 휴지통 폐기)
  const [hoveringFolderId, setHoveringFolderId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  // 컨텍스트 메뉴 — target 없으면 데스크탑(새폴더/앱저장소/정렬), 있으면 앱(제거)·폴더(이름변경/해체)
  const [menu, setMenu] = useState<{ x: number; y: number; target?: { id: string; kind: 'app' | 'folder' } } | null>(null);
  const folderRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const loadManifest = useCallback(() => {
    fetch('http://127.0.0.1:8765/launcher/instruments')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => setManifest(d.instruments || []))
      .catch(() => { /* 백엔드 미기동 시 static 도메인만 표시 */ });
  }, []);

  const loadLayout = useCallback(() => {
    api.getAppLayout().then(setLayout).catch(() => { /* 미기동/미생성 시 빈 레이아웃 */ });
  }, []);

  useEffect(() => {
    loadManifest();
    loadLayout();
    const onFocus = () => { loadManifest(); loadLayout(); };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [loadManifest, loadLayout]);

  // 레이아웃 낙관적 갱신 + 지속 (함수형 업데이트로 연속 드래그 race 방지)
  const mutate = useCallback((fn: (l: AppLayout) => AppLayout) => {
    setLayout((prev) => {
      const next = fn({
        ...prev,
        positions: { ...prev.positions },
        folders: { ...prev.folders },
        membership: { ...prev.membership },
        removed: [...prev.removed],
        uninstalled: [...(prev.uninstalled || [])],
        promoted: [...(prev.promoted || [])],
      });
      api.saveAppLayout(next).catch((e) => console.error('레이아웃 저장 실패:', e));
      return next;
    });
  }, []);

  // 카탈로그 — STATIC(평탄화) + 매니페스트 병합. 각 계기가 독립 최상위 앱(도메인 그룹핑 없음).
  const APPS = useMemo<App[]>(() => {
    const manById = new Map(manifest.map((i) => [i.id, i]));
    const statics = staticAppsFrom(manById);
    const staticIds = new Set(statics.map((a) => a.id));  // 매니페스트에서 static 이 소유한 것(realty·photo 등) 제외
    const all: App[] = [...statics, ...manifest.filter((i) => !staticIds.has(i.id)).map(manifestToApp)];
    const byId = new Map(all.map((a) => [a.id, a]));
    const ordered = HOME_ORDER.map((id) => byId.get(id)).filter((a): a is App => !!a);
    const orderedIds = new Set(ordered.map((a) => a.id));
    return [...ordered, ...all.filter((a) => !orderedIds.has(a.id))];
  }, [manifest]);

  // 승격 앱 딥링크 — openAppId 가 주어지면 그 앱을 바로 연다(계기 인라인 or 네이티브 창).
  // APPS 는 매니페스트 비동기 로드 후 채워지므로 준비될 때까지 대기하고, 같은 id 재적용은 스킵
  // (window focus 로 매니페스트 재조회 시 사용자 내비게이션을 되감지 않도록).
  const deepLinkRef = useRef<string | null>(null);
  useEffect(() => {
    if (!openAppId) { deepLinkRef.current = null; return; }
    if (deepLinkRef.current === openAppId) return;
    const a = APPS.find((x) => x.id === openAppId);
    if (!a) return;  // 매니페스트 아직 로드 전 — 다음 렌더에서 재시도
    deepLinkRef.current = openAppId;
    if (a.onOpen) { a.onOpen(); setOpenId(null); }  // 네이티브 창 — 앱 홈은 그대로
    else if (a.el) setOpenId(a.id);                 // 인라인 → 바로 레벨2
    else setOpenId(null);
  }, [openAppId, APPS]);

  const folderTargets = useMemo(() => Object.keys(layout.folders), [layout.folders]);

  // 완전 삭제(uninstalled)된 앱은 카탈로그에서 아예 뺀다 — 홈·앱저장소 어디에도 안 나옴.
  const catalog = useMemo(
    () => APPS.filter((a) => !(layout.uninstalled || []).includes(a.id)),
    [APPS, layout.uninstalled]
  );

  // 홈에 실제로 놓인 것: 카탈로그 중 removed 아니고 폴더에도 안 든 것 + 폴더 아이콘들
  const homeApps = useMemo(
    () => catalog.filter((a) => !layout.removed.includes(a.id) && !layout.membership[a.id]),
    [catalog, layout.removed, layout.membership]
  );

  // 앱의 *고정* 자리 인덱스 = 전체 카탈로그(APPS) 내 순서. 폴더 이동/제거로 홈 목록이 줄어도
  // 이 인덱스는 안 밀리므로, 위치를 안 준 아이콘들이 서로 밀려 재배치되는 일이 없다(버그 방지).
  const catalogIndex = useMemo(() => new Map(APPS.map((a, i) => [a.id, i])), [APPS]);

  const posOf = useCallback((id: string, idx: number): [number, number] =>
    layout.positions[id] || autoPos(idx), [layout.positions]);

  // ── 드래그 히트테스트 (폴더 드롭만 — 휴지통 폐기) ──
  const checkFolderHover = (x: number, y: number, draggedId: string): string | null => {
    for (const fid of folderTargets) {
      if (fid === draggedId) continue;
      const ref = folderRefs.current[fid];
      if (ref) {
        const r = ref.getBoundingClientRect();
        if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) {
          setHoveringFolderId(fid);
          return fid;
        }
      }
    }
    setHoveringFolderId(null);
    return null;
  };

  // ── 레이아웃 조작 ──
  const setPosition = (id: string, x: number, y: number) =>
    mutate((l) => { l.positions[id] = [x, y]; return l; });

  const moveToFolder = (appId: string, folderId: string) =>
    mutate((l) => { l.membership[appId] = folderId; delete l.positions[appId]; return l; });

  const ejectFromFolder = (appId: string) =>
    mutate((l) => { delete l.membership[appId]; return l; });

  // 승격/빼기 — 앱을 런처 모드 선택기(바)에 올리거나 내린다. promoted 배열 순서 = 바 표시 순서.
  const isPromoted = (id: string) => (layout.promoted || []).includes(id);
  const promoteApp = (id: string) =>
    mutate((l) => { if (!(l.promoted || []).includes(id)) l.promoted = [...(l.promoted || []), id]; return l; });
  const demoteApp = (id: string) =>
    mutate((l) => { l.promoted = (l.promoted || []).filter((x) => x !== id); return l; });

  // 제거(우클릭 메뉴): 앱 → 앱저장소로 되돌림 + 데이터 초기화(soft reset). 폴더 → 해체(자식은 홈으로).
  const removeApp = (id: string) => {
    api.resetApp(id).catch((e) => console.error('앱 초기화 실패:', e)); // 앱이 쌓은 데이터 지우기
    mutate((l) => {
      if (!l.removed.includes(id)) l.removed.push(id);
      delete l.positions[id];
      delete l.membership[id];
      l.promoted = (l.promoted || []).filter((x) => x !== id);  // 홈에서 빼면 바에서도 내린다
      return l;
    });
  };
  const dissolveFolder = (id: string) =>
    mutate((l) => {
      delete l.folders[id];
      delete l.positions[id];
      for (const app of Object.keys(l.membership)) if (l.membership[app] === id) delete l.membership[app];
      return l;
    });

  const addFromStore = (id: string) =>
    mutate((l) => { l.removed = l.removed.filter((x) => x !== id); return l; });

  // 완전 삭제 — 카탈로그에서 영구 제거 + 데이터 초기화. 홈·앱저장소 어디에도 안 나옴.
  const uninstallApp = (id: string) => {
    api.resetApp(id).catch((e) => console.error('앱 초기화 실패:', e));
    mutate((l) => {
      if (!(l.uninstalled || []).includes(id)) l.uninstalled = [...(l.uninstalled || []), id];
      l.removed = l.removed.filter((x) => x !== id);
      l.promoted = (l.promoted || []).filter((x) => x !== id);  // 완전 삭제 → 바에서도 제거
      delete l.positions[id];
      delete l.membership[id];
      return l;
    });
  };

  // window.prompt 는 Electron 에서 미지원(항상 null) → 폴더를 바로 만들고 인라인 이름변경으로 진입.
  const createFolder = () => {
    const fid = `folder_${Date.now()}`;
    const pos = autoPos(APPS.length + folderTargets.length);
    mutate((l) => {
      l.folders[fid] = { label: '새 폴더', icon: '📁' };
      l.positions[fid] = pos;
      return l;
    });
    setRenamingId(fid);  // 생성 즉시 이름 입력 상태로
  };

  const finishRename = (id: string, name: string) => {
    const clean = name.trim();
    if (clean) mutate((l) => { if (l.folders[id]) l.folders[id] = { ...l.folders[id], label: clean }; return l; });
    setRenamingId(null);
  };

  // 아이콘 정렬 — 홈의 앱·폴더를 현재 표시 순서대로 격자에 재배치하고 지속
  const arrangeIcons = () => {
    const ids = [...homeApps.map((d) => d.id), ...Object.keys(layout.folders)];
    mutate((l) => { ids.forEach((id, i) => { l.positions[id] = autoPos(i); }); return l; });
  };

  const openApp = (a: App) => {
    if (a.soon) return;
    if (a.onOpen) a.onOpen();        // 네이티브 창/외부(사진·파일·블로그·강의)
    else if (a.el) setOpenId(a.id);  // 인라인 계기 → 바로 레벨2 (중간 목록 없음)
  };

  // 레벨 2: 앱(인라인 계기) 열림 → 직접 조작. 뒤로 = 홈 (도메인 중간 단계 폐지).
  const openAppObj = openId ? APPS.find((a) => a.id === openId) || null : null;
  if (openAppObj?.el) {
    return (
      <div className="absolute inset-0 flex flex-col">
        <BackBar onBack={() => setOpenId(null)} crumbs={[openAppObj.label]} />
        <div className="flex-1 min-h-0">{openAppObj.el}</div>
      </div>
    );
  }

  // 앱저장소 — 카탈로그(완전삭제 제외)에서 골라 홈에 추가 / × 로 완전 삭제
  if (storeOpen) {
    return (
      <AppStore domains={catalog} removed={layout.removed} onBack={() => setStoreOpen(false)}
        onAdd={addFromStore} onUninstall={uninstallApp} />
    );
  }

  // 폴더 열림 — 그 폴더에 든 앱들
  const openFolder = openFolderId ? layout.folders[openFolderId] : null;
  if (openFolderId && openFolder) {
    const members = APPS.filter((a) => layout.membership[a.id] === openFolderId);
    return (
      <div className="absolute inset-0 flex flex-col">
        <BackBar onBack={() => setOpenFolderId(null)} crumbs={[`${openFolder.icon} ${openFolder.label}`]} />
        <div className="flex-1 overflow-auto p-8">
          {members.length === 0 ? (
            <Empty label="비어 있습니다 — 홈에서 아이콘을 이 폴더로 끌어 넣으세요" />
          ) : (
            <Grid>
              {members.map((d) => (
                <div key={d.id} className="relative">
                  <IconTile icon={d.icon} label={d.label} onClick={() => { setOpenFolderId(null); openApp(d); }} />
                  <button title="홈으로 꺼내기" onClick={() => ejectFromFolder(d.id)}
                    className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-white border border-stone-300 text-stone-500 text-xs shadow-sm hover:bg-stone-100">⤴</button>
                </div>
              ))}
            </Grid>
          )}
        </div>
      </div>
    );
  }

  // 레벨 0: 자유 배치 홈 (자율주행 데스크탑과 같은 조작)
  return (
    <div className="absolute inset-0 overflow-hidden" onClick={() => setMenu(null)}
      onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }); }}>
      {/* 새 폴더·앱저장소·아이콘 정렬은 빈 곳 오른쪽 클릭 메뉴로 (자율주행 데스크탑과 동일) */}

      {/* 앱 아이콘 — 위치 fallback은 고정 카탈로그 인덱스(홈 목록 변동에 안 흔들림) */}
      {homeApps.map((d) => {
        const p = posOf(d.id, catalogIndex.get(d.id) ?? 0);
        return (
          <DraggableIcon
            // 위치를 key에 넣어 프로그램적 재배치(아이콘 정렬)가 즉시 반영되게 함
            // — DraggableIcon은 position prop을 최초 1회만 내부 state로 받으므로 remount로 갱신.
            key={`${d.id}@${p.join(',')}`}
            icon={d.icon}
            label={d.label}
            position={p}
            whiteTile   // 앱 아이콘 = 흰 배경 타일
            onDoubleClick={() => openApp(d)}
            onPositionChange={(x, y) => setPosition(d.id, x, y)}
            onDragStart={() => {}}
            onDragEnd={() => setHoveringFolderId(null)}
            onDragMove={(x, y) => { checkFolderHover(x, y, d.id); return false; }}
            onDropOnTrash={() => {}}
            onDropOnFolder={(fid) => moveToFolder(d.id, fid)}
            trashHover={false}
            hoveringFolderId={hoveringFolderId}
            onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); setMenu({ x: e.clientX, y: e.clientY, target: { id: d.id, kind: 'app' } }); }}
          />
        );
      })}

      {/* 폴더 아이콘 — 폴더는 생성 시 명시 위치를 가지므로 fallback은 거의 안 쓰이나, 안정적으로 카탈로그 뒤에 둔다 */}
      {folderTargets.map((fid, i) => {
        const f = layout.folders[fid];
        const p = posOf(fid, APPS.length + i);
        return (
          <DraggableIcon
            key={`${fid}@${p.join(',')}`}
            icon={f.icon}
            label={f.label}
            position={p}
            isFolder
            onDoubleClick={() => setOpenFolderId(fid)}
            onPositionChange={(x, y) => setPosition(fid, x, y)}
            onDragStart={() => {}}
            onDragEnd={() => setHoveringFolderId(null)}
            onDragMove={() => false}
            onDropOnTrash={() => {}}
            trashHover={false}
            folderRef={(el) => { folderRefs.current[fid] = el; }}
            hoveringFolderId={hoveringFolderId}
            isFolderHovered={hoveringFolderId === fid}
            onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); setMenu({ x: e.clientX, y: e.clientY, target: { id: fid, kind: 'folder' } }); }}
            isRenaming={renamingId === fid}
            onFinishRename={(name) => finishRename(fid, name)}
            onCancelRename={() => setRenamingId(null)}
          />
        );
      })}

      {/* 컨텍스트 메뉴 — 앱(제거) / 폴더(이름변경·해체) / 빈 데스크탑(새폴더·앱저장소·정렬) */}
      {menu && (
        <div className="fixed z-50 bg-white rounded-lg shadow-lg border border-stone-200 py-1 text-sm text-stone-700 min-w-[150px]"
          style={{ left: menu.x, top: menu.y }} onClick={(e) => e.stopPropagation()}>
          {menu.target?.kind === 'app' ? (
            <>
              {isPromoted(menu.target.id) ? (
                <button className="flex items-center gap-2 w-full text-left px-4 py-1.5 hover:bg-stone-100"
                  onClick={() => { demoteApp(menu.target!.id); setMenu(null); }}><ArrowDownFromLine size={15} /> 런처에서 빼기</button>
              ) : (
                <button className="flex items-center gap-2 w-full text-left px-4 py-1.5 hover:bg-stone-100"
                  onClick={() => { promoteApp(menu.target!.id); setMenu(null); }}><ArrowUpFromLine size={15} /> 런처에 승격</button>
              )}
              <button className="flex items-center gap-2 w-full text-left px-4 py-1.5 hover:bg-stone-100 text-red-600"
                onClick={() => { removeApp(menu.target!.id); setMenu(null); }}><Trash2 size={15} /> 앱 제거</button>
            </>
          ) : menu.target?.kind === 'folder' ? (
            <>
              <button className="block w-full text-left px-4 py-1.5 hover:bg-stone-100"
                onClick={() => { setRenamingId(menu.target!.id); setMenu(null); }}>이름 변경</button>
              <button className="block w-full text-left px-4 py-1.5 hover:bg-stone-100 text-red-600"
                onClick={() => { dissolveFolder(menu.target!.id); setMenu(null); }}>폴더 해체</button>
            </>
          ) : (
            <>
              <button className="flex items-center gap-2 w-full text-left px-4 py-1.5 hover:bg-stone-100"
                onClick={() => { createFolder(); setMenu(null); }}><Plus size={15} /> 새 폴더</button>
              <button className="flex items-center gap-2 w-full text-left px-4 py-1.5 hover:bg-stone-100"
                onClick={() => { setStoreOpen(true); setMenu(null); }}><Package size={15} /> 앱저장소</button>
              <button className="flex items-center gap-2 w-full text-left px-4 py-1.5 hover:bg-stone-100"
                onClick={() => { arrangeIcons(); setMenu(null); }}><LayoutGrid size={15} /> 아이콘 정렬</button>
            </>
          )}
        </div>
      )}

      {homeApps.length === 0 && folderTargets.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-stone-400 text-sm pointer-events-none">
          빈 곳을 오른쪽 클릭해 앱저장소를 여세요
        </div>
      )}
    </div>
  );
}

// ===== 앱저장소 =====
function AppStore({ domains, removed, onBack, onAdd, onUninstall }: {
  domains: App[]; removed: string[]; onBack: () => void; onAdd: (id: string) => void; onUninstall: (id: string) => void;
}) {
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const confirmApp = domains.find((d) => d.id === confirmId) || null;
  return (
    <div className="absolute inset-0 flex flex-col">
      <div className="shrink-0 flex items-center gap-3 px-5 py-3 border-b border-stone-200">
        <button onClick={onBack} className="px-2 py-1 rounded-lg text-stone-500 hover:bg-stone-100">‹ 뒤로</button>
        <span className="text-stone-800 font-medium flex items-center gap-1.5"><Package size={16} /> 앱저장소</span>
        <span className="text-xs text-stone-400">앱을 골라 홈에 추가 · 제거로 완전 삭제</span>
      </div>
      <div className="flex-1 overflow-auto p-6">
        <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3 max-w-4xl mx-auto">
          {domains.map((d) => {
            const isRemoved = removed.includes(d.id);
            return (
              <div key={d.id} className="flex items-center gap-3 p-3 rounded-xl bg-white border border-stone-200 shadow-sm">
                <div className="w-11 h-11 shrink-0 rounded-xl bg-stone-50 border border-stone-100 flex items-center justify-center text-2xl">{d.icon}</div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-stone-700 truncate">{d.label}</div>
                  <div className="mt-1 flex items-center gap-1.5">
                    {isRemoved ? (
                      <button onClick={() => onAdd(d.id)}
                        className="text-xs px-2 py-0.5 rounded-full bg-stone-800 text-white hover:bg-stone-700">＋ 추가</button>
                    ) : (
                      <span className="text-xs text-stone-400">설치됨</span>
                    )}
                    {/* 완전 삭제 — 추가 버튼과 같은 알약 모양, 빨강 */}
                    <button onClick={() => setConfirmId(d.id)}
                      className="text-xs px-2 py-0.5 rounded-full bg-red-50 text-red-600 border border-red-200 hover:bg-red-100">제거</button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 완전 삭제 확인 */}
      {confirmApp && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setConfirmId(null)}>
          <div className="bg-white rounded-2xl shadow-xl border border-stone-200 p-6 max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 text-stone-800 font-medium mb-2">
              <span className="text-2xl">{confirmApp.icon}</span> {confirmApp.label}
            </div>
            <p className="text-sm text-stone-600 leading-relaxed">
              <b className="text-red-600">{confirmApp.label}</b> 앱을 완전 삭제하시겠습니까?<br />
              쌓인 데이터가 초기화되고 앱저장소에서도 사라집니다.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setConfirmId(null)}
                className="px-4 py-1.5 rounded-lg text-sm text-stone-600 hover:bg-stone-100">취소</button>
              <button onClick={() => { onUninstall(confirmApp.id); setConfirmId(null); }}
                className="px-4 py-1.5 rounded-lg text-sm bg-red-600 text-white hover:bg-red-700">완전 삭제</button>
            </div>
          </div>
        </div>
      )}
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
