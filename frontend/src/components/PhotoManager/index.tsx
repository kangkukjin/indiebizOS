/**
 * PhotoManager - 사진/동영상 관리 컴포넌트
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Camera, Video, Copy, Grid3x3, Calendar, BarChart2,
  Folder, RefreshCw, Image, Trash2, MapPin
} from 'lucide-react';
import 'leaflet/dist/leaflet.css';

// 타입 및 유틸리티
import type { PhotoManagerProps, Scan, MediaItem, DuplicateGroup, ViewMode } from './types';
import { initLeafletIcons } from './utils';

// 뷰 컴포넌트
import { GalleryView } from './GalleryView';
import { TimelineView } from './TimelineView';
import { DuplicatesView } from './DuplicatesView';
import { StatsView } from './StatsView';
import { MediaDetailModal } from './MediaDetailModal';
import { MapView } from './MapView';
import { TimeMapView } from './TimeMapView';

// Leaflet 아이콘 초기화
initLeafletIcons();

export function PhotoManager({ initialPath }: PhotoManagerProps) {
  const [apiUrl, setApiUrl] = useState<string>('');
  const [scans, setScans] = useState<Scan[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(initialPath || null);
  const [viewMode, setViewMode] = useState<ViewMode>('gallery');
  const [mediaType, setMediaType] = useState<'all' | 'photo' | 'video'>('all');
  const [sortBy, setSortBy] = useState<string>('taken_date');
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState<string>('');

  // Gallery data
  const [galleryItems, setGalleryItems] = useState<MediaItem[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [selectedItemIndex, setSelectedItemIndex] = useState<number | null>(null);
  const [viewerItems, setViewerItems] = useState<MediaItem[]>([]);

  // Duplicates data
  const [duplicates, setDuplicates] = useState<DuplicateGroup[]>([]);
  const [duplicateStats, setDuplicateStats] = useState<{ groups: number; total: number; wasted: number }>({ groups: 0, total: 0, wasted: 0 });

  // Stats data
  const [stats, setStats] = useState<any>(null);

  const getApiUrl = useCallback(async () => {
    try {
      if (window.electron) {
        const port = await window.electron.getApiPort();
        return `http://127.0.0.1:${port}`;
      }
      return 'http://127.0.0.1:8765';
    } catch {
      return 'http://127.0.0.1:8765';
    }
  }, []);

  // API URL 초기화
  useEffect(() => {
    getApiUrl().then(setApiUrl);
  }, [getApiUrl]);

  // 스캔 목록 로드
  const loadScans = useCallback(async () => {
    const url = await getApiUrl();
    try {
      const res = await fetch(`${url}/photo/scans`);
      const data = await res.json();
      if (data.success) {
        setScans(data.scans || []);

        if (initialPath && data.scans.some((s: Scan) => s.root_path === initialPath)) {
          setSelectedPath(initialPath);
        }
      }
    } catch (error) {
      console.error('Failed to load scans:', error);
    }
  }, [getApiUrl, initialPath]);

  useEffect(() => {
    loadScans();
  }, [loadScans]);

  // 갤러리 로드
  const loadGallery = useCallback(async () => {
    if (!selectedPath) return;

    const url = await getApiUrl();
    try {
      const typeParam = mediaType !== 'all' ? `&media_type=${mediaType}` : '';
      const res = await fetch(`${url}/photo/gallery?path=${encodeURIComponent(selectedPath)}&page=${currentPage}&limit=50&sort_by=${sortBy}${typeParam}`);
      const data = await res.json();

      if (data.success) {
        setGalleryItems(data.items || []);
        setTotalItems(data.total || 0);
      }
    } catch (error) {
      console.error('Failed to load gallery:', error);
    }
  }, [selectedPath, currentPage, sortBy, mediaType, getApiUrl]);

  // 중복 파일 로드
  const loadDuplicates = useCallback(async () => {
    if (!selectedPath) return;

    const url = await getApiUrl();
    try {
      const res = await fetch(`${url}/photo/duplicates?path=${encodeURIComponent(selectedPath)}`);
      const data = await res.json();

      if (data.success) {
        setDuplicates(data.groups || []);
        setDuplicateStats({
          groups: data.total_groups || 0,
          total: data.total_duplicates || 0,
          wasted: data.total_wasted_mb || 0
        });
      }
    } catch (error) {
      console.error('Failed to load duplicates:', error);
    }
  }, [selectedPath, getApiUrl]);

  // 통계 로드
  const loadStats = useCallback(async () => {
    if (!selectedPath) return;

    const url = await getApiUrl();
    try {
      const res = await fetch(`${url}/photo/stats?path=${encodeURIComponent(selectedPath)}`);
      const data = await res.json();

      if (data.success) {
        setStats(data);
      }
    } catch (error) {
      console.error('Failed to load stats:', error);
    }
  }, [selectedPath, getApiUrl]);

  // 뷰 모드 변경 시 데이터 로드
  useEffect(() => {
    if (!selectedPath) return;

    switch (viewMode) {
      case 'gallery':
        loadGallery();
        break;
      case 'duplicates':
        loadDuplicates();
        break;
      case 'stats':
        loadStats();
        break;
    }
  }, [viewMode, selectedPath, loadGallery, loadDuplicates, loadStats]);

  // 페이지 변경 시 갤러리 리로드
  useEffect(() => {
    if (viewMode === 'gallery' && selectedPath) {
      loadGallery();
    }
  }, [currentPage, sortBy, mediaType, viewMode, selectedPath, loadGallery]);

  // 폴더 선택
  const handleSelectFolder = async () => {
    if (!window.electron) return;

    const folderPath = await window.electron.selectFolder();
    if (folderPath) {
      handleScan(folderPath);
    }
  };

  // 스캔 실행
  const handleScan = async (path: string) => {
    const url = await getApiUrl();
    setIsScanning(true);
    setScanProgress('스캔 준비 중...');

    try {
      const previewRes = await fetch(`${url}/photo/scan/preview?path=${encodeURIComponent(path)}`);
      const preview = await previewRes.json();

      if (preview.success) {
        setScanProgress(`${preview.total_files}개 파일 스캔 중... (예상 ${Math.ceil(preview.estimated_seconds)}초)`);
      }

      const res = await fetch(`${url}/photo/scan?path=${encodeURIComponent(path)}`, {
        method: 'POST'
      });
      const data = await res.json();

      if (data.success) {
        setScanProgress(`완료! 사진 ${data.photo_count}개, 동영상 ${data.video_count}개`);
        await loadScans();
        setSelectedPath(path);
        setViewMode('gallery');
      } else {
        setScanProgress(`오류: ${data.error}`);
      }
    } catch (error) {
      setScanProgress('스캔 실패');
      console.error('Scan failed:', error);
    } finally {
      setTimeout(() => {
        setIsScanning(false);
        setScanProgress('');
      }, 2000);
    }
  };

  // 스캔 선택
  const handleSelectScan = (scan: Scan) => {
    setSelectedPath(scan.root_path);
    setCurrentPage(1);
    setViewMode('gallery');
  };

  // 스캔 삭제
  const handleDeleteScan = async (scan: Scan, e: React.MouseEvent) => {
    e.stopPropagation();

    const confirmed = window.confirm(
      `"${scan.name}" 스캔 데이터를 삭제하시겠습니까?\n\n` +
      `사진 ${scan.photo_count}개, 동영상 ${scan.video_count}개의 인덱스가 삭제됩니다.\n` +
      `(실제 파일은 삭제되지 않습니다)`
    );

    if (!confirmed) return;

    const url = await getApiUrl();
    try {
      const res = await fetch(`${url}/photo/scan/${scan.id}`, {
        method: 'DELETE'
      });
      const data = await res.json();

      if (data.success) {
        if (selectedPath === scan.root_path) {
          setSelectedPath(null);
          setGalleryItems([]);
          setTotalItems(0);
        }
        await loadScans();
      } else {
        alert(`삭제 실패: ${data.error}`);
      }
    } catch (error) {
      console.error('Failed to delete scan:', error);
      alert('스캔 삭제에 실패했습니다.');
    }
  };

  // 미디어 아이템 선택
  const handleSelectItem = (_item: MediaItem, index: number, items: MediaItem[]) => {
    setViewerItems(items);
    setSelectedItemIndex(index);
  };

  // 뷰어에서 이전/다음 이동
  const handlePrevItem = () => {
    if (selectedItemIndex !== null && selectedItemIndex > 0) {
      setSelectedItemIndex(selectedItemIndex - 1);
    }
  };

  const handleNextItem = () => {
    if (selectedItemIndex !== null && selectedItemIndex < viewerItems.length - 1) {
      setSelectedItemIndex(selectedItemIndex + 1);
    }
  };

  const handleCloseViewer = () => {
    setSelectedItemIndex(null);
    setViewerItems([]);
  };

  const selectedScan = scans.find(s => s.root_path === selectedPath);

  return (
    <div className="h-full flex flex-col bg-[#FAFAF8]">
      {/* 헤더 */}
      <div
        className="flex items-center justify-between px-4 py-3 bg-[#FAF9F7] border-b border-[#E8E4DC]"
        style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}
      >
        <div className="flex items-center gap-3 pl-16">
          <Camera className="text-[#8B7355] text-xl" />
          <h1 className="text-lg font-semibold text-[#5C5347]">Photo Manager</h1>
        </div>

        <div
          className="flex items-center gap-2"
          style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}
        >
          <button
            onClick={handleSelectFolder}
            className="flex items-center gap-2 px-3 py-1.5 bg-[#8B7355] text-white rounded-lg hover:bg-[#7A6349] transition-colors text-sm"
          >
            <Folder size={14} />
            새 폴더 스캔
          </button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* 사이드바 */}
        <div className="w-64 border-r border-[#E8E4DC] bg-[#FAF9F7] overflow-y-auto">
          <div className="p-3">
            <h3 className="text-xs font-semibold text-[#8B7355] mb-2 px-2">스캔된 폴더</h3>

            {scans.length === 0 ? (
              <div className="text-sm text-[#9B8B7A] px-2 py-4 text-center">
                스캔된 폴더가 없습니다
              </div>
            ) : (
              <div className="space-y-1">
                {scans.map((scan) => (
                  <div
                    key={scan.id}
                    onClick={() => handleSelectScan(scan)}
                    className={`w-full text-left p-2 rounded-lg transition-colors cursor-pointer group ${
                      selectedPath === scan.root_path
                        ? 'bg-[#E8E4DC] text-[#5C5347]'
                        : 'hover:bg-[#F0EDE8] text-[#6B5D4D]'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Folder className="flex-shrink-0 text-[#8B7355]" />
                      <span className="text-sm font-medium truncate flex-1">{scan.name}</span>
                      <button
                        onClick={(e) => handleDeleteScan(scan, e)}
                        className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-100 rounded transition-all"
                        title="스캔 데이터 삭제"
                      >
                        <Trash2 size={12} className="text-red-500" />
                      </button>
                    </div>
                    <div className="flex items-center gap-3 mt-1 ml-6 text-xs text-[#9B8B7A]">
                      <span className="flex items-center gap-1">
                        <Image size={10} /> {scan.photo_count}
                      </span>
                      <span className="flex items-center gap-1">
                        <Video size={10} /> {scan.video_count}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 메인 영역 */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {selectedPath && selectedScan ? (
            <>
              {/* 뷰 모드 탭 */}
              <div className="flex items-center gap-1 px-4 py-2 bg-[#FAF9F7] border-b border-[#E8E4DC]">
                <button
                  onClick={() => setViewMode('gallery')}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    viewMode === 'gallery' ? 'bg-[#8B7355] text-white' : 'text-[#6B5D4D] hover:bg-[#E8E4DC]'
                  }`}
                >
                  <Grid3x3 size={14} />
                  갤러리
                </button>
                <button
                  onClick={() => setViewMode('timeline')}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    viewMode === 'timeline' ? 'bg-[#8B7355] text-white' : 'text-[#6B5D4D] hover:bg-[#E8E4DC]'
                  }`}
                >
                  <Calendar size={14} />
                  타임라인
                </button>
                <button
                  onClick={() => setViewMode('duplicates')}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    viewMode === 'duplicates' ? 'bg-[#8B7355] text-white' : 'text-[#6B5D4D] hover:bg-[#E8E4DC]'
                  }`}
                >
                  <Copy size={14} />
                  중복
                </button>
                <button
                  onClick={() => setViewMode('stats')}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    viewMode === 'stats' ? 'bg-[#8B7355] text-white' : 'text-[#6B5D4D] hover:bg-[#E8E4DC]'
                  }`}
                >
                  <BarChart2 size={14} />
                  통계
                </button>
                <button
                  onClick={() => setViewMode('map')}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    viewMode === 'map' ? 'bg-[#8B7355] text-white' : 'text-[#6B5D4D] hover:bg-[#E8E4DC]'
                  }`}
                >
                  <MapPin size={14} />
                  지도
                </button>
                <button
                  onClick={() => setViewMode('timemap')}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    viewMode === 'timemap' ? 'bg-[#8B7355] text-white' : 'text-[#6B5D4D] hover:bg-[#E8E4DC]'
                  }`}
                >
                  <Calendar size={14} />
                  타임지도
                </button>

                <div className="flex-1" />

                {viewMode === 'gallery' && (
                  <>
                    <select
                      value={mediaType}
                      onChange={(e) => setMediaType(e.target.value as any)}
                      className="text-sm px-2 py-1 border border-[#E8E4DC] rounded-lg bg-white text-[#5C5347]"
                    >
                      <option value="all">전체</option>
                      <option value="photo">사진만</option>
                      <option value="video">동영상만</option>
                    </select>
                    <select
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value)}
                      className="text-sm px-2 py-1 border border-[#E8E4DC] rounded-lg bg-white text-[#5C5347]"
                    >
                      <option value="taken_date">촬영일</option>
                      <option value="mtime">수정일</option>
                      <option value="size">크기</option>
                      <option value="filename">이름</option>
                    </select>
                  </>
                )}

                <button
                  onClick={() => handleScan(selectedPath)}
                  disabled={isScanning}
                  className="flex items-center gap-1 px-2 py-1.5 text-sm text-[#6B5D4D] hover:bg-[#E8E4DC] rounded-lg"
                >
                  <RefreshCw size={14} className={isScanning ? 'animate-spin' : ''} />
                  재스캔
                </button>
              </div>

              {/* 스캔 진행 상태 */}
              {isScanning && scanProgress && (
                <div className="px-4 py-2 bg-[#FFF8E1] border-b border-[#FFE082] text-sm text-[#5C5347]">
                  {scanProgress}
                </div>
              )}

              {/* 콘텐츠 영역 */}
              <div className="flex-1 overflow-auto p-4">
                {viewMode === 'gallery' && (
                  <GalleryView
                    items={galleryItems}
                    totalItems={totalItems}
                    currentPage={currentPage}
                    onPageChange={setCurrentPage}
                    onSelectItem={handleSelectItem}
                  />
                )}

                {viewMode === 'timeline' && (
                  <TimelineView
                    apiUrl={apiUrl}
                    selectedPath={selectedPath}
                    onSelectItem={handleSelectItem}
                  />
                )}

                {viewMode === 'duplicates' && (
                  <DuplicatesView
                    groups={duplicates}
                    stats={duplicateStats}
                  />
                )}

                {viewMode === 'stats' && (
                  <StatsView data={stats} />
                )}

                {viewMode === 'map' && (
                  <MapView
                    apiUrl={apiUrl}
                    selectedPath={selectedPath}
                    onSelectItem={handleSelectItem}
                  />
                )}

                {viewMode === 'timemap' && (
                  <TimeMapView
                    apiUrl={apiUrl}
                    selectedPath={selectedPath}
                    onSelectItem={handleSelectItem}
                  />
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Camera className="mx-auto text-6xl text-[#D4C8B8] mb-4" />
                <h2 className="text-lg font-medium text-[#6B5D4D] mb-2">사진 관리를 시작하세요</h2>
                <p className="text-sm text-[#9B8B7A] mb-4">
                  왼쪽에서 스캔된 폴더를 선택하거나<br />
                  새 폴더를 스캔하세요
                </p>
                <button
                  onClick={handleSelectFolder}
                  className="px-4 py-2 bg-[#8B7355] text-white rounded-lg hover:bg-[#7A6349] transition-colors"
                >
                  폴더 선택
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 미디어 상세 모달 */}
      {selectedItemIndex !== null && viewerItems.length > 0 && (
        <MediaDetailModal
          item={viewerItems[selectedItemIndex]}
          currentIndex={selectedItemIndex}
          totalCount={viewerItems.length}
          onPrev={handlePrevItem}
          onNext={handleNextItem}
          onClose={handleCloseViewer}
        />
      )}
    </div>
  );
}
