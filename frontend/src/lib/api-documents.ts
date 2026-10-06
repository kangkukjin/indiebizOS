import { BACKEND_ORIGIN } from './backend-origin';

export type Document = { id: string; title: string; source_uri: string; source_format: string; source_sha256: string; revision_id: string; encoding: string | null };
export type Session = { id: string; client_id: string; engine_epoch: string; session_revision: number; state: string; blob: string };
export type Detail = { document: Document; session: Session | null; text?: string; capabilities: { edit_native: boolean; save: boolean; export_copy: boolean; reason: string; engine: string } };
export type Snapshot = { id: string; session_revision: number; blob: string };
export type Proposal = { id: string; snapshot_id: string };
/** 캔버스에서 미리보기를 낼 수 있는 원문 형식 */
export const PREVIEWABLE = ['md', 'markdown', 'html', 'htm'];

export async function documentRequest<T>(path: string, method = 'GET', body?: unknown, keepalive = false): Promise<T> {
  const response = await fetch(`${BACKEND_ORIGIN}/documents${path}`, {
    method, credentials: 'include', headers: { 'Content-Type': 'application/json' }, keepalive,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : `문서 요청 실패 (${response.status})`);
  return value as T;
}

export function documentCommand<T>(id: string, operation: string, args: Record<string, unknown> = {}): Promise<T> {
  return documentRequest<T>(`/${encodeURIComponent(id)}/${operation}`, 'POST', { args });
}

export function sessionArgs(session: Session) {
  return { session_id: session.id, client_id: session.client_id, epoch: session.engine_epoch, expected: session.session_revision };
}

/** 작성 세션을 놓는다(창을 떠날 때) — 초안이 남아 있으면 서버가 거절하고 세션은 그대로 남는다. 창이 닫히는 중에도 나가도록 keepalive. */
export function releaseSession(id: string, session: Session): Promise<void> {
  return documentRequest(`/${encodeURIComponent(id)}/close`, 'POST', { args: sessionArgs(session) }, true).then(() => undefined, () => undefined);
}
