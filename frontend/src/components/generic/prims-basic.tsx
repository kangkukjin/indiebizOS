/**
 * generic/prims-basic.tsx — 소형 뷰 프리미티브 + 문서 IR 렌더
 *
 * GenericInstrument.tsx 에서 분리(2026-07-18, 1500줄 규칙 모듈화).
 * Card·EmptyMsg·KvRow·Sparkline(플롯)·linkify(URL 링크화)·DocBlock(blocks 문서 IR).
 * p.type 디스패치는 GenericInstrument.tsx ViewPrim(정본 if-chain)에 있다.
 */
import { useState, useRef, type ReactNode } from 'react';
import {
  type AppViewPrim, type Json,
  jget, asList, trendClass, openUrlInApp,
} from './manifest';

export function linkify(text: string): React.ReactNode {
  const s = String(text ?? '');
  const re = /(https?:\/\/[^\s]+)/g;
  const out: React.ReactNode[] = [];
  let last = 0, m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) {
    if (m.index > last) out.push(s.slice(last, m.index));
    const url = m[0];
    out.push(
      <a key={m.index} onClick={(e) => { e.stopPropagation(); openUrlInApp(url); }}
        className="text-emerald-700 underline cursor-pointer break-all">{url}</a>
    );
    last = m.index + url.length;
  }
  if (last === 0) return s;           // URL 없음 — 원본 문자열 그대로
  if (last < s.length) out.push(s.slice(last));
  return out;
}

