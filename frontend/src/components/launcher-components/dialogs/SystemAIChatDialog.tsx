/**
 * SystemAIChatDialog - 시스템 AI 대화 (ChatView 래퍼)
 */
import { ChatView } from '../../chat/ChatView';

interface SystemAIChatDialogProps {
  show: boolean;
  onClose: () => void;
}

export function SystemAIChatDialog({ show, onClose }: SystemAIChatDialogProps) {
  return (
    <ChatView
      chatTarget={{ type: 'system_ai' }}
      layout="dialog"
      show={show}
      onClose={onClose}
    />
  );
}
