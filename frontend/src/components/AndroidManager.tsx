/**
 * AndroidManager.tsx
 * 안드로이드 폰 관리 UI (전화, 문자, 연락처, 앱)
 * 하단에 AI 대화창 포함 - 프로젝트 에이전트와 연결됨
 *
 * 문자 탭 → AndroidMessagesTab.tsx
 * 앱 정리 탭 → AndroidAppsTab.tsx
 */

import { useState, useEffect, useRef } from 'react';
import {
  Phone, MessageSquare, Users, Clock, PhoneIncoming, PhoneOutgoing,
  PhoneMissed, Trash2, Search, Send, RefreshCw, Smartphone,
  Loader2, Package, Edit3
} from 'lucide-react';
import { AndroidMessagesTab } from './AndroidMessagesTab';
import type { SMSItem, ContactItem } from './AndroidMessagesTab';
import { AndroidAppsTab } from './AndroidAppsTab';
import type { AppItem } from './AndroidAppsTab';

// API 기본 URL
const getApiUrl = () => {
  const port = (window as any).electronAPI?.getApiPort?.() || 8765;
  return `http://127.0.0.1:${port}`;
};

// WebSocket URL
const getWsUrl = () => {
  const port = (window as any).electronAPI?.getApiPort?.() || 8765;
  return `ws://127.0.0.1:${port}`;
};

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface CallItem {
  _id: string;
  number: string;
  name?: string;
  date_formatted: string;
  duration_formatted?: string;
  call_type: 'incoming' | 'outgoing' | 'missed' | 'rejected';
}

type TabType = 'recent' | 'contacts' | 'messages' | 'apps';

interface AndroidManagerProps {
  deviceId?: string | null;
  projectId?: string | null;
}

