/**
 * MusicGraphInstrument — 음악 관련곡 그래프 뷰 (Obsidian 로컬 그래프의 음악판).
 *
 * [self:music]{op:"graph"} 에고 그래프(중심곡+1홉 top-10+2홉)를 SVG 방사 레이아웃으로.
 * 노드 클릭 = 그 곡으로 중심 이동 + 재생. 곡이 끝나면(자동 이어듣기 ON) 관련곡(1홉) 중
 * 랜덤으로 다음 곡 — 그래프 산책이 곧 랜덤 플레이. 데스크탑 전용 커스텀 계기
 * (선언형 뷰 어휘 밖 — new_action_checklist '갈래 판별'의 리치 계기 갈래).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { runIBL, audioUrl, mediaSrc, fieldCls, type Json } from './generic/manifest';

interface GNode {
  path: string; title: string; artist: string; album: string;
  image: string; stream: string; ring: number; meta: string;
}
interface GraphData { nodes: GNode[]; edges: [number, number][]; center: string | null; message?: string }

const iblStr = (v: string) => v.replace(/\\/g, '\\\\').replace(/"/g, '\\"');

/** 방사 레이아웃 — 중심(0홉) 가운데, 1홉 안쪽 원, 2홉 부모 각도 근처 바깥 원 */
function layout(nodes: GNode[], edges: [number, number][], W: number, H: number): [number, number][] {
  const cx = W / 2, cy = H / 2;
  const r1 = Math.min(W, H) * 0.27, r2 = Math.min(W, H) * 0.44;
  const pos: [number, number][] = nodes.map(() => [cx, cy]);
  const ring1 = nodes.map((n, i) => (n.ring === 1 ? i : -1)).filter((i) => i >= 0);
  const angle: Record<number, number> = {};
  ring1.forEach((idx, k) => {
    const a = (k / Math.max(1, ring1.length)) * Math.PI * 2 - Math.PI / 2;
    angle[idx] = a;
    pos[idx] = [cx + r1 * Math.cos(a), cy + r1 * Math.sin(a)];
  });
  // 2홉 — 부모(1홉) 각도 주변으로 부챗살
  const kids: Record<number, number[]> = {};
  nodes.forEach((n, i) => {
    if (n.ring !== 2) return;
    const e = edges.find(([a, b]) => (a === i && angle[b] != null) || (b === i && angle[a] != null));
    const parent = e ? (e[0] === i ? e[1] : e[0]) : ring1[0];
    (kids[parent] ??= []).push(i);
  });
  Object.entries(kids).forEach(([p, arr]) => {
    const base = angle[Number(p)] ?? 0;
    arr.forEach((idx, k) => {
      const a = base + (k - (arr.length - 1) / 2) * 0.28;
      pos[idx] = [cx + r2 * Math.cos(a), cy + r2 * Math.sin(a)];
    });
  });
  return pos;
}

const trunc = (s: string, n: number) => (s.length > n ? s.slice(0, n) + '…' : s);

