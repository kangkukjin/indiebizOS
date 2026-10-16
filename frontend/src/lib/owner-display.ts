import { flushSync } from 'react-dom';
import baseline from 'virtual:owner-display';
import { chatDisplay } from '../components/chat/ChatDisplay';
import { launcherDisplay } from '../components/LauncherDisplay';
import { installUiMessages } from '../i18n/ui';
import { getBackendOrigin } from './backend-origin';

type Display = {format: string; state: number; surface: string; host: string; version: string; code: string; css: string; messages: Parameters<typeof installUiMessages>[0]};
type Candidate = {chat: Parameters<typeof chatDisplay.install>[0]; launcher: Parameters<typeof launcherDisplay.install>[0]};
const host = window as unknown as {__indieOwnerCandidate?: Candidate; getConversation: unknown};
const key='indiebiz.owner.display';
let current=baseline.version, busy=false, composing=false;
const ready=new Set<() => void>();
document.addEventListener('compositionstart',()=>{composing=true;},true);
document.addEventListener('compositionend',()=>{composing=false;ready.forEach(fn=>fn());ready.clear();},true);
const settled=()=>composing?new Promise<void>(resolve=>ready.add(resolve)):Promise.resolve();
async function validate(value: Display) {
  if(value.format!=='indiebiz-owner-display-1'||value.state!==1||value.surface!=='owner'||value.host!==baseline.host)throw Error('실행부가 다른 판본입니다. 앱 업데이트가 필요합니다');
  const {version,...body}=value;
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(body)));
  if(Array.from(new Uint8Array(bytes)).map(n=>n.toString(16).padStart(2,'0')).join('')!==version)throw Error('화면 지문 불일치');
}
export async function applyOwnerDisplay(value: Display, persist=true) {
  if(busy)throw Error('화면 갱신이 진행 중입니다');busy=true;
  const undo: Array<() => void>=[];
  try {
    await validate(value);await settled();
    const focus=document.activeElement as HTMLInputElement|null;
    const selection=focus&&typeof focus.selectionStart==='number'?[focus.selectionStart,focus.selectionEnd] as const:null;
    const scroll=Array.from(document.querySelectorAll('*')).filter(e=>e.scrollTop||e.scrollLeft).map(e=>({e,top:e.scrollTop,left:e.scrollLeft}));
    const oldRules=host.getConversation;
    undo.push(()=>{host.getConversation=oldRules;});
    delete host.__indieOwnerCandidate;
    const script=document.createElement('script');script.textContent=value.code;
    document.head.appendChild(script);script.remove();
    const candidate=host.__indieOwnerCandidate as Candidate|undefined;delete host.__indieOwnerCandidate;
    if(!candidate)throw Error('표시 모듈 구문 오류');
    undo.push(installUiMessages(value.messages));
    const previous=document.getElementById('owner-display-css');
    const style=document.createElement('style');style.id='owner-display-css';style.textContent=value.css;document.head.appendChild(style);previous?.remove();
    undo.push(()=>{style.remove();if(previous)document.head.appendChild(previous);});
    try {
      flushSync(()=>{undo.push(chatDisplay.install(candidate.chat));undo.push(launcherDisplay.install(candidate.launcher));});
      if(persist)localStorage.setItem(key,JSON.stringify(value));
      current=value.version;
    } finally {
      scroll.forEach(({e,top,left})=>{if(e.isConnected){e.scrollTop=top;e.scrollLeft=left;}});
      if(focus?.isConnected){focus.focus({preventScroll:true});if(selection)focus.setSelectionRange(selection[0],selection[1]);}
    }
  } catch(error) { flushSync(()=>undo.reverse().forEach(fn=>fn()));throw error; }
  finally {busy=false;}
}
export async function startOwnerDisplay() {
  try {const cached=localStorage.getItem(key);if(cached)await applyOwnerDisplay(JSON.parse(cached),false);}catch{/* The installed app is the recovery baseline. */}
  const button=document.createElement('button');button.hidden=true;button.textContent='새 화면 있음';button.id='ownerDisplayUpdate';
  button.style.cssText='position:fixed;right:12px;bottom:12px;z-index:100000;background:#fff8ed;color:#4a4035;border:1px solid #d8d0c5;border-radius:8px;padding:8px 12px';
  document.body.appendChild(button);
  const origin=await getBackendOrigin();const url=origin+'/launcher/owner-display';let offered: Display|null=null;
  async function check(){if(busy)return;try{const response=await fetch(url+'?metadata=true',{cache:'no-store'});if(!response.ok)return;const value=await response.json();offered=value.version===current?null:value;button.hidden=!offered;button.textContent=offered?.host!==baseline.host?'앱 업데이트 필요':'새 화면 있음';}catch{/* Offline is normal. */}}
  button.onclick=async()=>{
    if(!offered||busy)return;
    if(offered.host!==baseline.host){button.textContent='실행부가 바뀌었습니다. 앱을 업데이트하세요';return;}
    if(!window.confirm('새 화면을 적용할까요? 작성 중인 내용과 작업은 유지됩니다.'))return;
    const version=offered.version;button.disabled=true;
    try{const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw Error('화면 다운로드 실패');const value=await response.json();if(value.version!==version)throw Error('선택한 판본이 변경됐습니다');await applyOwnerDisplay(value);button.hidden=true;offered=null;}
    catch(error){button.textContent='이전 화면 유지 · '+String(error instanceof Error?error.message:error);}
    finally{button.disabled=false;}
  };
  setTimeout(check,15000);setInterval(check,60000);
}
