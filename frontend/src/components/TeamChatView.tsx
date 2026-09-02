/**
 * TeamChatView — 팀내 대화(대화 관리) 전용 창
 *
 * 프로젝트 창 안의 다이얼로그였던 것을 창으로 승격했다: 창 안 DOM 은 창 밖에 그려질
 * 자리가 없어 끌면 잘린다 — 프로젝트 창 옆에 나란히 놓고 보려면 OS 창이어야 한다
 * (2026-09-02 사용자 판정). 데이터는 프로젝트 창과 공유하지 않고 여기서 직접 읽는다
 * (독립 창 = 독립 렌더러).
 */

import { useCallback, useState } from 'react';
import { RefreshCw, Users } from 'lucide-react';
import { useRetryingLoad } from '../lib/use-retrying-load';
import { TeamChatPanes } from './manager-dialogs/dialogs/TeamChatPanes';
import type { ChatAgent, ChatPartner, TeamChatMessage } from './manager-dialogs';

const API_BASE = 'http://127.0.0.1:8765';

interface TeamChatViewProps {
  projectId: string;
}

export function TeamChatView({ projectId }: TeamChatViewProps) {
  const [chatAgents, setChatAgents] = useState<ChatAgent[]>([]);
  const [selectedChatAgent, setSelectedChatAgent] = useState<number | null>(null);
  const [chatPartners, setChatPartners] = useState<ChatPartner[]>([]);
  const [selectedPartner, setSelectedPartner] = useState<number | null>(null);
  const [teamChatMessages, setTeamChatMessages] = useState<TeamChatMessage[]>([]);
  const [teamChatLoading, setTeamChatLoading] = useState(false);

  const loadAllChatAgents = useCallback(async () => {
    const res = await fetch(`${API_BASE}/conversations/${encodeURIComponent(projectId)}`);
    const data = await res.json();
    const agentList: ChatAgent[] = data.conversations || [];
    // 사람이 먼저, 그다음 이름순 — 목록의 첫 줄이 늘 나 자신이게.
    const sorted = [...agentList].sort((a, b) => {
      if (a.type === 'human' && b.type !== 'human') return -1;
      if (a.type !== 'human' && b.type === 'human') return 1;
      return a.name.localeCompare(b.name);
    });
    setChatAgents(sorted);
  }, [projectId]);
  const { retry: refreshAgents } = useRetryingLoad(loadAllChatAgents);

  const loadChatPartners = useCallback(async () => {
    if (!selectedChatAgent) return;
    const res = await fetch(`${API_BASE}/conversations/${encodeURIComponent(projectId)}/${selectedChatAgent}/partners`);
    const data = await res.json();
    setChatPartners(data.partners || []);
  }, [projectId, selectedChatAgent]);
  useRetryingLoad(loadChatPartners, { enabled: !!selectedChatAgent });

  const loadMessagesBetween = useCallback(async () => {
    if (!selectedChatAgent || !selectedPartner) return;
    setTeamChatLoading(true);
    try {
      const res = await fetch(`${API_BASE}/conversations/${encodeURIComponent(projectId)}/between/${selectedChatAgent}/${selectedPartner}?limit=200`);
      const data = await res.json();
      setTeamChatMessages(data.messages || []);
    } finally {
      setTeamChatLoading(false);
    }
  }, [projectId, selectedChatAgent, selectedPartner]);
  const { retry: refreshMessages } = useRetryingLoad(loadMessagesBetween, {
    enabled: !!(selectedChatAgent && selectedPartner),
  });

  const getAgentNameById = (id: number): string => {
    const agent = chatAgents.find((a) => a.id === id);
    return agent?.name || `Agent ${id}`;
  };

  // 주체가 바뀌면 상대·메시지 선택을 비운다.
  const handleSelectAgent = (id: number | null) => {
    setSelectedChatAgent(id);
    setSelectedPartner(null);
    setTeamChatMessages([]);
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* 헤더 = 이 창의 이동 손잡이(drag). 버튼은 no-drag 로 빼둔다. */}
      <div className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-gray-200 bg-gray-50 drag">
        <div className="flex items-center gap-2 no-drag">
          <Users size={16} className="text-purple-600" />
          <span className="font-semibold text-gray-800">대화 관리</span>
          <span className="text-xs text-gray-400">{projectId}</span>
        </div>
        <button
          onClick={() => { refreshAgents(); refreshMessages(); }}
          className="no-drag flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-gray-200 transition-colors text-gray-600"
          title="새로고침"
        >
          <RefreshCw size={16} />
          <span className="text-sm">새로고침</span>
        </button>
      </div>

      <TeamChatPanes
        chatAgents={chatAgents}
        selectedChatAgent={selectedChatAgent}
        setSelectedChatAgent={handleSelectAgent}
        chatPartners={chatPartners}
        selectedPartner={selectedPartner}
        setSelectedPartner={setSelectedPartner}
        teamChatMessages={teamChatMessages}
        teamChatLoading={teamChatLoading}
        getAgentNameById={getAgentNameById}
      />
    </div>
  );
}
