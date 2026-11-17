import { Fragment, cloneElement, isValidElement, Children, type ReactNode } from 'react';
import { getConversation } from '../../../surfaces/shared/conversation.js';
import { ui, useLocale } from '../../i18n/ui';

export function conversationLabel(id: string) {
  return ui.source('conversation', getConversation().header.find((item: {id: string; label: string}) => item.id === id)?.label || id);
}
/** 실행자 CLI 세션의 크기 — 마지막 라운드의 문맥 토큰. 문턱도 경고도 없이 숫자만 보인다(새로 여는 것은 "새 세션"). */
export function SessionContextSize({ tokens }: { tokens?: number }) {
  useLocale();
  if (!tokens) return null;
  return <span title="이 대화 세션이 실행자에게 싣고 가는 문맥 크기(토큰)" className="px-1.5 text-xs tabular-nums opacity-70">{ui.number(tokens, { notation: 'compact', maximumFractionDigits: 1 })}</span>;
}
export function ConversationActions({ items }: { items: Partial<Record<string, ReactNode>> }) {
  useLocale();
  return <>{getConversation().header.map((item: {id: string; label: string}) => { const child=items[item.id];return <Fragment key={item.id}>{['history','new'].includes(item.id) && isValidElement<{children?: ReactNode}>(child) ? cloneElement(child, {}, ...Children.toArray(child.props.children).slice(0,-1), conversationLabel(item.id)) : child}</Fragment>; })}</>;
}
