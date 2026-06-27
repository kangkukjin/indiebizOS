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

export interface DocumentAttachment {
  file: File;
  filePath: string;
  fileName: string;
  fileType: string;
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

// 자율주행 작업전 공개 — 실행 직전 "지금 얼마나 확신하나/무슨 판단/무슨 IBL을 연상했나"
export interface CognitionInfo {
  decision: 'reflex' | 'think' | 'execute';
  score: number;        // 해마 최고 점수 0..1
  action?: string;      // 연상한 IBL 코드 (있으면)
  criteria?: string;    // 달성 기준 (숙고 경로일 때)
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  images?: string[];
  textFiles?: { name: string; content: string }[];
  documentFiles?: { fileName: string; filePath: string; fileType: string }[];
  toolActivities?: ToolActivity[];
  cognition?: CognitionInfo;   // 설정되면 일반 버블 대신 작업전 공개 칩을 렌더
}
