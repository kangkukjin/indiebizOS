/**
 * AndroidManager.tsx
 * 안드로이드 폰 관리 UI (전화, 문자, 연락처)
 * 하단에 AI 대화창 포함 - 프로젝트 에이전트와 연결됨
 */

import { useState, useEffect, useRef, useMemo } from 'react';
import {
  Phone, MessageSquare, Users, Clock, PhoneIncoming, PhoneOutgoing,
  PhoneMissed, Trash2, Search, Send, RefreshCw, Smartphone,
  X, Loader2, Package, HardDrive, Clock3, Edit3, Plus
} from 'lucide-react';

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

interface SMSItem {
  _id: string;
  address: string;
  body: string;
  date_formatted: string;
  direction: 'received' | 'sent';
  read?: string;
  message_type?: 'sms' | 'mms';  // SMS/MMS 구분
}

interface CallItem {
  _id: string;
  number: string;
  name?: string;
  date_formatted: string;
  duration_formatted?: string;
  call_type: 'incoming' | 'outgoing' | 'missed' | 'rejected';
}

interface ContactItem {
  id: string;
  name: string;
  phone: string;
}

interface AppItem {
  package: string;
  name: string;
  size?: string;
  last_used?: string;
  total_time_formatted?: string;
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
  const [selectedApps, setSelectedApps] = useState<Set<string>>(new Set());
  const [deletingApp, setDeletingApp] = useState<string | null>(null);
  const [selectedSMS, setSelectedSMS] = useState<Set<string>>(new Set());
  const [deletingSMS, setDeletingSMS] = useState(false);
  const [smsViewMode, setSmsViewMode] = useState<'list' | 'grouped'>('list');

  // 문자 보내기 모달
  const [showSmsModal, setShowSmsModal] = useState(false);
  const [smsRecipient, setSmsRecipient] = useState('');
  const [smsBody, setSmsBody] = useState('');
  const [sendingSMS, setSendingSMS] = useState(false);

