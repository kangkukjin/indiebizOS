/**
 * 채팅 컴포넌트 (스트리밍 지원)
 */

import { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Bot, User, StopCircle, Paperclip, X, Camera, FileText, CheckCircle2, Circle, CircleDot } from 'lucide-react';
import { CameraPreview } from './CameraPreview';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { createChatWebSocket, cancelAllAgents } from '../lib/api';
import type { Agent } from '../types';
import { RouteMap, type RouteMapData } from './RouteMap';
import { LocationMap, type LocationMapData } from './LocationMap';

interface ImageAttachment {
  file: File;
  preview: string;
  base64: string;
}

interface TextAttachment {
  file: File;
  content: string;
  preview: string;  // 미리보기용 (앞부분만)
}

// 텍스트 파일 확장자 목록
const TEXT_EXTENSIONS = ['.txt', '.md', '.json', '.yaml', '.yml', '.xml', '.csv', '.log', '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.sql', '.sh', '.env', '.ini', '.conf', '.toml'];

interface ChatProps {
  projectId: string;
  agent: Agent;
}

interface ToolActivity {
  name: string;
  status: 'running' | 'done';
  input?: Record<string, unknown>;
  result?: string;
}

interface TodoItem {
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
  activeForm: string;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  images?: string[];  // base64 이미지 배열
  textFiles?: { name: string; content: string }[];  // 첨부된 텍스트 파일
  toolActivities?: ToolActivity[];  // 도구 사용 활동
}

