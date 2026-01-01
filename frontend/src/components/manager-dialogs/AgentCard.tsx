/**
 * AgentCard - 에이전트 카드 컴포넌트
 */

import {
  Bot,
  Play,
  Square,
  FileText,
  Link,
  Link2Off,
} from 'lucide-react';
import type { AgentCardProps } from './types';

const providerColors: Record<string, string> = {
  anthropic: 'bg-orange-500',
  openai: 'bg-green-500',
  google: 'bg-blue-500',
};

export function AgentCard({
  agent,
  isRunning,
  isConnected,
  isSelected,
  onSelect,
  onToggleConnect,
  onStart,
  onStop,
  onEditNote,
}: AgentCardProps) {
  return (
    <div
      className={`p-3 border-b border-[#E5DFD5] cursor-pointer transition-colors ${
        isSelected ? 'bg-[#D97706]/10' : 'hover:bg-[#DDD5C8]'
      }`}
      onClick={onSelect}
    >
      {/* 상단: 이름과 상태 */}
      <div className="flex items-center gap-2 mb-2">
        <div className="w-8 h-8 rounded-full bg-[#E5DFD5] flex items-center justify-center text-[#6B5B4F]">
          <Bot size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-medium truncate text-[#4A4035] text-sm">{agent.name}</div>
          <div className="flex items-center gap-1.5 text-xs text-[#A09080]">
            <span className={`w-1.5 h-1.5 rounded-full ${providerColors[agent.ai?.provider || 'google']}`} />
            <span>{agent.ai?.provider || 'google'}</span>
          </div>
        </div>
        <div className={`text-xs ${isRunning ? 'text-green-600' : 'text-gray-400'}`}>
          {isRunning ? '● 실행 중' : '○ 중지'}
        </div>
      </div>

      {/* 하단: 버튼들 */}
      <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
        {/* 연결 버튼 */}
        <button
          onClick={onToggleConnect}
          className={`flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors ${
            isConnected
              ? 'bg-[#D97706] text-white'
              : 'bg-[#E5DFD5] text-[#6B5B4F] hover:bg-[#DDD5C8]'
          }`}
        >
          {isConnected ? <Link2Off size={12} /> : <Link size={12} />}
          {isConnected ? '연결됨' : '연결'}
        </button>

        {/* 시작/중지 버튼 */}
        {isRunning ? (
          <button
            onClick={onStop}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-red-500 text-white hover:bg-red-600 transition-colors"
          >
            <Square size={12} />
            중지
          </button>
        ) : (
          <button
            onClick={onStart}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-green-500 text-white hover:bg-green-600 transition-colors"
          >
            <Play size={12} />
            시작
          </button>
        )}

        {/* 노트 버튼 */}
        <button
          onClick={onEditNote}
          className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-purple-500 text-white hover:bg-purple-600 transition-colors"
        >
          <FileText size={12} />
          노트
        </button>
      </div>
    </div>
  );
}
