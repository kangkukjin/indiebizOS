/**
 * SystemAIChatDialog - 시스템 AI 대화창
 */

import { useState, useRef, useEffect } from 'react';
import { X, Send, Bot, RefreshCw, Paperclip, Camera } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { api } from '../../../lib/api';
import { CameraPreview } from '../../CameraPreview';

interface ImageAttachment {
  file: File;
  preview: string;
  base64: string;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  images?: string[];  // base64 데이터 URL
}

interface SystemAIChatDialogProps {
  show: boolean;
  onClose: () => void;
}

export function SystemAIChatDialog({ show, onClose }: SystemAIChatDialogProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [attachedImages, setAttachedImages] = useState<ImageAttachment[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isCameraOpen, setIsCameraOpen] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (show && inputRef.current) {
      inputRef.current.focus();
    }
  }, [show]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

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
    e.target.value = '';
  };

  const handleSend = async () => {
    if ((!input.trim() && attachedImages.length === 0) || isLoading) return;

    const userMessage = input.trim();

    // 이미지 데이터 준비
    const imageData = attachedImages.map(img => ({
      base64: img.base64,
      media_type: img.file.type
    }));

    // 메시지에 이미지 포함
    const messageImages = attachedImages.map(img => `data:${img.file.type};base64,${img.base64}`);

    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage, images: messageImages }]);

    // 이미지 정리
    attachedImages.forEach(img => URL.revokeObjectURL(img.preview));
    setAttachedImages([]);

    setIsLoading(true);

    try {
      const response = await api.chatWithSystemAI(userMessage, imageData.length > 0 ? imageData : undefined);
      setMessages(prev => [...prev, { role: 'assistant', content: response.response }]);
    } catch (error: any) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `오류: ${error.message || '응답을 받지 못했습니다. 설정에서 API 키를 확인해주세요.'}`
      }]);
    } finally {
      setIsLoading(false);
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
  };

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{
          width: 'min(600px, 90vw)',
          height: 'min(700px, 85vh)',
        }}
      >
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
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
                <div className="flex items-center gap-2">
                  <div className="flex gap-1">
                    <span className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
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

          {/* 드래그 오버레이 */}
          {isDragging && (
            <div className="mb-3 p-3 border-2 border-dashed border-amber-400 rounded-xl bg-amber-50 text-center text-amber-600 text-sm">
              이미지를 여기에 놓으세요
            </div>
          )}

          <div className="flex gap-2">
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
              className="p-2.5 bg-gray-100 rounded-xl border border-gray-200 hover:border-amber-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-gray-500 hover:text-amber-500"
              title="이미지 첨부"
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
              placeholder="메시지를 입력하세요... (이미지 붙여넣기 가능)"
              className="flex-1 px-4 py-2.5 bg-gray-100 border border-gray-200 rounded-xl focus:border-amber-400 focus:outline-none resize-none text-gray-800 placeholder:text-gray-400"
              rows={1}
              disabled={isLoading}
            />
            <button
              onClick={handleSend}
              disabled={(!input.trim() && attachedImages.length === 0) || isLoading}
              className="px-4 py-2.5 bg-amber-500 text-white rounded-xl hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Send size={18} />
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-2 text-center">Enter로 전송 · Shift+Enter로 줄바꿈 · 이미지 드래그 또는 붙여넣기</p>
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
