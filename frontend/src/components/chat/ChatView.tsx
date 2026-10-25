import * as __uiTools from '../../i18n/ui';
import * as React from 'react';
import { ChatDisplay } from './ChatDisplay';
import { ConversationActions, conversationLabel } from './ConversationHeader';
import { checkRemoteSession, isRemotePhoneLayout } from '../../lib/remote-session';
/**
 * ChatView - 통합 채팅 컴포넌트
 *
 * 프로젝트 에이전트 대화와 시스템 AI 대화를 하나의 컴포넌트로 처리합니다.
 * layout과 chatTarget props로 동작을 구성합니다.
 */
import { WEBSOCKET_ORIGIN } from '../../lib/backend-origin';

import { useState, useRef, useEffect, useCallback, Fragment, type ReactNode } from 'react';
import type { ChatSession } from './ChatSession';
import { historyDay, HistoryDate } from './SessionHistory';
import { claimGrimoireOwner, newGrimoireToken, onGrimoireSelection } from './grimoire-relay';
import { SessionWorkspace } from './SessionWorkspace';
import { Bot, Loader2, X, RefreshCw, History, RotateCw, BookOpen } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cancelAllAgents, api } from '../../lib/api';
import type { Agent } from '../../types';
import { isCliProvider } from '../../types';
import { CameraPreview } from '../CameraPreview';
import { MessageBubble } from './MessageBubble';
import { SystemAIChatHistoryDialog } from '../launcher-components/dialogs/SystemAIChatHistoryDialog';
import {
  type ChatMessage,
  type ToolActivity,
  type TodoItem,
  type QuestionItem,
  type PlanModeState,
  useFileAttachments,
  ToolHistoryPanel,
  TodoPanel,
  ChatInputArea,
  ActionGrimoire,
  QuestionPanel,
  PlanModePanel,
} from './index';

// ── 설정 타입 ────────────────────────────────────────────

export type ChatTarget =
  | { type: 'agent'; projectId: string; agent: Agent }
  | { type: 'session'; id: string; title: string }
  | { type: 'system_ai' }
  // 앱메이커 — 시스템 AI에 앱메이커 role을 씌운 앱모드 표면. 동작은 system_ai와 거의 동일하되
  // 대화 스레드 분리(thread='appmaker')·WS role 태그·타이틀만 다르다.
  | { type: 'appmaker' };

export type ChatLayout = 'fullpage' | 'dialog';

export interface ChatViewProps {
  chatTarget: ChatTarget;
  layout?: ChatLayout;
  session?: ChatSession;
  headerActions?: ReactNode;
  headerItems?: Partial<Record<string, ReactNode>>;
  datedHistory?: boolean;
  active?: boolean;
  /** hiddenInset Electron 창(시스템 AI)에서 헤더 왼쪽에 신호등 자리를 비운다. */
  titleBarInset?: boolean;
  // dialog 모드 전용
  show?: boolean;
  onClose?: () => void;
  // 연결되면 자동으로 한 번 전송할 첫 메시지(예: 지난 주행 분석 요청).
  // initialMessageLabel이 있으면 화면 버블엔 그것만 보이고, 실제 전송은 initialMessage.
  initialMessage?: string;
  initialMessageLabel?: string;
}

// ── 다이얼로그 크기 관련 상수 ────────────────────────────

interface DialogSize { width: number; height: number; }
const MIN_WIDTH = 400;
const MIN_HEIGHT = 400;
const MAX_WIDTH = typeof window !== 'undefined' ? window.innerWidth * 0.95 : 1200;
const MAX_HEIGHT = typeof window !== 'undefined' ? window.innerHeight * 0.95 : 800;
const DEFAULT_WIDTH = 600;
const DEFAULT_HEIGHT = 700;
const STORAGE_KEY = 'chat-dialog-size';
const POSITION_STORAGE_KEY = 'chat-dialog-position';
interface DialogPosition { x: number; y: number; }

// ── 메인 컴포넌트 ───────────────────────────────────────

export function ChatView(props: ChatViewProps) {
  const t = props.chatTarget;
  if (props.session || t.type === 'session') return <ChatPane {...props} />;
  const key = t.type === 'agent' ? `${t.projectId}:${t.agent.id}` : t.type;
  return <SessionWorkspace key={key} {...props} />;
}

