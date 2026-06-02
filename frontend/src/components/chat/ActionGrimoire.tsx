/**
 * ActionGrimoire — IBL 액션 사전 모달 ("마법책")
 *
 * indiebizOS의 신경계인 IBL 액션을 사용자가 발견할 수 있게 한다.
 * 액션을 클릭하면 actionId가 다음 메시지에 함께 전송되어, 해마 검색 대신
 * 그 액션이 의식 에이전트에 Top-1로 주입된다 (실행기억 자리 대체).
 *
 * 디자인 원칙: 기능 메뉴가 아니라 마법사의 책장. 사용자 인지를 보완한다.
 */
import { useEffect, useState } from 'react';
import { BookOpen, X } from 'lucide-react';

interface ActionMeta {
  description: string;
  target_description: string;
  target_key: string;
  implementation: string;
  keywords: string[];
  group?: string;
}

interface NodeData {
  actions: Record<string, ActionMeta>;
  count: number;
}

interface CatalogResponse {
  nodes: Record<string, NodeData>;
  total: number;
}

interface ActionGrimoireProps {
  open: boolean;
  onClose: () => void;
  onSelect: (actionId: string) => void;
}

const NODE_LABELS: Record<string, { ko: string; sub: string }> = {
  sense: { ko: '감각', sub: '세계를 보는 창' },
  self: { ko: '자아', sub: '스스로의 기억과 행위' },
  limbs: { ko: '사지', sub: '바깥에 손을 뻗다' },
  others: { ko: '타자', sub: '이웃과 협력자' },
  engines: { ko: '엔진', sub: '복합 생성과 변환' },
};

const NODE_ORDER = ['sense', 'self', 'limbs', 'others', 'engines'];

// 그룹 한국어 라벨 + 표시 순서. yaml의 group 값이 매칭되지 않으면 raw 값을 그대로 보여준다.
const GROUP_LABELS: Record<string, string> = {
  // sense
  finance: '금융·투자',
  real_estate: '부동산',
  research: '검색·연구',
  culture: '문화·도서',
  media: '영상·CCTV·라디오',
  places: '장소·수집',
  world: '세계',
  // self
  file: '파일·저장소',
  schedule: '스케줄·트리거',
  lecture: '강의·슬라이드',
  blog: '블로그',
  photo: '사진',
  memory: '기억',
  workflow: '워크플로우',
  goal: '목표',
  system: '시스템',
  data: '건강·CCTV·출력',
  // limbs
  browser: '브라우저',
  browser_session: '브라우저 세션',
  open: '앱·창 열기',
  desktop: '데스크톱 (macOS)',
  cloudflare: 'Cloudflare',
  // others
  delegation: '위임',
  channel: '채널',
  neighbor: '이웃',
  // engines
  media_produce: '미디어 생성',
  chart: '차트',
  music: '음악',
  web_builder: '웹 빌더',
};

const GROUP_ORDER = [
  // sense
  'finance', 'real_estate', 'research', 'culture', 'media', 'places', 'world',
  // self
  'file', 'schedule', 'lecture', 'blog', 'photo', 'memory',
  'workflow', 'goal', 'system', 'data',
  // limbs
  'browser', 'browser_session', 'open', 'desktop', 'cloudflare',
  // others
  'delegation', 'channel', 'neighbor',
  // engines
  'media_produce', 'chart', 'music', 'web_builder',
];

