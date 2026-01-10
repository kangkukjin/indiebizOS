/**
 * 다중채팅방 컴포넌트
 * 여러 에이전트와 동시에 대화하는 토론방
 * Manager.tsx와 동일한 레이아웃 (왼쪽: 에이전트 목록, 오른쪽: 채팅)
 */

import { useState, useRef, useEffect } from 'react';
import {
  Send, Loader2, Bot, X, Users, MessageSquare,
  Trash2, UserPlus, Play, Square, Wrench, ChevronDown
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { api } from '../lib/api';

interface Room {
  id: string;
  name: string;
  description: string;
  participant_count: number;
  created_at: string;
  updated_at: string;
}

interface Participant {
  agent_name: string;
  agent_source: string;
  system_prompt: string;
}

interface AvailableAgent {
  project_id: string;
  project_name: string;
  agent_id: string;
  agent_name: string;
  role: string;
  source: string;
}

interface ChatMessage {
  id: number;
  room_id: string;
  speaker: string;
  content: string;
  message_time: string;
}

interface Tool {
  name: string;
  description: string;
  package_id: string;
}

interface MultiChatProps {
  roomId?: string;
}

export function MultiChat({ roomId }: MultiChatProps) {
  // 상태
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [availableAgents, setAvailableAgents] = useState<AvailableAgent[]>([]);

  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showAgentSelector, setShowAgentSelector] = useState(false);
  const [responseCount, setResponseCount] = useState(2);

  // 에이전트 활성화 상태
  const [activeAgents, setActiveAgents] = useState<Set<string>>(new Set());
  const [allActive, setAllActive] = useState(false);

  // 올라마 상태
  const [ollamaRunning, setOllamaRunning] = useState(false);
  const [ollamaLoading, setOllamaLoading] = useState(false);

  // 도구 선택 상태
  const [showToolSelector, setShowToolSelector] = useState(false);
  const [availableTools, setAvailableTools] = useState<Tool[]>([]);
  const [selectedTools, setSelectedTools] = useState<string[]>([]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const toolSelectorRef = useRef<HTMLDivElement>(null);

  // roomId로 채팅방 로드
  useEffect(() => {
    if (roomId) {
      const loadRoom = async () => {
        try {
          const room = await api.getMultiChatRoom(roomId);
          if (room) {
            setSelectedRoom({
              id: room.id,
              name: room.name,
              description: room.description,
              participant_count: room.participants?.length || 0,
              created_at: '',
              updated_at: ''
            });
          }
        } catch (error) {
          console.error('Failed to load room:', error);
        }
      };
      loadRoom();
    }
  }, [roomId]);

  // 채팅방 선택 시 데이터 로드
  useEffect(() => {
    if (selectedRoom) {
      loadRoomData(selectedRoom.id);
    }
  }, [selectedRoom]);

  // 메시지 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 올라마 상태 확인
  useEffect(() => {
    const checkOllama = async () => {
      try {
        const status = await api.getOllamaStatus();
        setOllamaRunning(status.running);
      } catch {
        setOllamaRunning(false);
      }
    };
    checkOllama();
    const interval = setInterval(checkOllama, 10000);
    return () => clearInterval(interval);
  }, []);

  // 도구 목록 로드
  useEffect(() => {
    const loadTools = async () => {
      try {
        const data = await api.getTools();
        // 도구 목록 변환 - API는 직접 도구 배열을 반환
        const tools: Tool[] = data.tools
          .filter((t: { _is_system?: boolean }) => !t._is_system)  // 시스템 도구 제외
          .map((t: { name: string; description: string; _package_id?: string }) => ({
            name: t.name,
            description: t.description,
            package_id: t._package_id || 'system',
          }));
        setAvailableTools(tools);
      } catch (error) {
        console.error('도구 목록 로드 실패:', error);
      }
    };
    loadTools();
  }, []);

  // 도구 선택 드롭다운 외부 클릭 시 닫기
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (toolSelectorRef.current && !toolSelectorRef.current.contains(e.target as Node)) {
        setShowToolSelector(false);
      }
    };
    if (showToolSelector) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showToolSelector]);

  const loadRoomData = async (roomId: string) => {
    try {
      const [room, msgs] = await Promise.all([
        api.getMultiChatRoom(roomId),
        api.getMultiChatMessages(roomId),
      ]);
      setParticipants(room.participants || []);
      setMessages(msgs);
    } catch (error) {
      console.error('채팅방 데이터 로드 실패:', error);
    }
  };

  const loadAvailableAgents = async () => {
    try {
      const agents = await api.getAvailableAgentsForMultiChat();
      setAvailableAgents(agents);
    } catch (error) {
      console.error('에이전트 목록 로드 실패:', error);
    }
  };

  const addAgent = async (agent: AvailableAgent) => {
    if (!selectedRoom) return;

    try {
      await api.addAgentToMultiChatRoom(selectedRoom.id, agent.project_id, agent.agent_id);
      await loadRoomData(selectedRoom.id);
      setShowAgentSelector(false);
    } catch (error) {
      console.error('에이전트 추가 실패:', error);
    }
  };

  const removeAgent = async (agentName: string) => {
    if (!selectedRoom) return;

    try {
      await api.removeAgentFromMultiChatRoom(selectedRoom.id, agentName);
      setParticipants(participants.filter(p => p.agent_name !== agentName));
    } catch (error) {
      console.error('에이전트 제거 실패:', error);
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || !selectedRoom || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    setIsLoading(true);

    // 사용자 메시지를 먼저 표시
    const tempUserMsg: ChatMessage = {
      id: Date.now(),
      room_id: selectedRoom.id,
      speaker: '사용자',
      content: userMessage,
      message_time: new Date().toISOString(),
    };
    setMessages(prev => [...prev, tempUserMsg]);

    try {
      const result = await api.sendMultiChatMessage(selectedRoom.id, userMessage, responseCount);

      // AI 응답 추가
      const newMessages: ChatMessage[] = result.responses.map((r, i) => ({
        id: Date.now() + i + 1,
        room_id: selectedRoom.id,
        speaker: r.speaker,
        content: r.content,
        message_time: new Date().toISOString(),
      }));

      setMessages(prev => [...prev, ...newMessages]);
    } catch (error) {
      console.error('메시지 전송 실패:', error);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearMessages = async () => {
    if (!selectedRoom || !confirm('모든 메시지를 삭제하시겠습니까?')) return;

    try {
      await api.clearMultiChatMessages(selectedRoom.id);
      setMessages([]);
    } catch (error) {
      console.error('메시지 삭제 실패:', error);
    }
  };

  // 전체 시작
  const handleStartAll = async () => {
    if (!selectedRoom) return;
    try {
      await api.activateAllMultiChatAgents(selectedRoom.id, selectedTools);
      setAllActive(true);
      setActiveAgents(new Set(participants.map(p => p.agent_name)));
    } catch (error) {
      console.error('전체 시작 실패:', error);
    }
  };

  // 전체 중단
  const handleStopAll = async () => {
    if (!selectedRoom) return;
    try {
      await api.deactivateAllMultiChatAgents(selectedRoom.id);
      setAllActive(false);
      setActiveAgents(new Set());
    } catch (error) {
      console.error('전체 중단 실패:', error);
    }
  };

  // 올라마 토글
  const handleToggleOllama = async () => {
    setOllamaLoading(true);
    try {
      const action = ollamaRunning ? 'stop' : 'start';
      const result = await api.toggleOllama(action);
      setOllamaRunning(result.running);
    } catch (error) {
      console.error('올라마 토글 실패:', error);
    } finally {
      setOllamaLoading(false);
    }
  };

  // 도구 선택 토글
  const toggleToolSelection = (toolName: string) => {
    setSelectedTools(prev =>
      prev.includes(toolName)
        ? prev.filter(t => t !== toolName)
        : [...prev, toolName]
    );
  };

  // 에이전트별 색상
  const getAgentColor = (speaker: string) => {
    const colors = [
      { bg: 'bg-blue-100', text: 'text-blue-800', border: 'border-blue-300' },
      { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-300' },
      { bg: 'bg-purple-100', text: 'text-purple-800', border: 'border-purple-300' },
      { bg: 'bg-orange-100', text: 'text-orange-800', border: 'border-orange-300' },
      { bg: 'bg-pink-100', text: 'text-pink-800', border: 'border-pink-300' },
      { bg: 'bg-teal-100', text: 'text-teal-800', border: 'border-teal-300' },
    ];
    const index = participants.findIndex(p => p.agent_name === speaker);
    return colors[index % colors.length] || { bg: 'bg-gray-100', text: 'text-gray-800', border: 'border-gray-300' };
  };

  // roomId가 전달되었는데 아직 로딩 중인 경우
  if (roomId && !selectedRoom) {
    return (
      <div className="h-full flex items-center justify-center bg-[#F5F1EB]">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  // roomId 없이 열린 경우 (일반적으로 사용되지 않음)
  if (!selectedRoom) {
    return (
      <div className="h-full flex items-center justify-center bg-[#F5F1EB]">
        <div className="text-center text-gray-600">
          <MessageSquare className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>채팅방을 찾을 수 없습니다</p>
        </div>
      </div>
    );
  }

  // 채팅방 화면 - Manager.tsx와 동일한 레이아웃
  return (
    <div className="h-full flex flex-col bg-[#F5F1EB]">
      {/* 헤더 */}
      <div className="h-12 flex items-center justify-between px-4 bg-[#EAE4DA] border-b border-[#E5DFD5] drag">
        <div className="flex items-center gap-2 no-drag">
          <Users className="w-5 h-5 text-[#6B5B4F]" />
          <span className="font-semibold text-[#4A4035]">{selectedRoom.name}</span>
        </div>

        <div className="flex items-center gap-1 no-drag">
          {/* 전체 시작/중단 버튼 */}
          {allActive ? (
            <button
              onClick={handleStopAll}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500 hover:bg-red-600 transition-colors text-white"
              title="전체 중단"
            >
              <Square className="w-4 h-4" />
              <span className="text-sm">전체 중단</span>
            </button>
          ) : (
            <button
              onClick={handleStartAll}
              disabled={participants.length === 0}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-500 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-white"
              title="전체 시작"
            >
              <Play className="w-4 h-4" />
              <span className="text-sm">전체 시작</span>
            </button>
          )}

          {/* 올라마 버튼 */}
          <button
            onClick={handleToggleOllama}
            disabled={ollamaLoading}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors ${
              ollamaRunning
                ? 'bg-purple-500 hover:bg-purple-600 text-white'
                : 'bg-gray-200 hover:bg-gray-300 text-gray-700'
            }`}
            title={ollamaRunning ? 'Ollama 중단' : 'Ollama 시작'}
          >
            {ollamaLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Bot className="w-4 h-4" />
            )}
            <span className="text-sm">{ollamaRunning ? 'Ollama 실행중' : 'Ollama 시작'}</span>
          </button>

          {/* 도구 선택 버튼 */}
          <div className="relative" ref={toolSelectorRef}>
            <button
              onClick={() => setShowToolSelector(!showToolSelector)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-[#DDD5C8] transition-colors text-[#6B5B4F]"
              title="도구 선택"
            >
              <Wrench className="w-4 h-4" />
              <span className="text-sm">도구 ({selectedTools.length})</span>
              <ChevronDown className={`w-3 h-3 transition-transform ${showToolSelector ? 'rotate-180' : ''}`} />
            </button>

            {/* 도구 선택 드롭다운 */}
            {showToolSelector && (
              <div className="absolute right-0 top-full mt-1 w-72 bg-white rounded-lg shadow-xl border border-gray-200 z-50 max-h-80 overflow-auto">
                <div className="p-2 border-b border-gray-100">
                  <p className="text-xs text-gray-500">선택한 도구는 모든 에이전트에게 제공됩니다</p>
                </div>
                <div className="p-2 space-y-1">
                  {availableTools.length === 0 ? (
                    <p className="text-sm text-gray-400 text-center py-4">사용 가능한 도구가 없습니다</p>
                  ) : (
                    availableTools.map(tool => (
                      <label
                        key={tool.name}
                        className="flex items-start gap-2 p-2 rounded-lg hover:bg-gray-50 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={selectedTools.includes(tool.name)}
                          onChange={() => toggleToolSelection(tool.name)}
                          className="mt-1 rounded border-gray-300 text-indigo-500 focus:ring-indigo-500"
                        />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">{tool.name}</p>
                          <p className="text-xs text-gray-500 truncate">{tool.description}</p>
                        </div>
                      </label>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="w-px h-6 bg-[#DDD5C8] mx-1" />

          <button
            onClick={() => {
              loadAvailableAgents();
              setShowAgentSelector(true);
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-500 hover:bg-indigo-600 transition-colors text-white"
          >
            <UserPlus className="w-4 h-4" />
            <span className="text-sm">에이전트 추가</span>
          </button>
          <button
            onClick={clearMessages}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-[#DDD5C8] transition-colors text-[#6B5B4F]"
            title="대화 초기화"
          >
            <Trash2 className="w-4 h-4" />
            <span className="text-sm">초기화</span>
          </button>
        </div>
      </div>

      {/* 메인 영역 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 사이드바 - 참여 에이전트 목록 */}
        <div className="w-72 bg-[#EAE4DA] border-r border-[#E5DFD5] flex flex-col">
          <div className="p-3 border-b border-[#E5DFD5] flex items-center justify-between">
            <h3 className="text-sm font-semibold text-[#4A4035]">참여 에이전트</h3>
            <span className="text-xs text-[#6B5B4F] bg-[#DDD5C8] px-2 py-0.5 rounded-full">
              {participants.length}명
            </span>
          </div>
          <div className="flex-1 overflow-auto">
            {participants.length === 0 ? (
              <div className="p-4 text-center">
                <Bot className="w-10 h-10 mx-auto mb-2 text-[#A09080]" />
                <p className="text-sm text-[#6B5B4F]">참여 에이전트가 없습니다</p>
                <p className="text-xs text-[#A09080] mt-1">에이전트를 추가하세요</p>
              </div>
            ) : (
              <div className="p-2 space-y-2">
                {participants.map((p) => {
                  const color = getAgentColor(p.agent_name);
                  return (
                    <div
                      key={p.agent_name}
                      className={`p-3 rounded-lg border ${color.bg} ${color.border} ${color.text}`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-2">
                          <Bot className="w-5 h-5" />
                          <div>
                            <p className="font-medium text-sm">{p.agent_name}</p>
                            <p className="text-xs opacity-70 truncate max-w-[160px]">
                              {p.agent_source}
                            </p>
                          </div>
                        </div>
                        <button
                          onClick={() => removeAgent(p.agent_name)}
                          className="p-1 rounded hover:bg-black/10 transition-colors"
                          title="제거"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 응답 설정 */}
          <div className="p-3 border-t border-[#E5DFD5] bg-[#E5DFD5]">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#4A4035] font-medium">응답 에이전트 수</span>
              <select
                value={responseCount}
                onChange={(e) => setResponseCount(Number(e.target.value))}
                className="text-sm px-2 py-1 border border-[#DDD5C8] rounded-lg bg-white text-[#4A4035] focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {[1, 2, 3, 4, 5].map(n => (
                  <option key={n} value={n}>{n}명</option>
                ))}
              </select>
            </div>
            <p className="text-xs text-[#A09080] mt-1">
              @이름으로 특정 에이전트 지목 가능
            </p>
          </div>
        </div>

        {/* 오른쪽 - 채팅 영역 */}
        <div className="flex-1 flex flex-col bg-[#F5F1EB]">
          {/* 메시지 목록 */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 ? (
              <div className="h-full flex items-center justify-center">
                <div className="text-center">
                  <MessageSquare className="w-16 h-16 mx-auto mb-4 text-[#A09080]" />
                  <p className="text-[#6B5B4F] font-medium">대화를 시작해보세요</p>
                  <p className="text-sm text-[#A09080] mt-2">
                    {participants.length === 0
                      ? '먼저 에이전트를 추가하세요'
                      : '@에이전트이름 으로 특정 에이전트를 지목할 수 있습니다'}
                  </p>
                </div>
              </div>
            ) : (
              messages.map(msg => {
                const isUser = msg.speaker === '사용자';
                const color = getAgentColor(msg.speaker);

                return (
                  <div
                    key={msg.id}
                    className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[70%] rounded-2xl px-4 py-3 ${
                        isUser
                          ? 'bg-indigo-500 text-white rounded-br-md'
                          : `${color.bg} ${color.text} rounded-bl-md border ${color.border}`
                      }`}
                    >
                      {!isUser && (
                        <div className="flex items-center gap-2 mb-2">
                          <Bot className="w-4 h-4" />
                          <span className="text-sm font-semibold">{msg.speaker}</span>
                        </div>
                      )}
                      <div className={`prose prose-sm max-w-none ${isUser ? 'prose-invert' : ''}`}>
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* 입력 영역 */}
          <div className="p-4 border-t border-[#E5DFD5] bg-[#EAE4DA]">
            {participants.length === 0 ? (
              <div className="text-center py-3">
                <p className="text-sm text-orange-600 font-medium">
                  에이전트를 추가해야 대화할 수 있습니다
                </p>
              </div>
            ) : (
              <div className="flex items-end gap-3">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="메시지를 입력하세요... (@이름으로 지목 가능)"
                  className="flex-1 px-4 py-3 border border-[#DDD5C8] rounded-xl resize-none bg-white text-[#4A4035] placeholder-[#A09080] focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  rows={1}
                  disabled={isLoading}
                />
                <button
                  onClick={sendMessage}
                  disabled={isLoading || !input.trim()}
                  className="p-3 bg-indigo-500 text-white rounded-xl hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isLoading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Send className="w-5 h-5" />
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 에이전트 선택 모달 */}
      {showAgentSelector && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl w-[500px] max-h-[600px] shadow-xl overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">에이전트 추가</h2>
              <button
                onClick={() => setShowAgentSelector(false)}
                className="p-1 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-gray-600" />
              </button>
            </div>
            <div className="overflow-y-auto max-h-[500px] p-4">
              {availableAgents.length === 0 ? (
                <p className="text-center text-gray-500 py-8">
                  추가 가능한 에이전트가 없습니다
                </p>
              ) : (
                <div className="space-y-2">
                  {/* 프로젝트별로 그룹핑 */}
                  {Object.entries(
                    availableAgents.reduce((acc, agent) => {
                      if (!acc[agent.project_name]) acc[agent.project_name] = [];
                      acc[agent.project_name].push(agent);
                      return acc;
                    }, {} as Record<string, AvailableAgent[]>)
                  ).map(([projectName, agents]) => (
                    <div key={projectName} className="mb-4">
                      <h3 className="text-sm font-medium text-gray-500 mb-2 px-2">
                        {projectName}
                      </h3>
                      {agents.map(agent => {
                        const isAdded = participants.some(
                          p => p.agent_name === agent.agent_name
                        );
                        return (
                          <button
                            key={`${agent.project_id}-${agent.agent_id}`}
                            onClick={() => !isAdded && addAgent(agent)}
                            disabled={isAdded}
                            className={`w-full flex items-center gap-3 p-3 rounded-lg text-left transition-colors ${
                              isAdded
                                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                : 'hover:bg-indigo-50'
                            }`}
                          >
                            <Bot className={`w-5 h-5 ${isAdded ? 'text-gray-400' : 'text-indigo-500'}`} />
                            <div className="flex-1 min-w-0">
                              <p className={`font-medium truncate ${isAdded ? 'text-gray-400' : 'text-gray-900'}`}>
                                {agent.agent_name}
                              </p>
                              <p className={`text-sm truncate ${isAdded ? 'text-gray-400' : 'text-gray-600'}`}>
                                {agent.role || '역할 없음'}
                              </p>
                            </div>
                            {isAdded && (
                              <span className="text-xs text-gray-400 bg-gray-200 px-2 py-1 rounded">추가됨</span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
