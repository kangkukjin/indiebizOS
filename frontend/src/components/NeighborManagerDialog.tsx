/**
 * NeighborManagerDialog - 이웃 관리 다이얼로그
 * kvisual-mcp의 비즈니스 관리 기능을 이식
 * 이웃 목록, 대화 내역, 이웃 정보, 레벨별 필터링 지원
 */

import { useEffect, useState, useRef } from 'react';
import {
  Users, X, Search, MessageSquare, User, Phone, Mail, Plus, Trash2, Edit2, Send,
  ChevronLeft, Star, FileText, Share2, ToggleLeft, ToggleRight
} from 'lucide-react';
import { api } from '../lib/api';

// 타입 정의
interface Neighbor {
  id: number;
  name: string;
  info_level: number;
  rating: number;
  additional_info: string | null;
  business_doc: string | null;
  info_share: number;
  created_at: string;
  updated_at: string;
}

interface Contact {
  id: number;
  neighbor_id: number;
  contact_type: string;
  contact_value: string;
  created_at: string;
}

interface Message {
  id: number;
  neighbor_id: number | null;
  subject: string | null;
  content: string;
  message_time: string;
  is_from_user: number;
  contact_type: string;
  contact_value: string;
  attachment_path: string | null;
  status: string;
  error_message: string | null;
  sent_at: string | null;
  processed: number;
  replied: number;
  created_at: string;
}

// 연락처 유형 (kvisual-mcp와 동일)
const CONTACT_TYPES = [
  { value: 'email', label: '이메일', icon: '📧' },
  { value: 'phone', label: '전화', icon: '📞' },
  { value: 'kakao', label: '카카오', icon: '🟡' },
  { value: 'telegram', label: '텔레그램', icon: '✉️' },
  { value: 'line', label: '라인', icon: '🟢' },
  { value: 'nostr', label: 'Nostr', icon: '🔮' },
  { value: 'other', label: '기타', icon: '📋' },
];

