import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChatSession } from '../chat/ChatSession';
import type { ChatMessage, ToolActivity } from '../chat/types';
import { imageUrl } from '../generic/manifest';
import { researchCall, uploadAttachment, type ConversationData, type ResearchMessage } from './api';

/** 연구 전용 코드는 기록·자료 연결만 맡는다. 채팅 조작은 공통 ChatView가 소유한다. */
export function useResearchSession(project: string, thread: string, visible: boolean, onChange: () => void): ChatSession {
  const [data, setData] = useState<ConversationData | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<{ signature: string; id: string } | null>(null);
  const running = useRef(false);
  const sequence = useRef(0);
  const load = useCallback(async () => {
    const ticket = ++sequence.current;
    const result = await researchCall(project, 'thread_messages', { thread_ref: thread, limit: 100 }) as unknown as ConversationData;
    if (ticket !== sequence.current) return;
    setData(prev => prev ? { ...result, next_cursor: prev.next_cursor,
      items: [...new Map([...prev.items, ...result.items].map(m => [m.id, m])).values()].sort((a, b) => (a.display_order ?? a.id) - (b.display_order ?? b.id)) } : result);
    if (running.current && !result.active_run) onChange();
    running.current = !!result.active_run;
  }, [project, thread, onChange]);
  useEffect(() => {
    if (!visible) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try { await load(); } catch (e) { if (alive) setError(String(e)); }
      if (alive) timer = setTimeout(tick, running.current ? 1000 : 5000);
    };
    void tick();
    return () => { alive = false; clearTimeout(timer); sequence.current++; };
  }, [load, visible]);
  const send: ChatSession['send'] = async (text, files, actionHint) => {
    if (!visible || busy) return false;
    setBusy(true); setError('');
    try {
      const attachments = await Promise.all(files.map(uploadAttachment));
      const message = actionHint ? `${text}\n\n[선택한 IBL 액션: ${actionHint}]` : text;
      const signature = JSON.stringify([message, attachments]);
      if (pending.current?.signature !== signature) pending.current = { signature, id: crypto.randomUUID() };
      await researchCall(project, 'thread_send', { thread_ref: thread, message, attachments, request_id: pending.current.id });
      pending.current = null;
      // 접수 후 조회 실패는 전송 실패가 아니다. 입력을 비워 중복 전송을 피한다.
      try { await load(); } catch (e) { setError(String(e)); }
      onChange(); return true;
    } catch (e) { setError(String(e)); return false; }
    finally { setBusy(false); }
  };
  const cancel = async () => {
    try { await researchCall(project, 'thread_cancel', { thread_ref: thread }); await load(); }
    catch (e) { setError(String(e)); }
  };
  const loadOlder = async () => {
    if (!data?.next_cursor) return;
    try {
      const result = await researchCall(project, 'thread_messages', { thread_ref: thread, cursor: data.next_cursor, limit: 100 }) as unknown as ConversationData;
      setData(prev => prev ? { ...prev, next_cursor: result.next_cursor,
        items: [...new Map([...result.items, ...prev.items].map(m => [m.id, m])).values()].sort((a, b) => (a.display_order ?? a.id) - (b.display_order ?? b.id)) } : prev);
    } catch (e) { setError(String(e)); }
  };
  const streaming = data?.items.find(m => m.role === 'assistant' && m.status === 'running');
  const messages: ChatMessage[] = (data?.items || []).filter(m => m !== streaming).flatMap(m => {
    const message = toMessage(m);
    return m.cognition ? [{ ...message, id: `cognition-${m.id}`, content: '', cognition: m.cognition }, message] : [message];
  });
  if (streaming?.cognition) messages.push({ id: `cognition-${streaming.id}`, role: 'assistant', content: '', timestamp: new Date(), cognition: streaming.cognition });
  const latest = data?.items.at(-1);
  const panel = latest?.role === 'assistant' && latest.status !== 'running' ? latest : undefined;
  return { messages, loading: busy || !!data?.active_run, canSteer: !!data?.active_run && !busy, streamingContent: streaming?.content,
    toolHistory: streaming?.tool_activities as ToolActivity[] | undefined, thinkingText: streaming?.thinking,
    todos: streaming?.todos || panel?.todos, questions: panel?.questions || [],
    planMode: panel?.plan_mode || { active: false, phase: null }, error, hasOlder: !!data?.next_cursor, loadOlder, send, cancel };
}

function toMessage(m: ResearchMessage): ChatMessage {
  return { id: String(m.id), role: m.role,
    content: m.content + (m.status_label && m.status !== 'running' ? `\n\n*(${m.status_label})*` : ''),
    timestamp: new Date(m.message_time), toolActivities: m.tool_activities,
    images: m.attachments.filter(a => a.mime.startsWith('image/')).map(a => imageUrl(a.path)),
    documentFiles: m.attachments.filter(a => !a.mime.startsWith('image/')).map(a => ({ fileName: a.name, filePath: a.path, fileType: a.mime })),
  };
}
