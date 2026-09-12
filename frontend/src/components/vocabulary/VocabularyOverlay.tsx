import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { X } from 'lucide-react';

export function VocabularyOverlay({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const old = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    return () => old?.focus();
  }, []);
  return <div className="fixed inset-0 z-[250] bg-black/25 flex items-center justify-center p-4" onPointerDown={e => e.stopPropagation()} onContextMenu={e => e.stopPropagation()}>
    <div ref={panel} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1}
      className="w-full max-w-2xl max-h-[85vh] overflow-auto rounded-2xl bg-[#faf8f4] p-5 shadow-xl text-stone-700 outline-none" onKeyDown={e => {
        if (e.key === 'Escape') { e.stopPropagation(); onClose(); }
        if (e.key === 'Tab') {
          const nodes = panel.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input, select, textarea, a[href]');
          if (!nodes?.length) return;
          const first = nodes[0], last = nodes[nodes.length - 1];
          if (e.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && (document.activeElement === last || document.activeElement === panel.current)) { e.preventDefault(); first.focus(); }
        }
      }}>
      <div className="flex items-center justify-between gap-3 mb-4"><h2 className="font-semibold">{title}</h2><button onClick={onClose} aria-label="닫기" className="p-2 rounded hover:bg-stone-200"><X size={18} /></button></div>
      {children}
    </div>
  </div>;
}
