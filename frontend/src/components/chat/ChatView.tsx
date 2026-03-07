/**
 * ChatView - 통합 채팅 컴포넌트
 *
 * 프로젝트 에이전트 대화와 시스템 AI 대화를 하나의 컴포넌트로 처리합니다.
 * layout과 chatTarget props로 동작을 구성합니다.
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { Bot, User, Loader2, X, RefreshCw, History, ArrowLeft } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cancelAllAgents, api } from '../../lib/api';
import type { Agent } from '../../types';
import { CameraPreview } from '../CameraPreview';
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
  MessageContent,
  ChatInputArea,
  QuestionPanel,
  PlanModePanel,
} from './index';

// ── 설정 타입 ────────────────────────────────────────────

export type ChatTarget =
  | { type: 'agent'; projectId: string; agent: Agent }
  | { type: 'system_ai' };

export type ChatLayout = 'fullpage' | 'dialog';

export interface ChatViewProps {
  chatTarget: ChatTarget;
  layout?: ChatLayout;
  // dialog 모드 전용
  show?: boolean;
  onClose?: () => void;
  // 풀페이지 모드: 뒤로가기 핸들러
  onBack?: () => void;
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

export function ChatView({ chatTarget, layout = 'fullpage', show = true, onClose, onBack }: ChatViewProps) {
  const isAgent = chatTarget.type === 'agent';
  const isDialog = layout === 'dialog';
  const variant = isDialog ? 'neutral' : 'warm';

  // chatTarget에서 안정적인 primitive key 추출 (useEffect/useCallback dependency용)
  const targetKey = isAgent ? `agent-${chatTarget.projectId}-${chatTarget.agent.id}` : 'system_ai';
  const projectId = isAgent ? chatTarget.projectId : null;
  const agentId = isAgent ? chatTarget.agent.id : null;
  const agentName = isAgent ? chatTarget.agent.name : null;

  // ── 상태 ──
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [deepResearch, setDeepResearch] = useState(false);

  // 스트리밍
  const [streamingContent, setStreamingContent] = useState('');
  const [toolHistory, setToolHistory] = useState<ToolActivity[]>([]);
  const [thinkingText, setThinkingText] = useState('');
  const [currentToolLabel, setCurrentToolLabel] = useState<string | null>(null);
  const [todos, setTodos] = useState<TodoItem[]>([]);

  // 질문/계획 모드
  const [questions, setQuestions] = useState<QuestionItem[]>([]);
  const [questionStatus, setQuestionStatus] = useState<'none' | 'pending' | 'answered'>('none');
  const [planMode, setPlanMode] = useState<PlanModeState>({ active: false, phase: null });

  // 다이얼로그 히스토리
  const [showHistory, setShowHistory] = useState(false);

  // refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const toolHistoryRef = useRef<ToolActivity[]>([]);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef(false);
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

  const resetStreamingState = () => {
    setStreamingContent('');
    setToolHistory([]);
    toolHistoryRef.current = [];
    setThinkingText('');
    setCurrentToolLabel(null);
    setTodos([]);
  };

  const agentLabel = agentName || '시스템 AI';
  const agentModel = isAgent ? chatTarget.agent.ai?.model : null;

  // ── WebSocket 연결 ──

  const connectWebSocket = useCallback((isRetry = false) => {
    intentionalCloseRef.current = false; // 새 연결 시 리셋
    reconnectAttemptRef.current = isRetry ? reconnectAttemptRef.current : 0;

    const clientId = isAgent
      ? `${projectId}-${agentId}-${Date.now()}`
      : `system_ai_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    // createChatWebSocket 대신 직접 생성 (내부 핸들러 충돌 방지)
    const websocket = new WebSocket(`ws://127.0.0.1:8765/ws/chat/${clientId}`);

    websocket.onopen = () => {
      if (isRetry) console.log('WebSocket 재연결 성공');
      reconnectAttemptRef.current = 0;
      setWs(websocket);
    };

    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'start':
          setIsLoading(true);
          resetStreamingState();
          break;

        case 'stream_chunk':
          setStreamingContent(prev => prev + data.content);
          break;

        case 'tool_start': {
          const newTool: ToolActivity = { name: data.name, status: 'running', input: data.input };
          setToolHistory(prev => {
            const next = [...prev, newTool];
            toolHistoryRef.current = next;
            return next;
          });
          setCurrentToolLabel(`🔧 ${data.name} 실행 중...`);
          setThinkingText('');
          setStreamingContent('');
          break;
        }

        case 'tool_result':
          setCurrentToolLabel(`✓ ${data.name} 완료`);
          setToolHistory(prev => {
            const updated = [...prev];
            // 마지막으로 실행 중인 해당 도구 찾기
            let idx = -1;
            for (let i = updated.length - 1; i >= 0; i--) {
              if (updated[i].name === data.name && updated[i].status === 'running') {
                idx = i;
                break;
              }
            }
            if (idx !== -1) {
              updated[idx] = { ...updated[idx], result: data.result, status: 'done' };
            } else if (updated.length > 0) {
              // fallback: 마지막 항목 업데이트
              updated[updated.length - 1] = { ...updated[updated.length - 1], result: data.result, status: 'done' };
            }
            toolHistoryRef.current = updated;
            return updated;
          });
          if (data.todos) setTodos(data.todos);
          break;

        case 'thinking':
          setThinkingText(data.content);
          break;

        case 'response':
        case 'auto_report': {
          const savedTools = toolHistoryRef.current.length > 0 ? [...toolHistoryRef.current] : undefined;
          setMessages(prev => [...prev, {
            id: data.message_id ? String(data.message_id) : Date.now().toString(),
            role: 'assistant',
            content: data.content,
            timestamp: new Date(),
            toolActivities: savedTools,
          }]);
          resetStreamingState();
          setIsLoading(false);
          break;
        }

        case 'delegated':
          setCurrentToolLabel('⏳ 에이전트가 작업 중... 결과를 기다리는 중');
          break;

        case 'system_ai_report':
          setMessages(prev => [...prev, {
            id: Date.now().toString(),
            role: 'assistant',
            content: data.content,
            timestamp: new Date(),
          }]);
          setIsLoading(false);
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
          setIsLoading(false);
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
          setIsLoading(false);
          break;

        case 'end':
          setIsLoading(false);
          resetStreamingState();
          break;
      }
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    websocket.onclose = (event) => {
      console.log(`WebSocket closed (code: ${event.code}, intentional: ${intentionalCloseRef.current})`);
      setWs(null);

      // 의도적 종료(cleanup)면 재연결/에러 메시지 없이 종료
      if (intentionalCloseRef.current) return;

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
        setIsLoading(false);
        reconnectAttemptRef.current = 0;
      }
    };

    return websocket;
  }, [targetKey]);

  // ── Effects ──

  // WebSocket 연결 (마운트 시)
  useEffect(() => {
    if (isDialog && !show) return;

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

  // 미전달 메시지 폴링 (에이전트 전용)
  useEffect(() => {
    if (!projectId || !agentName) return;

    const pollInterval = setInterval(async () => {
      try {
        const undelivered = await api.getUndeliveredMessages(projectId, agentName);
        if (undelivered && undelivered.length > 0) {
          setMessages(prev => [
            ...prev,
            ...undelivered.map((msg: { id: number; content: string; timestamp: string }) => ({
              id: String(msg.id),
              role: 'assistant' as const,
              content: msg.content,
              timestamp: new Date(msg.timestamp),
            })),
          ]);
          setIsLoading(false);
          resetStreamingState();
        }
      } catch {
        // 폴링 실패는 무시
      }
    }, 60000);

    return () => clearInterval(pollInterval);
  }, [projectId, agentName]);

  // TODO/질문/계획 모드 상태 폴링
  useEffect(() => {
    if (isDialog && !show) return;

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
  }, [show, isDialog]);

  // 다이얼로그 input focus
  useEffect(() => {
    if (isDialog && show && inputRef.current) {
      inputRef.current.focus();
    }
  }, [show]);

  // 스크롤 자동 이동
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

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

  const sendMessage = () => {
    const hasContent = input.trim() || fileAttachments.hasAttachments;
    if (!hasContent || !ws || ws.readyState !== WebSocket.OPEN || isLoading) return;

    const imageData = fileAttachments.prepareImageData();
    const messageContent = fileAttachments.prepareMessageContent(input);

    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
      images: fileAttachments.getMessageImages(),
      textFiles: fileAttachments.getMessageTextFiles(),
    }]);

    // 에이전트와 시스템 AI는 다른 메시지 타입 사용
    if (isAgent && agentName && projectId) {
      ws.send(JSON.stringify({
        type: 'chat_stream',
        message: messageContent,
        agent_name: agentName,
        project_id: projectId,
        images: imageData.length > 0 ? imageData : undefined,
        deep_research: deepResearch || undefined,
      }));
    } else {
      ws.send(JSON.stringify({
        type: 'system_ai_stream',
        message: messageContent,
        images: imageData.length > 0 ? imageData : undefined,
        deep_research: deepResearch || undefined,
      }));
    }

    setInput('');
    fileAttachments.clearAttachments();
    inputRef.current?.focus();
  };

  // ── 취소 ──

  const handleCancel = async () => {
    if (isAgent && projectId) {
      try {
        await cancelAllAgents(projectId);
      } catch (error) {
        console.error('Cancel failed:', error);
      }
    } else {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'cancel' }));
      }
    }
    setIsLoading(false);
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

  const handleSubmitAnswer = async (answers: Record<number, string | string[]>) => {
    try {
      await api.submitSystemAIQuestionAnswer?.(answers);
      const answerText = Object.entries(answers)
        .map(([idx, ans]) => {
          const q = questions[parseInt(idx)];
          return `**${q?.header}**: ${Array.isArray(ans) ? ans.join(', ') : ans}`;
        })
        .join('\n');
      setMessages(prev => [...prev, { id: Date.now().toString(), role: 'user', content: answerText, timestamp: new Date() }]);
    } catch (err) {
      console.error('Failed to submit answer:', err);
    }
  };

  const handleApprovePlan = async () => {
    try {
      await api.approveSystemAIPlan?.();
      setMessages(prev => [...prev, { id: Date.now().toString(), role: 'user', content: '계획을 승인합니다. 진행해주세요.', timestamp: new Date() }]);
    } catch (err) {
      console.error('Failed to approve plan:', err);
    }
  };

  const handleRejectPlan = async () => {
    const reason = prompt('수정이 필요한 이유를 입력하세요:');
    if (reason !== null) {
      try {
        await api.rejectSystemAIPlan?.(reason);
        setMessages(prev => [...prev, { id: Date.now().toString(), role: 'user', content: `계획 수정 요청: ${reason || '다시 검토해주세요.'}`, timestamp: new Date() }]);
      } catch (err) {
        console.error('Failed to reject plan:', err);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleClear = () => {
    setMessages([]);
    fileAttachments.clearAttachments();
  };

  // ── 렌더링: 다이얼로그 모드 가시성 체크 ──

  if (isDialog && !show) return null;

  // ── 공통 채팅 내부 UI ──

  const chatContent = (
    <>
      {/* 헤더 (다이얼로그 모드에서는 드래그 핸들) */}
      <div
        className={isDialog
          ? 'flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gradient-to-r from-amber-50 to-orange-50 shrink-0 select-none'
          : 'h-14 px-4 flex items-center justify-between border-b border-[#E5DFD5] bg-[#EAE4DA] shrink-0 drag'
        }
        style={isDialog ? { cursor: isDragging ? 'grabbing' : 'grab' } : undefined}
        onMouseDown={isDialog ? handleDragStart : undefined}
      >
        <div className={`flex items-center gap-3${isDialog ? '' : ' no-drag'}`}>
          {/* 뒤로가기 버튼 (풀페이지 + onBack 있을 때) */}
          {!isDialog && onBack && (
            <button onClick={onBack} className="p-2 rounded-lg hover:bg-[#DDD5C8] transition-colors text-[#6B5B4F]" title="뒤로">
              <ArrowLeft size={20} />
            </button>
          )}
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white ${
            isDialog ? 'bg-gradient-to-br from-amber-400 to-orange-500' : 'bg-gradient-to-br from-[#D97706] to-[#B45309]'
          }`}>
            <Bot size={18} />
          </div>
          <div>
            <div className={isDialog ? 'text-lg font-bold text-gray-800' : 'font-medium text-[#4A4035]'}>
              {agentLabel}
            </div>
            <div className={isDialog ? 'text-xs text-gray-500' : 'text-xs text-[#A09080]'}>
              {agentModel || 'IndieBiz OS 도우미'}
            </div>
          </div>
        </div>
        <div className={`flex items-center gap-2${isDialog ? '' : ' no-drag'}`}>
          {/* 심층연구 토글 */}
          <button
            onClick={() => setDeepResearch(prev => !prev)}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
              deepResearch
                ? isDialog
                  ? 'bg-blue-500 text-white hover:bg-blue-600'
                  : 'bg-blue-500 text-white hover:bg-blue-600'
                : isDialog
                  ? 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                  : 'bg-[#DDD5C8] text-[#6B5B4F] hover:bg-[#D0C8BB]'
            }`}
            title={deepResearch ? '심층연구 모드 켜짐 — 클릭하여 끄기' : '심층연구 모드 — 클릭하여 켜기'}
          >
            {deepResearch ? '심층연구 ON' : '심층연구'}
          </button>
          {/* 히스토리/초기화 (시스템 AI일 때) */}
          {!isAgent && (
            <>
              <button onClick={() => setShowHistory(true)} className={`p-1.5 rounded-lg transition-colors ${isDialog ? 'hover:bg-gray-200' : 'hover:bg-[#DDD5C8]'}`} title="대화 히스토리">
                <History size={16} className={isDialog ? 'text-gray-500' : 'text-[#6B5B4F]'} />
              </button>
              <button onClick={handleClear} className={`p-1.5 rounded-lg transition-colors ${isDialog ? 'hover:bg-gray-200' : 'hover:bg-[#DDD5C8]'}`} title="대화 초기화">
                <RefreshCw size={16} className={isDialog ? 'text-gray-500' : 'text-[#6B5B4F]'} />
              </button>
            </>
          )}
          {/* 닫기 버튼 (다이얼로그 전용) */}
          {isDialog && onClose && (
            <button onClick={onClose} className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors">
              <X size={20} className="text-gray-500" />
            </button>
          )}
        </div>
      </div>

      {/* TODO 패널 (로딩 아닐 때, 다이얼로그 모드) */}
      {!isLoading && isDialog && <TodoPanel todos={todos} variant="neutral" collapsible />}

      {/* 질문 패널 */}
      {questionStatus === 'pending' && questions.length > 0 && (
        <QuestionPanel questions={questions} onSubmit={handleSubmitAnswer} />
      )}

      {/* 계획 모드 패널 */}
      <PlanModePanel planMode={planMode} onApprove={handleApprovePlan} onReject={handleRejectPlan} />

      {/* 메시지+입력 래퍼 — flex-1 min-h-0으로 남은 공간 전부 차지, 내부에서 메시지 스크롤 */}
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">

      {/* 메시지 영역 */}
      <div className={`flex-1 min-h-0 overflow-y-auto p-4 space-y-4 ${isDialog ? 'bg-gray-50 selectable-text dialog-messages-scroll' : ''}`}>
        {messages.length === 0 && !isLoading ? (
          <div className={`h-full flex items-center justify-center ${isDialog ? 'text-gray-400' : 'text-[#A09080]'}`}>
            <div className="text-center">
              <Bot size={48} className="mx-auto mb-3 opacity-50" />
              <p className={isDialog ? 'text-sm' : ''}>{isDialog ? '무엇을 도와드릴까요?' : `${agentLabel}에게 메시지를 보내보세요`}</p>
              {isDialog && <p className="text-xs mt-1">시스템 설정, 에이전트 관리 등을 도와드립니다</p>}
            </div>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <MessageBubble key={msg.id || idx} message={msg} variant={variant} />
          ))
        )}

        {/* 스트리밍 중인 응답 */}
        {isLoading && (
          isDialog ? (
            // 다이얼로그 모드: 버블 안에 모든 것
            <div className="flex justify-start">
              <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm max-w-[80%]">
                <TodoPanel todos={todos} variant="inline" />
                <ToolHistoryPanel toolHistory={toolHistory} variant="neutral" />
                {currentToolLabel && (
                  <div className="flex items-center gap-2 text-amber-600 text-sm mb-2">
                    {currentToolLabel.startsWith('✓') ? <span className="text-green-500">✓</span> : <Loader2 size={14} className="animate-spin" />}
                    <span>{currentToolLabel.replace(/^[✓🔧⏳]\s*/, '')}</span>
                  </div>
                )}
                {thinkingText && (
                  <div className="flex items-center gap-2 text-gray-500 text-sm italic mb-2">
                    <Loader2 size={14} className="animate-spin" />
                    <span>{thinkingText}</span>
                  </div>
                )}
                {streamingContent ? (
                  <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2 selectable-text">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingContent}</ReactMarkdown>
                    <span className="inline-block w-2 h-4 bg-amber-400 animate-pulse ml-0.5" />
                  </div>
                ) : !currentToolLabel && !thinkingText && (
                  <div className="flex gap-1">
                    <span className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                )}
              </div>
            </div>
          ) : (
            // 풀페이지 모드: 독립적 블록
            <div className="space-y-2">
              <TodoPanel todos={todos} variant="inline" />
              <ToolHistoryPanel toolHistory={toolHistory} variant="warm" />
              {thinkingText && (
                <div className="flex items-center gap-2 text-[#A09080] text-sm italic">
                  <Loader2 size={14} className="animate-spin" />
                  <span>{thinkingText}</span>
                </div>
              )}
              {streamingContent && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#D97706] to-[#B45309] flex items-center justify-center flex-shrink-0 text-white">
                    <Bot size={16} />
                  </div>
                  <div className="max-w-[70%] px-4 py-3 rounded-2xl bg-[#E5DFD5] text-[#4A4035] rounded-tl-sm">
                    <div className="chat-markdown">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingContent}</ReactMarkdown>
                    </div>
                    <span className="inline-block w-2 h-4 bg-[#D97706] animate-pulse ml-1" />
                  </div>
                </div>
              )}
              {!streamingContent && toolHistory.length === 0 && !thinkingText && (
                <div className="flex items-center gap-2 text-[#A09080]">
                  <Loader2 size={16} className="animate-spin" />
                  <span>{agentLabel}이(가) 응답 중...</span>
                </div>
              )}
            </div>
          )
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 입력 영역 */}
      <ChatInputArea
        input={input}
        onInputChange={setInput}
        onSend={sendMessage}
        onCancel={handleCancel}
        onKeyDown={handleKeyDown}
        isLoading={isLoading}
        hasContent={!!input.trim() || fileAttachments.hasAttachments}
        attachedImages={fileAttachments.attachedImages}
        attachedTextFiles={fileAttachments.attachedTextFiles}
        isDragging={fileAttachments.isDragging}
        onDragOver={fileAttachments.handleDragOver}
        onDragLeave={fileAttachments.handleDragLeave}
        onDrop={fileAttachments.handleDrop}
        onPaste={fileAttachments.handlePaste}
        onFileSelect={fileAttachments.handleFileSelect}
        onRemoveImage={fileAttachments.removeImage}
        onRemoveTextFile={fileAttachments.removeTextFile}
        onCameraClick={() => fileAttachments.setIsCameraOpen(true)}
        fileInputRef={fileAttachments.fileInputRef}
        inputRef={inputRef}
        placeholder={isAgent ? `${agentLabel}에게 메시지 보내기... (파일 드래그/붙여넣기 가능)` : '메시지를 입력하세요... (파일 드래그/붙여넣기 가능)'}
        variant={variant}
        showHelpText={isDialog}
      />

      </div>{/* 메시지+입력 래퍼 닫기 */}

      {/* 카메라 */}
      <CameraPreview
        isOpen={fileAttachments.isCameraOpen}
        onClose={() => fileAttachments.setIsCameraOpen(false)}
        onCapture={fileAttachments.handleCameraCapture}
      />

      {/* 히스토리 (시스템 AI) */}
      {!isAgent && (
        <SystemAIChatHistoryDialog show={showHistory} onClose={() => setShowHistory(false)} />
      )}
    </>
  );

  // ── 레이아웃 래핑 ──

  if (isDialog) {
    const dialogStyle: React.CSSProperties = {
      width: `min(${size.width}px, 95vw)`,
      height: `min(${size.height}px, 95vh)`,
      cursor: isResizing ? (resizeDirection.includes('n') || resizeDirection.includes('s') ? 'ns-resize' : resizeDirection.includes('e') || resizeDirection.includes('w') ? 'ew-resize' : 'nwse-resize') : 'default',
      ...(position ? { position: 'absolute' as const, left: position.x, top: position.y } : {})
    };

    return (
      <div
        className={`fixed inset-0 z-50 ${position ? '' : 'flex items-center justify-center'}`}
        style={{ backgroundColor: isDragging || isResizing ? 'transparent' : 'rgba(0,0,0,0.3)' }}
        onClick={(e) => { if (e.target === e.currentTarget && onClose) onClose(); }}
      >
        <div
          ref={dialogRef}
          className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden relative"
          style={dialogStyle}
        >
          {/* 리사이즈 핸들 */}
          <div className="absolute top-0 left-4 right-4 h-1 cursor-ns-resize hover:bg-amber-400/50 z-10" onMouseDown={(e) => handleResizeStart(e, 'n')} />
          <div className="absolute bottom-0 left-4 right-4 h-1 cursor-ns-resize hover:bg-amber-400/50 z-10" onMouseDown={(e) => handleResizeStart(e, 's')} />
          <div className="absolute left-0 top-4 bottom-4 w-1 cursor-ew-resize hover:bg-amber-400/50 z-10" onMouseDown={(e) => handleResizeStart(e, 'w')} />
          <div className="absolute right-0 top-4 bottom-4 w-1 cursor-ew-resize hover:bg-amber-400/50 z-10" onMouseDown={(e) => handleResizeStart(e, 'e')} />
          <div className="absolute top-0 left-0 w-4 h-4 cursor-nwse-resize z-20" onMouseDown={(e) => handleResizeStart(e, 'nw')} />
          <div className="absolute top-0 right-0 w-4 h-4 cursor-nesw-resize z-20" onMouseDown={(e) => handleResizeStart(e, 'ne')} />
          <div className="absolute bottom-0 left-0 w-4 h-4 cursor-nesw-resize z-20" onMouseDown={(e) => handleResizeStart(e, 'sw')} />
          <div className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize z-20" onMouseDown={(e) => handleResizeStart(e, 'se')} />

          {chatContent}
        </div>
      </div>
    );
  }

  // 풀페이지 모드
  return (
    <div className="flex-1 min-h-0 flex flex-col bg-[#F5F1EB]">
      {chatContent}
    </div>
  );
}

