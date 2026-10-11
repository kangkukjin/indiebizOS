import { useState } from 'react';
import { createPortal } from 'react-dom';
import { X, TerminalSquare, FolderOpen, ListChecks } from 'lucide-react';
import { RemoteTerminal } from './RemoteTerminal';
import { RemoteFiles } from './RemoteFiles';
import { RemoteTasks } from './RemoteTasks';

export function RemotePCWorkbench({ device, alias, terminal, onClose }: { device: string; alias: string; terminal: boolean; onClose: () => void }) {
  const [tab, setTab] = useState<'terminal' | 'files' | 'tasks'>('terminal');
  const [visited, setVisited] = useState({ files: false, tasks: false });
  return createPortal(<div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4">
    <section role="dialog" aria-modal="true" aria-label="원격 PC 작업창" className="flex h-[90vh] w-[95vw] max-w-[1500px] min-w-0 flex-col overflow-hidden rounded-xl border border-stone-300 bg-white shadow-2xl">
      <header className="flex items-center gap-3 border-b px-4 py-3"><TerminalSquare size={20} /><strong className="min-w-0 flex-1 truncate">{alias} · 원격 작업창</strong><button aria-label="작업창 닫기" title="터미널을 종료하고 작업창을 닫습니다." onClick={onClose} className="rounded p-1 hover:bg-stone-100"><X size={20} /></button></header>
      <nav aria-label="작업창 탭" className="flex gap-1 border-b bg-stone-50 px-3">
        <button aria-pressed={tab === 'terminal'} onClick={() => setTab('terminal')} className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm ${tab === 'terminal' ? 'border-blue-600 text-blue-700' : 'border-transparent text-stone-600'}`}><TerminalSquare size={16} />터미널</button>
        <button aria-pressed={tab === 'files'} onClick={() => { setTab('files'); setVisited(v => ({ ...v, files: true })); }} className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm ${tab === 'files' ? 'border-blue-600 text-blue-700' : 'border-transparent text-stone-600'}`}><FolderOpen size={16} />파일</button>
        <button aria-pressed={tab === 'tasks'} onClick={() => { setTab('tasks'); setVisited(v => ({ ...v, tasks: true })); }} className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm ${tab === 'tasks' ? 'border-blue-600 text-blue-700' : 'border-transparent text-stone-600'}`}><ListChecks size={16} />작업·로그</button>
      </nav>
      <div className={`min-h-0 flex-1 ${tab === 'terminal' ? '' : 'hidden'}`}><RemoteTerminal device={device} supported={terminal} /></div>
      <div className={`min-h-0 flex-1 ${tab === 'files' ? '' : 'hidden'}`}>{visited.files && <RemoteFiles device={device} />}</div>
      <div className={`min-h-0 flex-1 ${tab === 'tasks' ? '' : 'hidden'}`}>{visited.tasks && <RemoteTasks device={device} />}</div>
    </section>
  </div>, document.body);
}
