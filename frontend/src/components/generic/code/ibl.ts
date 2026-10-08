/* 코드 엔진이 부르는 IBL 문장 — 전부 기존 낱말([self:workspace]·[others:delegate]·[self:task]). 선언이 아니라 엔진의 고정 문장
 * (문서 엔진이 /documents 엔진 I/O 를 부르듯, 코드 엔진은 작업 공간 낱말을 판본 2 봉투로 부른다). 새 낱말 0.
 * docs/CODING_APP_ON_IBL_PLAN_2026_10_07.md §3-2 */
import type { AppMode, Json } from '../manifest';
import { actionRequest, runIBL } from '../manifest';
import { iblFailure } from '../../../lib/instrument';
import { BACKEND_ORIGIN } from '../../../lib/backend-origin';

export const GOAL_NAME = '목표.md';

export type ProjectDetail = {
  resource: string; name: string; path: string; goal_path: string; goal_exists: boolean; icon: string; summary: string;
  run_command: string; run_url: string; log: string; head: string; dirty: boolean; changed: string[];
  active_task: TaskRef | null; run: RunRecord | null;
};
export type TaskRef = { kind: string; task_id: string; owner?: string };
export type TaskView = { state: string; terminal: boolean; result?: unknown; failure?: string | null; progress?: Json | null };
export type FileItem = { path: string; size: number; changed: string };
export type FileText = { path: string; text: string; fingerprint: string; binary: boolean; lines: number };
export type Version = { id: string; short: string; created_at: number; label: string };
export type RunRecord = { id: string; command: string; state: string; exit_code: number | null; started_at: number; finished_at: number | null; serve: boolean; stdin?: boolean };

const T = {
  detail: '[self:workspace]{op: "read", resource: $resource, selector: {project: true}}',
  files: '[self:workspace]{op: "read", resource: $resource, selector: {files: true}}',
  file: '[self:workspace]{op: "read", resource: $resource, selector: {path: $path}}',
  propose: '[self:workspace]{op: "propose", resource: $resource, selector: {path: $path}, replacement: $content}',
  apply: '[self:workspace]{op: "apply", resource: $resource, proposal: $proposal}',
  save: '[self:workspace]{op: "save", resource: $resource, message: $message}',
  versions: '[self:workspace]{op: "versions", resource: $resource}',
  restore: '[self:workspace]{op: "restore", resource: $resource, revision: $revision}',
  restoreFile: '[self:workspace]{op: "restore", resource: $resource, revision: $revision, path: $path}',
  delegate: '[others:delegate]{scope: "system", role: "coding", mode: "async", message: $message, context: {project: $path, resource: $resource, goal: $goal}}',
  status: '[self:task]{op: "status", ref: $ref}',
  cancel: '[self:task]{op: "cancel", ref: $ref}',
  unregister: '[self:workspace]{op: "close", resource: $resource, unregister: true}',
};

async function call(block: AppMode | undefined, template: string, inputs: Record<string, unknown>): Promise<Json> {
  const r = await runIBL(actionRequest(block, template, inputs));
  const bad = iblFailure(r);
  if (bad) throw new Error(bad);
  return r;
}

export function codeIBL(block: AppMode | undefined, resource: string) {
  const c = (t: string, inputs: Record<string, unknown> = {}) => call(block, t, { resource, ...inputs });
  return {
    detail: () => c(T.detail) as Promise<Json & ProjectDetail>,
    files: async () => ((await c(T.files)).items as FileItem[]) || [],
    file: (path: string) => c(T.file, { path }) as Promise<Json & FileText>,
    /** 파일 본문을 바꾸고(제안→적용) 기록까지 — 사람의 직접 편집도 AI 코딩과 같은 길. */
    write: async (path: string, content: string, message: string) => {
      const p = await c(T.propose, { path, content });
      await c(T.apply, { proposal: p.proposal });
      return c(T.save, { message });
    },
    save: (message: string) => c(T.save, { message }),
    versions: async () => ((await c(T.versions)).items as Version[]) || [],
    restore: (revision: string, path?: string) => (path ? c(T.restoreFile, { revision, path }) : c(T.restore, { revision })),
    delegate: (path: string, goal: string, message: string) => c(T.delegate, { path, goal, message }),
    status: (ref: TaskRef) => c(T.status, { ref }) as Promise<Json & TaskView>,
    cancel: (ref: TaskRef) => c(T.cancel, { ref }),
    unregister: () => c(T.unregister),
  };
}

/* 실행 탭의 엔진 I/O — 프로젝트 명령의 샌드박스 프로세스(시작·출력·입력·중지). 선언이 부르지 않는 길. */
async function codingRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const r = await fetch(`${BACKEND_ORIGIN}/coding${path}`, {
    method, credentials: 'include', headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const v = await r.json();
  if (!r.ok) throw new Error(typeof v.detail === 'string' ? v.detail : `실행 요청 실패 (${r.status})`);
  return v as T;
}
export const runIO = {
  start: (resource: string, command: string, serve: boolean) =>
    codingRequest<{ task_ref: TaskRef; run: RunRecord }>(`/projects/${encodeURIComponent(resource)}/run`, 'POST', { command, serve }),
  latest: (resource: string) => codingRequest<{ run: RunRecord | null }>(`/projects/${encodeURIComponent(resource)}/runs`),
  output: (runId: string, offset: number) => codingRequest<{ run: RunRecord; text: string; offset: number }>(`/runs/${encodeURIComponent(runId)}?offset=${offset}`),
  stop: (runId: string) => codingRequest<RunRecord>(`/runs/${encodeURIComponent(runId)}/stop`, 'POST'),
  input: (runId: string, text: string) => codingRequest<{ accepted: boolean }>(`/runs/${encodeURIComponent(runId)}/input`, 'POST', { text }),
};

/** 실행 에이전트에게 보내는 코딩 위임문 — 목표 문서가 지시이고, 폴더 밖은 손대지 않으며, 끝나면 진행 기록 한 줄. */
export function delegationMessage(d: ProjectDetail): string {
  return [
    `코딩 프로젝트 「${d.name}」 을(를) 목표 문서대로 구현해라.`,
    `프로젝트 폴더: ${d.path}`,
    `먼저 ${d.goal_path} 를 읽어라 — 그 문서가 요구사항이다. 파일은 이 폴더 안에서만 만들고 고친다(절대 경로로 쓴다). 필요한 명령·테스트는 그 폴더에서 돌려라.`,
    `끝나면 목표 문서의 "## 진행 기록" 절 맨 위에 "YYYY-MM-DD HH:MM AI — 무엇을 했고 무엇이 남았는지" 한 줄을 덧붙이고, "## 실행 방법" 절이 비어 있거나 "(정해지지 않음)" 이면 실행 명령(백틱)과 URL(있으면)을 적어라.`,
    `커밋·git 조작은 하지 마라(앱이 기록한다). 폴더 밖 파일·시스템 설정은 건드리지 마라.`,
  ].join('\n');
}

export function elapsed(since: number): string {
  const s = Math.max(0, Math.round((Date.now() - since) / 1000));
  return s < 60 ? `${s}초` : `${Math.floor(s / 60)}분 ${s % 60}초`;
}
