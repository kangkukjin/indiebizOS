import { DocumentOCR } from './DocumentOCR';
import { useEffect, useRef, useState, type MutableRefObject } from 'react';
import { documentCommand, documentRequest, sessionArgs, type Detail, type Session } from '../lib/api-documents';

type OfficeInstance = { destroyEditor: () => void };
type OfficeAPI = { DocEditor: new (id: string, config: Record<string, unknown>) => OfficeInstance };
type Setup = { url: string; config: Record<string, unknown>; session: Session; plugin: { channel: string; origin: string } };
let scriptPromise: Promise<void> | undefined;
function loadScript(url: string) {
  if (!scriptPromise) scriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = `${url}/web-apps/apps/api/documents/api.js`;
    script.onload = () => resolve();
    script.onerror = () => { scriptPromise = undefined; script.remove(); reject(new Error('문서 편집 서버에 연결할 수 없습니다')); };
    document.head.appendChild(script);
  });
  return scriptPromise;
}

export function OfficeDocumentEditor({ detail, onChange, captureRef }: { detail: Detail; onChange: (detail: Detail) => void; captureRef: MutableRefObject<(() => Promise<Session>) | null> }) {
  const [message, setMessage] = useState('편집기를 여는 중…');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [outputFormat,setOutputFormat] = useState('pdf');
  const [pdfPages,setPdfPages] = useState('1');
  const [pdfAction,setPdfAction] = useState('rotate');
  const [filename, setFilename] = useState(`사본_${detail.document.title}`);
  const [versions, setVersions] = useState<{ id: string; created_at: number; label?: string }[]>([]);
  const [generation, setGeneration] = useState(0);
  const [selected, setSelected] = useState<{text:string;bookmark:string}|null>(null);
  const [instruction,setInstruction] = useState('문장의 뜻을 유지하며 자연스럽게 다듬어줘');
  const [replacement,setReplacement] = useState('');
  const [proposal,setProposal] = useState<{id:string}|null>(null);
  const [pluginReady,setPluginReady] = useState(false);
  const bridge = useRef<{channel:string;origin:string;source:Window|null}|null>(null);
  const calls = useRef(new Map<string,{resolve:(v:Record<string,unknown>)=>void;reject:(e:Error)=>void}>());
  const current = useRef(detail);
  const dirty = useRef(false);
  const instance = useRef<OfficeInstance | null>(null);
  const slot = useRef(`office-${crypto.randomUUID()}`);
  const ready = useRef(false);
  current.current = detail;
  useEffect(() => {
    let disposed = false;
    const start = async () => {
      const s = current.current.session; if (!s) return;
      const setup = await documentCommand<Setup>(detail.document.id, 'engine-config', sessionArgs(s));
      if (disposed) return;
      bridge.current = {...setup.plugin,source:null};
      current.current = { ...current.current, session: setup.session };
      onChange(current.current);
      await loadScript(setup.url);
      if (disposed) return;
      const api = (window as unknown as { DocsAPI: OfficeAPI }).DocsAPI;
      instance.current = new api.DocEditor(slot.current, { ...setup.config, events: {
        onDocumentReady: () => { ready.current = true; setMessage('편집 준비 완료'); },
        onDocumentStateChange: (event: { data: boolean }) => {
          dirty.current = event.data;
          setMessage(event.data ? '편집 중 · 변경 내용을 편집기에 전달 중' : '편집기 반영됨 · 원본 저장으로 파일을 확정하세요');
        },
        onError: (event: { data: { errorDescription: string } }) => setError(event.data.errorDescription),
        onRequestClose: () => setMessage('원본 저장을 완료한 뒤 다른 문서로 이동하세요'),
      } });
    };
    const receive = (event:MessageEvent) => {
      const value=event.data, b=bridge.current;
      if(!b || event.origin!==b.origin || !value || value.type!=='indiebiz-document' || value.channel!==b.channel) return;
      if(value.id==='ready') {b.source=event.source as Window;setPluginReady(true);return;}
      if(event.source!==b.source) return;
      const call=calls.current.get(value.id); if(!call) return; calls.current.delete(value.id);
      if(value.result?.error) call.reject(new Error(value.result.error)); else call.resolve(value.result);
    };
    window.addEventListener('message',receive);
    void start().catch(e => setError(String(e)));
    return () => { window.removeEventListener('message',receive); setPluginReady(false); bridge.current=null; disposed = true; ready.current = false; instance.current?.destroyEditor(); instance.current = null; };
  }, [detail.document.id, generation]);

  useEffect(() => {
    const before = (event: BeforeUnloadEvent) => {
      if (dirty.current || busy) { event.preventDefault(); event.returnValue = ''; }
    };
    window.addEventListener('beforeunload', before);
    return () => window.removeEventListener('beforeunload', before);
  }, [busy]);

  const run = async (action: () => Promise<void>) => {
    if (busy) return;
    setBusy(true); setError('');
    try { await action(); } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };
  const pluginCall = (op:string,args:Record<string,unknown>) => new Promise<Record<string,unknown>>((resolve,reject) => {
    const b=bridge.current; if(!b?.source) {reject(new Error('선택 편집 연결이 준비되지 않았습니다'));return;}
    const id=crypto.randomUUID(); calls.current.set(id,{resolve,reject});
    b.source.postMessage({type:'indiebiz-document-command',channel:b.channel,id,op,args},b.origin);
    setTimeout(()=>{if(calls.current.delete(id)) reject(new Error('선택 편집 응답이 지연됐습니다'));},15000);
  });
  const capture = async () => {
    if (!ready.current) throw new Error('편집기가 준비될 때까지 기다리세요');
    const until=Date.now()+15000;
    while(dirty.current && Date.now()<until) await new Promise(r=>setTimeout(r,150));
    if (dirty.current) throw new Error('편집기 안의 저장(Ctrl/Cmd+S)을 먼저 완료하세요. 아직 전송되지 않은 변경이 있습니다.');
    const d = await documentRequest<Detail>(`/${detail.document.id}`);
    if (!d.session || d.session.client_id !== current.current.session?.client_id || d.session.engine_epoch !== current.current.session?.engine_epoch)
      throw new Error('다른 창으로 편집 권한이 이동했습니다');
    const result = await documentCommand<{ session: Session }>(d.document.id, 'engine-capture', {
      ...sessionArgs(d.session), operation_id: crypto.randomUUID(),
    });
    current.current = { ...d, session: result.session }; onChange(current.current);
    return result.session;
  };
  useEffect(() => {
    captureRef.current = async () => {
      if (busy) throw new Error('진행 중인 문서 작업이 끝난 뒤 이동하세요');
      return capture();
    };
    return () => { captureRef.current = null; };
  });
  const save = () => run(async () => {
    const session = await capture(), d = current.current;
    await documentCommand(d.document.id, 'save', { ...sessionArgs(session),
      operation_id: crypto.randomUUID(), expected_revision: d.document.revision_id });
    const next = await documentRequest<Detail>(`/${d.document.id}`); current.current = next; onChange(next);
    setMessage('저장됨 · 원본 파일 기록 확인');
  });
  const copy = () => run(async () => {
    const session = await capture();
    const result = await documentCommand<{ path: string }>(detail.document.id, 'export', {
      ...sessionArgs(session), operation_id: crypto.randomUUID(), filename,
    });
    setMessage(`사본 저장됨: ${result.path}`);
  });
  return <div className="office-document">
    <div className="document-toolbar">
      <button disabled={busy} onClick={save}>원본 저장</button>
      <button disabled={busy} onClick={() => void run(async () => { await capture(); setMessage('복구 초안 저장됨'); })}>작업 저장</button>
      <button disabled={busy} onClick={() => void run(async () => {
        const result = await documentRequest<{ items: { id: string; created_at: number; label?: string }[] }>(`/${detail.document.id}/versions`); setVersions(result.items);
      })}>버전 이력</button>
      <button disabled={busy} onClick={() => setGeneration(v => v + 1)}>편집기 다시 연결</button>
      <label>사본 파일명<input value={filename} onChange={e => setFilename(e.target.value)} /></label>
      <button disabled={busy || !filename} onClick={copy}>사본 저장</button>
      <label>출력 형식<select value={outputFormat} onChange={e=>setOutputFormat(e.target.value)}>{['pdf','docx','odt','rtf','html','txt','epub'].map(f=><option key={f}>{f}</option>)}</select></label>
      <button disabled={busy} onClick={()=>void run(async()=>{const s=await capture();const d=current.current;const result=await documentCommand<Detail>(d.document.id,'convert',{...sessionArgs(s),expected_revision:d.document.revision_id,output_format:outputFormat});setMessage('변환 사본 저장됨: '+result.document.source_uri);})}>내보내기</button>
    </div>
    {error && <p role="alert">{error}</p>}
    {versions.length > 0 && <details open><summary>저장 버전</summary>{versions.map(v => <button key={v.id} disabled={busy} onClick={() => void run(async () => {
      const s = await capture();
      await documentCommand(detail.document.id, 'restore', { ...sessionArgs(s), operation_id: crypto.randomUUID(), revision_id: v.id });
      const next = await documentRequest<Detail>(`/${detail.document.id}`); current.current = next; onChange(next);
      setGeneration(g => g + 1); setVersions([]); setMessage('이전 버전을 초안으로 복구했습니다');
    })}>{new Date(v.created_at * 1000).toLocaleString()} · {v.label || '저장 버전'} · 초안 복구</button>)}</details>}
    {detail.document.source_format!=='pdf' && <details className="office-ai" open><summary>선택 수정 · AI</summary>
      <button disabled={busy||!pluginReady} onMouseDown={e=>e.preventDefault()} onClick={()=>void run(async()=>{
        const result=await pluginCall('select',{bookmark:'ib_'+crypto.randomUUID().replaceAll('-','').slice(0,24)});
        setSelected({text:String(result.text),bookmark:String(result.bookmark)});setReplacement(String(result.text));setProposal(null);
        setMessage('선택 위치를 고정했습니다');
      })}>문구 선택 고정</button>
      {selected && <><blockquote>{selected.text}</blockquote><label>사무 문서 AI 지시<input value={instruction} onChange={e=>setInstruction(e.target.value)}/></label>
      <p>고정한 선택과 지시가 설정된 AI 모델 제공자에게 전달됩니다.</p>
      <button disabled={busy} onClick={()=>void run(async()=>{
        const s=await capture();
        const result=await documentCommand<{id:string;replacement:string}>(detail.document.id,'office-proposal',{...sessionArgs(s),operation_id:crypto.randomUUID(),bookmark:selected.bookmark,selected:selected.text,instruction});
        setProposal(result);setReplacement(result.replacement);setMessage('AI 제안 도착 · 검토 후 적용하세요');
      })}>사무 문서 AI 제안</button>
      <label>사무 문서 교체 문구<textarea value={replacement} onChange={e=>{setReplacement(e.target.value);setProposal(null);}}/></label>
      <button disabled={busy} onClick={()=>void run(async()=>{
        const s=await capture();const result=await documentCommand<{id:string}>(detail.document.id,'office-proposal',{...sessionArgs(s),operation_id:crypto.randomUUID(),bookmark:selected.bookmark,selected:selected.text,instruction:'사용자가 직접 입력한 수정',replacement});setProposal(result);
      })}>사무 문서 제안 만들기</button>
      <button disabled={busy||!proposal} onClick={()=>void run(async()=>{
        const s=await capture();await documentCommand(detail.document.id,'office-approve',{...sessionArgs(s),proposal_id:proposal?.id});
        await pluginCall('apply',{bookmark:selected.bookmark,selected:selected.text,replacement,track:true});
        setProposal(null);setSelected(null);setMessage('변경 추적으로 적용했습니다 · 편집기 검토 메뉴에서 수락·거절하세요');
      })}>변경 추적으로 적용</button></>}
    </details>}
    {detail.document.source_format==='pdf' && <>
      <div className="document-toolbar"><label>작업할 PDF 쪽<input value={pdfPages} onChange={e=>setPdfPages(e.target.value)} placeholder="1,2,3"/></label>
      <label>PDF 쪽 작업<select value={pdfAction} onChange={e=>setPdfAction(e.target.value)}><option value="rotate">90도 회전</option><option value="delete">선택 쪽 삭제</option><option value="reorder">지정 순서로 전체 쪽 재정렬</option></select></label>
      <button disabled={busy} onClick={()=>void run(async()=>{
        const s=await capture();const pages=pdfPages.split(',').map(v=>Number(v.trim()));
        const next=await documentCommand<Detail>(detail.document.id,'pdf-pages',{...sessionArgs(s),pages,action:pdfAction});
        current.current=next;onChange(next);setGeneration(v=>v+1);setMessage('쪽 변경 초안 · 원본 저장으로 확정하세요');
      })}>PDF 쪽 변경</button></div>
      <DocumentOCR detail={detail}/>
    </>}
    <div className="office-frame"><div id={slot.current} /></div>
    <p role="status">{busy ? '저장 확인 중…' : message}</p>
  </div>;
}
