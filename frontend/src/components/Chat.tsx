/**
 * Chat - 프로젝트 에이전트 대화 (ChatView 래퍼)
 */
import type { Agent } from '../types';
import { ChatView } from './chat/ChatView';

interface ChatProps {
  projectId: string;
  agent: Agent;
}

export function Chat({ projectId, agent }: ChatProps) {
  return (
    <ChatView
      chatTarget={{ type: 'agent', projectId, agent }}
      layout="fullpage"
    />
  );
}
