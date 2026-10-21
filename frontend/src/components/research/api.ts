import type { CognitionInfo, ToolActivity, TodoItem, QuestionItem, PlanModeState } from '../chat/types';
import { runIBL, IMAGE_BASE } from '../generic/manifest';

export interface ResearchThread {
  id: string; thread_ref: string; title: string; updated_label: string;
  active_run?: string | null; archived?: boolean;
  revision?: number;
}
export interface SavedAttachment { name: string; version_ref: string; mime: string; path: string }
export interface ResearchMessage {
  id: number; display_order?: number; content: string; role: 'user' | 'assistant'; message_time: string;
  status: string; tool_activities?: ToolActivity[]; cognition?: CognitionInfo; thinking?: string; todos?: TodoItem[]; questions?: QuestionItem[]; plan_mode?: PlanModeState;
  status_label: string; attachments: SavedAttachment[];
}
export interface ConversationData extends ResearchThread {
  items: ResearchMessage[]; next_cursor: string | null;
}
export async function researchCall(project: string, op: string, params: Record<string, unknown> = {}) {
  const inputs = { project_ref: project, op, ...params };
  const fields = Object.keys(inputs).map(k => `${k}: $${k}`).join(', ');
  const result = await runIBL({ code: `[self:project]{${fields}}`, edition: 2, inputs, declared_inputs: Object.keys(inputs) });
  if (result.success === false || result.error) throw new Error(String(result.error || result.message || '요청 실패'));
  return result;
}
const uploads = new WeakMap<File, string>();
export async function uploadAttachment(file: File) {
  let path = uploads.get(file);
  if (!path) {
    const response = await fetch(`${IMAGE_BASE}/launcher/upload?name=${encodeURIComponent(file.name)}`, { method: 'POST', body: file });
    const data = await response.json();
    if (!response.ok || !data.success || !data.path) throw new Error(data.error || `${file.name} 업로드 실패`);
    path = String(data.path);
    uploads.set(file, path);
  }
  return { path, name: file.name };
}
