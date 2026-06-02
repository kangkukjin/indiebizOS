/**
 * ToolSearchDialog - 도구 검색 다이얼로그 (Nostr 기반)
 *
 * 기능:
 * - Nostr에서 공개된 패키지 검색
 * - 패키지 상세 정보 표시
 * - 시스템 AI와 대화하며 설치 진행
 */

import { useState, useEffect, useRef } from 'react';
import {
  X,
  Search,
  Package,
  Download,
  Loader2,
  AlertCircle,
  Send,
  Bot,
  User,
  RefreshCw,
  Clock,
} from 'lucide-react';
import { api } from '../../../lib/api';

interface NostrPackage {
  id: string;
  name: string;
  description: string;
  version: string;
  install: string;
  author: string;
  timestamp: number;
  raw_content: string;
}

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
}

interface ToolSearchDialogProps {
  show: boolean;
  onClose: () => void;
}

// 설치 검토 프롬프트
const INSTALL_REVIEW_PROMPT = `이 패키지를 설치하기 전에 다음을 검토해주세요:

1. 보안 검토
   - 설치 명령에 위험한 패턴이 있는지 (rm -rf, curl | sh, 알 수 없는 스크립트 실행 등)
   - 과도한 권한을 요구하는지

2. 품질 검토
   - 패키지 설명이 충분히 명확한지
   - 뭘 하는 도구인지 이해할 수 있는지
   - 설치 방법이 구체적으로 명시되어 있는지

3. 호환성 검토
   - 현재 시스템에서 설치 가능한지
   - 필요한 의존성이 명시되어 있는지

문제가 있으면 설치를 진행하지 말고 사용자에게 무엇이 문제인지 설명해주세요.
문제가 없으면 설치를 진행하고 결과를 알려주세요.`;

