/**
 * SystemAIView - 시스템 AI 풀페이지 채팅 뷰
 *
 * 에이전트 Chat과 동일한 풀페이지 레이아웃으로 시스템 AI와 대화합니다.
 */
import { ChatView } from './chat/ChatView';

export function SystemAIView() {
  const handleBack = () => {
    window.location.hash = '';
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <ChatView
        chatTarget={{ type: 'system_ai' }}
        layout="fullpage"
        onBack={handleBack}
      />
    </div>
  );
}
