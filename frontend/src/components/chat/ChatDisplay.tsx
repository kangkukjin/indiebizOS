import { displayOwner } from '../../lib/display-owner';
import { renderChatDisplay } from './ChatDisplayView';
export const chatDisplay = displayOwner(renderChatDisplay);
export const ChatDisplay = chatDisplay.View;
