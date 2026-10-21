import { useState } from 'react';
import { Pencil } from 'lucide-react';
import type { ResearchThread } from './api';

export function ResearchThreadRow({ thread, selected, onSelect, onRename }: {
  thread: ResearchThread;
  selected: boolean;
  onSelect: () => void;
  onRename: (title: string, revision?: number) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState('');
  const [revision, setRevision] = useState<number>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const save = async () => {
    if (saving || !title.trim()) return;
    setSaving(true); setError('');
    try {
      await onRename(title.trim(), revision);
      setEditing(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };
  return <div className="rounded-xl hover:bg-white/60">
    {editing ? <form onSubmit={e => { e.preventDefault(); void save(); }} className="p-3">
      <div className="flex flex-wrap items-center gap-2">
        <input autoFocus aria-label="연구 주제 이름" value={title} disabled={saving}
          onFocus={e => e.currentTarget.select()} onChange={e => setTitle(e.target.value)}
          onKeyDown={e => {
            if (e.nativeEvent.isComposing || e.keyCode === 229) {
              if (e.key === 'Enter') e.preventDefault();
              return;
            }
            if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); if (!saving) setEditing(false); }
          }}
          className="flex-1 min-w-0 px-3 py-2 rounded-lg border border-[#E5DFD5]" />
        <button disabled={saving || !title.trim()} className="px-3 py-2 rounded-lg bg-[#D97706] text-white text-sm disabled:opacity-50">{saving ? '저장 중…' : '저장'}</button>
        <button type="button" disabled={saving} onClick={() => setEditing(false)} className="px-2 py-2 text-sm disabled:opacity-50">취소</button>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-red-600">{error}</p>}
    </form> : <div className="flex items-center gap-2">
      <button type="button" onClick={onSelect} aria-current={selected} className="flex-1 min-w-0 text-left px-3 py-3 rounded-xl">
        <span className="block font-medium break-words">{thread.title}</span>
        <span className="block text-xs text-[#A09080] mt-1">{thread.updated_label}</span>
      </button>
      <button type="button" onClick={() => { setTitle(thread.title); setRevision(thread.revision); setError(''); setEditing(true); }}
        aria-label={`${thread.title} 이름 변경`} className="shrink-0 flex items-center gap-1 mr-3 px-2 py-1.5 rounded-lg hover:bg-white text-xs">
        <Pencil size={14} />이름 변경
      </button>
    </div>}
  </div>;
}
