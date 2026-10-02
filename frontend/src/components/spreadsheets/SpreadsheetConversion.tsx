import { useState } from 'react';
import { sheetCommand, sheetRequest, sessionArgs, type SheetDetail } from '../../lib/api-spreadsheets';

type Report = {message:string;unverified:string[];source_format:string;output_format:string;engine:string;calculation:string;changes:string[]};
export function SpreadsheetConversion({detail,beforeConvert,onConverted}:{
  detail:SheetDetail;beforeConvert:()=>Promise<void>;onConverted:(d:SheetDetail)=>Promise<void>;
}) {
  const [format,setFormat]=useState('xlsx'),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const report=(detail.document as SheetDetail['document'] & {provenance?:{loss_report?:Report}}).provenance?.loss_report;
  const supported=['xlsx','xltx','ods','ots'].includes(detail.document.source_format);
  const convert=async()=>{
    if(busy)return;
    setBusy(true);setError('');
    try {
      await beforeConvert();
      const current=await sheetRequest<SheetDetail>('/'+detail.document.id);
      const result=await sheetCommand<SheetDetail>(current.document.id,'convert',{
        output_format:format,expected_revision:current.document.revision_id,
        ...(current.session?sessionArgs(current.session):{}),
      });
      await onConverted(result);
    } catch(e) {setError(String(e));} finally {setBusy(false);}
  };
  return <section aria-label="통합문서 형식 변환" className="sheet-actions">
    {report&&<div role="status"><strong>{report.source_format.toUpperCase()} → {report.output_format.toUpperCase()}</strong>
      <p>{report.message}</p>{report.changes?.map(change=><p key={change} role="alert">{change}</p>)}<p>{report.engine} · {report.calculation}</p><p>보존 미확인: {report.unverified.join(' · ')}</p></div>}
    {supported&&<><label>변환 사본 형식<select aria-label="변환 사본 형식" value={format} disabled={busy} onChange={e=>setFormat(e.target.value)}>
      {['xlsx','xltx','ods','ots'].map(f=><option key={f} value={f}>{f.toUpperCase()}</option>)}
    </select></label><button disabled={busy} onClick={()=>void convert()}>{busy?'변환 중…':'변환 사본 만들기'}</button>
    <span>원본은 보존됩니다. 변환 후 수식·차트·서식·인쇄를 비교하세요. ODS·템플릿 편집은 XLSX 사본에서 합니다. ODS·OTS는 LibreOffice에서 별도 재계산될 수 있습니다.</span></>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}