export function Chat({ projectId, agent }: ChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [attachedImages, setAttachedImages] = useState<ImageAttachment[]>([]);
  const [attachedTextFiles, setAttachedTextFiles] = useState<TextAttachment[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  // 스트리밍 상태
  const [streamingContent, setStreamingContent] = useState('');
  const [, setCurrentToolActivity] = useState<ToolActivity | null>(null);
  const [toolHistory, setToolHistory] = useState<ToolActivity[]>([]);
  const [thinkingText, setThinkingText] = useState('');
  const [todos, setTodos] = useState<TodoItem[]>([]);

  // 카메라 상태
  const [isCameraOpen, setIsCameraOpen] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 파일을 base64로 변환
  const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => {
        const result = reader.result as string;
        // data:image/jpeg;base64, 부분 제거
        const base64 = result.split(',')[1];
        resolve(base64);
      };
      reader.onerror = reject;
    });
  };

  // 텍스트 파일인지 확인
  const isTextFile = (file: File): boolean => {
    const fileName = file.name.toLowerCase();
    return TEXT_EXTENSIONS.some(ext => fileName.endsWith(ext)) ||
           file.type.startsWith('text/') ||
           file.type === 'application/json' ||
           file.type === 'application/xml';
  };

  // 텍스트 파일 읽기
  const readTextFile = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsText(file, 'UTF-8');
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = reject;
    });
  };

  // 이미지 파일 처리
  const handleImageFile = async (file: File) => {
    if (!file.type.startsWith('image/')) return;

    const base64 = await fileToBase64(file);
    const preview = URL.createObjectURL(file);

    setAttachedImages(prev => [...prev, { file, preview, base64 }]);
  };

  // 텍스트 파일 처리
  const handleTextFile = async (file: File) => {
    if (!isTextFile(file)) return;

    const content = await readTextFile(file);
    const preview = content.length > 200 ? content.substring(0, 200) + '...' : content;

    setAttachedTextFiles(prev => [...prev, { file, content, preview }]);
  };

  // 파일 타입에 따라 처리
  const handleFile = async (file: File) => {
    if (file.type.startsWith('image/')) {
      await handleImageFile(file);
    } else if (isTextFile(file)) {
      await handleTextFile(file);
    }
  };

  // 이미지 제거
  const removeImage = (index: number) => {
    setAttachedImages(prev => {
      const newImages = [...prev];
      URL.revokeObjectURL(newImages[index].preview);
      newImages.splice(index, 1);
      return newImages;
    });
  };

  // 텍스트 파일 제거
  const removeTextFile = (index: number) => {
    setAttachedTextFiles(prev => {
      const newFiles = [...prev];
      newFiles.splice(index, 1);
      return newFiles;
    });
  };

  // 카메라 캡처 처리
  const handleCameraCapture = ({ base64, blob }: { base64: string; blob: Blob }) => {
    const file = new File([blob], `camera_${Date.now()}.jpg`, { type: 'image/jpeg' });
    const preview = URL.createObjectURL(blob);
    setAttachedImages(prev => [...prev, { file, preview, base64 }]);
    setIsCameraOpen(false);
  };

  // 드래그 앤 드롭 핸들러
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    for (const file of files) {
      await handleFile(file);
    }
  };

  // 붙여넣기 핸들러
  const handlePaste = async (e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData.items);
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        e.preventDefault();
        const file = item.getAsFile();
        if (file) {
          await handleImageFile(file);
        }
      }
    }
  };

  // 파일 선택 핸들러
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    for (const file of files) {
      await handleFile(file);
    }
    // input 초기화 (같은 파일 다시 선택 가능하게)
    e.target.value = '';
  };

  // WebSocket 재연결 관리
  const reconnectAttemptRef = useRef(0);
  const maxReconnectAttempts = 5;
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // WebSocket 연결 함수
  const connectWebSocket = (isRetry = false) => {
    const clientId = `${projectId}-${agent.id}-${Date.now()}`;
    const websocket = createChatWebSocket(clientId);

    websocket.onopen = () => {
      console.log(isRetry ? 'WebSocket 재연결 성공' : 'WebSocket connected');
      reconnectAttemptRef.current = 0; // 연결 성공 시 재연결 시도 횟수 초기화
      // 연결 완료 후 state 업데이트 (OPEN 상태에서만)
      setWs(websocket);
    };

    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'start':
          setIsLoading(true);
          setStreamingContent('');
          setCurrentToolActivity(null);
          setToolHistory([]);
          setThinkingText('');
          setTodos([]);
          break;

        case 'stream_chunk':
          setStreamingContent(prev => prev + data.content);
          break;

        case 'tool_start': {
          const newTool: ToolActivity = {
            name: data.name,
            status: 'running',
            input: data.input
          };
          setCurrentToolActivity(newTool);
          setToolHistory(prev => [...prev, newTool]);
          setThinkingText('');
          // 도구 실행 시작 시 중간 텍스트 초기화 (Claude Desktop처럼 최종 응답만 보여주기 위함)
          setStreamingContent('');
          break;
        }

        case 'tool_result':
          setCurrentToolActivity(prev => prev ? {
            ...prev,
            status: 'done',
            result: data.result
          } : null);
          setToolHistory(prev => {
            const updated = [...prev];
            if (updated.length > 0) {
              updated[updated.length - 1] = {
                ...updated[updated.length - 1],
                status: 'done',
                result: data.result
              };
            }
            return updated;
          });
          // TODO 업데이트
          if (data.todos) {
            setTodos(data.todos);
          }
          break;

        case 'thinking':
          setThinkingText(data.content);
          break;

        case 'response':
        case 'auto_report':
          setMessages((prev) => [
            ...prev,
            {
              id: data.message_id ? String(data.message_id) : Date.now().toString(),
              role: 'assistant',
              content: data.content,
              timestamp: new Date(),
            },
          ]);
          setStreamingContent('');
          setCurrentToolActivity(null);
          setToolHistory([]);
          setThinkingText('');
          setTodos([]);
          setIsLoading(false);
          break;

        case 'error':
          console.error('Chat error:', data.message);
          setStreamingContent('');
          setCurrentToolActivity(null);
          setToolHistory([]);
          setThinkingText('');
          setTodos([]);
          setIsLoading(false);
          break;

        case 'end':
          setIsLoading(false);
          setStreamingContent('');
          setCurrentToolActivity(null);
          setToolHistory([]);
          setTodos([]);
          setThinkingText('');
          break;
      }
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    websocket.onclose = (event) => {
      console.log(`WebSocket closed (code: ${event.code})`);
      setWs(null);

      // 비정상 종료 시 자동 재연결 (code 1000은 정상 종료)
      if (event.code !== 1000 && reconnectAttemptRef.current < maxReconnectAttempts) {
        reconnectAttemptRef.current++;
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current - 1), 16000); // exponential backoff, max 16초

        console.log(`${delay/1000}초 후 재연결 시도 (${reconnectAttemptRef.current}/${maxReconnectAttempts})`);

        reconnectTimeoutRef.current = setTimeout(() => {
          connectWebSocket(true);
          // setWs는 onopen에서 호출됨
        }, delay);
      } else if (reconnectAttemptRef.current >= maxReconnectAttempts) {
        console.error('최대 재연결 시도 횟수 초과');
        setIsLoading(false);
      }
    };

    return websocket;
  };

  // WebSocket 연결
  useEffect(() => {
    const websocket = connectWebSocket();
    // setWs는 onopen에서 호출됨 (연결 완료 후)

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      reconnectAttemptRef.current = maxReconnectAttempts; // cleanup 시 재연결 방지
      websocket.close();
    };
  }, [projectId, agent.id]);

  // 컴포넌트 언마운트 시 첨부 이미지 ObjectURL 정리 (메모리 누수 방지)
  useEffect(() => {
    return () => {
      attachedImages.forEach(img => URL.revokeObjectURL(img.preview));
    };
  }, []);

  // 스크롤 자동 이동
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  // 메시지 전송
  const sendMessage = () => {
    const hasContent = input.trim() || attachedImages.length > 0 || attachedTextFiles.length > 0;
    console.log('[Chat] sendMessage called:', { hasContent, ws: !!ws, readyState: ws?.readyState, isLoading, input: input.substring(0, 50) });
    if (!hasContent || !ws || ws.readyState !== WebSocket.OPEN || isLoading) {
      console.log('[Chat] sendMessage blocked:', { hasContent, wsExists: !!ws, readyState: ws?.readyState, isLoading });
      return;
    }

    // 이미지 base64 배열 준비
    const imageData = attachedImages.map(img => ({
      base64: img.base64,
      media_type: img.file.type
    }));

    // 텍스트 파일 내용을 메시지에 추가
    let messageContent = input.trim();
    if (attachedTextFiles.length > 0) {
      const fileContents = attachedTextFiles.map(tf =>
        `\n\n--- 첨부파일: ${tf.file.name} ---\n${tf.content}`
      ).join('');
      messageContent = messageContent + fileContents;
    }

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
      // base64 데이터 URL로 저장 (blob URL은 revoke되면 무효화됨)
      images: attachedImages.map(img => `data:${img.file.type};base64,${img.base64}`),
      textFiles: attachedTextFiles.map(tf => ({ name: tf.file.name, content: tf.content })),
    };

    setMessages((prev) => [...prev, userMessage]);

    // 스트리밍 모드로 전송
    ws.send(
      JSON.stringify({
        type: 'chat_stream',  // 스트리밍 모드
        message: messageContent,
        agent_name: agent.name,
        project_id: projectId,
        images: imageData.length > 0 ? imageData : undefined,
      })
    );

    setInput('');
    // 첨부 파일 초기화
    attachedImages.forEach(img => URL.revokeObjectURL(img.preview));
    setAttachedImages([]);
    setAttachedTextFiles([]);
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // 한글 IME 조합 중에는 Enter 무시 (중복 전송 방지)
    if (e.nativeEvent.isComposing) return;

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // 작업 중단
  const handleCancel = async () => {
    try {
      await cancelAllAgents(projectId);
      setIsLoading(false);
      setStreamingContent('');
      setCurrentToolActivity(null);
      setThinkingText('');
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: 'assistant',
          content: '작업이 중단되었습니다.',
          timestamp: new Date(),
        },
      ]);
    } catch (error) {
      console.error('Cancel failed:', error);
    }
  };

  return (
    <div className="flex-1 flex flex-col bg-[#F5F1EB]">
      {/* 채팅 헤더 */}
      <div className="h-14 px-4 flex items-center justify-between border-b border-[#E5DFD5] bg-[#EAE4DA]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#D97706] to-[#B45309] flex items-center justify-center text-white">
            <Bot size={18} />
          </div>
          <div>
            <div className="font-medium text-[#4A4035]">{agent.name}</div>
            <div className="text-xs text-[#A09080]">{agent.ai?.model}</div>
          </div>
        </div>

      </div>

      {/* 메시지 목록 */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {messages.length === 0 && !isLoading ? (
          <div className="h-full flex items-center justify-center text-[#A09080]">
            <div className="text-center">
              <Bot size={48} className="mx-auto mb-4 opacity-50" />
              <p>{agent.name}에게 메시지를 보내보세요</p>
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))
        )}

        {/* 스트리밍 중인 응답 표시 */}
        {isLoading && (
          <div className="space-y-2">
            {/* TODO 리스트 - Claude Code 스타일 */}
            {todos.length > 0 && (
              <div className="mb-3 border border-[#E5DFD5] rounded-lg overflow-hidden bg-white">
                <div className="px-3 py-2 bg-gradient-to-r from-[#F5F1EB] to-[#EAE4DA] border-b border-[#E5DFD5]">
                  <span className="text-xs font-semibold text-[#4A4035]">📋 작업 목록</span>
                </div>
                <div className="p-2 space-y-1">
                  {todos.map((todo, idx) => (
                    <div key={idx} className="flex items-center gap-2 px-2 py-1 text-xs">
                      {todo.status === 'completed' ? (
                        <CheckCircle2 size={14} className="text-green-500 shrink-0" />
                      ) : todo.status === 'in_progress' ? (
                        <CircleDot size={14} className="text-[#D97706] shrink-0 animate-pulse" />
                      ) : (
                        <Circle size={14} className="text-[#A09080] shrink-0" />
                      )}
                      <span className={`${
                        todo.status === 'completed' ? 'text-[#A09080] line-through' :
                        todo.status === 'in_progress' ? 'text-[#4A4035] font-medium' :
                        'text-[#4A4035]'
                      }`}>
                        {todo.status === 'in_progress' ? todo.activeForm : todo.content}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 도구 사용 히스토리 - Claude Desktop 스타일 */}
            {toolHistory.length > 0 && (
              <div className="mb-3 space-y-2">
                {toolHistory.map((tool, idx) => (
                  <div key={idx} className="text-xs border border-[#E5DFD5] rounded-lg overflow-hidden bg-white">
                    {/* 도구 헤더 */}
                    <div className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-[#F5F1EB] to-[#EAE4DA] border-b border-[#E5DFD5]">
                      {tool.status === 'running' ? (
                        <Loader2 size={14} className="animate-spin text-[#D97706] shrink-0" />
                      ) : (
                        <CheckCircle2 size={14} className="text-green-500 shrink-0" />
                      )}
                      <span className="font-semibold text-[#4A4035]">{tool.name}</span>
                      {tool.status === 'running' && (
                        <span className="ml-auto text-[10px] text-[#D97706] bg-amber-100 px-2 py-0.5 rounded-full">실행 중</span>
                      )}
                    </div>

                    {/* 입력 파라미터 */}
                    {tool.input && Object.keys(tool.input).length > 0 && (
                      <div className="px-3 py-2 border-b border-[#E5DFD5]/50 bg-blue-50/30">
                        <div className="text-[10px] text-blue-600 font-medium mb-1 flex items-center gap-1">
                          <span>📥</span> 입력
                        </div>
                        <pre className="text-[11px] text-[#4A4035] bg-white/80 p-2 rounded border border-[#E5DFD5]/50 overflow-x-auto max-h-40 overflow-y-auto">
                          {JSON.stringify(tool.input, null, 2)}
                        </pre>
                      </div>
                    )}

                    {/* 결과 */}
                    {tool.result && (
                      <div className="px-3 py-2 bg-green-50/30">
                        <div className="text-[10px] text-green-600 font-medium mb-1 flex items-center gap-1">
                          <span>📤</span> 결과
                        </div>
                        <pre className="text-[11px] text-[#4A4035] bg-white/80 p-2 rounded border border-[#E5DFD5]/50 overflow-x-auto max-h-60 overflow-y-auto whitespace-pre-wrap break-words">
                          {tool.result}
                        </pre>
                      </div>
                    )}

                    {/* 실행 중일 때 로딩 표시 */}
                    {tool.status === 'running' && !tool.result && (
                      <div className="px-3 py-3 flex items-center justify-center gap-2 text-[#A09080]">
                        <Loader2 size={12} className="animate-spin" />
                        <span className="text-[11px]">결과를 기다리는 중...</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* AI 사고 과정 */}
            {thinkingText && (
              <div className="flex items-center gap-2 text-[#A09080] text-sm italic">
                <Loader2 size={14} className="animate-spin" />
                <span>{thinkingText}</span>
              </div>
            )}

            {/* 스트리밍 텍스트 */}
            {streamingContent && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#D97706] to-[#B45309] flex items-center justify-center flex-shrink-0 text-white">
                  <Bot size={16} />
                </div>
                <div className="max-w-[70%] px-4 py-3 rounded-2xl bg-[#E5DFD5] text-[#4A4035] rounded-tl-sm">
                  <div className="chat-markdown">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {streamingContent}
                    </ReactMarkdown>
                  </div>
                  <span className="inline-block w-2 h-4 bg-[#D97706] animate-pulse ml-1" />
                </div>
              </div>
            )}

            {/* 로딩 표시 (스트리밍 콘텐츠가 없을 때) */}
            {!streamingContent && toolHistory.length === 0 && !thinkingText && (
              <div className="flex items-center gap-2 text-[#A09080]">
                <Loader2 size={16} className="animate-spin" />
                <span>{agent.name}이(가) 응답 중...</span>
              </div>
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 입력 영역 */}
      <div
        className={`p-4 border-t border-[#E5DFD5] bg-[#EAE4DA] ${isDragging ? 'ring-2 ring-[#D97706] ring-inset' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* 첨부된 이미지 미리보기 */}
        {attachedImages.length > 0 && (
          <div className="flex gap-2 mb-3 flex-wrap">
            {attachedImages.map((img, index) => (
              <div key={index} className="relative group">
                <img
                  src={img.preview}
                  alt={`첨부 이미지 ${index + 1}`}
                  className="w-20 h-20 object-cover rounded-lg border border-[#E5DFD5]"
                />
                <button
                  onClick={() => removeImage(index)}
                  className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 rounded-full flex items-center justify-center text-white opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* 첨부된 텍스트 파일 미리보기 */}
        {attachedTextFiles.length > 0 && (
          <div className="flex gap-2 mb-3 flex-wrap">
            {attachedTextFiles.map((tf, index) => (
              <div key={index} className="relative group bg-white border border-[#E5DFD5] rounded-lg p-2 max-w-[200px]">
                <div className="flex items-center gap-2 mb-1">
                  <FileText size={16} className="text-[#D97706] flex-shrink-0" />
                  <span className="text-xs font-medium text-[#4A4035] truncate">{tf.file.name}</span>
                </div>
                <div className="text-[10px] text-[#A09080] line-clamp-2 break-all">
                  {tf.preview}
                </div>
                <button
                  onClick={() => removeTextFile(index)}
                  className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 rounded-full flex items-center justify-center text-white opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* 드래그 오버레이 */}
        {isDragging && (
          <div className="mb-3 p-4 border-2 border-dashed border-[#D97706] rounded-xl bg-[#FEF3C7] text-center text-[#D97706]">
            파일을 여기에 놓으세요 (이미지, 텍스트 파일)
          </div>
        )}

        <div className="flex items-end gap-3">
          {/* 파일 선택 버튼 */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,.txt,.md,.json,.yaml,.yml,.xml,.csv,.log,.py,.js,.ts,.tsx,.jsx,.html,.css,.sql,.sh,.env,.ini,.conf,.toml"
            multiple
            onChange={handleFileSelect}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className="p-3 bg-white rounded-xl border border-[#E5DFD5] hover:border-[#D97706] disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-[#A09080] hover:text-[#D97706]"
            title="파일 첨부 (이미지, 텍스트)"
          >
            <Paperclip size={20} />
          </button>

          {/* 카메라 버튼 */}
          <button
            onClick={() => setIsCameraOpen(true)}
            disabled={isLoading}
            className="p-3 bg-white rounded-xl border border-[#E5DFD5] hover:border-[#D97706] disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-[#A09080] hover:text-[#D97706]"
            title="카메라로 촬영"
          >
            <Camera size={20} />
          </button>

          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={`${agent.name}에게 메시지 보내기... (파일 드래그/붙여넣기 가능)`}
            className="flex-1 px-4 py-3 bg-white rounded-xl border border-[#E5DFD5] focus:border-[#D97706] focus:outline-none resize-none min-h-[48px] max-h-[200px] text-[#4A4035] placeholder:text-[#A09080]"
            rows={1}
            disabled={isLoading}
          />
          {isLoading ? (
            <button
              onClick={handleCancel}
              className="p-3 bg-red-500 rounded-xl hover:bg-red-600 transition-colors text-white"
              title="작업 중단"
            >
              <StopCircle size={20} />
            </button>
          ) : (
            <button
              onClick={sendMessage}
              disabled={!input.trim() && attachedImages.length === 0 && attachedTextFiles.length === 0}
              className="p-3 bg-[#D97706] rounded-xl hover:bg-[#B45309] disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-white"
            >
              <Send size={20} />
            </button>
          )}
        </div>
      </div>

      {/* 카메라 미리보기 모달 */}
      <CameraPreview
        isOpen={isCameraOpen}
        onClose={() => setIsCameraOpen(false)}
        onCapture={handleCameraCapture}
      />
    </div>
  );
}

// 이미지 경로 패턴 감지 및 변환
function parseImagePaths(content: string): { text: string; images: string[] } {
  const images: string[] = [];

  // 패턴 1: [IMAGE:/path/to/file.jpg] 형식
  const imageTagPattern = /\[IMAGE:(\/[^\]]+\.(jpg|jpeg|png|gif|webp))\]/gi;

  // 패턴 2: 일반 파일 경로 (outputs, captures 폴더 내 이미지)
  // /outputs/... 또는 /something/outputs/... 형태 모두 지원, 백틱 제외
  const filePathPattern = /(\/(?:[^\s`]+\/)?(outputs|captures)\/[^\s`]+\.(jpg|jpeg|png|gif|webp))/gi;

  // 패턴 3: 마크다운 이미지 ![alt](path)
  const markdownImagePattern = /!\[[^\]]*\]\((\/[^)]+\.(jpg|jpeg|png|gif|webp))\)/gi;

  let text = content;

  // [IMAGE:path] 패턴 추출 및 제거
  let match;
  while ((match = imageTagPattern.exec(content)) !== null) {
    images.push(match[1]);
  }
  text = text.replace(imageTagPattern, '');

  // 마크다운 이미지 패턴 추출 및 제거
  const mdMatches = [...content.matchAll(/!\[[^\]]*\]\((\/[^)]+\.(jpg|jpeg|png|gif|webp))\)/gi)];
  for (const m of mdMatches) {
    if (!images.includes(m[1])) {
      images.push(m[1]);
    }
  }
  // 마크다운 이미지 문법 제거 (이미지로 표시하므로)
  text = text.replace(markdownImagePattern, '');

  // 일반 파일 경로 패턴 추출
  const pathMatches = text.match(filePathPattern);
  if (pathMatches) {
    for (const path of pathMatches) {
      if (!images.includes(path)) {
        images.push(path);
      }
    }
  }

  return { text: text.trim(), images };
}

// 지도 데이터 패턴 감지 및 파싱 (route_map, location_map 모두 지원)
function parseMapData(content: string): { text: string; routeMaps: RouteMapData[]; locationMaps: LocationMapData[] } {
  const routeMaps: RouteMapData[] = [];
  const locationMaps: LocationMapData[] = [];
  let text = content;

  // [MAP:{...}] 패턴 찾기 - JSON 내부의 ]를 피하기 위해 수동 파싱
  const mapStart = '[MAP:';
  let startIdx = text.indexOf(mapStart);

  while (startIdx !== -1) {
    const jsonStart = startIdx + mapStart.length;

    // JSON 끝 찾기: 중괄호 카운팅
    let braceCount = 0;
    let jsonEnd = -1;
    let inString = false;
    let escaped = false;

    for (let i = jsonStart; i < text.length; i++) {
      const char = text[i];

      if (escaped) {
        escaped = false;
        continue;
      }

      if (char === '\\' && inString) {
        escaped = true;
        continue;
      }

      if (char === '"') {
        inString = !inString;
        continue;
      }

      if (inString) continue;

      if (char === '{') {
        braceCount++;
      } else if (char === '}') {
        braceCount--;
        if (braceCount === 0) {
          // ] 확인
          if (text[i + 1] === ']') {
            jsonEnd = i + 2;
            break;
          }
        }
      }
    }

    if (jsonEnd !== -1) {
      const jsonStr = text.substring(jsonStart, jsonEnd - 1);
      try {
        const mapData = JSON.parse(jsonStr);
        if (mapData.type === 'route_map') {
          routeMaps.push(mapData as RouteMapData);
        } else if (mapData.type === 'location_map') {
          locationMaps.push(mapData as LocationMapData);
        }
      } catch {
        // JSON 파싱 실패 시 무시
      }

      // 태그 제거
      text = text.substring(0, startIdx) + text.substring(jsonEnd);
      startIdx = text.indexOf(mapStart);
    } else {
      break;
    }
  }

  return { text: text.trim(), routeMaps, locationMaps };
}

// 메시지 버블 컴포넌트
function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

  // AI 응답에서 이미지 경로 및 지도 데이터 파싱
  const parsedContent = !isUser
    ? parseImagePaths(message.content)
    : { text: message.content, images: [] };

  const parsedMaps = !isUser
    ? parseMapData(parsedContent.text)
    : { text: parsedContent.text, routeMaps: [], locationMaps: [] };

  const finalText = !isUser ? parsedMaps.text : message.content;

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-white ${
          isUser
            ? 'bg-gradient-to-br from-[#3B82F6] to-[#1D4ED8]'
            : 'bg-gradient-to-br from-[#D97706] to-[#B45309]'
        }`}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>
      <div
        className={`max-w-[70%] px-4 py-3 rounded-2xl ${
          isUser
            ? 'bg-[#3B82F6] text-white rounded-tr-sm'
            : 'bg-[#E5DFD5] text-[#4A4035] rounded-tl-sm'
        }`}
      >
        {/* 사용자 첨부 이미지 표시 */}
        {message.images && message.images.length > 0 && (
          <div className="flex gap-2 flex-wrap mb-2">
            {message.images.map((img, index) => (
              <img
                key={index}
                src={img}
                alt={`첨부 이미지 ${index + 1}`}
                className="max-w-[200px] max-h-[200px] rounded-lg object-cover"
              />
            ))}
          </div>
        )}
        {/* 사용자 첨부 텍스트 파일 표시 */}
        {message.textFiles && message.textFiles.length > 0 && (
          <div className="flex gap-2 flex-wrap mb-2">
            {message.textFiles.map((tf, index) => (
              <div key={index} className={`flex items-center gap-2 px-2 py-1 rounded ${isUser ? 'bg-blue-400/30' : 'bg-[#D5CFC5]'}`}>
                <FileText size={14} />
                <span className="text-xs font-medium">{tf.name}</span>
              </div>
            ))}
          </div>
        )}
        {/* AI 응답 내 이미지 표시 (파일 경로 기반 - API로 서빙) */}
        {!isUser && parsedContent.images.length > 0 && (
          <div className="flex gap-2 flex-wrap mb-2">
            {parsedContent.images.map((imgPath, index) => (
              <img
                key={index}
                src={`http://127.0.0.1:8765/image?path=${encodeURIComponent(imgPath)}`}
                alt={`캡처 이미지 ${index + 1}`}
                className="max-w-[300px] max-h-[300px] rounded-lg object-cover cursor-pointer hover:opacity-90 transition-opacity"
                onClick={() => window.electron?.openExternal(`file://${imgPath}`)}
                title="클릭하여 원본 보기"
              />
            ))}
          </div>
        )}
        {/* AI 응답 내 경로 지도 표시 */}
        {!isUser && parsedMaps.routeMaps.length > 0 && (
          <div className="mb-2 space-y-2">
            {parsedMaps.routeMaps.map((mapData, index) => (
              <RouteMap key={`route-${index}`} data={mapData} />
            ))}
          </div>
        )}
        {/* AI 응답 내 위치 지도 표시 */}
        {!isUser && parsedMaps.locationMaps.length > 0 && (
          <div className="mb-2 space-y-2">
            {parsedMaps.locationMaps.map((mapData, index) => (
              <LocationMap key={`location-${index}`} data={mapData} />
            ))}
          </div>
        )}
        {finalText && (
          <div className="chat-markdown">
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
              {finalText}
            </ReactMarkdown>
          </div>
        )}
        <div
          className={`text-xs mt-1 ${
            isUser ? 'text-blue-200' : 'text-[#A09080]'
          }`}
        >
          {message.timestamp.toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>
    </div>
  );
}
