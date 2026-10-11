import { api } from '../../lib/api';

export const post = <T>(path: string, body: unknown) => api.request<T>(path, { method: 'POST', body: JSON.stringify(body) });
export const newId = () => crypto.randomUUID().replaceAll('-', '');
export const bytesFrom64 = (data: string) => Uint8Array.from(atob(data), c => c.charCodeAt(0));
export function bytesTo64(data: Uint8Array) {
  let s = '';
  for (let i = 0; i < data.length; i += 8192) s += String.fromCharCode(...data.subarray(i, i + 8192));
  return btoa(s);
}
export const message = (e: unknown) => e instanceof Error ? e.message : String(e);
export type Task = { id: string; state: string; created: number; summary: { op?: string; cmd?: string; path?: string }; result: Record<string, unknown> | null };
export type History = { tasks: Task[]; events: { cursor: number; kind: string; payload: { text?: string; reason?: string } }[]; cursor: number };
export async function run(target: string, command: Record<string, unknown>, signal: AbortSignal) {
  signal.throwIfAborted();
  const receipt = await post<{ job_id: string }>('/remote-pcs/command', { target, command, request_id: newId() });
  const until = Date.now() + 300000;
  while (!signal.aborted && Date.now() < until) {
    const history = await api.request<History>(`/remote-pcs/history?job=${receipt.job_id}`, { signal });
    const task = history.tasks[0];
    if (task?.result) {
      if (task.state !== 'succeeded' || task.result.error) throw new Error(String(task.result.error || task.state));
      return task.result;
    }
    if (task && ['unknown', 'expired', 'cancelled', 'failed'].includes(task.state)) throw new Error(task.state);
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error(`조회 대기가 끝났습니다. 작업 목록에서 상태를 확인하세요. (${receipt.job_id})`);
}