export function useChatHost({ chatTarget, layout = 'fullpage', show = true, onClose, initialMessage, initialMessageLabel, session, headerActions, headerItems, datedHistory, active = true, titleBarInset = false }: ChatViewProps) {
  const isAgent = chatTarget.type === 'agent';
  const isAppMaker = chatTarget.type === 'appmaker';  // system_ai 분기(!isAgent)를 공유하되 스레드/타이틀만 분기
  const isDialog = layout === 'dialog';
  const variant: 'neutral' | 'warm' = isDialog ? 'neutral' : 'warm';

  // chatTarget에서 안정적인 primitive key 추출 (useEffect/useCallback dependency용)
  const targetKey = chatTarget.type === 'session' ? chatTarget.id : isAgent ? `agent-${chatTarget.projectId}-${chatTarget.agent.id}` : (isAppMaker ? 'appmaker' : 'system_ai');
  const projectId = isAgent ? chatTarget.projectId : null;
  const agentId = isAgent ? chatTarget.agent.id : null;
  const agentName = isAgent ? chatTarget.agent.name : null;

  // ── 상태 ──
  const [localMessages, setMessages] = useState<ChatMessage[]>([]);
  const messages = session?.messages ?? localMessages;
  const [input, setInput] = useState('');
  const [localIsLoading, setIsLoading] = useState(false);
  const isLoading = session?.loading ?? localIsLoading;
  const [ws, setWs] = useState<WebSocket | null>(null);

  // 스트리밍
  const [localStreamingContent, setStreamingContent] = useState('');
  const streamingContent = session?.streamingContent ?? localStreamingContent;
  const streamingContentRef = useRef('');
  const interimMessageIdsRef = useRef(new Set<string>());
  const [localToolHistory, setToolHistory] = useState<ToolActivity[]>([]);
  const toolHistory = session?.toolHistory ?? localToolHistory;
  const [localThinkingText, setThinkingText] = useState('');
  const thinkingText = session?.thinkingText ?? localThinkingText;
  const [currentToolLabel, setCurrentToolLabel] = useState<string | null>(null);
  const [localTodos, setTodos] = useState<TodoItem[]>([]);
  const todos = session?.todos ?? localTodos;

  // 질문/계획 모드
  const [localQuestions, setQuestions] = useState<QuestionItem[]>([]);
  const questions = session?.questions ?? localQuestions;
  const [localQuestionStatus, setQuestionStatus] = useState<'none' | 'pending' | 'answered'>('none');
  const questionStatus = session ? (questions.length ? 'pending' : 'none') : localQuestionStatus;
  const [localPlanMode, setPlanMode] = useState<PlanModeState>({ active: false, phase: null });
  const planMode = session?.planMode ?? localPlanMode;

  // 마법책 (IBL 액션 사전) 모달 — 웹 표면(네이티브 창 없음)에서만. Electron 은 독립 창(`#/grimoire`).
  const [grimoireOpen, setGrimoireOpen] = useState(false);
  // 마법책에서 선택한 액션 — 다음 메시지 전송 시 action_hint로 전달, 전송 후 자동 초기화
  const [selectedAction, setSelectedAction] = useState<string | null>(null);
  // 독립 사전 창이 고른 낱말을 돌려보낼 때 이 대화창을 가리키는 표. 사전 창은 하나, 주인은 마지막으로 연 대화창.
  const grimoireTokenRef = useRef<string>(newGrimoireToken());
  const openGrimoire = useCallback(async () => {
    const native = window.electron?.openToolWindow;
    if (native) {
      claimGrimoireOwner(grimoireTokenRef.current);
      // true 가 아니면(아직 재시작 안 한 옛 메인 프로세스는 undefined) 모달로 물러선다 — 단추가 죽어 있는 틈을 없앤다.
      let opened: boolean | void = false;
      try { opened = await native('grimoire'); } catch { opened = false; }
      if (opened === true) return;
    }
    setGrimoireOpen(true);
  }, []);
  useEffect(() => onGrimoireSelection(grimoireTokenRef.current, (actionId) => setSelectedAction(actionId)), []);

  // 다이얼로그 히스토리
  const [showHistory, setShowHistory] = useState(false);
  const [readingOlder, setReadingOlder] = useState(false);

  // refs
  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const toolHistoryRef = useRef<ToolActivity[]>([]);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef(false);
  // 진행 중 여부 미러 — onclose 는 오래된 클로저를 볼 수 있어 state 를 직접 못 읽는다.
  const isLoadingRef = useRef(false);
  const maxReconnectAttempts = 5;

  // 파일 첨부
  const fileAttachments = useFileAttachments();

  // 다이얼로그 크기 조절
  const dialogRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<DialogSize>(() => {
    if (!isDialog) return { width: 0, height: 0 };
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return {
          width: Math.min(Math.max(parsed.width, MIN_WIDTH), MAX_WIDTH),
          height: Math.min(Math.max(parsed.height, MIN_HEIGHT), MAX_HEIGHT)
        };
      }
    } catch {}
    return { width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT };
  });
  const [isResizing, setIsResizing] = useState(false);
  const [resizeDirection, setResizeDirection] = useState('');

  // 다이얼로그 위치 (드래그 이동)
  const [position, setPosition] = useState<DialogPosition | null>(() => {
    if (!isDialog) return null;
    try {
      const saved = localStorage.getItem(POSITION_STORAGE_KEY);
      if (saved) return JSON.parse(saved);
    } catch {}
    return null; // null = 중앙 정렬 (기본)
  });
  const [isDragging, setIsDragging] = useState(false);
  const dragOffsetRef = useRef({ x: 0, y: 0 });

  // ── 헬퍼 ──

  // setIsLoading 단일 통로 — ref 를 함께 맞춘다(둘이 갈리면 onclose 판정이 틀어진다).
  const setLoading = (v: boolean) => {
    isLoadingRef.current = v;
    setIsLoading(v);
  };

  const resetStreamingState = () => {
    setStreamingContent('');
    streamingContentRef.current = '';
    setToolHistory([]);
    toolHistoryRef.current = [];
    setThinkingText('');
    setCurrentToolLabel(null);
    setTodos([]);
  };

  const agentLabel = (chatTarget.type === 'session' ? chatTarget.title : agentName) || (isAppMaker ? '앱메이커' : '시스템 AI');

  // provider 추적 — Claude Code일 때만 세션 재시작 버튼 노출.
  // 시스템 AI는 status API에서, 프로젝트 에이전트는 agent 객체에서 직접.
  const [systemAiProvider, setSystemAiProvider] = useState<string | null>(null);
  useEffect(() => {
    if (!isAgent && !session) {
      api.getSystemAIStatus().then(s => setSystemAiProvider(s.provider)).catch(() => {});
    }
  }, [isAgent]);
  const currentProvider = isAgent
    ? chatTarget.agent.ai?.provider
    : systemAiProvider;
  const showResetSessionButton = !session && isCliProvider(currentProvider);

  const handleResetSession = async () => {
    try {
      const result = isAgent
        ? await api.resetAgentSession(projectId!, agentId!)
        : await api.resetSystemAISession(isAppMaker ? "appmaker" : "system_ai");
      const ok = (result as { ok?: boolean }).ok !== false;
      console.log('[ChatView] 세션 재시작:', result);
      setMessages(prev => [...prev, {
        id: `reset-${Date.now()}`,
        role: 'assistant',
        content: ok
          ? `↻ ${result.message || '세션 매핑 정리 결과를 받았습니다.'}`
          : `↻ 세션 재시작 실패: ${(result as { error?: string }).error || '알 수 없는 오류'}`,
        timestamp: new Date(),
      }]);
    } catch (e) {
      console.error('[ChatView] 세션 재시작 실패:', e);
      setMessages(prev => [...prev, {
        id: `reset-error-${Date.now()}`,
        role: 'assistant',
        content: `↻ 세션 재시작 실패: ${(e as Error).message}`,
        timestamp: new Date(),
      }]);
    }
  };

  // ── WebSocket 연결 ──

  const connectWebSocket = useCallback((isRetry = false) => {
    intentionalCloseRef.current = false; // 새 연결 시 리셋
    reconnectAttemptRef.current = isRetry ? reconnectAttemptRef.current : 0;

    const clientId = isAgent
      ? `${projectId}-${agentId}-${Date.now()}`
      : `system_ai_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    // createChatWebSocket 대신 직접 생성 (내부 핸들러 충돌 방지)
    const websocket = new WebSocket(`${WEBSOCKET_ORIGIN}/ws/chat/${clientId}`);

    websocket.onopen = () => {
      if (isRetry) console.log('WebSocket 재연결 성공');
      reconnectAttemptRef.current = 0;
      setWs(websocket);
    };

    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'start':
          setLoading(true);
          interimMessageIdsRef.current.clear();
          resetStreamingState();
          break;

        case 'stream_chunk':
          setStreamingContent(prev => {
            const updated = prev + data.content;
            streamingContentRef.current = updated;
            return updated;
          });
          break;

        case 'tool_start': {
          // 도구 실행 중에는 초안을 보이되, 이번 턴의 최종 채택 본문이 오면 대체한다.
          const pendingText = streamingContentRef.current.trim();
          if (pendingText) {
            const interimId = `interim-${Date.now()}-${interimMessageIdsRef.current.size}`;
            interimMessageIdsRef.current.add(interimId);
            setMessages(prev => [...prev, {
              id: interimId,
              role: 'assistant',
              content: pendingText,
              timestamp: new Date(),
            }]);
          }
          const newTool: ToolActivity = { id: data.id, name: data.name, status: 'running', input: data.input };
          setToolHistory(prev => {
            const next = [...prev, newTool];
            toolHistoryRef.current = next;
            return next;
          });
          setCurrentToolLabel(`🔧 ${data.name} 실행 중...`);
          setThinkingText('');
          setStreamingContent('');
          streamingContentRef.current = '';
          break;
        }

        case 'tool_result': {
          const failed = data.is_error === true;
          setCurrentToolLabel(`${failed ? '✖' : '✓'} ${data.name} ${failed ? '실패' : '완료'}`);
          setToolHistory(prev => {
            const updated = [...prev];
            // ★짝짓기는 id 가 정답이다 — 병렬 호출은 같은 이름이 여러 개 동시에 돌아
            // 이름만으로 찾으면 엉뚱한 호출에 결과가 붙는다. id 가 없는 프로바이더는
            // 예전대로 이름·순서로 폴백한다.
            let idx = -1;
            if (data.id) {
              idx = updated.findIndex(t => t.id === data.id);
            }
            if (idx === -1) {
              for (let i = updated.length - 1; i >= 0; i--) {
                if (updated[i].name === data.name && updated[i].status === 'running') {
                  idx = i;
                  break;
                }
              }
            }
            if (idx === -1 && updated.length > 0) idx = updated.length - 1;
            if (idx !== -1) {
              updated[idx] = {
                ...updated[idx],
                result: data.result,
                status: 'done',
                isError: failed,
                input: updated[idx].input ?? data.input,
              };
            }
            toolHistoryRef.current = updated;
            return updated;
          });
          if (data.todos) setTodos(data.todos);
          break;
        }

        case 'thinking':
          setThinkingText(data.content);
          break;

        case 'response':
        case 'auto_report': {
          const savedTools = toolHistoryRef.current.length > 0 ? [...toolHistoryRef.current] : undefined;
          const newMsgId = data.message_id ? String(data.message_id) : Date.now().toString();
          const interimIds = new Set(interimMessageIdsRef.current);
          if (data.type === 'response') interimMessageIdsRef.current.clear();
          setMessages(prev => {
            // 자동 보고는 진행 중인 사용자 턴의 초안을 지우지 않는다.
            const adopted = data.type === 'response' ? prev.filter(m => !interimIds.has(m.id)) : prev;
            // id 기반 중복 방지 (이력 로드 후 동일 메시지가 WS로 다시 올 수 있음)
            if (data.message_id && adopted.some(m => m.id === newMsgId)) return adopted;
            return [...adopted, {
              id: newMsgId,
              role: 'assistant',
              content: data.content,
              timestamp: new Date(),
              toolActivities: savedTools,
            }];
          });
          resetStreamingState();
          setLoading(false);
          break;
        }

        case 'delegated':
          setCurrentToolLabel('⏳ 에이전트가 작업 중... 결과를 기다리는 중');
          break;

        case 'cognition':
          // 자율주행 작업전 공개 — 실행 직전 해마점수·판단·달성기준을 칩으로 노출
          setMessages(prev => [...prev, {
            id: `cognition-${Date.now()}`,
            role: 'assistant',
            content: '',
            timestamp: new Date(),
            cognition: {
              decision: data.decision,
              score: typeof data.score === 'number' ? data.score : 0,
              action: data.action || '',
              criteria: data.criteria || '',
            },
          }]);
          break;

        case 'system_ai_report':
          setMessages(prev => [...prev, {
            id: Date.now().toString(),
            role: 'assistant',
            content: data.content,
            timestamp: new Date(),
          }]);
          setLoading(false);
          resetStreamingState();
          break;

        case 'error':
          console.error('Chat error:', data.message);
          setMessages(prev => [...prev, {
            id: Date.now().toString(),
            role: 'assistant',
            content: `오류: ${data.message}`,
            timestamp: new Date(),
          }]);
          resetStreamingState();
          setLoading(false);
          break;

        case 'cancelled':
          if (streamingContent) {
            setMessages(prev => [...prev, {
              id: Date.now().toString(),
              role: 'assistant',
              content: streamingContent + '\n\n*(중단됨)*',
              timestamp: new Date(),
            }]);
          }
          resetStreamingState();
          setLoading(false);
          break;

        case 'steer_accepted':
          // (2026-08-15 조향) 실행 중 보낸 메시지가 조향으로 접수됨 — 작은 확인 줄만.
          setMessages(prev => [...prev, {
            id: Date.now().toString(),
            role: 'assistant',
            content: `*${data.message || '⤳ 조향 접수 — 다음 도구 완료 시 반영됩니다'}*`,
            timestamp: new Date(),
          }]);
          break;

        case 'end':
          setLoading(false);
          resetStreamingState();
          break;

        case 'media_event':
          // 수신 통화 등 미디어 세션 사건 → 전역 배너(IncomingCallBanner)로 넘긴다. 채팅 상태와 무관.
          window.dispatchEvent(new CustomEvent('indiebiz:media-event', { detail: data }));
          break;
      }
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    websocket.onclose = (event) => {
      checkRemoteSession(event.code);
      if (event.code === 1008) return;
      console.log(`WebSocket closed (code: ${event.code}, intentional: ${intentionalCloseRef.current})`);
      setWs(null);

      // 의도적 종료(cleanup)면 재연결/에러 메시지 없이 종료
      if (intentionalCloseRef.current) return;

      // ★진행 중이던 턴은 연결과 함께 죽었다 — 그 워커는 사라졌고 'end' 는 영영 안 온다.
      //   옛 구현은 *재연결 최대 실패* 가지에서만 풀어서, 백엔드가 금방 돌아오는 흔한
      //   경우(자기수정 apply 가 부른 리로드 등)에 오히려 영영 안 풀렸다 — 복구가 잘 될수록
      //   창이 멈추는 구조였다(2026-08-18 실측: 수리는 성공했는데 칩이 계속 돎).
      if (isLoadingRef.current) {
        setLoading(false);
        resetStreamingState();
        setMessages(prev => [...prev, {
          id: Date.now().toString(),
          role: 'assistant',
          content: '연결이 끊겨 이 턴은 중단됐습니다. 서버가 재기동된 경우(자기수정 반영 등) '
                   + '작업 자체는 완료됐을 수 있습니다 — 다음 메시지에서 결과를 확인하세요.',
          timestamp: new Date(),
        }]);
      }

      if (event.code !== 1000 && reconnectAttemptRef.current < maxReconnectAttempts) {
        reconnectAttemptRef.current++;
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current - 1), 16000);
        console.log(`${delay/1000}초 후 재연결 시도 (${reconnectAttemptRef.current}/${maxReconnectAttempts})`);
        reconnectTimeoutRef.current = setTimeout(() => {
          connectWebSocket(true);
        }, delay);
      } else if (reconnectAttemptRef.current >= maxReconnectAttempts) {
        console.error('최대 재연결 시도 횟수 초과');
        setMessages(prev => [...prev, {
          id: Date.now().toString(),
          role: 'assistant',
          content: '연결이 불안정합니다. 잠시 후 다시 시도해주세요.',
          timestamp: new Date(),
        }]);
        setLoading(false);
        reconnectAttemptRef.current = 0;
      }
    };

    return websocket;
  }, [targetKey]);

  // ── Effects ──

  // WebSocket 연결 (마운트 시)
  useEffect(() => {
    if (session || (isDialog && !show)) return;

    const websocket = connectWebSocket();

    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      intentionalCloseRef.current = true; // onclose에서 에러 메시지 방지
      reconnectAttemptRef.current = maxReconnectAttempts; // cleanup 시 재연결 방지
      if (projectId) {
        cancelAllAgents(projectId).catch(() => {});
      } else {
        // 시스템 AI: WebSocket으로 cancel 전송
        if (websocket.readyState === WebSocket.OPEN) {
          websocket.send(JSON.stringify({ type: 'cancel' }));
        }
      }
      websocket.close();
    };
  }, [show, targetKey]);

  // 미전달 메시지 폴링 (에이전트 전용) — 마운트 즉시 + 30초 간격
  useEffect(() => {
    if (session || !projectId || !agentName) return;

    const fetchUndelivered = async () => {
      try {
        const undelivered = await api.getUndeliveredMessages(projectId, agentName);
        if (undelivered && undelivered.length > 0) {
          setMessages(prev => {
            // 이력 로더가 같은 messages 테이블에서 이미 실은 id 는 건너뛴다.
            const existing = new Set(prev.map(m => m.id));
            const fresh = undelivered
              .filter((msg: { id: number }) => !existing.has(String(msg.id)))
              .map((msg: { id: number; content: string; timestamp: string }) => ({
                id: String(msg.id),
                role: 'assistant' as const,
                content: msg.content,
                timestamp: new Date(msg.timestamp),
              }));
            if (fresh.length === 0) return prev;
            return [...prev, ...fresh];
          });
          setLoading(false);
          resetStreamingState();
        }
      } catch {
        // 폴링 실패는 무시
      }
    };

    // 마운트 시 즉시 체크
    fetchUndelivered();
    // 이후 30초 간격으로 폴링
    const pollInterval = setInterval(fetchUndelivered, 30000);

    return () => clearInterval(pollInterval);
  }, [projectId, agentName]);

  // 시스템 AI 대화 이력 로드 (마운트 시 1회)
  useEffect(() => {
    if (isAgent || session) return; // 에이전트는 아래 별도 이력 로더가 처리

    const loadSystemAIHistory = async () => {
      try {
        const data = await api.getSystemAIRecentConversations?.(10, isAppMaker ? 'appmaker' : 'system_ai');
        if (data?.conversations && data.conversations.length > 0) {
          setMessages(data.conversations.map((msg: { id: number; timestamp: string; role: string; content: string }) => ({
            id: String(msg.id),
            role: msg.role === 'user' ? 'user' as const : 'assistant' as const,
            content: msg.content,
            timestamp: new Date(msg.timestamp),
          })));
        }
      } catch {
        // 이력 로드 실패는 무시
      }
    };

    loadSystemAIHistory();
  }, [isAgent, targetKey]);

  // 프로젝트 에이전트 대화 이력 로드 (마운트 시 1회) — 시스템 AI처럼 창을 다시 열면
  // 이전 대화 스레드를 채팅 뷰에 복원한다. WS 응답 핸들러의 message_id 중복 가드가
  // 이력↔실시간 중복을 막아준다.
  useEffect(() => {
    if (session || !isAgent || !projectId || !agentId) return;

    const loadAgentHistory = async () => {
      try {
        // 백엔드는 message_time DESC(최신순)로 반환 → reverse 해서 시간순으로 표시.
        const rows = await api.getMessages(projectId, agentId, 30);
        if (rows && rows.length > 0) {
          const history = rows
            .slice()
            .reverse()
            .map((msg) => ({
              id: String(msg.id),
              role: msg.is_agent ? 'assistant' as const : 'user' as const,
              content: msg.content,
              timestamp: new Date(msg.timestamp),
            }));
          // 미전달 폴러/실시간 WS가 먼저 채운 메시지와 겹치지 않게 병합(id 중복 제거).
          // 이력은 앞에 붙이고, 이미 존재하는 id 는 건너뛴다.
          setMessages(prev => {
            const existing = new Set(prev.map(m => m.id));
            const fresh = history.filter(m => !existing.has(m.id));
            return [...fresh, ...prev];
          });
        }
      } catch {
        // 이력 로드 실패는 무시
      }
    };

    loadAgentHistory();
  }, [isAgent, projectId, agentId, targetKey]);

  // TODO/질문/계획 모드 상태 폴링
  useEffect(() => {
    if (session || !active || (isDialog && !show)) return;

    const fetchStates = async () => {
      try {
        const todoData = await api.getSystemAITodos?.();
        if (todoData) setTodos(prev => prev.length > 0 && isLoading ? prev : (todoData.todos || []));

        const questionData = await api.getSystemAIQuestions?.();
        if (questionData) {
          setQuestions(questionData.questions || []);
          setQuestionStatus(questionData.status);
        }
        const planData = await api.getSystemAIPlanMode?.();
        if (planData) setPlanMode(planData);
      } catch {
        // 지원하지 않으면 무시
      }
    };

    fetchStates();
    const interval = setInterval(fetchStates, 2000);
    return () => clearInterval(interval);
  }, [show, isDialog, isAgent, targetKey, active]);

  // 다이얼로그 input focus
  useEffect(() => {
    if (isDialog && show && inputRef.current) {
      inputRef.current.focus();
    }
  }, [show]);

  const followRef = useRef(true);
  useEffect(() => {
    if (active && followRef.current) messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent, active]);

  // 다이얼로그 크기 저장
  useEffect(() => {
    if (isDialog && !isResizing) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(size));
    }
  }, [size, isResizing]);

  // 다이얼로그 위치 저장
  useEffect(() => {
    if (isDialog && !isDragging && position) {
      localStorage.setItem(POSITION_STORAGE_KEY, JSON.stringify(position));
    }
  }, [position, isDragging]);

  // 드래그 이벤트
  const handleDragStart = useCallback((e: React.MouseEvent) => {
    // 버튼 클릭은 무시
    if ((e.target as HTMLElement).closest('button')) return;
    e.preventDefault();
    if (!dialogRef.current) return;
    const rect = dialogRef.current.getBoundingClientRect();
    dragOffsetRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    setIsDragging(true);
  }, []);

  useEffect(() => {
    if (!isDragging) return;
    const handleMouseMove = (e: MouseEvent) => {
      const newX = Math.max(0, Math.min(window.innerWidth - 100, e.clientX - dragOffsetRef.current.x));
      const newY = Math.max(0, Math.min(window.innerHeight - 50, e.clientY - dragOffsetRef.current.y));
      setPosition({ x: newX, y: newY });
    };
    const handleMouseUp = () => setIsDragging(false);
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);

  // 리사이즈 이벤트
  const handleResizeStart = useCallback((e: React.MouseEvent, direction: string) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizing(true);
    setResizeDirection(direction);
  }, []);

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!dialogRef.current) return;
      const rect = dialogRef.current.getBoundingClientRect();
      let newWidth = size.width;
      let newHeight = size.height;
      let newX = position?.x ?? rect.left;
      let newY = position?.y ?? rect.top;

      if (position) {
        // 절대 위치 모드: 가장자리 기준 리사이즈
        if (resizeDirection.includes('e')) newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, e.clientX - rect.left));
        if (resizeDirection.includes('w')) { const dx = rect.left - e.clientX; newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, size.width + dx)); newX = e.clientX; }
        if (resizeDirection.includes('s')) newHeight = Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, e.clientY - rect.top));
        if (resizeDirection.includes('n')) { const dy = rect.top - e.clientY; newHeight = Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, size.height + dy)); newY = e.clientY; }
        setPosition({ x: newX, y: newY });
      } else {
        // 중앙 정렬 모드: 기존 로직 (center 기준)
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        if (resizeDirection.includes('e')) newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, (e.clientX - centerX) * 2));
        if (resizeDirection.includes('w')) newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, (centerX - e.clientX) * 2));
        if (resizeDirection.includes('s')) newHeight = Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, (e.clientY - centerY) * 2));
        if (resizeDirection.includes('n')) newHeight = Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, (centerY - e.clientY) * 2));
      }

      setSize({ width: newWidth, height: newHeight });
    };

    const handleMouseUp = () => { setIsResizing(false); setResizeDirection(''); };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing, resizeDirection, size]);

  // ── 메시지 전송 ──

  const sendingRef = useRef(false);
  const sendMessage = async () => {
    if (session) {
      if (!active || sendingRef.current || (!input.trim() && !fileAttachments.hasAttachments)) return;
      sendingRef.current = true; followRef.current = true;
      try {
        const files = [...fileAttachments.attachedImages, ...fileAttachments.attachedTextFiles,
          ...fileAttachments.attachedDocuments].map(item => item.file);
        if (await session.send(input.trim(), files, selectedAction)) {
          setInput(''); fileAttachments.clearAttachments(); setSelectedAction(null);
          inputRef.current?.focus();
        }
      } finally { sendingRef.current = false; }
      return;
    }
    const hasContent = input.trim() || fileAttachments.hasAttachments;
    // (2026-08-15 조향) 실행 중에도 전송 허용 — 백엔드 WS 가 실행 중 도착한 메시지를
    // 새 턴이 아니라 조향(steer)으로 접수해 다음 도구 결과에 배달한다(시스템 AI·에이전트 공통).
    if (!hasContent || !ws || ws.readyState !== WebSocket.OPEN) return;

    const imageData = fileAttachments.prepareImageData();
    const documentData = fileAttachments.prepareDocumentData();
    const messageContent = fileAttachments.prepareMessageContent(input);

    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
      images: fileAttachments.getMessageImages(),
      textFiles: fileAttachments.getMessageTextFiles(),
      documentFiles: fileAttachments.getMessageDocuments(),
    }]);

    // 에이전트와 시스템 AI는 다른 메시지 타입 사용
    if (isAgent && agentName && projectId) {
      ws.send(JSON.stringify({
        type: 'chat_stream',
        message: messageContent,
        agent_name: agentName,
        project_id: projectId,
        images: imageData.length > 0 ? imageData : undefined,
        documents: documentData.length > 0 ? documentData : undefined,
        action_hint: selectedAction || undefined,
      }));
    } else {
      ws.send(JSON.stringify({
        type: 'system_ai_stream',
        message: messageContent,
        images: imageData.length > 0 ? imageData : undefined,
        documents: documentData.length > 0 ? documentData : undefined,
        action_hint: selectedAction || undefined,
        role: isAppMaker ? 'appmaker' : undefined,  // 백엔드가 appmaker role(extra_role)+분리 스레드로 처리
      }));
    }

    setInput('');
    fileAttachments.clearAttachments();
    setSelectedAction(null);  // 전송 후 마법책 선택 자동 초기화
    inputRef.current?.focus();
  };

  // ── 초기 메시지 자동 전송 — 분석 스위치 등이 연결 직후 첫 요청을 흘려보낸다.
  // 같은 메시지는 한 번만, 새 메시지(다른 주행 분석)면 다시 보낸다.
  // ★StrictMode 이중 마운트/재연결 대비: 막 열린 연결은 곧 닫힐 수 있다(그 죽은 연결로
  //   보내면 백엔드가 처리해도 응답이 "연결 없음"으로 버려진다). 약간 지연해 보내고,
  //   그 사이 연결(ws)이 바뀌면 effect cleanup이 타이머를 취소 → 살아남는 연결에서만 전송. ──
  const lastSentInitialRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!initialMessage || lastSentInitialRef.current === initialMessage) return;
    if (!ws || ws.readyState !== WebSocket.OPEN || isLoading) return;
    const sock = ws;
    const timer = setTimeout(() => {
      if (sock.readyState !== WebSocket.OPEN) return;  // 그새 닫혔으면 전송 취소
      lastSentInitialRef.current = initialMessage;
      // 화면엔 라벨(있으면)만, 실제 전송은 전체 initialMessage
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'user',
        content: initialMessageLabel || initialMessage,
        timestamp: new Date(),
      }]);
      if (isAgent && agentName && projectId) {
        sock.send(JSON.stringify({
          type: 'chat_stream', message: initialMessage,
          agent_name: agentName, project_id: projectId,
        }));
      } else {
        sock.send(JSON.stringify({ type: 'system_ai_stream', message: initialMessage }));
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [initialMessage, initialMessageLabel, ws, isLoading, isAgent, agentName, projectId]);

  // ── 취소 ──

  const handleCancel = async () => {
    if (session) { await session.cancel(); return; }
    // (2026-08-15) WS cancel 은 두 경로 공통 — 도는 턴의 도구 루프를 실제로 끊는
    // 유일한 신호(cancel_check). 이전엔 에이전트 경로가 HTTP cancel_all 만 불러
    // 백엔드 턴은 계속 돌고 UI 만 멈춘 척했다(4라운드 감사 실측).
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'cancel' }));
    }
    if (isAgent && projectId) {
      try {
        await cancelAllAgents(projectId);
      } catch (error) {
        console.error('Cancel failed:', error);
      }
    }
    setLoading(false);
    resetStreamingState();
    if (isAgent) {
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: '작업이 중단되었습니다.',
        timestamp: new Date(),
      }]);
    }
  };

  // ── 질문/계획 모드 핸들러 ──

  // 인지 패널(질문/계획)의 응답을 에이전트로 되돌린다.
  // 핸들러가 논블로킹이라 질문을 던진 원래 턴은 이미 끝나 있다 → 답을 일반 대화
  // 메시지(system_ai_stream)로 흘려보내 다음 턴을 연다(히스토리에 질문이 남아 맥락 유지).
  // API 호출은 상태 파일을 마감(패널 내림)하는 역할.
  const continueSystemAI = (message: string) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'system_ai_stream', message }));
    }
  };

  const handleSubmitAnswer = async (answers: Record<number, string | string[]>) => {
    const answerText = Object.entries(answers)
      .map(([idx, ans]) => {
        const q = questions[parseInt(idx)];
        return `**${q?.header}**: ${Array.isArray(ans) ? ans.join(', ') : ans}`;
      })
      .join('\n');
    if (session) { if (session.respondToPanel) await session.respondToPanel('answer', `[질문 답변]\n${answerText}`); else await session.send(`[질문 답변]\n${answerText}`, [], null); return; }
    try {
      await api.submitSystemAIQuestionAnswer?.(answers);
    } catch (err) {
      console.error('Failed to submit answer:', err);
    }
    // 패널 즉시 숨김(다음 폴링이 확정) + 답을 화면에 표시하고 에이전트 재개
    setQuestionStatus('none');
    setQuestions([]);
    setMessages(prev => [...prev, { id: Date.now().toString(), role: 'user', content: answerText, timestamp: new Date() }]);
    continueSystemAI(`[질문 답변]\n${answerText}`);
  };

  const handleApprovePlan = async () => {
    if (session) { if (session.respondToPanel) await session.respondToPanel('approve', '계획을 승인합니다. 진행해주세요.'); else await session.send('계획을 승인합니다. 진행해주세요.', [], null); return; }
    try {
      await api.approveSystemAIPlan?.();
    } catch (err) {
      console.error('Failed to approve plan:', err);
    }
    setMessages(prev => [...prev, { id: Date.now().toString(), role: 'user', content: '계획을 승인합니다. 진행해주세요.', timestamp: new Date() }]);
    continueSystemAI('계획을 승인합니다. 진행해주세요.');
  };

  const handleRejectPlan = async () => {
    const reason = prompt('수정이 필요한 이유를 입력하세요:');
    if (reason !== null) {
      if (session) { if (session.respondToPanel) await session.respondToPanel('reject', `계획 수정 요청: ${reason || '다시 검토해주세요.'}`); else await session.send(`계획 수정 요청: ${reason || '다시 검토해주세요.'}`, [], null); return; }
      try {
        await api.rejectSystemAIPlan?.(reason);
      } catch (err) {
        console.error('Failed to reject plan:', err);
      }
      const msg = `계획 수정 요청: ${reason || '다시 검토해주세요.'}`;
      setMessages(prev => [...prev, { id: Date.now().toString(), role: 'user', content: msg, timestamp: new Date() }]);
      continueSystemAI(msg);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return;
    // 폰 키보드의 Enter는 줄바꿈. 전송은 명시적인 전송 버튼으로 한다.
    if (isRemotePhoneLayout()) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleClear = () => {
    setMessages([]);
    fileAttachments.clearAttachments();
  };

  return { __uiTools, React, ActionGrimoire, BookOpen, Bot, CameraPreview, ChatInputArea, ConversationActions, Fragment, History, HistoryDate, Loader2, MessageBubble, PlanModePanel, QuestionPanel, ReactMarkdown, RefreshCw, RotateCw, SystemAIChatHistoryDialog, TodoPanel, ToolHistoryPanel, X, active, agentLabel, conversationLabel, currentToolLabel, datedHistory, dialogRef, fileAttachments, followRef, grimoireOpen, handleApprovePlan, handleCancel, handleClear, handleDragStart, handleKeyDown, handleRejectPlan, handleResetSession, handleResizeStart, handleSubmitAnswer, headerActions, headerItems, historyDay, input, inputRef, isAgent, isDialog, isDragging, isLoading, isResizing, messages, messagesEndRef, messagesScrollRef, onClose, openGrimoire, planMode, position, questionStatus, questions, readingOlder, remarkGfm, resizeDirection, selectedAction, sendMessage, session, setGrimoireOpen, setInput, setReadingOlder, setSelectedAction, setShowHistory, show, showHistory, showResetSessionButton, size, streamingContent, thinkingText, titleBarInset, todos, toolHistory, variant };
}

export type ChatDisplayBindings = ReturnType<typeof useChatHost>;
export function ChatPane(props: ChatViewProps) {
  const bindings = useChatHost(props);
  return <ChatDisplay bindings={bindings}/>;
}
