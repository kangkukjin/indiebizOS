import { BACKEND_ORIGIN } from './backend-origin';
export { sessionArgs } from './api-documents';
export type { Session, Document } from './api-documents';
import type { Session, Document } from './api-documents';
/* capabilities.engine(2026-10-07): grid=브라우저 격자(기본) · office=사무 엔진(ONLYOFFICE, 격자가 못 그리는 부품이 있을 때) · none=열람만 */
export type SheetCapabilities = { edit_native: boolean; reason: string; engine: 'grid' | 'office' | 'none'; grid?: boolean; office?: boolean;
  office_available?: boolean; grid_blockers?: string[]; empty?: boolean; save?: boolean; blocked_parts?: string[] };
export type SheetDetail = { document: Document; session: Session | null; capabilities: SheetCapabilities; workbook: { sheets?: { sheet_id: string; name: string }[] } };
export type SheetSnapshot = { id: string; session_revision: number; calc_status: string; unsaved: boolean };
export async function sheetRequest<T>(path: string, method = 'GET', body?: unknown, keepalive = false): Promise<T> {
  const response = await fetch(`${BACKEND_ORIGIN}/spreadsheets${path}`, { method, credentials: 'include', headers: { 'Content-Type': 'application/json' }, keepalive, body: body === undefined ? undefined : JSON.stringify(body) });
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : `스프레드시트 요청 실패 (${response.status})`);
  return value as T;
}
export async function sheetUpload(file: File): Promise<SheetDetail> {
  const response = await fetch(`${BACKEND_ORIGIN}/spreadsheets/import?filename=${encodeURIComponent(file.name)}`, { method: 'POST', credentials: 'include', body: file });
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : '파일 가져오기에 실패했습니다');
  return value as SheetDetail;
}
export function sheetCommand<T>(id: string, op: string, args: Record<string, unknown> = {}): Promise<T> {
  return sheetRequest<T>(`/${encodeURIComponent(id)}/${op}`, 'POST', { args });
}
/** 작성 세션을 놓는다(창을 떠날 때) — 초안이 남아 있으면 서버가 거절하고 세션은 그대로 남는다. 창이 닫히는 중에도 나가도록 keepalive. */
export function releaseSheetSession(id: string, session: Session): Promise<void> {
  const args = { session_id: session.id, client_id: session.client_id, epoch: session.engine_epoch, expected: session.session_revision };
  return sheetRequest(`/${encodeURIComponent(id)}/close`, 'POST', { args }, true).then(() => undefined, () => undefined);
}
