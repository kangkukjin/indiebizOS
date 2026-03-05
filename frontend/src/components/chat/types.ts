/**
 * 채팅 공통 타입 정의
 */

export interface ImageAttachment {
  file: File;
  preview: string;
  base64: string;
}

export interface TextAttachment {
  file: File;
  content: string;
  preview: string;
}

export interface ToolActivity {
  name: string;
  status: 'running' | 'done' | 'completed';
  input?: Record<string, unknown>;
  result?: string;
}

export interface TodoItem {
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
  activeForm: string;
}

export interface QuestionOption {
  label: string;
  description: string;
}

export interface QuestionItem {
  question: string;
  header: string;
  options: QuestionOption[];
  multiSelect?: boolean;
}

export interface PlanModeState {
  active: boolean;
  phase: string | null;
  plan_content?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  images?: string[];
  textFiles?: { name: string; content: string }[];
  toolActivities?: ToolActivity[];
}
