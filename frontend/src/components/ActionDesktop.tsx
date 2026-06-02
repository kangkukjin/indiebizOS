/**
 * ActionDesktop — 런처의 두 번째 탭 "액션 데스크탑"
 *
 * 스마트폰 홈 화면 구조:
 *   도메인 아이콘(부동산·투자…) → 누르면 그 도메인의 계기들 → 계기를 열면 직접 조작
 *
 * 프로젝트 탭이 '에이전트에게 맡기는' 오토파일럿이라면,
 * 이 탭은 '내가 직접 다이얼을 도는' 수동 운전이다. 같은 도메인의 두 얼굴.
 */
import { useState, type ReactNode } from 'react';
import { RealtyInstrument } from './RealtyInstrument';
import { CommercialInstrument } from './CommercialInstrument';
import { BookInstrument } from './BookInstrument';
import { InvestInstrument } from './InvestInstrument';
import { WeatherInstrument } from './WeatherInstrument';
import { CultureInstrument } from './CultureInstrument';
import { LocalInstrument } from './LocalInstrument';
import { RadioInstrument } from './RadioInstrument';
import { YtMusicInstrument } from './YtMusicInstrument';

// 계기는 두 종류 — 인라인으로 펼쳐지는 것(el)과, 누르면 별도 네이티브 창을 띄우는 것(onOpen).
interface Instrument { id: string; icon: string; label: string; el?: ReactNode; onOpen?: () => void; soon?: boolean }
// 도메인도 onOpen을 가질 수 있다 — 계기 화면을 거치지 않고 홈에서 바로 액션을 실행하는 단일 아이콘.
interface Domain { id: string; icon: string; label: string; soon?: boolean; onOpen?: () => void; instruments: Instrument[] }

// 앱 모드 IBL 직접 실행(0 토큰) — BookInstrument와 동일한 경로/프로젝트 컨텍스트.
function runIBL(code: string) {
  fetch('http://127.0.0.1:8765/ibl/execute', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, project_id: '앱모드' }),
  }).catch(() => { /* 액션이 브라우저를 띄우므로 응답은 신경쓰지 않음 */ });
}

// 도메인 → 계기 구성. 부동산/실거래가만 실제 동작, 나머지는 구조를 보여주는 자리.
const DOMAINS: Domain[] = [
  {
    id: 'realestate', icon: '🏢', label: '부동산',
    instruments: [
      { id: 'realty', icon: '🏢', label: '실거래가', el: <RealtyInstrument /> },
      { id: 'commercial', icon: '🏪', label: '상권', el: <CommercialInstrument /> },
      { id: 'listing', icon: '🔑', label: '매물', soon: true },
    ],
  },
  {
    id: 'book', icon: '📚', label: '도서',
    instruments: [
      { id: 'booksearch', icon: '📖', label: '도서검색', el: <BookInstrument /> },
    ],
  },
  {
    id: 'device', icon: '🖥️', label: '내 기기',
    instruments: [
      { id: 'photo', icon: '📷', label: '사진', onOpen: () => window.electron?.openPhotoManagerWindow?.(null) },
      { id: 'pcmanager', icon: '🗂️', label: 'PC 관리', onOpen: () => window.electron?.openPCManagerWindow?.(null) },
    ],
  },
  // 즐겨찾기 사이트 런처 — 홈 아이콘 한 번으로 [limbs:launch] 실행(Launchpad 띄우기).
  { id: 'launchpad', icon: '🚀', label: '즐겨찾기', onOpen: () => runIBL('[limbs:launch]'), instruments: [] },
  // 강의 만들기 — 홈 아이콘 한 번으로 강의 워크스페이스 네이티브 창 열기.
  { id: 'lecture', icon: '🎓', label: '강의 만들기', onOpen: () => window.electron?.openLectureWorkspaceWindow?.(null), instruments: [] },
  {
    id: 'invest', icon: '📈', label: '투자',
    instruments: [
      { id: 'market', icon: '📈', label: '주식·코인', el: <InvestInstrument /> },
    ],
  },
  {
    id: 'local', icon: '🗺️', label: '지역정보',
    instruments: [
      { id: 'places', icon: '🗺️', label: '장소·맛집', el: <LocalInstrument /> },
    ],
  },
  {
    id: 'weather', icon: '🌤️', label: '날씨',
    instruments: [
      { id: 'forecast', icon: '🌤️', label: '날씨·예보', el: <WeatherInstrument /> },
    ],
  },
  {
    id: 'culture', icon: '🎭', label: '문화공연',
    instruments: [
      { id: 'showexhibit', icon: '🎭', label: '공연·전시', el: <CultureInstrument /> },
    ],
  },
  {
    id: 'radio', icon: '📻', label: '라디오',
    instruments: [
      { id: 'radioplayer', icon: '📻', label: '라디오', el: <RadioInstrument /> },
    ],
  },
  {
    id: 'ytmusic', icon: '🎵', label: '유튜브 뮤직',
    instruments: [
      { id: 'ytmusicplayer', icon: '🎵', label: '재생·저장', el: <YtMusicInstrument /> },
    ],
  },
];

export function ActionDesktop() {
  const [domainId, setDomainId] = useState<string | null>(null);
  const [instrumentId, setInstrumentId] = useState<string | null>(null);

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
