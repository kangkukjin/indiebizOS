import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../lib/api';
import { BACKEND_ORIGIN } from '../../lib/backend-origin';
import type { ChatSession } from './ChatSession';
import type { ChatMessage, ToolActivity, TodoItem, QuestionItem, PlanModeState } from './types';
import { fileToBase64, isTextFile } from './chatUtils';
export interface SessionTarget { target: string; project_id?: string; agent_id?: string; before?: string }
export interface SavedSession { id: string; title: string; running?: boolean; created_at?: string; updated_at?: string }
interface Event { type: string; id?: string; name?: string; input?: Record<string, unknown>; result?: string;
 content?: string; message?: string; is_error?: boolean; todos?: TodoItem[]; questions?: QuestionItem[] }
interface Snapshot {
 messages: { id: string; role: string; content: string; timestamp: string; images: string[] }[];
 panels?: { todo?: {todos?: TodoItem[]}; question?: {status?:string;questions?:QuestionItem[]}; plan_mode?: PlanModeState };
 has_older: boolean; turn: { id: string; state: string; stream_content?: string } | null; events: Event[];
}
export const sessionQuery = (t: SessionTarget) => new URLSearchParams(Object.entries(t).filter(([,v]) => v !== undefined) as [string,string][]).toString();
export const sessionCall = <T,>(path: string, target: SessionTarget, method = 'GET', body?: object) => api.request<T>(
 `/chat-sessions${path}${method === 'GET' ? `?${sessionQuery(target)}` : ''}`,
 { method, ...(method !== 'GET' ? { body: JSON.stringify({ ...target, ...body }) } : {}) });
export function useConversationSession(id: string, target: SessionTarget, active: boolean): ChatSession {
 const [messages, setMessages] = useState<ChatMessage[]>([]), [snapshot, setSnapshot] = useState<Snapshot>();
 const [error, setError] = useState(''), [sending, setSending] = useState(false), [hasOlder, setHasOlder] = useState(false);
 const pending = useRef(false), mounted = useRef(true), loaded = useRef(false);
 const targetRef = useRef(target); targetRef.current = target;
 const query = sessionQuery(target);
 const load = useCallback(async (before?: string) => {
  const result = await sessionCall<Snapshot>(`/${id}`, { ...targetRef.current, ...(before ? { before } : {}) });
  if (!mounted.current) return;
  const rows: ChatMessage[] = result.messages.map(m => ({ ...m, role: m.role === 'user' ? 'user' : 'assistant',
   timestamp: new Date(m.timestamp.endsWith('Z') || /[+-]\d\d:\d\d$/.test(m.timestamp) ? m.timestamp : `${m.timestamp.replace(' ', 'T')}Z`),
   images: m.images.map(path => targetRef.current.target === 'agent'
    ? `${BACKEND_ORIGIN}/conversations/${encodeURIComponent(targetRef.current.project_id!)}/image?path=${encodeURIComponent(path)}`
    : `${BACKEND_ORIGIN}/system-ai/image?path=${encodeURIComponent(path)}`) }));
  setMessages(prev => { const map = new Map(prev.map(m => [m.id,m])); rows.forEach(m => map.set(m.id,m)); return [...map.values()].sort((a,b) => Number(a.id)-Number(b.id)); });
  if (before || !loaded.current) setHasOlder(result.has_older);
  loaded.current = true;
  if (!before) setSnapshot(result);
  setError('');
 }, [id, query]);
 const loadRef = useRef(load); loadRef.current = load;
 useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
 useEffect(() => {
  if (!active) return;
  let disposed = false; let timer: ReturnType<typeof setTimeout>;
  const poll = async () => { try { await loadRef.current(); } catch(e) { if (!disposed) setError((e as Error).message); }
   if (!disposed) timer = setTimeout(poll, 1200); };
  void poll(); return () => { disposed = true; clearTimeout(timer); };
 }, [id,query,active]);
 const tools: ToolActivity[] = []; let thinking = '', todos: TodoItem[] = [], questions: QuestionItem[] = [];
 for (const e of snapshot?.events || []) {
  if (e.type === 'tool_start') tools.push({ id:e.id, name:e.name || '도구', input:e.input, status:'running' });
  if (e.type === 'tool_result') { const tool = [...tools].reverse().find(t => e.id ? t.id === e.id : t.name === e.name && t.status === 'running');
   if (tool) Object.assign(tool, { result:e.result, isError:e.is_error, status:'done' }); if (e.todos) todos = e.todos; }
  if (e.type === 'thinking') thinking = e.content || '';
  if (e.questions) questions = e.questions;
 }
 if (snapshot?.panels?.todo?.todos) todos = snapshot.panels.todo.todos;
 if (snapshot?.panels?.question) questions = snapshot.panels.question.status === 'pending' ? snapshot.panels.question.questions || [] : [];
 const running = snapshot?.turn?.state === 'running';
 const failure = [...(snapshot?.events || [])].reverse().find(e => e.type === 'error');
 const lastAssistant = messages.map(m => m.role).lastIndexOf('assistant');
 return { messages:messages.map((m,i) => i === lastAssistant && snapshot?.turn?.state === 'completed' && tools.length ? {...m,toolActivities:tools} : m),
  loading:sending || running, canSteer:false, streamingContent:running ? snapshot?.turn?.stream_content : '',
  toolHistory:running ? tools : [], thinkingText:running ? thinking : '', todos, questions, planMode:snapshot?.panels?.plan_mode,
  error:error || failure?.message || failure?.content || (snapshot?.turn?.state === 'interrupted' ? '앱 재시작으로 실행이 중단됐습니다. 기록을 확인하고 이어서 요청하세요.' : undefined),
  hasOlder, loadOlder:async () => {
   try { if (messages[0]) await load(messages[0].id); }
   catch(e) { setError((e as Error).message); }
  },
  send:async (text,files,actionHint) => {
   if (pending.current || running) return false;
   pending.current = true; setSending(true); setError('');
   try { const images = [], documents = []; let message = text;
    for (const file of files) {
     if (file.type.startsWith('image/')) images.push({ base64:await fileToBase64(file), media_type:file.type });
     else if (isTextFile(file)) message += `\n\n--- ${file.name} ---\n${await file.text()}`;
     else { const path = window.electron?.getPathForFile?.(file); if (!path) throw Error('이 문서는 데스크톱에서 첨부하거나 텍스트로 변환해주세요.'); documents.push({filePath:path,fileName:file.name}); }
    }
    await sessionCall(`/${id}/messages`,targetRef.current,'POST',{message:message || '첨부 자료를 확인해주세요.',images,documents,action_hint:actionHint});
    await load().catch(e => setError((e as Error).message)); return true;
   } catch(e) { setError((e as Error).message); return false; } finally { pending.current = false; setSending(false); }
  },
  respondToPanel:async (action,message) => {
   if (pending.current || running) return false;
   pending.current = true;setSending(true);
   try {await sessionCall(`/${id}/messages`,targetRef.current,'POST',{message,panel_action:action});await load().catch(e => setError((e as Error).message));return true;}
   catch(e) {setError((e as Error).message);return false;} finally {pending.current=false;setSending(false);}
  },
  cancel:async () => { try { await sessionCall(`/${id}/cancel`,targetRef.current,'POST'); await load(); } catch(e) { setError((e as Error).message); } }
 };
}
