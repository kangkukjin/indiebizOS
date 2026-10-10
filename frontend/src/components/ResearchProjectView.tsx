import { useCallback, useState } from 'react';
import type { Project } from '../types';
import { GenericInstrument, type AppInstrument } from './GenericInstrument';
import { runIBL } from './generic/manifest';
import { useRetryingLoad } from '../lib/use-retrying-load';

/** 연구 화면의 내용은 서버 매니페스트가 소유한다. 프로젝트 창은 동일 렌더러를 담는다. */
export function ResearchProjectView({ project }: { project: Project }) {
  const [instrument, setInstrument] = useState<AppInstrument | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try {
      const d = await runIBL({code: '[self:project]{op: "research_view", project_ref: $project}', edition: 2,
        inputs: {project: project.project_uid || project.id}, declared_inputs: ['project']});
      if (!d.manifest) throw new Error(String(d.error || '연구 화면을 불러오지 못했습니다'));
      setInstrument(d.manifest as AppInstrument); setError('');
    } catch(e) { setError(String(e)); throw e; }
  }, [project.id, project.project_uid]);
  useRetryingLoad(load);
  return <div className="h-full flex flex-col bg-stone-50">
    <div className="px-5 py-3 border-b bg-white font-semibold">📚 {project.name}<span className="ml-3 text-xs text-stone-500">연구 프로젝트</span></div>
    <div className="flex-1 min-h-0 overflow-auto">{error ? <p role="alert" className="p-5 text-red-600">{error}</p> : instrument ?
      <GenericInstrument key={project.project_uid || project.id} instrument={instrument} /> : <p className="p-5">자료실을 여는 중…</p>}</div>
  </div>;
}