export function AndroidManager(_props: AndroidManagerProps) {
  // 탭 상태
  const [activeTab, setActiveTab] = useState<TabType>('recent');

  // 데이터 상태
  const [callLog, setCallLog] = useState<CallItem[]>([]);
  const [smsList, setSmsList] = useState<SMSItem[]>([]);
  const [contacts, setContacts] = useState<ContactItem[]>([]);
  const [apps, setApps] = useState<AppItem[]>([]);
  const [deviceInfo, setDeviceInfo] = useState<any>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // 로딩 상태
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // 검색 (최근기록 & 연락처 탭용)
  const [searchQuery, setSearchQuery] = useState('');

  // 페이지네이션
  const PAGE_SIZE = 100;

  const [smsPage, setSmsPage] = useState(0);
  const [smsTotalCount, setSmsTotalCount] = useState(0);
  const [smsHasMore, setSmsHasMore] = useState(false);

  const [callPage, setCallPage] = useState(0);
  const [callTotalCount, setCallTotalCount] = useState(0);
  const [callHasMore, setCallHasMore] = useState(false);

  const [contactPage, setContactPage] = useState(0);
  const [contactTotalCount, setContactTotalCount] = useState(0);
  const [contactHasMore, setContactHasMore] = useState(false);

  const [appPage, setAppPage] = useState(0);
  const [appTotalCount, setAppTotalCount] = useState(0);
  const [appHasMore, setAppHasMore] = useState(false);

  // AI 대화
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const streamingMessageRef = useRef<string>('');

  // 안드로이드 전용 에이전트 ID
  const [androidAgentId, setAndroidAgentId] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);

  // ─── 초기 로드 ─────────────────────

  useEffect(() => {
    checkConnection();
    startAndroidAgent();
    return () => { stopAndroidAgent(); };
  }, []);

  // 안드로이드 전용 에이전트 시작
  const startAndroidAgent = async () => {
    try {
      console.log('[AndroidManager] 에이전트 시작 요청...');
      const res = await fetch(`${getApiUrl()}/android/agent/start`, { method: 'POST' });
      const data = await res.json();
      console.log('[AndroidManager] 에이전트 응답:', data);
      if (data.success && data.agent_id) {
        setAndroidAgentId(data.agent_id);
      } else {
        console.error('[AndroidManager] 에이전트 시작 실패:', data.error || '알 수 없는 오류');
      }
    } catch (e) {
      console.error('[AndroidManager] 에이전트 시작 예외:', e);
    }
  };

  const stopAndroidAgent = async () => {
    if (!androidAgentId) return;
    try {
      await fetch(`${getApiUrl()}/android/agent/stop`, { method: 'POST' });
      console.log('[AndroidManager] 에이전트 종료');
    } catch (e) {
      console.error('[AndroidManager] 에이전트 종료 실패:', e);
    }
  };

  // ─── WebSocket 연결 ────────────────

  useEffect(() => {
    if (!androidAgentId) return;

    const wsUrl = `${getWsUrl()}/ws/android/${androidAgentId}`;
    console.log('[AndroidManager] WebSocket 연결:', wsUrl);

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[AndroidManager] WebSocket 연결됨');
      setWsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'chunk') {
          streamingMessageRef.current += data.content;
          setMessages(prev => {
            const updated = [...prev];
            if (updated.length > 0 && updated[updated.length - 1].role === 'assistant') {
              updated[updated.length - 1].content = streamingMessageRef.current;
            }
            return updated;
          });
        } else if (data.type === 'done') {
          setIsStreaming(false);
          streamingMessageRef.current = '';
          loadAllData();
        } else if (data.type === 'error') {
          setIsStreaming(false);
          streamingMessageRef.current = '';
          addAssistantMessage(`오류: ${data.message}`);
        }
      } catch (e) {
        console.error('[AndroidManager] WebSocket 메시지 파싱 오류:', e);
      }
    };

    ws.onerror = (error) => {
      console.error('[AndroidManager] WebSocket 오류:', error);
    };

    ws.onclose = () => {
      console.log('[AndroidManager] WebSocket 연결 종료');
      setWsConnected(false);
    };

    return () => { ws.close(); };
  }, [androidAgentId]);

  // 스크롤
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ─── 데이터 로드 ───────────────────

  const checkConnection = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`${getApiUrl()}/android/devices`);
      const data = await res.json();
      if (data.success && data.devices?.length > 0) {
        setIsConnected(true);
        setDeviceInfo(data.devices[0]);
        loadAllData();
      } else if (data.detail) {
        setIsConnected(false);
        setErrorMessage(data.detail);
      } else if (data.message) {
        setIsConnected(false);
        setErrorMessage(data.message);
      } else {
        setIsConnected(false);
      }
    } catch (e: any) {
      console.error('[AndroidManager] checkConnection error:', e);
      setIsConnected(false);
      setErrorMessage(e.message || '서버 연결 실패');
    }
    setLoading(false);
  };

  const loadAllData = async () => {
    setRefreshing(true);
    await Promise.all([loadCallLog(), loadSMS(), loadContacts(), loadApps()]);
    setRefreshing(false);
  };

  const loadCallLog = async (page: number = 0) => {
    try {
      const offset = page * PAGE_SIZE;
      const res = await fetch(`${getApiUrl()}/android/calls?limit=${PAGE_SIZE}&offset=${offset}`);
      const data = await res.json();
      if (data.success) {
        setCallLog(data.calls || []);
        setCallTotalCount(data.total || data.count || 0);
        setCallHasMore(data.has_more || false);
        setCallPage(page);
      }
    } catch (e) {
      console.error('통화 기록 로드 실패:', e);
    }
  };

  const loadSMS = async (page: number = 0) => {
    try {
      const offset = page * PAGE_SIZE;
      const res = await fetch(`${getApiUrl()}/android/messages?box=all&limit=${PAGE_SIZE}&offset=${offset}`);
      const data = await res.json();
      if (data.success) {
        setSmsList(data.messages || []);
        setSmsTotalCount(data.total || data.count || 0);
        setSmsHasMore(data.has_more || false);
        setSmsPage(page);
      }
    } catch (e) {
      console.error('메시지 로드 실패:', e);
    }
  };

  const loadContacts = async (page: number = 0) => {
    try {
      const offset = page * PAGE_SIZE;
      const res = await fetch(`${getApiUrl()}/android/contacts?limit=${PAGE_SIZE}&offset=${offset}`);
      const data = await res.json();
      if (data.success) {
        setContacts(data.contacts || []);
        setContactTotalCount(data.total || data.count || 0);
        setContactHasMore(data.has_more || false);
        setContactPage(page);
      }
    } catch (e) {
      console.error('연락처 로드 실패:', e);
    }
  };

  const loadApps = async (page: number = 0) => {
    try {
      const offset = page * PAGE_SIZE;
      const res = await fetch(`${getApiUrl()}/android/apps?limit=${PAGE_SIZE}&offset=${offset}`);
      const data = await res.json();
      if (data.success) {
        setApps(data.apps || []);
        setAppTotalCount(data.total || data.count || 0);
        setAppHasMore(data.has_more || false);
        setAppPage(page);
      }
    } catch (e) {
      console.error('앱 목록 로드 실패:', e);
    }
  };

  // ─── 핸들러 ────────────────────────

  const makeCall = async (phoneNumber: string) => {
    try {
      const res = await fetch(`${getApiUrl()}/android/calls/make`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: phoneNumber })
      });
      const data = await res.json();
      if (data.success) {
        addAssistantMessage(`${phoneNumber}에 전화를 겁니다.`);
      }
    } catch (e) {
      console.error('전화 걸기 실패:', e);
    }
  };

  const deleteCallLog = async (callId: string) => {
    if (!confirm('이 통화 기록을 삭제하시겠습니까?')) return;
    try {
      const res = await fetch(`${getApiUrl()}/android/calls/${callId}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) {
        setCallLog(prev => prev.filter(c => c._id !== callId));
      }
    } catch (e) {
      console.error('통화 기록 삭제 실패:', e);
    }
  };

  const deleteContact = async (contactId: string, contactName: string) => {
    if (!confirm(`'${contactName}' 연락처를 삭제하시겠습니까?`)) return;
    try {
      const res = await fetch(`${getApiUrl()}/android/contacts/${contactId}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) {
        setContacts(prev => prev.filter(c => c.id !== contactId));
        setContactTotalCount(prev => prev - 1);
        addAssistantMessage(`연락처 '${contactName}'이(가) 삭제되었습니다.`);
      } else {
        addAssistantMessage(`연락처 삭제 실패: ${data.message || '알 수 없는 오류'}`);
      }
    } catch (e) {
      console.error('연락처 삭제 실패:', e);
      addAssistantMessage('연락처 삭제 중 오류가 발생했습니다.');
    }
  };

  // AI 메시지 추가
  const addAssistantMessage = (content: string) => {
    setMessages(prev => [...prev, { role: 'assistant', content }]);
  };

  // AI 대화 전송
  const sendMessage = async () => {
    if (!inputValue.trim() || isStreaming) return;

    const userMessage = inputValue.trim();
    setInputValue('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsStreaming(true);

    if (wsConnected && wsRef.current) {
      setMessages(prev => [...prev, { role: 'assistant', content: '' }]);
      streamingMessageRef.current = '';
      wsRef.current.send(JSON.stringify({ type: 'chat', message: userMessage }));
    } else {
      try {
        const res = await fetch(`${getApiUrl()}/android/ai-command`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command: userMessage })
        });
        const data = await res.json();
        if (data.success) {
          addAssistantMessage(data.response || data.message);
          if (data.refresh) loadAllData();
        } else {
          addAssistantMessage(data.error || '명령을 처리할 수 없습니다.');
        }
      } catch (e) {
        addAssistantMessage('오류가 발생했습니다. 다시 시도해주세요.');
      }
      setIsStreaming(false);
    }
  };

  /* 추후 연락처 이름 표시에 사용
  const contactMap = useMemo(() => {
    const map: Record<string, string> = {};
    contacts.forEach(c => {
      if (c.phone && c.name) {
        const normalizedPhone = c.phone.replace(/[-\s]/g, '');
        map[normalizedPhone] = c.name;
        map[c.phone] = c.name;
      }
    });
    return map;
  }, [contacts]);

  const getContactName = (phone: string): string => {
    if (!phone) return phone;
    const normalized = phone.replace(/[-\s]/g, '');
    return contactMap[normalized] || contactMap[phone] || phone;
  }; */

  // 검색 필터링 (최근기록 & 연락처 탭)
  const filteredCallLog = callLog.filter(c =>
    c.number?.includes(searchQuery) || c.name?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredContacts = contacts.filter(c =>
    c.name?.toLowerCase().includes(searchQuery.toLowerCase()) || c.phone?.includes(searchQuery)
  );

  // 통화 유형 아이콘
  const getCallIcon = (type: string) => {
    switch (type) {
      case 'incoming': return <PhoneIncoming className="w-4 h-4 text-green-500" />;
      case 'outgoing': return <PhoneOutgoing className="w-4 h-4 text-blue-500" />;
      case 'missed': return <PhoneMissed className="w-4 h-4 text-red-500" />;
      default: return <Phone className="w-4 h-4 text-gray-500" />;
    }
  };

  // ─── 로딩 화면 ─────────────────────

  if (loading) {
    return (
      <div className="h-full flex flex-col bg-gray-900 text-white">
        <div
          className="h-8 bg-gray-800 flex items-center justify-center shrink-0"
          style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}
        >
          <span className="text-xs text-gray-500">Android Manager</span>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <Loader2 className="w-12 h-12 text-blue-500 animate-spin mb-4" />
          <p className="text-gray-400">기기 연결 확인 중...</p>
        </div>
      </div>
    );
  }

  // ─── 연결 안됨 화면 ────────────────

  if (!isConnected) {
    return (
      <div className="h-full flex flex-col bg-gray-900 text-white">
        <div
          className="h-8 bg-gray-800 flex items-center justify-center shrink-0"
          style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}
        >
          <span className="text-xs text-gray-500">Android Manager</span>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <Smartphone className="w-16 h-16 text-gray-500 mb-4" />
          <h2 className="text-xl font-semibold mb-2">Android 기기가 연결되지 않았습니다</h2>
          <p className="text-gray-400 text-center mb-4">
            USB 케이블로 기기를 연결하고<br />
            USB 디버깅을 활성화해주세요.
          </p>
          {errorMessage && (
            <p className="text-red-400 text-xs text-center mb-4 max-w-xs bg-red-900/30 p-2 rounded">
              {errorMessage}
            </p>
          )}
          <button
            onClick={checkConnection}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 rounded-lg hover:bg-blue-700"
          >
            <RefreshCw className="w-4 h-4" />
            다시 확인
          </button>
        </div>
      </div>
    );
  }

  // ─── 메인 렌더링 ───────────────────

  return (
    <div className="h-full flex flex-col bg-gray-900 text-white">
      {/* 드래그 영역 (macOS) */}
      <div
        className="h-8 bg-gray-800 flex items-center justify-center shrink-0"
        style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}
      >
        <span className="text-xs text-gray-500">Android Manager</span>
      </div>

      {/* 헤더 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 bg-gray-800">
        <div className="flex items-center gap-3">
          <Smartphone className="w-5 h-5 text-green-500" />
          <span className="font-medium">
            {deviceInfo?.model || 'Android'}
          </span>
          <span className="text-xs text-gray-400">연결됨</span>
        </div>
        <button
          onClick={loadAllData}
          disabled={refreshing}
          className="p-2 hover:bg-gray-700 rounded-lg"
          style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* 탭 */}
      <div className="flex border-b border-gray-700">
        {([
          { key: 'recent' as const, icon: Clock, label: '최근기록' },
          { key: 'contacts' as const, icon: Users, label: '연락처' },
          { key: 'messages' as const, icon: MessageSquare, label: '문자' },
          { key: 'apps' as const, icon: Package, label: '앱정리' },
        ]).map(tab => (
          <button
            key={tab.key}
            onClick={() => { setActiveTab(tab.key); setSearchQuery(''); }}
            className={`flex-1 py-3 flex items-center justify-center gap-2 ${
              activeTab === tab.key ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* 컨텐츠 영역 */}
      <div className="flex-1 overflow-y-auto">

        {/* 최근 기록 탭 */}
        {activeTab === 'recent' && (
          <>
            {/* 검색 */}
            <div className="px-4 py-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  placeholder="검색..."
                  className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>
            <div className="flex flex-col h-full">
              <div className="flex-1 divide-y divide-gray-800 overflow-y-auto">
                {filteredCallLog.length === 0 ? (
                  <div className="p-8 text-center">
                    <p className="text-gray-500 mb-2">통화 기록이 없습니다</p>
                    <p className="text-xs text-gray-600">Android 보안 정책으로 ADB를 통한<br/>통화 기록 접근이 제한될 수 있습니다.</p>
                  </div>
                ) : (
                  filteredCallLog.map(call => (
                    <div key={call._id} className="flex items-center px-4 py-3 hover:bg-gray-800">
                      <div className="mr-3">{getCallIcon(call.call_type)}</div>
                      <div
                        className="flex-1 min-w-0 cursor-pointer hover:text-green-400 transition-colors"
                        onClick={() => makeCall(call.number)}
                        title={`${call.number}에 전화 걸기`}
                      >
                        <div className="font-medium truncate">{call.name || call.number}</div>
                        <div className="text-xs text-gray-500">
                          {call.date_formatted} {call.duration_formatted && `• ${call.duration_formatted}`}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => makeCall(call.number)}
                          className="p-2 hover:bg-gray-700 rounded-full text-green-500"
                          title="전화 걸기"
                        >
                          <Phone className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => deleteCallLog(call._id)}
                          className="p-2 hover:bg-gray-700 rounded-full text-red-500"
                          title="삭제"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* 페이지네이션 */}
              {callTotalCount > PAGE_SIZE && (
                <div className="sticky bottom-0 bg-gray-800 border-t border-gray-700 px-4 py-3 flex items-center justify-between">
                  <div className="text-xs text-gray-400">
                    전체 {callTotalCount}개 중 {callPage * PAGE_SIZE + 1}~{Math.min((callPage + 1) * PAGE_SIZE, callTotalCount)}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => loadCallLog(callPage - 1)}
                      disabled={callPage === 0}
                      className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      이전
                    </button>
                    <span className="text-sm text-gray-300">
                      {callPage + 1} / {Math.ceil(callTotalCount / PAGE_SIZE)}
                    </span>
                    <button
                      onClick={() => loadCallLog(callPage + 1)}
                      disabled={!callHasMore}
                      className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      다음
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}

        {/* 연락처 탭 */}
        {activeTab === 'contacts' && (
          <>
            {/* 검색 */}
            <div className="px-4 py-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  placeholder="검색..."
                  className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>
            <div className="flex flex-col h-full">
              <div className="flex-1 divide-y divide-gray-800 overflow-y-auto">
                {filteredContacts.length === 0 ? (
                  <div className="p-8 text-center">
                    <p className="text-gray-500 mb-2">연락처가 없습니다</p>
                    <p className="text-xs text-gray-600">Android 보안 정책으로 연락처 접근이<br/>제한될 수 있습니다.</p>
                  </div>
                ) : (
                  filteredContacts.map(contact => (
                    <div key={contact.id} className="flex items-center px-4 py-3 hover:bg-gray-800">
                      <div className="w-10 h-10 bg-gray-700 rounded-full flex items-center justify-center mr-3">
                        <span className="text-lg">{contact.name.charAt(0)}</span>
                      </div>
                      <div
                        className="flex-1 min-w-0 cursor-pointer hover:text-green-400 transition-colors"
                        onClick={() => makeCall(contact.phone)}
                        title={`${contact.phone}에 전화 걸기`}
                      >
                        <div className="font-medium truncate">{contact.name}</div>
                        <div className="text-xs text-gray-500">{contact.phone}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => makeCall(contact.phone)}
                          className="p-2 hover:bg-gray-700 rounded-full text-green-500"
                          title="전화 걸기"
                        >
                          <Phone className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => {
                            // 연락처 탭에서 문자 보내기 → 문자 탭의 모달을 직접 열 수 없으므로,
                            // 문자 탭으로 이동 시키되 AI에게 알림
                            addAssistantMessage(`${contact.name} (${contact.phone})에게 문자를 보내려면 문자 탭으로 이동하세요.`);
                          }}
                          className="p-2 hover:bg-gray-700 rounded-full text-yellow-500"
                          title="문자 보내기"
                        >
                          <Edit3 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => {
                            setActiveTab('messages');
                          }}
                          className="p-2 hover:bg-gray-700 rounded-full text-blue-500"
                          title="문자 보기"
                        >
                          <MessageSquare className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => deleteContact(contact.id, contact.name)}
                          className="p-2 hover:bg-gray-700 rounded-full text-red-500"
                          title="연락처 삭제"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* 페이지네이션 */}
              {contactTotalCount > PAGE_SIZE && (
                <div className="sticky bottom-0 bg-gray-800 border-t border-gray-700 px-4 py-3 flex items-center justify-between">
                  <div className="text-xs text-gray-400">
                    전체 {contactTotalCount}개 중 {contactPage * PAGE_SIZE + 1}~{Math.min((contactPage + 1) * PAGE_SIZE, contactTotalCount)}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => loadContacts(contactPage - 1)}
                      disabled={contactPage === 0}
                      className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      이전
                    </button>
                    <span className="text-sm text-gray-300">
                      {contactPage + 1} / {Math.ceil(contactTotalCount / PAGE_SIZE)}
                    </span>
                    <button
                      onClick={() => loadContacts(contactPage + 1)}
                      disabled={!contactHasMore}
                      className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      다음
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}

        {/* 문자 탭 → AndroidMessagesTab */}
        {activeTab === 'messages' && (
          <AndroidMessagesTab
            getApiUrl={getApiUrl}
            smsList={smsList}
            contacts={contacts}
            addAssistantMessage={addAssistantMessage}
            loadSMS={loadSMS}
            smsPage={smsPage}
            smsTotalCount={smsTotalCount}
            smsHasMore={smsHasMore}
            PAGE_SIZE={PAGE_SIZE}
          />
        )}

        {/* 앱 정리 탭 → AndroidAppsTab */}
        {activeTab === 'apps' && (
          <AndroidAppsTab
            getApiUrl={getApiUrl}
            apps={apps}
            setApps={setApps}
            addAssistantMessage={addAssistantMessage}
            loadApps={loadApps}
            appPage={appPage}
            appTotalCount={appTotalCount}
            appHasMore={appHasMore}
            PAGE_SIZE={PAGE_SIZE}
          />
        )}
      </div>

      {/* AI 대화창 */}
      <div className="border-t border-gray-700 bg-gray-850">
        {messages.length > 0 && (
          <div className="max-h-32 overflow-y-auto px-4 py-2 space-y-2 bg-gray-800/50">
            {messages.slice(-3).map((msg, i) => (
              <div key={i} className={`text-sm ${msg.role === 'user' ? 'text-blue-300' : 'text-gray-300'}`}>
                <span className="font-medium">{msg.role === 'user' ? '나: ' : 'AI: '}</span>
                {msg.content}
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>
        )}

        <div className="flex items-center gap-2 p-3">
          <input
            type="text"
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && sendMessage()}
            placeholder="AI에게 명령하기... (예: 엄마한테 온 문자만 보여줘)"
            className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-full text-sm focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={sendMessage}
            disabled={isStreaming || !inputValue.trim()}
            className="p-2 bg-blue-600 rounded-full hover:bg-blue-700 disabled:opacity-50"
          >
            {isStreaming ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
