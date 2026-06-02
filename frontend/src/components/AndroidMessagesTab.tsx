/**
 * AndroidMessagesTab.tsx
 * 안드로이드 문자(SMS/MMS) 탭 - 목록/발신자별 뷰, 검색, 선택 삭제, 문자 보내기
 */

import { useState, useMemo } from 'react';
import {
  MessageSquare, Trash2, Search, Loader2,
  X, Edit3, Plus, Send
} from 'lucide-react';

// ─── 타입 ─────────────────────────────
export interface SMSItem {
  _id: string;
  address: string;
  body: string;
  date_formatted: string;
  direction: 'received' | 'sent';
  read?: string;
  message_type?: 'sms' | 'mms';
}

export interface ContactItem {
  id: string;
  name: string;
  phone: string;
}

interface AndroidMessagesTabProps {
  getApiUrl: () => string;
  smsList: SMSItem[];
  contacts: ContactItem[];
  addAssistantMessage: (content: string) => void;
  loadSMS: (page?: number) => Promise<void>;
  // 페이지네이션
  smsPage: number;
  smsTotalCount: number;
  smsHasMore: boolean;
  PAGE_SIZE: number;
}

// ─── 컴포넌트 ─────────────────────────
export function AndroidMessagesTab({
  getApiUrl,
  smsList: externalSmsList,
  contacts,
  addAssistantMessage,
  loadSMS,
  smsPage,
  smsTotalCount,
  smsHasMore,
  PAGE_SIZE,
}: AndroidMessagesTabProps) {
  // 검색
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchMode, setIsSearchMode] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchPage, setSearchPage] = useState(0);
  const [searchTotalCount, setSearchTotalCount] = useState(0);
  const [searchHasMore, setSearchHasMore] = useState(false);

  // 로컬 문자 목록 (검색 결과용)
  const [localSmsList, setLocalSmsList] = useState<SMSItem[]>([]);

  // 선택/삭제
  const [selectedSMS, setSelectedSMS] = useState<Set<string>>(new Set());
  const [deletingSMS, setDeletingSMS] = useState(false);

  // 뷰 모드
  const [smsViewMode, setSmsViewMode] = useState<'list' | 'grouped'>('list');

  // 문자 보내기 모달
  const [showSmsModal, setShowSmsModal] = useState(false);
  const [smsRecipient, setSmsRecipient] = useState('');
  const [smsBody, setSmsBody] = useState('');
  const [sendingSMS, setSendingSMS] = useState(false);

  // 실제 표시할 문자 목록: 검색 모드면 로컬, 아니면 외부
  const smsList = isSearchMode ? localSmsList : externalSmsList;

  // 전화번호 → 연락처 이름 매핑
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
  };

  // 필터링
  const filteredSMS = isSearchMode
    ? smsList
    : smsList.filter(s =>
        s.address?.includes(searchQuery) || s.body?.toLowerCase().includes(searchQuery.toLowerCase())
      );

  // 발신자별 그룹핑
  const groupedSMS = filteredSMS.reduce((groups, sms) => {
    const key = sms.address;
    if (!groups[key]) groups[key] = [];
    groups[key].push(sms);
    return groups;
  }, {} as Record<string, SMSItem[]>);

  // ─── 핸들러 ─────────────────────────

  // 서버 측 SMS 검색
  const searchSMSFromServer = async (query: string, page: number = 0) => {
    if (!query.trim()) {
      setIsSearchMode(false);
      setSearchPage(0);
      setSearchTotalCount(0);
      setSearchHasMore(false);
      setLocalSmsList([]);
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
        setLocalSmsList(data.messages || []);
        setIsSearchMode(true);
        setSearchPage(page);
        setSearchTotalCount(data.total || 0);
        setSearchHasMore(data.has_more || false);
        setSelectedSMS(new Set());
        if (page === 0) {
          addAssistantMessage(`'${query}' 검색 결과: ${data.total || 0}개`);
        }
      }
    } catch (e) {
      console.error('SMS 검색 실패:', e);
    }
    setSearchLoading(false);
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      searchSMSFromServer(searchQuery);
    }
  };

  const clearSearch = () => {
    setSearchQuery('');
    setIsSearchMode(false);
    setSearchPage(0);
    setSearchTotalCount(0);
    setSearchHasMore(false);
    setLocalSmsList([]);
    loadSMS();
  };

  // SMS 삭제 (단일)
  const deleteSMS = async (smsId: string) => {
    if (!confirm('이 문자를 삭제하시겠습니까?')) return;

    try {
      const msg = smsList.find(s => s._id === smsId);
      const isMMS = msg?.message_type === 'mms';

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
      if (next.has(smsId)) next.delete(smsId);
      else next.add(smsId);
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

  // 선택된 SMS/MMS 일괄 삭제
  const deleteSelectedSMS = async () => {
    if (selectedSMS.size === 0) return;
    if (!confirm(`선택된 ${selectedSMS.size}개의 문자를 삭제하시겠습니까?\n삭제 후 복구할 수 없습니다.`)) return;

    setDeletingSMS(true);

    try {
      const smsIds: string[] = [];
      const mmsIds: string[] = [];

      selectedSMS.forEach(id => {
        const msg = smsList.find(s => s._id === id);
        if (msg?.message_type === 'mms') mmsIds.push(id);
        else smsIds.push(id);
      });

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

    if (isSearchMode && searchQuery) {
      searchSMSFromServer(searchQuery);
    } else {
      loadSMS();
    }
  };

  // 발신자별 일괄 삭제
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

  // ─── 렌더링 ─────────────────────────
  return (
    <>
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
            placeholder="검색 후 Enter (전체 문자 대상)"
            className="w-full pl-10 pr-10 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
          />
          {isSearchMode && (
            <button
              onClick={clearSearch}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-1 hover:bg-gray-700 rounded"
              title="검색 초기화"
            >
              <X className="w-4 h-4 text-gray-400" />
            </button>
          )}
        </div>
        {isSearchMode && (
          <div className="mt-1 text-xs text-blue-400">
            검색 모드 - '{searchQuery}' 검색 결과 표시 중
          </div>
        )}
      </div>

      {/* 뷰 모드 토글 & 선택 삭제 */}
      <div className="sticky top-0 bg-gray-800 px-4 py-2 border-b border-gray-700 flex items-center justify-between z-10">
        <div className="flex items-center gap-2">
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
          {filteredSMS.length > 0 && (
            <button
              onClick={() => {
                const filteredIds = filteredSMS.map(s => s._id);
                const allSelected = filteredIds.every(id => selectedSMS.has(id));
                if (allSelected) {
                  setSelectedSMS(prev => {
                    const next = new Set(prev);
                    filteredIds.forEach(id => next.delete(id));
                    return next;
                  });
                } else {
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

      {/* 문자 목록 */}
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
            '{searchQuery}' 검색 결과: 전체 {searchTotalCount}개 중 {searchPage * PAGE_SIZE + 1}~{Math.min((searchPage + 1) * PAGE_SIZE, searchTotalCount)}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => searchSMSFromServer(searchQuery, searchPage - 1)}
              disabled={searchPage === 0 || searchLoading}
              className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              이전
            </button>
            <span className="text-sm text-gray-300">
              {searchPage + 1} / {Math.ceil(searchTotalCount / PAGE_SIZE)}
            </span>
            <button
              onClick={() => searchSMSFromServer(searchQuery, searchPage + 1)}
              disabled={!searchHasMore || searchLoading}
              className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              다음
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
              이전
            </button>
            <span className="text-sm text-gray-300">
              {smsPage + 1} / {Math.ceil(smsTotalCount / PAGE_SIZE)}
            </span>
            <button
              onClick={() => loadSMS(smsPage + 1)}
              disabled={!smsHasMore}
              className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              다음
            </button>
          </div>
        </div>
      )}

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
    </>
  );
}
