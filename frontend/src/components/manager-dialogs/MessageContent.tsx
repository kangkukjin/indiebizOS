/** 관리 메시지는 같은 렌더러의 일반 텍스트 표현을 사용한다. */
import { MessageContent as SharedMessageContent } from '../chat/MessageContent';

export function MessageContent({ content }: { content: string }) {
  return <div><SharedMessageContent content={content} role="assistant" variant="neutral" presentation="plain" /></div>;
}
