/**
 * ForageBrowser 비-JSX 지원층 (2026-07-18 모듈화 — 1500줄 규칙)
 *
 * ForageBrowser.tsx 에서 verbatim 이동: API 상수·webview escape-hatch·
 * 인라인 번역 JS 조각·사냥판 타입(PoolItem/Hunt)·후보 파서·탭 타입·
 * 비밀번호 금고 IPC·목적지 추출. GenericInstrument 의 generic/manifest.ts 대응물.
 */
import type * as React from 'react';

export const API = 'http://127.0.0.1:8765';

// <webview> 는 표준 JSX 엘리먼트가 아니다(Electron 전용 escape-hatch).
export const WebView = 'webview' as unknown as React.FC<Record<string, unknown>>;

// 인라인 DOM 번역 — 구글 페이지 프록시(translate.goog)가 일부 지역에서 막혀(지역 차단), webview 로
// *이동*하지 않고 현재 페이지의 텍스트 노드만 백엔드로 보내 번역해 *제자리 치환*한다. 세 JS 조각을
// executeJavaScript 로 주입: 추출(원문 보관) → 치환 → 복원. 노드 참조를 webview window 전역에 남겨
// 같은 페이지 컨텍스트의 세 호출이 공유한다(페이지 이동 시 stale → onStart 에서 상태 리셋).

// 텍스트 노드 수집(script/style/입력요소 제외, 공백-only 제외) → window.__forageTx 에 노드·원문 보관,
// 문자열 배열 반환. 4000 상한으로 초대형 페이지 폭주 방지.
export const EXTRACT_JS = `(function(){
  var W=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,{acceptNode:function(n){
    if(!n.nodeValue||!n.nodeValue.trim())return NodeFilter.FILTER_REJECT;
    var p=n.parentElement;if(!p)return NodeFilter.FILTER_REJECT;
    var t=p.tagName;if(t==='SCRIPT'||t==='STYLE'||t==='NOSCRIPT'||t==='TEXTAREA'||p.isContentEditable)return NodeFilter.FILTER_REJECT;
    return NodeFilter.FILTER_ACCEPT;
  }});
  var nodes=[],texts=[],n;while((n=W.nextNode())&&nodes.length<4000){nodes.push(n);texts.push(n.nodeValue);}
  window.__forageTx=nodes;window.__forageTxOrig=texts.slice();
  return texts;
})()`;

// 번역문 배열을 노드에 주입(원문은 __forageTxOrig 에 이미 보관). translations 는 JSON 으로 끼워넣는다.
export const replaceJs = (translations: string[]) => `(function(){
  var t=${JSON.stringify(translations)};var ns=window.__forageTx||[];
  for(var i=0;i<ns.length&&i<t.length;i++){if(t[i]!=null&&ns[i])ns[i].nodeValue=t[i];}
  return ns.length;
})()`;

// 원문 복원.
export const RESTORE_JS = `(function(){
  var ns=window.__forageTx||[],o=window.__forageTxOrig||[];
  for(var i=0;i<ns.length&&i<o.length;i++){if(ns[i])ns[i].nodeValue=o[i];}
  return ns.length;
})()`;


export interface Destination { label: string; meta?: string; url: string }

// --- 사냥판(합작 포식 후보 풀) ---
// 후보 하나의 생애: 신규 → (제외 | 방문 → (삭제 | 유지)) → 정답.
// 판의 규칙: 빼기는 인간만, 더하기는 AI(+인간의 📌 담기)만. 리스트 조작이 곧 대화다.
export interface PoolItem {
  id: string;
  url: string;
  title: string;
  reason: string;          // 한 줄 이유 — 어떤 해석으로 골랐는지 드러나는 곳
  source: 'ai' | 'human';  // human = 브라우징 중 직접 담음(가장 강한 양성 신호)
  round: number;           // 몇 차 보충에서 왔나
  removed: null | 'excluded' | 'deleted';  // excluded=안 가보고 치움, deleted=가보고 치움
  visited: boolean;
  dwellMs: number;         // 누적 체류(대략) — 판으로 돌아올 때 합산
  image?: string;          // 대표 이미지(og:image) — 그리드용. undefined=아직 안 받음, ''=받았지만 없음
}

export interface Hunt {
  id: string;      // 보존·복원용 안정 식별자 — 세션을 넘어 살아남는다
  saved: boolean;  // 판 도서관에 보존 중인가(수동 토글)
  query: string;   // 원 질의 — 보충 라운드의 기준
  intro: string;   // AI 서두 한 줄
  outro: string;   // 링크 뒤 덧말(재고 고갈 시 되물음 등)
  round: number;
  items: PoolItem[];
}

