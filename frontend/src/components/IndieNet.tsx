/**
 * IndieNet - Nostr 기반 P2P 커뮤니티 게시판
 */

import { useEffect, useState, useRef } from 'react';
import { Globe, Send, RefreshCw, Settings, Copy, Check, X, MessageCircle, Edit2, Save, Key, RotateCcw, AlertTriangle, ArrowLeft, Mail } from 'lucide-react';
import { api } from '../lib/api';

interface IndieNetPost {
  id: string;
  author: string;
  content: string;
  created_at: number;
  tags: string[][];
}

interface IndieNetDM {
  id: string;
  from: string;
  content: string;
  created_at: number;
  tags: string[][];
}

interface IndieNetIdentity {
  npub: string;
  display_name: string;
  created_at: string;
}

interface IndieNetSettings {
  relays: string[];
  default_tags: string[];
  auto_refresh: boolean;
  refresh_interval: number;
}

export function IndieNet() {
  const [posts, setPosts] = useState<IndieNetPost[]>([]);
  const [identity, setIdentity] = useState<IndieNetIdentity | null>(null);
  const [settings, setSettings] = useState<IndieNetSettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPosting, setIsPosting] = useState(false);
  const [newPostContent, setNewPostContent] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [copiedNpub, setCopiedNpub] = useState(false);

  // 설정에서 이름 편집
  const [editingName, setEditingName] = useState(false);
  const [newDisplayName, setNewDisplayName] = useState('');

  // ID 가져오기/초기화
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [importNsec, setImportNsec] = useState('');
  const [importError, setImportError] = useState<string | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  // 선택된 게시글 (상세보기)
  const [selectedPost, setSelectedPost] = useState<IndieNetPost | null>(null);

  // 탭 (게시판/DM)
  const [activeTab, setActiveTab] = useState<'posts' | 'dms'>('posts');

  // DM 관련
  const [dms, setDms] = useState<IndieNetDM[]>([]);
  const [selectedDm, setSelectedDm] = useState<IndieNetDM | null>(null);
  const [isLoadingDms, setIsLoadingDms] = useState(false);
  const [showSendDmDialog, setShowSendDmDialog] = useState(false);
  const [dmRecipient, setDmRecipient] = useState('');
  const [dmContent, setDmContent] = useState('');
  const [isSendingDm, setIsSendingDm] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const refreshIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 초기 로드
  useEffect(() => {
    loadStatus();
    loadPosts();
  }, []);

  // 자동 새로고침
  useEffect(() => {
    if (settings?.auto_refresh && settings?.refresh_interval > 0) {
      refreshIntervalRef.current = setInterval(() => {
        loadPosts();
      }, settings.refresh_interval * 1000);
    }
    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }
    };
  }, [settings?.auto_refresh, settings?.refresh_interval]);

  const loadStatus = async () => {
    try {
      const status = await api.getIndieNetStatus();
      if (status.identity) {
        setIdentity(status.identity);
        setNewDisplayName(status.identity.display_name || '');
      }
      if (status.settings) {
        setSettings(status.settings);
      }
    } catch (err: any) {
      console.error('IndieNet 상태 로드 실패:', err);
    }
  };

  const loadPosts = async () => {
    try {
      setIsLoading(true);
      const result = await api.getIndieNetPosts(50);
      setPosts(result.posts || []);
      setError(null);
    } catch (err: any) {
      setError(err.message || '게시글 로드 실패');
    } finally {
      setIsLoading(false);
    }
  };

  const loadDms = async () => {
    try {
      setIsLoadingDms(true);
      const result = await api.getIndieNetDMs(50);
      setDms(result.dms || []);
    } catch (err: any) {
      console.error('DM 로드 실패:', err);
    } finally {
      setIsLoadingDms(false);
    }
  };

  const handleSendDm = async () => {
    if (!dmRecipient.trim() || !dmContent.trim() || isSendingDm) return;

    try {
      setIsSendingDm(true);
      await api.sendIndieNetDM(dmRecipient.trim(), dmContent.trim());
      setShowSendDmDialog(false);
      setDmRecipient('');
      setDmContent('');
      // DM 목록 새로고침
      loadDms();
    } catch (err: any) {
      setError(err.message || 'DM 전송 실패');
    } finally {
      setIsSendingDm(false);
    }
  };

  const handlePost = async () => {
    if (!newPostContent.trim() || isPosting) return;

    const content = newPostContent.trim();

    try {
      setIsPosting(true);
      const result = await api.createIndieNetPost(content);

      // 낙관적 업데이트: 게시 성공 시 로컬 목록에 바로 추가
      const resultAny = result as any;
      if (resultAny.event_id) {
        const newPost: IndieNetPost = {
          id: resultAny.event_id,
          author: resultAny.pubkey || identity?.npub || '',
          content: content + '\n\n#IndieNet',
          created_at: resultAny.created_at || Math.floor(Date.now() / 1000),
          tags: [['t', 'indienet']]
        };

        // 중복 제거하며 맨 앞에 추가
        setPosts(prev => [newPost, ...prev.filter(p => p.id !== newPost.id)]);
      }

      setNewPostContent('');
    } catch (err: any) {
      setError(err.message || '게시 실패');
    } finally {
      setIsPosting(false);
    }
  };

  const copyNpub = () => {
    if (identity?.npub) {
      navigator.clipboard.writeText(identity.npub);
      setCopiedNpub(true);
      setTimeout(() => setCopiedNpub(false), 2000);
    }
  };

  const handleSaveDisplayName = async () => {
    try {
      await api.updateIndieNetDisplayName(newDisplayName);
      setIdentity(prev => prev ? { ...prev, display_name: newDisplayName } : null);
      setEditingName(false);
    } catch (err: any) {
      console.error('이름 변경 실패:', err);
    }
  };

  const handleImportNsec = async () => {
    if (!importNsec.trim()) return;

    try {
      setIsImporting(true);
      setImportError(null);
      const result = await api.importIndieNetNsec(importNsec.trim());
      setIdentity(result.identity);
      setShowImportDialog(false);
      setImportNsec('');
    } catch (err: any) {
      setImportError(err.message || 'ID 가져오기 실패');
    } finally {
      setIsImporting(false);
    }
  };

  const handleResetIdentity = async () => {
    try {
      const result = await api.resetIndieNetIdentity();
      setIdentity(result.identity);
      setShowResetConfirm(false);
    } catch (err: any) {
      console.error('ID 초기화 실패:', err);
    }
  };

  const formatTimestamp = (ts: number) => {
    const date = new Date(ts * 1000);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return '방금 전';
    if (minutes < 60) return `${minutes}분 전`;
    if (hours < 24) return `${hours}시간 전`;
    if (days < 7) return `${days}일 전`;
    return date.toLocaleDateString('ko-KR');
  };

  const shortenPubkey = (pubkey: string) => {
    if (pubkey.startsWith('npub')) {
      return pubkey.substring(0, 12) + '...' + pubkey.substring(pubkey.length - 8);
    }
    return pubkey.substring(0, 8) + '...' + pubkey.substring(pubkey.length - 8);
  };

  // 컨텐츠에서 #IndieNet 태그 제거
  const cleanContent = (content: string) => {
    return content
      .replace(/#IndieNet/gi, '')
      .replace(/\n\n\s*$/g, '')
      .trim();
  };

  // 미리보기용 컨텐츠 (최대 150자)
  const getPreviewContent = (content: string) => {
    const cleaned = cleanContent(content);
    if (cleaned.length <= 150) return cleaned;
    return cleaned.substring(0, 150) + '...';
  };

  return (
    <div className="h-full flex flex-col bg-[#F5F1EB]">
      {/* 헤더 */}
      <div className="h-12 flex items-center justify-between px-4 bg-[#F5F1EB] border-b border-[#E5DFD5] drag">
        <div className="flex items-center gap-3 no-drag">
          <Globe size={24} className="text-[#D97706]" />
          <span className="text-lg font-bold text-[#6B5B4F]">
            IndieNet
          </span>
        </div>
        <div className="flex items-center gap-2 no-drag">
          <button
            onClick={() => activeTab === 'posts' ? loadPosts() : loadDms()}
            disabled={isLoading || isLoadingDms}
            className="p-2 rounded-lg hover:bg-[#EAE4DA] transition-colors text-[#6B5B4F] disabled:opacity-50"
            title="새로고침"
          >
            <RefreshCw size={18} className={(isLoading || isLoadingDms) ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={() => setShowSettings(true)}
            className="p-2 rounded-lg hover:bg-[#EAE4DA] transition-colors text-[#6B5B4F]"
            title="설정"
          >
            <Settings size={18} />
          </button>
        </div>
      </div>

      {/* 탭 */}
      <div className="flex border-b border-[#E5DFD5] bg-white">
        <button
          onClick={() => { setActiveTab('posts'); setSelectedPost(null); }}
          className={`flex-1 py-2 text-sm font-medium transition-colors ${
            activeTab === 'posts'
              ? 'text-[#D97706] border-b-2 border-[#D97706]'
              : 'text-[#6B5B4F] hover:text-[#D97706]'
          }`}
        >
          <div className="flex items-center justify-center gap-2">
            <MessageCircle size={16} />
            게시판
          </div>
        </button>
        <button
          onClick={() => { setActiveTab('dms'); setSelectedDm(null); loadDms(); }}
          className={`flex-1 py-2 text-sm font-medium transition-colors ${
            activeTab === 'dms'
              ? 'text-[#D97706] border-b-2 border-[#D97706]'
              : 'text-[#6B5B4F] hover:text-[#D97706]'
          }`}
        >
          <div className="flex items-center justify-center gap-2">
            <Mail size={16} />
            DM
          </div>
        </button>
      </div>

      {/* 게시판 탭 */}
      {activeTab === 'posts' && (
        <>
          {/* 글쓰기 영역 */}
          <div className="px-4 py-3 border-b border-[#E5DFD5] bg-white">
            <div className="flex gap-2">
              <textarea
                ref={textareaRef}
                value={newPostContent}
                onChange={(e) => setNewPostContent(e.target.value)}
                placeholder="무슨 생각을 하고 계세요?"
                className="flex-1 bg-[#F5F1EB] border border-[#E5DFD5] rounded-lg px-3 py-2 text-sm text-[#3D3D3D] placeholder-[#9CA3AF] focus:outline-none focus:border-[#D97706] resize-none"
                rows={2}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    handlePost();
                  }
                }}
              />
              <button
                onClick={handlePost}
                disabled={!newPostContent.trim() || isPosting}
                className="px-4 py-2 bg-[#D97706] text-white rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[#B45309] transition-colors"
              >
                {isPosting ? (
                  <RefreshCw size={18} className="animate-spin" />
                ) : (
                  <Send size={18} />
                )}
              </button>
            </div>
            <p className="text-xs text-[#9CA3AF] mt-1">Cmd/Ctrl + Enter로 게시</p>
          </div>

          {/* 게시글 목록 / 상세보기 */}
          <div className="flex-1 overflow-y-auto bg-white">
            {error && (
              <div className="m-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">
                {error}
              </div>
            )}

            {/* 상세보기 */}
            {selectedPost ? (
              <div className="h-full flex flex-col">
                {/* 상세보기 헤더 */}
                <div className="px-4 py-3 border-b border-[#E5DFD5] bg-[#F9F7F4]">
                  <button
                    onClick={() => setSelectedPost(null)}
                    className="flex items-center gap-2 text-sm text-[#6B5B4F] hover:text-[#D97706] transition-colors"
                  >
                    <ArrowLeft size={16} />
                    목록으로 돌아가기
                  </button>
                </div>
                {/* 게시글 내용 */}
                <div className="flex-1 overflow-y-auto p-4">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-sm text-[#D97706] font-medium">
                      {shortenPubkey(selectedPost.author)}
                    </span>
                    <span className="text-xs text-[#9CA3AF]">
                      {formatTimestamp(selectedPost.created_at)}
                    </span>
                  </div>
                  <p className="text-sm text-[#3D3D3D] whitespace-pre-wrap break-words leading-relaxed">
                    {cleanContent(selectedPost.content)}
                  </p>
                </div>
              </div>
            ) : (
              /* 목록 보기 */
              <>
                {isLoading && posts.length === 0 ? (
                  <div className="flex items-center justify-center h-32">
                    <RefreshCw size={24} className="animate-spin text-[#D97706]" />
                  </div>
                ) : posts.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-32 text-[#9CA3AF]">
                    <MessageCircle size={32} className="mb-2" />
                    <p>아직 게시글이 없습니다</p>
                    <p className="text-sm">첫 번째 글을 작성해보세요!</p>
                  </div>
                ) : (
                  <div className="divide-y divide-[#E5DFD5]">
                    {posts.map((post) => (
                      <div
                        key={post.id}
                        onClick={() => setSelectedPost(post)}
                        className="px-4 py-3 hover:bg-[#F9F7F4] transition-colors cursor-pointer"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm text-[#D97706] font-medium">
                            {shortenPubkey(post.author)}
                          </span>
                          <span className="text-xs text-[#9CA3AF]">
                            {formatTimestamp(post.created_at)}
                          </span>
                        </div>
                        <p className="text-sm text-[#3D3D3D] line-clamp-2">
                          {getPreviewContent(post.content)}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}

      {/* DM 탭 */}
      {activeTab === 'dms' && (
        <>
          {/* DM 작성 버튼 */}
          <div className="px-4 py-3 border-b border-[#E5DFD5] bg-white">
            <button
              onClick={() => setShowSendDmDialog(true)}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-[#D97706] text-white rounded-lg font-medium hover:bg-[#B45309] transition-colors"
            >
              <Send size={16} />
              새 DM 보내기
            </button>
          </div>

          {/* DM 목록 / 상세보기 */}
          <div className="flex-1 overflow-y-auto bg-white">
            {error && (
              <div className="m-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">
                {error}
              </div>
            )}

            {/* DM 상세보기 */}
            {selectedDm ? (
              <div className="h-full flex flex-col">
                <div className="px-4 py-3 border-b border-[#E5DFD5] bg-[#F9F7F4]">
                  <button
                    onClick={() => setSelectedDm(null)}
                    className="flex items-center gap-2 text-sm text-[#6B5B4F] hover:text-[#D97706] transition-colors"
                  >
                    <ArrowLeft size={16} />
                    목록으로 돌아가기
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto p-4">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-sm text-[#D97706] font-medium">
                      {shortenPubkey(selectedDm.from)}
                    </span>
                    <span className="text-xs text-[#9CA3AF]">
                      {formatTimestamp(selectedDm.created_at)}
                    </span>
                  </div>
                  <p className="text-sm text-[#3D3D3D] whitespace-pre-wrap break-words leading-relaxed">
                    {selectedDm.content}
                  </p>
                  {/* 답장 버튼 */}
                  <button
                    onClick={() => {
                      setDmRecipient(selectedDm.from);
                      setShowSendDmDialog(true);
                    }}
                    className="mt-4 flex items-center gap-2 px-4 py-2 bg-[#F5F1EB] border border-[#E5DFD5] rounded-lg text-sm text-[#6B5B4F] hover:bg-[#EAE4DA] transition-colors"
                  >
                    <Send size={14} />
                    답장하기
                  </button>
                </div>
              </div>
            ) : (
              /* DM 목록 */
              <>
                {isLoadingDms && dms.length === 0 ? (
                  <div className="flex items-center justify-center h-32">
                    <RefreshCw size={24} className="animate-spin text-[#D97706]" />
                  </div>
                ) : dms.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-32 text-[#9CA3AF]">
                    <Mail size={32} className="mb-2" />
                    <p>받은 DM이 없습니다</p>
                    <p className="text-sm">공개 게시글에서 다른 사용자가 DM을 보내면 여기에 표시됩니다</p>
                  </div>
                ) : (
                  <div className="divide-y divide-[#E5DFD5]">
                    {dms.map((dm) => (
                      <div
                        key={dm.id}
                        onClick={() => setSelectedDm(dm)}
                        className="px-4 py-3 hover:bg-[#F9F7F4] transition-colors cursor-pointer"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm text-[#D97706] font-medium">
                            {shortenPubkey(dm.from)}
                          </span>
                          <span className="text-xs text-[#9CA3AF]">
                            {formatTimestamp(dm.created_at)}
                          </span>
                        </div>
                        <p className="text-sm text-[#3D3D3D] line-clamp-2">
                          {dm.content.length > 150 ? dm.content.substring(0, 150) + '...' : dm.content}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}

      {/* 설정 다이얼로그 */}
      {showSettings && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white border border-[#E5DFD5] rounded-xl w-96 max-h-[80vh] overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5DFD5] bg-[#F5F1EB]">
              <h3 className="font-bold text-lg text-[#6B5B4F]">IndieNet 설정</h3>
              <button
                onClick={() => setShowSettings(false)}
                className="p-1 hover:bg-[#EAE4DA] rounded-lg transition-colors text-[#6B5B4F]"
              >
                <X size={18} />
              </button>
            </div>
            <div className="p-4 space-y-4 overflow-y-auto">
              {/* 표시 이름 */}
              <div>
                <label className="block text-sm font-medium text-[#6B5B4F] mb-1">표시 이름</label>
                {editingName ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={newDisplayName}
                      onChange={(e) => setNewDisplayName(e.target.value)}
                      className="flex-1 bg-[#F5F1EB] border border-[#E5DFD5] rounded-lg px-3 py-2 text-sm text-[#3D3D3D] focus:outline-none focus:border-[#D97706]"
                      placeholder="표시할 이름"
                    />
                    <button
                      onClick={handleSaveDisplayName}
                      className="p-2 bg-[#D97706] text-white rounded-lg hover:bg-[#B45309]"
                    >
                      <Save size={16} />
                    </button>
                    <button
                      onClick={() => {
                        setEditingName(false);
                        setNewDisplayName(identity?.display_name || '');
                      }}
                      className="p-2 bg-gray-200 text-gray-600 rounded-lg hover:bg-gray-300"
                    >
                      <X size={16} />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="flex-1 text-sm text-[#3D3D3D]">
                      {identity?.display_name || '(설정되지 않음)'}
                    </span>
                    <button
                      onClick={() => setEditingName(true)}
                      className="p-2 hover:bg-[#EAE4DA] rounded-lg text-[#6B5B4F]"
                    >
                      <Edit2 size={16} />
                    </button>
                  </div>
                )}
              </div>

              {/* 내 ID */}
              <div>
                <label className="block text-sm font-medium text-[#6B5B4F] mb-1">내 ID (npub)</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={identity?.npub || ''}
                    readOnly
                    className="flex-1 bg-[#F5F1EB] border border-[#E5DFD5] rounded-lg px-3 py-2 text-xs text-[#9CA3AF] font-mono"
                  />
                  <button
                    onClick={copyNpub}
                    className="p-2 bg-[#F5F1EB] border border-[#E5DFD5] rounded-lg hover:bg-[#EAE4DA] text-[#6B5B4F]"
                    title="복사"
                  >
                    {copiedNpub ? <Check size={16} className="text-green-500" /> : <Copy size={16} />}
                  </button>
                </div>
                <p className="text-xs text-[#9CA3AF] mt-1">다른 사람에게 공유할 수 있는 공개 ID입니다</p>
              </div>

              {/* 릴레이 목록 */}
              <div>
                <label className="block text-sm font-medium text-[#6B5B4F] mb-1">릴레이 서버</label>
                <div className="space-y-1 max-h-24 overflow-y-auto">
                  {settings?.relays.map((relay, i) => (
                    <div key={i} className="text-xs text-[#6B5B4F] bg-[#F5F1EB] px-2 py-1 rounded">
                      {relay}
                    </div>
                  ))}
                </div>
              </div>

              {/* 자동 새로고침 */}
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-[#6B5B4F]">자동 새로고침</label>
                <span className="text-sm text-[#9CA3AF]">
                  {settings?.auto_refresh ? `${settings.refresh_interval}초` : '꺼짐'}
                </span>
              </div>

              {/* 생성일 */}
              {identity?.created_at && (
                <div className="pt-2 border-t border-[#E5DFD5]">
                  <p className="text-xs text-[#9CA3AF]">
                    ID 생성일: {new Date(identity.created_at).toLocaleDateString('ko-KR')}
                  </p>
                </div>
              )}

              {/* ID 관리 버튼 */}
              <div className="pt-3 border-t border-[#E5DFD5] space-y-2">
                <button
                  onClick={() => {
                    setShowSettings(false);
                    setShowImportDialog(true);
                  }}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-[#F5F1EB] border border-[#E5DFD5] rounded-lg text-sm text-[#6B5B4F] hover:bg-[#EAE4DA] transition-colors"
                >
                  <Key size={16} />
                  기존 Nostr ID 가져오기
                </button>
                <button
                  onClick={() => {
                    setShowSettings(false);
                    setShowResetConfirm(true);
                  }}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600 hover:bg-red-100 transition-colors"
                >
                  <RotateCcw size={16} />
                  새 ID 생성
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ID 가져오기 다이얼로그 */}
      {showImportDialog && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white border border-[#E5DFD5] rounded-xl w-96 overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5DFD5] bg-[#F5F1EB]">
              <h3 className="font-bold text-lg text-[#6B5B4F]">Nostr ID 가져오기</h3>
              <button
                onClick={() => {
                  setShowImportDialog(false);
                  setImportNsec('');
                  setImportError(null);
                }}
                className="p-1 hover:bg-[#EAE4DA] rounded-lg transition-colors text-[#6B5B4F]"
              >
                <X size={18} />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#6B5B4F] mb-1">
                  비밀 키 (nsec)
                </label>
                <input
                  type="password"
                  value={importNsec}
                  onChange={(e) => setImportNsec(e.target.value)}
                  placeholder="nsec1..."
                  className="w-full bg-[#F5F1EB] border border-[#E5DFD5] rounded-lg px-3 py-2 text-sm text-[#3D3D3D] font-mono focus:outline-none focus:border-[#D97706]"
                />
                <p className="text-xs text-[#9CA3AF] mt-1">
                  기존 Nostr 클라이언트에서 사용하던 nsec 키를 입력하세요
                </p>
              </div>

              {importError && (
                <div className="flex items-center gap-2 p-2 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">
                  <AlertTriangle size={16} />
                  {importError}
                </div>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setShowImportDialog(false);
                    setImportNsec('');
                    setImportError(null);
                  }}
                  className="flex-1 px-3 py-2 bg-gray-100 rounded-lg text-sm text-gray-600 hover:bg-gray-200 transition-colors"
                >
                  취소
                </button>
                <button
                  onClick={handleImportNsec}
                  disabled={!importNsec.trim() || isImporting}
                  className="flex-1 px-3 py-2 bg-[#D97706] text-white rounded-lg text-sm font-medium disabled:opacity-50 hover:bg-[#B45309] transition-colors"
                >
                  {isImporting ? '가져오는 중...' : '가져오기'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ID 초기화 확인 다이얼로그 */}
      {showResetConfirm && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white border border-[#E5DFD5] rounded-xl w-80 overflow-hidden shadow-2xl">
            <div className="p-4 space-y-4">
              <div className="flex items-center gap-3 text-red-600">
                <AlertTriangle size={24} />
                <h3 className="font-bold text-lg">새 ID 생성</h3>
              </div>
              <p className="text-sm text-[#3D3D3D]">
                현재 ID를 삭제하고 새로운 ID를 생성합니다.
                <br />
                <span className="text-red-600 font-medium">이 작업은 되돌릴 수 없습니다.</span>
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowResetConfirm(false)}
                  className="flex-1 px-3 py-2 bg-gray-100 rounded-lg text-sm text-gray-600 hover:bg-gray-200 transition-colors"
                >
                  취소
                </button>
                <button
                  onClick={handleResetIdentity}
                  className="flex-1 px-3 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors"
                >
                  생성
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* DM 전송 다이얼로그 */}
      {showSendDmDialog && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white border border-[#E5DFD5] rounded-xl w-96 overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5DFD5] bg-[#F5F1EB]">
              <h3 className="font-bold text-lg text-[#6B5B4F]">DM 보내기</h3>
              <button
                onClick={() => {
                  setShowSendDmDialog(false);
                  setDmRecipient('');
                  setDmContent('');
                }}
                className="p-1 hover:bg-[#EAE4DA] rounded-lg transition-colors text-[#6B5B4F]"
              >
                <X size={18} />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#6B5B4F] mb-1">
                  받는 사람 (npub 또는 hex)
                </label>
                <input
                  type="text"
                  value={dmRecipient}
                  onChange={(e) => setDmRecipient(e.target.value)}
                  placeholder="npub1... 또는 hex 공개키"
                  className="w-full bg-[#F5F1EB] border border-[#E5DFD5] rounded-lg px-3 py-2 text-sm text-[#3D3D3D] font-mono focus:outline-none focus:border-[#D97706]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#6B5B4F] mb-1">
                  메시지
                </label>
                <textarea
                  value={dmContent}
                  onChange={(e) => setDmContent(e.target.value)}
                  placeholder="메시지를 입력하세요..."
                  className="w-full bg-[#F5F1EB] border border-[#E5DFD5] rounded-lg px-3 py-2 text-sm text-[#3D3D3D] focus:outline-none focus:border-[#D97706] resize-none"
                  rows={4}
                />
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setShowSendDmDialog(false);
                    setDmRecipient('');
                    setDmContent('');
                  }}
                  className="flex-1 px-3 py-2 bg-gray-100 rounded-lg text-sm text-gray-600 hover:bg-gray-200 transition-colors"
                >
                  취소
                </button>
                <button
                  onClick={handleSendDm}
                  disabled={!dmRecipient.trim() || !dmContent.trim() || isSendingDm}
                  className="flex-1 px-3 py-2 bg-[#D97706] text-white rounded-lg text-sm font-medium disabled:opacity-50 hover:bg-[#B45309] transition-colors"
                >
                  {isSendingDm ? '전송 중...' : '전송'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
