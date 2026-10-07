import { BACKEND_ORIGIN } from './backend-origin';

/** 네이티브 창이 없는 웹에서는 같은 창의 라우트로 이동한다. 브라우저 뒤로가기로 돌아온다. */
function openPage(route: string, nativeOpen?: () => unknown) {
  if (nativeOpen) {
    nativeOpen();
    return;
  }
  window.location.hash = route;
}

export function openSystemAI() {
  openPage('/system-ai', window.electron?.openSystemAIWindow);
}

export function openProject(id: string, name: string) {
  openPage(`/project/${encodeURIComponent(id)}`,
    window.electron?.openProjectWindow?.bind(window.electron, id, name));
}

export function openPhoto(path: string | null = null) {
  openPage('/photo' + (path ? `?path=${encodeURIComponent(path)}` : ''),
    window.electron?.openPhotoManagerWindow?.bind(window.electron, path));
}

export function openPCManager(path: string | null = null) {
  openPage('/pcmanager' + (path ? `?path=${encodeURIComponent(path)}` : ''),
    window.electron?.openPCManagerWindow?.bind(window.electron, path));
}

export function openLecture(id: string | null = null) {
  openPage('/lecture-workspace' + (id ? `?lecture_id=${encodeURIComponent(id)}` : ''),
    window.electron?.openLectureWorkspaceWindow?.bind(window.electron, id));
}

/** 안경 메뉴 도구 창 — 런처 안 모달이 아니라 독립 창(크기 조절). 웹 표면은 같은 창의 라우트. */
export function openPromptComposition() {
  openPage('/prompt-composition', window.electron?.openToolWindow?.bind(window.electron, 'prompt-composition'));
}


export function openDocuments() {
  openPage('/documents', window.electron?.openToolWindow?.bind(window.electron, 'documents'));
}

export function openCoding() {
  openPage('/coding', window.electron?.openToolWindow?.bind(window.electron, 'coding'));
}

export function openGuides() {
  openPage('/guides', window.electron?.openToolWindow?.bind(window.electron, 'guides'));
}

export function openExternalUsers() {
  openPage('/external-users', window.electron?.openToolWindow?.bind(window.electron, 'external-users'));
}

export function openVocabulary(folderId = 'desktop') {
  openPage(`/vocabulary/${encodeURIComponent(folderId)}`,
    window.electron?.openToolWindow?.bind(window.electron, 'vocabulary', folderId));
}

/** 링크 href 의 목적지 분류 — 순수 함수(openExternalLink 가 쓴다).
 *
 *  AI 답변의 링크는 셋 중 하나다: 웹 URL · **파일시스템 경로**(`/Users/…/memory.md`, `file://…`,
 *  `C:\\…`) · 스킴 없는 상대경로(`ibl.md`). 예전엔 href 를 `new URL(href, window.location.href)`
 *  로 창 주소에 붙여 해석해서 `/Users/…` 가 dev 서버 `http://localhost:5173/Users/…` 가 됐고,
 *  Vite SPA 폴백이 그 주소에 런처 index.html 을 돌려줘 브라우저에 엉뚱한 런처가 떴다
 *  (프로덕션 file:// 창에선 `file:` 스킴으로 조용히 무시 — 클릭해도 아무 일 없음. 2026-10-07 실측).
 *  경로는 경로로, URL 은 URL 로 — 창 주소에 붙이는 해석은 하지 않는다. */
export type LinkTarget =
  | { kind: 'web'; url: string }     // http(s)·mailto·obsidian 등 허용 스킴의 절대 URL
  | { kind: 'local'; path: string }  // 이 컴퓨터의 파일/폴더 절대경로(디코딩됨)
  | { kind: 'none' };                // 열 수 없음(상대경로·미허용 스킴·빈 값)

const WEB_PROTOCOLS = ['http:', 'https:', 'mailto:', 'obsidian:'];
// `www.iros.go.kr` 처럼 스킴 없는 도메인꼴 — ForageBrowser 주소창과 같은 보정(https 추정).
const DOMAIN_LIKE = /^[\w-]+(\.[\w-]+)+(:\d+)?([/?#]\S*)?$/;
// 코드 참조꼴 `…/model_resolver.py:349` 또는 `:349:12` 의 꼬리 — 파일을 열 땐 떼어낸다.
const LINE_SUFFIX = /:\d+(:\d+)?$/;

export function classifyLinkTarget(href: string): LinkTarget {
  const raw = (href || '').trim();
  if (!raw) return { kind: 'none' };

  if (/^file:\/\//i.test(raw)) {
    try {
      const u = new URL(raw);
      const path = decodeURIComponent(u.pathname);
      return path ? { kind: 'local', path: path.replace(LINE_SUFFIX, '') } : { kind: 'none' };
    } catch { return { kind: 'none' }; }
  }
  // POSIX 절대경로(`//host` 꼴 제외) · 윈도우 드라이브 경로
  if ((raw.startsWith('/') && !raw.startsWith('//')) || /^[A-Za-z]:[\\/]/.test(raw)) {
    let path = raw.replace(LINE_SUFFIX, '');
    try { path = decodeURIComponent(path); } catch { /* 이미 날 경로 */ }
    return { kind: 'local', path };
  }
  try {
    const u = new URL(raw);  // 절대 URL 만 — 상대 href 는 여기서 throw
    return WEB_PROTOCOLS.includes(u.protocol) ? { kind: 'web', url: u.href } : { kind: 'none' };
  } catch { /* 스킴 없음 */ }
  if (DOMAIN_LIKE.test(raw) && !/^[\w-]+\.(md|txt|py|ts|tsx|js|json|yaml|yml|csv|html|pdf)$/i.test(raw)) {
    return { kind: 'web', url: `https://${raw}` };
  }
  return { kind: 'none' };
}

/** 절대경로 → file URL. 윈도우 `C:\\a\\b` 는 `file:///C:/a/b`(드라이브 콜론은 살린다). */
export function toFileUrl(path: string): string {
  const posix = path.replace(/\\/g, '/');
  const rooted = /^[A-Za-z]:\//.test(posix) ? '/' + posix : posix;
  return 'file://' + rooted.split('/').map((seg) => encodeURIComponent(seg).replace(/%3A/g, ':')).join('/');
}

/** 로컬 경로 → 기본 앱으로. Electron 은 shell.openExternal(file URL) — openResultImage 와 같은 길.
 *  웹 표면(원격 런처)엔 이 컴퓨터의 파일이 없으니 백엔드 산출물 서빙(/launcher/file, BASE_PATH 하위만)으로 받는다. */
function openLocalPath(path: string) {
  if (window.electron?.openExternal) {
    window.electron.openExternal(toFileUrl(path));
    return;
  }
  window.open(`${BACKEND_ORIGIN}/launcher/file?path=${encodeURIComponent(path)}`, '_blank', 'noopener');
}

export function openExternalLink(href: string) {
  const target = classifyLinkTarget(href);
  if (target.kind === 'local') { openLocalPath(target.path); return; }
  if (target.kind !== 'web') return;
  if (window.electron?.openExternal) window.electron.openExternal(target.url);
  else window.open(target.url, '_blank', 'noopener');
}

export function openResultImage(path: string) {
  if (window.electron?.openExternal) window.electron.openExternal(`file://${path}`);
  else window.open(`${BACKEND_ORIGIN}/image?path=${encodeURIComponent(path)}`, '_blank', 'noopener');
}
