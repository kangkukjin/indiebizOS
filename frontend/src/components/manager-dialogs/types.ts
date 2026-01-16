/**
 * Manager 관련 타입 정의
 */

import type { Agent } from '../../types';

// 채팅 에이전트 타입
export interface ChatAgent {
  id: number;
  name: string;
  type: string;
}

// 채팅 파트너 타입
export interface ChatPartner {
  id: number;
  name: string;
  type: string;
  message_count: number;
}

// 채팅 메시지 타입
export interface TeamChatMessage {
  id: number;
  from_agent_id: number;
  to_agent_id: number;
  content: string;
  timestamp: string;
}

// 스위치 폼 타입
export interface SwitchForm {
  name: string;
  icon: string;
  command: string;
  agentName: string;
}

// 에이전트 폼 타입
export interface AgentForm {
  name: string;
  type: string;
  provider: string;
  model: string;
  apiKey: string;
  role: string;
  // 채널 설정
  hasGmail: boolean;
  hasNostr: boolean;
  email: string;
  gmailClientId: string;
  gmailClientSecret: string;
  nostrKeyName: string;
  nostrPrivateKey: string;
  nostrRelays: string;
  // 도구 설정
  allowedTools: string[];
}

// 도구 AI 폼 타입
export interface ToolAIForm {
  provider: string;
  model: string;
  apiKey: string;
}

// 도구 타입
export interface Tool {
  name: string;
  description: string;
  is_base_tool?: boolean;
  uses_ai?: boolean;
  ai_config_key?: string;
  _is_system?: boolean;  // 시스템 기본 도구 (삭제 불가)
  _package_id?: string;  // 패키지 ID
}

// 도구 설정 타입
export interface ToolSettings {
  [key: string]: {
    report_ai?: {
      provider: string;
      model: string;
      api_key: string;
    };
  };
}

// 대화 다이얼로그 크기/위치 타입
export interface DialogSize {
  width: number;
  height: number;
}

export interface DialogPosition {
  x: number;
  y: number;
}

// AgentCard props 타입
export interface AgentCardProps {
  agent: Agent;
  isRunning: boolean;
  isConnected: boolean;
  isSelected: boolean;
  onSelect: () => void;
  onToggleConnect: () => void;
  onStart: () => void;
  onStop: () => void;
  onEditNote: () => void;
}
