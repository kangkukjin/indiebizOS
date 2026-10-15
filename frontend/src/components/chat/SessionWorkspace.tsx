import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Plus, Archive, Pencil, X } from 'lucide-react';
import { ChatPane, type ChatViewProps } from './ChatView';
import { sessionCall, sessionQuery, useConversationSession, type SavedSession, type SessionTarget } from './useConversationSession';
function SessionPane({ item,target,active,initialMessage,...props }: ChatViewProps & {item:SavedSession;target:SessionTarget}) {
 const session = useConversationSession(item.id,target,active !== false); const sent = useRef<string | undefined>(undefined);
 useEffect(() => {
  if (!active || !initialMessage || sent.current === initialMessage) return;
  const timer = setTimeout(() => { sent.current = initialMessage; void session.send(initialMessage,[],null).then(ok => {if (!ok) sent.current = undefined;}); },500);
  return () => clearTimeout(timer);
 },[active,initialMessage]);
 return <ChatPane {...props} layout="fullpage" active={active} session={{...session,title:item.title}} chatTarget={props.chatTarget} />;
}
export function SessionWorkspace(props:ChatViewProps) {
 const c = props.chatTarget;
 const target:SessionTarget = c.type === 'agent' ? {target:'agent',project_id:c.projectId,agent_id:String(c.agent.id)} : {target:c.type === 'appmaker' ? 'appmaker' : 'system_ai'};
 const query = sessionQuery(target), stableTarget = useMemo(() => target,[query]);
 const [items,setItems] = useState<SavedSession[]>([]), [selected,setSelected] = useState(''), [visited,setVisited] = useState<string[]>([]);
 const [error,setError] = useState(''), [busy,setBusy] = useState(false), [archived,setArchived] = useState(false);
 const initialRecipient = useRef<{message?:string;id:string}>({id:''});
 if (props.initialMessage !== initialRecipient.current.message) initialRecipient.current = {message:props.initialMessage,id:''};
 if (selected && !initialRecipient.current.id) initialRecipient.current.id = selected;
 const [sidebarHost,setSidebarHost] = useState<HTMLElement|null>(null);
 const select = (id:string) => { setSelected(id);setVisited(prev => prev.includes(id) ? prev : [...prev,id]);localStorage.setItem(`conversation-selection:${query}`,id); };
 useEffect(() => {setSidebarHost(c.type === 'agent' && props.layout !== 'dialog' ? document.getElementById('project-sessions') : null);},[query,props.layout]);
 useEffect(() => {
  let disposed = false;
  const refresh = async () => {
   try { const data = await sessionCall<{sessions:SavedSession[]}>('',stableTarget); if (disposed) return;
    setItems(data.sessions);setError('');setSelected(prev => {
     if (prev) return prev;
     const saved = localStorage.getItem(`conversation-selection:${query}`);
     const id = data.sessions.find(s => !s.archived && s.id === saved)?.id || data.sessions.find(s => !s.archived)?.id || '';
     if (id) setVisited(old => old.includes(id) ? old : [...old,id]);return id;
    });
   } catch(e) {if (!disposed) setError((e as Error).message);}
  };
  void refresh();const timer = setInterval(refresh,2500);return () => {disposed = true;clearInterval(timer);};
 },[query]);
 const create = async () => {if (busy) return;setBusy(true);
  try { const row = await sessionCall<SavedSession>('',target,'POST',{});setItems(prev => [row,...prev]);setArchived(false);select(row.id);setError(''); }
  catch(e) {setError((e as Error).message);} finally {setBusy(false);}
 };
 const change = async (item:SavedSession,body:object) => {
  try { const row = await sessionCall<SavedSession>(`/${item.id}`,target,'PATCH',body);setItems(prev => prev.map(s => s.id === row.id ? row : s));
   if (row.archived && row.id === selected) {setSelected('');setVisited(prev => prev.filter(id => id !== row.id));} if (!row.archived) select(row.id);setError('');
  } catch(e) {setError((e as Error).message);}
 };
 const sidebar = <aside className="flex flex-col min-h-0 h-full bg-[#EAE4DA] text-[#4A4035]" aria-label="대화 세션">
  <div className="p-3 border-b border-[#D8D0C5] flex items-center justify-between gap-2"><span className="font-semibold text-sm">{c.type === 'agent' ? `${c.agent.name}의 세션` : '대화 세션'}</span><Plus size={18}/></div>
  <button type="button" disabled={busy} onClick={create} className="mx-3 my-2 p-2 text-sm border border-[#C8BBAA] rounded-lg text-left">＋ 새 세션 시작</button>
  <div className="flex-1 overflow-auto p-2 space-y-1">{items.filter(s => Boolean(s.archived) === archived).map(s => <div key={s.id} className={`rounded-lg p-2 ${selected === s.id ? 'bg-white shadow-sm' : 'hover:bg-white/50'}`}>
   <button type="button" onClick={() => select(s.id)} className="text-left w-full" aria-current={selected === s.id}><div className="text-sm truncate">{s.title}</div><div className="text-xs text-[#8B7355] mt-1">{s.running ? '● 진행 중' : s.archived ? '보관됨' : '이어서 대화하기'}</div></button>
   <div className="flex justify-end gap-2 mt-1"><button type="button" title="세션 이름 변경" onClick={() => {const title = prompt('세션 이름',s.title);if (title?.trim()) void change(s,{title});}}><Pencil size={13}/></button>
    <button type="button" title={s.archived ? '세션 복원' : '세션 보관'} onClick={() => void change(s,{archived:!s.archived})}><Archive size={13}/></button></div>
  </div>)}</div>
  <button type="button" onClick={() => setArchived(v => !v)} className="p-3 border-t border-[#D8D0C5] text-xs text-left">{archived ? '현재 세션 보기' : '보관한 세션 보기'}</button>
 </aside>;
 if (props.layout === 'dialog' && props.show === false) return null;
 const content = <div className="flex flex-1 min-w-0 min-h-0 h-full overflow-hidden">
  {sidebarHost ? createPortal(sidebar,sidebarHost) : <div className="w-56 min-w-40 border-r border-[#D8D0C5] shrink-0">{sidebar}</div>}
  <div className="flex flex-col flex-1 min-w-0 min-h-0">{error && <p role="alert" className="p-3 text-sm text-red-600">{error}</p>}
   {Boolean(items.find(s => s.id === selected)?.archived) && <p className="p-2 text-sm">보관된 세션입니다. 복원 후 이어갈 수 있습니다.</p>}
   {visited.map(id => {const item = items.find(s => s.id === id);return item && <div key={id} className={id === selected ? 'flex flex-1 min-h-0' : 'hidden'}><SessionPane {...props} item={item} target={stableTarget} active={id === selected && props.show !== false} initialMessage={id === initialRecipient.current.id ? props.initialMessage : undefined}/></div>;})}
   {!selected && <div className="m-auto text-[#8B7355]">새 세션을 시작하거나 왼쪽에서 대화를 선택하세요.</div>}
  </div>
 </div>;
 return props.layout === 'dialog' ? <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center"><div className="w-[1000px] max-w-[95vw] h-[85vh] bg-[#F5F1EB] shadow-xl rounded-xl overflow-hidden flex flex-col"><div className="flex justify-end p-2"><button onClick={props.onClose} aria-label="닫기"><X size={20}/></button></div>{content}</div></div> : content;
}
