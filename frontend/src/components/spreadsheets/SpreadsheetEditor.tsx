import { BACKEND_ORIGIN } from '../../lib/backend-origin';
import { useEffect, useRef, useState, type MutableRefObject } from 'react';
import { sheetCommand, sheetRequest, sheetUpload, sessionArgs, type SheetDetail, type Session, type SheetSnapshot } from '../../lib/api-spreadsheets';

type Result=Record<string,unknown>;
type Setup={url:string;config:Result;session:Session;plugin:{channel:string;origin:string}};
type Engine={destroyEditor:()=>void};
let sdkPromise:Promise<void>|null=null;
function sdk(url:string){
  if(!sdkPromise)sdkPromise=new Promise<void>((resolve,reject)=>{const s=document.createElement('script');s.src=url+'/web-apps/apps/api/documents/api.js';s.onload=()=>resolve();s.onerror=()=>{sdkPromise=null;s.remove();reject(new Error('스프레드시트 편집 서버에 연결하지 못했습니다'));};document.head.appendChild(s);});
  return sdkPromise;
}
export function SpreadsheetEditor({detail,onChange,captureRef,onSaved}:{detail:SheetDetail;onChange:(d:SheetDetail)=>void;captureRef:MutableRefObject<null|(()=>Promise<void>)>;onSaved?:(d:SheetDetail)=>void}){
  const [message,setMessage]=useState('편집기를 여는 중…'),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [ready,setReady]=useState(false),[generation,setGeneration]=useState(0),[snapshot,setSnapshot]=useState<SheetSnapshot|null>(null);
  const [sheetId,setSheetId]=useState(detail.workbook.sheets?.[0]?.sheet_id||'1'),[range,setRange]=useState('A1:D10');
  const [preview,setPreview]=useState<Result|null>(null),[replacement,setReplacement]=useState('[["수정할 값"]]');
  const [kind,setKind]=useState('set_values'),[proposal,setProposal]=useState<{id:string}|null>(null);
  const [instruction,setInstruction]=useState('이 범위의 오탈자를 정리해줘');
  const [linkedReport,setLinkedReport]=useState(false);
  const [changes,setChanges]=useState<{operation_id:string;status:string;result?:{applied?:boolean;snapshot_id?:string}}[]>([]);
  const [imports,setImports]=useState<{id:string;rows_imported:number}[]>([]);
  const [importSource,setImportSource]=useState('');
  const [exportFormat,setExportFormat]=useState('csv'),[exportEncoding,setExportEncoding]=useState('utf-8-sig');
  const [exportNewline,setExportNewline]=useState('crlf'),[textMode,setTextMode]=useState('safe'),[allowStale,setAllowStale]=useState(false);
  const [filename,setFilename]=useState('사본_'+detail.document.title),[versions,setVersions]=useState<{id:string;created_at:number;label?:string}[]>([]);
  const slot=useRef('sheet-'+crypto.randomUUID()),current=useRef(detail),dirty=useRef(false),working=useRef(false);
  const engine=useRef<Engine|null>(null),bridge=useRef<{channel:string;origin:string;source:Window|null}|null>(null);
  const calls=useRef(new Map<string,{resolve:(v:Result)=>void;reject:(e:Error)=>void;timer:ReturnType<typeof setTimeout>}>());
  const completed=useRef(new Map<string,Result>());
  current.current=detail;
  function publish(d:SheetDetail){current.current=d;onChange(d);}
  const pluginCall=(op:string,args:Result={})=>new Promise<Result>((resolve,reject)=>{
    const b=bridge.current;if(!b?.source){reject(new Error('계산·AI 연결을 준비하고 있습니다'));return;}
    const id=crypto.randomUUID();const timer=setTimeout(()=>{calls.current.delete(id);reject(new Error('편집기 응답이 지연됐습니다'));},30000);
    calls.current.set(id,{resolve,reject,timer});b.source.postMessage({type:'indiebiz-sheet-command',channel:b.channel,id,op,args},b.origin);
  });
  const run=async(action:()=>Promise<void>)=>{if(working.current)return;working.current=true;setBusy(true);setError('');try{await action();}catch(e){setError(String(e));}finally{working.current=false;setBusy(false);}};
  const capture=async()=>{
    const deadline=Date.now()+15000;
    while(dirty.current&&Date.now()<deadline)await new Promise(r=>setTimeout(r,150));
    if(dirty.current)throw new Error('편집기 안의 저장을 먼저 완료하세요. 아직 전달되지 않은 입력이 있습니다');
    const d=await sheetRequest<SheetDetail>('/'+detail.document.id),old=current.current.session;
    if(!d.session||d.session.client_id!==old?.client_id||d.session.engine_epoch!==old.engine_epoch)throw new Error('작성 권한 또는 엔진 세대가 바뀌었습니다');
    const result=await sheetCommand<{session:Session}>(d.document.id,'engine-capture',{...sessionArgs(d.session),operation_id:crypto.randomUUID()});
    const next=await sheetRequest<SheetDetail>('/'+d.document.id);
    if(!next.session||next.session.engine_epoch!==result.session.engine_epoch||next.session.client_id!==old.client_id)throw new Error('저장 확인 중 작성 권한이 바뀌었습니다');
    publish(next);return next.session;
  };
  useEffect(()=>{
    let disposed=false;
    const receive=(event:MessageEvent)=>{
      const b=bridge.current,v=event.data;
      if(!b||event.origin!==b.origin||!v||v.type!=='indiebiz-sheet'||v.channel!==b.channel)return;
      if(v.id==='ready'){b.source=event.source as Window;setReady(true);return;}
      if(event.source!==b.source)return;
      const call=calls.current.get(v.id);if(!call)return;calls.current.delete(v.id);clearTimeout(call.timer);
      if(v.result?.error)call.reject(Object.assign(new Error(v.result.error),{editorResult:v.result}));else call.resolve(v.result);
    };
    window.addEventListener('message',receive);
    void(async()=>{
      if(!current.current.session)return;
      const setup=await sheetCommand<Setup>(detail.document.id,'engine-config',sessionArgs(current.current.session));
      if(disposed)return;bridge.current={...setup.plugin,source:null};publish({...current.current,session:setup.session});await sdk(setup.url);if(disposed)return;
      const api=(window as unknown as {DocsAPI:{DocEditor:new(id:string,c:Result)=>Engine}}).DocsAPI;
      engine.current=new api.DocEditor(slot.current,{...setup.config,events:{
        onDocumentReady:()=>setMessage('편집 준비 완료'),
        onDocumentStateChange:(e:{data:boolean})=>{dirty.current=e.data;if(e.data){setSnapshot(null);setPreview(null);}setMessage(e.data?'편집 중 · 계산 확인 필요':'편집기 반영됨 · 원본 저장 전');},
        onError:(e:{data:{errorDescription:string}})=>setError(e.data.errorDescription),
      }});
    })().catch(e=>setError(String(e)));
    return()=>{disposed=true;setReady(false);window.removeEventListener('message',receive);bridge.current=null;engine.current?.destroyEditor();for(const call of calls.current.values()){clearTimeout(call.timer);call.reject(new Error('편집 연결이 닫혔습니다'));}calls.current.clear();};
  },[detail.document.id,generation]);
  useEffect(()=>{captureRef.current=async()=>{if(working.current)throw new Error('진행 중인 작업을 기다리세요');await capture();};return()=>{captureRef.current=null;};});
  useEffect(()=>{const before=(e:BeforeUnloadEvent)=>{if(dirty.current||working.current||current.current.session?.state==='draft'){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',before);return()=>window.removeEventListener('beforeunload',before);},[]);
  useEffect(()=>{
    if(!ready)return;
    let stopped=false;
    const timer=setInterval(()=>{if(stopped||working.current||!current.current.session)return;void(async()=>{
      const s=current.current.session!;
      const queue=await sheetCommand<{id:string;command:Result}[]>(detail.document.id,'pending',sessionArgs(s));
      if(!queue.length||stopped||working.current)return;
      await run(async()=>{for(const op of queue){
        let result=completed.current.get(op.id);
        if(!result){try{
          if(op.command.kind==='snapshot'){result={snapshot:await takeSnapshot(),completed:true};}
          else if(op.command.kind==='save'){const captured=await capture();result=await sheetCommand<Result>(detail.document.id,'save',{...sessionArgs(captured),expected_revision:op.command.expected_revision,operation_id:String(op.command.operation_id)});publish(await sheetRequest<SheetDetail>('/'+detail.document.id));}
          else {
            const captured=await capture();
            await sheetCommand(detail.document.id,'preflight',{...sessionArgs(captured),operation_id:op.id});
            result=await pluginCall('apply',op.command);
            if(result.applied){
              try {const captured=await takeSnapshot();result.snapshot_id=captured.id;}
              catch(e){result.capture_warning=String(e);}
            }
          }
        }catch(e){result=(e as {editorResult?:Result}).editorResult||{error:String(e),applied:false};}completed.current.set(op.id,result);}
        result=await sheetCommand<Result>(detail.document.id,'receipt',{...sessionArgs(current.current.session!),operation_id:op.id,result});
        completed.current.set(op.id,result);
        if(result.applied){setMessage('변경 묶음 적용됨 · 원본 저장 전'+(result.capture_warning?' · '+String(result.capture_warning):''));setProposal(null);setSnapshot(null);}else if(result.error)throw new Error(String(result.error));
      }});
    })().catch(e=>{if(!stopped)setError(String(e));});},1500);
    return()=>{stopped=true;clearInterval(timer);};
  },[ready,detail.document.id]);
  const takeSnapshot=async()=>{
    const observed=await pluginCall('calculate');
    const s=await capture();
    const verified=await pluginCall('state');
    if(observed.engine_state!==verified.engine_state)throw new Error('계산·저장 중 편집이 바뀌었습니다. 다시 스냅샷을 만드세요');
    const snap=await sheetCommand<SheetSnapshot>(detail.document.id,'snapshot',{...sessionArgs(s),engine_state:observed.engine_state,calculation:observed.calculation});
    setSnapshot(snap);setMessage('계산 상태 '+snap.calc_status+' · 스냅샷 고정됨 · '+(snap.unsaved?'미저장 편집 포함':'원본과 같음'));return snap;
  };
  return <section className="sheet-editor">
    <div className="sheet-actions">
      <button disabled={busy} onClick={()=>void run(async()=>{const s=await capture();const d=current.current;await sheetCommand(d.document.id,'save',{...sessionArgs(s),operation_id:crypto.randomUUID(),expected_revision:d.document.revision_id});const saved=await sheetRequest<SheetDetail>('/'+d.document.id);publish(saved);onSaved?.(saved);setMessage('저장됨 · 원본 파일 기록 확인');})}>원본 저장</button>
      <button disabled={busy} onClick={()=>void run(async()=>{await capture();setMessage('복구 초안 저장됨');})}>작업 저장</button>
      <button disabled={busy||!ready} onClick={()=>void run(async()=>{await takeSnapshot();})}>계산·스냅샷</button>
      <button disabled={busy} onClick={()=>void run(async()=>setVersions((await sheetRequest<{items:{id:string;created_at:number;label?:string}[]}>('/'+detail.document.id+'/versions')).items))}>버전 이력</button>
      <label>사본 이름<input value={filename} onChange={e=>setFilename(e.target.value)}/></label><button disabled={busy} onClick={()=>void run(async()=>{const s=await capture();const r=await sheetCommand<{path:string}>(detail.document.id,'export',{...sessionArgs(s),operation_id:crypto.randomUUID(),filename});setMessage('사본 저장됨: '+r.path);})}>사본 저장</button>
      <span>인쇄·PDF·피벗·차트는 편집기 메뉴에서 사용할 수 있습니다.</span>
    </div>
    {error&&<p role="alert">{error}</p>}
    {versions.length>0&&<div className="sheet-versions">{versions.map(v=><button key={v.id} disabled={busy} onClick={()=>void run(async()=>{const s=await capture();await sheetCommand(detail.document.id,'restore',{...sessionArgs(s),revision_id:v.id,operation_id:crypto.randomUUID()});publish(await sheetRequest<SheetDetail>('/'+detail.document.id));setVersions([]);setGeneration(g=>g+1);})}>{new Date(v.created_at*1000).toLocaleString()} {v.label||'저장 버전'} 복구</button>)}</div>}
    <div className="sheet-content"><div className="sheet-engine"><div id={slot.current}/></div>
      <aside className="sheet-review"><h2>AI와 변경 검토</h2><label>대상 시트<select value={sheetId} onChange={e=>{setSheetId(e.target.value);setProposal(null);}}>{detail.workbook.sheets?.map(s=><option key={s.sheet_id} value={s.sheet_id}>{s.name}</option>)}</select></label>
      <label>범위<input value={range} onChange={e=>{setRange(e.target.value);setProposal(null);}}/></label>
      <button disabled={busy||!ready} onClick={()=>void run(async()=>{const s=await takeSnapshot();const r=await sheetRequest<Result>(`/${detail.document.id}/snapshots/${s.id}?sheet_id=${encodeURIComponent(sheetId)}&range=${encodeURIComponent(range)}`);setPreview(r);})}>최신 범위 읽기</button>
      <details><summary>범위 내보내기</summary>
        <label>출력 형식<select aria-label="출력 형식" value={exportFormat} onChange={e=>setExportFormat(e.target.value)}>{['csv','tsv','html','json'].map(f=><option key={f} value={f}>{f.toUpperCase()}</option>)}</select></label>
        {(exportFormat==='csv'||exportFormat==='tsv')&&<>
          <label>문자 인코딩<select aria-label="문자 인코딩" value={exportEncoding} onChange={e=>setExportEncoding(e.target.value)}>{['utf-8-sig','utf-8','utf-16','cp949','euc-kr'].map(v=><option key={v} value={v}>{v}</option>)}</select></label>
          <label>줄바꿈<select aria-label="줄바꿈" value={exportNewline} onChange={e=>setExportNewline(e.target.value)}><option value="crlf">CRLF</option><option value="lf">LF</option></select></label>
          <label>텍스트 처리<select aria-label="텍스트 처리" value={textMode} onChange={e=>setTextMode(e.target.value)}><option value="safe">수식 오인 방지</option><option value="raw">원문 유지</option></select></label>
          <p>CSV·TSV는 값만 저장하며 빈 셀과 빈 문자열을 구분하지 않습니다. 수식 오인 방지는 =·+·-·@ 등으로 시작하는 문자 앞에 작은따옴표를 붙입니다. 원문 유지는 외부 프로그램이 문자를 수식으로 해석할 수 있습니다. 식별자의 셀 타입까지 보존하려면 JSON이나 XLSX를 사용하세요.</p>
        </>}
        <label><input type="checkbox" checked={allowStale} onChange={e=>setAllowStale(e.target.checked)}/>계산 미확인 시 현재 캐시 내보내기</label>
        <button disabled={busy||!ready} onClick={()=>void run(async()=>{
          const s=await takeSnapshot();
          const response=await fetch(`${BACKEND_ORIGIN}/spreadsheets/${detail.document.id}/range-export`,{
            method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({args:{snapshot_id:s.id,sheet_id:sheetId,range,format:exportFormat,
              encoding:exportEncoding,newline:exportNewline,text_mode:textMode,allow_stale:allowStale}}),
          });
          if(!response.ok){const failure=await response.json();throw new Error(failure.detail||'범위 출력 실패');}
          const info=JSON.parse(response.headers.get('X-Sheet-Export')||'{}') as Result;
          const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');
          link.href=url;link.download=`범위.${exportFormat}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
          setMessage(`범위 출력됨 · ${String(info.cells??'')}셀 · 계산 ${s.calc_status} · 수식 오인 방지 ${String(info.escaped_text_cells??0)}셀 · 계산값 없음 ${String(info.missing_formula_cells??0)}셀 · 오류 ${String(info.error_cells??0)}셀`);
        })}>현재 범위 다운로드</button>
      </details>
      {preview&&<details open><summary>값·수식·계산 근거</summary><pre>{JSON.stringify(preview,null,2)}</pre></details>}
      <label><input type="checkbox" checked={linkedReport} onChange={e=>setLinkedReport(e.target.checked)}/>보고서에 원본 연결 유지</label>
      <button disabled={busy||!snapshot} onClick={()=>void run(async()=>{const report=await sheetCommand<{document:{title:string;source_uri?:string}}>(detail.document.id,'report',{snapshot_id:snapshot?.id,sheet_id:sheetId,range,operation_id:crypto.randomUUID(),linked:linkedReport});setMessage('문서에 표 보고서를 만들었습니다: '+report.document.title+' · 문서 앱의 "열기"에서 여세요'+(report.document.source_uri?': '+report.document.source_uri:''));})}>문서에 표 보고서 만들기</button>
      <details><summary>변경 취소와 가져오기 갱신</summary>
      <button disabled={busy} onClick={()=>void run(async()=>{setChanges(await sheetCommand(detail.document.id,'changes',{}));setImports(await sheetCommand(detail.document.id,'imports',{}));})}>변경·가져오기 이력</button>
      {changes.filter(c=>c.result?.applied&&c.result.snapshot_id).map(c=><button key={c.operation_id} disabled={busy||!ready} onClick={()=>void run(async()=>{const s=await takeSnapshot();const p=await sheetCommand<{id:string;values:unknown}>(detail.document.id,'undo-propose',{operation_id:c.operation_id,snapshot_id:s.id});setProposal(p);setReplacement(JSON.stringify(p.values));setMessage('영향 셀만 되돌리는 변경안입니다. 후속 편집을 비교했습니다');})}>변경 {c.operation_id.slice(0,8)} 취소안</button>)}
      <label>갱신 CSV/TSV 파일<input type="file" disabled={busy} accept=".csv,.tsv" onChange={e=>{const file=e.target.files?.[0];if(file)void run(async()=>{const d=await sheetUpload(file);setImportSource(d.document.id);setMessage('갱신 원본을 등록했습니다');});}}/></label>
      {imports.map(r=><button key={r.id} disabled={busy||!ready||!importSource} onClick={()=>void run(async()=>{const s=await takeSnapshot();const source=await sheetRequest<SheetDetail>('/'+importSource);const p=await sheetCommand<{id:string;values:unknown}>(detail.document.id,'import-refresh',{recipe_id:r.id,source_resource_id:importSource,expected_revision:source.document.revision_id,snapshot_id:s.id});setProposal(p);setReplacement(JSON.stringify(p.values));setMessage('기록된 열 타입으로 전체 행을 검사했습니다. 갱신안을 적용하세요');})}>{r.rows_imported}행 가져오기 갱신안</button>)}
      </details>
      <label>AI에게 요청<input value={instruction} onChange={e=>setInstruction(e.target.value)}/></label>
      <button disabled={busy||!snapshot} onClick={()=>void run(async()=>{const r=await sheetCommand<{id:string;values:unknown}>(detail.document.id,'ai',{snapshot_id:snapshot?.id,sheet_id:sheetId,range,instruction});setProposal(r);setReplacement(JSON.stringify(r.values));})}>AI 수정 제안</button>
      <details><summary>직접 변경안 작성</summary><label>입력 종류<select value={kind} onChange={e=>{setKind(e.target.value);setProposal(null);}}><option value="set_values">값</option><option value="set_formulas">수식</option></select></label><label>행·열 값 (JSON)<textarea value={replacement} onChange={e=>{setReplacement(e.target.value);setProposal(null);}}/></label><button disabled={busy||!snapshot} onClick={()=>void run(async()=>setProposal(await sheetCommand(detail.document.id,'propose',{snapshot_id:snapshot?.id,sheet_id:sheetId,range,kind,values:JSON.parse(replacement)})))}>변경안 만들기</button></details>
      {proposal&&<><pre>{replacement}</pre><button disabled={busy} onClick={()=>void run(async()=>{const s=current.current.session;if(!s)return;await sheetCommand(detail.document.id,'apply',{...sessionArgs(s),proposal_id:proposal.id,operation_id:crypto.randomUUID()});setMessage('변경안을 편집기로 전달했습니다');})}>변경안 적용</button></>}
      <p>선택한 범위와 지시는 설정된 AI 제공자에게 전달됩니다. 원본 확정은 원본 저장으로 수행합니다.</p>
      </aside></div><footer role="status">{message}</footer>
  </section>;
}