// ── 메시지 버블 ──

function MessageBubble({ message, variant = 'warm' }: { message: ChatMessage; variant?: 'warm' | 'neutral' }) {
  const isUser = message.role === 'user';

  if (variant === 'neutral') {
    return (
      <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
        <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
          isUser
            ? 'bg-amber-500 text-white rounded-br-md'
            : 'bg-white border border-gray-200 text-gray-800 rounded-bl-md shadow-sm'
        }`}>
          <MessageContent
            content={message.content}
            role={message.role}
            images={message.images}
            textFiles={message.textFiles}
            toolActivities={message.toolActivities}
            variant="neutral"
          />
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-white ${
        isUser
          ? 'bg-gradient-to-br from-[#3B82F6] to-[#1D4ED8]'
          : 'bg-gradient-to-br from-[#D97706] to-[#B45309]'
      }`}>
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>
      <div className={`max-w-[70%] px-4 py-3 rounded-2xl ${
        isUser
          ? 'bg-[#3B82F6] text-white rounded-tr-sm'
          : 'bg-[#E5DFD5] text-[#4A4035] rounded-tl-sm'
      }`}>
        <MessageContent
          content={message.content}
          role={message.role}
          images={message.images}
          textFiles={message.textFiles}
          toolActivities={message.toolActivities}
          variant="warm"
        />
        <div className={`text-xs mt-1 ${isUser ? 'text-blue-200' : 'text-[#A09080]'}`}>
          {message.timestamp.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
}
