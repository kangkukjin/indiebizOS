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

/** IBL 안쪽의 진행 신고(ibl_progress report_step/beat) — execute_ibl 한 호출이 도는 동안 "지금 어느 낱말인가" */
export interface ToolProgress {
  /** 현재 액션 `node:action` (좌표 소유자의 신고) */
  action?: string;
  /** 호출 번호(1부터). of 는 0=미지 — 함수·each 안의 호출은 정적으로 셀 수 없다 */
  step?: number;
  of?: number;
  /** 호출을 새로 실행하지 않고 영수증으로 재사용했는가 */
  reused?: boolean;
  /** 회차 등 움직임(beat) — row/rows/row_label, substep/substeps/subaction 등 자리마다 다른 키 */
  detail?: Record<string, unknown>;
  /** 마지막 움직임 시각(클라이언트 시계 ms) — 멈춤과 느림을 가르는 유일한 증거 */
  at: number;
}

export interface ToolActivity {
  /** 프로바이더가 부여한 호출 id — 병렬 호출의 start↔result 페어링 키(없을 수 있음) */
  id?: string;
  name: string;
  status: 'running' | 'done' | 'completed';
  input?: Record<string, unknown>;
  result?: string;
  /** 호출이 실패했나 — backend tool_result.is_error 그대로. 미표명이면 undefined */
  isError?: boolean;
  /** 실행 중 진행 좌표 — 끝나면 비운다 */
  progress?: ToolProgress;
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
