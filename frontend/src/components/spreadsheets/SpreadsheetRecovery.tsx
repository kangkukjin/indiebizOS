import { useEffect, useState } from 'react';
import { sheetCommand, sheetRequest, sessionArgs, type SheetDetail } from '../../lib/api-spreadsheets';

type Version = {id:string;created_at:number;label?:string;is_recovery?:boolean};
type Recovery = {items:{state:string}[];detail:SheetDetail};

// This surface does not require a working editor or force-save callback.
export function SpreadsheetRecovery({documentId,clientId,onRecovered,onCancel}:{documentId:string;clientId:string;onRecovered:(d:SheetDetail)=>void;onCancel:()=>void}) {
  const [detail,setDetail]=useState<SheetDetail|null>(null),[versions,setVersions]=useState<Version[]>([]);
  const [selected,setSelected]=useState(''),[confirmed,setConfirmed]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState('');
  async function inspect(){
    setBusy(true);setError('');setConfirmed(false);setDetail(null);setSelected('');
    try {
      const r=await sheetCommand<Recovery>(documentId,'recover');
      const v=await sheetRequest<{items:Version[]}>(`/${documentId}/versions`);
      setDetail(r.detail);setVersions(v.items);
      const labels:Record<string,string>={saved:'원본 저장 확인됨',copy_saved:'사본 저장 확인됨',not_written:'원본에 기록되지 않음 · 초안 보존',conflict:'외부 파일 변경 또는 저장 충돌 · 초안 보존'};
      setResult(r.items.length?r.items.map(x=>labels[x.state]||x.state).join(' / '):'확정 대기 중인 파일 저장이 없습니다');
    } catch(e){setError(String(e));} finally{setBusy(false);}
  }
  useEffect(()=>{void inspect();},[documentId]);
  async function resume(){
    if(!detail||!confirmed)return;
    setBusy(true);setError('');
    try {
      const s=detail.session;
      let d=s?await sheetCommand<SheetDetail>(documentId,'reclaim',{client_id:clientId,expected_epoch:s.engine_epoch,expected_revision:s.session_revision}):await sheetCommand<SheetDetail>(documentId,'sessions',{client_id:clientId});
      // Keep the successful claim locally even if restoring fails; no silent retry.
      setDetail(d);
      if(selected&&d.session){
        await sheetCommand(documentId,'restore',{...sessionArgs(d.session),revision_id:selected,operation_id:crypto.randomUUID()});
        d=await sheetRequest<SheetDetail>(`/${documentId}`);
      }
      onRecovered(d);
    } catch(e){setError(String(e));setConfirmed(false);} finally{setBusy(false);}
  }
  const needsChoice=detail?.session?.state==='recovering';
  const captured=(detail?.session as (SheetDetail['session'] & {captured_at?:number}))?.captured_at;
  return <section className="sheet-home" aria-label="스프레드시트 복구">
    <h2>연결·저장 복구</h2>
    <p>원본 파일을 덮어쓰지 않고 보존된 초안으로 편집을 다시 연결합니다. 서버에 전달되지 않은 입력은 복구할 수 없습니다.</p>
    <p role="status">{busy?'복구 상태 확인 중…':result}</p>
    {captured&&<p>마지막 초안 확인: {new Date(captured*1000).toLocaleString()}</p>}
    {detail&&<>
      {needsChoice&&<p>마지막 확인 초안과 엔진 종료 후보의 순서를 확정할 수 없습니다. 이어갈 버전을 선택하세요.</p>}
      <label>복구할 버전<select value={selected} disabled={busy} onChange={e=>setSelected(e.target.value)}>
        <option value="">{needsChoice?'버전을 선택하세요':'현재 보존된 초안'}</option>
        {versions.map(v=><option key={v.id} value={v.id}>{v.label||'원본 저장 버전'} · {new Date(v.created_at*1000).toLocaleString()}</option>)}
      </select></label>
      <p>복구 후 계산 상태는 다시 확인해야 합니다. 원본 반영은 편집 화면의 원본 저장에서 수행합니다.</p>
      <label><input type="checkbox" checked={confirmed} disabled={busy} onChange={e=>setConfirmed(e.target.checked)}/>이전 창의 작성 권한을 종료하고 선택한 초안으로 이어갑니다</label>
      <button disabled={busy||!confirmed||(needsChoice&&!selected)} onClick={()=>void resume()}>선택한 초안으로 다시 연결</button>
    </>}
    <button disabled={busy} onClick={()=>void inspect()}>복구 상태 다시 확인</button>
    <button disabled={busy} onClick={onCancel}>돌아가기</button>
    {error&&<p role="alert">{error}</p>}
  </section>;
}
