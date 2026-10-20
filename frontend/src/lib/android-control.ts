import { iblExecuteApp } from './instrument';

export type AndroidTask = Record<string, unknown>;
const record = (v: unknown): AndroidTask => v && typeof v === 'object' && !Array.isArray(v) ? v as AndroidTask : {};
const pending = new Map<string, AndroidTask>();
const listeners = new Set<() => void>();
export const subscribeAndroidTasks = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export const pendingAndroidTask = (target: string) => pending.get(target);

function remember(task: AndroidTask) {
  if (typeof task.target !== 'string') return;
  if (['pending', 'unknown'].includes(String(task.status))) pending.set(task.target, task);
  else pending.delete(task.target);
  listeners.forEach(listener => listener());
}

export function androidCommandCode(target: string, request: AndroidTask): string {
  if (!target.trim()) throw new Error('제어할 폰을 선택해 주세요.');
  return '#!ibl edition=2\nreturn [fn:Android제어]' + JSON.stringify({ 대상: target, 요청: request });
}

export function androidState(value: unknown): AndroidTask {
  const task = record(value), state = record(task.result);
  if (task.status !== 'completed') {
    throw new Error(String(record(task.failure).message || '작업이 진행 중입니다.') +
      (task.task_ref ? ' 기존 작업 확인으로 결과를 조회하세요.' : ' 상태를 확인하세요. 변경을 다시 보내지 마세요.'));
  }
  if (state.success !== true || state.protocol !== 'android-control/1' || state.platform !== 'android') {
    throw new Error('Android 제어 결과를 확인하지 못했습니다.');
  }
  return state;
}

export async function executeAndroid(target: string, code: string): Promise<unknown> {
  if (pending.has(target)) throw new Error('미확인 작업이 있습니다. 기존 작업 확인을 먼저 눌러 주세요.');
  let value: unknown;
  try { value = await iblExecuteApp(code, { allowIncomplete: true }); }
  catch (error) {
    remember({ target, status: 'unknown', task_ref: null, failure: {
      message: '응답을 받지 못했습니다. 실행 기록 또는 현재 상태를 확인하세요.',
    } });
    throw error;
  }
  const task = record(value);
  if (task.target !== target) throw new Error('요청과 다른 폰의 응답입니다.');
  remember(task);
  return value;
}

export async function confirmAndroid(task: AndroidTask): Promise<AndroidTask> {
  const value = await iblExecuteApp('#!ibl edition=2\nreturn [fn:Android제어확인]' +
    JSON.stringify({ 작업: task, 대기: 60 }), { allowIncomplete: true });
  const outcome = record(value);
  remember(outcome);
  return androidState(outcome);
}

// Clearing a UI notice never replays the request. Observation remains available.
export function dismissAndroidTask(target: string) {
  pending.delete(target);
  listeners.forEach(listener => listener());
}