export function MusicGraphInstrument() {
  const [data, setData] = useState<GraphData | null>(null);
  const [q, setQ] = useState('');
  const [now, setNow] = useState<GNode | null>(null);   // 재생 중인 곡
  const [auto, setAuto] = useState(true);               // 자동 이어듣기(랜덤 워크)
  const [busy, setBusy] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const dataRef = useRef<GraphData | null>(null);
  dataRef.current = data;
  const autoRef = useRef(auto);
  autoRef.current = auto;

  const load = useCallback(async (opts: { path?: string; q?: string }) => {
    setBusy(true);
    try {
      const param = opts.path ? `path: "${iblStr(opts.path)}"` : opts.q ? `q: "${iblStr(opts.q)}"` : '';
      const d = (await runIBL(`[self:music]{op: "graph"${param ? ', ' + param : ''}}`)) as Json;
      const nodes = (d.items as GNode[]) || [];
      setData({ nodes, edges: (d.edges as [number, number][]) || [], center: (d.center as string) || null,
                message: (d.message as string) || '' });
    } catch (e) {
      setData({ nodes: [], edges: [], center: null, message: String(e) });
    } finally { setBusy(false); }
  }, []);

  useEffect(() => { load({}); }, [load]);

  const play = useCallback((n: GNode) => {
    setNow(n);
    const el = audioRef.current;
    if (el) { el.src = audioUrl(n.stream); el.play().catch(() => {}); }
  }, []);

  // 노드 클릭 — 그 곡으로 중심 이동 + 재생 (Obsidian 로컬 그래프 내비게이션)
  const focusNode = useCallback((n: GNode) => { play(n); load({ path: n.path }); }, [play, load]);

  // 랜덤 다음 곡 — 현재 그래프의 1홉(관련곡 top-10) 중 하나
  const randomNext = useCallback(() => {
    const d = dataRef.current;
    if (!d) return;
    const ring1 = d.nodes.filter((n) => n.ring === 1);
    if (!ring1.length) return;
    focusNode(ring1[Math.floor(Math.random() * ring1.length)]);
  }, [focusNode]);

  const nodes = data?.nodes ?? [];
  const W = 920, H = 560;
  const pos = data ? layout(nodes, data.edges, W, H) : [];
  const R = [30, 24, 16];  // 홉별 노드 반지름

  return (
    <div className="h-full flex flex-col bg-stone-50">
      {/* 상단 바 — 중심곡 검색 + 자동 이어듣기 토글 */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-stone-200 bg-white">
        <span className="text-sm font-semibold text-stone-700 shrink-0">🕸️ 음악 그래프</span>
        <input value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && q.trim()) load({ q: q.trim() }); }}
          placeholder="중심에 둘 곡 검색 (제목·아티스트·앨범)" className={`${fieldCls} flex-1 min-w-0`} />
        <button onClick={() => q.trim() && load({ q: q.trim() })}
          className="px-3 py-2 rounded-lg bg-stone-800 text-white text-sm hover:bg-stone-700 shrink-0">이동</button>
        <button onClick={randomNext} title="관련곡 중 랜덤으로 이동+재생"
          className="px-3 py-2 rounded-lg border border-stone-300 text-sm text-stone-600 hover:border-stone-500 shrink-0">🎲 랜덤</button>
        <label className="flex items-center gap-1.5 text-xs text-stone-500 shrink-0 cursor-pointer">
          <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
          자동 이어듣기
        </label>
      </div>

      {/* 그래프 */}
      <div className="flex-1 min-h-0 overflow-auto">
        {busy && !data && <p className="text-sm text-stone-400 p-6">그래프를 불러오는 중…</p>}
        {data && !nodes.length && (
          <p className="text-sm text-stone-400 p-6">
            {data.message || '라이브러리가 비어 있습니다.'} 🎧 음악 앱의 보관함 탭에서 폴더를 등록·스캔하면 그래프가 생깁니다.
          </p>
        )}
        {nodes.length > 0 && (
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full" style={{ minHeight: 420 }}>
            {data!.edges.map(([a, b], i) => (
              pos[a] && pos[b] && (
                <line key={i} x1={pos[a][0]} y1={pos[a][1]} x2={pos[b][0]} y2={pos[b][1]}
                  stroke="#d6d3d1" strokeWidth={nodes[a].ring === 0 || nodes[b].ring === 0 ? 1.6 : 0.8} />
              )
            ))}
            {nodes.map((n, i) => {
              const [x, y] = pos[i] || [0, 0];
              const r = R[n.ring] ?? 14;
              const playing = now?.path === n.path;
              return (
                <g key={n.path} transform={`translate(${x},${y})`} onClick={() => focusNode(n)}
                  style={{ cursor: 'pointer' }}>
                  <title>{`${n.title} — ${n.artist}${n.album ? ' · ' + n.album : ''} (클릭=재생+중심 이동)`}</title>
                  <clipPath id={`clip${i}`}><circle r={r} /></clipPath>
                  <circle r={r + 2.5} fill={playing ? '#f59e0b' : n.ring === 0 ? '#a8a29e' : '#e7e5e4'} />
                  <image href={mediaSrc(n.image)} x={-r} y={-r} width={r * 2} height={r * 2}
                    clipPath={`url(#clip${i})`} preserveAspectRatio="xMidYMid slice" />
                  <text y={r + 13} textAnchor="middle" fontSize={n.ring === 0 ? 12 : 10}
                    fill={playing ? '#b45309' : '#57534e'} fontWeight={n.ring === 0 ? 600 : 400}>
                    {trunc(n.title, n.ring === 2 ? 10 : 16)}
                  </text>
                </g>
              );
            })}
          </svg>
        )}
      </div>

      {/* 하단 재생 바 */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-t border-stone-200 bg-white">
        <div className="text-sm text-stone-700 min-w-0 truncate flex-1">
          {now ? <>▶ <b>{now.title}</b> — {now.artist}{auto && <span className="text-xs text-stone-400"> · 끝나면 관련곡 랜덤</span>}</>
               : <span className="text-stone-400">노드를 클릭하면 재생됩니다</span>}
        </div>
        <audio ref={audioRef} controls preload="none" className="h-9 w-72 shrink-0"
          onEnded={() => { if (autoRef.current) randomNext(); }} />
      </div>
    </div>
  );
}
