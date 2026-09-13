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

export function openGuides() {
  openPage('/guides', window.electron?.openToolWindow?.bind(window.electron, 'guides'));
}

export function openExternalLink(href: string) {
  let url: URL;
  try { url = new URL(href, window.location.href); } catch { return; }
  if (!['http:', 'https:', 'mailto:', 'obsidian:'].includes(url.protocol)) return;
  if (window.electron?.openExternal) window.electron.openExternal(url.href);
  else window.open(url.href, '_blank', 'noopener');
}

export function openResultImage(path: string) {
  if (window.electron?.openExternal) window.electron.openExternal(`file://${path}`);
  else window.open(`${BACKEND_ORIGIN}/image?path=${encodeURIComponent(path)}`, '_blank', 'noopener');
}
