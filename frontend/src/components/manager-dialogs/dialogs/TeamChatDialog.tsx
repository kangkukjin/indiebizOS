/**
 * TeamChatDialog - 팀내 대화 다이얼로그
 */

import { useRef } from 'react';
import { X, RefreshCw } from 'lucide-react';
import { MessageContent } from '../MessageContent';
import type { ChatAgent, ChatPartner, TeamChatMessage, DialogSize, DialogPosition } from '../types';

interface TeamChatDialogProps {
  show: boolean;
  onClose: () => void;
  chatDialogSize: DialogSize;
  chatDialogPos: DialogPosition;
  chatAgents: ChatAgent[];
  selectedChatAgent: number | null;
  setSelectedChatAgent: (id: number | null) => void;
  chatPartners: ChatPartner[];
  selectedPartner: number | null;
  setSelectedPartner: (id: number | null) => void;
  teamChatMessages: TeamChatMessage[];
  teamChatLoading: boolean;
  getAgentNameById: (id: number) => string;
  onRefresh: () => void;
  onDragStart: (e: React.MouseEvent) => void;
  onResizeStart: (e: React.MouseEvent) => void;
}

export function TeamChatDialog({
  show,
  onClose,
  chatDialogSize,
  chatDialogPos,
  chatAgents,
  selectedChatAgent,
  setSelectedChatAgent,
  chatPartners,
  selectedPartner,
  setSelectedPartner,
  teamChatMessages,
  teamChatLoading,
  getAgentNameById,
  onRefresh,
  onDragStart,
  onResizeStart,
}: TeamChatDialogProps) {
  const chatDialogRef = useRef<HTMLDivElement>(null);

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 z-50">
      <div
        ref={chatDialogRef}
        className="absolute bg-white rounded-xl shadow-2xl overflow-hidden flex flex-col"
        style={{
          left: chatDialogPos.x,
          top: chatDialogPos.y,
          width: chatDialogSize.width,
          height: chatDialogSize.height,
        }}
      >
        {/* 드래그 가능한 헤더 */}
        <div
          className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 shrink-0 cursor-move select-none"
          onMouseDown={onDragStart}
        >
          <h2 className="text-xl font-bold text-gray-800">💬 대화 관리</h2>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-gray-200 rounded-lg cursor-pointer"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <X size={20} className="text-gray-500" />
          </button>
        </div>
        <div className="flex-1 flex overflow-hidden">
          {/* 왼쪽: 대화 주체 목록 */}
          <div className="w-44 border-r border-gray-200 bg-gray-50 overflow-y-auto">
            <div className="p-2">
              <p className="text-xs text-gray-500 px-2 py-1 font-medium">대화 주체</p>
              {chatAgents.map((agent) => (
                <button
                  key={agent.id}
                  onClick={() => setSelectedChatAgent(agent.id)}
                  className={`w-full text-left px-3 py-2 rounded-lg mb-1 transition-colors ${
                    selectedChatAgent === agent.id
                      ? 'bg-blue-100 text-blue-700'
                      : 'hover:bg-gray-100 text-gray-700'
                  }`}
                >
                  <span className="text-sm">{agent.type === 'human' ? '👤' : '🤖'} {agent.name}</span>
                </button>
              ))}
              {chatAgents.length === 0 && (
                <p className="text-xs text-gray-400 px-2 py-4 text-center">에이전트 없음</p>
              )}
            </div>
          </div>
          {/* 중간: 대화 상대 목록 */}
          <div className="w-52 border-r border-gray-200 bg-white overflow-y-auto">
            <div className="p-2">
              {selectedChatAgent ? (
                <>
                  <p className="text-xs text-gray-500 px-2 py-1 font-medium">
                    대화 상대 ({chatPartners.length})
                  </p>
                  {chatPartners.map((partner) => (
                    <button
                      key={partner.id}
                      onClick={() => setSelectedPartner(partner.id)}
                      className={`w-full text-left px-3 py-2 rounded-lg mb-1 transition-colors ${
                        selectedPartner === partner.id
                          ? 'bg-blue-100 text-blue-700'
                          : 'hover:bg-gray-100 text-gray-700'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm">{partner.type === 'ai_agent' ? '🤖' : '👤'} {partner.name}</span>
                        <span className="text-xs text-gray-400">{partner.message_count}</span>
                      </div>
                    </button>
                  ))}
                  {chatPartners.length === 0 && (
                    <p className="text-xs text-gray-400 px-2 py-4 text-center">대화 상대 없음</p>
                  )}
                </>
              ) : (
                <p className="text-xs text-gray-400 px-2 py-4 text-center">주체를 선택하세요</p>
              )}
            </div>
          </div>
          {/* 오른쪽: 메시지 목록 */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {selectedPartner && selectedChatAgent ? (
              <>
                <div className="px-4 py-2 bg-gray-100 border-b border-gray-200">
                  <span className="text-sm font-medium text-gray-700">
                    {getAgentNameById(selectedChatAgent)} ↔ {getAgentNameById(selectedPartner)} 대화
                  </span>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                  {teamChatLoading ? (
                    <div className="flex items-center justify-center h-full">
                      <RefreshCw className="animate-spin text-gray-400" size={24} />
                    </div>
                  ) : teamChatMessages.length > 0 ? (
                    [...teamChatMessages].reverse().map((msg) => (
                      <div
                        key={msg.id}
                        className={`flex ${msg.from_agent_id === selectedChatAgent ? 'justify-end' : 'justify-start'}`}
                      >
                        <div
                          className={`max-w-[70%] rounded-lg px-4 py-2 ${
                            msg.from_agent_id === selectedChatAgent
                              ? 'bg-blue-500 text-white'
                              : 'bg-gray-200 text-gray-800'
                          }`}
                        >
                          <div className="text-xs opacity-70 mb-1">
                            {getAgentNameById(msg.from_agent_id)}
                          </div>
                          <MessageContent content={msg.content} />
                          <div className="text-xs opacity-50 mt-1">
                            {new Date(msg.timestamp).toLocaleString('ko-KR')}
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-400">
                      대화 기록이 없습니다
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-gray-400">
                {selectedChatAgent ? '대화 상대를 선택하세요' : '주체와 대화 상대를 선택하세요'}
              </div>
            )}
          </div>
        </div>
        <div className="flex justify-between px-6 py-4 border-t border-gray-200 bg-gray-50 shrink-0">
          <button
            onClick={onRefresh}
            className="px-4 py-2 rounded-lg hover:bg-gray-200 transition-colors text-gray-600 flex items-center gap-2"
          >
            <RefreshCw size={16} />
            새로고침
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg hover:bg-gray-200 transition-colors text-gray-600"
          >
            닫기
          </button>
        </div>
        {/* 리사이즈 핸들 (우하단) */}
        <div
          className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize"
          onMouseDown={onResizeStart}
          style={{
            background: 'linear-gradient(135deg, transparent 50%, #a0a0a0 50%)',
          }}
        />
      </div>
    </div>
  );
}
