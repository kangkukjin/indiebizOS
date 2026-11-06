import { useEffect, useRef, useState } from 'react';
import { api } from '../../lib/api';
import { sessionCall, type SessionTarget } from './useConversationSession';
interface Process {id:string;command:string;state:string;generation:string;cursor:number;output:{stream:string;text:string}[];capabilities:{resize:boolean};gap:unknown}
export function ProcessSessionsPanel({sid,target,onClose}:{sid:string;target:SessionTarget;onClose:()=>void}) {
 const [items,setItems]=useState<Process[]>([]),[error,setError]=useState(''),[input,setInput]=useState(''),[selected,setSelected]=useState('');
 const refresh=()=>sessionCall<{items:Process[]}>(`/${sid}/processes`,target).then(r=>{setItems(r.items);setSelected(old=>old||r.items[0]?.id||'');});
 useEffect(()=>{void refresh().catch(e=>setError(String(e)));const timer=setInterval(()=>{void refresh().catch(e=>setError(String(e)));},1000);return ()=>clearInterval(timer);},[sid]);
 const pending=useRef<{signature:string;id:string}|undefined>(undefined);
 const [sending,setSending]=useState(false);
 const proc=items.find(p=>p.id===selected);
 const control=async(action:string)=>{
  if(!proc||sending)return;
  const body={action,generation:proc.generation,...(action==='input'?{text:input,newline:true}:{}),...(action==='resize'?{cols:120,rows:40}:{})};
  const signature=JSON.stringify({id:proc.id,...body});
  if(pending.current&&pending.current.signature!==signature){setError('이전 입력의 결과가 불명확합니다. 같은 입력으로 결과를 확인하거나 프로세스를 종료하세요.');if(action!=='cancel')return;}
  if(!pending.current||pending.current.signature!==signature)pending.current={signature,id:crypto.randomUUID()};
  setSending(true);
  try{
   const result=action==='cancel'
    ? await api.request(`/process-sessions/${proc.id}`,{method:'DELETE'})
    : await api.request<{delivery?:string}>(`/process-sessions/${proc.id}/control`,{method:'POST',body:JSON.stringify({...body,request_id:pending.current.id})});
   if(['delivery_unknown','partial','backpressure'].includes((result as {delivery?:string}).delivery||'')){
    setError('입력이 모두 전달됐는지 확인이 필요합니다. 자동 재전송하지 않습니다. 출력을 확인하세요: '+JSON.stringify(result)+'');
   }else{
    pending.current=undefined;if(action==='input')setInput('');setError('');
   }
   await refresh();
  }catch(e){setError(String(e));}finally{setSending(false);}
 };
 return <div className="fixed inset-0 z-[70] bg-black/40 flex items-center justify-center" role="dialog" aria-label="프로세스 제어"><div className="bg-white rounded-xl p-5 w-[750px] max-w-[95vw] space-y-3">
  <div className="flex justify-between"><h2>실행 중인 프로그램</h2><button onClick={onClose}>닫기</button></div>
  <select className="border p-2 w-full" value={selected} onChange={e=>setSelected(e.target.value)}>{items.map(p=><option key={p.id} value={p.id}>{p.command} ({p.state})</option>)}</select>
  {!items.length&&<p>이 대화에서 시작한 프로세스 세션이 없습니다.</p>}
  {proc&&<><pre className="h-64 overflow-auto bg-gray-950 text-gray-100 p-3 text-xs whitespace-pre-wrap">{proc.gap?'[오래된 출력 일부가 보존 범위를 벗어났습니다]\n':''}{proc.output.map(o=>o.text).join('')}</pre>
   <div className="flex gap-2"><input aria-label="프로세스 입력" className="border rounded p-2 flex-1" value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')void control('input');}}/><button disabled={sending||proc.state!=='running'} onClick={()=>void control('input')}>입력 전송</button></div>
   <div className="flex gap-4 text-sm"><button onClick={()=>void control('interrupt')}>Ctrl+C</button><button onClick={()=>void control('eof')}>EOF</button>{proc.capabilities.resize&&<button onClick={()=>void control('resize')}>120 × 40</button>}<button onClick={()=>void control('cancel')}>프로세스 종료</button></div>
  </>}{error&&<p role="alert" className="text-red-700 text-sm">{error}</p>}
 </div></div>;
}
