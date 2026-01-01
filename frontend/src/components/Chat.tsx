/**
 * 채팅 컴포넌트
 */

import { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Bot, User, StopCircle, Paperclip, X, Mic, Camera } from 'lucide-react';
import { CameraPreview } from './CameraPreview';
import ReactMarkdown from 'react-markdown';
import { createChatWebSocket, cancelAllAgents, api } from '../lib/api';
import type { Agent } from '../types';

interface ImageAttachment {
  file: File;
  preview: string;
  base64: string;
}

interface ChatProps {
  projectId: string;
  agent: Agent;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  images?: string[];  // base64 이미지 배열
}

export function Chat({ projectId, agent }: ChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [attachedImages, setAttachedImages] = useState<ImageAttachment[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  // Push-to-Talk 상태
  const [isListening, setIsListening] = useState(false);

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

  // 이미지 파일 처리
  const handleImageFile = async (file: File) => {
    if (!file.type.startsWith('image/')) return;

    const base64 = await fileToBase64(file);
    const preview = URL.createObjectURL(file);

    setAttachedImages(prev => [...prev, { file, preview, base64 }]);
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
      await handleImageFile(file);
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
      await handleImageFile(file);
    }
    // input 초기화 (같은 파일 다시 선택 가능하게)
    e.target.value = '';
  };

  // WebSocket 연결
  useEffect(() => {
    const clientId = `${projectId}-${agent.id}-${Date.now()}`;
    const websocket = createChatWebSocket(clientId);

    websocket.onopen = () => {
      console.log('WebSocket connected');
    };

    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'start':
          setIsLoading(true);
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
          setIsLoading(false);
          break;
        case 'error':
          console.error('Chat error:', data.message);
          setIsLoading(false);
          break;
        case 'end':
          setIsLoading(false);
          break;
      }
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsLoading(false);
    };

    websocket.onclose = () => {
      console.log('WebSocket closed');
    };

    setWs(websocket);

    return () => {
      websocket.close();
    };
  }, [projectId, agent.id]);

  // 스크롤 자동 이동
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 메시지 전송
  const sendMessage = () => {
    if ((!input.trim() && attachedImages.length === 0) || !ws || isLoading) return;

    // 이미지 base64 배열 준비
    const imageData = attachedImages.map(img => ({
      base64: img.base64,
      media_type: img.file.type
    }));

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
      // base64 데이터 URL로 저장 (blob URL은 revoke되면 무효화됨)
      images: attachedImages.map(img => `data:${img.file.type};base64,${img.base64}`),
    };

    setMessages((prev) => [...prev, userMessage]);

    ws.send(
      JSON.stringify({
        type: 'chat',
        message: input.trim(),
        agent_name: agent.name,
        project_id: projectId,
        images: imageData.length > 0 ? imageData : undefined,
      })
    );

    setInput('');
    // 이미지 첨부 초기화
    attachedImages.forEach(img => URL.revokeObjectURL(img.preview));
    setAttachedImages([]);
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
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
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: 'assistant',
          content: '⛔ 작업이 중단되었습니다.',
          timestamp: new Date(),
        },
      ]);
    } catch (error) {
      console.error('Cancel failed:', error);
    }
  };

  // Push-to-Talk: 버튼 누르고 있는 동안 녹음
  const handleMicMouseDown = async () => {
    if (isLoading) return;

    setIsListening(true);

    try {
      // 음성 모드 시작 (Whisper 초기화)
      await api.startVoiceMode(projectId, agent.id);
    } catch (error) {
      console.error('Failed to start voice mode:', error);
      setIsListening(false);
    }
  };

  const handleMicMouseUp = async () => {
    if (!isListening) return;

    try {
      // 음성 입력 받기
      const listenResult = await api.voiceListen(projectId, agent.id);

      setIsListening(false);

      if (listenResult.status === 'success' && listenResult.text) {
        // 음성 입력을 채팅으로 전송
        const userMessage: ChatMessage = {
          id: Date.now().toString(),
          role: 'user',
          content: `🎤 ${listenResult.text}`,
          timestamp: new Date(),
        };

        setMessages((prev) => [...prev, userMessage]);
        setIsLoading(true);

        ws?.send(
          JSON.stringify({
            type: 'chat',
            message: listenResult.text.trim(),
            agent_name: agent.name,
            project_id: projectId,
          })
        );
      }

      // 음성 모드 종료
      await api.stopVoiceMode(projectId, agent.id);
    } catch (error) {
      console.error('Voice input error:', error);
      setIsListening(false);
    }
  };

  // 마우스가 버튼 밖으로 나갔을 때도 처리
  const handleMicMouseLeave = () => {
    if (isListening) {
      handleMicMouseUp();
    }
  };

  // 컴포넌트 언마운트 시 정리
  useEffect(() => {
    return () => {
      if (isListening) {
        api.stopVoiceMode(projectId, agent.id).catch(console.error);
      }
    };
  }, [isListening, projectId, agent.id]);

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

        {/* Push-to-Talk 마이크 버튼 */}
        <button
          onMouseDown={handleMicMouseDown}
          onMouseUp={handleMicMouseUp}
          onMouseLeave={handleMicMouseLeave}
          disabled={isLoading}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors select-none ${
            isListening
              ? 'bg-red-500 text-white'
              : 'bg-[#D97706] hover:bg-[#B45309] text-white'
          } disabled:opacity-50`}
          title="누르고 말하기"
        >
          <Mic size={16} className={isListening ? 'animate-pulse' : ''} />
          <span className="text-sm">
            {isListening ? '말하세요...' : '누르고 말하기'}
          </span>
        </button>
      </div>

      {/* 메시지 목록 */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {messages.length === 0 ? (
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

        {isLoading && (
          <div className="flex items-center gap-2 text-[#A09080]">
            <Loader2 size={16} className="animate-spin" />
            <span>{agent.name}이(가) 응답 중...</span>
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

        {/* 드래그 오버레이 */}
        {isDragging && (
          <div className="mb-3 p-4 border-2 border-dashed border-[#D97706] rounded-xl bg-[#FEF3C7] text-center text-[#D97706]">
            이미지를 여기에 놓으세요
          </div>
        )}

        <div className="flex items-end gap-3">
          {/* 파일 선택 버튼 */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            onChange={handleFileSelect}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className="p-3 bg-white rounded-xl border border-[#E5DFD5] hover:border-[#D97706] disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-[#A09080] hover:text-[#D97706]"
            title="이미지 첨부"
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
            placeholder={`${agent.name}에게 메시지 보내기... (이미지 붙여넣기 가능)`}
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
              disabled={!input.trim() && attachedImages.length === 0}
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
  const filePathPattern = /(\/[^\s]+\/(outputs|captures)\/[^\s]+\.(jpg|jpeg|png|gif|webp))/gi;

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

// 메시지 버블 컴포넌트
function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

  // AI 응답에서 이미지 경로 파싱
  const parsedContent = !isUser
    ? parseImagePaths(message.content)
    : { text: message.content, images: [] };

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
        {(isUser ? message.content : parsedContent.text) && (
          <div className="chat-markdown">
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
              {isUser ? message.content : parsedContent.text}
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
