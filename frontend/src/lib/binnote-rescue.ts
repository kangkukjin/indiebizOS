/**
 * 빈노트 은퇴(2026-10-05) 뒷정리 — 빈노트는 쓰던 글을 브라우저(localStorage)에만 임시저장했다.
 * 문서 앱으로 흡수되면서 그 초안을 읽을 화면이 없어지므로, 저장된 파일과 다를 때 한 번
 * 문서함(outputs/binnote)에 '_미저장초안' 파일로 건져 놓고 키를 지운다. 같으면 키만 지운다.
 * 건지기에 실패하면 키를 남겨 다음 실행에서 다시 시도한다.
 */
import { iblExecuteApp } from './instrument';

const KEYS = { draft: 'binnote.draft', name: 'binnote.name', cwd: 'binnote.cwd' };
const ROOT = 'outputs/binnote';

export async function rescueBinnoteDraft(): Promise<void> {
  let draft = '', name = '', cwd = '';
  try {
    draft = localStorage.getItem(KEYS.draft) || '';
    name = (localStorage.getItem(KEYS.name) || '제목없음.md').replace(/[\\/:*?"<>|]/g, '');
    cwd = localStorage.getItem(KEYS.cwd) || '';
  } catch { return; }
  const clear = () => { try { Object.values(KEYS).forEach((k) => localStorage.removeItem(k)); } catch { /* 무해 */ } };
  if (!draft.trim()) { clear(); return; }
  const dir = cwd ? `${ROOT}/${cwd}` : ROOT;
  try {
    const r = await iblExecuteApp(`[self:read]{path: ${JSON.stringify(`${dir}/${name}`)}}`);
    const o = r && typeof r === 'object' ? (r as { result?: unknown; text?: unknown }) : null;
    const saved = typeof r === 'string' ? r : String(o?.result ?? o?.text ?? '');
    if (saved === draft) { clear(); return; }
  } catch { /* 저장본이 없으면 아래에서 건진다 */ }
  const now = new Date(), two = (n: number) => String(n).padStart(2, '0');
  const stamp = `${now.getFullYear()}${two(now.getMonth() + 1)}${two(now.getDate())}-${two(now.getHours())}${two(now.getMinutes())}`;
  const base = name.replace(/\.(md|txt)$/i, '') || '제목없음';
  try {
    const w = await iblExecuteApp(`[self:write]{path: ${JSON.stringify(`${dir}/${base}_미저장초안_${stamp}.md`)}, content: ${JSON.stringify(draft)}}`);
    if (w && typeof w === 'object' && (w as { success?: boolean }).success) clear();
  } catch { /* 다음 실행에서 다시 */ }
}