export function Card({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return (
    <div onClick={onClick}
      className={`bg-white rounded-xl border border-stone-200 p-4 mb-3 ${onClick ? 'cursor-pointer hover:border-stone-400 transition' : ''}`}>
      {children}
    </div>
  );
}

export function EmptyMsg({ p, data }: { p: AppViewPrim; data: unknown }) {
  const m = (p.empty_from ? jget(data, p.empty_from as string) : null) || p.empty || '결과가 없습니다';
  return <p className="text-sm text-stone-400 mt-2">{String(m)}</p>;
}

export function KvRow({ k, v }: { k: string; v: string }) {
  // 값이 http(s) URL 이면 클릭 시 외부 브라우저로 열리는 링크로(공개 사이트 주소 등).
  const isUrl = typeof v === 'string' && /^https?:\/\/\S+$/.test(v.trim());
  return (
    <div className="flex justify-between py-1.5 border-b border-stone-100 last:border-0 text-sm gap-3">
      <span className="text-stone-500 shrink-0">{k}</span>
      {isUrl ? (
        <a href={v.trim()} target="_blank" rel="noopener noreferrer"
           className="text-blue-700 hover:underline text-right break-all">{v.trim()}</a>
      ) : (
        <span className="text-stone-800 text-right">{v}</span>
      )}
    </div>
  );
}

// 스파크라인 수치 포맷 — 큰 값(가격)은 천단위 콤마·정수, 작은 값(환율·코인)은 소수.
function fmtSpark(n: number): string {
  const a = Math.abs(n);
  const d = a >= 1000 ? 0 : a >= 1 ? 2 : 4;
  return n.toLocaleString(undefined, { maximumFractionDigits: d });
}

export function Sparkline({ p, data }: { p: AppViewPrim; data: unknown }) {
  const arr = asList(data, p.from);
  // x축 라벨 필드: 매니페스트 p.x 우선, 없으면 흔한 시간 필드 자동 감지(date/time/label).
  const first = arr[0] as Json | undefined;
  const xkey = (p.x as string) || (first && typeof first === 'object'
    ? ['date', 'time', 'label', 'x'].find((k) => (first as Json)[k] != null) : undefined);
  const rows = arr
    .map((x) => ({ v: Number(p.y ? (x as Json)[p.y as string] : x), x: xkey ? String((x as Json)[xkey] ?? '') : '' }))
    .filter((r) => !isNaN(r.v));
  const [hi, setHi] = useState<number | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  if (rows.length < 2) return null;
  const vals = rows.map((r) => r.v);
  const up = !trendClass(p, data) || trendClass(p, data) === 'text-red-500';
  const w = 280, h = 50;
  const mn = Math.min(...vals), mx = Math.max(...vals), rg = mx - mn || 1;
  const px = (i: number) => (i / (rows.length - 1)) * w;
  const py = (v: number) => h - ((v - mn) / rg) * h;
  const pts = rows.map((r, i) => `${px(i).toFixed(1)},${py(r.v).toFixed(1)}`).join(' ');
  const stroke = up ? 'stroke-red-400' : 'stroke-blue-500';
  const dot = up ? 'bg-red-400' : 'bg-blue-500';

  const onMove = (e: React.MouseEvent) => {
    const el = boxRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    setHi(Math.round(frac * (rows.length - 1)));
  };

  const cur = hi != null ? rows[hi] : null;
  return (
    <Card>
      <div className="relative">
        {/* 플롯 — y축 스케일(최고/최저가)은 플롯 안쪽에 얹어 날짜 줄과 겹치지 않게 한다 */}
        <div ref={boxRef} className="relative h-16" onMouseMove={onMove} onMouseLeave={() => setHi(null)}>
          <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full h-full">
            <polyline points={pts} fill="none" strokeWidth={1.5} vectorEffect="non-scaling-stroke" className={stroke} />
            {cur && <line x1={px(hi!)} y1={0} x2={px(hi!)} y2={h} strokeWidth={0.5} vectorEffect="non-scaling-stroke" className="stroke-stone-300" />}
          </svg>
          {cur && (
            <div className={`absolute w-1.5 h-1.5 -ml-[3px] -mt-[3px] rounded-full ${dot}`}
              style={{ left: `${(hi! / (rows.length - 1)) * 100}%`, top: `${(py(cur.v) / h) * 100}%` }} />
          )}
          <div className="absolute right-0 top-0 text-[10px] text-stone-400 leading-none bg-white/70 px-0.5 rounded z-10">{fmtSpark(mx)}</div>
          <div className="absolute right-0 bottom-0 text-[10px] text-stone-400 leading-none bg-white/70 px-0.5 rounded z-10">{fmtSpark(mn)}</div>
        </div>
        {/* x축 날짜 + 호버 시 해당 시점 값 */}
        <div className="flex justify-between items-baseline text-[10px] text-stone-400 mt-1">
          <span>{rows[0].x}</span>
          <span className="text-stone-700 font-medium">{cur ? `${cur.x ? cur.x + ' · ' : ''}${fmtSpark(cur.v)}` : ''}</span>
          <span>{rows[rows.length - 1].x}</span>
        </div>
      </div>
    </Card>
  );
}

// ===== blocks — 문서 IR 렌더 (표현 언어 층위 조항: 페이로드 IR의 정적 부분집합이 표면 언어에 옴) =====
// [self:read]{blocks:true}·[table:structure] 출력(items=블록 배열 {type,...})을 문서로 그린다.
// 블록 구조는 IR이 정본 — 여기선 인라인 마크다운(**굵게**·`코드`·[링크](url))만 얇게 해석.
const MD_INLINE_RE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g;
function mdInline(text: unknown): ReactNode[] {
  return String(text ?? '').split(MD_INLINE_RE).filter(Boolean).map((seg, i) => {
    if (seg.startsWith('**') && seg.endsWith('**') && seg.length > 4) return <strong key={i}>{seg.slice(2, -2)}</strong>;
    if (seg.startsWith('`') && seg.endsWith('`') && seg.length > 2) return <code key={i} className="bg-stone-100 px-1 rounded text-[0.88em]">{seg.slice(1, -1)}</code>;
    const m = seg.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
    if (m) return <a key={i} href={m[2]} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline">{m[1]}</a>;
    return <span key={i}>{seg}</span>;
  });
}

const HEADING_CLS: Record<number, string> = {
  1: 'text-xl mt-4 mb-2',
  2: 'text-lg mt-4 mb-1.5 border-b border-stone-200 pb-1',
  3: 'text-base mt-3 mb-1',
  4: 'text-sm mt-2.5 mb-1',
};

export function DocBlock({ b }: { b: Json }) {
  const t = String(b.type || 'paragraph');
  if (t === 'heading') {
    const lvl = Math.min(6, Math.max(1, Number(b.level) || 2));
    return <div className={`font-bold text-stone-900 ${HEADING_CLS[lvl] || 'text-sm mt-2 mb-1'}`}>{mdInline(b.text)}</div>;
  }
  if (t === 'list') {
    const items = (Array.isArray(b.items) ? b.items : []) as unknown[];
    const Tag = (b.ordered ? 'ol' : 'ul') as 'ol' | 'ul';
    return (
      <Tag className={`${b.ordered ? 'list-decimal' : 'list-disc'} pl-5 my-1.5 space-y-1`}>
        {items.map((it, i) => {
          const o = (typeof it === 'object' && it !== null ? it : null) as Json | null;
          const text = o ? String(o.text ?? '') : String(it ?? '');
          const url = o?.url ? String(o.url) : '';
          return (
            <li key={i} className="text-sm text-stone-700 leading-relaxed whitespace-pre-wrap">
              {url
                ? <a href={url} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline">{text}</a>
                : mdInline(text)}
            </li>
          );
        })}
      </Tag>
    );
  }
  if (t === 'table') {
    const cols = (Array.isArray(b.columns) ? b.columns : []) as unknown[];
    const rows = (Array.isArray(b.rows) ? b.rows : []).filter((r) => Array.isArray(r)) as unknown[][];
    return (
      <div className="overflow-x-auto my-2">
        <table className="text-sm border-collapse w-full">
          {cols.length > 0 && (
            <thead><tr>{cols.map((c, i) => <th key={i} className="border border-stone-200 bg-stone-50 px-2.5 py-1.5 text-left font-semibold text-stone-700">{String(c ?? '')}</th>)}</tr></thead>
          )}
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>{r.map((c, j) => <td key={j} className="border border-stone-200 px-2.5 py-1.5 text-stone-700">{String(c ?? '')}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (t === 'quote') {
    return (
      <blockquote className="border-l-4 border-stone-300 pl-3 my-2 text-sm text-stone-500 whitespace-pre-wrap">
        {mdInline(b.text)}
        {!!b.cite && <cite className="block mt-1 text-xs not-italic text-stone-400">— {String(b.cite)}</cite>}
      </blockquote>
    );
  }
  if (t === 'code') {
    return <pre className="bg-stone-50 border border-stone-200 rounded-lg p-3 my-2 text-xs overflow-x-auto"><code>{String(b.text ?? '')}</code></pre>;
  }
  if (t === 'divider') return <hr className="my-3 border-stone-200" />;
  if (t === 'image') {
    const src = String(b.src || b.path || '');
    if (!src) return null;
    return (
      <figure className="my-2">
        <img src={src} alt={String(b.caption ?? '')} className="max-w-full rounded-lg" loading="lazy" />
        {!!b.caption && <figcaption className="text-xs text-stone-400 text-center mt-1">{String(b.caption)}</figcaption>}
      </figure>
    );
  }
  return <p className="text-sm text-stone-700 leading-relaxed my-1.5 whitespace-pre-wrap">{mdInline(b.text)}</p>;
}
