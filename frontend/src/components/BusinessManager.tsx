/**
 * BusinessManager - 비즈니스 관리 창
 * kvisual-mcp의 my-business 기능을 React/TypeScript로 재구현
 */

import { useEffect, useState } from 'react';
import {
  Building2, Plus, Search, FileText, ClipboardList,
  Edit2, Trash2, Save, X, Package, RefreshCw, Users, Briefcase, Zap, ImagePlus
} from 'lucide-react';
import { api } from '../lib/api';
import { NeighborManagerDialog } from './NeighborManagerDialog';

// 타입 정의
interface Business {
  id: number;
  name: string;
  level: number;
  description: string | null;
  created_at: string;
  updated_at: string;
}

interface BusinessItem {
  id: number;
  business_id: number;
  title: string;
  details: string | null;
  attachment_path: string | null;
  created_at: string;
  updated_at: string;
}

interface BusinessDocument {
  id: number;
  level: number;
  title: string;
  content: string;
  updated_at: string;
}

// 이미지 경로 파싱 (JSON 배열 or 레거시 단일 경로)
function parseImagePaths(attachmentPath: string | null): string[] {
  if (!attachmentPath) return [];
  try {
    const parsed = JSON.parse(attachmentPath);
    if (Array.isArray(parsed)) return parsed;
  } catch {
    // 레거시 단일 경로
  }
  return [attachmentPath];
}

const IMAGE_EXTS = /\.(jpg|jpeg|png|gif|webp)$/i;

const LEVEL_NAMES = ['폐쇄중', '레벨 0', '레벨 1', '레벨 2', '레벨 3', '레벨 4'];
const LEVEL_COLORS: Record<number, string> = {
  [-1]: 'bg-stone-200 text-stone-700 border-stone-300',
  0: 'bg-amber-50 text-amber-700 border-amber-200',
  1: 'bg-orange-50 text-orange-700 border-orange-200',
  2: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  3: 'bg-sky-50 text-sky-700 border-sky-200',
  4: 'bg-violet-50 text-violet-700 border-violet-200',
};

