import { useCallback, useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import type { Project } from '../types';
import { useRetryingLoad } from '../lib/use-retrying-load';
import { ResearchConversation } from './research/ResearchConversation';
import { researchCall, type ResearchThread } from './research/api';

/** 대화 입력·첨부·메시지 표시는 일반 프로젝트의 공통 채팅 컴포넌트를 사용한다. */
export function ResearchProjectView({ project }: { project: Project }) {
  const uid = project.project_uid || project.id;
  const key = `research-thread:${uid}`;
  const [threads, setThreads] = useState<ResearchThread[]>([]);
  const [selected, setSelected] = useState(() => localStorage.getItem(key) || '');
  const [opened, setOpened] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState('');
  const [error, setError] = useState('');
  const [archived, setArchived] = useState(false);
  const load = useCallback(async () => {
    let cursor: string | null = null;
    const all: ResearchThread[] = [];
    do {
      const result = await researchCall(uid, 'thread_list', { limit: 100, archived, ...(cursor ? { cursor } : {}) });
      all.push(...result.items as ResearchThread[]); cursor = result.next_cursor as string | null;
    } while (cursor);
    setThreads(all); setError('');
  }, [uid, archived]);
  useRetryingLoad(load);
  const refresh = useCallback(() => { void load().catch(e => setError(String(e))); }, [load]);
  useEffect(() => {
    if (threads.length) setSelected(prev => threads.some(t => t.id === prev) ? prev : threads[0].id);
  }, [threads]);
  useEffect(() => {
    if (selected) { localStorage.setItem(key, selected); setOpened(prev => prev.includes(selected) ? prev : [...prev, selected]); }
  }, [selected, key]);
  const create = async () => {
    if (!title.trim()) return;
    try {
      const result = await researchCall(uid, 'thread_create', { title: title.trim() });
      const item = (result.items as ResearchThread[])[0];
      setSelected(item.id); setCreating(false); setTitle(''); setArchived(false); if (!archived) await load();
    } catch (e) { setError(String(e)); }
  };
  return <div className="h-full flex flex-col bg-[#F5F1EB] text-[#4A4035]">
    <div className="drag select-none shrink-0 h-12 flex items-center pl-20 pr-5 border-b border-[#E5DFD5] bg-[#EAE4DA] font-semibold">📚 {project.name}<span className="ml-3 text-xs text-[#6B5B4F]">연구 프로젝트</span></div>
    {error && <p role="alert" className="px-4 py-2 text-sm text-red-600">{error}</p>}
    <div className="flex flex-1 min-h-0">
      <aside className="w-64 max-w-[32%] shrink-0 flex flex-col border-r border-[#E5DFD5] bg-[#F0EBE3]">
        <div className="flex-1 overflow-y-auto p-3">
          {threads.map(thread => <button key={thread.id} onClick={() => setSelected(thread.id)} className={`block w-full text-left px-3 py-3 rounded-xl mb-1 ${selected === thread.id ? 'bg-white border border-[#D97706]/40 shadow-sm' : 'hover:bg-white/60 border border-transparent'}`}>
            <span className="block font-medium truncate">{thread.title}</span><span className="block text-xs text-[#A09080] mt-1">{thread.updated_label}</span>
          </button>)}
          {!threads.length && <p className="p-3 text-sm text-[#A09080]">{archived ? '보관한 대화가 없습니다.' : '새 대화를 만들어 시작하세요.'}</p>}
        </div>
        <div className="p-3 border-t border-[#E5DFD5]">
          {creating ? <form onSubmit={e => { e.preventDefault(); void create(); }} className="mb-2">
            <input autoFocus aria-label="새 대화 이름" placeholder="예: 교육" value={title} onChange={e => setTitle(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[#E5DFD5] outline-none focus:border-[#D97706]" />
            <div className="flex gap-2 mt-2"><button disabled={!title.trim()} className="px-3 py-2 rounded-lg bg-[#D97706] text-white disabled:opacity-50">만들기</button><button type="button" onClick={() => setCreating(false)}>취소</button></div>
          </form> : <button onClick={() => setCreating(true)} className="flex items-center justify-center gap-2 w-full py-2 rounded-lg bg-[#D97706] hover:bg-[#B45309] text-white"><Plus size={17} />새 대화</button>}
          <button className="block mx-auto mt-3 text-xs text-[#8B7D6B]" onClick={() => setArchived(v => !v)}>{archived ? '대화 목록으로' : '보관한 대화'}</button>
        </div>
      </aside>
      {threads.filter(t => opened.includes(t.id)).map(thread => <ResearchConversation key={thread.id} project={uid} thread={thread} visible={selected === thread.id} onChange={refresh} />)}
      {!threads.length && <div className="flex-1 flex items-center justify-center text-[#A09080]">대화를 선택하거나 새로 만드세요.</div>}
    </div>
  </div>;
}
