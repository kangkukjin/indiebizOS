/**
 * 매니저 - 프로젝트 내 에이전트 관리
 * 원본 manager.py의 기능을 React로 구현
 */

import { useEffect, useState, useRef } from 'react';
import {
  ArrowLeft,
  Settings,
  Users,
  Zap,
  PlayCircle,
  StopCircle,
  Server,
  ServerOff,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAppStore } from '../stores/appStore';
import { api } from '../lib/api';
import { Chat } from './Chat';
import type { Agent, Switch } from '../types';

// 모듈화된 컴포넌트 임포트
import {
  AgentCard,
  SwitchDialog,
  NoteDialog,
  AgentEditDialog,
  TeamChatDialog,
  SettingsDialog,
} from './manager-dialogs';
import type {
  ChatAgent,
  ChatPartner,
  TeamChatMessage,
  SwitchForm,
  AgentForm,
} from './manager-dialogs';

export function Manager() {
  const {
    currentProject,
    agents,
    currentAgent,
    loadAgents,
    setCurrentAgent,
    setCurrentView,
    switches,
    loadSwitches,
  } = useAppStore();

  // 상태
  const [connectedAgentId, setConnectedAgentId] = useState<string | null>(null);
  const [runningAgents, setRunningAgents] = useState<Set<string>>(new Set());
  const [ollamaRunning, setOllamaRunning] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // 다이얼로그 상태
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [showTeamChatDialog, setShowTeamChatDialog] = useState(false);
  const [showSwitchDialog, setShowSwitchDialog] = useState(false);
  const [showNoteDialog, setShowNoteDialog] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [noteContent, setNoteContent] = useState('');

  // 팀내 대화 상태
  const [chatAgents, setChatAgents] = useState<ChatAgent[]>([]);
  const [selectedChatAgent, setSelectedChatAgent] = useState<number | null>(null);
  const [chatPartners, setChatPartners] = useState<ChatPartner[]>([]);
  const [selectedPartner, setSelectedPartner] = useState<number | null>(null);
  const [teamChatMessages, setTeamChatMessages] = useState<TeamChatMessage[]>([]);
  const [teamChatLoading, setTeamChatLoading] = useState(false);

  // 사내대화 창 크기/위치 상태
  const [chatDialogSize, setChatDialogSize] = useState({ width: 900, height: 600 });
  const [chatDialogPos, setChatDialogPos] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });

  // 스위치 생성/편집 폼
  const [switchForm, setSwitchForm] = useState<SwitchForm>({
    name: '',
    icon: '⚡',
    command: '',
    agentName: '',
  });
  const [editingSwitch, setEditingSwitch] = useState<Switch | null>(null);

  // 설정 다이얼로그 상태
  const [settingsTab, setSettingsTab] = useState<'channels' | 'tools' | 'agents'>('agents');
  const [showAgentEditDialog, setShowAgentEditDialog] = useState(false);
  const [editingAgentData, setEditingAgentData] = useState<Agent | null>(null);
  const [agentForm, setAgentForm] = useState<AgentForm>({
    name: '',
    type: 'internal',
    provider: 'google',
    model: 'gemini-2.0-flash-exp',
    apiKey: '',
    role: '',
    hasGmail: false,
    hasNostr: false,
    email: '',
    gmailClientId: '',
    gmailClientSecret: '',
    nostrKeyName: '',
    nostrPrivateKey: '',
    nostrRelays: 'wss://relay.damus.io,wss://relay.nostr.band,wss://nos.lol',
    allowedNodes: [],
  });
  const [defaultTools, setDefaultTools] = useState<string[]>([]);


  // ============ useEffect 훅들 ============

  useEffect(() => {
    if (currentProject) {
      loadAgents(currentProject.id);
      loadSwitches();  // 스위치 로드
      // 프로젝트 로드 시 default_tools도 함께 로드
      const loadDefaultTools = async () => {
        try {
          const config = await api.getProjectConfig(currentProject.id);
          if (config.default_tools) {
            setDefaultTools(config.default_tools as string[]);
          } else {
            setDefaultTools([]);
          }
        } catch (error) {
          console.error('default_tools 로드 실패:', error);
        }
      };
      loadDefaultTools();
    }
  }, [currentProject, loadAgents, loadSwitches]);

  useEffect(() => {
    const checkOllamaStatus = async () => {
      try {
        const status = await api.getOllamaStatus();
        setOllamaRunning(status.running);
      } catch {
        // 무시
      }
    };
    checkOllamaStatus();
  }, []);


  useEffect(() => {
    if (showSettingsDialog && currentProject) {
      loadSettingsData();
    }
  }, [showSettingsDialog, currentProject]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  useEffect(() => {
    if (showTeamChatDialog && currentProject) {
      setChatDialogPos({
        x: (window.innerWidth - chatDialogSize.width) / 2,
        y: (window.innerHeight - chatDialogSize.height) / 2
      });
      loadAllChatAgents();
    }
  }, [showTeamChatDialog, currentProject]);

  useEffect(() => {
    if (selectedChatAgent && currentProject) {
      setSelectedPartner(null);
      setTeamChatMessages([]);
      loadChatPartners(selectedChatAgent);
    }
  }, [selectedChatAgent, currentProject]);

  useEffect(() => {
    if (selectedPartner && selectedChatAgent && currentProject) {
      loadMessagesBetween(selectedChatAgent, selectedPartner);
    }
  }, [selectedPartner, selectedChatAgent, currentProject]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging) {
        setChatDialogPos({
          x: e.clientX - dragOffset.x,
          y: e.clientY - dragOffset.y
        });
      }
      if (isResizing) {
        const newWidth = Math.max(600, e.clientX - chatDialogPos.x);
        const newHeight = Math.max(400, e.clientY - chatDialogPos.y);
        setChatDialogSize({ width: newWidth, height: newHeight });
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      setIsResizing(false);
    };

    if (isDragging || isResizing) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, isResizing, dragOffset, chatDialogPos]);

  // ============ 데이터 로딩 함수들 ============

  const loadSettingsData = async () => {
    if (!currentProject) return;

    try {
      const config = await api.getProjectConfig(currentProject.id);
      // 프로젝트 기본 노드 로드
      if (config.default_tools) {
        setDefaultTools(config.default_tools as string[]);
      } else {
        setDefaultTools([]);
      }
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const loadAllChatAgents = async () => {
    if (!currentProject) return;
    try {
      const res = await fetch(`http://localhost:8765/conversations/${currentProject.id}`);
      const data = await res.json();
      const agentList = data.conversations || [];
      const sortedAgents = [...agentList].sort((a: ChatAgent, b: ChatAgent) => {
        if (a.type === 'human' && b.type !== 'human') return -1;
        if (a.type !== 'human' && b.type === 'human') return 1;
        return a.name.localeCompare(b.name);
      });
      setChatAgents(sortedAgents);
    } catch (error) {
      console.error('에이전트 로드 실패:', error);
    }
  };

  const loadChatPartners = async (agentId: number) => {
    if (!currentProject) return;
    try {
      const res = await fetch(`http://localhost:8765/conversations/${currentProject.id}/${agentId}/partners`);
      const data = await res.json();
      setChatPartners(data.partners || []);
    } catch (error) {
      console.error('대화 상대 로드 실패:', error);
    }
  };

  const loadMessagesBetween = async (agent1Id: number, agent2Id: number) => {
    if (!currentProject) return;
    setTeamChatLoading(true);
    try {
      const res = await fetch(`http://localhost:8765/conversations/${currentProject.id}/between/${agent1Id}/${agent2Id}?limit=200`);
      const data = await res.json();
      setTeamChatMessages(data.messages || []);
    } catch (error) {
      console.error('대화 메시지 로드 실패:', error);
    } finally {
      setTeamChatLoading(false);
    }
  };

  // ============ 유틸리티 함수들 ============

  const addLog = (message: string) => {
    setLogs((prev) => [...prev, message]);
  };

  const getAgentNameById = (id: number): string => {
    const agent = chatAgents.find(a => a.id === id);
    return agent?.name || `Agent ${id}`;
  };

  // ============ 이벤트 핸들러들 ============

  const handleDragStart = (e: React.MouseEvent) => {
    setIsDragging(true);
    setDragOffset({
      x: e.clientX - chatDialogPos.x,
      y: e.clientY - chatDialogPos.y
    });
  };

  const handleResizeStart = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsResizing(true);
  };

  const handleStartAgent = async (agent: Agent) => {
    try {
      await api.startAgent(currentProject!.id, agent.id);
      setRunningAgents((prev) => new Set([...prev, agent.id]));
      addLog(`[시작] ${agent.name} 에이전트가 시작되었습니다.`);
    } catch (error) {
      addLog(`[오류] ${agent.name} 시작 실패: ${error}`);
    }
  };

  const handleStopAgent = async (agent: Agent) => {
    try {
      await api.stopAgent(currentProject!.id, agent.id);
      setRunningAgents((prev) => {
        const next = new Set(prev);
        next.delete(agent.id);
        return next;
      });
      addLog(`[중지] ${agent.name} 에이전트가 중지되었습니다.`);
    } catch (error) {
      addLog(`[오류] ${agent.name} 중지 실패: ${error}`);
    }
  };

  const handleStartAll = async () => {
    addLog('[시스템] 전체 에이전트 시작 중...');
    for (const agent of agents) {
      await handleStartAgent(agent);
    }
  };

  const handleStopAll = async () => {
    addLog('[시스템] 전체 에이전트 중지 중...');
    for (const agent of agents) {
      await handleStopAgent(agent);
    }
  };

  const handleToggleConnect = (agent: Agent) => {
    if (connectedAgentId === agent.id) {
      setConnectedAgentId(null);
      addLog(`[연결 해제] ${agent.name}`);
    } else {
      setConnectedAgentId(agent.id);
      addLog(`[연결됨] ${agent.name}`);
    }
  };

  const handleToggleOllama = async () => {
    if (ollamaRunning) {
      addLog('[Ollama] 서버 중지 중...');
      try {
        const result = await api.toggleOllama('stop');
        setOllamaRunning(result.running);
        addLog('[Ollama] ✅ 서버 중지 완료');
      } catch (error) {
        addLog(`[Ollama] ❌ 중지 실패: ${error}`);
      }
    } else {
      addLog('[Ollama] 서버 시작 중...');
      try {
        const result = await api.toggleOllama('start');
        setOllamaRunning(result.running);
        if (result.running) {
          addLog('[Ollama] ✅ 서버 시작 완료');
        } else {
          addLog('[Ollama] ⚠️ 서버 시작 확인 실패 (Ollama가 설치되어 있는지 확인하세요)');
        }
      } catch (error) {
        addLog(`[Ollama] ❌ 시작 실패: ${error}`);
      }
    }
  };

  const handleEditNote = async (agent: Agent) => {
    setEditingAgent(agent);
    try {
      const note = await api.getAgentNote(currentProject!.id, agent.id);
      setNoteContent(note || '');
    } catch {
      setNoteContent('');
    }
    setShowNoteDialog(true);
  };

  const handleSaveNote = async () => {
    if (!editingAgent) return;
    try {
      await api.saveAgentNote(currentProject!.id, editingAgent.id, noteContent);
      addLog(`[저장됨] ${editingAgent.name}의 영구 메모가 저장되었습니다.`);
      setShowNoteDialog(false);
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message :
        (typeof error === 'object' && error !== null ? (error as Record<string, unknown>).detail || (error as Record<string, unknown>).message || '알 수 없는 오류' : String(error));
      addLog(`[오류] 노트 저장 실패: ${errMsg}`);
    }
  };

  const handleToggleDefaultTool = (toolName: string) => {
    setDefaultTools(prev => {
      if (prev.includes(toolName)) {
        return prev.filter(t => t !== toolName);
      } else {
        return [...prev, toolName];
      }
    });
  };

  const handleSaveDefaultTools = async () => {
    if (!currentProject) return;
    try {
      await api.updateProjectConfig(currentProject.id, { default_tools: defaultTools });
      addLog(`[설정] 기본 노드가 저장되었습니다. (${defaultTools.length}개)`);
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message :
        (typeof error === 'object' && error !== null ? (error as Record<string, unknown>).detail || (error as Record<string, unknown>).message || '알 수 없는 오류' : String(error));
      addLog(`[오류] 기본 노드 저장 실패: ${errMsg}`);
    }
  };

  const handleEditAgentSettings = async (agent: Agent) => {
    setEditingAgentData(agent);

    let role = '';
    if (currentProject) {
      try {
        const roleData = await api.getAgentRole(currentProject.id, agent.id);
        role = roleData.role || '';
      } catch {
        // 역할 파일이 없을 수 있음
      }
    }

    let hasGmail = false;
    let hasNostr = false;
    let email = '';
    let gmailClientId = '';
    let gmailClientSecret = '';
    let nostrKeyName = '';
    let nostrPrivateKey = '';
    let nostrRelays = 'wss://relay.damus.io,wss://relay.nostr.band,wss://nos.lol';

    if (agent.channels && agent.channels.length > 0) {
      const gmailChannel = agent.channels.find(c => c.type === 'gmail');
      const nostrChannel = agent.channels.find(c => c.type === 'nostr');
      if (gmailChannel) {
        hasGmail = true;
        email = gmailChannel.email || '';
        gmailClientId = gmailChannel.client_id || '';
        gmailClientSecret = gmailChannel.client_secret || '';
      }
      if (nostrChannel) {
        hasNostr = true;
        nostrKeyName = nostrChannel.key_name || '';
        nostrPrivateKey = nostrChannel.private_key || '';
        nostrRelays = nostrChannel.relays?.join(',') || nostrRelays;
      }
    } else if (agent.channel) {
      if (agent.channel === 'gmail') {
        hasGmail = true;
        email = agent.email || '';
        if (agent.gmail) {
          gmailClientId = agent.gmail.client_id || '';
          gmailClientSecret = agent.gmail.client_secret || '';
        }
      }
      if (agent.channel === 'nostr' || agent.nostr) {
        hasNostr = true;
        if (agent.nostr) {
          nostrKeyName = agent.nostr.key_name || '';
          nostrPrivateKey = agent.nostr.private_key || '';
          nostrRelays = agent.nostr.relays?.join(',') || nostrRelays;
        }
      }
    }

    setAgentForm({
      name: agent.name,
      type: agent.type || 'internal',
      provider: agent.ai?.provider || 'google',
      model: agent.ai?.model || 'gemini-2.0-flash-exp',
      apiKey: agent.ai?.api_key || '',
      role,
      hasGmail,
      hasNostr,
      email,
      gmailClientId,
      gmailClientSecret,
      nostrKeyName,
      nostrPrivateKey,
      nostrRelays,
      allowedNodes: [...(agent.allowed_nodes || [])],
    });

    setShowAgentEditDialog(true);
  };

  const handleAddAgentSettings = async () => {
    setEditingAgentData(null);
    setAgentForm({
      name: '',
      type: 'internal',
      provider: 'google',
      model: 'gemini-2.0-flash-exp',
      apiKey: '',
      role: '',
      hasGmail: false,
      hasNostr: false,
      email: '',
      gmailClientId: '',
      gmailClientSecret: '',
      nostrKeyName: '',
      nostrPrivateKey: '',
      nostrRelays: 'wss://relay.damus.io,wss://relay.nostr.band,wss://nos.lol',
      allowedNodes: [],
    });

    setShowAgentEditDialog(true);
  };

  const handleSaveAgentSettings = async () => {
    if (!agentForm.name.trim()) {
      addLog('[오류] 에이전트 이름을 입력하세요.');
      return;
    }

    if (!currentProject) return;

    try {
      let gmail: Record<string, string> | undefined;
      let nostr: Record<string, unknown> | undefined;
      const channels: Array<Record<string, unknown>> = [];

      if (agentForm.type === 'external') {
        if (agentForm.hasGmail) {
          gmail = {
            client_id: agentForm.gmailClientId,
            client_secret: agentForm.gmailClientSecret,
          };
          channels.push({
            type: 'gmail',
            email: agentForm.email,
            client_id: agentForm.gmailClientId,
            client_secret: agentForm.gmailClientSecret,
          });
        }
        if (agentForm.hasNostr) {
          nostr = {
            key_name: agentForm.nostrKeyName,
            private_key: agentForm.nostrPrivateKey,
            relays: agentForm.nostrRelays.split(',').map(r => r.trim()).filter(r => r),
          };
          channels.push({
            type: 'nostr',
            key_name: agentForm.nostrKeyName,
            private_key: agentForm.nostrPrivateKey,
            relays: agentForm.nostrRelays.split(',').map(r => r.trim()).filter(r => r),
          });
        }
      }

      const primaryChannel = agentForm.hasGmail ? 'gmail' : (agentForm.hasNostr ? 'nostr' : undefined);

      const agentData = {
        name: agentForm.name,
        type: agentForm.type,
        provider: agentForm.provider,
        model: agentForm.model,
        api_key: agentForm.apiKey || undefined,
        role: agentForm.role || undefined,
        allowed_nodes: agentForm.allowedNodes.length > 0 ? agentForm.allowedNodes : undefined,
        channel: primaryChannel,
        email: agentForm.email || undefined,
        gmail,
        nostr,
        channels: channels.length > 0 ? channels : undefined,
      };

      if (editingAgentData) {
        await api.updateAgent(currentProject.id, editingAgentData.id, agentData);
        addLog(`[설정] 에이전트 '${agentForm.name}' 업데이트됨`);
      } else {
        await api.createAgent(currentProject.id, agentData);
        addLog(`[설정] 에이전트 '${agentForm.name}' 생성됨`);
      }

      setShowAgentEditDialog(false);
      loadAgents(currentProject.id);
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message :
        (typeof error === 'object' && error !== null ? (error as Record<string, unknown>).detail || (error as Record<string, unknown>).message || '알 수 없는 오류' : String(error));
      addLog(`[오류] 에이전트 저장 실패: ${errMsg}`);
    }
  };

  const handleDeleteAgentSettings = async (agent: Agent) => {
    if (!confirm(`'${agent.name}' 에이전트를 삭제하시겠습니까?`)) return;
    if (!currentProject) return;

    try {
      await api.deleteAgent(currentProject.id, agent.id);
      addLog(`[설정] 에이전트 '${agent.name}' 삭제됨`);
      loadAgents(currentProject.id);
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message :
        (typeof error === 'object' && error !== null ? (error as Record<string, unknown>).detail || (error as Record<string, unknown>).message || '알 수 없는 오류' : String(error));
      addLog(`[오류] 에이전트 삭제 실패: ${errMsg}`);
    }
  };

  const handleAutoAssignTools = async () => {
    if (!currentProject) return;

    if (!confirm('시스템 AI가 모든 에이전트의 노드를 재배분합니다.\n기존에 수동으로 설정한 노드도 덮어씌워집니다.\n\n계속하시겠습니까?')) return;

    try {
      addLog('[설정] 노드 자동 배분 시작...');
      const result = await api.autoAssignTools(currentProject.id);
      if (result.status === 'success') {
        addLog('[설정] 노드 자동 배분이 완료되었습니다.');
        loadAgents(currentProject.id);
      } else {
        addLog(`[오류] ${result.status}`);
      }
    } catch (error) {
      addLog(`[오류] 노드 자동 배분 실패: ${error}`);
    }
  };

  const handleCreateSwitch = async () => {
    if (!switchForm.name || !switchForm.command || !switchForm.agentName) {
      addLog('[오류] 모든 필드를 입력하세요.');
      return;
    }
    try {
      await api.createSwitch(
        switchForm.name,
        switchForm.command,
        { projectId: currentProject!.id, agentName: switchForm.agentName },
        switchForm.icon
      );
      addLog(`[스위치 생성] '${switchForm.name}' 스위치가 생성되었습니다!`);
      setSwitchForm({ name: '', icon: '⚡', command: '', agentName: '' });
      loadSwitches();  // 목록 새로고침
    } catch (error) {
      addLog(`[오류] 스위치 생성 실패: ${error}`);
    }
  };

  const handleUpdateSwitch = async () => {
    if (!editingSwitch) return;
    if (!switchForm.name || !switchForm.command) {
      addLog('[오류] 이름과 명령어를 입력하세요.');
      return;
    }
    try {
      await api.updateSwitch(editingSwitch.id, {
        name: switchForm.name,
        command: switchForm.command,
        icon: switchForm.icon,
      });
      addLog(`[스위치 수정] '${switchForm.name}' 스위치가 수정되었습니다!`);
      setEditingSwitch(null);
      setSwitchForm({ name: '', icon: '⚡', command: '', agentName: '' });
      loadSwitches();  // 목록 새로고침
    } catch (error) {
      addLog(`[오류] 스위치 수정 실패: ${error}`);
    }
  };

  const handleEditSwitch = (switchItem: Switch) => {
    setEditingSwitch(switchItem);
    setSwitchForm({
      name: switchItem.name,
      icon: switchItem.icon || '⚡',
      command: switchItem.command,
      agentName: (switchItem.config?.agent_name as string) || '',
    });
    setShowSwitchDialog(true);
  };

  // ============ 렌더링 ============

  if (!currentProject) {
    return (
      <div className="h-full flex items-center justify-center bg-[#F5F1EB]">
        <p className="text-[#6B5B4F]">프로젝트를 선택해주세요.</p>
      </div>
    );
  }

  const connectedAgent = agents.find((a) => a.id === connectedAgentId);

  // 현재 프로젝트의 스위치만 필터링
  const projectSwitches = switches.filter(
    (sw) => sw.config?.projectId === currentProject.id
  );

  return (
    <div className="h-full flex flex-col bg-[#F5F1EB]">
      {/* 헤더 */}
      <div className="h-12 flex items-center justify-between px-4 bg-[#EAE4DA] border-b border-[#E5DFD5] drag">
        <div className="flex items-center gap-2 no-drag">
          <button
            onClick={() => {
              setCurrentAgent(null);
              setCurrentView('launcher');
            }}
            className="p-2 rounded-lg hover:bg-[#DDD5C8] transition-colors text-[#6B5B4F]"
            title="뒤로"
          >
            <ArrowLeft size={20} />
          </button>
          <span className="font-semibold text-[#4A4035]">{currentProject.name}</span>
        </div>

        <div className="flex items-center gap-1 no-drag">
          <button
            onClick={() => setShowSettingsDialog(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-[#DDD5C8] transition-colors text-[#6B5B4F]"
            title="설정"
          >
            <Settings size={16} />
            <span className="text-sm">설정</span>
          </button>

          <button
            onClick={() => setShowTeamChatDialog(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500 hover:bg-purple-600 transition-colors text-white"
            title="팀내 대화"
          >
            <Users size={16} />
            <span className="text-sm">팀내 대화</span>
          </button>

          <button
            onClick={() => setShowSwitchDialog(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#D97706] hover:bg-[#B45309] transition-colors text-white"
            title="스위치"
          >
            <Zap size={16} />
            <span className="text-sm">스위치</span>
          </button>

          <button
            onClick={handleStartAll}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-500 hover:bg-green-600 transition-colors text-white"
            title="전체 시작"
          >
            <PlayCircle size={16} />
            <span className="text-sm">전체 시작</span>
          </button>

          <button
            onClick={handleStopAll}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500 hover:bg-red-600 transition-colors text-white"
            title="전체 중지"
          >
            <StopCircle size={16} />
            <span className="text-sm">전체 중지</span>
          </button>

          <button
            onClick={handleToggleOllama}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors text-white ${
              ollamaRunning ? 'bg-orange-500 hover:bg-orange-600' : 'bg-blue-500 hover:bg-blue-600'
            }`}
            title={ollamaRunning ? 'Ollama 중지' : 'Ollama 시작'}
          >
            {ollamaRunning ? <ServerOff size={16} /> : <Server size={16} />}
            <span className="text-sm">{ollamaRunning ? 'Ollama 중지' : 'Ollama 시작'}</span>
          </button>
        </div>
      </div>

      {/* 메인 영역 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 사이드바 - 에이전트 목록 */}
        <div className="w-72 bg-[#EAE4DA] border-r border-[#E5DFD5] flex flex-col">
          <div className="p-3 border-b border-[#E5DFD5]">
            <h3 className="text-sm font-semibold text-[#6B5B4F]">에이전트 목록</h3>
          </div>
          <div className="flex-1 overflow-auto">
            {agents.length === 0 ? (
              <div className="p-4 text-center text-[#A09080]">에이전트가 없습니다</div>
            ) : (
              agents.map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  isRunning={runningAgents.has(agent.id)}
                  isConnected={connectedAgentId === agent.id}
                  isSelected={currentAgent?.id === agent.id}
                  onSelect={() => setCurrentAgent(agent)}
                  onToggleConnect={() => handleToggleConnect(agent)}
                  onStart={() => handleStartAgent(agent)}
                  onStop={() => handleStopAgent(agent)}
                  onEditNote={() => handleEditNote(agent)}
                />
              ))
            )}
          </div>
        </div>

        {/* 오른쪽 - 채팅/로그 */}
        {connectedAgent && currentProject ? (
          <Chat projectId={currentProject.id} agent={connectedAgent} />
        ) : (
          <div className="flex-1 flex flex-col bg-[#F5F1EB]">
            <div className="flex-1 flex flex-col overflow-hidden">
              <div className="px-4 py-2 border-b border-[#E5DFD5] bg-[#EAE4DA]">
                <span className="text-sm font-semibold text-[#6B5B4F]">실행 로그</span>
              </div>
              <div className="flex-1 overflow-auto p-3 font-mono text-base text-[#6B5B4F]">
                {logs.length === 0 ? (
                  <p className="text-[#A09080]">에이전트에 연결하여 채팅을 시작하세요.</p>
                ) : (
                  logs.map((log, i) => (
                    <div key={i} className="py-1 chat-markdown">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          a: ({ href, children }) => (
                            <a
                              href={href}
                              onClick={(e) => {
                                e.preventDefault();
                                if (href) {
                                  window.electron?.openExternal(href);
                                }
                              }}
                              className="text-blue-500 hover:underline cursor-pointer"
                            >
                              {children}
                            </a>
                          ),
                        }}
                      >
                        {log}
                      </ReactMarkdown>
                    </div>
                  ))
                )}
                <div ref={logsEndRef} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 다이얼로그들 */}
      <SwitchDialog
        show={showSwitchDialog}
        onClose={() => {
          setShowSwitchDialog(false);
          setEditingSwitch(null);
          setSwitchForm({ name: '', icon: '⚡', command: '', agentName: '' });
        }}
        switchForm={switchForm}
        setSwitchForm={setSwitchForm}
        agents={agents}
        onCreateSwitch={handleCreateSwitch}
        onUpdateSwitch={handleUpdateSwitch}
        editingSwitch={editingSwitch}
        projectSwitches={projectSwitches}
        onEditSwitch={handleEditSwitch}
        onCancelEdit={() => setEditingSwitch(null)}
      />

      <NoteDialog
        show={showNoteDialog}
        onClose={() => setShowNoteDialog(false)}
        editingAgent={editingAgent}
        noteContent={noteContent}
        setNoteContent={setNoteContent}
        onSaveNote={handleSaveNote}
      />

      <SettingsDialog
        show={showSettingsDialog}
        onClose={() => setShowSettingsDialog(false)}
        settingsTab={settingsTab}
        setSettingsTab={setSettingsTab}
        agents={agents}
        runningAgents={runningAgents}
        onAddAgentSettings={handleAddAgentSettings}
        onEditAgentSettings={handleEditAgentSettings}
        onDeleteAgentSettings={handleDeleteAgentSettings}
        onAutoAssignTools={handleAutoAssignTools}
        defaultTools={defaultTools}
        onToggleDefaultTool={handleToggleDefaultTool}
        onSaveDefaultTools={handleSaveDefaultTools}
      />

      <AgentEditDialog
        show={showAgentEditDialog}
        onClose={() => setShowAgentEditDialog(false)}
        editingAgentData={editingAgentData}
        agentForm={agentForm}
        setAgentForm={setAgentForm}
        onSaveAgentSettings={handleSaveAgentSettings}
      />

      <TeamChatDialog
        show={showTeamChatDialog}
        onClose={() => setShowTeamChatDialog(false)}
        chatDialogSize={chatDialogSize}
        chatDialogPos={chatDialogPos}
        chatAgents={chatAgents}
        selectedChatAgent={selectedChatAgent}
        setSelectedChatAgent={setSelectedChatAgent}
        chatPartners={chatPartners}
        selectedPartner={selectedPartner}
        setSelectedPartner={setSelectedPartner}
        teamChatMessages={teamChatMessages}
        teamChatLoading={teamChatLoading}
        getAgentNameById={getAgentNameById}
        onRefresh={() => selectedPartner && selectedChatAgent && loadMessagesBetween(selectedChatAgent, selectedPartner)}
        onDragStart={handleDragStart}
        onResizeStart={handleResizeStart}
      />
    </div>
  );
}
