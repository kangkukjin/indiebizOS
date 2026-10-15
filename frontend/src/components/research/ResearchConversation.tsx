import { useState, type ReactNode } from 'react';
import { BookOpen, ArrowLeft, FileText } from 'lucide-react';
import { ChatView } from '../chat/ChatView';
import { GenericInstrument, type AppInstrument } from '../GenericInstrument';
import { researchCall, type ResearchThread } from './api';
import { ResearchQuestions } from './ResearchQuestions';
import { ResearchPerspective } from './ResearchPerspective';
import { useResearchSession } from './useResearchSession';

/** 일반 프로젝트의 대화창에 대화별 자료실만 더한다. */
export function ResearchConversation({ project, thread, visible, onChange, sessionActions }: {
  project: string; thread: ResearchThread; visible: boolean; onChange: () => void; sessionActions?: ReactNode;
}) {
  const session = useResearchSession(project, thread.id, visible, onChange);
  const [library, setLibrary] = useState<AppInstrument | null>(null);
  const [showLibrary, setShowLibrary] = useState(false);
  const [showQuestions, setShowQuestions] = useState(false);
  const [showPerspective, setShowPerspective] = useState(false);
  const [error, setError] = useState('');
  const openLibrary = async () => {
    try {
      const result = await researchCall(project, 'research_view', { thread_ref: thread.id });
      setLibrary(result.manifest as AppInstrument); setShowLibrary(true); setError('');
    } catch (e) { setError(String(e)); }
  };
  return <section className={`${visible ? 'flex' : 'hidden'} flex-col flex-1 min-h-0 min-w-0`}>
    {error && <p role="alert" className="px-4 py-2 text-sm text-red-600">{error}</p>}
    <div className={`${showLibrary || showPerspective || showQuestions ? 'hidden' : 'flex'} flex-col flex-1 min-h-0`}>
      <div className="flex flex-wrap justify-end border-b border-[#E5DFD5]"><button onClick={() => setShowQuestions(true)} className="px-3 py-2 rounded-lg hover:bg-[#DDD5C8] text-sm">연구 질문</button><button onClick={() => setShowPerspective(true)} className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-[#DDD5C8] text-sm"><FileText size={17} />사용자의 관점</button><button onClick={openLibrary} className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-[#DDD5C8] text-sm"><BookOpen size={17} />자료실</button></div>
      <ChatView chatTarget={{ type: 'session', id: `${project}:${thread.id}`, title: thread.title }}
        session={session} active={visible && !showLibrary && !showPerspective && !showQuestions}
        headerActions={sessionActions} />
    </div>
    {showQuestions && <ResearchQuestions project={project} thread={thread.id} onBack={() => setShowQuestions(false)} />}
    {showPerspective && <ResearchPerspective project={project} thread={thread.id} title={thread.title} onBack={() => setShowPerspective(false)} onChange={onChange} />}
    {showLibrary && library && <>
      <header className="h-14 shrink-0 px-4 flex items-center justify-between border-b border-[#E5DFD5] bg-[#EAE4DA]">
        <span className="font-medium truncate">{thread.title} · 자료실</span>
        <button onClick={() => { setShowLibrary(false); onChange(); }} className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-[#DDD5C8] text-sm"><ArrowLeft size={17} />대화로 돌아가기</button>
      </header>
      <div className="flex-1 min-h-0 overflow-auto"><GenericInstrument presentation="project" primaryModeCount={3} instrument={library} /></div>
    </>}
  </section>;
}
