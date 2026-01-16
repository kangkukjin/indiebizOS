/**
 * SystemAIChatDialog - 시스템 AI 대화창
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { X, Send, Bot, RefreshCw, Paperclip, Camera, FileText, History, ListTodo, CheckCircle2, Circle, Loader2, HelpCircle, FileEdit, Check, XCircle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { api } from '../../../lib/api';
import { CameraPreview } from '../../CameraPreview';
import { SystemAIChatHistoryDialog } from './SystemAIChatHistoryDialog';

interface ImageAttachment {
  file: File;
  preview: string;
  base64: string;
}

interface TextAttachment {
  file: File;
  content: string;
  preview: string;
}

interface TodoItem {
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
  activeForm: string;
}

interface QuestionOption {
  label: string;
  description: string;
}

interface QuestionItem {
  question: string;
  header: string;
  options: QuestionOption[];
  multiSelect?: boolean;
}

interface PlanModeState {
  active: boolean;
  phase: string | null;
  plan_content?: string;
}

// 텍스트 파일 확장자 목록
const TEXT_EXTENSIONS = ['.txt', '.md', '.json', '.yaml', '.yml', '.xml', '.csv', '.log', '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.sql', '.sh', '.env', '.ini', '.conf', '.toml'];

interface DialogSize {
  width: number;
  height: number;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  images?: string[];  // base64 데이터 URL
  textFiles?: { name: string; content: string }[];
}

interface SystemAIChatDialogProps {
  show: boolean;
  onClose: () => void;
}

// 최소/최대 크기 상수
const MIN_WIDTH = 400;
const MIN_HEIGHT = 400;
const MAX_WIDTH = window.innerWidth * 0.95;
const MAX_HEIGHT = window.innerHeight * 0.95;
const DEFAULT_WIDTH = 600;
const DEFAULT_HEIGHT = 700;

// 로컬 스토리지 키
const STORAGE_KEY = 'system-ai-dialog-size';

export function SystemAIChatDialog({ show, onClose }: SystemAIChatDialogProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [attachedImages, setAttachedImages] = useState<ImageAttachment[]>([]);
  const [attachedTextFiles, setAttachedTextFiles] = useState<TextAttachment[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [showTodos, setShowTodos] = useState(true);
  const [questions, setQuestions] = useState<QuestionItem[]>([]);
  const [questionStatus, setQuestionStatus] = useState<'none' | 'pending' | 'answered'>('none');
  const [selectedAnswers, setSelectedAnswers] = useState<Record<number, string | string[]>>({});
  const [planMode, setPlanMode] = useState<PlanModeState>({ active: false, phase: null });
  // 스트리밍 관련 상태
  const [streamingContent, setStreamingContent] = useState('');
  const [currentToolActivity, setCurrentToolActivity] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const clientIdRef = useRef<string>(`system_ai_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);

  // 크기 조절 관련 상태
  const [size, setSize] = useState<DialogSize>(() => {
    // 저장된 크기 로드
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
  const [resizeDirection, setResizeDirection] = useState<string>('');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (show && inputRef.current) {
      inputRef.current.focus();
    }
  }, [show]);

  // Todo/질문/계획 모드 상태 폴링
  useEffect(() => {
    if (!show) return;

    const fetchStates = async () => {
      try {
        // Todo 상태
        const todoData = await api.getSystemAITodos();
        setTodos(todoData.todos || []);

        // 질문 상태
        const questionData = await api.getSystemAIQuestions();
        setQuestions(questionData.questions || []);
        setQuestionStatus(questionData.status);

        // 계획 모드 상태
        const planData = await api.getSystemAIPlanMode();
        setPlanMode(planData);
      } catch (err) {
        console.error('Failed to fetch states:', err);
      }
    };

    fetchStates();
    const interval = setInterval(fetchStates, 2000); // 2초마다 폴링

    return () => clearInterval(interval);
  }, [show]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 크기 변경 시 저장
  useEffect(() => {
    if (!isResizing) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(size));
    }
  }, [size, isResizing]);

  // 리사이즈 시작
  const handleResizeStart = useCallback((e: React.MouseEvent, direction: string) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizing(true);
    setResizeDirection(direction);
  }, []);

  // 리사이즈 중
  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!dialogRef.current) return;

      const rect = dialogRef.current.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;

      let newWidth = size.width;
      let newHeight = size.height;

      // 방향에 따라 크기 계산
      if (resizeDirection.includes('e')) {
        newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, (e.clientX - centerX) * 2));
      }
      if (resizeDirection.includes('w')) {
        newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, (centerX - e.clientX) * 2));
      }
      if (resizeDirection.includes('s')) {
        newHeight = Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, (e.clientY - centerY) * 2));
      }
      if (resizeDirection.includes('n')) {
        newHeight = Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, (centerY - e.clientY) * 2));
      }

      setSize({ width: newWidth, height: newHeight });
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      setResizeDirection('');
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing, resizeDirection, size]);

  // 파일을 base64로 변환
  const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => {
        const result = reader.result as string;
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
    e.target.value = '';
  };

  const handleSend = async () => {
    const hasContent = input.trim() || attachedImages.length > 0 || attachedTextFiles.length > 0;
    if (!hasContent || isLoading) return;

    // 텍스트 파일 내용을 메시지에 추가
    let messageContent = input.trim();
    if (attachedTextFiles.length > 0) {
      const fileContents = attachedTextFiles.map(tf =>
        `\n\n--- 첨부파일: ${tf.file.name} ---\n${tf.content}`
      ).join('');
      messageContent = messageContent + fileContents;
    }

    // 이미지 데이터 준비
    const imageData = attachedImages.map(img => ({
      base64: img.base64,
      media_type: img.file.type
    }));

    // 메시지에 이미지 포함
    const messageImages = attachedImages.map(img => `data:${img.file.type};base64,${img.base64}`);

    setInput('');
    setMessages(prev => [...prev, {
      role: 'user',
      content: input.trim(),
      images: messageImages,
      textFiles: attachedTextFiles.map(tf => ({ name: tf.file.name, content: tf.content }))
    }]);

    // 첨부 파일 정리
    attachedImages.forEach(img => URL.revokeObjectURL(img.preview));
    setAttachedImages([]);
    setAttachedTextFiles([]);

    setIsLoading(true);
    setStreamingContent('');
    setCurrentToolActivity(null);

    // WebSocket 연결 및 스트리밍
    const wsUrl = `ws://localhost:8765/ws/chat/${clientIdRef.current}`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        // 메시지 전송
        ws.send(JSON.stringify({
          type: 'system_ai_stream',
          message: messageContent,
          images: imageData.length > 0 ? imageData : undefined
        }));
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case 'stream_chunk':
            setStreamingContent(prev => prev + data.content);
            break;

          case 'tool_start':
            setCurrentToolActivity(`🔧 ${data.name} 실행 중...`);
            break;

          case 'tool_result':
            setCurrentToolActivity(null);
            // 도구 결과는 스트리밍 내용에 포함되지 않음 (AI가 요약해서 전달)
            break;

          case 'response':
            // 최종 응답 - 메시지에 추가
            setMessages(prev => [...prev, { role: 'assistant', content: data.content }]);
            setStreamingContent('');
            break;

          case 'end':
            setIsLoading(false);
            setCurrentToolActivity(null);
            ws.close();
            break;

          case 'error':
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: `오류: ${data.message}`
            }]);
            setIsLoading(false);
            setStreamingContent('');
            setCurrentToolActivity(null);
            ws.close();
            break;
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: '연결 오류가 발생했습니다. 다시 시도해주세요.'
        }]);
        setIsLoading(false);
        setStreamingContent('');
      };

      ws.onclose = () => {
        wsRef.current = null;
      };

    } catch (error: any) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `오류: ${error.message || '응답을 받지 못했습니다. 설정에서 API 키를 확인해주세요.'}`
      }]);
      setIsLoading(false);
      setStreamingContent('');
    }
  };

  // 질문 응답 제출
  const handleSubmitAnswer = async () => {
    try {
      await api.submitSystemAIQuestionAnswer(selectedAnswers);
      setSelectedAnswers({});
      // 메시지에 응답 추가
      const answerText = Object.entries(selectedAnswers)
        .map(([idx, ans]) => {
          const q = questions[parseInt(idx)];
          return `**${q?.header}**: ${Array.isArray(ans) ? ans.join(', ') : ans}`;
        })
        .join('\n');
      setMessages(prev => [...prev, { role: 'user', content: answerText }]);
    } catch (err) {
      console.error('Failed to submit answer:', err);
    }
  };

  // 계획 승인
  const handleApprovePlan = async () => {
    try {
      await api.approveSystemAIPlan();
      setMessages(prev => [...prev, { role: 'user', content: '계획을 승인합니다. 진행해주세요.' }]);
    } catch (err) {
      console.error('Failed to approve plan:', err);
    }
  };

  // 계획 거부
  const handleRejectPlan = async () => {
    const reason = prompt('수정이 필요한 이유를 입력하세요:');
    if (reason !== null) {
      try {
        await api.rejectSystemAIPlan(reason);
        setMessages(prev => [...prev, { role: 'user', content: `계획 수정 요청: ${reason || '다시 검토해주세요.'}` }]);
      } catch (err) {
        console.error('Failed to reject plan:', err);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClear = () => {
    setMessages([]);
    attachedImages.forEach(img => URL.revokeObjectURL(img.preview));
    setAttachedImages([]);
    setAttachedTextFiles([]);
  };

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div
        ref={dialogRef}
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden relative"
        style={{
          width: `min(${size.width}px, 95vw)`,
          height: `min(${size.height}px, 95vh)`,
          cursor: isResizing ? (resizeDirection.includes('n') || resizeDirection.includes('s') ? 'ns-resize' : resizeDirection.includes('e') || resizeDirection.includes('w') ? 'ew-resize' : 'nwse-resize') : 'default'
        }}
      >
        {/* 리사이즈 핸들들 */}
        {/* 상단 */}
        <div
          className="absolute top-0 left-4 right-4 h-1 cursor-ns-resize hover:bg-amber-400/50 z-10"
          onMouseDown={(e) => handleResizeStart(e, 'n')}
        />
        {/* 하단 */}
        <div
          className="absolute bottom-0 left-4 right-4 h-1 cursor-ns-resize hover:bg-amber-400/50 z-10"
          onMouseDown={(e) => handleResizeStart(e, 's')}
        />
        {/* 좌측 */}
        <div
          className="absolute left-0 top-4 bottom-4 w-1 cursor-ew-resize hover:bg-amber-400/50 z-10"
          onMouseDown={(e) => handleResizeStart(e, 'w')}
        />
        {/* 우측 */}
        <div
          className="absolute right-0 top-4 bottom-4 w-1 cursor-ew-resize hover:bg-amber-400/50 z-10"
          onMouseDown={(e) => handleResizeStart(e, 'e')}
        />
        {/* 코너들 */}
        <div
          className="absolute top-0 left-0 w-4 h-4 cursor-nwse-resize z-20"
          onMouseDown={(e) => handleResizeStart(e, 'nw')}
        />
        <div
          className="absolute top-0 right-0 w-4 h-4 cursor-nesw-resize z-20"
          onMouseDown={(e) => handleResizeStart(e, 'ne')}
        />
        <div
          className="absolute bottom-0 left-0 w-4 h-4 cursor-nesw-resize z-20"
          onMouseDown={(e) => handleResizeStart(e, 'sw')}
        />
        <div
          className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize z-20"
          onMouseDown={(e) => handleResizeStart(e, 'se')}
        />
        {/* 헤더 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gradient-to-r from-amber-50 to-orange-50 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center">
              <Bot size={18} className="text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-800">시스템 AI</h2>
              <p className="text-xs text-gray-500">IndieBiz OS 도우미</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowHistory(true)}
              className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
              title="대화 히스토리"
            >
              <History size={16} className="text-gray-500" />
            </button>
            <button
              onClick={handleClear}
              className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
              title="대화 초기화"
            >
              <RefreshCw size={16} className="text-gray-500" />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
            >
              <X size={20} className="text-gray-500" />
            </button>
          </div>
        </div>

        {/* Todo 패널 */}
        {todos.length > 0 && showTodos && (
          <div className="px-4 py-2 bg-amber-50 border-b border-amber-200 shrink-0">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 text-amber-700">
                <ListTodo size={14} />
                <span className="text-xs font-medium">작업 진행 상황</span>
                <span className="text-[10px] text-amber-500">
                  ({todos.filter(t => t.status === 'completed').length}/{todos.length})
                </span>
              </div>
              <button
                onClick={() => setShowTodos(false)}
                className="text-amber-400 hover:text-amber-600"
              >
                <X size={12} />
              </button>
            </div>
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {todos.map((todo, idx) => (
                <div
                  key={idx}
                  className={`flex items-center gap-2 text-xs py-0.5 ${
                    todo.status === 'completed' ? 'text-gray-400 line-through' :
                    todo.status === 'in_progress' ? 'text-amber-700 font-medium' :
                    'text-gray-600'
                  }`}
                >
                  {todo.status === 'completed' ? (
                    <CheckCircle2 size={12} className="text-green-500 flex-shrink-0" />
                  ) : todo.status === 'in_progress' ? (
                    <Loader2 size={12} className="text-amber-500 animate-spin flex-shrink-0" />
                  ) : (
                    <Circle size={12} className="text-gray-300 flex-shrink-0" />
                  )}
                  <span className="truncate">
                    {todo.status === 'in_progress' ? todo.activeForm : todo.content}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Todo 최소화 버튼 */}
        {todos.length > 0 && !showTodos && (
          <button
            onClick={() => setShowTodos(true)}
            className="absolute top-14 right-4 z-30 px-2 py-1 bg-amber-100 text-amber-600 rounded-full text-xs flex items-center gap-1 hover:bg-amber-200 transition-colors"
          >
            <ListTodo size={12} />
            {todos.filter(t => t.status === 'completed').length}/{todos.length}
          </button>
        )}

        {/* 질문 패널 */}
        {questionStatus === 'pending' && questions.length > 0 && (
          <div className="px-4 py-3 bg-blue-50 border-b border-blue-200 shrink-0">
            <div className="flex items-center gap-2 text-blue-700 mb-3">
              <HelpCircle size={16} />
              <span className="text-sm font-medium">AI가 질문합니다</span>
            </div>
            <div className="space-y-4">
              {questions.map((q, qIdx) => (
                <div key={qIdx} className="bg-white rounded-lg p-3 border border-blue-100">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-[10px] font-medium rounded">
                      {q.header}
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 mb-3">{q.question}</p>
                  <div className="space-y-2">
                    {q.options.map((opt, optIdx) => (
                      <label
                        key={optIdx}
                        className={`flex items-start gap-3 p-2 rounded-lg cursor-pointer transition-colors ${
                          (q.multiSelect
                            ? (selectedAnswers[qIdx] as string[] || []).includes(opt.label)
                            : selectedAnswers[qIdx] === opt.label)
                            ? 'bg-blue-100 border border-blue-300'
                            : 'bg-gray-50 border border-gray-200 hover:bg-gray-100'
                        }`}
                      >
                        <input
                          type={q.multiSelect ? 'checkbox' : 'radio'}
                          name={`question-${qIdx}`}
                          checked={
                            q.multiSelect
                              ? (selectedAnswers[qIdx] as string[] || []).includes(opt.label)
                              : selectedAnswers[qIdx] === opt.label
                          }
                          onChange={() => {
                            if (q.multiSelect) {
                              const current = (selectedAnswers[qIdx] as string[]) || [];
                              const updated = current.includes(opt.label)
                                ? current.filter(l => l !== opt.label)
                                : [...current, opt.label];
                              setSelectedAnswers(prev => ({ ...prev, [qIdx]: updated }));
                            } else {
                              setSelectedAnswers(prev => ({ ...prev, [qIdx]: opt.label }));
                            }
                          }}
                          className="mt-1"
                        />
                        <div className="flex-1">
                          <div className="text-sm font-medium text-gray-800">{opt.label}</div>
                          {opt.description && (
                            <div className="text-xs text-gray-500 mt-0.5">{opt.description}</div>
                          )}
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2 mt-3">
              <button
                onClick={handleSubmitAnswer}
                disabled={Object.keys(selectedAnswers).length === 0}
                className="px-4 py-2 bg-blue-500 text-white text-sm rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              >
                <Check size={14} />
                응답 제출
              </button>
            </div>
          </div>
        )}

        {/* 계획 모드 패널 */}
        {planMode.active && planMode.phase === 'awaiting_approval' && (
          <div className="px-4 py-3 bg-purple-50 border-b border-purple-200 shrink-0 max-h-64 overflow-y-auto">
            <div className="flex items-center gap-2 text-purple-700 mb-3">
              <FileEdit size={16} />
              <span className="text-sm font-medium">구현 계획 검토</span>
            </div>
            <div className="bg-white rounded-lg p-3 border border-purple-100 mb-3">
              <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2 text-gray-700">
                <ReactMarkdown>{planMode.plan_content || ''}</ReactMarkdown>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={handleRejectPlan}
                className="px-4 py-2 bg-gray-200 text-gray-700 text-sm rounded-lg hover:bg-gray-300 transition-colors flex items-center gap-2"
              >
                <XCircle size={14} />
                수정 요청
              </button>
              <button
                onClick={handleApprovePlan}
                className="px-4 py-2 bg-purple-500 text-white text-sm rounded-lg hover:bg-purple-600 transition-colors flex items-center gap-2"
              >
                <Check size={14} />
                계획 승인
              </button>
            </div>
          </div>
        )}

        {/* 계획 모드 진행 중 표시 */}
        {planMode.active && planMode.phase !== 'awaiting_approval' && (
          <div className="px-4 py-2 bg-purple-50 border-b border-purple-200 shrink-0">
            <div className="flex items-center gap-2 text-purple-700">
              <FileEdit size={14} />
              <span className="text-xs font-medium">계획 모드 진행 중</span>
              <Loader2 size={12} className="animate-spin text-purple-500" />
              <span className="text-xs text-purple-500">
                {planMode.phase === 'exploring' ? '코드 탐색 중...' :
                 planMode.phase === 'designing' ? '설계 중...' :
                 planMode.phase === 'reviewing' ? '검토 중...' :
                 planMode.phase === 'finalizing' ? '마무리 중...' : '진행 중...'}
              </span>
            </div>
          </div>
        )}

        {/* 메시지 영역 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-400">
              <Bot size={48} className="mb-3 opacity-50" />
              <p className="text-sm">무엇을 도와드릴까요?</p>
              <p className="text-xs mt-1">시스템 설정, 에이전트 관리 등을 도와드립니다</p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
                    msg.role === 'user'
                      ? 'bg-amber-500 text-white rounded-br-md'
                      : 'bg-white border border-gray-200 text-gray-800 rounded-bl-md shadow-sm'
                  }`}
                >
                  {/* 사용자 첨부 이미지 표시 */}
                  {msg.images && msg.images.length > 0 && (
                    <div className="flex gap-2 flex-wrap mb-2">
                      {msg.images.map((img, imgIdx) => (
                        <img
                          key={imgIdx}
                          src={img}
                          alt={`첨부 이미지 ${imgIdx + 1}`}
                          className="max-w-[150px] max-h-[150px] rounded-lg object-cover"
                        />
                      ))}
                    </div>
                  )}
                  {/* 사용자 첨부 텍스트 파일 표시 */}
                  {msg.textFiles && msg.textFiles.length > 0 && (
                    <div className="flex gap-2 flex-wrap mb-2">
                      {msg.textFiles.map((tf, tfIdx) => (
                        <div key={tfIdx} className={`flex items-center gap-2 px-2 py-1 rounded ${msg.role === 'user' ? 'bg-amber-400/30' : 'bg-gray-200'}`}>
                          <FileText size={14} />
                          <span className="text-xs font-medium">{tf.name}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {msg.role === 'assistant' ? (
                    <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  ) : (
                    msg.content && <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                  )}
                </div>
              </div>
            ))
          )}
          {/* 스트리밍 중인 응답 표시 */}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm max-w-[80%]">
                {/* 도구 활동 표시 */}
                {currentToolActivity && (
                  <div className="flex items-center gap-2 text-amber-600 text-sm mb-2 pb-2 border-b border-gray-100">
                    <Loader2 size={14} className="animate-spin" />
                    <span>{currentToolActivity}</span>
                  </div>
                )}
                {/* 스트리밍 텍스트 표시 */}
                {streamingContent ? (
                  <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2">
                    <ReactMarkdown>{streamingContent}</ReactMarkdown>
                    <span className="inline-block w-2 h-4 bg-amber-400 animate-pulse ml-0.5" />
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <div className="flex gap-1">
                      <span className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* 입력 영역 */}
        <div
          className={`p-4 border-t border-gray-200 bg-white shrink-0 ${isDragging ? 'ring-2 ring-amber-400 ring-inset' : ''}`}
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
                    className="w-16 h-16 object-cover rounded-lg border border-gray-200"
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
                <div key={index} className="relative group bg-gray-100 border border-gray-200 rounded-lg p-2 max-w-[180px]">
                  <div className="flex items-center gap-2 mb-1">
                    <FileText size={14} className="text-amber-500 flex-shrink-0" />
                    <span className="text-xs font-medium text-gray-700 truncate">{tf.file.name}</span>
                  </div>
                  <div className="text-[10px] text-gray-500 line-clamp-2 break-all">
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
            <div className="mb-3 p-3 border-2 border-dashed border-amber-400 rounded-xl bg-amber-50 text-center text-amber-600 text-sm">
              파일을 여기에 놓으세요 (이미지, 텍스트 파일)
            </div>
          )}

          <div className="flex gap-2">
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
              className="p-2.5 bg-gray-100 rounded-xl border border-gray-200 hover:border-amber-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-gray-500 hover:text-amber-500"
              title="파일 첨부 (이미지, 텍스트)"
            >
              <Paperclip size={18} />
            </button>

            {/* 카메라 버튼 */}
            <button
              onClick={() => setIsCameraOpen(true)}
              disabled={isLoading}
              className="p-2.5 bg-gray-100 rounded-xl border border-gray-200 hover:border-amber-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-gray-500 hover:text-amber-500"
              title="카메라로 촬영"
            >
              <Camera size={18} />
            </button>

            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder="메시지를 입력하세요... (파일 드래그/붙여넣기 가능)"
              className="flex-1 px-4 py-2.5 bg-gray-100 border border-gray-200 rounded-xl focus:border-amber-400 focus:outline-none resize-none text-gray-800 placeholder:text-gray-400"
              rows={1}
              disabled={isLoading}
            />
            <button
              onClick={handleSend}
              disabled={(!input.trim() && attachedImages.length === 0 && attachedTextFiles.length === 0) || isLoading}
              className="px-4 py-2.5 bg-amber-500 text-white rounded-xl hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Send size={18} />
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-2 text-center">Enter로 전송 · Shift+Enter로 줄바꿈 · 파일 드래그 또는 붙여넣기</p>
        </div>
      </div>

      {/* 카메라 미리보기 모달 */}
      <CameraPreview
        isOpen={isCameraOpen}
        onClose={() => setIsCameraOpen(false)}
        onCapture={handleCameraCapture}
      />

      {/* 대화 히스토리 모달 */}
      <SystemAIChatHistoryDialog
        show={showHistory}
        onClose={() => setShowHistory(false)}
      />
    </div>
  );
}