export function ToolSearchDialog({ show, onClose }: ToolSearchDialogProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [packages, setPackages] = useState<NostrPackage[]>([]);
  const [selectedPackage, setSelectedPackage] = useState<NostrPackage | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 채팅 관련 상태
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // 초기 로드
  useEffect(() => {
    if (show && isInitialLoad) {
      handleSearch();
      setIsInitialLoad(false);
    }
  }, [show, isInitialLoad]);

  // 채팅 스크롤
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  // 다이얼로그 닫힐 때 상태 초기화
  useEffect(() => {
    if (!show) {
      setSelectedPackage(null);
      setChatMessages([]);
      setChatInput('');
    }
  }, [show]);

  const handleSearch = async () => {
    setIsSearching(true);
    setError(null);
    try {
      const result = await api.searchPackagesOnNostr(searchQuery || undefined, 30);
      setPackages(result.packages);
      if (result.packages.length === 0) {
        setError('검색 결과가 없습니다.');
      }
    } catch (err: any) {
      setError(err.message || '검색 중 오류가 발생했습니다.');
      setPackages([]);
    } finally {
      setIsSearching(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const handleInstallRequest = async (pkg: NostrPackage) => {
    setSelectedPackage(pkg);

    // 시스템 메시지 추가
    const systemMessage: ChatMessage = {
      role: 'system',
      content: `📦 **${pkg.name}** 패키지 설치를 요청했습니다.`,
      timestamp: new Date(),
    };

    // 사용자 메시지 (설치 요청)
    const userMessage: ChatMessage = {
      role: 'user',
      content: `다음 패키지를 검토하고 설치해주세요:

패키지 이름: ${pkg.name}
설명: ${pkg.description}
버전: ${pkg.version}
설치 방법: ${pkg.install}

${INSTALL_REVIEW_PROMPT}`,
      timestamp: new Date(),
    };

    setChatMessages([systemMessage, userMessage]);
    setIsChatLoading(true);

    try {
      // 시스템 AI에게 요청
      const response = await api.chatWithSystemAI(userMessage.content);

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: response.response,
        timestamp: new Date(),
      };

      setChatMessages((prev) => [...prev, assistantMessage]);
    } catch (err: any) {
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: `⚠️ 오류가 발생했습니다: ${err.message || '알 수 없는 오류'}`,
        timestamp: new Date(),
      };
      setChatMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleSendChat = async () => {
    if (!chatInput.trim() || isChatLoading) return;

    const userMessage: ChatMessage = {
      role: 'user',
      content: chatInput,
      timestamp: new Date(),
    };

    setChatMessages((prev) => [...prev, userMessage]);
    setChatInput('');
    setIsChatLoading(true);

    try {
      const response = await api.chatWithSystemAI(chatInput);

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: response.response,
        timestamp: new Date(),
      };

      setChatMessages((prev) => [...prev, assistantMessage]);
    } catch (err: any) {
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: `⚠️ 오류가 발생했습니다: ${err.message || '알 수 없는 오류'}`,
        timestamp: new Date(),
      };
      setChatMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const formatTimestamp = (timestamp: number) => {
    const date = new Date(timestamp * 1000);
    return date.toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const truncateAuthor = (author: string) => {
    if (author.length > 16) {
      return author.slice(0, 8) + '...' + author.slice(-8);
    }
    return author;
  };

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{
          width: 'min(1100px, 95vw)',
          height: 'min(750px, 90vh)',
        }}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-purple-50 to-indigo-50 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center">
              <Search size={22} className="text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-800">도구 검색</h2>
              <p className="text-xs text-gray-500">Nostr 네트워크에서 공개된 도구를 찾아보세요</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-200 rounded-lg transition-colors"
          >
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        {/* 검색바 */}
        <div className="px-6 py-3 border-b border-gray-100 bg-gray-50 shrink-0">
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Search
                size={18}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
              />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="패키지 이름 또는 키워드로 검색..."
                className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
              />
            </div>
            <button
              onClick={handleSearch}
              disabled={isSearching}
              className="px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 disabled:opacity-50 flex items-center gap-2 transition-colors"
            >
              {isSearching ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <Search size={18} />
              )}
              검색
            </button>
            <button
              onClick={() => {
                setSearchQuery('');
                handleSearch();
              }}
              disabled={isSearching}
              className="p-2 text-gray-500 hover:bg-gray-200 rounded-lg transition-colors"
              title="새로고침"
            >
              <RefreshCw size={18} />
            </button>
          </div>
        </div>

        {/* 컨텐츠 영역 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 패키지 목록 */}
          <div className="w-1/3 border-r border-gray-200 overflow-y-auto bg-gray-50">
            {isSearching ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-400">
                <Loader2 size={32} className="animate-spin mb-3" />
                <p className="text-sm">검색 중...</p>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-400 p-4">
                <AlertCircle size={32} className="mb-3 text-yellow-500" />
                <p className="text-sm text-center">{error}</p>
              </div>
            ) : packages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-400 p-4">
                <Package size={32} className="mb-3 opacity-50" />
                <p className="text-sm text-center">검색어를 입력하고 검색 버튼을 누르세요</p>
              </div>
            ) : (
              <div className="p-3 space-y-2">
                {packages.map((pkg) => (
                  <div
                    key={pkg.id}
                    onClick={() => setSelectedPackage(pkg)}
                    className={`p-3 rounded-lg cursor-pointer transition-all ${
                      selectedPackage?.id === pkg.id
                        ? 'bg-purple-50 border-2 border-purple-300'
                        : 'bg-white border border-gray-200 hover:border-gray-300 hover:shadow-sm'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-9 h-9 rounded-lg bg-purple-100 text-purple-600 flex items-center justify-center shrink-0">
                        <Package size={18} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-gray-800 text-sm truncate">
                          {pkg.name}
                        </h3>
                        <p className="text-xs text-gray-500 truncate">
                          {pkg.description || '설명 없음'}
                        </p>
                        <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                          <span>v{pkg.version}</span>
                          <span>•</span>
                          <Clock size={10} />
                          <span>{formatTimestamp(pkg.timestamp)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 상세 정보 + 채팅 */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {selectedPackage ? (
              <>
                {/* 패키지 상세 정보 */}
                <div className="p-4 border-b border-gray-200 shrink-0">
                  <div className="flex items-start gap-4">
                    <div className="w-14 h-14 rounded-xl bg-purple-100 text-purple-600 flex items-center justify-center shrink-0">
                      <Package size={28} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="text-xl font-bold text-gray-800">
                          {selectedPackage.name}
                        </h3>
                        <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
                          v{selectedPackage.version}
                        </span>
                      </div>
                      <p className="text-sm text-gray-600 mt-1">
                        {selectedPackage.description || '설명이 없습니다.'}
                      </p>
                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-400">
                        <span title={selectedPackage.author}>
                          작성자: {truncateAuthor(selectedPackage.author)}
                        </span>
                        <span>{formatTimestamp(selectedPackage.timestamp)}</span>
                      </div>
                    </div>
                    <button
                      onClick={() => handleInstallRequest(selectedPackage)}
                      disabled={isChatLoading}
                      className="px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 disabled:opacity-50 flex items-center gap-2 transition-colors shrink-0"
                    >
                      {isChatLoading ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Download size={16} />
                      )}
                      설치하기
                    </button>
                  </div>

                  {/* 설치 방법 */}
                  {selectedPackage.install && (
                    <div className="mt-3 p-3 bg-gray-50 rounded-lg">
                      <h4 className="text-xs font-medium text-gray-700 mb-1">
                        설치 방법
                      </h4>
                      <pre className="text-xs text-gray-600 whitespace-pre-wrap font-mono">
                        {selectedPackage.install}
                      </pre>
                    </div>
                  )}
                </div>

                {/* 채팅 영역 */}
                <div className="flex-1 flex flex-col overflow-hidden bg-gray-50">
                  {/* 채팅 메시지 */}
                  <div className="flex-1 overflow-y-auto p-4 space-y-3">
                    {chatMessages.length === 0 ? (
                      <div className="flex flex-col items-center justify-center h-full text-gray-400">
                        <Bot size={40} className="mb-3 opacity-50" />
                        <p className="text-sm text-center">
                          "설치하기" 버튼을 누르면
                          <br />
                          시스템 AI가 패키지를 검토하고 설치를 진행합니다.
                        </p>
                      </div>
                    ) : (
                      chatMessages.map((msg, idx) => (
                        <div
                          key={idx}
                          className={`flex items-start gap-2 ${
                            msg.role === 'user' ? 'flex-row-reverse' : ''
                          }`}
                        >
                          <div
                            className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                              msg.role === 'user'
                                ? 'bg-blue-100 text-blue-600'
                                : msg.role === 'system'
                                ? 'bg-gray-200 text-gray-500'
                                : 'bg-purple-100 text-purple-600'
                            }`}
                          >
                            {msg.role === 'user' ? (
                              <User size={16} />
                            ) : (
                              <Bot size={16} />
                            )}
                          </div>
                          <div
                            className={`max-w-[80%] p-3 rounded-lg ${
                              msg.role === 'user'
                                ? 'bg-blue-500 text-white'
                                : msg.role === 'system'
                                ? 'bg-gray-200 text-gray-700'
                                : 'bg-white border border-gray-200 text-gray-800'
                            }`}
                          >
                            <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                          </div>
                        </div>
                      ))
                    )}
                    {isChatLoading && (
                      <div className="flex items-start gap-2">
                        <div className="w-8 h-8 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center shrink-0">
                          <Bot size={16} />
                        </div>
                        <div className="bg-white border border-gray-200 p-3 rounded-lg">
                          <Loader2 size={16} className="animate-spin text-purple-500" />
                        </div>
                      </div>
                    )}
                    <div ref={chatEndRef} />
                  </div>

                  {/* 채팅 입력 */}
                  <div className="p-3 border-t border-gray-200 bg-white shrink-0">
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={chatInput}
                        onChange={(e) => setChatInput(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && handleSendChat()}
                        placeholder="시스템 AI에게 메시지 보내기..."
                        className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
                        disabled={isChatLoading}
                      />
                      <button
                        onClick={handleSendChat}
                        disabled={!chatInput.trim() || isChatLoading}
                        className="px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 disabled:opacity-50 transition-colors"
                      >
                        <Send size={18} />
                      </button>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-gray-400 p-4">
                <Package size={48} className="mb-3 opacity-50" />
                <p className="text-sm">왼쪽에서 패키지를 선택하세요</p>
                <p className="text-xs mt-1 text-center">
                  패키지를 선택하면 상세 정보를 확인하고
                  <br />
                  시스템 AI에게 설치를 요청할 수 있습니다.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
