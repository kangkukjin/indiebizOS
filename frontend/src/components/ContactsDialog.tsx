/**
 * ContactsDialog - 빠른 연락처 다이얼로그
 * 즐겨찾기(favorite)로 등록된 이웃만 보여주는 간단한 목록
 * 클릭하면 이웃관리창(NeighborManagerDialog)에서 해당 이웃의 대화창을 열어줌
 */

import { useState, useEffect } from 'react';
import { X, Star, Mail, Phone, MessageCircle } from 'lucide-react';
import { api } from '../lib/api';
import { NeighborManagerDialog } from './NeighborManagerDialog';

interface Neighbor {
  id: number;
  name: string;
  info_level: number;
  rating: number;
  additional_info: string | null;
  business_doc: string | null;
  info_share: number;
  favorite: number;
}

interface Contact {
  id: number;
  neighbor_id: number;
  contact_type: string;
  contact_value: string;
}

interface ContactsDialogProps {
  show: boolean;
  onClose: () => void;
}

export function ContactsDialog({ show, onClose }: ContactsDialogProps) {
  const [favorites, setFavorites] = useState<Neighbor[]>([]);
  const [contacts, setContacts] = useState<{ [neighborId: number]: Contact[] }>({});
  const [isLoading, setIsLoading] = useState(false);

  // 이웃관리창 상태
  const [showNeighborManager, setShowNeighborManager] = useState(false);
  const [selectedNeighborId, setSelectedNeighborId] = useState<number | undefined>(undefined);

  // 빠른 연락처 목록 로드
  const loadFavorites = async () => {
    setIsLoading(true);
    try {
      const data = await api.getFavoriteNeighbors();
      setFavorites(data);

      // 각 이웃의 연락처도 로드
      const contactsMap: { [neighborId: number]: Contact[] } = {};
      for (const neighbor of data) {
        try {
          const neighborContacts = await api.getNeighborContacts(neighbor.id);
          contactsMap[neighbor.id] = neighborContacts;
        } catch {
          contactsMap[neighbor.id] = [];
        }
      }
      setContacts(contactsMap);
    } catch (error) {
      console.error('빠른 연락처 로드 실패:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (show) {
      loadFavorites();
    }
  }, [show]);

  // 이웃 클릭 시 이웃관리창 열기
  const handleOpenNeighbor = (neighbor: Neighbor) => {
    setSelectedNeighborId(neighbor.id);
    setShowNeighborManager(true);
  };

  // 이웃관리창 닫기
  const handleCloseNeighborManager = () => {
    setShowNeighborManager(false);
    setSelectedNeighborId(undefined);
    // 빠른 연락처 목록 새로고침 (즐겨찾기 해제했을 수 있으므로)
    loadFavorites();
  };

  // 연락처 타입 아이콘
  const getContactIcon = (type: string) => {
    switch (type) {
      case 'email':
      case 'gmail':
        return <Mail size={12} className="text-red-500" />;
      case 'nostr':
        return <MessageCircle size={12} className="text-purple-500" />;
      case 'phone':
        return <Phone size={12} className="text-green-500" />;
      default:
        return <MessageCircle size={12} className="text-gray-400" />;
    }
  };

  // 빠른 연락처에서 제거
  const handleRemoveFavorite = async (e: React.MouseEvent, neighborId: number) => {
    e.stopPropagation();
    try {
      await api.toggleNeighborFavorite(neighborId);
      setFavorites(favorites.filter(n => n.id !== neighborId));
    } catch (error) {
      console.error('즐겨찾기 해제 실패:', error);
    }
  };

  if (!show) return null;

  return (
    <>
      <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
        <div className="bg-[#FAF8F5] rounded-xl w-[360px] max-h-[500px] shadow-xl flex flex-col overflow-hidden">
          {/* 헤더 */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5DFD5] bg-white">
            <div className="flex items-center gap-2">
              <Star size={18} className="text-amber-500 fill-amber-500" />
              <h2 className="font-semibold text-[#4A4035]">빠른 연락처</h2>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 hover:bg-[#F5F1EB] rounded-lg transition-colors"
            >
              <X size={16} className="text-[#6B5B4F]" />
            </button>
          </div>

          {/* 컨텐츠 */}
          <div className="flex-1 overflow-y-auto">
            {isLoading ? (
              <div className="flex items-center justify-center h-32">
                <div className="animate-spin rounded-full h-6 w-6 border-2 border-[#E5DFD5] border-t-[#D97706]" />
              </div>
            ) : favorites.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-40 text-[#8B7B6B] px-6 text-center">
                <Star size={32} className="mb-3 text-[#D5CFC5]" />
                <p className="text-sm mb-2">빠른 연락처가 없습니다</p>
                <p className="text-xs text-[#A99B8E]">
                  비즈니스 → 이웃관리에서<br />
                  이웃의 ★ 버튼을 눌러 추가하세요
                </p>
              </div>
            ) : (
              <div className="py-1">
                {favorites.map((neighbor) => {
                  const neighborContacts = contacts[neighbor.id] || [];
                  return (
                    <button
                      key={neighbor.id}
                      onClick={() => handleOpenNeighbor(neighbor)}
                      className="w-full px-4 py-3 flex items-center gap-3 hover:bg-amber-50 transition-colors text-left border-b border-[#EAE4DA] last:border-b-0"
                    >
                      {/* 아바타 */}
                      <div className="w-10 h-10 rounded-full bg-gradient-to-br from-amber-100 to-orange-100 flex items-center justify-center text-[#D97706] font-medium flex-shrink-0">
                        {neighbor.name.charAt(0)}
                      </div>

                      {/* 정보 */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-[#4A4035] truncate">{neighbor.name}</span>
                        </div>
                        {/* 연락처 미리보기 */}
                        {neighborContacts.length > 0 ? (
                          <div className="flex items-center gap-2 mt-1 flex-wrap">
                            {neighborContacts.slice(0, 2).map((contact) => (
                              <span key={contact.id} className="flex items-center gap-1 text-xs text-[#8B7B6B]">
                                {getContactIcon(contact.contact_type)}
                                <span className="truncate max-w-[120px]">{contact.contact_value}</span>
                              </span>
                            ))}
                            {neighborContacts.length > 2 && (
                              <span className="text-xs text-[#A99B8E]">+{neighborContacts.length - 2}</span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-[#A99B8E]">연락처 없음</span>
                        )}
                      </div>

                      {/* 오른쪽 - 즐겨찾기 제거 버튼 */}
                      <button
                        onClick={(e) => handleRemoveFavorite(e, neighbor.id)}
                        className="p-1.5 hover:bg-amber-100 rounded-lg transition-colors flex-shrink-0"
                        title="빠른 연락처에서 제거"
                      >
                        <Star size={14} className="text-amber-500 fill-amber-500" />
                      </button>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* 푸터 */}
          {favorites.length > 0 && (
            <div className="px-4 py-2.5 border-t border-[#E5DFD5] bg-white">
              <p className="text-xs text-[#A99B8E] text-center">
                클릭하면 대화창이 열립니다
              </p>
            </div>
          )}
        </div>
      </div>

      {/* 이웃관리창 (대화창) */}
      <NeighborManagerDialog
        isOpen={showNeighborManager}
        onClose={handleCloseNeighborManager}
        initialNeighborId={selectedNeighborId}
      />
    </>
  );
}