export function ActionGrimoire({ open, onClose, onSelect }: ActionGrimoireProps) {
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoveredAction, setHoveredAction] = useState<{ node: string; action: string } | null>(null);
  const [visible, setVisible] = useState(false);

  // 카탈로그 페치 — 한 번만 (모달이 처음 열릴 때)
  useEffect(() => {
    if (!open || catalog) return;
    setLoading(true);
    setError(null);
    fetch('http://127.0.0.1:8765/ibl/actions/catalog')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: CatalogResponse) => setCatalog(data))
      .catch((err) => {
        console.error('[마법책] 카탈로그 페치 실패:', err);
        setError(String(err));
      })
      .finally(() => setLoading(false));
  }, [open, catalog]);

  // 등장 애니메이션: 다음 프레임에 visible=true로 전환
  useEffect(() => {
    if (!open) {
      setVisible(false);
      return;
    }
    const id = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(id);
  }, [open]);

  // ESC로 닫기
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const handleSelect = (node: string, action: string) => {
    onSelect(`${node}:${action}`);
    onClose();
  };

  const hoveredMeta =
    hoveredAction && catalog
      ? catalog.nodes[hoveredAction.node]?.actions[hoveredAction.action]
      : null;

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm transition-opacity duration-200 ${
        visible ? 'opacity-100' : 'opacity-0'
      }`}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`relative w-[min(90vw,900px)] max-h-[80vh] flex flex-col bg-[#FEF9EE] border border-[#D6C8A8] rounded-2xl shadow-2xl transition-all duration-200 ease-out ${
          visible ? 'opacity-100 scale-100' : 'opacity-0 scale-95'
        }`}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#E5D5B0] bg-gradient-to-r from-[#F3E5C2] to-[#FEF9EE] rounded-t-2xl">
          <div className="flex items-center gap-3">
            <BookOpen size={22} className="text-[#92400E]" />
            <div>
              <h2 className="text-lg font-semibold text-[#4A4035]">마법책 — IBL 액션 사전</h2>
              {catalog && (
                <p className="text-xs text-[#A09080]">
                  {catalog.total}개 액션 · 5개 노드 · 클릭하여 선택
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-[#A09080] hover:text-[#4A4035] p-1.5 rounded-lg hover:bg-[#E5D5B0]/40 transition-colors"
            title="닫기 (ESC)"
          >
            <X size={20} />
          </button>
        </div>

        {/* 본문 */}
        <div className="flex-1 overflow-hidden flex">
          {/* 카탈로그 그리드 */}
          <div className="flex-1 overflow-y-auto p-6">
            {loading && (
              <div className="text-center text-[#A09080] py-12">책장을 펼치는 중…</div>
            )}
            {error && (
              <div className="text-center text-red-600 py-8">
                카탈로그를 불러오지 못했습니다: {error}
              </div>
            )}
            {catalog &&
              NODE_ORDER.filter((node) => catalog.nodes[node]).map((node) => {
                const nodeData = catalog.nodes[node];
                const labels = NODE_LABELS[node] || { ko: node, sub: '' };
                const actions = Object.entries(nodeData.actions);

                // 그룹별 분류 — group 필드가 있는 액션만 그룹 섹션으로 묶고,
                // 비어있는 경우는 '__ungrouped' 키로 평탄 표시.
                const grouped: Record<string, [string, ActionMeta][]> = {};
                for (const [action, meta] of actions) {
                  const g = meta.group || '__ungrouped';
                  if (!grouped[g]) grouped[g] = [];
                  grouped[g].push([action, meta]);
                }
                // 표시 순서: GROUP_ORDER 우선, 그 외 그룹은 알파벳, __ungrouped는 마지막
                const groupKeys = Object.keys(grouped);
                groupKeys.sort((a, b) => {
                  if (a === '__ungrouped') return 1;
                  if (b === '__ungrouped') return -1;
                  const ia = GROUP_ORDER.indexOf(a);
                  const ib = GROUP_ORDER.indexOf(b);
                  if (ia !== -1 && ib !== -1) return ia - ib;
                  if (ia !== -1) return -1;
                  if (ib !== -1) return 1;
                  return a.localeCompare(b);
                });
                const hasGroups = groupKeys.some((k) => k !== '__ungrouped');

                return (
                  <section key={node} className="mb-6 last:mb-0">
                    <div className="flex items-baseline gap-2 mb-2">
                      <h3 className="text-base font-semibold text-[#4A4035]">
                        {labels.ko}
                      </h3>
                      <span className="text-xs text-[#A09080]">
                        {node} · {nodeData.count}
                      </span>
                      <span className="text-xs text-[#A09080] italic">{labels.sub}</span>
                    </div>
                    {hasGroups ? (
                      <div className="space-y-3">
                        {groupKeys.map((g) => {
                          const items = grouped[g];
                          const label =
                            g === '__ungrouped' ? '기타' : GROUP_LABELS[g] || g;
                          return (
                            <div key={g}>
                              <div className="text-[11px] font-semibold text-[#92400E] uppercase tracking-wide mb-1">
                                {label}
                                <span className="ml-1.5 text-[#A09080] font-normal normal-case">
                                  · {items.length}
                                </span>
                              </div>
                              <div className="flex flex-wrap gap-1.5">
                                {items.map(([action, meta]) => (
                                  <button
                                    key={action}
                                    onClick={() => handleSelect(node, action)}
                                    onMouseEnter={() =>
                                      setHoveredAction({ node, action })
                                    }
                                    onMouseLeave={() => setHoveredAction(null)}
                                    className="px-2.5 py-1 text-xs font-mono bg-white border border-[#E5D5B0] rounded-md text-[#4A4035] hover:bg-[#FFE9B8] hover:border-[#D97706] hover:text-[#92400E] transition-colors"
                                    title={meta.description}
                                  >
                                    {action}
                                  </button>
                                ))}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {actions.map(([action, meta]) => (
                          <button
                            key={action}
                            onClick={() => handleSelect(node, action)}
                            onMouseEnter={() => setHoveredAction({ node, action })}
                            onMouseLeave={() => setHoveredAction(null)}
                            className="px-2.5 py-1 text-xs font-mono bg-white border border-[#E5D5B0] rounded-md text-[#4A4035] hover:bg-[#FFE9B8] hover:border-[#D97706] hover:text-[#92400E] transition-colors"
                            title={meta.description}
                          >
                            {action}
                          </button>
                        ))}
                      </div>
                    )}
                  </section>
                );
              })}
          </div>

          {/* 호버 시 상세 패널 */}
          {hoveredMeta && hoveredAction && (
            <aside className="w-80 shrink-0 border-l border-[#E5D5B0] bg-[#FFFCF4] p-5 overflow-y-auto">
              <div className="font-mono text-sm text-[#92400E] mb-2">
                [{hoveredAction.node}:{hoveredAction.action}]
              </div>
              <p className="text-sm text-[#4A4035] mb-3 leading-relaxed">
                {hoveredMeta.description}
              </p>
              {hoveredMeta.target_description && (
                <div className="text-xs text-[#A09080] mb-2 leading-relaxed">
                  <span className="font-semibold">파라미터:</span>{' '}
                  {hoveredMeta.target_key ? (
                    <code className="bg-[#F3E5C2] px-1 rounded">{hoveredMeta.target_key}</code>
                  ) : null}{' '}
                  — {hoveredMeta.target_description}
                </div>
              )}
              {hoveredMeta.implementation && (
                <div className="text-xs text-[#A09080] mt-3 pt-3 border-t border-[#E5D5B0] leading-relaxed">
                  <span className="font-semibold">구현:</span> {hoveredMeta.implementation}
                </div>
              )}
            </aside>
          )}
        </div>

        {/* 푸터 안내 */}
        <div className="px-6 py-3 border-t border-[#E5D5B0] text-xs text-[#A09080] bg-[#FBF1D9]/40 rounded-b-2xl text-center">
          액션을 선택하면 다음 메시지에 함께 전달됩니다 · ESC로 닫기
        </div>
      </div>
    </div>
  );
}
