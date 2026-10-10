import type { ChatMessage, ToolActivity, TodoItem, QuestionItem, PlanModeState } from './types';

/** 저장/전송 방식만 교체한다. 입력·첨부·표시·복사·도구 패널은 ChatView가 소유한다. */
export interface ChatSession {
  messages: ChatMessage[];
  loading: boolean;
  canSteer?: boolean;
  streamingContent?: string;
  toolHistory?: ToolActivity[];
  thinkingText?: string;
  todos?: TodoItem[];
  questions?: QuestionItem[];
  planMode?: PlanModeState;
  error?: string;
  hasOlder?: boolean;
  loadOlder: () => Promise<void>;
  send: (text: string, files: File[], actionHint: string | null) => Promise<boolean>;
  cancel: () => Promise<void>;
}