// 정보레벨 이름
const LEVEL_NAMES = ['레벨 0', '레벨 1', '레벨 2', '레벨 3', '레벨 4'];

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export function NeighborManagerDialog({ isOpen, onClose }: Props) {
  // 상태
  const [neighbors, setNeighbors] = useState<Neighbor[]>([]);
  const [selectedNeighbor, setSelectedNeighbor] = useState<Neighbor | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [activeLevel, setActiveLevel] = useState<number>(0);
  const [view, setView] = useState<'messages' | 'info'>('messages');

  // 모달 상태
  const [showNeighborModal, setShowNeighborModal] = useState(false);
  const [showContactModal, setShowContactModal] = useState(false);
  const [showContactEditModal, setShowContactEditModal] = useState(false);
  const [showBusinessDocModal, setShowBusinessDocModal] = useState(false);
  const [editingNeighbor, setEditingNeighbor] = useState<Neighbor | null>(null);
  const [editingContact, setEditingContact] = useState<Contact | null>(null);

  // 폼 상태
  const [neighborForm, setNeighborForm] = useState({
    name: '', info_level: 0, rating: 0, additional_info: '', business_doc: '', info_share: 0
  });
  const [contactForm, setContactForm] = useState({ contact_type: 'email', contact_value: '' });
  const [messageInput, setMessageInput] = useState('');
  const [selectedContact, setSelectedContact] = useState<Contact | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 이웃 목록 로드
  const loadNeighbors = async () => {
    try {
      setIsLoading(true);
      const data = await api.getNeighbors(searchQuery || undefined, activeLevel);
      setNeighbors(data);
    } catch (err) {
      console.error('Failed to load neighbors:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // 연락처 로드
  const loadContacts = async (neighborId: number) => {
    try {
      const data = await api.getNeighborContacts(neighborId);
      setContacts(data);
      if (data.length > 0) {
        setSelectedContact(data[0]);
      } else {
        setSelectedContact(null);
      }
    } catch (err) {
      console.error('Failed to load contacts:', err);
      setContacts([]);
      setSelectedContact(null);
    }
  };

  // 메시지 로드
  const loadMessages = async (neighborId: number) => {
    try {
      const data = await api.getBusinessMessages({ neighbor_id: neighborId, limit: 100 });
      setMessages(data.sort((a, b) => new Date(a.message_time).getTime() - new Date(b.message_time).getTime()));
    } catch (err) {
      console.error('Failed to load messages:', err);
      setMessages([]);
    }
  };

  // 초기 로드 및 필터 변경 시 로드
  useEffect(() => {
    if (isOpen) {
      loadNeighbors();
    }
  }, [isOpen, searchQuery, activeLevel]);

  // 이웃 선택 시 연락처와 메시지 로드
  useEffect(() => {
    if (selectedNeighbor) {
      loadContacts(selectedNeighbor.id);
      loadMessages(selectedNeighbor.id);
    }
  }, [selectedNeighbor]);

  // 메시지 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 이웃 선택
  const handleSelectNeighbor = (neighbor: Neighbor) => {
    setSelectedNeighbor(neighbor);
    setView('messages');
  };

  // 이웃 저장
  const handleSaveNeighbor = async () => {
    try {
      if (editingNeighbor) {
        await api.updateNeighbor(editingNeighbor.id, neighborForm);
      } else {
        await api.createNeighbor(neighborForm);
      }
      setShowNeighborModal(false);
      setEditingNeighbor(null);
      setNeighborForm({ name: '', info_level: 0, rating: 0, additional_info: '', business_doc: '', info_share: 0 });
      loadNeighbors();
    } catch (err) {
      console.error('Failed to save neighbor:', err);
      alert('이웃 저장에 실패했습니다.');
    }
  };

  // 이웃 삭제
  const handleDeleteNeighbor = async (id: number) => {
    if (!confirm('이 이웃을 삭제하시겠습니까? 관련 연락처와 메시지도 모두 삭제됩니다.')) return;
    try {
      await api.deleteNeighbor(id);
      if (selectedNeighbor?.id === id) {
        setSelectedNeighbor(null);
      }
      loadNeighbors();
    } catch (err) {
      console.error('Failed to delete neighbor:', err);
      alert('이웃 삭제에 실패했습니다.');
    }
  };

  // 연락처 추가
  const handleAddContact = async () => {
    if (!selectedNeighbor) return;
    try {
      await api.addNeighborContact(selectedNeighbor.id, contactForm);
      setShowContactModal(false);
      setContactForm({ contact_type: 'email', contact_value: '' });
      loadContacts(selectedNeighbor.id);
    } catch (err) {
      console.error('Failed to add contact:', err);
      alert('연락처 추가에 실패했습니다.');
    }
  };

  // 연락처 수정
  const handleUpdateContact = async () => {
    if (!editingContact) return;
    try {
      await api.updateContact(editingContact.id, contactForm);
      setShowContactEditModal(false);
      setEditingContact(null);
      setContactForm({ contact_type: 'email', contact_value: '' });
      if (selectedNeighbor) {
        loadContacts(selectedNeighbor.id);
      }
    } catch (err) {
      console.error('Failed to update contact:', err);
      alert('연락처 수정에 실패했습니다.');
    }
  };

  // 연락처 삭제
  const handleDeleteContact = async (contactId: number) => {
    if (!confirm('이 연락처를 삭제하시겠습니까?')) return;
    try {
      await api.deleteContact(contactId);
      if (selectedNeighbor) {
        loadContacts(selectedNeighbor.id);
      }
    } catch (err) {
      console.error('Failed to delete contact:', err);
      alert('연락처 삭제에 실패했습니다.');
    }
  };

  // 메시지 보내기
  const handleSendMessage = async () => {
    if (!selectedNeighbor || !selectedContact || !messageInput.trim()) return;
    try {
      await api.createBusinessMessage({
        content: messageInput,
        contact_type: selectedContact.contact_type,
        contact_value: selectedContact.contact_value,
        neighbor_id: selectedNeighbor.id,
        is_from_user: 1,
      });
      setMessageInput('');
      loadMessages(selectedNeighbor.id);
    } catch (err) {
      console.error('Failed to send message:', err);
      alert('메시지 전송에 실패했습니다.');
    }
  };

  // 이웃 편집 모달 열기
  const openEditNeighborModal = (neighbor: Neighbor) => {
    setEditingNeighbor(neighbor);
    setNeighborForm({
      name: neighbor.name,
      info_level: neighbor.info_level,
      rating: neighbor.rating,
      additional_info: neighbor.additional_info || '',
      business_doc: neighbor.business_doc || '',
      info_share: neighbor.info_share || 0
    });
    setShowNeighborModal(true);
  };

  // 연락처 편집 모달 열기
  const openEditContactModal = (contact: Contact) => {
    setEditingContact(contact);
    setContactForm({
      contact_type: contact.contact_type,
      contact_value: contact.contact_value
    });
    setShowContactEditModal(true);
  };

  // 정보공유 토글
  const handleToggleInfoShare = async () => {
    if (!selectedNeighbor) return;
    try {
      const newValue = selectedNeighbor.info_share === 1 ? 0 : 1;
      await api.updateNeighbor(selectedNeighbor.id, { info_share: newValue });
      setSelectedNeighbor({ ...selectedNeighbor, info_share: newValue });
      loadNeighbors();
    } catch (err) {
      console.error('Failed to toggle info share:', err);
    }
  };

  // 평점 변경
  const handleRatingChange = async (newRating: number) => {
    if (!selectedNeighbor) return;
    try {
      await api.updateNeighbor(selectedNeighbor.id, { rating: newRating });
      setSelectedNeighbor({ ...selectedNeighbor, rating: newRating });
      loadNeighbors();
    } catch (err) {
      console.error('Failed to update rating:', err);
    }
  };

  // 레벨 변경
  const handleLevelChange = async (newLevel: number) => {
    if (!selectedNeighbor) return;
    try {
      await api.updateNeighbor(selectedNeighbor.id, { info_level: newLevel });
      setSelectedNeighbor({ ...selectedNeighbor, info_level: newLevel });
      loadNeighbors();
    } catch (err) {
      console.error('Failed to update level:', err);
    }
  };

  // 연락처 유형 아이콘
  const getContactIcon = (type: string) => {
    const ct = CONTACT_TYPES.find(t => t.value === type);
    return ct?.icon || '📋';
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-[#FAF8F5] rounded-2xl w-full max-w-5xl h-[85vh] shadow-2xl flex flex-col overflow-hidden">
        {/* 헤더 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#E5DFD5] bg-white">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shadow-sm">
              <Users size={18} className="text-white" />
            </div>
            <h3 className="font-semibold text-lg text-[#4A4035]">이웃 관리</h3>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-[#F5F1EB] rounded-lg transition-colors">
            <X size={18} className="text-[#6B5B4F]" />
          </button>
        </div>

        {/* 컨텐츠 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 왼쪽 사이드바: 이웃 목록 */}
          <div className="w-72 border-r border-[#E5DFD5] flex flex-col bg-[#FAF8F5]">
            {/* 레벨 탭 */}
            <div className="flex border-b border-[#E5DFD5] bg-white">
              {LEVEL_NAMES.map((name, level) => (
                <button
                  key={level}
                  onClick={() => setActiveLevel(level)}
                  className={`flex-1 py-2.5 text-xs font-medium transition-colors ${
                    activeLevel === level
                      ? 'bg-[#D97706] text-white'
                      : 'text-[#6B5B4F] hover:bg-[#F5F1EB]'
                  }`}
                >
                  {name}
                </button>
              ))}
            </div>

            {/* 검색 */}
            <div className="p-3 border-b border-[#E5DFD5] bg-white">
              <div className="relative">
                <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#A99B8E]" />
                <input
                  type="text"
                  placeholder="이름으로 검색..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-10 pr-3 py-2.5 text-sm bg-[#F5F1EB] border-0 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 text-[#4A4035] placeholder-[#A99B8E]"
                />
              </div>
            </div>

            {/* 이웃 목록 */}
            <div className="flex-1 overflow-y-auto">
              {isLoading ? (
                <div className="flex items-center justify-center h-32">
                  <div className="animate-spin rounded-full h-6 w-6 border-2 border-[#E5DFD5] border-t-[#D97706]" />
                </div>
              ) : neighbors.length === 0 ? (
                <div className="p-8 text-center text-[#A99B8E] text-sm">
                  등록된 이웃이 없습니다.
                </div>
              ) : (
                neighbors.map(neighbor => (
                  <div
                    key={neighbor.id}
                    onClick={() => handleSelectNeighbor(neighbor)}
                    className={`p-3 border-b border-[#EAE4DA] cursor-pointer transition-all ${
                      selectedNeighbor?.id === neighbor.id
                        ? 'bg-amber-50 border-l-4 border-l-[#D97706]'
                        : 'hover:bg-[#F5F1EB] bg-white'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-gradient-to-br from-amber-100 to-orange-100 rounded-full flex items-center justify-center">
                        <User size={18} className="text-[#D97706]" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm text-[#4A4035] truncate">{neighbor.name}</div>
                        <div className="flex items-center gap-2 text-xs text-[#8B7B6B] mt-0.5">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${
                            neighbor.info_level === 0 ? 'bg-stone-100 text-stone-600 border-stone-200' :
                            neighbor.info_level === 1 ? 'bg-emerald-50 text-emerald-600 border-emerald-200' :
                            neighbor.info_level === 2 ? 'bg-sky-50 text-sky-600 border-sky-200' :
                            neighbor.info_level === 3 ? 'bg-violet-50 text-violet-600 border-violet-200' : 'bg-rose-50 text-rose-600 border-rose-200'
                          }`}>
                            L{neighbor.info_level}
                          </span>
                          <span className="text-amber-600">{neighbor.rating}/5</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* 이웃 추가 버튼 */}
            <div className="p-3 border-t border-[#E5DFD5] bg-white">
              <button
                onClick={() => {
                  setEditingNeighbor(null);
                  setNeighborForm({ name: '', info_level: activeLevel, rating: 0, additional_info: '', business_doc: '', info_share: 0 });
                  setShowNeighborModal(true);
                }}
                className="w-full py-2.5 bg-[#D97706] text-white text-sm font-medium rounded-xl hover:bg-[#B45309] transition-colors flex items-center justify-center gap-2 shadow-sm"
              >
                <Plus size={16} />
                이웃 추가
              </button>
            </div>
          </div>

          {/* 오른쪽: 상세 정보 */}
          {selectedNeighbor ? (
            <div className="flex-1 flex flex-col bg-white">
              {/* 이웃 헤더 + 탭 */}
              <div className="p-4 border-b border-[#E5DFD5]">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-lg font-semibold text-[#4A4035]">{selectedNeighbor.name}</h2>
                  <div className="flex gap-1">
                    <button
                      onClick={() => openEditNeighborModal(selectedNeighbor)}
                      className="p-2 hover:bg-[#F5F1EB] rounded-lg transition-colors"
                      title="편집"
                    >
                      <Edit2 size={16} className="text-[#6B5B4F]" />
                    </button>
                    <button
                      onClick={() => handleDeleteNeighbor(selectedNeighbor.id)}
                      className="p-2 hover:bg-red-50 rounded-lg transition-colors"
                      title="삭제"
                    >
                      <Trash2 size={16} className="text-red-400" />
                    </button>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setView('messages')}
                    className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                      view === 'messages'
                        ? 'bg-[#D97706] text-white'
                        : 'bg-[#F5F1EB] text-[#6B5B4F] hover:bg-[#EAE4DA]'
                    }`}
                  >
                    대화
                  </button>
                  <button
                    onClick={() => setView('info')}
                    className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                      view === 'info'
                        ? 'bg-[#D97706] text-white'
                        : 'bg-[#F5F1EB] text-[#6B5B4F] hover:bg-[#EAE4DA]'
                    }`}
                  >
                    이웃 정보
                  </button>
                </div>
              </div>

              {/* 대화 뷰 */}
              {view === 'messages' && (
                <>
                  {/* 연락처 선택 */}
                  <div className="p-3 border-b border-[#E5DFD5] bg-[#FAF8F5]">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-[#4A4035]">연락처</span>
                      <button
                        onClick={() => {
                          setContactForm({ contact_type: 'email', contact_value: '' });
                          setShowContactModal(true);
                        }}
                        className="text-xs text-[#D97706] hover:text-[#B45309] flex items-center gap-1 font-medium"
                      >
                        <Plus size={12} /> 추가
                      </button>
                    </div>
                    {contacts.length === 0 ? (
                      <p className="text-xs text-[#A99B8E]">연락처가 없습니다.</p>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {contacts.map(contact => (
                          <button
                            key={contact.id}
                            onClick={() => setSelectedContact(contact)}
                            className={`flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-full border transition-all ${
                              selectedContact?.id === contact.id
                                ? 'bg-[#D97706] text-white border-[#D97706] shadow-sm'
                                : 'bg-white text-[#6B5B4F] border-[#E5DFD5] hover:border-[#D97706]'
                            }`}
                          >
                            <span>{getContactIcon(contact.contact_type)}</span>
                            <span className="max-w-[100px] truncate">{contact.contact_value}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* 메시지 목록 */}
                  <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-[#F5F1EB]">
                    {messages.length === 0 ? (
                      <div className="h-full flex items-center justify-center text-[#A99B8E] text-sm">
                        아직 대화 내역이 없습니다.
                      </div>
                    ) : (
                      messages.map(msg => (
                        <div
                          key={msg.id}
                          className={`flex ${msg.is_from_user ? 'justify-end' : 'justify-start'}`}
                        >
                          <div
                            className={`max-w-[70%] rounded-2xl p-3 ${
                              msg.is_from_user
                                ? 'bg-[#D97706] text-white'
                                : 'bg-white text-[#4A4035] shadow-sm border border-[#E5DFD5]'
                            }`}
                          >
                            {msg.subject && (
                              <div className={`text-xs font-medium mb-1 ${msg.is_from_user ? 'text-amber-100' : 'text-[#8B7B6B]'}`}>
                                {msg.subject}
                              </div>
                            )}
                            <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
                            <div className={`text-xs mt-1.5 flex items-center gap-2 ${msg.is_from_user ? 'text-amber-100' : 'text-[#A99B8E]'}`}>
                              <span>{new Date(msg.message_time).toLocaleString('ko-KR')}</span>
                              {msg.contact_type && (
                                <span>{getContactIcon(msg.contact_type)} {msg.contact_value}</span>
                              )}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                    <div ref={messagesEndRef} />
                  </div>

                  {/* 메시지 입력 */}
                  <div className="p-3 border-t border-[#E5DFD5] bg-white">
                    {!selectedContact ? (
                      <p className="text-sm text-[#A99B8E] text-center">연락처를 선택하거나 추가하세요</p>
                    ) : (
                      <div className="flex gap-2">
                        <input
                          type="text"
                          placeholder="메시지를 입력하세요..."
                          value={messageInput}
                          onChange={(e) => setMessageInput(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
                          className="flex-1 px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 text-[#4A4035] placeholder-[#A99B8E]"
                        />
                        <button
                          onClick={handleSendMessage}
                          disabled={!messageInput.trim()}
                          className="px-4 py-2.5 bg-[#D97706] text-white rounded-xl hover:bg-[#B45309] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          <Send size={18} />
                        </button>
                      </div>
                    )}
                  </div>
                </>
              )}

              {/* 이웃 정보 뷰 */}
              {view === 'info' && (
                <div className="flex-1 overflow-y-auto p-6 bg-[#FAF8F5]">
                  <div className="max-w-2xl mx-auto space-y-5">
                    {/* 기본 정보 */}
                    <div className="bg-white rounded-xl p-5 shadow-sm border border-[#E5DFD5]">
                      <h3 className="font-semibold text-[#4A4035] mb-4">기본 정보</h3>
                      <div className="grid grid-cols-3 gap-4">
                        {/* 정보레벨 */}
                        <div>
                          <label className="block text-xs font-medium text-[#6B5B4F] mb-1.5">정보레벨</label>
                          <select
                            value={selectedNeighbor.info_level}
                            onChange={(e) => handleLevelChange(parseInt(e.target.value))}
                            className="w-full px-3 py-2.5 bg-[#F5F1EB] border-0 rounded-xl text-sm text-[#4A4035] font-medium focus:outline-none focus:ring-2 focus:ring-[#D97706]/30"
                          >
                            {LEVEL_NAMES.map((name, level) => (
                              <option key={level} value={level}>{name}</option>
                            ))}
                          </select>
                        </div>

                        {/* 평점 */}
                        <div>
                          <label className="block text-xs font-medium text-[#6B5B4F] mb-1.5">평점</label>
                          <select
                            value={selectedNeighbor.rating}
                            onChange={(e) => handleRatingChange(parseInt(e.target.value))}
                            className="w-full px-3 py-2.5 bg-[#F5F1EB] border-0 rounded-xl text-sm text-[#4A4035] font-medium focus:outline-none focus:ring-2 focus:ring-[#D97706]/30"
                          >
                            {[0, 1, 2, 3, 4, 5].map(r => (
                              <option key={r} value={r}>{r}/5</option>
                            ))}
                          </select>
                        </div>

                        {/* 정보공유 */}
                        <div>
                          <label className="block text-xs font-medium text-[#6B5B4F] mb-1.5">정보공유</label>
                          <button
                            onClick={handleToggleInfoShare}
                            className={`w-full px-3 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                              selectedNeighbor.info_share === 1
                                ? 'bg-emerald-500 text-white'
                                : 'bg-[#F5F1EB] text-[#6B5B4F]'
                            }`}
                          >
                            {selectedNeighbor.info_share === 1 ? (
                              <span className="flex items-center justify-center gap-2">
                                <ToggleRight size={16} /> ON
                              </span>
                            ) : (
                              <span className="flex items-center justify-center gap-2">
                                <ToggleLeft size={16} /> OFF
                              </span>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* 연락처 */}
                    <div className="bg-white rounded-xl p-5 shadow-sm border border-[#E5DFD5]">
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="font-semibold text-[#4A4035]">연락처</h3>
                        <button
                          onClick={() => {
                            setContactForm({ contact_type: 'email', contact_value: '' });
                            setShowContactModal(true);
                          }}
                          className="text-sm text-[#D97706] hover:text-[#B45309] font-medium"
                        >
                          + 추가
                        </button>
                      </div>
                      {contacts.length === 0 ? (
                        <p className="text-sm text-[#A99B8E]">등록된 연락처가 없습니다.</p>
                      ) : (
                        <div className="space-y-2">
                          {contacts.map(contact => (
                            <div
                              key={contact.id}
                              className="flex items-center justify-between p-3 bg-[#FAF8F5] rounded-xl"
                            >
                              <div className="flex items-center gap-2">
                                <span>{getContactIcon(contact.contact_type)}</span>
                                <span className="text-sm font-medium text-[#6B5B4F]">{contact.contact_type}</span>
                                <span className="text-sm text-[#4A4035]">{contact.contact_value}</span>
                              </div>
                              <div className="flex gap-1">
                                <button
                                  onClick={() => openEditContactModal(contact)}
                                  className="p-1.5 hover:bg-[#E5DFD5] rounded-lg transition-colors"
                                >
                                  <Edit2 size={14} className="text-[#6B5B4F]" />
                                </button>
                                <button
                                  onClick={() => handleDeleteContact(contact.id)}
                                  className="p-1.5 hover:bg-red-50 rounded-lg transition-colors"
                                >
                                  <Trash2 size={14} className="text-red-400" />
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* 비즈니스 문서 */}
                    <div className="bg-white rounded-xl p-5 shadow-sm border border-[#E5DFD5]">
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="font-semibold text-[#4A4035]">열린 비즈니스 문서</h3>
                        {selectedNeighbor.business_doc && (
                          <button
                            onClick={() => setShowBusinessDocModal(true)}
                            className="text-sm text-[#D97706] hover:text-[#B45309] font-medium"
                          >
                            보기
                          </button>
                        )}
                      </div>
                      {selectedNeighbor.business_doc ? (
                        <div
                          onClick={() => setShowBusinessDocModal(true)}
                          className="p-3 bg-amber-50 rounded-xl cursor-pointer hover:bg-amber-100 transition-colors border border-amber-200"
                        >
                          <div className="flex items-center gap-2 text-[#D97706]">
                            <FileText size={16} />
                            <span className="text-sm font-medium">비즈니스 문서 있음 (클릭하여 보기)</span>
                          </div>
                        </div>
                      ) : (
                        <p className="text-sm text-[#A99B8E]">등록된 비즈니스 문서가 없습니다.</p>
                      )}
                    </div>

                    {/* 추가 정보 */}
                    <div className="bg-white rounded-xl p-5 shadow-sm border border-[#E5DFD5]">
                      <h3 className="font-semibold text-[#4A4035] mb-4">추가 정보</h3>
                      {selectedNeighbor.additional_info ? (
                        <p className="text-sm text-[#4A4035] whitespace-pre-wrap leading-relaxed">
                          {selectedNeighbor.additional_info}
                        </p>
                      ) : (
                        <p className="text-sm text-[#A99B8E]">추가 정보가 없습니다.</p>
                      )}
                    </div>

                    {/* 등록일 */}
                    <div className="text-xs text-[#A99B8E] text-right">
                      등록일: {new Date(selectedNeighbor.created_at).toLocaleDateString('ko-KR')}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center bg-[#FAF8F5]">
              <div className="text-center">
                <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-[#F5F1EB] flex items-center justify-center">
                  <Users size={28} className="text-[#A99B8E]" />
                </div>
                <p className="text-[#8B7B6B]">왼쪽에서 이웃을 선택해주세요</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 이웃 추가/편집 모달 */}
      {showNeighborModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[60]">
          <div className="bg-white rounded-2xl w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#E5DFD5]">
              <h3 className="font-semibold text-lg text-[#4A4035]">
                {editingNeighbor ? '이웃 편집' : '새 이웃 추가'}
              </h3>
              <button onClick={() => setShowNeighborModal(false)} className="p-2 hover:bg-[#F5F1EB] rounded-lg transition-colors">
                <X size={18} className="text-[#6B5B4F]" />
              </button>
            </div>
            <div className="p-5 space-y-4 max-h-[60vh] overflow-y-auto">
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">이름 *</label>
                <input
                  type="text"
                  value={neighborForm.name}
                  onChange={(e) => setNeighborForm(prev => ({ ...prev, name: e.target.value }))}
                  className="w-full px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl text-[#4A4035] focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 placeholder-[#A99B8E]"
                  placeholder="이웃의 이름을 입력하세요"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-[#4A4035] mb-1.5">정보 레벨</label>
                  <select
                    value={neighborForm.info_level}
                    onChange={(e) => setNeighborForm(prev => ({ ...prev, info_level: parseInt(e.target.value) }))}
                    className="w-full px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl text-[#4A4035] focus:outline-none focus:ring-2 focus:ring-[#D97706]/30"
                  >
                    {LEVEL_NAMES.map((name, level) => (
                      <option key={level} value={level}>{name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#4A4035] mb-1.5">평점</label>
                  <select
                    value={neighborForm.rating}
                    onChange={(e) => setNeighborForm(prev => ({ ...prev, rating: parseInt(e.target.value) }))}
                    className="w-full px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl text-[#4A4035] focus:outline-none focus:ring-2 focus:ring-[#D97706]/30"
                  >
                    {[0, 1, 2, 3, 4, 5].map(r => (
                      <option key={r} value={r}>{r}점</option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">열린 비즈니스 문서</label>
                <textarea
                  value={neighborForm.business_doc}
                  onChange={(e) => setNeighborForm(prev => ({ ...prev, business_doc: e.target.value }))}
                  className="w-full px-4 py-3 bg-[#F5F1EB] border-0 rounded-xl text-[#4A4035] focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 resize-none placeholder-[#A99B8E]"
                  rows={4}
                  placeholder="이웃이 제공한 비즈니스 문서 내용..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">추가 정보</label>
                <textarea
                  value={neighborForm.additional_info}
                  onChange={(e) => setNeighborForm(prev => ({ ...prev, additional_info: e.target.value }))}
                  className="w-full px-4 py-3 bg-[#F5F1EB] border-0 rounded-xl text-[#4A4035] focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 resize-none placeholder-[#A99B8E]"
                  rows={3}
                  placeholder="추가 정보, 특이사항 등..."
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 px-5 py-4 border-t border-[#E5DFD5]">
              <button
                onClick={() => setShowNeighborModal(false)}
                className="px-4 py-2.5 text-[#6B5B4F] hover:bg-[#F5F1EB] rounded-xl font-medium transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleSaveNeighbor}
                disabled={!neighborForm.name.trim()}
                className="px-5 py-2.5 bg-[#D97706] text-white rounded-xl hover:bg-[#B45309] font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                저장
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 연락처 추가 모달 */}
      {showContactModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[60]">
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#E5DFD5]">
              <h3 className="font-semibold text-lg text-[#4A4035]">연락처 추가</h3>
              <button onClick={() => setShowContactModal(false)} className="p-2 hover:bg-[#F5F1EB] rounded-lg transition-colors">
                <X size={18} className="text-[#6B5B4F]" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">연락처 유형</label>
                <select
                  value={contactForm.contact_type}
                  onChange={(e) => setContactForm(prev => ({ ...prev, contact_type: e.target.value }))}
                  className="w-full px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl text-[#4A4035] focus:outline-none focus:ring-2 focus:ring-[#D97706]/30"
                >
                  {CONTACT_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.icon} {type.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">연락처 값</label>
                <input
                  type="text"
                  value={contactForm.contact_value}
                  onChange={(e) => setContactForm(prev => ({ ...prev, contact_value: e.target.value }))}
                  className="w-full px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl text-[#4A4035] focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 placeholder-[#A99B8E]"
                  placeholder={
                    contactForm.contact_type === 'email' ? 'example@email.com' :
                    contactForm.contact_type === 'phone' ? '010-0000-0000' :
                    contactForm.contact_type === 'nostr' ? 'npub1...' :
                    '연락처를 입력하세요'
                  }
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 px-5 py-4 border-t border-[#E5DFD5]">
              <button
                onClick={() => setShowContactModal(false)}
                className="px-4 py-2.5 text-[#6B5B4F] hover:bg-[#F5F1EB] rounded-xl font-medium transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleAddContact}
                disabled={!contactForm.contact_value.trim()}
                className="px-5 py-2.5 bg-[#D97706] text-white rounded-xl hover:bg-[#B45309] font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                추가
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 연락처 편집 모달 */}
      {showContactEditModal && editingContact && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[60]">
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#E5DFD5]">
              <h3 className="font-semibold text-lg text-[#4A4035]">연락처 편집</h3>
              <button onClick={() => setShowContactEditModal(false)} className="p-2 hover:bg-[#F5F1EB] rounded-lg transition-colors">
                <X size={18} className="text-[#6B5B4F]" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">연락처 유형</label>
                <select
                  value={contactForm.contact_type}
                  onChange={(e) => setContactForm(prev => ({ ...prev, contact_type: e.target.value }))}
                  className="w-full px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl text-[#4A4035] focus:outline-none focus:ring-2 focus:ring-[#D97706]/30"
                >
                  {CONTACT_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.icon} {type.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">연락처 값</label>
                <input
                  type="text"
                  value={contactForm.contact_value}
                  onChange={(e) => setContactForm(prev => ({ ...prev, contact_value: e.target.value }))}
                  className="w-full px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl text-[#4A4035] focus:outline-none focus:ring-2 focus:ring-[#D97706]/30"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 px-5 py-4 border-t border-[#E5DFD5]">
              <button
                onClick={() => setShowContactEditModal(false)}
                className="px-4 py-2.5 text-[#6B5B4F] hover:bg-[#F5F1EB] rounded-xl font-medium transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleUpdateContact}
                disabled={!contactForm.contact_value.trim()}
                className="px-5 py-2.5 bg-[#D97706] text-white rounded-xl hover:bg-[#B45309] font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                저장
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 비즈니스 문서 보기 모달 */}
      {showBusinessDocModal && selectedNeighbor && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[60]">
          <div className="bg-white rounded-2xl w-full max-w-2xl shadow-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#E5DFD5]">
              <h3 className="font-semibold text-lg text-[#4A4035]">{selectedNeighbor.name}의 열린 비즈니스 문서</h3>
              <button onClick={() => setShowBusinessDocModal(false)} className="p-2 hover:bg-[#F5F1EB] rounded-lg transition-colors">
                <X size={18} className="text-[#6B5B4F]" />
              </button>
            </div>
            <div className="flex-1 p-5 overflow-y-auto bg-[#FAF8F5]">
              <pre className="whitespace-pre-wrap text-sm text-[#4A4035] font-sans leading-relaxed">
                {selectedNeighbor.business_doc || '(문서 내용 없음)'}
              </pre>
            </div>
            <div className="flex justify-end px-5 py-4 border-t border-[#E5DFD5]">
              <button
                onClick={() => setShowBusinessDocModal(false)}
                className="px-5 py-2.5 bg-[#6B5B4F] text-white rounded-xl hover:bg-[#5A4A3F] font-medium transition-colors"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
