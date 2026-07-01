/**
 * ForageBrowser — 계기판에 박힌 "포식 브라우저" (개인 검색엔진 + 도로)
 *
 * 외골격형 공동 포식. 두 상태로 동작한다:
 *   1) search — 구글 같은 검색홈. 프롬프트를 치면 포식 에이전트(/forage/chat)가
 *      "가볼 만한 곳"의 링크를 내준다. *무엇을·어디로*는 전부 에이전트(프롬프트+IBL) 몫.
 *   2) browse — 링크를 클릭하면 진짜 크로미움(webview)으로 그 장소에 진입. 인간이 직접 운전.
 *
 * 핵심: AI는 운전석이 아니라 *목적지를 까는 자리*에 앉는다. 클릭·진입은 100% 인간.
 * 검색 결과의 링크(마크다운 [제목](url) + [MAP:] 마커의 url)를 클릭하면 외부 브라우저가
 * 아니라 이 창의 webview로 열린다 — "검색 → 클릭해서 들어감"이 한 창에서 닫힌다.
 *
 * webview 는 main.js 의 webviewTag=true 필요(앱 재시작 후 적용).
 */
import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useFileAttachments } from './chat/useFileAttachments';

const API = 'http://127.0.0.1:8765';

// <webview> 는 표준 JSX 엘리먼트가 아니다(Electron 전용 escape-hatch).
const WebView = 'webview' as unknown as React.FC<Record<string, unknown>>;

// 인라인 DOM 번역 — 구글 페이지 프록시(translate.goog)가 일부 지역에서 막혀(지역 차단), webview 로
// *이동*하지 않고 현재 페이지의 텍스트 노드만 백엔드로 보내 번역해 *제자리 치환*한다. 세 JS 조각을
// executeJavaScript 로 주입: 추출(원문 보관) → 치환 → 복원. 노드 참조를 webview window 전역에 남겨
// 같은 페이지 컨텍스트의 세 호출이 공유한다(페이지 이동 시 stale → onStart 에서 상태 리셋).

