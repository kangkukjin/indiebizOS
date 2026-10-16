import { Fragment, cloneElement, isValidElement, Children, type ReactNode } from 'react';
import { getConversation } from '../../../surfaces/shared/conversation.js';
import { ui, useLocale } from '../../i18n/ui';

export function conversationLabel(id: string) {
  return ui.source('conversation', getConversation().header.find((item: {id: string; label: string}) => item.id === id)?.label || id);
}
export function ConversationActions({ items }: { items: Partial<Record<string, ReactNode>> }) {
  useLocale();
  return <>{getConversation().header.map((item: {id: string; label: string}) => { const child=items[item.id];return <Fragment key={item.id}>{['history','new'].includes(item.id) && isValidElement<{children?: ReactNode}>(child) ? cloneElement(child, {}, ...Children.toArray(child.props.children).slice(0,-1), conversationLabel(item.id)) : child}</Fragment>; })}</>;
}
