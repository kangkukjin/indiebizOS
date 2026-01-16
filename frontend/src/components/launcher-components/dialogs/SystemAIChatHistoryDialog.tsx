/**
 * SystemAIChatHistoryDialog - 시스템 AI 대화 히스토리
 */

import { useState, useEffect, useRef } from 'react';
import { X, Calendar, MessageSquare, RefreshCw, ChevronRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { api } from '../../../lib/api';

interface ConversationDate {
  date: string;
  count: number;
}

interface Conversation {
  id: number;
  timestamp: string;
  role: string;
  content: string;
}

interface SystemAIChatHistoryDialogProps {
  show: boolean;
  onClose: () => void;
}

export function SystemAIChatHistoryDialog({ show, onClose }: SystemAIChatHistoryDialogProps) {
  const [dates, setDates] = useState<ConversationDate[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoadingDates, setIsLoadingDates] = useState(false);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (show) {
      loadDates();
    }
  }, [show]);

  useEffect(() => {
    if (selectedDate) {
      loadConversations(selectedDate);
    }
  }, [selectedDate]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversations]);

  const loadDates = async () => {
    try {
      setIsLoadingDates(true);
      const data = await api.getSystemAIConversationDates();
      setDates(data.dates);
      // 최근 날짜 자동 선택
      if (data.dates.length > 0 && !selectedDate) {
        setSelectedDate(data.dates[0].date);
      }
    } catch (err) {
      console.error('Failed to load conversation dates:', err);
    } finally {
      setIsLoadingDates(false);
    }
  };

  const loadConversations = async (date: string) => {
    try {
      setIsLoadingConversations(true);
      const data = await api.getSystemAIConversationsByDate(date);
      setConversations(data.conversations);
    } catch (err) {
      console.error('Failed to load conversations:', err);
    } finally {
      setIsLoadingConversations(false);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (dateStr === today.toISOString().split('T')[0]) {
      return '오늘';
    } else if (dateStr === yesterday.toISOString().split('T')[0]) {
      return '어제';
    }
    return date.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' });
  };

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
  };

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-[60]">
      <div className="bg-white rounded-xl shadow-2xl w-[900px] h-[700px] flex flex-col overflow-hidden">
        {/* 헤더 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 bg-gradient-to-r from-amber-50 to-orange-50 shrink-0">
          <div className="flex items-center gap-3">
            <MessageSquare size={20} className="text-amber-600" />
            <h2 className="text-lg font-bold text-gray-800">대화 히스토리</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={loadDates}
              className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
              title="새로고침"
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

        {/* 본문 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 왼쪽: 날짜 목록 */}
          <div className="w-56 border-r border-gray-200 bg-gray-50 overflow-y-auto">
            <div className="p-2">
              <div className="flex items-center gap-2 px-3 py-2 text-xs text-gray-500 font-medium">
                <Calendar size={14} />
                날짜별 대화
              </div>
              {isLoadingDates ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="animate-spin text-gray-400" size={20} />
                </div>
              ) : dates.length > 0 ? (
                dates.map((d) => (
                  <button
                    key={d.date}
                    onClick={() => setSelectedDate(d.date)}
                    className={`w-full text-left px-3 py-2.5 rounded-lg mb-1 transition-colors flex items-center justify-between ${
                      selectedDate === d.date
                        ? 'bg-amber-100 text-amber-700'
                        : 'hover:bg-gray-100 text-gray-700'
                    }`}
                  >
                    <span className="text-sm">{formatDate(d.date)}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      selectedDate === d.date ? 'bg-amber-200 text-amber-800' : 'bg-gray-200 text-gray-600'
                    }`}>
                      {d.count}
                    </span>
                  </button>
                ))
              ) : (
                <p className="text-xs text-gray-400 px-3 py-4 text-center">대화 기록이 없습니다</p>
              )}
            </div>
          </div>

          {/* 오른쪽: 대화 내용 */}
          <div className="flex-1 flex flex-col overflow-hidden bg-gray-50">
            {selectedDate ? (
              <>
                <div className="px-4 py-2.5 bg-white border-b border-gray-200 shrink-0">
                  <span className="text-sm font-medium text-gray-700">
                    {formatDate(selectedDate)} 대화
                  </span>
                  <span className="text-xs text-gray-500 ml-2">
                    ({conversations.length}개 메시지)
                  </span>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                  {isLoadingConversations ? (
                    <div className="flex items-center justify-center h-full">
                      <RefreshCw className="animate-spin text-gray-400" size={24} />
                    </div>
                  ) : conversations.length > 0 ? (
                    <>
                      {conversations.map((conv) => (
                        <div
                          key={conv.id}
                          className={`flex ${conv.role === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                          <div
                            className={`max-w-[75%] rounded-2xl px-4 py-2.5 ${
                              conv.role === 'user'
                                ? 'bg-amber-500 text-white rounded-br-md'
                                : 'bg-white border border-gray-200 text-gray-800 rounded-bl-md shadow-sm'
                            }`}
                          >
                            <div className={`text-[10px] mb-1 ${
                              conv.role === 'user' ? 'text-amber-200' : 'text-gray-400'
                            }`}>
                              {formatTime(conv.timestamp)}
                            </div>
                            {conv.role === 'assistant' ? (
                              <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2">
                                <ReactMarkdown>{conv.content}</ReactMarkdown>
                              </div>
                            ) : (
                              <p className="text-sm whitespace-pre-wrap">{conv.content}</p>
                            )}
                          </div>
                        </div>
                      ))}
                      <div ref={messagesEndRef} />
                    </>
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-400">
                      선택한 날짜에 대화가 없습니다
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-gray-400">
                <ChevronRight size={32} className="mb-2 opacity-50" />
                <p className="text-sm">날짜를 선택하세요</p>
              </div>
            )}
          </div>
        </div>

        {/* 푸터 */}
        <div className="flex justify-end px-5 py-3 border-t border-gray-200 bg-white shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 text-gray-700 transition-colors"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