// 응답 텍스트 → 후보들. "- [제목](URL) — 이유" 줄을 파싱, 링크 없는 서두/말미는 intro/outro 로.
// 링크가 하나도 없으면 items 가 비고 → 호출측이 본문 마크다운 렌더로 폴백한다.
export function parseCandidates(text: string): { intro: string; outro: string; items: { title: string; url: string; reason: string }[] } {
  const items: { title: string; url: string; reason: string }[] = [];
  const intro: string[] = [];
  const outro: string[] = [];
  const linkRe = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/;
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    const m = line.match(linkRe);
    if (m) {
      const after = line.slice((m.index ?? 0) + m[0].length);
      items.push({
        title: m[1].replace(/\*+/g, '').trim(),
        url: m[2],
        reason: after.replace(/^[\s—–:·,-]+/, '').replace(/\*+/g, '').trim(),
      });
    } else {
      (items.length === 0 ? intro : outro).push(line.replace(/^[#>*-]+\s*/, '').replace(/\*+/g, ''));
    }
  }
  return { intro: intro.join(' '), outro: outro.join(' '), items };
}

// 브라우저 탭 — initialUrl 은 webview src(최초 1회만 로드), url/title 은 네비게이션으로 갱신되는 표시값.
// src 를 이후에 안 건드려야 in-page 이동이 재로드로 튀지 않는다(원래 단일 webview 의 src 불변 원칙 계승).
export interface Tab {
  id: string;
  kind: 'web' | 'favorites' | 'history' | 'library';   // web=webview, 나머지=내부 페이지(webview 아님)
  initialUrl: string;
  url: string;
  title: string;
  canBack: boolean;
  canFwd: boolean;
  loading: boolean;
  translated: boolean;
}

// 비밀번호 금고 IPC (Electron preload 노출). 웹(비-Electron)에선 undefined → 기능 자동 비활성.
export type ForagePwApi = {
  foragePwListHost?: (url: string) => Promise<{ username: string }[]>;
  foragePwGet?: (url: string, username: string | null) => Promise<{ username: string; password: string } | null>;
  foragePwSave?: (origin: string, username: string, password: string) => Promise<true | { error: string }>;
  foragePwImportChrome?: () => Promise<{ imported: number; total: number } | { error: string }>;
};
export const pwApi = (): ForagePwApi => ((window as any).electron || {});
export const hasPwVault = () => typeof (window as any).electron?.foragePwGet === 'function';

// 현재 페이지에 비밀번호 입력칸이 있는지 + origin/host 반환 (없으면 null)
export const DETECT_PW_JS = `(function(){var pw=document.querySelector('input[type="password"]');return pw?{host:location.host,origin:location.origin}:null;})()`;

// 현재 채워진 로그인 값 읽기 (저장용). 비밀번호칸 직전의 text/email 칸을 아이디로 추정.
export const READ_PW_JS = `(function(){var pw=document.querySelector('input[type="password"]');if(!pw||!pw.value)return null;var all=[].slice.call(document.querySelectorAll('input'));var i=all.indexOf(pw);var user=null;for(var j=i-1;j>=0;j--){var t=(all[j].type||'').toLowerCase();if(t==='text'||t==='email'||t===''){user=all[j];break;}}return{origin:location.origin,host:location.host,username:user?user.value:'',password:pw.value};})()`;

// 아이디/비번을 DOM 에 주입. React 통제 입력도 먹도록 native setter + input/change 이벤트 발사.
// 자동 제출은 하지 않는다 — 채우기까지만(augmentation-over-autonomy).
export function fillPwJs(username: string, password: string): string {
  return `(function(){
    function setVal(el,val){var proto=el.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;var d=Object.getOwnPropertyDescriptor(proto,'value');if(d&&d.set)d.set.call(el,val);else el.value=val;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}
    var pw=document.querySelector('input[type="password"]');if(!pw)return false;
    var all=[].slice.call(document.querySelectorAll('input'));var i=all.indexOf(pw);var user=null;
    for(var j=i-1;j>=0;j--){var t=(all[j].type||'').toLowerCase();if(t==='text'||t==='email'||t===''){user=all[j];break;}}
    if(!user){user=document.querySelector('input[type="email"],input[type="text"]');}
    var U=${JSON.stringify(username)},P=${JSON.stringify(password)};
    if(user&&U)setVal(user,U);setVal(pw,P);try{pw.focus();}catch(e){}return true;
  })()`;
}

// 응답에서 목적지(클릭 가능한 링크)를 뽑고, [MAP:] 원문은 본문에서 걷어낸다.
// 1) [MAP:{...}] 블록의 markers[].{name,meta,url}  2) 본문 인라인 링크는 마크다운 a 렌더러가 처리.
export function extractDestinations(content: string): { text: string; destinations: Destination[] } {
  const destinations: Destination[] = [];
  let text = content;

  const MARK = '[MAP:';
  let start = text.indexOf(MARK);
  while (start !== -1) {
    // JSON 끝(중괄호 카운팅, 문자열 내부 무시) — chatUtils.parseMapData 와 같은 방식.
    let depth = 0, end = -1, inStr = false, esc = false;
    for (let i = start + MARK.length; i < text.length; i++) {
      const c = text[i];
      if (esc) { esc = false; continue; }
      if (c === '\\' && inStr) { esc = true; continue; }
      if (c === '"') { inStr = !inStr; continue; }
      if (inStr) continue;
      if (c === '{') depth++;
      else if (c === '}') { depth--; if (depth === 0 && text[i + 1] === ']') { end = i + 2; break; } }
    }
    if (end === -1) break;
    try {
      const data = JSON.parse(text.substring(start + MARK.length, end - 1));
      for (const m of data.markers || []) {
        if (m?.url) destinations.push({ label: m.name || m.url, meta: m.meta, url: m.url });
      }
    } catch { /* 파싱 실패 무시 */ }
    text = text.slice(0, start) + text.slice(end);
    start = text.indexOf(MARK);
  }
  return { text: text.trim(), destinations };
}
