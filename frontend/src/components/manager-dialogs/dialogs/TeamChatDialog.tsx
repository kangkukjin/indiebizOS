/**
 * TeamChatDialog - 팀내 대화 다이얼로그 (Electron 밖 대비 예비 경로)
 *
 * 정본은 전용 창(TeamChatView, `#/projectpanel/teamchat/<projectId>`) — 창 안 DOM 은 창 밖으로
 * 나갈 수 없어 끌면 잘리기 때문이다. 여기 남은 판은 `window.electron` 이 없는 표면
 * (브라우저·원격)에서만 쓰인다. 알맹이는 TeamChatPanes 하나를 같이 쓴다.
 */

import { useRef } from 'react';
import { X, RefreshCw } from 'lucide-react';
import { TeamChatPanes } from './TeamChatPanes';
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
      {/* 창 이동 손잡이 되살리기 — 이 판이 프로젝트 창의 드래그바(Manager 헤더 h-12)를 덮는다.
          같은 자리에 drag 를 다시 선언하고, 다이얼로그 자신은 no-drag 로 빼둔다
          (안 그러면 다이얼로그 헤더를 끌 때 창이 함께 끌린다). */}
      <div className="absolute inset-x-0 top-0 h-12 drag" />
      <div
        ref={chatDialogRef}
        className="absolute bg-white rounded-xl shadow-2xl overflow-hidden flex flex-col no-drag"
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
        <TeamChatPanes
          chatAgents={chatAgents}
          selectedChatAgent={selectedChatAgent}
          setSelectedChatAgent={setSelectedChatAgent}
          chatPartners={chatPartners}
          selectedPartner={selectedPartner}
          setSelectedPartner={setSelectedPartner}
          teamChatMessages={teamChatMessages}
          teamChatLoading={teamChatLoading}
          getAgentNameById={getAgentNameById}
        />
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
