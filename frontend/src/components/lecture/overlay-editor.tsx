/**
 * 강의 워크스페이스 — '글자 얹기' 배치 편집기 (2026-08-09)
 *
 * PowerPoint식 직접 조작: base(원본) 이미지 위에 글자 박스를 드래그로 놓고,
 * 크기·서체·색·배경칩을 박스별로 고른 뒤 저장하면 서버가 원본에서 재합성한다.
 * 미리보기 CSS는 합성기(media_producer/slide_overlay.py)와 같은 규칙 — 둘 다
 * Chromium이라 저장 결과가 미리보기와 거의 픽셀 단위로 일치한다.
 */
import { useEffect, useRef, useState } from 'react';
import { api } from '../../lib/api';
import type { TextOverlay } from '../../lib/api-lecture-workspace';

// 합성기(slide_overlay.py)와 동기 — 폰트 스택·크기 키워드·웹폰트 링크
const FONTS: Record<string, string> = {
  sans: "Pretendard, 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif",
  serif: "'Noto Serif KR', 'Nanum Myeongjo', AppleMyungjo, Batang, serif",
  gowun: "'Gowun Batang', 'Noto Serif KR', serif",
  jua: "'Jua', 'Noto Sans KR', sans-serif",
  black: "'Black Han Sans', 'Noto Sans KR', sans-serif",
  pen: "'Nanum Pen Script', cursive",
  brush: "'Nanum Brush Script', cursive",
};
const FONT_LABELS: [string, string][] = [
  ['sans', '고딕'], ['serif', '명조'], ['gowun', '고운바탕'], ['jua', '주아(둥근)'],
  ['black', '헤드라인'], ['pen', '손글씨'], ['brush', '붓글씨'],
];
const FONT_LINK =
  'https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600&family=Noto+Serif+KR:wght@400;600' +
  '&family=Gowun+Batang:wght@400;700&family=Jua&family=Black+Han+Sans' +
  '&family=Nanum+Pen+Script&family=Nanum+Brush+Script&display=swap';
const SIZE_VW: Record<string, number> = { small: 2.0, medium: 2.9, large: 4.0 };

const CANVAS_W = 896;
const CANVAS_H = 504; // 16:9

function sizeVwOf(ov: TextOverlay): number {
  if (typeof ov.size_vw === 'number' && ov.size_vw >= 0.5 && ov.size_vw <= 12) return ov.size_vw;
  return SIZE_VW[ov.size || 'small'] ?? 2.0;
}

function isDark(color?: string): boolean {
  const c = (color || 'white').trim();
  if (c === 'black') return true;
  if (c.startsWith('#')) {
    const hex = c.length >= 7 ? c.slice(1, 7) : c.slice(1, 4).split('').map((ch) => ch + ch).join('');
    const n = parseInt(hex, 16);
    if (!Number.isNaN(n)) {
      const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
      return 0.299 * r + 0.587 * g + 0.114 * b < 128;
    }
  }
  return false;
}

/** 박스 스타일 — 합성기 CSS 사상 (x/y 자유 좌표 전제: 편집기는 열 때 전부 x/y로 변환). */
function boxStyle(ov: TextOverlay, selected: boolean): React.CSSProperties {
  const vw = sizeVwOf(ov);
  const dark = isDark(ov.color);
  const color = ov.color === 'black' ? '#111111' : ov.color === 'white' || !ov.color ? '#ffffff' : ov.color;
  const style: React.CSSProperties = {
    position: 'absolute',
    left: `${ov.x ?? 50}%`,
    top: `${ov.y ?? 50}%`,
    maxWidth: '70%',
    whiteSpace: 'pre-line',
    lineHeight: 1.35,
    fontWeight: ov.weight === 'normal' ? 400 : 600,
    fontFamily: FONTS[ov.font || 'sans'] || FONTS.sans,
    fontSize: `${(vw / 100) * CANVAS_W}px`,
    textAlign: 'left',
    color,
    cursor: 'move',
    userSelect: 'none',
    outline: selected ? '2px dashed #f59e0b' : '1px dashed rgba(128,128,128,.35)',
    outlineOffset: 2,
  };
  if (ov.chip) {
    style.background = dark ? 'rgba(255,255,255,.78)' : 'rgba(12,12,14,.58)';
    style.padding = '.45em .9em';
    style.borderRadius = '.45em';
  } else if (ov.shadow) {
    style.textShadow = dark
      ? '0 1px 3px rgba(255,255,255,.65), 0 0 14px rgba(255,255,255,.45)'
      : '0 1px 3px rgba(0,0,0,.6), 0 0 14px rgba(0,0,0,.45)';
  }
  return style;
}

