/**
 * grimoire-relay — 독립 창으로 뜬 IBL 사전(마법책)과 대화창 사이의 선택 전달.
 *
 * Electron 에서 사전은 자기 창(`#/grimoire`)에 뜬다. 거기서 고른 낱말은 그 사전을 연 대화창의
 * 입력 칩으로 가야 한다. 창 사이 통로는 localStorage + `storage` 이벤트(같은 origin 의 다른 창에서만
 * 발화 — 런처→시스템 AI 창의 분석 요청 전달과 같은 길).
 *
 *  - 대화창이 사전을 열 때 `claimGrimoireOwner(token)` 으로 "마지막으로 연 대화창" 을 적는다.
 *    사전 창은 하나뿐이므로 마지막으로 연 창이 주인이다.
 *  - 사전 창은 `publishGrimoireSelection(actionId)` 로 {actionId, owner, ts} 를 쓴다(ts 로 매번 다른 값 → 이벤트 보장).
 *  - 대화창은 `onGrimoireSelection(token, cb)` 로 자기 token 앞으로 온 선택만 받는다.
 */

export const GRIMOIRE_OWNER_KEY = 'indiebiz_grimoire_owner';
export const GRIMOIRE_SELECT_KEY = 'indiebiz_grimoire_select';

export interface GrimoireSelection { actionId: string; owner: string | null; ts: number }

export function newGrimoireToken(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export function claimGrimoireOwner(token: string): void {
  try { localStorage.setItem(GRIMOIRE_OWNER_KEY, JSON.stringify({ token, ts: Date.now() })); } catch { /* 저장소 불가 — 선택 전달만 못 한다 */ }
}

export function currentGrimoireOwner(): string | null {
  try {
    const raw = localStorage.getItem(GRIMOIRE_OWNER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { token?: unknown };
    return typeof parsed?.token === 'string' ? parsed.token : null;
  } catch { return null; }
}

export function publishGrimoireSelection(actionId: string): GrimoireSelection {
  const sel: GrimoireSelection = { actionId, owner: currentGrimoireOwner(), ts: Date.now() };
  try { localStorage.setItem(GRIMOIRE_SELECT_KEY, JSON.stringify(sel)); } catch { /* noop */ }
  return sel;
}

export function parseGrimoireSelection(raw: string | null): GrimoireSelection | null {
  if (!raw) return null;
  try {
    const p = JSON.parse(raw) as Partial<GrimoireSelection>;
    if (typeof p?.actionId !== 'string' || !p.actionId) return null;
    return { actionId: p.actionId, owner: typeof p.owner === 'string' ? p.owner : null, ts: Number(p.ts) || 0 };
  } catch { return null; }
}

/** 이 대화창(token) 앞으로 온 선택을 받는다. 반환값은 해제 함수. */
export function onGrimoireSelection(token: string, cb: (actionId: string) => void): () => void {
  const onStorage = (e: StorageEvent) => {
    if (e.key !== GRIMOIRE_SELECT_KEY) return;
    const sel = parseGrimoireSelection(e.newValue);
    if (sel && sel.owner === token) cb(sel.actionId);
  };
  window.addEventListener('storage', onStorage);
  return () => window.removeEventListener('storage', onStorage);
}
