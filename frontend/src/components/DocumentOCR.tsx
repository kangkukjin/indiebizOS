import { useState } from 'react';
import { documentCommand, type Detail } from '../lib/api-documents';
type OCR = {id:string;pages:{number:number;words:{id:number;text:string;confidence:number}[]}[]};
export function DocumentOCR({detail}:{detail:Detail}) {
  const [pages,setPages]=useState('1');
  const [data,setData]=useState<OCR|null>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const act=async(fn:()=>Promise<void>)=>{if(busy)return;setBusy(true);setMessage('');try{await fn();}catch(e){setMessage(String(e));}finally{setBusy(false);}};
  return <details className="document-ocr"><summary>스캔 OCR · 인식문 교정</summary>
    <p>원본 저장 후 실행하세요. 한·영 인식문을 원본 페이지와 대조하고 교정할 수 있습니다. 선택한 쪽은 영상과 검색 텍스트를 담은 새 PDF로 출력합니다.</p>
    <label>OCR 쪽 번호<input value={pages} onChange={e=>setPages(e.target.value)} placeholder="1,2,3"/></label>
    <button disabled={busy} onClick={()=>void act(async()=>{
      const numbers=pages.split(',').map(v=>Number(v.trim()));
      setData(await documentCommand<OCR>(detail.document.id,'ocr',{expected_revision:detail.document.revision_id,pages:numbers}));setMessage('인식 완료 · 낮은 신뢰도의 단어부터 확인하세요');
    })}>한국어·영어 OCR</button>
    {data && <><div className="ocr-words">{data.pages.map(p=><section key={p.number}><h4>{p.number}쪽</h4>{p.words.map(w=><label key={w.id} className={w.confidence<75?'ocr-low':''}>신뢰도 {Math.round(w.confidence)}%<input aria-label={`${p.number}쪽 단어 ${w.id+1}`} value={w.text} onChange={e=>setData({...data,pages:data.pages.map(page=>page.number===p.number?{...page,words:page.words.map(word=>word.id===w.id?{...word,text:e.target.value}:word)}:page)})}/></label>)}</section>)}</div>
      <button disabled={busy} onClick={()=>void act(async()=>{
        await documentCommand(detail.document.id,'ocr-correct',{ocr_id:data.id,edits:data.pages.flatMap(p=>p.words.map(w=>({page:p.number,word:w.id,text:w.text})))});
        const result=await documentCommand<Detail>(detail.document.id,'ocr-export',{ocr_id:data.id});setMessage('검색 PDF 저장됨: '+result.document.source_uri);
      })}>교정한 검색 PDF 저장</button></>}
    <p role="status">{busy?'OCR 처리 중…':message}</p>
  </details>;
}