/** 9방(position) 항목을 자유 x/y로 변환 — 렌더된 박스의 실측 위치 기준(합성기와 같은 CSS라 충실). */
function legacyStyle(ov: TextOverlay): React.CSSProperties {
  const vw = sizeVwOf(ov);
  const s: React.CSSProperties = {
    position: 'absolute', maxWidth: '70%', whiteSpace: 'pre-line', lineHeight: 1.35,
    fontWeight: ov.weight === 'normal' ? 400 : 600,
    fontFamily: FONTS[ov.font || 'sans'] || FONTS.sans,
    fontSize: `${(vw / 100) * CANVAS_W}px`, visibility: 'hidden',
  };
  if (ov.chip) s.padding = '.45em .9em';
  const pos = ov.position || 'bottom-right';
  const [h, v] = {
    'top-left': ['left', 'top'], top: ['center', 'top'], 'top-right': ['right', 'top'],
    left: ['left', 'middle'], center: ['center', 'middle'], right: ['right', 'middle'],
    'bottom-left': ['left', 'bottom'], bottom: ['center', 'bottom'], 'bottom-right': ['right', 'bottom'],
  }[pos] || ['right', 'bottom'];
  if (h === 'left') { s.left = '3.2%'; s.textAlign = 'left'; }
  else if (h === 'right') { s.right = '3.2%'; s.textAlign = 'right'; }
  else { s.left = '50%'; s.textAlign = 'center'; }
  if (v === 'top') s.top = '4.5%';
  else if (v === 'bottom') s.bottom = '4.5%';
  else s.top = '50%';
  const tx = h === 'center' ? '-50%' : '0';
  const ty = v === 'middle' ? '-50%' : '0';
  if (tx !== '0' || ty !== '0') s.transform = `translate(${tx},${ty})`;
  return s;
}

