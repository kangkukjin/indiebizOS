import { useState } from 'react';
import { sheetCommand,type SheetDetail } from '../../lib/api-spreadsheets';
type Preview={rows:string[][];total_rows:number;shown_rows:number;types:string[];error_count:number;errors:{row:number;column?:number;error:string}[];duplicate_headers:boolean};
export function SpreadsheetImport({detail,onImported}:{detail:SheetDetail;onImported:(d:SheetDetail)=>Promise<void>}){
  const [encoding,setEncoding]=useState('utf-8-sig'),[delimiter,setDelimiter]=useState(detail.document.source_format==='tsv'?'\t':','),[header,setHeader]=useState(true);
  const [types,setTypes]=useState<string[]>([]),[preview,setPreview]=useState<Preview|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const args=()=>({expected_revision:detail.document.revision_id,encoding,delimiter,header,types:types.length?types:undefined});
  const run=async(action:()=>Promise<void>)=>{setBusy(true);setError('');try{await action();}catch(e){setError(String(e));}finally{setBusy(false);}};
  const invalidate=()=>setPreview(null);
  return <section className="sheet-import"><h2>구분자 파일 가져오기</h2><p>기본은 모든 열을 텍스트로 보존합니다. 필요한 열만 숫자·날짜로 지정하세요.</p>
    <div className="sheet-actions"><label>인코딩<select value={encoding} onChange={e=>{setEncoding(e.target.value);invalidate();}}>{['utf-8-sig','utf-8','utf-16','cp949','euc-kr'].map(v=><option key={v}>{v}</option>)}</select></label>
    <label>구분자<select value={delimiter} onChange={e=>{setDelimiter(e.target.value);setTypes([]);invalidate();}}><option value=",">쉼표</option><option value={'\t'}>탭</option><option value=";">세미콜론</option><option value="|">세로줄</option></select></label>
    <label><input type="checkbox" checked={header} onChange={e=>{setHeader(e.target.checked);invalidate();}}/>첫 행은 제목</label>
    <button disabled={busy} onClick={()=>void run(async()=>{const r=await sheetCommand<Preview>(detail.document.id,'csv-preview',args());setPreview(r);setTypes(r.types);})}>가져오기 미리보기</button></div>
    {types.length>0&&<div className="sheet-actions">{types.map((t,i)=><label key={i}>{i+1}열 {preview?.rows[0]?.[i]}<select value={t} onChange={e=>{setTypes(v=>v.map((x,j)=>j===i?e.target.value:x));invalidate();}}>{Object.entries({text:'텍스트',number:'숫자',percent:'백분율',boolean:'참·거짓',date:'ISO 날짜'}).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>)}</div>}
    {error&&<p role="alert">{error}</p>}
    {preview&&<><p>전체 {preview.total_rows}행 검사 · 미리보기 {preview.shown_rows}행 · 오류 {preview.error_count}개{preview.duplicate_headers?' · 중복 제목은 열 위치로 구분합니다':''}</p>
      <div style={{overflow:'auto',maxHeight:350}}><table><tbody>{preview.rows.map((r,i)=><tr key={i}>{r.map((v,j)=><td key={j} style={{border:'1px solid #bbc',padding:6,whiteSpace:'pre-wrap'}}>{v}</td>)}</tr>)}</tbody></table></div>
      {preview.errors.map((e,i)=><p key={i}>{e.row}행 {e.column?`${e.column}열`:''}: {e.error}</p>)}
      <button disabled={busy||preview.error_count>0} onClick={()=>void run(async()=>onImported(await sheetCommand<SheetDetail>(detail.document.id,'csv-import',args())))}>XLSX 사본으로 가져오기</button></>}
  </section>;
}
