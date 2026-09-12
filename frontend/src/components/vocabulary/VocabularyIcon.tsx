import { useRef, useState } from 'react';
import type { ReactNode, MouseEvent } from 'react';
import type { Placement } from './types';

/** 자율주행과 같은 타일·이름. 포인터 캡처로 폴더 창 밖으로도 끌어낼 수 있다. */
export function VocabularyIcon({ id, name, icon, placement, destination, fixed, large, protectedIcon, disabled,
  selected, onSelect, onOpen, onMenu, onMove }: {
  id: string; name: string; icon: ReactNode; placement: Placement; destination?: string;
  fixed?: boolean; large?: boolean; protectedIcon?: boolean; disabled?: boolean; selected: boolean;
  onSelect: () => void; onOpen: () => void; onMenu: (e: MouseEvent) => void;
  onMove: (parent: string, x: number, y: number) => void;
}) {
  const start = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const [drag, setDrag] = useState<{ x: number; y: number } | null>(null);
  const hover = useRef<HTMLElement | null>(null);
  const resetHover = () => { hover.current?.removeAttribute('data-vocab-hover'); hover.current = null; };
  return <button type="button" data-vocab-icon={id} data-vocab-destination={destination}
    aria-label={name} aria-pressed={selected} title={name}
    className="vocabulary-icon absolute w-28 flex flex-col items-center gap-1.5 p-2 rounded-xl select-none text-stone-700"
    style={{ left: drag?.x ?? placement.x, top: drag?.y ?? placement.y,
      position: drag ? 'fixed' : 'absolute', zIndex: drag ? 200 : undefined,
      pointerEvents: drag ? 'none' : undefined, touchAction: 'none', cursor: fixed ? 'pointer' : 'grab' }}
    onClick={onSelect} onDoubleClick={onOpen} onContextMenu={onMenu}
    onKeyDown={e => {
      if (e.key === 'Enter') onOpen();
      if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) {
        e.preventDefault(); const rect = e.currentTarget.getBoundingClientRect();
        onMenu({ preventDefault() {}, stopPropagation() {}, clientX: rect.left + 30, clientY: rect.top + 30 } as MouseEvent);
      }
    }}
    onPointerDown={e => {
      if (e.button !== 0 || disabled) return;
      onSelect();
      if (fixed) return;
      const rect = e.currentTarget.getBoundingClientRect();
      start.current = { x: e.clientX, y: e.clientY, left: rect.left, top: rect.top };
      e.currentTarget.setPointerCapture(e.pointerId);
    }}
    onPointerMove={e => {
      const origin = start.current;
      if (!origin || (Math.hypot(e.clientX - origin.x, e.clientY - origin.y) < 6 && !drag)) return;
      setDrag({ x: origin.left + e.clientX - origin.x, y: origin.top + e.clientY - origin.y });
      const target = document.elementFromPoint(e.clientX, e.clientY)?.closest<HTMLElement>('[data-vocab-destination]');
      resetHover();
      if (target && target.dataset.vocabIcon !== id) { hover.current = target; target.setAttribute('data-vocab-hover', 'true'); }
    }}
    onPointerCancel={() => { start.current = null; setDrag(null); resetHover(); }}
    onPointerUp={e => {
      const origin = start.current;
      if (origin && drag) {
        const target = document.elementFromPoint(e.clientX, e.clientY)?.closest<HTMLElement>('[data-vocab-destination]');
        if (target && target.dataset.vocabIcon !== id) {
          const parent = target.dataset.vocabDestination!;
          const rect = target.getBoundingClientRect();
          const canvas = target.hasAttribute('data-vocab-canvas');
          onMove(parent, canvas ? Math.max(0, e.clientX - rect.left - (origin.x - origin.left)) : -1,
            canvas ? Math.max(0, e.clientY - rect.top - (origin.y - origin.top)) : -1);
        }
      }
      start.current = null; resetHover(); setDrag(null);
    }}>
    <span className={`${large ? 'w-20 h-20' : 'w-14 h-14'} rounded-2xl flex items-center justify-center shadow-[0_1px_3px_rgba(0,0,0,0.08),0_4px_12px_rgba(0,0,0,0.06)] ${
      protectedIcon ? 'bg-gradient-to-br from-violet-400 to-violet-600 text-white' : destination
        ? 'bg-gradient-to-br from-amber-300 to-amber-500 text-white' : 'bg-gradient-to-br from-blue-400 to-blue-600 text-white'
    } ${selected ? 'ring-2 ring-amber-600 ring-offset-2 ring-offset-[#F5F1EB]' : ''}`}>{icon}</span>
    <span className={`text-[11px] leading-tight text-center line-clamp-2 max-w-full px-1 py-0.5 rounded font-medium break-words ${selected ? 'bg-amber-600 text-white' : ''}`}>{name}</span>
  </button>;
}
