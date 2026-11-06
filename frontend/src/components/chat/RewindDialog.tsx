import { useEffect, useState } from 'react';
import { sessionCall, type SessionTarget } from './useConversationSession';
interface Checkpoint { id:string; created_at:number; turn_id:string; messages:number[]; pinned:boolean }
interface Plan { id:string; state:string; mode:string; files:{path:string;current:string;restored:string}[]; conflicts:string[]; external_effects:string; error?:string; diff?:string }
export function RewindDialog({sid,target,onClose}:{sid:string;target:SessionTarget;onClose:()=>void}) {
 const [points,setPoints]=useState<Checkpoint[]>([]), [selected,setSelected]=useState(''), [mode,setMode]=useState('both');
 const [plan,setPlan]=useState<Plan>(), [busy,setBusy]=useState(false), [error,setError]=useState('');
 useEffect(()=>{void sessionCall<{items:Checkpoint[]}>(`/${sid}/checkpoints`,target).then(r=>{setPoints(r.items);setSelected(r.items[0]?.id || '');}).catch(e=>setError(String(e)));},[sid]);
 useEffect(()=>{
  if (!plan || ['prepared','completed','cancelled'].includes(plan.state) || plan.error) return;
  const timer=setInterval(()=>{void sessionCall<Plan>(`/${sid}/rewinds/${plan.id}`,target).then(setPlan).catch(e=>setError(String(e)));},700);
  return ()=>clearInterval(timer);
 },[plan?.id,plan?.state,plan?.error]);
 const preview=async()=>{setBusy(true);setError('');try{setPlan(await sessionCall<Plan>(`/${sid}/rewinds/preview`,target,'POST',{checkpoint:selected,mode}));}catch(e){setError(String(e));}finally{setBusy(false);}};
 const apply=async()=>{if(!plan)return;setBusy(true);setError('');try{await sessionCall(`/${sid}/rewinds`,target,'POST',{preview:plan.id});setPlan({...plan,state:'quiescing',error:undefined});}catch(e){setError(String(e));}finally{setBusy(false);}};
 return <div className="fixed inset-0 z-[70] bg-black/40 flex items-center justify-center" role="dialog" aria-label="대화 시점 복구">
  <div className="bg-white rounded-xl shadow-xl p-5 w-[650px] max-w-[95vw] max-h-[85vh] overflow-auto space-y-4">
   <div className="flex justify-between"><h2 className="font-semibold">대화 시점으로 되돌리기</h2><button onClick={onClose}>닫기</button></div>
   <p className="text-sm text-gray-600">각 요청이 시작되기 직전으로 돌아갑니다. 현재 상태도 복구 지점으로 보존합니다.</p>
   <select aria-label="복구 시점" className="w-full border rounded p-2" value={selected} onChange={e=>{setSelected(e.target.value);setPlan(undefined);}}>
    {points.map(p=><option key={p.id} value={p.id}>{new Date(p.created_at*1000).toLocaleString()} · {p.pinned?'복구 전 보존 상태':`요청 전 (이전 메시지 ${p.messages.length}개)`}</option>)}
   </select>
   <div className="flex gap-4">{[['both','대화와 파일'],['files','파일만'],['conversation','대화만']].map(([value,label])=><label key={value}><input type="radio" checked={mode===value} onChange={()=>{setMode(value);setPlan(undefined);}}/> {label}</label>)}</div>
   <button disabled={busy||!selected} onClick={()=>void preview()} className="border rounded px-3 py-2">변경 미리보기</button>
   {plan&&<div className="text-sm space-y-2"><p>상태: {plan.state==='completed'?'복구 완료':plan.state}</p><p>{plan.external_effects}</p>
    <p>추적된 파일 {plan.files.length}개</p><ul>{plan.files.map(f=><li className="font-mono text-xs break-all" key={f.path}>{f.path}</li>)}</ul>
    {plan.diff&&<pre className="max-h-64 overflow-auto bg-gray-50 p-2 text-xs whitespace-pre-wrap">{plan.diff}</pre>}
    {plan.conflicts.length>0&&<p className="text-red-700">외부 수정 충돌 — 덮어쓰지 않습니다: {plan.conflicts.join(', ')}</p>}
    {(plan.state==='prepared'||plan.error)&&<button disabled={busy||!!plan.conflicts.length} onClick={()=>void apply()} className="bg-amber-800 text-white rounded px-3 py-2">이 상태로 복구</button>}
    {plan.error&&<p className="text-red-700">{plan.error}</p>}
   </div>}
   {error&&<p role="alert" className="text-red-700 text-sm">{error}</p>}
  </div>
 </div>;
}
