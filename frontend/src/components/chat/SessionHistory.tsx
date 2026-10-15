import { useEffect, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { ui, useLocale } from '../../i18n/ui';
import type { SavedSession } from './useConversationSession';

export function historyDay(value?: string | Date) {
  const date = value instanceof Date ? value : new Date(value || '');
  if (Number.isNaN(date.getTime())) return '';
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
export function HistoryDate({ day }: { day: string }) {
  useLocale();
  return day ? <time dateTime={day}>{ui.date(new Date(`${day}T12:00:00`), { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' })}</time> : <span>날짜 미상</span>;
}
export function DatedSessions({ items, render }: { items: SavedSession[]; render: (item: SavedSession) => ReactNode }) {
  const groups = new Map<string, SavedSession[]>();
  for (const item of items) {
    const day = historyDay(item.updated_at || item.created_at);
    groups.set(day, [...(groups.get(day) || []), item]);
  }
  return <>{[...groups].sort(([a], [b]) => b.localeCompare(a)).map(([day, rows]) => <section key={day} data-session-day={day} className="mb-4">
    <h3 className="px-2 py-2 text-xs font-medium text-[#8B7355]"><HistoryDate day={day} /></h3>
    {rows.map(item => <div key={item.id}>{render(item)}</div>)}
  </section>)}</>;
}
export function SessionHistory({ items, selected, onSelect, onClose }: { selected: string; items: SavedSession[]; onSelect: (item: SavedSession) => void; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const node = dialog.current!;
    node.showModal();
    return () => node.close();
  }, []);
  return <dialog ref={dialog} onCancel={onClose} onClick={event => { if (event.target === event.currentTarget) onClose(); }} aria-label="대화 히스토리" className="m-auto p-0 rounded-xl shadow-xl bg-[#F5F1EB] text-[#4A4035] w-[1040px] max-w-[94vw] h-[82vh] max-h-[90vh] backdrop:bg-black/30">
   <div className="flex flex-col h-full">
    <div className="p-5 flex shrink-0 items-center justify-between border-b border-[#D8D0C5]"><h2 className="text-lg font-semibold">대화 히스토리</h2><button onClick={onClose} aria-label="닫기"><X size={20}/></button></div>
    <div className="p-4 overflow-y-auto flex-1 min-h-0">
      <DatedSessions items={items} render={item => <button type="button" aria-current={item.id === selected} onClick={() => onSelect(item)} className="w-full p-4 text-left rounded-lg hover:bg-white aria-[current=true]:bg-white flex justify-between gap-3">
        <span className="min-w-0 break-words">{item.title}</span>{Boolean(item.running) && <span className="text-xs shrink-0 text-[#8B7355]">진행 중</span>}
      </button>}/>
      {!items.length && <p className="text-center text-sm text-[#8B7355] py-8">표시할 세션이 없습니다.</p>}
    </div>
   </div>
  </dialog>;
}