// 텍스트 노드 수집(script/style/입력요소 제외, 공백-only 제외) → window.__forageTx 에 노드·원문 보관,
// 문자열 배열 반환. 4000 상한으로 초대형 페이지 폭주 방지.
const EXTRACT_JS = `(function(){
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
const replaceJs = (translations: string[]) => `(function(){
  var t=${JSON.stringify(translations)};var ns=window.__forageTx||[];
  for(var i=0;i<ns.length&&i<t.length;i++){if(t[i]!=null&&ns[i])ns[i].nodeValue=t[i];}
  return ns.length;
})()`;

// 원문 복원.
const RESTORE_JS = `(function(){
  var ns=window.__forageTx||[],o=window.__forageTxOrig||[];
  for(var i=0;i<ns.length&&i<o.length;i++){if(ns[i])ns[i].nodeValue=o[i];}
  return ns.length;
})()`;


interface Destination { label: string; meta?: string; url: string }

// 브라우저 탭 — initialUrl 은 webview src(최초 1회만 로드), url/title 은 네비게이션으로 갱신되는 표시값.
// src 를 이후에 안 건드려야 in-page 이동이 재로드로 튀지 않는다(원래 단일 webview 의 src 불변 원칙 계승).
interface Tab {
  id: string;
  kind: 'web' | 'favorites';   // web=webview, favorites=내부 즐겨찾기 바둑판 페이지(webview 아님)
  initialUrl: string;
  url: string;
  title: string;
  canBack: boolean;
  canFwd: boolean;
  loading: boolean;
  translated: boolean;
}

// 비밀번호 금고 IPC (Electron preload 노출). 웹(비-Electron)에선 undefined → 기능 자동 비활성.
type ForagePwApi = {
  foragePwListHost?: (url: string) => Promise<{ username: string }[]>;
  foragePwGet?: (url: string, username: string | null) => Promise<{ username: string; password: string } | null>;
  foragePwSave?: (origin: string, username: string, password: string) => Promise<true | { error: string }>;
  foragePwImportChrome?: () => Promise<{ imported: number; total: number } | { error: string }>;
};
const pwApi = (): ForagePwApi => ((window as any).electron || {});
const hasPwVault = () => typeof (window as any).electron?.foragePwGet === 'function';

// 현재 페이지에 비밀번호 입력칸이 있는지 + origin/host 반환 (없으면 null)
const DETECT_PW_JS = `(function(){var pw=document.querySelector('input[type="password"]');return pw?{host:location.host,origin:location.origin}:null;})()`;

// 현재 채워진 로그인 값 읽기 (저장용). 비밀번호칸 직전의 text/email 칸을 아이디로 추정.
const READ_PW_JS = `(function(){var pw=document.querySelector('input[type="password"]');if(!pw||!pw.value)return null;var all=[].slice.call(document.querySelectorAll('input'));var i=all.indexOf(pw);var user=null;for(var j=i-1;j>=0;j--){var t=(all[j].type||'').toLowerCase();if(t==='text'||t==='email'||t===''){user=all[j];break;}}return{origin:location.origin,host:location.host,username:user?user.value:'',password:pw.value};})()`;

// 아이디/비번을 DOM 에 주입. React 통제 입력도 먹도록 native setter + input/change 이벤트 발사.
// 자동 제출은 하지 않는다 — 채우기까지만(augmentation-over-autonomy).
function fillPwJs(username: string, password: string): string {
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
function extractDestinations(content: string): { text: string; destinations: Destination[] } {
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

export function ForageBrowser({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [mode, setMode] = useState<'search' | 'browse'>('search');

  // --- 검색홈 상태 ---
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [destinations, setDestinations] = useState<Destination[]>([]);
  const [error, setError] = useState<string | null>(null);
  // 첫화면 즐겨찾기 — 즐겨찾기 계기(🔖)와 같은 sites.json 을 IBL 로 공유(별도 저장소 없음).
  const [favorites, setFavorites] = useState<{ name: string; url: string }[]>([]);

  // 첨부(이미지·텍스트파일) — 프로젝트 에이전트 입력창과 같은 훅 재사용. 이건 에이전트 입력창이니까.
  const att = useFileAttachments();

  // --- 브라우즈(탭) 상태 — 크롬처럼 여러 사이트를 탭으로 동시에. 각 탭 = 하나의 webview. ---
  const webviewRefs = useRef<Record<string, any>>({});   // 탭 id → webview DOM
  const tabSeq = useRef(0);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  // 활성 탭에서 파생 — 주소/네비 버튼/로딩은 전부 활성 탭 값을 본다.
  const activeTab = tabs.find((t) => t.id === activeId) || null;
  const addr = activeTab?.url || '';
  const canBack = !!activeTab?.canBack;
  const canFwd = !!activeTab?.canFwd;
  const loading = !!activeTab?.loading;
  const activeWebview = (): any => (activeId ? webviewRefs.current[activeId] : null);

  const registerRef = (id: string, el: any) => { if (el) webviewRefs.current[id] = el; };
  const updateTab = (id: string, patch: Partial<Tab>) =>
    setTabs((prev) => prev.map((t) => (t.id === id ? { ...t, ...patch } : t)));

  // 새 탭으로 사이트 열기 — 즐겨찾기·검색결과·링크 클릭이 전부 여기로(각각 별개 탭이 쌓인다).
  const openTab = (url: string) => {
    const id = `t${++tabSeq.current}`;
    setTabs((prev) => [...prev, { id, kind: 'web', initialUrl: url, url, title: url, canBack: false, canFwd: false, loading: true, translated: false }]);
    setActiveId(id);
    setMode('browse');
  };

  // 스위치 → 즐겨찾기 바둑판 페이지를 새 탭으로(이미 있으면 그 탭으로 전환). 최신 목록 당김.
  const openFavoritesTab = () => {
    const existing = tabs.find((t) => t.kind === 'favorites');
    if (existing) { setActiveId(existing.id); setMode('browse'); loadFavorites(); return; }
    const id = `t${++tabSeq.current}`;
    setTabs((prev) => [...prev, { id, kind: 'favorites', initialUrl: '', url: '', title: '즐겨찾기', canBack: false, canFwd: false, loading: false, translated: false }]);
    setActiveId(id);
    setMode('browse');
    loadFavorites();
  };

  // 탭 닫기 — 닫은 게 활성이면 인접 탭으로, 마지막이면 검색홈으로 복귀.
  const closeTab = (id: string) => {
    const idx = tabs.findIndex((t) => t.id === id);
    const next = tabs.filter((t) => t.id !== id);
    delete webviewRefs.current[id];
    setTabs(next);
    if (id === activeId) {
      if (next.length === 0) { setActiveId(null); setMode('search'); }
      else { setActiveId(next[Math.min(idx, next.length - 1)].id); setMode('browse'); }
    }
  };

  // 주소·검색줄 자동 숨김 — 본문 볼 땐 감췄다가 상단 얇은 센서에 마우스를 올리면 다시 나온다.
  // (본문 webview 위의 마우스 이동은 호스트로 안 올라오므로, flex 흐름 안의 센서 띠로 되살린다.)
  const [barHidden, setBarHidden] = useState(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showBar = () => { if (hideTimer.current) { clearTimeout(hideTimer.current); hideTimer.current = null; } setBarHidden(false); };
  const scheduleHide = () => { if (hideTimer.current) clearTimeout(hideTimer.current); hideTimer.current = setTimeout(() => setBarHidden(true), 700); };

  // --- 비밀번호 채우기 상태 ---
  const [pwHasField, setPwHasField] = useState(false);          // 현재 페이지에 로그인 폼이 있나
  const [pwAccounts, setPwAccounts] = useState<{ username: string }[]>([]); // 이 host 저장 계정들
  const [pwMenuOpen, setPwMenuOpen] = useState(false);
  const [pwToast, setPwToast] = useState<string | null>(null);
  // ms=0 이면 자동으로 안 사라짐(에러 진단용) — 토스트를 클릭하면 닫힌다.
  const flash = (msg: string, ms = 1800) => { setPwToast(msg); if (ms > 0) setTimeout(() => setPwToast(null), ms); };

  // 번역 진행중 플래그(활성 탭 기준). 번역 여부는 탭별로 Tab.translated 에 보관.
  const [translating, setTranslating] = useState(false);

  // 번역 토글 — 텍스트 노드 추출 → 백엔드 번역 → 제자리 치환, 다시 누르면 원문 복원. 활성 탭 대상.
  const toggleTranslation = async () => {
    const el = activeWebview();
    if (!el || translating || !activeTab) return;
    if (activeTab.translated) {
      try { await el.executeJavaScript(RESTORE_JS, true); } catch { /* 페이지 전환 중일 수 있음 */ }
      updateTab(activeTab.id, { translated: false });
      return;
    }
    setTranslating(true);
    try {
      const texts: string[] = await el.executeJavaScript(EXTRACT_JS, true);
      if (!texts || !texts.length) { setTranslating(false); return; }
      const r = await fetch(`${API}/forage/translate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texts, target: 'ko' }),
      });
      if (!r.ok) throw new Error(`번역 실패 (${r.status})`);
      const d = await r.json();
      await el.executeJavaScript(replaceJs(d.translations || []), true);
      updateTab(activeTab.id, { translated: true });
    } catch (e: any) {
      flash(e?.message || '번역 중 오류가 발생했습니다.');
    } finally {
      setTranslating(false);
    }
  };

  // 페이지의 로그인 폼 감지 → 저장 계정 조회 → 단일 매칭이면 조용히 자동 채움(제출은 안 함).
  const detectAndAutofill = async () => {
    const el = activeWebview();
    if (!el || !hasPwVault()) return;
    try {
      const found = await el.executeJavaScript(DETECT_PW_JS, true);
      if (!found?.host) { setPwHasField(false); setPwAccounts([]); return; }
      setPwHasField(true);
      const accts = (await pwApi().foragePwListHost?.(found.origin)) || [];
      setPwAccounts(accts);
      if (accts.length === 1) {
        const cred = await pwApi().foragePwGet?.(found.origin, accts[0].username);
        if (cred) await el.executeJavaScript(fillPwJs(cred.username, cred.password), true);
      }
    } catch { /* 페이지가 막 바뀌는 중일 수 있음 — 무시 */ }
  };

  const fillCredential = async (username: string) => {
    const el = activeWebview();
    if (!el) return;
    const cred = await pwApi().foragePwGet?.(addr, username);
    if (cred) { await el.executeJavaScript(fillPwJs(cred.username, cred.password), true); flash('채웠어요'); }
    setPwMenuOpen(false);
  };

  const saveCurrentLogin = async () => {
    const el = activeWebview();
    if (!el) return;
    setPwMenuOpen(false);
    let data: any = null;
    try { data = await el.executeJavaScript(READ_PW_JS, true); } catch { /* */ }
    if (!data?.password) { flash('저장할 로그인 입력값이 없어요'); return; }
    const res = await pwApi().foragePwSave?.(data.origin, data.username || '', data.password);
    flash(res === true ? '이 로그인을 저장했어요' : '저장 실패');
    setPwAccounts((await pwApi().foragePwListHost?.(data.origin)) || []);
  };

  const importFromChrome = async () => {
    setPwMenuOpen(false);
    flash('크롬에서 가져오는 중…', 6000);
    const res = await pwApi().foragePwImportChrome?.();
    if (res && 'imported' in res) {
      flash(`크롬에서 ${res.imported}개 가져왔어요${res.total ? ` (총 ${res.total}개 중)` : ''}`, 3000);
    } else {
      // 실패 메시지는 자동으로 안 사라지게(ms=0) — 원인을 끝까지 읽을 수 있도록.
      flash(`가져오기 실패: ${(res as any)?.error || '알 수 없음'} — (탭하면 닫힘)`, 0);
    }
    setPwAccounts((await pwApi().foragePwListHost?.(addr)) || []);
  };

  // 브라우징 중에도 또 검색 — 검색홈으로 돌아갈 필요 없이, 슬림 검색바에서 바로.
  const searchAndShow = () => {
    if (!query.trim() && !att.hasAttachments) return;
    setMode('search');   // 결과를 보려면 검색홈으로(웹뷰는 mount 게이트로 자동 unmount)
    runSearch();
  };

  const runSearch = async () => {
    const q = query.trim();
    if ((!q && !att.hasAttachments) || searching) return;
    const message = att.prepareMessageContent(query);   // 텍스트파일 내용은 메시지에 인라인
    const images = att.prepareImageData();               // 이미지는 base64 로 동봉
    setSearching(true); setError(null); setAnswer(null); setDestinations([]);
    try {
      const r = await fetch(`${API}/forage/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, images }),
      });
      if (!r.ok) throw new Error(`검색 실패 (${r.status})`);
      const d = await r.json();
      const { text, destinations } = extractDestinations(d.response || '');
      setAnswer(text); setDestinations(destinations);
      att.clearAttachments();
    } catch (e: any) {
      setError(e?.message || '검색 중 오류가 발생했습니다.');
    } finally {
      setSearching(false);
    }
  };

  // 즐겨찾기 IBL 헬퍼 — 계기(🔖)와 같은 sites.json 을 공유(add/remove/list).
  const iblExec = async (code: string): Promise<any> => {
    const r = await fetch(`${API}/ibl/execute`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, project_id: '앱모드' }),
    });
    const d = await r.json();
    let res = (d && typeof d === 'object' && 'result' in d) ? (d as any).result : d;
    if (typeof res === 'string') { try { res = JSON.parse(res); } catch { /* keep */ } }
    return res;
  };

  const loadFavorites = async () => {
    try {
      const res = await iblExec('[limbs:launch]{action: "list"}');
      const items = res && Array.isArray(res.items) ? res.items : [];
      setFavorites(items.filter((s: any) => s?.url).map((s: any) => ({ name: s.name || s.url, url: s.url })));
    } catch { /* 즐겨찾기 없으면 조용히 비움 */ }
  };

  // 열릴 때마다 즐겨찾기를 당긴다(계기에서 편집한 게 즉시 반영).
  useEffect(() => { if (open) loadFavorites(); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  // 현재 페이지가 이미 즐겨찾기인가 — 끝 슬래시 무시하고 비교.
  const normUrl = (u: string) => (u || '').replace(/\/+$/, '').toLowerCase();
  const currentFav = favorites.find((f) => normUrl(f.url) === normUrl(addr));

  // IBL 문자열 파라미터 이스케이프(따옴표·개행 제거) — CalendarInstrument 와 같은 방식.
  const escq = (s: string) => (s || '').replace(/"/g, "'").replace(/[\r\n]+/g, ' ').trim();

  // 현재 브라우징 중인 페이지를 즐겨찾기에 담기/빼기(토글). 추가는 자동 augmentation.
  const toggleFavorite = async () => {
    const url = addr;
    if (!url || url === 'about:blank') return;
    try {
      if (currentFav) {
        await iblExec(`[limbs:launch]{action: "remove", name: "${escq(currentFav.name)}"}`);
        flash('즐겨찾기에서 뺐어요');
      } else {
        let title = '';
        try { title = activeWebview()?.getTitle?.() || ''; } catch { /* 페이지 전환 중 */ }
        let host = url; try { host = new URL(url).hostname; } catch { /* */ }
        const name = (escq(title || host).slice(0, 60)) || host;
        await iblExec(`[limbs:launch]{action: "add", name: "${name}", url: "${escq(url)}"}`);
        flash('즐겨찾기에 담았어요');
      }
      await loadFavorites();
    } catch { flash('즐겨찾기 처리 실패'); }
  };

  // 즐겨찾기 페이지에서 항목 제거 — 이름으로 삭제 후 목록 최신화.
  const removeFavorite = async (name: string) => {
    try {
      await iblExec(`[limbs:launch]{action: "remove", name: "${escq(name)}"}`);
      flash('즐겨찾기에서 뺐어요');
      await loadFavorites();
    } catch { flash('삭제 실패'); }
  };

  // Esc 로 닫기 — webview 가 상단 바를 가려 버튼이 안 먹는 상황의 안전판.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  // 활성 탭 로그인 폼 감지 — 탭 전환/로딩 완료/페이지 이동 시 다시 감지(이미 로드된 탭으로
  // 전환해도 자동 채움이 붙도록). 각 webview 이벤트는 자식(BrowserTabView)이 Tab 상태로 올린다.
  useEffect(() => {
    setPwMenuOpen(false);
    if (mode !== 'browse' || !activeId) { setPwHasField(false); setPwAccounts([]); return; }
    if (activeTab && !activeTab.loading) detectAndAutofill();
  }, [activeId, mode, activeTab?.loading, activeTab?.url]); // eslint-disable-line react-hooks/exhaustive-deps

  // 탭 전환 시 주소줄을 잠깐 보여준다(어디로 왔는지 확인) — 본문으로 내려가면 다시 숨는다.
  useEffect(() => { showBar(); }, [activeId]);

  return (
    <div
      className={`absolute inset-0 z-30 flex-col bg-white ${open ? 'flex' : 'hidden'}`}
    >
      {/* 탭 스트립 — 탭이 하나라도 있으면 항상. 클릭=전환, +=새 탭(검색홈), ×=닫기. */}
      {tabs.length > 0 && (
        <div className="shrink-0 flex items-stretch gap-1 px-2 pt-1.5 bg-stone-100 border-b border-stone-200 overflow-x-auto">
          {tabs.map((t) => (
            <div key={t.id}
              onClick={() => { setActiveId(t.id); setMode('browse'); }}
              className={`group flex items-center gap-1.5 pl-2 pr-1 py-1.5 rounded-t-lg cursor-pointer shrink-0 w-44 ${
                mode === 'browse' && t.id === activeId ? 'bg-white' : 'bg-stone-200/50 hover:bg-stone-200'
              }`}>
              {t.kind === 'favorites'
                ? <span className="w-4 h-4 shrink-0 text-sm leading-none flex items-center justify-center">⊞</span>
                : <TabFav url={t.url} />}
              <span className="text-xs text-stone-700 truncate flex-1">{t.loading ? '불러오는 중…' : (t.title || t.url)}</span>
              <button onClick={(e) => { e.stopPropagation(); closeTab(t.id); }} title="탭 닫기"
                className="w-4 h-4 rounded text-stone-400 hover:bg-stone-300 hover:text-stone-700 text-xs leading-none shrink-0 flex items-center justify-center">×</button>
            </div>
          ))}
          <button onClick={() => setMode('search')} title="새 탭"
            className={`shrink-0 px-2.5 py-1.5 rounded-t-lg text-lg leading-none text-stone-500 hover:bg-stone-200 ${mode === 'search' ? 'bg-white' : ''}`}>+</button>
        </div>
      )}

      {/* 상단 바 — 모드별로 다르다. 브라우즈에선 주소·검색줄이 자동 숨김(센서 띠로 되살림). */}
      {mode === 'browse' ? (
        barHidden ? (
          <div onMouseEnter={showBar} title="주소·검색줄 보기"
            className="shrink-0 h-3 flex items-center justify-center bg-stone-100 border-b border-stone-200 cursor-pointer hover:bg-stone-200 transition">
            <span className="text-[10px] leading-none text-stone-400 select-none">⌄</span>
          </div>
        ) : (
        <div onMouseEnter={showBar} onMouseLeave={scheduleHide} className="shrink-0 border-b border-stone-200 bg-stone-50">
          {/* 슬림 검색바 — 브라우징 중에도 항상 떠 있어, 처음 자리로 안 돌아와도 또 검색. 길게·얇게. */}
          <form onSubmit={(e) => { e.preventDefault(); searchAndShow(); }} className="flex items-center gap-2 px-3 pt-2 pb-1">
            <span className="text-stone-400 text-sm select-none">🔍</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); searchAndShow(); } }}
              className="flex-1 px-3 py-1 rounded-full border border-stone-200 bg-white text-sm text-stone-700 focus:outline-none focus:ring-2 focus:ring-stone-300"
            />
          </form>
          {/* 주소/네비 바 */}
          <div className="flex items-center gap-1.5 px-3 pb-2 pt-0.5">
            <button onClick={() => setMode('search')} className="px-3 py-1.5 rounded-lg text-sm text-stone-600 hover:bg-stone-200 whitespace-nowrap">＋ 새 탭</button>
            {activeTab?.kind === 'favorites' ? (
              <>
                <span className="px-3 py-1.5 text-sm text-stone-500">⊞ 즐겨찾기</span>
                <div className="flex-1" />
              </>
            ) : (
            <>
            <NavBtn onClick={() => activeWebview()?.goBack()} disabled={!canBack} label="‹" title="뒤로" />
            <NavBtn onClick={() => activeWebview()?.goForward()} disabled={!canFwd} label="›" title="앞으로" />
            <NavBtn onClick={() => activeWebview()?.reload()} label="⟳" title="새로고침" />
            <button
              onClick={toggleTranslation}
              disabled={translating}
              title={activeTab?.translated ? "원본 보기" : "한국어로 번역"}
              className={`px-2.5 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition flex items-center gap-1 disabled:opacity-50 ${
                activeTab?.translated
                  ? 'bg-blue-100 text-blue-700 hover:bg-blue-200 ring-1 ring-blue-300'
                  : 'text-stone-600 hover:bg-stone-200'
              }`}
            >
              <span>🌐</span>
              <span>{translating ? '번역 중…' : activeTab?.translated ? '원본' : '번역'}</span>
            </button>
            <button
              onClick={toggleFavorite}
              title={currentFav ? '즐겨찾기에서 빼기' : '이 페이지를 즐겨찾기에 추가'}
              className={`px-2.5 py-1.5 rounded-lg text-base leading-none whitespace-nowrap transition ${
                currentFav ? 'text-amber-500 hover:bg-amber-50' : 'text-stone-400 hover:bg-stone-200'
              }`}
            >
              {currentFav ? '★' : '☆'}
            </button>
            <div className="flex-1 px-3 py-1.5 rounded-lg border border-stone-200 bg-white text-sm text-stone-500 truncate">{addr}</div>
            {loading && <span className="text-xs text-stone-400 px-1 whitespace-nowrap">불러오는 중…</span>}

            {/* 비밀번호 채우기 — Electron 금고가 있을 때만. 로그인 폼이 감지되면 강조. */}
            {hasPwVault() && (
              <div className="relative">
                <button
                  onClick={() => setPwMenuOpen((v) => !v)}
                  title="비밀번호 채우기"
                  className={`px-2.5 py-1.5 rounded-lg text-sm whitespace-nowrap transition ${
                    pwHasField ? 'bg-amber-100 text-amber-700 hover:bg-amber-200' : 'text-stone-500 hover:bg-stone-200'
                  }`}
                >
                  🔑{pwAccounts.length > 0 ? ` ${pwAccounts.length}` : ''}
                </button>
                {pwMenuOpen && (
                  <div className="absolute right-0 top-full mt-1 z-50 w-60 rounded-xl border border-stone-200 bg-white shadow-lg py-1.5 text-sm">
                    {pwAccounts.length > 0 && (
                      <>
                        <div className="px-3 py-1 text-[11px] text-stone-400">저장된 계정으로 채우기</div>
                        {pwAccounts.map((a, i) => (
                          <button key={i} onClick={() => fillCredential(a.username)}
                            className="w-full text-left px-3 py-1.5 hover:bg-stone-50 text-stone-700 truncate">
                            {a.username || '(아이디 없음)'}
                          </button>
                        ))}
                        <div className="my-1 border-t border-stone-100" />
                      </>
                    )}
                    <button onClick={saveCurrentLogin}
                      className="w-full text-left px-3 py-1.5 hover:bg-stone-50 text-stone-700">
                      💾 이 로그인 저장
                    </button>
                    <button onClick={importFromChrome}
                      className="w-full text-left px-3 py-1.5 hover:bg-stone-50 text-stone-700">
                      ⬇️ 크롬에서 비밀번호 가져오기
                    </button>
                  </div>
                )}
              </div>
            )}
            </>
            )}

            <button onClick={onClose} className="px-3 py-1.5 rounded-lg text-sm text-stone-500 hover:bg-stone-200 whitespace-nowrap">✕ 닫기</button>
          </div>
          {pwToast && (
            <div onClick={() => setPwToast(null)}
              className="px-3 pb-1.5 -mt-0.5 text-xs text-stone-500 cursor-pointer break-all">{pwToast}</div>
          )}
        </div>
        )
      ) : (
        <div className="shrink-0 flex items-center justify-between px-4 py-2">
          <button onClick={openFavoritesTab} title="즐겨찾기 모아보기"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-stone-200 bg-white text-sm text-stone-600 hover:bg-stone-100 hover:border-stone-300 transition">
            <span className="text-base leading-none">⊞</span>
            <span>즐겨찾기</span>
          </button>
          <button onClick={onClose} className="px-3 py-1.5 rounded-lg text-sm text-stone-500 hover:bg-stone-100">✕ 닫기</button>
        </div>
      )}

      {/* 검색홈 — webview 와 공존(숨김)시켜 세션·페이지를 살려둔다 */}
      <div className={`flex-1 min-h-0 overflow-auto ${mode === 'search' ? 'block' : 'hidden'}`}>
        <div className={`max-w-2xl mx-auto px-6 ${answer || searching || error ? 'pt-8' : 'pt-[18vh]'}`}>
          {!answer && !searching && !error && (
            // 나중에 로고 이미지로 교체 가능. 지금은 워드마크.
            <h1 className="text-center text-4xl font-light tracking-tight text-stone-700 mb-6">indiebizOS</h1>
          )}

          <form onSubmit={(e) => { e.preventDefault(); runSearch(); }}>
            {/* 첨부 미리보기 */}
            {(att.attachedImages.length > 0 || att.attachedTextFiles.length > 0) && (
              <div className="flex flex-wrap gap-2 mb-2">
                {att.attachedImages.map((img, i) => (
                  <div key={`img${i}`} className="relative">
                    <img src={img.preview} alt="" className="w-14 h-14 object-cover rounded-lg border border-stone-200" />
                    <button type="button" onClick={() => att.removeImage(i)}
                      className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-stone-700 text-white text-[11px] leading-none flex items-center justify-center">×</button>
                  </div>
                ))}
                {att.attachedTextFiles.map((tf, i) => (
                  <div key={`tf${i}`} className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-stone-100 text-xs text-stone-600">
                    <span>📄 {tf.file.name}</span>
                    <button type="button" onClick={() => att.removeTextFile(i)} className="text-stone-400 hover:text-stone-600">×</button>
                  </div>
                ))}
              </div>
            )}

            <div className="relative flex items-center">
              <button type="button" onClick={() => att.fileInputRef.current?.click()} title="사진·파일 첨부"
                className="absolute left-2.5 w-8 h-8 rounded-lg text-stone-400 hover:text-stone-600 hover:bg-stone-100 flex items-center justify-center">📎</button>
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onPaste={att.handlePaste}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); runSearch(); } }}
                rows={1}
                autoFocus
                className="w-full resize-none pl-12 pr-20 py-3.5 rounded-2xl border border-stone-300 bg-white text-stone-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-stone-300 focus:border-stone-300"
              />
              <button type="submit" disabled={searching || (!query.trim() && !att.hasAttachments)}
                className="absolute right-2.5 px-4 py-1.5 rounded-xl bg-stone-800 text-white text-sm disabled:opacity-40 hover:bg-stone-700 transition">
                {searching ? '…' : '찾기'}
              </button>
            </div>
            <input ref={att.fileInputRef} type="file" multiple
              accept="image/*,.txt,.md,.json,.csv,.log,.py,.js,.ts,.html,.css"
              onChange={att.handleFileSelect} className="hidden" />
          </form>

          {error && <div className="mt-6 text-sm text-rose-500">{error}</div>}

          {searching && <div className="mt-8 text-center text-sm text-stone-400">포식 중… 가볼 만한 곳을 찾고 있어요</div>}

          {/* 목적지 카드 (MAP 마커 등) — 클릭하면 webview 진입 */}
          {destinations.length > 0 && (
            <div className="mt-6 space-y-2">
              {destinations.map((d, i) => (
                <button key={i} onClick={() => openTab(d.url)}
                  className="w-full text-left p-3 rounded-xl border border-stone-200 hover:border-stone-300 hover:bg-stone-50 transition">
                  <div className="text-sm font-medium text-stone-800">{d.label}</div>
                  {d.meta && <div className="text-xs text-stone-500 mt-0.5">{d.meta}</div>}
                  <div className="text-[11px] text-sky-600 mt-0.5 truncate">{d.url}</div>
                </button>
              ))}
            </div>
          )}

          {/* 에이전트 본문 — 인라인 링크는 클릭 시 webview 로 */}
          {answer && (
            <div className="mt-6 pb-12 prose prose-sm prose-stone max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ href, children }) => (
                    <a
                      href={href}
                      onClick={(e) => { e.preventDefault(); if (href) openTab(href); }}
                      className="text-sky-600 hover:underline cursor-pointer"
                    >
                      {children}
                    </a>
                  ),
                }}
              >
                {answer}
              </ReactMarkdown>
            </div>
          )}
        </div>
      </div>

      {/* 도로 — 탭별 크로미움 webview. 열려 있으면 전부 mount 유지(세션·페이지 보존), 활성 탭만 보임.
          검색홈(mode!=='browse')이면 스택 전체를 숨긴다. partition persist:forage 로 탭끼리 세션 공유. */}
      <div className={`flex-1 min-h-0 bg-stone-100 ${mode === 'browse' ? 'block' : 'hidden'}`}>
        {open && tabs.map((t) => (
          <div key={t.id} className="w-full h-full"
            style={{ display: mode === 'browse' && t.id === activeId ? 'block' : 'none' }}>
            {t.kind === 'favorites'
              ? <FavoritesPage favorites={favorites} onOpen={openTab} onRemove={removeFavorite} />
              : <BrowserTabView tab={t} onUpdate={updateTab} registerRef={registerRef} onOpenTab={openTab} />}
          </div>
        ))}
      </div>
    </div>
  );
}

// 탭 하나 = webview 하나. 자기 네비 이벤트를 부모 Tab 상태로 올리고, 팝업(target=_blank 등)은 새 탭으로.
// src 는 initialUrl 로 최초 1회만 로드 — 이후 이동은 goBack/reload 등 imperative 로만(재로드 튐 방지).
function BrowserTabView({ tab, onUpdate, registerRef, onOpenTab }: {
  tab: Tab;
  onUpdate: (id: string, patch: Partial<Tab>) => void;
  registerRef: (id: string, el: any) => void;
  onOpenTab: (url: string) => void;
}) {
  const ref = useRef<any>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    registerRef(tab.id, el);
    const sync = (e?: any) => {
      const u = e?.url || el.getURL?.();
      onUpdate(tab.id, {
        url: u || tab.url,
        title: el.getTitle?.() || u || tab.url,
        canBack: !!el.canGoBack?.(),
        canFwd: !!el.canGoForward?.(),
      });
    };
    const onStart = () => onUpdate(tab.id, { loading: true, translated: false });
    const onStop = () => { onUpdate(tab.id, { loading: false }); sync(); };
    const onTitle = (e: any) => onUpdate(tab.id, { title: e?.title || el.getTitle?.() || tab.url });
    const onNew = (e: any) => { if (e?.url) onOpenTab(e.url); };  // target=_blank / window.open → 새 탭
    el.addEventListener('did-navigate', sync);
    el.addEventListener('did-navigate-in-page', sync);
    el.addEventListener('did-start-loading', onStart);
    el.addEventListener('did-stop-loading', onStop);
    el.addEventListener('page-title-updated', onTitle);
    el.addEventListener('new-window', onNew);
    return () => {
      el.removeEventListener('did-navigate', sync);
      el.removeEventListener('did-navigate-in-page', sync);
      el.removeEventListener('did-start-loading', onStart);
      el.removeEventListener('did-stop-loading', onStop);
      el.removeEventListener('page-title-updated', onTitle);
      el.removeEventListener('new-window', onNew);
    };
  }, [tab.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <WebView ref={ref} src={tab.initialUrl} partition="persist:forage" allowpopups="true"
      style={{ width: '100%', height: '100%', border: 'none' }} />
  );
}

// 즐겨찾기 바둑판 페이지 — 스위치로 새 탭에서 열림. 타일 클릭=새 탭으로 방문, × =즐겨찾기에서 제거.
function FavoritesPage({ favorites, onOpen, onRemove }: {
  favorites: { name: string; url: string }[];
  onOpen: (url: string) => void;
  onRemove: (name: string) => void;
}) {
  return (
    <div className="w-full h-full overflow-auto bg-white">
      <div className="max-w-4xl mx-auto px-8 py-10">
        <h2 className="text-2xl font-light tracking-tight text-stone-700 mb-8 text-center">즐겨찾기</h2>
        {favorites.length === 0 ? (
          <div className="text-center text-sm text-stone-400 mt-16">
            아직 즐겨찾기가 없어요. 사이트를 방문해 주소창의 ☆ 를 눌러 담아 보세요.
          </div>
        ) : (
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-x-4 gap-y-7">
            {favorites.map((f, i) => (
              <div key={i} className="group relative flex flex-col items-center">
                <button onClick={() => onRemove(f.name)} title="즐겨찾기에서 제거"
                  className="absolute -top-1 -right-1 z-10 w-5 h-5 rounded-full bg-stone-200 text-stone-500 hover:bg-red-500 hover:text-white text-[11px] leading-none flex items-center justify-center transition">×</button>
                <button onClick={() => onOpen(f.url)} title={f.url}
                  className="flex flex-col items-center gap-2 p-2 rounded-2xl hover:bg-stone-100 transition w-full">
                  <FavIcon url={f.url} name={f.name} />
                  <span className="text-xs leading-tight text-stone-600 text-center line-clamp-2 w-full">{f.name}</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// 탭 파비콘(작게). 실패/무효 URL 은 점(◦)으로.
function TabFav({ url }: { url: string }) {
  const [err, setErr] = useState(false);
  let host = '';
  try { host = new URL(url).hostname; } catch { /* 잘못된 URL */ }
  if (err || !host) return <span className="w-4 h-4 shrink-0 text-stone-400 text-[10px] flex items-center justify-center">◦</span>;
  return <img src={`https://www.google.com/s2/favicons?sz=32&domain=${host}`} alt="" onError={() => setErr(true)}
    className="w-4 h-4 shrink-0 rounded-sm" />;
}

// 즐겨찾기 타일 아이콘 — 사이트 파비콘, 실패 시 첫 글자 배지로 폴백.
function FavIcon({ url, name }: { url: string; name: string }) {
  const [err, setErr] = useState(false);
  let host = '';
  try { host = new URL(url).hostname; } catch { /* 잘못된 URL */ }
  if (err || !host) {
    const initial = (name || host || '?').trim().charAt(0).toUpperCase();
    return (
      <div className="w-12 h-12 rounded-2xl bg-stone-200 text-stone-500 flex items-center justify-center text-lg font-medium">
        {initial || '?'}
      </div>
    );
  }
  return (
    <img
      src={`https://www.google.com/s2/favicons?sz=64&domain=${host}`}
      alt=""
      onError={() => setErr(true)}
      className="w-12 h-12 rounded-2xl bg-white border border-stone-100 object-contain p-2"
    />
  );
}

function NavBtn({ onClick, disabled, label, title }: { onClick: () => void; disabled?: boolean; label: string; title: string }) {
  return (
    <button onClick={onClick} disabled={disabled} title={title}
      className={`w-8 h-8 rounded-lg text-base flex items-center justify-center transition ${
        disabled ? 'text-stone-300 cursor-default' : 'text-stone-600 hover:bg-stone-200'
      }`}>
      {label}
    </button>
  );
}