  // 로딩 상태
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // 검색
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchMode, setIsSearchMode] = useState(false);  // 서버 검색 모드 (문자 탭)
  const [searchLoading, setSearchLoading] = useState(false);

  // 검색 결과 페이지네이션
  const [searchPage, setSearchPage] = useState(0);
  const [searchTotalCount, setSearchTotalCount] = useState(0);
  const [searchHasMore, setSearchHasMore] = useState(false);

  // 페이지네이션
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

  const PAGE_SIZE = 100;

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

  // 초기 로드
  useEffect(() => {
    checkConnection();
    // 안드로이드 전용 에이전트 시작
    startAndroidAgent();

    // 창 닫힐 때 에이전트 종료
    return () => {
      stopAndroidAgent();
    };
  }, []);

  // 안드로이드 전용 에이전트 시작
  const startAndroidAgent = async () => {
    try {
      console.log('[AndroidManager] 에이전트 시작 요청...');
      const res = await fetch(`${getApiUrl()}/android/agent/start`, {
        method: 'POST'
      });
      console.log('[AndroidManager] 응답 상태:', res.status);
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

  // 안드로이드 전용 에이전트 종료
  const stopAndroidAgent = async () => {
    if (!androidAgentId) return;
    try {
      await fetch(`${getApiUrl()}/android/agent/stop`, {
        method: 'POST'
      });
      console.log('[AndroidManager] 에이전트 종료');
    } catch (e) {
      console.error('[AndroidManager] 에이전트 종료 실패:', e);
    }
  };

  // WebSocket 연결 (안드로이드 전용 에이전트와)
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
        console.log('[AndroidManager] WS 메시지:', data);

        if (data.type === 'chunk') {
          // 스트리밍 청크
          streamingMessageRef.current += data.content;
          setMessages(prev => {
            const updated = [...prev];
            if (updated.length > 0 && updated[updated.length - 1].role === 'assistant') {
              updated[updated.length - 1].content = streamingMessageRef.current;
            }
            return updated;
          });
        } else if (data.type === 'done') {
          // 스트리밍 완료
          setIsStreaming(false);
          streamingMessageRef.current = '';
          // 데이터 새로고침
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

    return () => {
      ws.close();
    };
  }, [androidAgentId]);

  // 스크롤
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 기기 연결 확인
  const checkConnection = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`${getApiUrl()}/android/devices`);
      const data = await res.json();

      console.log('[AndroidManager] devices response:', data);

      if (data.success && data.devices?.length > 0) {
        setIsConnected(true);
        setDeviceInfo(data.devices[0]);
        loadAllData();
      } else if (data.detail) {
        // API 에러
        setIsConnected(false);
        setErrorMessage(data.detail);
      } else if (data.message) {
        // 기기 없음 메시지
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

  // 모든 데이터 로드
  const loadAllData = async () => {
    setRefreshing(true);
    await Promise.all([loadCallLog(), loadSMS(), loadContacts(), loadApps()]);
    setRefreshing(false);
  };

  // 통화 기록 로드 (페이지네이션 지원)
  const loadCallLog = async (page: number = 0) => {
    try {
      const offset = page * PAGE_SIZE;
      const res = await fetch(`${getApiUrl()}/android/calls?limit=${PAGE_SIZE}&offset=${offset}`);
      const data = await res.json();
      console.log('[AndroidManager] calls response:', data);
      if (data.success) {
        setCallLog(data.calls || []);
        setCallTotalCount(data.total || data.count || 0);
        setCallHasMore(data.has_more || false);
        setCallPage(page);
      } else {
        console.error('통화 기록 로드 실패:', data.message || data.detail);
      }
    } catch (e) {
      console.error('통화 기록 로드 실패:', e);
    }
  };

  // SMS + MMS 통합 로드 (페이지네이션 지원)
  const loadSMS = async (page: number = 0) => {
    try {
      const offset = page * PAGE_SIZE;
      // SMS + MMS 통합 조회 (삼성 채팅+ 메시지 포함)
      const res = await fetch(`${getApiUrl()}/android/messages?box=all&limit=${PAGE_SIZE}&offset=${offset}`);
      const data = await res.json();
      console.log('[AndroidManager] messages (SMS+MMS) response:', data);
      if (data.success) {
        setSmsList(data.messages || []);
        setSmsTotalCount(data.total || data.count || 0);
        setSmsHasMore(data.has_more || false);
        setSmsPage(page);
      } else {
        console.error('메시지 로드 실패:', data.message || data.detail);
      }
    } catch (e) {
      console.error('메시지 로드 실패:', e);
    }
  };

  // 연락처 로드 (페이지네이션 지원)
  const loadContacts = async (page: number = 0) => {
    try {
      const offset = page * PAGE_SIZE;
      const res = await fetch(`${getApiUrl()}/android/contacts?limit=${PAGE_SIZE}&offset=${offset}`);
      const data = await res.json();
      console.log('[AndroidManager] contacts response:', data);
      if (data.success) {
        setContacts(data.contacts || []);
        setContactTotalCount(data.total || data.count || 0);
        setContactHasMore(data.has_more || false);
        setContactPage(page);
      } else {
        console.error('연락처 로드 실패:', data.message || data.detail);
      }
    } catch (e) {
      console.error('연락처 로드 실패:', e);
    }
  };

  // 앱 목록 로드 (페이지네이션 지원)
  const loadApps = async (page: number = 0) => {
    try {
      const offset = page * PAGE_SIZE;
      const res = await fetch(`${getApiUrl()}/android/apps?limit=${PAGE_SIZE}&offset=${offset}`);
      const data = await res.json();
      console.log('[AndroidManager] apps response:', data);
      if (data.success) {
        setApps(data.apps || []);
        setAppTotalCount(data.total || data.count || 0);
        setAppHasMore(data.has_more || false);
        setAppPage(page);
      } else {
        console.error('앱 목록 로드 실패:', data.message || data.detail);
      }
    } catch (e) {
      console.error('앱 목록 로드 실패:', e);
    }
  };

  // 앱 삭제
  const uninstallApp = async (packageName: string) => {
    if (!confirm(`${packageName} 앱을 삭제하시겠습니까?\n삭제 후 복구할 수 없습니다.`)) return;

    setDeletingApp(packageName);
    try {
      const res = await fetch(`${getApiUrl()}/android/apps/${packageName}`, {
        method: 'DELETE'
      });
      const data = await res.json();
      if (data.success) {
        setApps(prev => prev.filter(a => a.package !== packageName));
        setSelectedApps(prev => {
          const next = new Set(prev);
          next.delete(packageName);
          return next;
        });
        addAssistantMessage(`${packageName} 앱이 삭제되었습니다.`);
      } else {
        addAssistantMessage(`삭제 실패: ${data.message}`);
      }
    } catch (e) {
      console.error('앱 삭제 실패:', e);
      addAssistantMessage('앱 삭제 중 오류가 발생했습니다.');
    }
    setDeletingApp(null);
  };

  // 선택된 앱 삭제
  const uninstallSelectedApps = async () => {
    if (selectedApps.size === 0) return;
    if (!confirm(`선택된 ${selectedApps.size}개의 앱을 삭제하시겠습니까?\n삭제 후 복구할 수 없습니다.`)) return;

    for (const pkg of selectedApps) {
      setDeletingApp(pkg);
      try {
        const res = await fetch(`${getApiUrl()}/android/apps/${pkg}`, {
          method: 'DELETE'
        });
        const data = await res.json();
        if (data.success) {
          setApps(prev => prev.filter(a => a.package !== pkg));
        }
      } catch (e) {
        console.error(`앱 삭제 실패 (${pkg}):`, e);
      }
    }
    setSelectedApps(new Set());
    setDeletingApp(null);
    addAssistantMessage(`${selectedApps.size}개의 앱이 삭제되었습니다.`);
  };

  // 앱 선택 토글
  const toggleAppSelection = (packageName: string) => {
    setSelectedApps(prev => {
      const next = new Set(prev);
      if (next.has(packageName)) {
        next.delete(packageName);
      } else {
        next.add(packageName);
      }
      return next;
    });
  };

  // 전화 걸기
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

  // 문자 보내기 모달 열기
  const openSmsModal = (phoneNumber?: string) => {
    setSmsRecipient(phoneNumber || '');
    setSmsBody('');
    setShowSmsModal(true);
  };

  // 문자 보내기
  const sendSMS = async () => {
    if (!smsRecipient.trim() || !smsBody.trim()) {
      addAssistantMessage('받는 사람과 내용을 입력해주세요.');
      return;
    }

    setSendingSMS(true);
    try {
      const res = await fetch(`${getApiUrl()}/android/sms/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phone_number: smsRecipient.trim(),
          message: smsBody.trim()
        })
      });
      const data = await res.json();
      if (data.success) {
        addAssistantMessage(`${smsRecipient}에게 문자를 보냈습니다. ${data.note || ''}`);
        setShowSmsModal(false);
        setSmsRecipient('');
        setSmsBody('');
        // 문자 목록 새로고침
        loadSMS();
      } else {
        addAssistantMessage(`문자 전송 실패: ${data.message || '알 수 없는 오류'}`);
      }
    } catch (e) {
      console.error('문자 보내기 실패:', e);
      addAssistantMessage('문자 전송 중 오류가 발생했습니다.');
    }
    setSendingSMS(false);
  };

  // SMS/MMS 삭제 (단일)
  const deleteSMS = async (smsId: string) => {
    if (!confirm('이 문자를 삭제하시겠습니까?')) return;

    try {
      // 메시지 타입 확인
      const msg = smsList.find(s => s._id === smsId);
      const isMMS = msg?.message_type === 'mms';

      // SMS/MMS 통합 삭제 API 사용
      const res = await fetch(`${getApiUrl()}/android/messages/bulk-delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sms_ids: isMMS ? null : [smsId],
          mms_ids: isMMS ? [smsId] : null
        })
      });
      const data = await res.json();
      if (data.success) {
        // 삭제 후 다시 100개 채우기
        if (isSearchMode && searchQuery) {
          searchSMSFromServer(searchQuery);
        } else {
          loadSMS();
        }
      }
    } catch (e) {
      console.error('SMS/MMS 삭제 실패:', e);
    }
  };

  // SMS 선택 토글
  const toggleSMSSelection = (smsId: string) => {
    setSelectedSMS(prev => {
      const next = new Set(prev);
      if (next.has(smsId)) {
        next.delete(smsId);
      } else {
        next.add(smsId);
      }
      return next;
    });
  };

  // 발신자의 모든 SMS 선택
  const selectAllFromAddress = (address: string) => {
    const ids = smsList.filter(s => s.address === address).map(s => s._id);
    setSelectedSMS(prev => {
      const next = new Set(prev);
      ids.forEach(id => next.add(id));
      return next;
    });
  };

  // 선택된 SMS/MMS 일괄 삭제 (SMS와 MMS를 분류하여 처리)
  const deleteSelectedSMS = async () => {
    if (selectedSMS.size === 0) return;
    if (!confirm(`선택된 ${selectedSMS.size}개의 문자를 삭제하시겠습니까?\n삭제 후 복구할 수 없습니다.`)) return;

    setDeletingSMS(true);

    try {
      // 선택된 ID들을 SMS와 MMS로 분류
      const smsIds: string[] = [];
      const mmsIds: string[] = [];

      selectedSMS.forEach(id => {
        const msg = smsList.find(s => s._id === id);
        if (msg?.message_type === 'mms') {
          mmsIds.push(id);
        } else {
          smsIds.push(id);
        }
      });

      // SMS/MMS 통합 삭제 API 호출
      const res = await fetch(`${getApiUrl()}/android/messages/bulk-delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sms_ids: smsIds.length > 0 ? smsIds : null,
          mms_ids: mmsIds.length > 0 ? mmsIds : null
        })
      });
      const data = await res.json();

      if (data.success) {
        addAssistantMessage(`${data.deleted_count || selectedSMS.size}개의 문자가 삭제되었습니다. (SMS ${data.deleted_sms || 0}개, MMS ${data.deleted_mms || 0}개)`);
      } else {
        addAssistantMessage(`삭제 실패: ${data.message}`);
      }
    } catch (e) {
      console.error('SMS/MMS 일괄 삭제 실패:', e);
      addAssistantMessage('삭제 중 오류가 발생했습니다.');
    }

    setSelectedSMS(new Set());
    setDeletingSMS(false);

    // 삭제 후 다시 100개 채우기
    if (isSearchMode && searchQuery) {
      searchSMSFromServer(searchQuery);
    } else {
      loadSMS();
    }
  };

  // 발신자별 일괄 삭제 (조건부)
  const deleteSMSByAddress = async (address: string) => {
    const count = smsList.filter(s => s.address === address).length;
    if (!confirm(`'${address}'의 모든 문자 ${count}개를 삭제하시겠습니까?\n삭제 후 복구할 수 없습니다.`)) return;

    setDeletingSMS(true);
    try {
      const res = await fetch(`${getApiUrl()}/android/sms/bulk-delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address })
      });
      const data = await res.json();
      if (data.success) {
        setSelectedSMS(new Set());
        addAssistantMessage(`'${address}'의 문자 ${data.deleted_count || count}개가 삭제되었습니다.`);

        // 삭제 후 다시 100개 채우기
        if (isSearchMode && searchQuery) {
          searchSMSFromServer(searchQuery);
        } else {
          loadSMS();
        }
      } else {
        addAssistantMessage(`삭제 실패: ${data.message}`);
      }
    } catch (e) {
      console.error('일괄 삭제 실패:', e);
      addAssistantMessage('일괄 삭제 중 오류가 발생했습니다.');
    }
    setDeletingSMS(false);
  };

  // 서버 측 SMS 검색 (전체 대상, 페이지네이션 지원)
  const searchSMSFromServer = async (query: string, page: number = 0) => {
    if (!query.trim()) {
      // 검색어 없으면 일반 모드로
      setIsSearchMode(false);
      setSearchPage(0);
      setSearchTotalCount(0);
      setSearchHasMore(false);
      loadSMS();
      return;
    }

    setSearchLoading(true);
    try {
      const offset = page * PAGE_SIZE;
      const res = await fetch(`${getApiUrl()}/android/sms/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), limit: PAGE_SIZE, offset })
      });
      const data = await res.json();
      if (data.success) {
        setSmsList(data.messages || []);
        setIsSearchMode(true);
        setSearchPage(page);
        setSearchTotalCount(data.total || 0);
        setSearchHasMore(data.has_more || false);
        setSelectedSMS(new Set());
        if (page === 0) {
          const total = data.total || 0;
          addAssistantMessage(`'${query}' 검색 결과: ${total}개`);
        }
      }
    } catch (e) {
      console.error('SMS 검색 실패:', e);
    }
    setSearchLoading(false);
  };

  // 검색 엔터 처리 (문자 탭에서)
  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && activeTab === 'messages') {
      e.preventDefault();
      searchSMSFromServer(searchQuery);
    }
  };

  // 검색 초기화 (문자 탭)
  const clearSearch = () => {
    setSearchQuery('');
    setIsSearchMode(false);
    setSearchPage(0);
    setSearchTotalCount(0);
    setSearchHasMore(false);
    loadSMS();
  };

  // 통화 기록 삭제
  const deleteCallLog = async (callId: string) => {
    if (!confirm('이 통화 기록을 삭제하시겠습니까?')) return;

    try {
      const res = await fetch(`${getApiUrl()}/android/calls/${callId}`, {
        method: 'DELETE'
      });
      const data = await res.json();
      if (data.success) {
        setCallLog(prev => prev.filter(c => c._id !== callId));
      }
    } catch (e) {
      console.error('통화 기록 삭제 실패:', e);
    }
  };

  // 연락처 삭제
  const deleteContact = async (contactId: string, contactName: string) => {
    if (!confirm(`'${contactName}' 연락처를 삭제하시겠습니까?`)) return;

    try {
      const res = await fetch(`${getApiUrl()}/android/contacts/${contactId}`, {
        method: 'DELETE'
      });
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

    // 안드로이드 전용 에이전트가 있으면 WebSocket으로 전송
    if (wsConnected && wsRef.current) {
      // 빈 assistant 메시지 추가 (스트리밍용)
      setMessages(prev => [...prev, { role: 'assistant', content: '' }]);
      streamingMessageRef.current = '';

      wsRef.current.send(JSON.stringify({
        type: 'chat',
        message: userMessage
      }));
    } else {
      // 에이전트가 없으면 기존 방식 (간단한 패턴 매칭)
      try {
        const res = await fetch(`${getApiUrl()}/android/ai-command`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command: userMessage })
        });

        const data = await res.json();

        if (data.success) {
          addAssistantMessage(data.response || data.message);
          if (data.refresh) {
            loadAllData();
          }
        } else {
          addAssistantMessage(data.error || '명령을 처리할 수 없습니다.');
        }
      } catch (e) {
        addAssistantMessage('오류가 발생했습니다. 다시 시도해주세요.');
      }
      setIsStreaming(false);
    }
  };

  // 전화번호 → 연락처 이름 매핑 (SMS에서 이름 표시용)
  const contactMap = useMemo(() => {
    const map: Record<string, string> = {};
    contacts.forEach(c => {
      if (c.phone && c.name) {
        // 전화번호 정규화 (하이픈, 공백 제거)
        const normalizedPhone = c.phone.replace(/[-\s]/g, '');
        map[normalizedPhone] = c.name;
        // 원본 번호도 추가
        map[c.phone] = c.name;
      }
    });
    return map;
  }, [contacts]);

  // 전화번호로 연락처 이름 찾기 (없으면 번호 반환)
  const getContactName = (phone: string): string => {
    if (!phone) return phone;
    // 정규화된 번호로 검색
    const normalized = phone.replace(/[-\s]/g, '');
    return contactMap[normalized] || contactMap[phone] || phone;
  };

  // 검색 필터링
  const filteredCallLog = callLog.filter(c =>
    c.number?.includes(searchQuery) || c.name?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // 검색 모드면 smsList 전체 사용 (이미 서버에서 필터링됨), 아니면 클라이언트 필터링
  const filteredSMS = isSearchMode
    ? smsList
    : smsList.filter(s =>
        s.address?.includes(searchQuery) || s.body?.toLowerCase().includes(searchQuery.toLowerCase())
      );

  // SMS를 발신자별로 그룹핑
  const groupedSMS = filteredSMS.reduce((groups, sms) => {
    const key = sms.address;
    if (!groups[key]) {
      groups[key] = [];
    }
    groups[key].push(sms);
    return groups;
  }, {} as Record<string, SMSItem[]>);

  const filteredContacts = contacts.filter(c =>
    c.name?.toLowerCase().includes(searchQuery.toLowerCase()) || c.phone?.includes(searchQuery)
  );

  const filteredApps = apps.filter(a =>
    a.package?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    a.name?.toLowerCase().includes(searchQuery.toLowerCase())
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

  // 로딩 화면
  if (loading) {
    return (
      <div className="h-full flex flex-col bg-gray-900 text-white">
        {/* 드래그 영역 (macOS) */}
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

  // 연결 안됨 화면
  if (!isConnected) {
    return (
      <div className="h-full flex flex-col bg-gray-900 text-white">
        {/* 드래그 영역 (macOS) */}
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
        <button
          onClick={() => { setActiveTab('recent'); setSearchQuery(''); setIsSearchMode(false); setCallPage(0); }}
          className={`flex-1 py-3 flex items-center justify-center gap-2 ${
            activeTab === 'recent' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400'
          }`}
        >
          <Clock className="w-4 h-4" />
          최근기록
        </button>
        <button
          onClick={() => { setActiveTab('contacts'); setSearchQuery(''); setIsSearchMode(false); setContactPage(0); }}
          className={`flex-1 py-3 flex items-center justify-center gap-2 ${
            activeTab === 'contacts' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400'
          }`}
        >
          <Users className="w-4 h-4" />
          연락처
        </button>
        <button
          onClick={() => { setActiveTab('messages'); setSearchQuery(''); setIsSearchMode(false); setSmsPage(0); }}
          className={`flex-1 py-3 flex items-center justify-center gap-2 ${
            activeTab === 'messages' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400'
          }`}
        >
          <MessageSquare className="w-4 h-4" />
          문자
        </button>
        <button
          onClick={() => { setActiveTab('apps'); setSearchQuery(''); setIsSearchMode(false); setAppPage(0); }}
          className={`flex-1 py-3 flex items-center justify-center gap-2 ${
            activeTab === 'apps' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400'
          }`}
        >
          <Package className="w-4 h-4" />
          앱정리
        </button>
      </div>

      {/* 검색 */}
      <div className="px-4 py-2">
        <div className="relative">
          {searchLoading ? (
            <Loader2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-blue-500 animate-spin" />
          ) : (
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          )}
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder={activeTab === 'messages' ? "검색 후 Enter (전체 문자 대상)" : "검색..."}
            className="w-full pl-10 pr-10 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
          />
          {/* 검색 모드 표시 및 초기화 버튼 (문자 탭) */}
          {activeTab === 'messages' && isSearchMode && (
            <button
              onClick={clearSearch}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-1 hover:bg-gray-700 rounded"
              title="검색 초기화"
            >
              <X className="w-4 h-4 text-gray-400" />
            </button>
          )}
        </div>
        {/* 검색 모드 안내 */}
        {activeTab === 'messages' && isSearchMode && (
          <div className="mt-1 text-xs text-blue-400">
            🔍 전체 검색 모드 - '{searchQuery}' 검색 결과 표시 중
          </div>
        )}
      </div>

      {/* 컨텐츠 영역 */}
      <div className="flex-1 overflow-y-auto">
        {/* 최근 기록 탭 */}
        {activeTab === 'recent' && (
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
                    {/* 클릭하면 전화 걸기 */}
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
                    ← 이전
                  </button>
                  <span className="text-sm text-gray-300">
                    {callPage + 1} / {Math.ceil(callTotalCount / PAGE_SIZE)}
                  </span>
                  <button
                    onClick={() => loadCallLog(callPage + 1)}
                    disabled={!callHasMore}
                    className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    다음 →
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 연락처 탭 */}
        {activeTab === 'contacts' && (
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
                    {/* 클릭하면 전화 걸기 */}
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
                        onClick={() => openSmsModal(contact.phone)}
                        className="p-2 hover:bg-gray-700 rounded-full text-yellow-500"
                        title="문자 보내기"
                      >
                        <Edit3 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => {
                          setActiveTab('messages');
                          setSearchQuery(contact.phone);
                          // 서버 검색 실행
                          searchSMSFromServer(contact.phone);
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
                    ← 이전
                  </button>
                  <span className="text-sm text-gray-300">
                    {contactPage + 1} / {Math.ceil(contactTotalCount / PAGE_SIZE)}
                  </span>
                  <button
                    onClick={() => loadContacts(contactPage + 1)}
                    disabled={!contactHasMore}
                    className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    다음 →
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 문자 탭 */}
        {activeTab === 'messages' && (
          <div>
            {/* 뷰 모드 토글 & 선택 삭제 */}
            <div className="sticky top-0 bg-gray-800 px-4 py-2 border-b border-gray-700 flex items-center justify-between z-10">
              <div className="flex items-center gap-2">
                {/* 새 문자 버튼 */}
                <button
                  onClick={() => openSmsModal()}
                  className="flex items-center gap-1 px-3 py-1 bg-green-600 rounded text-xs hover:bg-green-700"
                >
                  <Plus className="w-3 h-3" />
                  새 문자
                </button>
                <button
                  onClick={() => setSmsViewMode('list')}
                  className={`px-3 py-1 rounded text-xs ${smsViewMode === 'list' ? 'bg-blue-600' : 'bg-gray-700'}`}
                >
                  목록
                </button>
                <button
                  onClick={() => setSmsViewMode('grouped')}
                  className={`px-3 py-1 rounded text-xs ${smsViewMode === 'grouped' ? 'bg-blue-600' : 'bg-gray-700'}`}
                >
                  발신자별
                </button>
              </div>
              <div className="flex items-center gap-2">
                {/* 전체 선택/해제 버튼 */}
                {filteredSMS.length > 0 && (
                  <button
                    onClick={() => {
                      const filteredIds = filteredSMS.map(s => s._id);
                      const allSelected = filteredIds.every(id => selectedSMS.has(id));
                      if (allSelected) {
                        // 전체 해제
                        setSelectedSMS(prev => {
                          const next = new Set(prev);
                          filteredIds.forEach(id => next.delete(id));
                          return next;
                        });
                      } else {
                        // 전체 선택
                        setSelectedSMS(prev => new Set([...prev, ...filteredIds]));
                      }
                    }}
                    className="flex items-center gap-1 px-3 py-1 bg-gray-700 rounded-lg text-xs hover:bg-gray-600"
                  >
                    {filteredSMS.length > 0 && filteredSMS.every(s => selectedSMS.has(s._id)) ? (
                      <>
                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                        선택 해제
                      </>
                    ) : (
                      <>
                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        전체 선택 ({filteredSMS.length})
                      </>
                    )}
                  </button>
                )}
                {selectedSMS.size > 0 && (
                  <button
                    onClick={deleteSelectedSMS}
                    disabled={deletingSMS}
                    className="flex items-center gap-2 px-3 py-1 bg-red-600 rounded-lg text-xs hover:bg-red-700 disabled:opacity-50"
                  >
                    {deletingSMS ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                    {selectedSMS.size}개 삭제
                  </button>
                )}
              </div>
            </div>

            {filteredSMS.length === 0 ? (
              <div className="p-8 text-center">
                <p className="text-gray-500 mb-2">문자가 없습니다</p>
                <p className="text-xs text-gray-600">Android 보안 정책으로 SMS 접근이 제한됩니다.<br/>알림에서 최근 메시지를 가져올 수 있습니다.</p>
              </div>
            ) : smsViewMode === 'list' ? (
              /* 목록 뷰 */
              <div className="divide-y divide-gray-800">
                {filteredSMS.map(sms => (
                  <div key={sms._id} className={`px-4 py-3 hover:bg-gray-800 ${selectedSMS.has(sms._id) ? 'bg-gray-800/50' : ''}`}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        {/* 체크박스 */}
                        <button
                          onClick={() => toggleSMSSelection(sms._id)}
                          className={`w-4 h-4 rounded border flex items-center justify-center ${
                            selectedSMS.has(sms._id) ? 'bg-blue-500 border-blue-500' : 'border-gray-600'
                          }`}
                        >
                          {selectedSMS.has(sms._id) && (
                            <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                            </svg>
                          )}
                        </button>
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          sms.direction === 'received' ? 'bg-green-900 text-green-300' : 'bg-blue-900 text-blue-300'
                        }`}>
                          {sms.direction === 'received' ? '수신' : '발신'}
                        </span>
                        <span className="font-medium text-sm">{getContactName(sms.address)}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-500">{sms.date_formatted}</span>
                        <button
                          onClick={() => openSmsModal(sms.address)}
                          className="p-1 hover:bg-gray-700 rounded text-yellow-500"
                          title="답장"
                        >
                          <Edit3 className="w-3 h-3" />
                        </button>
                        <button
                          onClick={() => deleteSMS(sms._id)}
                          className="p-1 hover:bg-gray-700 rounded text-red-500"
                          title="삭제"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                    <div className="text-sm text-gray-300 line-clamp-2 ml-6">{sms.body}</div>
                  </div>
                ))}
              </div>
            ) : (
              /* 발신자별 그룹 뷰 */
              <div className="divide-y divide-gray-700">
                {Object.entries(groupedSMS).map(([address, messages]) => (
                  <div key={address} className="bg-gray-850">
                    {/* 발신자 헤더 */}
                    <div className="flex items-center justify-between px-4 py-3 bg-gray-800 sticky top-10 z-5">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-gray-700 rounded-full flex items-center justify-center">
                          <MessageSquare className="w-4 h-4 text-gray-400" />
                        </div>
                        <div>
                          <div className="font-medium text-sm">{getContactName(address)}</div>
                          <div className="text-xs text-gray-500">{address !== getContactName(address) ? `${address} • ` : ''}{messages.length}개의 메시지</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => openSmsModal(address)}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-green-600/80 rounded hover:bg-green-600"
                        >
                          <Edit3 className="w-3 h-3" />
                          답장
                        </button>
                        <button
                          onClick={() => selectAllFromAddress(address)}
                          className="px-2 py-1 text-xs bg-gray-700 rounded hover:bg-gray-600"
                        >
                          전체 선택
                        </button>
                        <button
                          onClick={() => deleteSMSByAddress(address)}
                          disabled={deletingSMS}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-red-600/80 rounded hover:bg-red-600 disabled:opacity-50"
                        >
                          {deletingSMS ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                          전체 삭제
                        </button>
                      </div>
                    </div>
                    {/* 메시지 목록 */}
                    <div className="divide-y divide-gray-800">
                      {messages.slice(0, 5).map(sms => (
                        <div key={sms._id} className={`px-4 py-2 hover:bg-gray-800/50 ${selectedSMS.has(sms._id) ? 'bg-gray-800/30' : ''}`}>
                          <div className="flex items-start gap-2">
                            <button
                              onClick={() => toggleSMSSelection(sms._id)}
                              className={`w-4 h-4 rounded border flex items-center justify-center mt-0.5 ${
                                selectedSMS.has(sms._id) ? 'bg-blue-500 border-blue-500' : 'border-gray-600'
                              }`}
                            >
                              {selectedSMS.has(sms._id) && (
                                <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                                </svg>
                              )}
                            </button>
                            <div className="flex-1 min-w-0">
                              <div className="text-xs text-gray-500 mb-1">{sms.date_formatted}</div>
                              <div className="text-sm text-gray-300 line-clamp-2">{sms.body}</div>
                            </div>
                            <button
                              onClick={() => deleteSMS(sms._id)}
                              className="p-1 hover:bg-gray-700 rounded text-red-500"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          </div>
                        </div>
                      ))}
                      {messages.length > 5 && (
                        <div className="px-4 py-2 text-center text-xs text-gray-500">
                          +{messages.length - 5}개 더 있음
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* 페이지네이션 - 검색 모드 */}
            {isSearchMode && searchTotalCount > PAGE_SIZE && (
              <div className="sticky bottom-0 bg-gray-800 border-t border-gray-700 px-4 py-3 flex items-center justify-between">
                <div className="text-xs text-gray-400">
                  🔍 '{searchQuery}' 검색 결과: 전체 {searchTotalCount}개 중 {searchPage * PAGE_SIZE + 1}~{Math.min((searchPage + 1) * PAGE_SIZE, searchTotalCount)}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => searchSMSFromServer(searchQuery, searchPage - 1)}
                    disabled={searchPage === 0 || searchLoading}
                    className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    ← 이전
                  </button>
                  <span className="text-sm text-gray-300">
                    {searchPage + 1} / {Math.ceil(searchTotalCount / PAGE_SIZE)}
                  </span>
                  <button
                    onClick={() => searchSMSFromServer(searchQuery, searchPage + 1)}
                    disabled={!searchHasMore || searchLoading}
                    className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    다음 →
                  </button>
                </div>
              </div>
            )}

            {/* 페이지네이션 - 일반 모드 */}
            {!isSearchMode && smsTotalCount > PAGE_SIZE && (
              <div className="sticky bottom-0 bg-gray-800 border-t border-gray-700 px-4 py-3 flex items-center justify-between">
                <div className="text-xs text-gray-400">
                  전체 {smsTotalCount}개 중 {smsPage * PAGE_SIZE + 1}~{Math.min((smsPage + 1) * PAGE_SIZE, smsTotalCount)}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => loadSMS(smsPage - 1)}
                    disabled={smsPage === 0}
                    className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    ← 이전
                  </button>
                  <span className="text-sm text-gray-300">
                    {smsPage + 1} / {Math.ceil(smsTotalCount / PAGE_SIZE)}
                  </span>
                  <button
                    onClick={() => loadSMS(smsPage + 1)}
                    disabled={!smsHasMore}
                    className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    다음 →
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 앱 정리 탭 */}
        {activeTab === 'apps' && (
          <div className="flex flex-col h-full">
            {/* 선택 삭제 버튼 */}
            {selectedApps.size > 0 && (
              <div className="sticky top-0 bg-gray-800 px-4 py-2 border-b border-gray-700 flex items-center justify-between z-10">
                <span className="text-sm text-gray-300">{selectedApps.size}개 선택됨</span>
                <button
                  onClick={uninstallSelectedApps}
                  disabled={!!deletingApp}
                  className="flex items-center gap-2 px-3 py-1 bg-red-600 rounded-lg text-sm hover:bg-red-700 disabled:opacity-50"
                >
                  <Trash2 className="w-4 h-4" />
                  선택 삭제
                </button>
              </div>
            )}

            <div className="flex-1 divide-y divide-gray-800 overflow-y-auto">
              {filteredApps.length === 0 ? (
                <div className="p-8 text-center">
                  <p className="text-gray-500 mb-2">앱 목록을 불러오는 중...</p>
                  <p className="text-xs text-gray-600">잠시만 기다려주세요.</p>
                </div>
              ) : (
                filteredApps.map(app => (
                  <div
                    key={app.package}
                    className={`flex items-center px-4 py-3 hover:bg-gray-800 ${
                      selectedApps.has(app.package) ? 'bg-gray-800/50' : ''
                    }`}
                  >
                    {/* 체크박스 */}
                    <button
                      onClick={() => toggleAppSelection(app.package)}
                      className={`w-5 h-5 rounded border mr-3 flex items-center justify-center ${
                        selectedApps.has(app.package)
                          ? 'bg-blue-500 border-blue-500'
                          : 'border-gray-600'
                      }`}
                    >
                      {selectedApps.has(app.package) && (
                        <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </button>

                    {/* 앱 아이콘 */}
                    <div className="w-10 h-10 bg-gray-700 rounded-lg flex items-center justify-center mr-3">
                      <Package className="w-5 h-5 text-gray-400" />
                    </div>

                    {/* 앱 정보 */}
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate text-sm">{app.name || app.package.split('.').pop()}</div>
                      <div className="text-xs text-gray-500 truncate">{app.package}</div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                        {app.size && (
                          <span className="flex items-center gap-1">
                            <HardDrive className="w-3 h-3" />
                            {app.size}
                          </span>
                        )}
                        {app.total_time_formatted && (
                          <span className="flex items-center gap-1">
                            <Clock3 className="w-3 h-3" />
                            {app.total_time_formatted}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* 삭제 버튼 */}
                    <button
                      onClick={() => uninstallApp(app.package)}
                      disabled={deletingApp === app.package}
                      className="p-2 hover:bg-gray-700 rounded-full text-red-500 disabled:opacity-50"
                    >
                      {deletingApp === app.package ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                ))
              )}
            </div>

            {/* 페이지네이션 */}
            {appTotalCount > PAGE_SIZE && (
              <div className="sticky bottom-0 bg-gray-800 border-t border-gray-700 px-4 py-3 flex items-center justify-between">
                <div className="text-xs text-gray-400">
                  전체 {appTotalCount}개 중 {appPage * PAGE_SIZE + 1}~{Math.min((appPage + 1) * PAGE_SIZE, appTotalCount)}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => loadApps(appPage - 1)}
                    disabled={appPage === 0}
                    className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    ← 이전
                  </button>
                  <span className="text-sm text-gray-300">
                    {appPage + 1} / {Math.ceil(appTotalCount / PAGE_SIZE)}
                  </span>
                  <button
                    onClick={() => loadApps(appPage + 1)}
                    disabled={!appHasMore}
                    className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    다음 →
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 문자 보내기 모달 */}
      {showSmsModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg w-80 max-w-[90%] p-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-medium flex items-center gap-2">
                <Edit3 className="w-4 h-4" />
                새 문자
              </h3>
              <button
                onClick={() => setShowSmsModal(false)}
                className="p-1 hover:bg-gray-700 rounded"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs text-gray-400 mb-1">받는 사람</label>
                <input
                  type="tel"
                  value={smsRecipient}
                  onChange={e => setSmsRecipient(e.target.value)}
                  placeholder="010-1234-5678"
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1">내용</label>
                <textarea
                  value={smsBody}
                  onChange={e => setSmsBody(e.target.value)}
                  placeholder="문자 내용을 입력하세요..."
                  rows={4}
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm focus:outline-none focus:border-blue-500 resize-none"
                />
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => setShowSmsModal(false)}
                  className="flex-1 py-2 bg-gray-700 rounded text-sm hover:bg-gray-600"
                >
                  취소
                </button>
                <button
                  onClick={sendSMS}
                  disabled={sendingSMS || !smsRecipient.trim() || !smsBody.trim()}
                  className="flex-1 py-2 bg-green-600 rounded text-sm hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {sendingSMS ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                  보내기
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* AI 대화창 */}
      <div className="border-t border-gray-700 bg-gray-850">
        {/* 대화 내역 (최근 3개만) */}
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

        {/* 입력창 */}
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