export function BusinessManager() {
  // 상태
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [selectedBusiness, setSelectedBusiness] = useState<Business | null>(null);
  const [businessItems, setBusinessItems] = useState<BusinessItem[]>([]);
  const [currentLevel, setCurrentLevel] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 모달 상태
  const [showBusinessModal, setShowBusinessModal] = useState(false);
  const [showItemModal, setShowItemModal] = useState(false);
  const [showDocumentModal, setShowDocumentModal] = useState(false);
  const [documentType, setDocumentType] = useState<'business' | 'guideline'>('business');

  // 편집 상태
  const [editingBusiness, setEditingBusiness] = useState<Business | null>(null);
  const [editingItem, setEditingItem] = useState<BusinessItem | null>(null);

  // 폼 상태
  const [businessForm, setBusinessForm] = useState({ name: '', level: 0, description: '' });
  const [itemForm, setItemForm] = useState({ title: '', details: '', attachment_paths: [] as string[] });

  // 문서 상태
  const [documents, setDocuments] = useState<Record<number, BusinessDocument>>({});
  const [currentDocLevel, setCurrentDocLevel] = useState(0);
  const [docForm, setDocForm] = useState({ title: '', content: '' });

  // 이웃관리 다이얼로그
  const [showNeighborManager, setShowNeighborManager] = useState(false);

  // 아이템 저장 로딩 (nostr.build 업로드 포함)
  const [isSavingItem, setIsSavingItem] = useState(false);

  // 자동응답 상태
  const [autoResponseRunning, setAutoResponseRunning] = useState(false);
  const [autoResponseLoading, setAutoResponseLoading] = useState(false);

  // 초기 로드
  useEffect(() => {
    loadBusinesses();
  }, [currentLevel, searchQuery]);

  // 자동응답 상태 로드
  useEffect(() => {
    loadAutoResponseStatus();
  }, []);

  const loadAutoResponseStatus = async () => {
    try {
      const status = await api.getAutoResponseStatus();
      setAutoResponseRunning(status.running);
    } catch (err) {
      console.error('Failed to load auto-response status:', err);
    }
  };

  const toggleAutoResponse = async () => {
    try {
      setAutoResponseLoading(true);
      if (autoResponseRunning) {
        const result = await api.stopAutoResponse();
        setAutoResponseRunning(result.running);
      } else {
        const result = await api.startAutoResponse();
        setAutoResponseRunning(result.running);
      }
    } catch (err) {
      console.error('Failed to toggle auto-response:', err);
    } finally {
      setAutoResponseLoading(false);
    }
  };

  // 비즈니스 목록 로드
  const loadBusinesses = async () => {
    try {
      setIsLoading(true);
      const data = await api.getBusinesses(currentLevel, searchQuery || undefined);
      setBusinesses(data);
      setError(null);
    } catch (err) {
      setError('비즈니스 목록을 불러오는데 실패했습니다.');
      console.error('Failed to load businesses:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // 비즈니스 아이템 로드
  const loadBusinessItems = async (businessId: number) => {
    try {
      const data = await api.getBusinessItems(businessId);
      setBusinessItems(data);
    } catch (err) {
      console.error('Failed to load business items:', err);
      setBusinessItems([]);
    }
  };

  // 비즈니스 선택
  const handleSelectBusiness = (business: Business) => {
    setSelectedBusiness(business);
    loadBusinessItems(business.id);
  };

  // 비즈니스 저장
  const handleSaveBusiness = async () => {
    try {
      if (editingBusiness) {
        await api.updateBusiness(editingBusiness.id, businessForm);
      } else {
        await api.createBusiness(businessForm);
      }
      setShowBusinessModal(false);
      setEditingBusiness(null);
      setBusinessForm({ name: '', level: currentLevel, description: '' });
      loadBusinesses();
    } catch (err) {
      console.error('Failed to save business:', err);
      alert('비즈니스 저장에 실패했습니다.');
    }
  };

  // 비즈니스 삭제
  const handleDeleteBusiness = async (id: number) => {
    if (!confirm('이 비즈니스를 삭제하시겠습니까? 관련 아이템도 모두 삭제됩니다.')) return;
    try {
      await api.deleteBusiness(id);
      if (selectedBusiness?.id === id) {
        setSelectedBusiness(null);
        setBusinessItems([]);
      }
      loadBusinesses();
    } catch (err) {
      console.error('Failed to delete business:', err);
      alert('비즈니스 삭제에 실패했습니다.');
    }
  };

  // 아이템 저장 (이미지 업로드 포함 - 시간 소요 가능)
  const handleSaveItem = async () => {
    if (!selectedBusiness) return;
    try {
      setIsSavingItem(true);
      const payload = {
        title: itemForm.title,
        details: itemForm.details || undefined,
        attachment_paths: itemForm.attachment_paths.length > 0 ? itemForm.attachment_paths : undefined,
      };
      if (editingItem) {
        await api.updateBusinessItem(editingItem.id, payload);
      } else {
        await api.createBusinessItem(selectedBusiness.id, payload);
      }
      setShowItemModal(false);
      setEditingItem(null);
      setItemForm({ title: '', details: '', attachment_paths: [] });
      loadBusinessItems(selectedBusiness.id);
    } catch (err) {
      console.error('Failed to save item:', err);
      alert('아이템 저장에 실패했습니다.');
    } finally {
      setIsSavingItem(false);
    }
  };

  // 이미지 파일 선택
  const handleSelectImages = async () => {
    if (!window.electron?.selectImages) return;
    const filePaths = await window.electron.selectImages();
    if (!filePaths || filePaths.length === 0) return;
    try {
      const result = await api.copyImagesForBusinessItem(filePaths);
      if (result.paths.length > 0) {
        setItemForm(prev => ({
          ...prev,
          attachment_paths: [...prev.attachment_paths, ...result.paths]
        }));
      }
    } catch (err) {
      console.error('Failed to copy images:', err);
      alert('이미지 복사에 실패했습니다.');
    }
  };

  // 이미지 제거
  const handleRemoveImage = (index: number) => {
    setItemForm(prev => ({
      ...prev,
      attachment_paths: prev.attachment_paths.filter((_, i) => i !== index)
    }));
  };

  // 아이템 삭제
  const handleDeleteItem = async (id: number) => {
    if (!selectedBusiness) return;
    if (!confirm('이 아이템을 삭제하시겠습니까?')) return;
    try {
      await api.deleteBusinessItem(id);
      loadBusinessItems(selectedBusiness.id);
    } catch (err) {
      console.error('Failed to delete item:', err);
      alert('아이템 삭제에 실패했습니다.');
    }
  };

  // 문서 모달 열기
  const handleOpenDocumentModal = async (type: 'business' | 'guideline') => {
    setDocumentType(type);
    setCurrentDocLevel(0);
    try {
      const data = type === 'business'
        ? await api.getAllBusinessDocuments()
        : await api.getAllWorkGuidelines();

      const docsMap: Record<number, BusinessDocument> = {};
      data.forEach((doc: BusinessDocument) => {
        docsMap[doc.level] = doc;
      });
      setDocuments(docsMap);

      const firstDoc = docsMap[0];
      if (firstDoc) {
        setDocForm({ title: firstDoc.title, content: firstDoc.content });
      } else {
        setDocForm({ title: '', content: '' });
      }

      setShowDocumentModal(true);
    } catch (err) {
      console.error('Failed to load documents:', err);
      alert('문서를 불러오는데 실패했습니다.');
    }
  };

  // 문서 레벨 변경
  const handleDocLevelChange = (level: number) => {
    setCurrentDocLevel(level);
    const doc = documents[level];
    if (doc) {
      setDocForm({ title: doc.title, content: doc.content });
    } else {
      setDocForm({ title: '', content: '' });
    }
  };

  // 문서 저장
  const handleSaveDocument = async () => {
    try {
      if (documentType === 'business') {
        await api.updateBusinessDocument(currentDocLevel, docForm);
      } else {
        await api.updateWorkGuideline(currentDocLevel, docForm);
      }

      // 업데이트된 문서 반영
      setDocuments(prev => ({
        ...prev,
        [currentDocLevel]: {
          ...prev[currentDocLevel],
          level: currentDocLevel,
          title: docForm.title,
          content: docForm.content,
          updated_at: new Date().toISOString(),
        } as BusinessDocument
      }));

      alert('문서가 저장되었습니다.');
    } catch (err) {
      console.error('Failed to save document:', err);
      alert('문서 저장에 실패했습니다.');
    }
  };

  // 비즈니스 문서 자동 생성
  const handleRegenerateDocuments = async () => {
    if (!confirm('비즈니스 목록을 기반으로 모든 레벨의 문서를 자동 생성합니다.\n기존 문서 내용이 덮어씌워집니다. 계속하시겠습니까?')) {
      return;
    }
    try {
      const result = await api.regenerateBusinessDocuments();
      if (result.status === 'success') {
        // 문서 다시 로드
        const data = await api.getAllBusinessDocuments();
        const docsMap: Record<number, BusinessDocument> = {};
        data.forEach((doc: BusinessDocument) => {
          docsMap[doc.level] = doc;
        });
        setDocuments(docsMap);

        // 현재 선택된 레벨 문서 반영
        const currentDoc = docsMap[currentDocLevel];
        if (currentDoc) {
          setDocForm({ title: currentDoc.title, content: currentDoc.content });
        }

        alert(result.message);
      } else {
        alert('문서 생성에 실패했습니다: ' + result.message);
      }
    } catch (err) {
      console.error('Failed to regenerate documents:', err);
      alert('문서 자동 생성에 실패했습니다.');
    }
  };

  // 비즈니스 편집 모달 열기
  const openEditBusinessModal = (business: Business) => {
    setEditingBusiness(business);
    setBusinessForm({
      name: business.name,
      level: business.level,
      description: business.description || ''
    });
    setShowBusinessModal(true);
  };

  // 아이템 편집 모달 열기
  const openEditItemModal = (item: BusinessItem) => {
    setEditingItem(item);
    setItemForm({
      title: item.title,
      details: item.details || '',
      attachment_paths: parseImagePaths(item.attachment_path)
    });
    setShowItemModal(true);
  };

  return (
    <div className="h-full flex flex-col bg-[#F5F1EB]">
      {/* 헤더 */}
      <div className="h-11 flex items-center justify-between px-4 bg-[#F5F1EB] border-b border-[#E5DFD5] drag">
        <div className="flex items-center gap-2.5 no-drag">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shadow-sm">
            <Building2 size={16} className="text-white" />
          </div>
          <span className="font-semibold text-[#4A4035]">비즈니스 관리</span>
        </div>
        <div className="flex items-center gap-3 no-drag">
          {/* 자동응답 토글 */}
          <button
            onClick={toggleAutoResponse}
            disabled={autoResponseLoading}
            className={`flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded-lg transition-all shadow-sm ${
              autoResponseRunning
                ? 'bg-emerald-500 text-white hover:bg-emerald-600'
                : 'bg-[#E5DFD5] text-[#6B5B4F] hover:bg-[#D9D2C7]'
            } ${autoResponseLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
            title={autoResponseRunning ? '자동응답 끄기' : '자동응답 켜기'}
          >
            <Zap size={15} className={autoResponseRunning ? 'fill-current' : ''} />
            자동응답
            <div className={`w-8 h-4 rounded-full relative transition-colors ${
              autoResponseRunning ? 'bg-emerald-300' : 'bg-[#C5BFB5]'
            }`}>
              <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-all ${
                autoResponseRunning ? 'left-4' : 'left-0.5'
              }`} />
            </div>
          </button>
          <button
            onClick={() => setShowNeighborManager(true)}
            className="flex items-center gap-2 px-3 py-1.5 bg-[#6B5B4F] text-white text-sm font-medium rounded-lg hover:bg-[#5A4A3F] transition-colors shadow-sm"
          >
            <Users size={15} />
            이웃관리
          </button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* 사이드바 */}
        <div className="w-72 bg-[#FAF8F5] border-r border-[#E5DFD5] flex flex-col">
          {/* 레벨 탭 */}
          <div className="flex flex-wrap border-b border-[#E5DFD5] bg-white">
            {[-1, 0, 1, 2, 3, 4].map(level => (
              <button
                key={level}
                onClick={() => setCurrentLevel(level)}
                className={`flex-1 min-w-[33%] py-2.5 text-xs font-medium transition-all ${
                  currentLevel === level
                    ? 'text-[#4A4035] bg-[#F5F1EB] border-b-2 border-[#D97706]'
                    : 'text-[#8B7B6B] hover:bg-[#F5F1EB]/50'
                }`}
              >
                {LEVEL_NAMES[level + 1]}
              </button>
            ))}
          </div>

          {/* 검색 */}
          <div className="p-3 bg-white border-b border-[#E5DFD5]">
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#A99B8E]" />
              <input
                type="text"
                placeholder="비즈니스 검색..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-sm bg-[#F5F1EB] border-0 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 text-[#4A4035] placeholder-[#A99B8E]"
              />
            </div>
          </div>

          {/* 비즈니스 목록 */}
          <div className="flex-1 overflow-y-auto">
            {isLoading ? (
              <div className="flex items-center justify-center h-32">
                <div className="animate-spin rounded-full h-6 w-6 border-2 border-[#D97706] border-t-transparent" />
              </div>
            ) : error ? (
              <div className="p-4 text-center text-red-600 text-sm">{error}</div>
            ) : businesses.length === 0 ? (
              <div className="p-8 text-center text-[#A99B8E] text-sm">
                <Briefcase size={32} className="mx-auto mb-3 opacity-40" />
                등록된 비즈니스가 없습니다
              </div>
            ) : (
              businesses.map(business => (
                <div
                  key={business.id}
                  onClick={() => handleSelectBusiness(business)}
                  className={`p-3.5 border-b border-[#EAE4DA] cursor-pointer transition-all group ${
                    selectedBusiness?.id === business.id
                      ? 'bg-white border-l-3 border-l-[#D97706] shadow-sm'
                      : 'hover:bg-white/60'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm text-[#4A4035] truncate">
                        {business.name}
                      </div>
                      <div className="flex items-center gap-2 mt-1.5">
                        <span className={`px-2 py-0.5 text-xs font-medium rounded border ${LEVEL_COLORS[business.level] || LEVEL_COLORS[0]}`}>
                          {LEVEL_NAMES[business.level + 1]}
                        </span>
                      </div>
                      {business.description && (
                        <div className="text-xs text-[#8B7B6B] mt-1.5 truncate">
                          {business.description}
                        </div>
                      )}
                    </div>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity ml-2">
                      <button
                        onClick={(e) => { e.stopPropagation(); openEditBusinessModal(business); }}
                        className="p-1.5 hover:bg-[#EAE4DA] rounded-lg transition-colors"
                      >
                        <Edit2 size={13} className="text-[#6B5B4F]" />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteBusiness(business.id); }}
                        className="p-1.5 hover:bg-red-50 rounded-lg transition-colors"
                      >
                        <Trash2 size={13} className="text-red-500" />
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* 하단 버튼들 */}
          <div className="p-3 bg-white border-t border-[#E5DFD5] space-y-2">
            <button
              onClick={() => {
                setEditingBusiness(null);
                setBusinessForm({ name: '', level: currentLevel, description: '' });
                setShowBusinessModal(true);
              }}
              className="w-full py-2.5 bg-[#D97706] text-white text-sm font-medium rounded-lg hover:bg-[#B45309] transition-colors flex items-center justify-center gap-2 shadow-sm"
            >
              <Plus size={16} />
              비즈니스 생성
            </button>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => handleOpenDocumentModal('business')}
                className="py-2 bg-[#6B5B4F] text-white text-xs font-medium rounded-lg hover:bg-[#5A4A3F] transition-colors flex items-center justify-center gap-1.5"
              >
                <FileText size={14} />
                비즈니스 문서
              </button>
              <button
                onClick={() => handleOpenDocumentModal('guideline')}
                className="py-2 bg-[#8B7B6B] text-white text-xs font-medium rounded-lg hover:bg-[#6B5B4F] transition-colors flex items-center justify-center gap-1.5"
              >
                <ClipboardList size={14} />
                근무 지침
              </button>
            </div>
          </div>
        </div>

        {/* 메인 컨텐츠 */}
        <div className="flex-1 flex flex-col bg-white">
          <div className="px-6 py-4 border-b border-[#E5DFD5] bg-[#FAF8F5]">
            <h2 className="text-lg font-semibold text-[#4A4035]">
              {selectedBusiness ? selectedBusiness.name : '비즈니스를 선택해주세요'}
            </h2>
            {selectedBusiness?.description && (
              <p className="text-sm text-[#8B7B6B] mt-1">{selectedBusiness.description}</p>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            {!selectedBusiness ? (
              <div className="h-full flex items-center justify-center">
                <div className="text-center text-[#A99B8E]">
                  <Package size={48} className="mx-auto mb-4 opacity-40" />
                  <p className="font-medium">왼쪽에서 비즈니스를 선택하면</p>
                  <p className="text-sm mt-1">아이템 목록이 표시됩니다</p>
                </div>
              </div>
            ) : businessItems.length === 0 ? (
              <div className="h-full flex items-center justify-center">
                <div className="text-center text-[#A99B8E]">
                  <Package size={48} className="mx-auto mb-4 opacity-40" />
                  <p className="font-medium">등록된 아이템이 없습니다</p>
                  <p className="text-sm mt-1">아래 버튼을 눌러 아이템을 추가하세요</p>
                </div>
              </div>
            ) : (
              <div className="space-y-3 max-w-3xl">
                {businessItems.map(item => (
                  <div
                    key={item.id}
                    className="p-5 bg-[#FAF8F5] border border-[#E5DFD5] rounded-xl hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <h3 className="font-semibold text-[#4A4035]">{item.title}</h3>
                      <div className="flex gap-1.5">
                        <button
                          onClick={() => openEditItemModal(item)}
                          className="px-2.5 py-1 text-xs font-medium text-[#6B5B4F] bg-white border border-[#E5DFD5] rounded-lg hover:bg-[#F5F1EB] transition-colors"
                        >
                          편집
                        </button>
                        <button
                          onClick={() => handleDeleteItem(item.id)}
                          className="px-2.5 py-1 text-xs font-medium text-red-600 bg-white border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
                        >
                          삭제
                        </button>
                      </div>
                    </div>
                    {item.details && (
                      <p className="text-sm text-[#6B5B4F] whitespace-pre-wrap leading-relaxed">{item.details}</p>
                    )}
                    {item.attachment_path && (() => {
                      const paths = parseImagePaths(item.attachment_path);
                      const images = paths.filter(p => IMAGE_EXTS.test(p));
                      const files = paths.filter(p => !IMAGE_EXTS.test(p));
                      return (
                        <div className="mt-3">
                          {images.length > 0 && (
                            <div className="flex flex-wrap gap-2 mb-2">
                              {images.map((imgPath, idx) => (
                                <img
                                  key={idx}
                                  src={`http://127.0.0.1:8765/image?path=${encodeURIComponent(imgPath)}`}
                                  alt=""
                                  className="w-24 h-24 object-cover rounded-lg border border-[#E5DFD5]"
                                />
                              ))}
                            </div>
                          )}
                          {files.map((filePath, idx) => (
                            <div key={idx} className="inline-flex items-center gap-2 px-3 py-1.5 bg-white border border-[#E5DFD5] rounded-lg text-xs text-[#6B5B4F] mr-2">
                              <FileText size={14} className="text-[#D97706]" />
                              {filePath.split('/').pop()}
                            </div>
                          ))}
                        </div>
                      );
                    })()}
                    <div className="mt-3 pt-3 border-t border-[#E5DFD5] text-xs text-[#A99B8E]">
                      수정: {new Date(item.updated_at).toLocaleString('ko-KR')}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 아이템 추가 버튼 */}
          {selectedBusiness && (
            <div className="absolute bottom-6 right-6">
              <button
                onClick={() => {
                  setEditingItem(null);
                  setItemForm({ title: '', details: '', attachment_paths: [] });
                  setShowItemModal(true);
                }}
                className="px-5 py-3 bg-[#D97706] text-white font-medium rounded-full shadow-lg hover:bg-[#B45309] transition-colors flex items-center gap-2"
              >
                <Plus size={18} />
                아이템 추가
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 비즈니스 모달 */}
      {showBusinessModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#E5DFD5]">
              <h3 className="font-semibold text-[#4A4035]">
                {editingBusiness ? '비즈니스 편집' : '새 비즈니스 추가'}
              </h3>
              <button onClick={() => setShowBusinessModal(false)} className="p-1.5 hover:bg-[#F5F1EB] rounded-lg transition-colors">
                <X size={18} className="text-[#6B5B4F]" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">비즈니스 이름 *</label>
                <input
                  type="text"
                  value={businessForm.name}
                  onChange={(e) => setBusinessForm(prev => ({ ...prev, name: e.target.value }))}
                  className="w-full px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 text-[#4A4035] placeholder-[#A99B8E]"
                  placeholder="비즈니스 이름을 입력하세요"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">레벨</label>
                <select
                  value={businessForm.level}
                  onChange={(e) => setBusinessForm(prev => ({ ...prev, level: parseInt(e.target.value) }))}
                  className="w-full px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 text-[#4A4035]"
                >
                  {[-1, 0, 1, 2, 3, 4].map(level => (
                    <option key={level} value={level}>{LEVEL_NAMES[level + 1]}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">설명</label>
                <textarea
                  value={businessForm.description}
                  onChange={(e) => setBusinessForm(prev => ({ ...prev, description: e.target.value }))}
                  className="w-full px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 resize-none text-[#4A4035] placeholder-[#A99B8E]"
                  rows={3}
                  placeholder="비즈니스에 대한 설명을 입력하세요"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 px-5 py-4 border-t border-[#E5DFD5]">
              <button
                onClick={() => setShowBusinessModal(false)}
                className="px-4 py-2 text-[#6B5B4F] hover:bg-[#F5F1EB] rounded-lg font-medium transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleSaveBusiness}
                disabled={!businessForm.name.trim()}
                className="px-5 py-2 bg-[#D97706] text-white rounded-lg font-medium hover:bg-[#B45309] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                저장
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 아이템 모달 */}
      {showItemModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#E5DFD5]">
              <h3 className="font-semibold text-[#4A4035]">
                {editingItem ? '아이템 편집' : '새 아이템 추가'}
              </h3>
              <button onClick={() => setShowItemModal(false)} className="p-1.5 hover:bg-[#F5F1EB] rounded-lg transition-colors">
                <X size={18} className="text-[#6B5B4F]" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">제목 *</label>
                <input
                  type="text"
                  value={itemForm.title}
                  onChange={(e) => setItemForm(prev => ({ ...prev, title: e.target.value }))}
                  className="w-full px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 text-[#4A4035] placeholder-[#A99B8E]"
                  placeholder="아이템 제목을 입력하세요"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">세부사항</label>
                <textarea
                  value={itemForm.details}
                  onChange={(e) => setItemForm(prev => ({ ...prev, details: e.target.value }))}
                  className="w-full px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 resize-none text-[#4A4035] placeholder-[#A99B8E]"
                  rows={4}
                  placeholder="아이템에 대한 자세한 설명을 입력하세요"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">
                  이미지 ({itemForm.attachment_paths.length}개)
                </label>
                {itemForm.attachment_paths.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-3">
                    {itemForm.attachment_paths.map((imgPath, idx) => (
                      <div key={idx} className="relative group">
                        {IMAGE_EXTS.test(imgPath) ? (
                          <img
                            src={`http://127.0.0.1:8765/image?path=${encodeURIComponent(imgPath)}`}
                            alt=""
                            className="w-20 h-20 object-cover rounded-lg border border-[#E5DFD5]"
                          />
                        ) : (
                          <div className="w-20 h-20 flex items-center justify-center rounded-lg border border-[#E5DFD5] bg-[#F5F1EB]">
                            <FileText size={20} className="text-[#6B5B4F]" />
                          </div>
                        )}
                        <button
                          type="button"
                          onClick={() => handleRemoveImage(idx)}
                          className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 text-white rounded-full text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <button
                  type="button"
                  onClick={handleSelectImages}
                  className="w-full py-2.5 bg-[#F5F1EB] border-2 border-dashed border-[#D9D2C7] rounded-xl text-sm text-[#6B5B4F] hover:bg-[#EAE4DA] hover:border-[#C5BFB5] transition-colors flex items-center justify-center gap-2"
                >
                  <ImagePlus size={16} />
                  이미지 추가
                </button>
              </div>
            </div>
            <div className="flex justify-end gap-2 px-5 py-4 border-t border-[#E5DFD5]">
              <button
                onClick={() => setShowItemModal(false)}
                className="px-4 py-2 text-[#6B5B4F] hover:bg-[#F5F1EB] rounded-lg font-medium transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleSaveItem}
                disabled={!itemForm.title.trim() || isSavingItem}
                className="px-5 py-2 bg-[#D97706] text-white rounded-lg font-medium hover:bg-[#B45309] disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              >
                {isSavingItem ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                    {itemForm.attachment_paths.length > 0 ? '이미지 업로드 중...' : '저장 중...'}
                  </>
                ) : '저장'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 문서 모달 */}
      {showDocumentModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl w-full max-w-3xl shadow-2xl max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#E5DFD5]">
              <h3 className="font-semibold text-[#4A4035]">
                {documentType === 'business' ? '나의 비즈니스 문서' : '근무 지침'}
              </h3>
              <button onClick={() => setShowDocumentModal(false)} className="p-1.5 hover:bg-[#F5F1EB] rounded-lg transition-colors">
                <X size={18} className="text-[#6B5B4F]" />
              </button>
            </div>

            {/* 레벨 탭 */}
            <div className="grid grid-cols-5 border-b border-[#E5DFD5]">
              {[0, 1, 2, 3, 4].map(level => (
                <button
                  key={level}
                  onClick={() => handleDocLevelChange(level)}
                  className={`py-3 text-sm font-medium transition-all ${
                    currentDocLevel === level
                      ? 'text-[#D97706] bg-[#FEF3C7] border-b-2 border-[#D97706]'
                      : 'text-[#8B7B6B] hover:bg-[#F5F1EB]'
                  }`}
                >
                  레벨 {level}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">제목</label>
                <input
                  type="text"
                  value={docForm.title}
                  onChange={(e) => setDocForm(prev => ({ ...prev, title: e.target.value }))}
                  className="w-full px-4 py-2.5 bg-[#F5F1EB] border-0 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 text-[#4A4035] placeholder-[#A99B8E]"
                  placeholder="문서 제목을 입력하세요"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#4A4035] mb-1.5">내용</label>
                <textarea
                  value={docForm.content}
                  onChange={(e) => setDocForm(prev => ({ ...prev, content: e.target.value }))}
                  className="w-full px-4 py-3 bg-[#F5F1EB] border-0 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#D97706]/30 resize-none font-mono text-sm text-[#4A4035] placeholder-[#A99B8E] leading-relaxed"
                  rows={15}
                  placeholder="문서 내용을 입력하세요"
                />
              </div>
            </div>

            <div className="flex justify-between px-5 py-4 border-t border-[#E5DFD5]">
              <div>
                {documentType === 'business' && (
                  <button
                    onClick={handleRegenerateDocuments}
                    className="px-4 py-2 bg-[#8B7B6B] text-white rounded-lg font-medium hover:bg-[#6B5B4F] transition-colors flex items-center gap-2"
                    title="비즈니스 목록 기반으로 문서 자동 생성"
                  >
                    <RefreshCw size={15} />
                    자동 생성
                  </button>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowDocumentModal(false)}
                  className="px-4 py-2 text-[#6B5B4F] hover:bg-[#F5F1EB] rounded-lg font-medium transition-colors"
                >
                  취소
                </button>
                <button
                  onClick={handleSaveDocument}
                  className="px-5 py-2 bg-[#D97706] text-white rounded-lg font-medium hover:bg-[#B45309] transition-colors flex items-center gap-2"
                >
                  <Save size={15} />
                  저장
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 이웃관리 다이얼로그 */}
      <NeighborManagerDialog
        isOpen={showNeighborManager}
        onClose={() => setShowNeighborManager(false)}
      />
    </div>
  );
}
