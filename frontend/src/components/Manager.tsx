/**
 * 매니저 - 프로젝트 내 에이전트 관리
 * 원본 manager.py의 기능을 React로 구현
 */

import { useCallback, useEffect, useState, useRef } from 'react';
import {
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
import { useRetryingLoad } from '../lib/use-retrying-load';
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

interface ManagerProps {
  initialAgent?: string | null;
}

// ── 팀내 대화 창의 경계 ──
// 이 창은 프로젝트 창 안에 사는 DOM 이라 창 밖으로 나간 부분은 그려질 자리가 없다(잘린다).
// 그래서 '자를지'가 아니라 '나가지 못하게' 가 답 — 열 때·끌 때·크기 바꿀 때·창 크기가
// 변할 때 모두 이 관문 하나를 지난다(2026-09-02 사용자 신고: 끌면 잘려 나갔다).
const CHAT_MARGIN_X = 16;       // 좌우 여백
const CHAT_MARGIN_TOP = 56;     // 상단 여백(창 드래그바 h-12=48px 아래)
const CHAT_MARGIN_BOTTOM = 16;  // 하단 여백
const CHAT_MIN_WIDTH = 600;
const CHAT_MIN_HEIGHT = 400;

function clampChatDialog(
  pos: { x: number; y: number },
  size: { width: number; height: number },
) {
  const maxW = Math.max(320, window.innerWidth - CHAT_MARGIN_X * 2);
  const maxH = Math.max(320, window.innerHeight - CHAT_MARGIN_TOP - CHAT_MARGIN_BOTTOM);
  const width = Math.min(size.width, maxW);
  const height = Math.min(size.height, maxH);
  const maxX = Math.max(CHAT_MARGIN_X, window.innerWidth - width - CHAT_MARGIN_X);
  const maxY = Math.max(CHAT_MARGIN_TOP, window.innerHeight - height - CHAT_MARGIN_BOTTOM);
  return {
    size: { width, height },
    pos: {
      x: Math.min(Math.max(CHAT_MARGIN_X, pos.x), maxX),
      y: Math.min(Math.max(CHAT_MARGIN_TOP, pos.y), maxY),
    },
  };
}

export function Manager({ initialAgent }: ManagerProps = {}) {
  const {
    currentProject,
    agents,
    currentAgent,
    loadAgents,
    setCurrentAgent,
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

  // 프로젝트 진입 시 에이전트·스위치·default_tools 로드.
  // loadAgents/loadSwitches(스토어)는 실패를 삼키므로, 같은 백엔드로 가는
  // getProjectConfig 의 실패 전파가 셋을 함께 재시도시킨다.
  const loadProjectData = useCallback(async () => {
    if (!currentProject) return;
    const [config] = await Promise.all([
      api.getProjectConfig(currentProject.id),
      loadAgents(currentProject.id),
      loadSwitches(),  // 스위치 로드
    ]);
    setDefaultTools((config.default_tools as string[]) || []);
  }, [currentProject, loadAgents, loadSwitches]);
  useRetryingLoad(loadProjectData, { enabled: !!currentProject });

  // 모델 기어/프리셋/핀이 계기판(별도 창)에서 바뀌면 에이전트 카드의 effective_model 을 갱신.
  // 계기판이 같은 origin localStorage 를 bump → 이 창에서 storage 이벤트 수신 → 재조회.
  useEffect(() => {
    const onGearChange = (e: StorageEvent) => {
      if (e.key === '__model_gear_rev' && currentProject) {
        loadAgents(currentProject.id);
      }
    };
    window.addEventListener('storage', onGearChange);
    return () => window.removeEventListener('storage', onGearChange);
  }, [currentProject, loadAgents]);

  // 실행 상태 재동기화 — 백엔드 등기부가 진실 (GET /agents 의 running 필드).
  // 이 Set 은 원래 시작/중지 버튼만 갱신하는 화면 로컬 상태라, 백엔드가 재기동해
  // 등기부가 비워지면 '실행 중' 거짓 표시가 남았다 (2026-08-10 진단). 목록을 읽어올
  // 때마다 서버 값으로 덮어써 드리프트를 없앤다.
  useEffect(() => {
    setRunningAgents(new Set(agents.filter((a) => a.running).map((a) => a.id)));
  }, [agents]);

  // 창 복귀 시 목록 재조회 — 자리 비운 사이의 백엔드 재기동을 화면이 알아채는 경로.
  useEffect(() => {
    if (!currentProject) return;
    const onFocus = () => loadAgents(currentProject.id);
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [currentProject, loadAgents]);

  // 에이전트 자동 활성화 헬퍼: 선택 + 시작 + 연결
  const autoActivateAgent = async (target: Agent) => {
    setCurrentAgent(target);
    // ★화면 상태(runningAgents)를 믿지 않는다 — 백엔드 재기동 후 거짓 '실행 중'이
    // 남을 수 있다(2026-08-10). startAgent 는 already_running 을 돌려주는 멱등
    // 호출이라 무조건 부르는 게 안전하다.
    if (currentProject) {
      try {
        await api.startAgent(currentProject.id, target.id);
        setRunningAgents(prev => new Set([...prev, target.id]));
        addLog(`[자동 시작] ${target.name} 에이전트 (스케줄 결과 전달)`);
      } catch {
        // 시작 실패해도 연결은 진행 — 백엔드 WS 쪽 자동 시작이 한 번 더 받쳐준다
        setRunningAgents(prev => new Set([...prev, target.id]));
      }
    }
    // 대화 연결
    setConnectedAgentId(target.id);
  };

  // initialAgent가 있으면 해당 에이전트 자동 활성화 (스케줄 결과 전달용)
  useEffect(() => {
    if (initialAgent && agents.length > 0) {
      const target = agents.find(a => a.name === initialAgent || a.id === initialAgent);
      if (target && connectedAgentId !== target.id) {
        autoActivateAgent(target);
      }
    }
  }, [initialAgent, agents]);

  // Electron IPC: select-agent 메시지 수신 (이미 열린 창에서 에이전트 전환)
  useEffect(() => {
    const electronApi = (window as any).electron;
    if (!electronApi?.onSelectAgent) return;

    const handleSelectAgent = (agentName: string) => {
      if (agentName && agents.length > 0) {
        const target = agents.find(a => a.name === agentName || a.id === agentName);
        if (target) {
          autoActivateAgent(target);
        }
      }
    };

    electronApi.onSelectAgent(handleSelectAgent);
    return () => {
      electronApi.removeSelectAgentListener?.();
    };
  }, [agents]);

  const checkOllamaStatus = useCallback(async () => {
    const status = await api.getOllamaStatus();
    setOllamaRunning(status.running);
  }, []);
  useRetryingLoad(checkOllamaStatus);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  useEffect(() => {
    if (showTeamChatDialog && currentProject) {
      // 창 한가운데에 놓고 관문 통과 — 창이 900×600 보다 작아도 잘리지 않는다.
      const wanted = { width: 900, height: 600 };
      const centered = {
        x: Math.round((window.innerWidth - wanted.width) / 2),
        y: Math.round((window.innerHeight - wanted.height) / 2),
      };
      const { pos, size } = clampChatDialog(centered, wanted);
      setChatDialogSize(size);
      setChatDialogPos(pos);
    }
  }, [showTeamChatDialog, currentProject]);

  // 창 크기가 바뀌면 다이얼로그를 다시 창 안으로 — 줄인 창 밖에 남아 잘리지 않게.
  useEffect(() => {
    if (!showTeamChatDialog) return;
    const onResize = () => {
      const { pos, size } = clampChatDialog(chatDialogPos, chatDialogSize);
      if (pos.x !== chatDialogPos.x || pos.y !== chatDialogPos.y) setChatDialogPos(pos);
      if (size.width !== chatDialogSize.width || size.height !== chatDialogSize.height) setChatDialogSize(size);
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [showTeamChatDialog, chatDialogPos, chatDialogSize]);

  // 대화 에이전트가 바뀌면 상대·메시지 선택을 초기화 (조회는 아래 useRetryingLoad 가 담당)
  useEffect(() => {
    if (selectedChatAgent && currentProject) {
      setSelectedPartner(null);
      setTeamChatMessages([]);
    }
  }, [selectedChatAgent, currentProject]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging) {
        setChatDialogPos(clampChatDialog(
          { x: e.clientX - dragOffset.x, y: e.clientY - dragOffset.y },
          chatDialogSize,
        ).pos);
      }
      if (isResizing) {
        // 오른쪽·아래 모서리 잡기 — 창 오른쪽/아래 여백까지만 자란다.
        const maxWidth = Math.max(CHAT_MIN_WIDTH, window.innerWidth - CHAT_MARGIN_X - chatDialogPos.x);
        const maxHeight = Math.max(CHAT_MIN_HEIGHT, window.innerHeight - CHAT_MARGIN_BOTTOM - chatDialogPos.y);
        setChatDialogSize({
          width: Math.min(maxWidth, Math.max(CHAT_MIN_WIDTH, e.clientX - chatDialogPos.x)),
          height: Math.min(maxHeight, Math.max(CHAT_MIN_HEIGHT, e.clientY - chatDialogPos.y)),
        });
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
  }, [isDragging, isResizing, dragOffset, chatDialogPos, chatDialogSize]);

  // ============ 데이터 로딩 함수들 ============

  const loadSettingsData = useCallback(async () => {
    if (!currentProject) return;
    const config = await api.getProjectConfig(currentProject.id);
    // 프로젝트 기본 노드 로드
    setDefaultTools((config.default_tools as string[]) || []);
  }, [currentProject]);
  useRetryingLoad(loadSettingsData, { enabled: showSettingsDialog && !!currentProject });

  const loadAllChatAgents = useCallback(async () => {
    if (!currentProject) return;
    const res = await fetch(`http://localhost:8765/conversations/${currentProject.id}`);
    const data = await res.json();
    const agentList = data.conversations || [];
    const sortedAgents = [...agentList].sort((a: ChatAgent, b: ChatAgent) => {
      if (a.type === 'human' && b.type !== 'human') return -1;
      if (a.type !== 'human' && b.type === 'human') return 1;
      return a.name.localeCompare(b.name);
    });
    setChatAgents(sortedAgents);
  }, [currentProject]);
  useRetryingLoad(loadAllChatAgents, { enabled: showTeamChatDialog && !!currentProject });

  const loadChatPartners = useCallback(async () => {
    if (!currentProject || !selectedChatAgent) return;
    const res = await fetch(`http://localhost:8765/conversations/${currentProject.id}/${selectedChatAgent}/partners`);
    const data = await res.json();
    setChatPartners(data.partners || []);
  }, [currentProject, selectedChatAgent]);
  useRetryingLoad(loadChatPartners, { enabled: !!(selectedChatAgent && currentProject) });

  const loadMessagesBetween = useCallback(async () => {
    if (!currentProject || !selectedChatAgent || !selectedPartner) return;
    setTeamChatLoading(true);
    try {
      const res = await fetch(`http://localhost:8765/conversations/${currentProject.id}/between/${selectedChatAgent}/${selectedPartner}?limit=200`);
      const data = await res.json();
      setTeamChatMessages(data.messages || []);
    } finally {
      setTeamChatLoading(false);
    }
  }, [currentProject, selectedChatAgent, selectedPartner]);
  const { retry: refreshMessages } = useRetryingLoad(loadMessagesBetween, {
    enabled: !!(selectedPartner && selectedChatAgent && currentProject),
  });

  // ============ 유틸리티 함수들 ============

  const addLog = (message: string) => {
    setLogs((prev) => [...prev, message]);
  };

  const getAgentNameById = (id: number): string => {
    const agent = chatAgents.find(a => a.id === id);
    return agent?.name || `Agent ${id}`;
  };

  // ============ 이벤트 핸들러들 ============

  // 보조 패널 열기 — 정본은 전용 창(창 밖으로 옮겨 프로젝트 창과 나란히 볼 수 있게).
  // Electron 이 아닌 표면(브라우저·원격)에는 창이 없으니 창 안 다이얼로그로 물러선다.
  const openProjectPanel = (panel: 'teamchat' | 'switches', fallback: () => void) => {
    if (!currentProject) return;
    const open = window.electron?.openProjectPanelWindow;
    if (open) {
      open(panel, currentProject.id, currentProject.name);
      return;
    }
    fallback();
  };

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
      window.electron?.refreshLauncher();  // 런처 새로고침
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
      window.electron?.refreshLauncher();  // 런처 새로고침
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
            onClick={() => openProjectPanel('teamchat', () => setShowTeamChatDialog(true))}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500 hover:bg-purple-600 transition-colors text-white"
            title="팀내 대화"
          >
            <Users size={16} />
            <span className="text-sm">팀내 대화</span>
          </button>

          <button
            onClick={() => openProjectPanel('switches', () => setShowSwitchDialog(true))}
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
        onRefresh={() => { if (selectedPartner && selectedChatAgent) refreshMessages(); }}
        onDragStart={handleDragStart}
        onResizeStart={handleResizeStart}
      />
    </div>
  );
}
