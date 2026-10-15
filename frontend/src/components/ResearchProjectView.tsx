import { useCallback, useEffect, useRef, useState } from 'react';
import { Plus, History, X } from 'lucide-react';
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
  const history = useRef<HTMLDialogElement>(null);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    const groups = await Promise.all([false, true].map(async archived => {
      let cursor: string | null = null;
      const items: ResearchThread[] = [];
      do {
        const result = await researchCall(uid, 'thread_list', { limit: 100, archived, ...(cursor ? { cursor } : {}) });
        items.push(...result.items as ResearchThread[]); cursor = result.next_cursor as string | null;
      } while (cursor);
      return items;
    }));
    setThreads(groups.flat()); setError('');
  }, [uid]);
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
      setSelected(item.id); setCreating(false); setTitle(''); await load();
    } catch (e) { setError(String(e)); }
  };
  const sessionMenu = <div className="flex items-center gap-1 shrink-0 whitespace-nowrap">
      <button onClick={() => {history.current?.showModal(); void load();}} className="flex items-center gap-1 px-2 py-1.5 rounded-lg hover:bg-white/60 text-xs"><History size={14} className="hidden sm:block"/>히스토리</button>
      <button onClick={() => setCreating(true)} className="flex items-center gap-1 px-2 py-1.5 rounded-lg hover:bg-white/60 text-xs"><Plus size={14} className="hidden sm:block"/>새 세션</button>
    </div>;
  return <div className="h-full flex flex-col bg-[#F5F1EB] text-[#4A4035]">
    <div className="drag select-none shrink-0 h-12 flex items-center pl-20 pr-5 border-b border-[#E5DFD5] bg-[#EAE4DA] font-semibold">📚 {project.name}<span className="ml-3 text-xs text-[#6B5B4F]">연구 프로젝트</span></div>
    {error && <p role="alert" className="px-4 py-2 text-sm text-red-600">{error}</p>}
    {!selected && <div className="flex justify-end p-2">{sessionMenu}</div>}
    <dialog ref={history} aria-label="대화 히스토리" onClick={e => {if (e.target === e.currentTarget) history.current?.close();}} className="m-auto p-4 rounded-xl bg-[#F5F1EB] text-[#4A4035] w-[1040px] max-w-[94vw] h-[82vh] max-h-[90vh] open:flex open:flex-col backdrop:bg-black/30">
      <div className="flex justify-between items-center mb-3"><h2 className="font-semibold">대화 히스토리</h2><button onClick={() => history.current?.close()} aria-label="닫기"><X size={20}/></button></div>
      <div className="flex-1 min-h-0 overflow-auto">
        {threads.map(thread => <button key={thread.id} onClick={() => {setSelected(thread.id);history.current?.close();setCreating(false);}} aria-current={selected === thread.id} className="block w-full text-left px-3 py-3 rounded-xl hover:bg-white/60">
          <span className="block font-medium">{thread.title}</span><span className="block text-xs text-[#A09080] mt-1">{thread.updated_label}</span>
        </button>)}
        {!threads.length && <p className="p-3 text-sm text-[#A09080]">새 대화를 만들어 시작하세요.</p>}
      </div>
    </dialog>
    {creating && <form onSubmit={e => {e.preventDefault(); void create();}} className="p-4 border-b border-[#E5DFD5] flex flex-wrap gap-2">
      <input autoFocus aria-label="새 대화 이름" placeholder="연구 주제 이름" value={title} onChange={e => setTitle(e.target.value)} className="flex-1 min-w-0 px-3 py-2 rounded-lg border border-[#E5DFD5]"/>
      <button disabled={!title.trim()} className="px-3 py-2 rounded-lg bg-[#D97706] text-white disabled:opacity-50">만들기</button><button type="button" onClick={() => setCreating(false)}>취소</button>
    </form>}
    <div className="flex flex-1 min-h-0">
      {threads.filter(t => opened.includes(t.id)).map(thread => <ResearchConversation key={thread.id} project={uid} thread={thread} visible={selected === thread.id} onChange={refresh} sessionActions={sessionMenu} />)}
      {!threads.length && <div className="flex-1 flex items-center justify-center text-[#A09080]">대화를 선택하거나 새로 만드세요.</div>}
    </div>
  </div>;
}