export function OverlayEditor(props: {
  lectureId: string;
  slideId: string;
  initial: TextOverlay[];
  onSaved: (count: number) => void;
  onClose: () => void;
}) {
  const { lectureId, slideId, initial, onSaved, onClose } = props;
  const [overlays, setOverlays] = useState<TextOverlay[]>([]);
  const [selected, setSelected] = useState<number>(-1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 배경 img 캐시버스터 — 열 때 1회 고정 (렌더마다 Date.now()면 부모 폴링 리렌더에 이미지 재요청)
  const [imgBust] = useState(() => Date.now());

  // 웹폰트 주입 — 합성기와 같은 Google Fonts (미리보기=결과 서체 일치). 1회, 제거 안 함.
  useEffect(() => {
    if (!document.getElementById('overlay-editor-fonts')) {
      const link = document.createElement('link');
      link.id = 'overlay-editor-fonts';
      link.rel = 'stylesheet';
      link.href = FONT_LINK;
      document.head.appendChild(link);
    }
  }, []);
  const canvasRef = useRef<HTMLDivElement>(null);
  const legacyRefs = useRef<(HTMLDivElement | null)[]>([]);
  const drag = useRef<{ idx: number; startX: number; startY: number; ox: number; oy: number } | null>(null);

  // 열 때: 9방 항목을 실측 좌표로 x/y 변환 (한 프레임 숨겨 그려 offset 측정)
  useEffect(() => {
    const legacy = initial.filter((o) => o.x === undefined || o.y === undefined);
    if (legacy.length === 0) {
      setOverlays(initial.map((o) => ({ ...o })));
      return;
    }
    // 다음 프레임에 legacyRefs 측정
    requestAnimationFrame(() => {
      const canvas = canvasRef.current;
      const converted = initial.map((o, i) => {
        if (o.x !== undefined && o.y !== undefined) return { ...o };
        const el = legacyRefs.current[i];
        if (!canvas || !el) return { ...o, x: 30, y: 40 };
        const cr = canvas.getBoundingClientRect();
        const er = el.getBoundingClientRect();
        const { position: _pos, ...rest } = o;
        return {
          ...rest,
          x: Math.round(((er.left - cr.left) / cr.width) * 1000) / 10,
          y: Math.round(((er.top - cr.top) / cr.height) * 1000) / 10,
        };
      });
      setOverlays(converted);
    });
  }, [initial]);

  const sel = selected >= 0 && selected < overlays.length ? overlays[selected] : null;
  const patchSel = (patch: Partial<TextOverlay>) => {
    if (selected < 0) return;
    setOverlays((list) => list.map((o, i) => (i === selected ? { ...o, ...patch } : o)));
  };

  // 드래그
  const onPointerDown = (e: React.PointerEvent, idx: number) => {
    e.preventDefault();
    setSelected(idx);
    const o = overlays[idx];
    drag.current = { idx, startX: e.clientX, startY: e.clientY, ox: o.x ?? 50, oy: o.y ?? 50 };
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const cr = canvas.getBoundingClientRect();
    const nx = d.ox + ((e.clientX - d.startX) / cr.width) * 100;
    const ny = d.oy + ((e.clientY - d.startY) / cr.height) * 100;
    setOverlays((list) => list.map((o, i) =>
      i === d.idx ? { ...o, x: Math.round(Math.min(105, Math.max(-5, nx)) * 10) / 10, y: Math.round(Math.min(105, Math.max(-5, ny)) * 10) / 10 } : o));
  };
  const onPointerUp = () => { drag.current = null; };

  // 방향키 미세 이동 (0.5%)
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (selected < 0) return;
    const step = e.shiftKey ? 2 : 0.5;
    const o = overlays[selected];
    if (e.key === 'ArrowLeft') patchSel({ x: Math.round(((o.x ?? 50) - step) * 10) / 10 });
    else if (e.key === 'ArrowRight') patchSel({ x: Math.round(((o.x ?? 50) + step) * 10) / 10 });
    else if (e.key === 'ArrowUp') patchSel({ y: Math.round(((o.y ?? 50) - step) * 10) / 10 });
    else if (e.key === 'ArrowDown') patchSel({ y: Math.round(((o.y ?? 50) + step) * 10) / 10 });
    else if (e.key === 'Escape') onClose();
    else return;
    e.preventDefault();
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.textOverlaySlide(lectureId, slideId, { overlays });
      onSaved(r.overlays);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
      return;
    }
    setBusy(false);
    onClose();
  };

  const converting = overlays.length === 0 && initial.length > 0
    && initial.some((o) => o.x === undefined || o.y === undefined);

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-2xl p-4 space-y-3 outline-none"
        style={{ width: CANVAS_W + 32 }}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
        tabIndex={0}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-stone-700">
            🎯 글자 배치 편집 — {slideId}
            <span className="ml-2 text-xs font-normal text-stone-400">
              드래그로 이동 · 방향키 미세 이동 · 그림 픽셀은 그대로
            </span>
          </h3>
          <button onClick={onClose} className="text-stone-400 hover:text-stone-700 text-lg leading-none">✕</button>
        </div>

        {/* 캔버스 */}
        <div
          ref={canvasRef}
          className="relative overflow-hidden rounded-lg border border-stone-200 bg-stone-100"
          style={{ width: CANVAS_W, height: CANVAS_H }}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onClick={() => setSelected(-1)}
        >
          <img
            src={api.slideBasePngUrl(lectureId, slideId) + `&t=${imgBust}`}
            alt="원본 슬라이드"
            className="absolute inset-0 w-full h-full"
            draggable={false}
          />
          {/* 9방 항목 실측용 숨김 렌더 (변환 전 한 프레임) */}
          {converting && initial.map((o, i) => (
            <div key={`legacy-${i}`} ref={(el) => { legacyRefs.current[i] = el; }} style={legacyStyle(o)}>
              {o.text}
            </div>
          ))}
          {overlays.map((o, i) => (
            <div
              key={i}
              style={boxStyle(o, i === selected)}
              onPointerDown={(e) => { e.stopPropagation(); onPointerDown(e, i); }}
              onClick={(e) => e.stopPropagation()}
            >
              {o.text}
            </div>
          ))}
        </div>

        {/* 선택 박스 도구 */}
        {sel ? (
          <div className="flex items-center gap-2 flex-wrap">
            <input
              value={sel.text}
              onChange={(e) => patchSel({ text: e.target.value })}
              className="flex-1 min-w-40 px-2 py-1 text-sm border border-stone-300 rounded"
              placeholder="문구"
            />
            <select
              value={sel.font && FONTS[sel.font] ? sel.font : 'sans'}
              onChange={(e) => patchSel({ font: e.target.value })}
              className="px-1.5 py-1 text-xs border border-stone-300 rounded bg-white"
              title="서체"
            >
              {FONT_LABELS.map(([value, label]) => (
                <option key={value} value={value} style={{ fontFamily: FONTS[value] }}>{label}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => patchSel({ weight: sel.weight === 'normal' ? undefined : 'normal' })}
              title="굵기 — 그림 속 다른 글자와 맞출 때 보통으로"
              className={`px-2 py-1 text-xs rounded border ${
                sel.weight === 'normal'
                  ? 'bg-white text-stone-700 border-stone-300'
                  : 'bg-stone-800 text-white border-stone-800'
              }`}
            >
              굵게
            </button>
            <button
              type="button"
              onClick={() => patchSel({ shadow: !sel.shadow })}
              title="글자 그림자 — 배경과 색이 비슷해 안 보일 때만"
              className={`px-2 py-1 text-xs rounded border ${
                sel.shadow ? 'bg-stone-800 text-white border-stone-800' : 'bg-white text-stone-700 border-stone-300'
              }`}
            >
              그림자
            </button>
            <label className="flex items-center gap-1 text-xs text-stone-500" title="글자 크기 (슬라이드 폭 %)">
              크기
              <input
                type="range" min={0.8} max={8} step={0.1}
                value={sizeVwOf(sel)}
                onChange={(e) => patchSel({ size_vw: Number(e.target.value), size: undefined })}
              />
            </label>
            <input
              type="color"
              value={sel.color === 'white' || !sel.color ? '#ffffff' : sel.color === 'black' ? '#111111' : sel.color}
              onChange={(e) => patchSel({ color: e.target.value })}
              className="w-7 h-7 p-0 border border-stone-300 rounded cursor-pointer"
              title="글자색"
            />
            <button
              type="button"
              onClick={() => patchSel({ chip: !sel.chip })}
              className={`px-2 py-1 text-xs rounded border ${
                sel.chip ? 'bg-stone-800 text-white border-stone-800' : 'bg-white text-stone-700 border-stone-300'
              }`}
            >
              배경칩
            </button>
            <button
              type="button"
              onClick={() => { setOverlays((l) => l.filter((_, i) => i !== selected)); setSelected(-1); }}
              className="px-2 py-1 text-xs rounded border border-red-200 text-red-600 hover:bg-red-50"
            >
              삭제
            </button>
          </div>
        ) : (
          <div className="text-xs text-stone-400">박스를 클릭해 선택 — 문구·서체·크기·색을 바꿀 수 있습니다.</div>
        )}

        {error && <div className="text-xs text-red-600">❌ {error}</div>}

        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => {
              setOverlays((l) => [...l, { text: '새 문구', x: 30, y: 42, size_vw: 2.9, color: 'white', chip: false }]);
              setSelected(overlays.length);
            }}
            className="px-3 py-1.5 text-xs rounded border border-stone-300 bg-white text-stone-700 hover:border-stone-500"
          >
            ＋ 글자 추가
          </button>
          <div className="flex gap-2">
            <button
              type="button" onClick={onClose} disabled={busy}
              className="px-3 py-1.5 text-xs rounded border border-stone-300 bg-white text-stone-600 disabled:opacity-50"
            >
              취소
            </button>
            <button
              type="button" onClick={save} disabled={busy}
              className="px-4 py-1.5 text-xs rounded bg-stone-800 text-white hover:bg-stone-700 disabled:opacity-50"
            >
              {busy ? '합성 중…' : '💾 저장 (재합성)'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
