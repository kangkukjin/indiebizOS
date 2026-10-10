import { useCallback, useEffect, useRef, useState } from 'react';
import { BookOpen, ArrowLeft } from 'lucide-react';
import { ChatInputArea } from '../chat/ChatInputArea';
import { MessageBubble } from '../chat/MessageBubble';
import { useFileAttachments } from '../chat/useFileAttachments';
import { CameraPreview } from '../CameraPreview';
import { GenericInstrument, type AppInstrument } from '../GenericInstrument';
import { imageUrl } from '../generic/manifest';
import { researchCall, uploadAttachment, type ResearchThread, type ConversationData, type ResearchMessage } from './api';

export function ResearchConversation({ project, thread, visible, onChange }: {
  project: string; thread: ResearchThread; visible: boolean; onChange: () => void;
}) {
  const files = useFileAttachments();
  const [input, setInput] = useState('');
  const [data, setData] = useState<ConversationData | null>(null);
  const [older, setOlder] = useState<ResearchMessage[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [library, setLibrary] = useState<AppInstrument | null>(null);
  const [showLibrary, setShowLibrary] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const pending = useRef<{ signature: string; id: string } | null>(null);
  const sending = useRef(false);
  const running = useRef(false);
  const loadSequence = useRef(0);
  const load = useCallback(async () => {
    const sequence = ++loadSequence.current;
    const result = await researchCall(project, 'thread_messages', { thread_ref: thread.id, limit: 100 }) as unknown as ConversationData;
    if (sequence !== loadSequence.current) return result;
    setData(prev => prev ? { ...result, next_cursor: prev.next_cursor,
      items: [...new Map([...prev.items, ...result.items].map(m => [m.id, m])).values()].sort((a, b) => a.id - b.id) } : result);
    if (running.current && !result.active_run) onChange();
    running.current = !!result.active_run;
    return result;
  }, [project, thread.id, onChange]);
  useEffect(() => {
    if (!visible) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try { await load(); if (alive) setError(''); }
      catch (e) { if (alive) setError(String(e)); }
      if (alive) timer = setTimeout(tick, running.current ? 1500 : 5000);
    };
    void tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [load, visible]);
  useEffect(() => {
    if (visible && !showLibrary && follow.current && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [data, visible, showLibrary]);
  const send = async () => {
    if (sending.current || data?.active_run || (!input.trim() && !files.hasAttachments)) return;
    sending.current = true; setBusy(true); setError('');
    try {
      const attachments = [];
      for (const item of [...files.attachedImages, ...files.attachedTextFiles, ...files.attachedDocuments]) {
        attachments.push(await uploadAttachment(item.file));
      }
      const signature = JSON.stringify([input, attachments]);
      if (pending.current?.signature !== signature) pending.current = { signature, id: crypto.randomUUID() };
      await researchCall(project, 'thread_send', { thread_ref: thread.id, message: input.trim(), attachments, request_id: pending.current.id });
      pending.current = null; setInput(''); files.clearAttachments(); follow.current = true;
      await load(); onChange();
    } catch (e) { setError(String(e)); }
    finally { sending.current = false; setBusy(false); }
  };
  const cancel = async () => {
    try { await researchCall(project, 'thread_cancel', { thread_ref: thread.id }); await load(); }
    catch (e) { setError(String(e)); }
  };
  const openLibrary = async () => {
    try {
      const result = await researchCall(project, 'research_view', { thread_ref: thread.id });
      setLibrary(result.manifest as AppInstrument); setShowLibrary(true);
    } catch (e) { setError(String(e)); }
  };
  const previous = async () => {
    try {
      const before = cursor || data?.next_cursor;
      if (!before) return;
      const result = await researchCall(project, 'thread_messages', { thread_ref: thread.id, cursor: before, limit: 100 }) as unknown as ConversationData;
      const height = scroll.current?.scrollHeight || 0;
      setOlder(prev => [...result.items, ...prev]); setCursor(result.next_cursor || ''); follow.current = false;
      requestAnimationFrame(() => { if (scroll.current) scroll.current.scrollTop += scroll.current.scrollHeight - height; });
    } catch (e) { setError(String(e)); }
  };
  const messages = [...older, ...(data?.items || [])].filter((m, i, all) => all.findIndex(x => x.id === m.id) === i);
  return <section className={`${visible ? 'flex' : 'hidden'} flex-col flex-1 min-h-0 min-w-0`}>
    <header className="shrink-0 h-14 px-5 flex items-center justify-between border-b border-[#E5DFD5]">
      <h2 className="font-semibold truncate">{data?.title || thread.title}</h2>
      <button className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-[#EAE4DA] text-sm" onClick={showLibrary ? () => { setShowLibrary(false); onChange(); void load(); } : openLibrary}>
        {showLibrary ? <ArrowLeft size={17} /> : <BookOpen size={17} />}{showLibrary ? '대화로 돌아가기' : '자료실'}
      </button>
    </header>
    {error && <p role="alert" className="px-5 py-2 text-sm text-red-600">{error}</p>}
    {showLibrary && library && <div className="flex-1 min-h-0 overflow-auto"><GenericInstrument presentation="project" primaryModeCount={3} instrument={library} /></div>}
    <div className={`${showLibrary ? 'hidden' : 'flex'} flex-col flex-1 min-h-0`} onDragOver={files.handleDragOver} onDragLeave={files.handleDragLeave} onDrop={e => { e.stopPropagation(); if (!busy && !data?.active_run) void files.handleDrop(e); else e.preventDefault(); }}>
      <div ref={scroll} className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4" onScroll={() => {
        const el = scroll.current; if (el) follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      }}>
        {(cursor === null ? data?.next_cursor : cursor) && <button className="block mx-auto mb-5 text-sm text-[#9A6A30]" onClick={previous}>이전 대화 읽기</button>}
        {!messages.length && <p className="text-center text-sm text-[#A09080] mt-12">질문하거나 자료를 첨부해 대화를 시작하세요.</p>}
        {messages.map(message => <MessageBubble key={message.id} message={{
          id: String(message.id), role: message.role, content: message.content,
          timestamp: new Date(message.message_time),
          images: message.attachments.filter(a => a.mime.startsWith('image/')).map(a => imageUrl(a.path)),
        }}>
          {message.attachments.map(a => <button key={a.version_ref} className="block mt-2 text-xs underline" onClick={openLibrary}>📎 {a.name}</button>)}
          {message.status_label && <p className="mt-2 text-xs opacity-60">{message.status_label}</p>}
        </MessageBubble>)}
      </div>
      <ChatInputArea input={input} onInputChange={setInput} onSend={() => void send()} onCancel={() => void cancel()}
        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); } }}
        isLoading={busy || !!data?.active_run} hasContent={!!input.trim() || files.hasAttachments}
        attachedImages={files.attachedImages} attachedTextFiles={files.attachedTextFiles} attachedDocuments={files.attachedDocuments}
        isDragging={files.isDragging} onDragOver={files.handleDragOver} onDragLeave={files.handleDragLeave}
        onDrop={e => { e.stopPropagation(); if (!busy && !data?.active_run) void files.handleDrop(e); else e.preventDefault(); }}
        onPaste={files.handlePaste} onFileSelect={files.handleFileSelect} onRemoveImage={files.removeImage}
        onRemoveTextFile={files.removeTextFile} onRemoveDocument={files.removeDocument}
        onCameraClick={() => files.setIsCameraOpen(true)} fileInputRef={files.fileInputRef} inputRef={inputRef} />
      <CameraPreview isOpen={visible && files.isCameraOpen} onClose={() => files.setIsCameraOpen(false)} onCapture={files.handleCameraCapture} />
    </div>
  </section>;
}
