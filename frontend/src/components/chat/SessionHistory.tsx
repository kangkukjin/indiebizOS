import { useEffect, useRef, useState, type ReactNode } from 'react';
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
export function SessionHistory({ items, onSelect, onClose }: { items: SavedSession[]; onSelect: (item: SavedSession) => void; onClose: () => void }) {
  const [search, setSearch] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const node = dialog.current!;
    node.showModal();
    node.querySelector('input')?.focus();
    return () => node.close();
  }, []);
  const filtered = items.filter(item => `${item.title} ${historyDay(item.updated_at || item.created_at)}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  return <dialog ref={dialog} onCancel={onClose} onClick={event => { if (event.target === event.currentTarget) onClose(); }} aria-label="대화 히스토리" className="m-auto p-0 rounded-xl shadow-xl bg-[#F5F1EB] text-[#4A4035] w-[680px] max-w-[92vw] backdrop:bg-black/30">
    <div className="p-4 flex items-center justify-between border-b border-[#D8D0C5]"><h2 className="font-semibold">대화 히스토리</h2><button onClick={onClose} aria-label="닫기"><X size={20}/></button></div>
    <div className="px-4 pt-4"><p className="text-sm text-[#8B7355] mb-3">마지막 대화 날짜별로 표시됩니다. 제목을 누르면 해당 세션이 열립니다.</p>
      <input autoFocus type="search" value={search} onChange={event => setSearch(event.target.value)} aria-label="세션 검색" placeholder="제목 또는 날짜 검색 (YYYY-MM-DD)" className="w-full p-2 border border-[#D8D0C5] rounded-lg bg-white"/>
    </div>
    <div className="p-4 overflow-y-auto max-h-[60vh]">
      <DatedSessions items={filtered} render={item => <button type="button" onClick={() => onSelect(item)} className="w-full p-3 text-left rounded-lg hover:bg-white flex justify-between gap-3">
        <span className="min-w-0 break-words">{item.title}</span>{Boolean(item.archived) && <span className="text-xs shrink-0 text-[#8B7355]">보관됨</span>}
      </button>}/>
      {!filtered.length && <p className="text-center text-sm text-[#8B7355] py-8">표시할 세션이 없습니다.</p>}
    </div>
  </dialog>;
}
