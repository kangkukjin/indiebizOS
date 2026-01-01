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
import { useAppStore } from '../stores/appStore';
import { api } from '../lib/api';
import { Chat } from './Chat';
import type { Agent } from '../types';

// 모듈화된 컴포넌트 임포트
import {
  AgentCard,
  SwitchDialog,
  NoteDialog,
  ToolAIDialog,
  AutoPromptDialog,
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
  ToolAIForm,
  Tool,
  ToolSettings,
  GeneratedPrompts,
  SystemAIConfig,
} from './manager-dialogs';

export function Manager() {
  const {
    currentProject,
    agents,
    currentAgent,
    loadAgents,
    setCurrentAgent,
    setCurrentView,
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

  // 스위치 생성 폼
  const [switchForm, setSwitchForm] = useState<SwitchForm>({
    name: '',
    icon: '⚡',
    command: '',
    agentName: '',
  });

  // 설정 다이얼로그 상태
  const [settingsTab, setSettingsTab] = useState<'channels' | 'tools' | 'agents' | 'common'>('agents');
  const [commonSettings, setCommonSettings] = useState('');
  const [tools, setTools] = useState<Tool[]>([]);
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
    allowedTools: [],
  });
  const [allTools, setAllTools] = useState<Tool[]>([]);
  const [baseTools, setBaseTools] = useState<string[]>([]);
  const [defaultTools, setDefaultTools] = useState<string[]>([]);

  // 도구 AI 설정 다이얼로그 상태
  const [showToolAIDialog, setShowToolAIDialog] = useState(false);
  const [editingToolAI, setEditingToolAI] = useState<{ name: string; config_key: string } | null>(null);
  const [toolAIForm, setToolAIForm] = useState<ToolAIForm>({
    provider: 'gemini',
    model: 'gemini-2.0-flash',
    apiKey: '',
  });
  const [toolSettings, setToolSettings] = useState<ToolSettings>({});

  // 자동 프롬프트 다이얼로그 상태
  const [showAutoPromptDialog, setShowAutoPromptDialog] = useState(false);
  const [projectPurpose, setProjectPurpose] = useState('');
  const [autoPromptLoading, setAutoPromptLoading] = useState(false);
  const [generatedPrompts, setGeneratedPrompts] = useState<GeneratedPrompts | null>(null);
  const [agentRoleDescriptions, setAgentRoleDescriptions] = useState<Record<string, string>>({});
  const [systemAiConfig, setSystemAiConfig] = useState<SystemAIConfig | null>(null);

  // ============ useEffect 훅들 ============

  useEffect(() => {
    if (currentProject) {
      loadAgents(currentProject.id);
    }
  }, [currentProject, loadAgents]);

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
    const loadSystemAiConfig = async () => {
      try {
        const config = await api.getSystemAI();
        setSystemAiConfig({
          provider: config.provider,
          model: config.model,
          apiKey: config.apiKey,
        });
      } catch {
        // 무시
      }
    };
    loadSystemAiConfig();
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
      const toolsResponse = await api.getTools();
      if (toolsResponse && toolsResponse.tools) {
        setTools(toolsResponse.tools);
        setAllTools(toolsResponse.tools);
        setBaseTools(toolsResponse.base_tools || []);
      }

      try {
        const settings = await api.getToolSettings();
        setToolSettings(settings);
      } catch {
        // 설정 없으면 무시
      }

      const config = await api.getProjectConfig(currentProject.id);
      if (config.common_settings) {
        setCommonSettings(config.common_settings as string);
      }
      // 프로젝트 기본 도구 로드
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
    } catch (error) {
      addLog(`[오류] 노트 저장 실패: ${error}`);
    }
  };

  const handleSaveCommonSettings = async () => {
    if (!currentProject) return;
    try {
      await api.updateProjectConfig(currentProject.id, { common_settings: commonSettings });
      addLog('[설정] 공통 설정이 저장되었습니다.');
    } catch (error) {
      addLog(`[오류] 공통 설정 저장 실패: ${error}`);
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
      addLog(`[설정] 기본 도구가 저장되었습니다. (${defaultTools.length}개)`);
    } catch (error) {
      addLog(`[오류] 기본 도구 저장 실패: ${error}`);
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
      allowedTools: agent.allowed_tools || [],
    });

    try {
      const toolsResponse = await api.getTools();
      if (toolsResponse && toolsResponse.tools) {
        setAllTools(toolsResponse.tools);
        setBaseTools(toolsResponse.base_tools || []);
      }
    } catch {
      // 무시
    }

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
      allowedTools: [],
    });

    try {
      const toolsResponse = await api.getTools();
      if (toolsResponse && toolsResponse.tools) {
        setAllTools(toolsResponse.tools);
        setBaseTools(toolsResponse.base_tools || []);
      }
    } catch {
      // 무시
    }

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
        allowed_tools: agentForm.allowedTools.length > 0 ? agentForm.allowedTools : undefined,
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
    } catch (error) {
      addLog(`[오류] 에이전트 저장 실패: ${error}`);
    }
  };

  const handleDeleteAgentSettings = async (agent: Agent) => {
    if (!confirm(`'${agent.name}' 에이전트를 삭제하시겠습니까?`)) return;
    if (!currentProject) return;

    try {
      await api.deleteAgent(currentProject.id, agent.id);
      addLog(`[설정] 에이전트 '${agent.name}' 삭제됨`);
      loadAgents(currentProject.id);
    } catch (error) {
      addLog(`[오류] 에이전트 삭제 실패: ${error}`);
    }
  };

  const handleAutoAssignTools = async () => {
    if (!currentProject) return;

    if (!confirm('시스템 AI가 모든 에이전트의 도구를 재배분합니다.\n기존에 수동으로 설정한 도구도 덮어씌워집니다.\n\n계속하시겠습니까?')) return;

    try {
      addLog('[설정] 도구 자동 배분 시작...');
      const result = await api.autoAssignTools(currentProject.id);
      if (result.status === 'success') {
        addLog('[설정] 도구 자동 배분이 완료되었습니다.');
        loadAgents(currentProject.id);
      } else {
        addLog(`[오류] ${result.status}`);
      }
    } catch (error) {
      addLog(`[오류] 도구 자동 배분 실패: ${error}`);
    }
  };

  const handleEditToolAI = async (tool: Tool) => {
    const configKey = tool.ai_config_key || tool.name;
    setEditingToolAI({ name: tool.name, config_key: configKey });

    try {
      const settings = await api.getToolSetting(configKey);
      setToolAIForm({
        provider: settings.provider || 'gemini',
        model: settings.model || 'gemini-2.0-flash',
        apiKey: settings.api_key || '',
      });
    } catch {
      setToolAIForm({
        provider: 'gemini',
        model: 'gemini-2.0-flash',
        apiKey: '',
      });
    }

    setShowToolAIDialog(true);
  };

  const handleSaveToolAI = async () => {
    if (!editingToolAI) return;

    try {
      await api.updateToolSetting(editingToolAI.config_key, {
        provider: toolAIForm.provider,
        model: toolAIForm.model,
        api_key: toolAIForm.apiKey,
      });
      addLog(`[설정] ${editingToolAI.name} 도구 AI 설정이 저장되었습니다.`);
      setShowToolAIDialog(false);
      setEditingToolAI(null);
      const settings = await api.getToolSettings();
      setToolSettings(settings);
    } catch (error) {
      addLog(`[오류] 도구 AI 설정 저장 실패: ${error}`);
    }
  };

  const handleAutoPrompt = () => {
    if (agents.length === 0) {
      addLog('[오류] 등록된 에이전트가 없습니다. 먼저 에이전트를 추가하세요.');
      return;
    }
    setProjectPurpose('범용');
    setGeneratedPrompts(null);
    const initialDescriptions: Record<string, string> = {};
    agents.forEach(agent => {
      initialDescriptions[agent.name] = agent.role_description || '';
    });
    setAgentRoleDescriptions(initialDescriptions);
    setShowAutoPromptDialog(true);
  };

  const handleSaveRoleDescriptions = async () => {
    if (!currentProject) return;

    try {
      const descriptionsToSave: Record<string, string> = {};
      Object.entries(agentRoleDescriptions).forEach(([name, desc]) => {
        if (desc.trim()) {
          descriptionsToSave[name] = desc.trim();
        }
      });

      if (Object.keys(descriptionsToSave).length > 0) {
        const result = await api.updateRoleDescriptions(currentProject.id, descriptionsToSave);
        addLog(`[저장] 역할 설명이 저장되었습니다. (${result.updated_agents?.join(', ') || ''})`);
        await loadAgents(currentProject.id);
      } else {
        addLog('[알림] 저장할 역할 설명이 없습니다.');
      }
    } catch (error) {
      const errMsg = error instanceof Error ? error.message : JSON.stringify(error);
      addLog(`[오류] 역할 설명 저장 실패: ${errMsg}`);
    }
  };

  const handleGeneratePrompts = async () => {
    if (!currentProject) {
      addLog('[오류] 프로젝트가 선택되지 않았습니다.');
      return;
    }

    setAutoPromptLoading(true);
    try {
      const agentList = agents.map(agent => ({
        name: agent.name,
        role_description: agentRoleDescriptions[agent.name]?.trim() ||
          `${agent.type === 'external' ? '외부 사용자와 소통하는' : '내부 작업을 처리하는'} 에이전트`,
        type: agent.type
      }));

      const result = await api.generatePrompts(currentProject.id, {
        project_purpose: projectPurpose.trim() || '범용',
        agents: agentList,
        use_ai: true,
        ai_config: systemAiConfig ? {
          provider: systemAiConfig.provider,
          model: systemAiConfig.model,
          api_key: systemAiConfig.apiKey,
        } : undefined
      });

      if (result.common_settings && result.agent_roles) {
        setGeneratedPrompts({
          common_settings: result.common_settings,
          agent_roles: result.agent_roles
        });
        addLog('[프롬프트] 미리보기가 생성되었습니다.');
      } else {
        addLog(`[오류] 응답 형식이 올바르지 않습니다: ${JSON.stringify(result)}`);
      }
    } catch (error) {
      addLog(`[오류] 프롬프트 생성 실패: ${error instanceof Error ? error.message : error}`);
    } finally {
      setAutoPromptLoading(false);
    }
  };

  const handleSavePrompts = async () => {
    if (!currentProject) return;
    if (!generatedPrompts) {
      addLog('[오류] 저장할 프롬프트가 없습니다. 먼저 미리보기를 생성하세요.');
      return;
    }

    setAutoPromptLoading(true);
    try {
      const result = await api.savePrompts(currentProject.id, {
        common_settings: generatedPrompts.common_settings,
        agent_roles: generatedPrompts.agent_roles
      });

      const fileNames = typeof result.saved_files === 'object'
        ? Object.keys(result.saved_files)
        : result.saved_files;
      addLog(`[프롬프트] 저장 완료: ${Array.isArray(fileNames) ? fileNames.join(', ') : fileNames}`);
      setShowAutoPromptDialog(false);
    } catch (error) {
      addLog(`[오류] 프롬프트 저장 실패: ${error instanceof Error ? error.message : error}`);
    } finally {
      setAutoPromptLoading(false);
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
      setShowSwitchDialog(false);
      setSwitchForm({ name: '', icon: '⚡', command: '', agentName: '' });
    } catch (error) {
      addLog(`[오류] 스위치 생성 실패: ${error}`);
    }
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
        onClose={() => setShowSwitchDialog(false)}
        switchForm={switchForm}
        setSwitchForm={setSwitchForm}
        agents={agents}
        onCreateSwitch={handleCreateSwitch}
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
        onAutoPrompt={handleAutoPrompt}
        onAutoAssignTools={handleAutoAssignTools}
        tools={tools}
        toolSettings={toolSettings}
        onEditToolAI={handleEditToolAI}
        defaultTools={defaultTools}
        onToggleDefaultTool={handleToggleDefaultTool}
        onSaveDefaultTools={handleSaveDefaultTools}
        commonSettings={commonSettings}
        setCommonSettings={setCommonSettings}
        onSaveCommonSettings={handleSaveCommonSettings}
      />

      <ToolAIDialog
        show={showToolAIDialog}
        onClose={() => setShowToolAIDialog(false)}
        editingToolAI={editingToolAI}
        toolAIForm={toolAIForm}
        setToolAIForm={setToolAIForm}
        onSaveToolAI={handleSaveToolAI}
      />

      <AutoPromptDialog
        show={showAutoPromptDialog}
        onClose={() => setShowAutoPromptDialog(false)}
        agents={agents}
        projectPurpose={projectPurpose}
        setProjectPurpose={setProjectPurpose}
        agentRoleDescriptions={agentRoleDescriptions}
        setAgentRoleDescriptions={setAgentRoleDescriptions}
        autoPromptLoading={autoPromptLoading}
        generatedPrompts={generatedPrompts}
        onGeneratePrompts={handleGeneratePrompts}
        onSavePrompts={handleSavePrompts}
        onSaveRoleDescriptions={handleSaveRoleDescriptions}
      />

      <AgentEditDialog
        show={showAgentEditDialog}
        onClose={() => setShowAgentEditDialog(false)}
        editingAgentData={editingAgentData}
        agentForm={agentForm}
        setAgentForm={setAgentForm}
        allTools={allTools}
        baseTools={baseTools}
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
