import { useCallback, useRef, useState } from 'react';
import { sheetRequest, sheetCommand, type SheetDetail, type Document } from '../lib/api-spreadsheets';
import { useRetryingLoad } from '../lib/use-retrying-load';
import { SpreadsheetImport } from './spreadsheets/SpreadsheetImport';
import { SpreadsheetEditor } from './spreadsheets/SpreadsheetEditor';
import { SpreadsheetConversion } from './spreadsheets/SpreadsheetConversion';
import { BACKEND_ORIGIN } from '../lib/backend-origin';
import './spreadsheets/spreadsheet.css';

export function SpreadsheetWorkspace() {
  const [recent,setRecent]=useState<Document[]>([]), [tabs,setTabs]=useState<SheetDetail[]>([]);
  const [active,setActive]=useState(''), [path,setPath]=useState(''), [title,setTitle]=useState('새 통합문서');
  const [template,setTemplate]=useState('blank'), [error,setError]=useState(''), [busy,setBusy]=useState(false);
  const client=useRef(sessionStorage.getItem('sheet-client')||crypto.randomUUID());
  sessionStorage.setItem('sheet-client',client.current);
  const capture=useRef<null|(()=>Promise<void>)>(null);
  const load=useCallback(async()=>{const r=await sheetRequest<{items:Document[]}>('');setRecent(r.items);},[]);
  const {retrying}=useRetryingLoad(load,{onFocus:true});
  const update=(d:SheetDetail)=>setTabs(rows=>rows.map(r=>r.document.id===d.document.id?d:r));
  const run=async(action:()=>Promise<void>)=>{if(busy)return;setBusy(true);setError('');try{await action();}catch(e){setError(String(e));}finally{setBusy(false);}};
  const activate=async(d:SheetDetail)=>{
    if(active&&active!==d.document.id&&capture.current)await capture.current();
    const acquired=d.capabilities.edit_native?await sheetCommand<SheetDetail>(d.document.id,'sessions',{client_id:client.current}):d;
    setTabs(rows=>[...rows.filter(r=>r.document.id!==acquired.document.id),acquired]);setActive(acquired.document.id);await load();
  };
  const detail=tabs.find(d=>d.document.id===active);
  return <main className="spreadsheet-workspace">
    <header className="sheet-header"><strong>스프레드시트</strong><span>셀과 계산 · 내 파일</span>
      <button onClick={()=>window.open(window.location.href,'_blank','noopener')}>새 창</button>
      <details><summary>지원 현황</summary><p>XLSX 직접 편집·원본 저장을 제공합니다. 전체 출시 인수는 진행 중이며 다른 형식과 매크로·외부 연결 보존은 아직 검증 중입니다.</p></details>
    </header>
    <div className="sheet-open">
      <label>로컬 파일 경로<input value={path} onChange={e=>setPath(e.target.value)} placeholder="/…/장부.xlsx"/></label>
      <button disabled={busy||!path} onClick={()=>void run(async()=>activate(await sheetRequest<SheetDetail>('/open','POST',{path})))}>파일 열기</button>
      <label className="sheet-upload">파일 가져오기<input type="file" accept=".xlsx,.xltx,.xlsm,.ods,.ots,.fods,.xls,.csv,.tsv,.numbers,.cell,.nxl" disabled={busy} onChange={e=>{
        const file=e.target.files?.[0];if(!file)return;
        void run(async()=>{const response=await fetch(`${BACKEND_ORIGIN}/spreadsheets/import?filename=${encodeURIComponent(file.name)}`,{method:'POST',credentials:'include',body:file});const result=await response.json();if(!response.ok)throw new Error(result.detail);await activate(result);});
      }}/></label>
      <label>새 통합문서 제목<input value={title} onChange={e=>setTitle(e.target.value)}/></label>
      <label>템플릿<select aria-label="템플릿" value={template} onChange={e=>setTemplate(e.target.value)}>{Object.entries({blank:'빈 통합문서',quotation:'간단 견적',print_quotation:'인쇄용 견적서',invoice:'청구서',ledger:'수입지출',inventory:'재고·입출고',attendance:'근태',schedule:'일정',budget:'프로젝트 예산'}).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
      <button disabled={busy} onClick={()=>void run(async()=>activate(await sheetRequest<SheetDetail>('/new','POST',{args:{title,template}})))}>새로 만들기</button>
    </div>
    {error&&<p role="alert">{error}</p>}
    <nav className="sheet-tabs" aria-label="통합문서 탭">{tabs.map(d=><button key={d.document.id} aria-pressed={active===d.document.id} disabled={busy} onClick={()=>void run(async()=>activate(d))}>{d.document.title}{d.session?.state==='draft'?' •':''}</button>)}</nav>
    <div inert={busy} aria-busy={busy}>
    {detail&&<SpreadsheetConversion key={'conversion-'+detail.document.id} detail={detail} beforeConvert={async()=>{if(detail.capabilities.edit_native){if(!capture.current)throw new Error("편집기가 아직 준비되지 않았습니다");await capture.current();}}} onConverted={activate} onBusyChange={setBusy} disabled={busy}/>}
    {!detail?<section className="sheet-home"><h1>계산하고, 정리하고, 함께 검토하세요.</h1><p>파일을 열거나 템플릿으로 새 장부를 시작하세요.</p><h2>최근 통합문서</h2>{retrying&&<p role="status">연결을 기다리고 있습니다…</p>}{recent.map(d=><button key={d.id} onClick={()=>void run(async()=>activate(await sheetRequest<SheetDetail>(`/${d.id}`)))}>{d.title}<small>{d.source_uri}</small></button>)}</section>
      :!detail.capabilities.edit_native?<section className="sheet-home"><h2>{detail.document.title}</h2><p>{detail.capabilities.reason}</p><p>등록한 원본 파일은 변경하지 않았습니다.</p>{['csv','tsv'].includes(detail.document.source_format)&&<SpreadsheetImport detail={detail} onImported={activate}/>}</section>
      :<SpreadsheetEditor key={detail.document.id} detail={detail} onChange={update} captureRef={capture}/>}
    </div>
  </main>;
}
