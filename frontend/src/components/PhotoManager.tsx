/**
 * PhotoManager - 사진/동영상 관리 컴포넌트
 */

import { useState, useEffect, useCallback } from 'react';
import { Camera, Video, Copy, Grid3x3, Calendar, BarChart2, Folder, RefreshCw, ChevronRight, Image, Trash2, MapPin, ZoomIn, ZoomOut, RotateCcw, ChevronLeft, X } from 'lucide-react';
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, BarChart, Bar
} from 'recharts';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Leaflet 기본 마커 아이콘 설정
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

// 클러스터 아이콘 생성 함수
const createClusterCustomIcon = (cluster: any) => {
  const count = cluster.getChildCount();
  let size = 'small';
  let dimension = 30;

  if (count >= 100) {
    size = 'large';
    dimension = 50;
  } else if (count >= 10) {
    size = 'medium';
    dimension = 40;
  }

  return L.divIcon({
    html: `<div style="
      background-color: #8B7355;
      color: white;
      border-radius: 50%;
      width: ${dimension}px;
      height: ${dimension}px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: bold;
      font-size: ${size === 'large' ? '14px' : size === 'medium' ? '12px' : '10px'};
      border: 3px solid white;
      box-shadow: 0 2px 5px rgba(0,0,0,0.3);
    ">${count}</div>`,
    className: 'custom-cluster-icon',
    iconSize: L.point(dimension, dimension),
  });
};

interface PhotoManagerProps {
  initialPath?: string | null;
}

interface Scan {
  id: number;
  name: string;
  root_path: string;
  last_scan: string;
  photo_count: number;
  video_count: number;
  total_size_mb: number;
}

interface MediaItem {
  id: number;
  path: string;
  filename: string;
  extension: string;
  size_mb: number;
  mtime: string;
  media_type: string;
  width: number | null;
  height: number | null;
  taken_date: string | null;
  camera: string | null;
}

interface DuplicateGroup {
  hash: string;
  count: number;
  wasted_mb: number;
  files: MediaItem[];
}

type ViewMode = 'gallery' | 'timeline' | 'duplicates' | 'stats' | 'map';

interface GpsPhoto {
  id: number;
  path: string;
  filename: string;
  lat: number;
  lon: number;
  taken_date: string | null;
  mtime: string | null;
}

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

        // 초기 경로가 있고 스캔 목록에 있으면 선택
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
      // timeline은 TimelineView 컴포넌트 내부에서 자체 로드
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
      // 미리보기로 예상 시간 확인
      const previewRes = await fetch(`${url}/photo/scan/preview?path=${encodeURIComponent(path)}`);
      const preview = await previewRes.json();

      if (preview.success) {
        setScanProgress(`${preview.total_files}개 파일 스캔 중... (예상 ${Math.ceil(preview.estimated_seconds)}초)`);
      }

      // 스캔 실행
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
        // 현재 선택된 스캔이 삭제된 경우 선택 해제
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

  // 미디어 아이템 선택 - 갤러리에서 인덱스와 목록을 받음
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
      {/* 헤더 - 드래그 영역 */}
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
        {/* 사이드바 - 스캔 목록 */}
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
                    viewMode === 'gallery'
                      ? 'bg-[#8B7355] text-white'
                      : 'text-[#6B5D4D] hover:bg-[#E8E4DC]'
                  }`}
                >
                  <Grid3x3 size={14} />
                  갤러리
                </button>
                <button
                  onClick={() => setViewMode('timeline')}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    viewMode === 'timeline'
                      ? 'bg-[#8B7355] text-white'
                      : 'text-[#6B5D4D] hover:bg-[#E8E4DC]'
                  }`}
                >
                  <Calendar size={14} />
                  타임라인
                </button>
                <button
                  onClick={() => setViewMode('duplicates')}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    viewMode === 'duplicates'
                      ? 'bg-[#8B7355] text-white'
                      : 'text-[#6B5D4D] hover:bg-[#E8E4DC]'
                  }`}
                >
                  <Copy size={14} />
                  중복
                </button>
                <button
                  onClick={() => setViewMode('stats')}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    viewMode === 'stats'
                      ? 'bg-[#8B7355] text-white'
                      : 'text-[#6B5D4D] hover:bg-[#E8E4DC]'
                  }`}
                >
                  <BarChart2 size={14} />
                  통계
                </button>
                <button
                  onClick={() => setViewMode('map')}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    viewMode === 'map'
                      ? 'bg-[#8B7355] text-white'
                      : 'text-[#6B5D4D] hover:bg-[#E8E4DC]'
                  }`}
                >
                  <MapPin size={14} />
                  지도
                </button>

                <div className="flex-1" />

                {/* 필터 (갤러리 모드에서만) */}
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

// 갤러리 뷰
function GalleryView({
  items,
  totalItems,
  currentPage,
  onPageChange,
  onSelectItem
}: {
  items: MediaItem[];
  totalItems: number;
  currentPage: number;
  onPageChange: (page: number) => void;
  onSelectItem: (item: MediaItem, index: number, items: MediaItem[]) => void;
}) {
  const totalPages = Math.ceil(totalItems / 50);

  if (items.length === 0) {
    return (
      <div className="text-center py-12 text-[#9B8B7A]">
        미디어 파일이 없습니다
      </div>
    );
  }

  return (
    <div>
      <div className="grid grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-2">
        {items.map((item, index) => (
          <div
            key={item.id}
            onClick={() => onSelectItem(item, index, items)}
            className="aspect-square bg-[#F0EDE8] rounded-lg overflow-hidden cursor-pointer hover:ring-2 hover:ring-[#8B7355] transition-all relative group"
          >
            {item.media_type === 'photo' ? (
              <img
                src={`http://127.0.0.1:8765/photo/thumbnail?path=${encodeURIComponent(item.path)}&size=200`}
                alt={item.filename}
                className="w-full h-full object-cover"
                loading="lazy"
                onError={(e) => {
                  // 썸네일 로드 실패 시 플레이스홀더 표시
                  (e.target as HTMLImageElement).style.display = 'none';
                }}
              />
            ) : (
              <div className="w-full h-full relative bg-[#2D2D2D]">
                <img
                  src={`http://127.0.0.1:8765/photo/video-thumbnail?path=${encodeURIComponent(item.path)}&size=200`}
                  alt={item.filename}
                  className="w-full h-full object-cover"
                  loading="lazy"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                  }}
                />
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-10 h-10 rounded-full bg-black/50 flex items-center justify-center">
                    <Video className="text-white text-lg" />
                  </div>
                </div>
              </div>
            )}
            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent p-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <p className="text-white text-xs truncate">{item.filename}</p>
            </div>
          </div>
        ))}
      </div>

      {/* 페이지네이션 */}
      {totalPages > 1 && (
        <div className="flex flex-col items-center gap-3 mt-6">
          {/* 슬라이더 (10페이지 이상일 때) */}
          {totalPages >= 10 && (
            <div className="w-full max-w-md flex items-center gap-3">
              <span className="text-xs text-[#9B8B7A] w-8">1</span>
              <input
                type="range"
                min={1}
                max={totalPages}
                value={currentPage}
                onChange={(e) => onPageChange(Number(e.target.value))}
                className="flex-1 h-2 bg-[#E8E4DC] rounded-lg appearance-none cursor-pointer accent-[#8B7355]"
              />
              <span className="text-xs text-[#9B8B7A] w-8 text-right">{totalPages}</span>
            </div>
          )}

          {/* 버튼 및 페이지 입력 */}
          <div className="flex items-center gap-2">
            {/* 처음으로 */}
            <button
              onClick={() => onPageChange(1)}
              disabled={currentPage === 1}
              className="px-2 py-1 text-sm rounded-lg bg-[#E8E4DC] text-[#5C5347] disabled:opacity-50"
              title="처음으로"
            >
              ⏮
            </button>
            <button
              onClick={() => onPageChange(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
              className="px-3 py-1 text-sm rounded-lg bg-[#E8E4DC] text-[#5C5347] disabled:opacity-50"
            >
              이전
            </button>

            {/* 페이지 직접 입력 */}
            <div className="flex items-center gap-1">
              <input
                type="number"
                min={1}
                max={totalPages}
                value={currentPage}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  if (val >= 1 && val <= totalPages) {
                    onPageChange(val);
                  }
                }}
                className="w-16 px-2 py-1 text-sm text-center rounded-lg border border-[#D4C4B0] bg-white text-[#5C5347]"
              />
              <span className="text-sm text-[#6B5D4D]">/ {totalPages}</span>
            </div>

            <button
              onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
              className="px-3 py-1 text-sm rounded-lg bg-[#E8E4DC] text-[#5C5347] disabled:opacity-50"
            >
              다음
            </button>
            {/* 끝으로 */}
            <button
              onClick={() => onPageChange(totalPages)}
              disabled={currentPage === totalPages}
              className="px-2 py-1 text-sm rounded-lg bg-[#E8E4DC] text-[#5C5347] disabled:opacity-50"
              title="끝으로"
            >
              ⏭
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// 타임라인 뷰 (줌 가능)
function TimelineView({
  apiUrl,
  selectedPath,
  onSelectItem
}: {
  apiUrl: string;
  selectedPath: string;
  onSelectItem: (item: any, index: number, items: any[]) => void;
}) {
  const [timelineData, setTimelineData] = useState<any>(null);
  const [timelineStartDate, setTimelineStartDate] = useState<string>('');
  const [timelineEndDate, setTimelineEndDate] = useState<string>('');
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(0);
  const [zoomHistory, setZoomHistory] = useState<Array<{start: string, end: string}>>([]);

  // 타임라인 데이터 로드
  const loadTimelineZoom = useCallback(async (startDate?: string, endDate?: string) => {
    if (!selectedPath || !apiUrl) return;

    setTimelineLoading(true);
    try {
      let endpoint = `${apiUrl}/photo/timeline-zoom?path=${encodeURIComponent(selectedPath)}`;
      if (startDate) endpoint += `&start_date=${startDate}`;
      if (endDate) endpoint += `&end_date=${endDate}`;

      const res = await fetch(endpoint);
      const result = await res.json();

      if (result.success) {
        setTimelineData(result);
        setCurrentPage(0); // 새 데이터 로드시 페이지 리셋
      }
    } catch (err) {
      console.error('타임라인 로드 실패:', err);
    } finally {
      setTimelineLoading(false);
    }
  }, [apiUrl, selectedPath]);

  // 초기 로드
  useEffect(() => {
    loadTimelineZoom();
  }, [loadTimelineZoom]);

  // 타임라인 범위 변경 핸들러
  const handleTimelineRangeChange = () => {
    loadTimelineZoom(timelineStartDate || undefined, timelineEndDate || undefined);
  };

  // 타임라인 리셋
  const resetTimeline = () => {
    setTimelineStartDate('');
    setTimelineEndDate('');
    setZoomHistory([]);
    loadTimelineZoom();
  };

  // 한 단계 줌아웃 (뒤로가기)
  const zoomOut = () => {
    if (zoomHistory.length === 0) {
      // 히스토리가 없으면 전체 보기
      resetTimeline();
      return;
    }
    const newHistory = [...zoomHistory];
    const prev = newHistory.pop();
    setZoomHistory(newHistory);
    setTimelineStartDate(prev?.start || '');
    setTimelineEndDate(prev?.end || '');
    loadTimelineZoom(prev?.start || undefined, prev?.end || undefined);
  };

  // 막대 클릭으로 줌인
  const handleBarClick = (data: any) => {
    const period = data?.period || data?.payload?.period;
    if (!period) return;

    // 현재 범위를 히스토리에 저장 (줌인 전)
    setZoomHistory(prev => [...prev, { start: timelineStartDate, end: timelineEndDate }]);

    let startDate: string;
    let endDate: string;

    if (period.length === 4) {
      // 년 → 해당 년도 전체
      startDate = `${period}-01-01`;
      endDate = `${period}-12-31`;
    } else if (period.length === 7) {
      // 월 → 해당 월 전체
      const [year, month] = period.split('-');
      const lastDay = new Date(parseInt(year), parseInt(month), 0).getDate();
      startDate = `${period}-01`;
      endDate = `${period}-${String(lastDay).padStart(2, '0')}`;
    } else if (period.length === 10) {
      // 일 → 해당 일 하루만
      startDate = period;
      endDate = period;
    } else {
      return;
    }

    setTimelineStartDate(startDate);
    setTimelineEndDate(endDate);
    loadTimelineZoom(startDate, endDate);
  };

  // 파일 열기
  const openWithDefaultApp = async (filePath: string) => {
    try {
      await fetch(`${apiUrl}/photo/open-external?path=${encodeURIComponent(filePath)}`, {
        method: 'POST'
      });
    } catch (err) {
      console.error('파일 열기 실패:', err);
    }
  };

  if (timelineLoading && !timelineData) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCw className="w-8 h-8 text-[#8B7355] animate-spin" />
      </div>
    );
  }

  if (!timelineData) {
    return <div className="text-center text-[#9B8B7A]">데이터 없음</div>;
  }

  const { time_range, stats, density, density_label, files, show_files } = timelineData;

  return (
    <div className="flex flex-col h-full">
      {/* 상단 컨트롤 */}
      <div className="flex items-center gap-4 mb-4 p-3 bg-[#F5F3F0] rounded-lg">
        {/* 시간 범위 정보 */}
        <div className="text-xs text-[#9B8B7A]">
          전체: {time_range?.min_date?.slice(0, 10)} ~ {time_range?.max_date?.slice(0, 10)}
          <span className="ml-2">({time_range?.total_files?.toLocaleString()}개)</span>
        </div>

        <div className="flex-1" />

        {/* 날짜 범위 선택 */}
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={timelineStartDate}
            onChange={(e) => setTimelineStartDate(e.target.value)}
            className="px-2 py-1 text-xs rounded border border-[#E8E4DC] bg-white"
          />
          <span className="text-[#9B8B7A]">~</span>
          <input
            type="date"
            value={timelineEndDate}
            onChange={(e) => setTimelineEndDate(e.target.value)}
            className="px-2 py-1 text-xs rounded border border-[#E8E4DC] bg-white"
          />
          <button
            onClick={handleTimelineRangeChange}
            className="p-1.5 rounded bg-[#8B7355] text-white hover:bg-[#7A6349]"
            title="적용"
          >
            <ZoomIn size={14} />
          </button>
          <button
            onClick={zoomOut}
            disabled={zoomHistory.length === 0 && !timelineStartDate && !timelineEndDate}
            className="p-1.5 rounded bg-[#6B9B8B] text-white hover:bg-[#5B8B7B] disabled:opacity-50 disabled:cursor-not-allowed"
            title={`한 단계 뒤로 (${zoomHistory.length})`}
          >
            <ZoomOut size={14} />
          </button>
          <button
            onClick={resetTimeline}
            className="p-1.5 rounded bg-[#9B8B7A] text-white hover:bg-[#8B7B6A]"
            title="초기화"
          >
            <RotateCcw size={14} />
          </button>
        </div>
      </div>

      {/* 현재 선택 범위 통계 */}
      {stats && (
        <div className="flex items-center gap-4 mb-4 px-2">
          <div className="text-sm">
            <span className="text-[#9B8B7A]">선택 범위:</span>
            <span className="ml-2 font-medium text-[#5C5347]">
              {stats.range_start?.slice(0, 10)} ~ {stats.range_end?.slice(0, 10)}
            </span>
          </div>
          <div className="text-sm flex items-center gap-1">
            <Camera size={12} className="text-[#8B7355]" />
            <span className="font-medium text-[#8B7355]">{stats.photo_count?.toLocaleString()}</span>
          </div>
          <div className="text-sm flex items-center gap-1">
            <Video size={12} className="text-[#6B9B8B]" />
            <span className="font-medium text-[#6B9B8B]">{stats.video_count?.toLocaleString()}</span>
          </div>
          <div className="text-sm">
            <span className="text-[#9B8B7A]">용량:</span>
            <span className="ml-1 font-medium text-[#5C5347]">{stats.total_size_mb?.toLocaleString()} MB</span>
          </div>
          <div className="text-xs text-[#B0A090]">
            ({density_label === 'year' ? '년' : density_label === 'month' ? '월' : '일'} 단위)
          </div>
        </div>
      )}

      {/* 밀도 차트 (컬럼 전체 클릭 가능) */}
      <div className="mb-4">
        <div className="text-xs text-[#9B8B7A] mb-2 px-2">
          차트를 클릭하면 해당 기간으로 줌인됩니다
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart
            data={density.map((d: any) => ({ ...d, _clickArea: 1 }))}
            margin={{ top: 10, right: 30, left: 20, bottom: 40 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#E8E4DC" />
            <XAxis
              dataKey="period"
              angle={-45}
              textAnchor="end"
              tick={{ fontSize: 10 }}
              interval="preserveStartEnd"
            />
            <YAxis yAxisId="left" tick={{ fontSize: 10 }} />
            <YAxis yAxisId="click" hide domain={[0, 1]} />
            <Tooltip
              contentStyle={{ backgroundColor: '#FAFAF8', border: '1px solid #E8E4DC' }}
              formatter={(value, name) => {
                if (name === '_clickArea' || value === undefined) return null;
                const v = Number(value);
                if (name === 'photos') return [`${v.toLocaleString()} 장`, '사진'];
                if (name === 'videos') return [`${v.toLocaleString()} 개`, '동영상'];
                return [v.toLocaleString(), String(name)];
              }}
              filterNull={true}
            />
            {/* 투명한 클릭 영역 - 전체 높이 */}
            <Bar
              yAxisId="click"
              dataKey="_clickArea"
              fill="transparent"
              cursor="pointer"
              onClick={handleBarClick}
            />
            {/* 실제 데이터 막대 */}
            <Bar yAxisId="left" dataKey="photos" fill="#8B7355" name="photos" stackId="stack" />
            <Bar yAxisId="left" dataKey="videos" fill="#6B9B8B" name="videos" stackId="stack" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* 썸네일 갤러리 (줌인 상태에서만) */}
      {show_files && files && files.length > 0 && (
        <div className="flex-1 overflow-hidden flex flex-col">
          <div className="text-xs text-[#9B8B7A] mb-2 px-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ZoomIn size={12} />
              미디어 파일 ({files.length}개) - 클릭: 미리보기 / 더블클릭: 파일 열기
            </div>
            {files.length > 50 && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
                  disabled={currentPage === 0}
                  className="px-2 py-1 bg-[#F0EDE8] rounded disabled:opacity-50 hover:bg-[#E8E4DC]"
                >
                  ◀
                </button>
                <span>{currentPage + 1} / {Math.ceil(files.length / 50)}</span>
                <button
                  onClick={() => setCurrentPage(Math.min(Math.ceil(files.length / 50) - 1, currentPage + 1))}
                  disabled={currentPage >= Math.ceil(files.length / 50) - 1}
                  className="px-2 py-1 bg-[#F0EDE8] rounded disabled:opacity-50 hover:bg-[#E8E4DC]"
                >
                  ▶
                </button>
              </div>
            )}
          </div>
          <div className="overflow-y-auto flex-1 border border-[#E8E4DC] rounded-lg p-2">
            <div className="grid grid-cols-5 lg:grid-cols-8 xl:grid-cols-10 gap-2">
              {files.slice(currentPage * 50, (currentPage + 1) * 50).map((file: any, idx: number) => {
                const pageFiles = files.slice(currentPage * 50, (currentPage + 1) * 50);
                return (
                <div
                  key={idx}
                  className="aspect-square bg-[#F0EDE8] rounded-lg overflow-hidden cursor-pointer relative group hover:ring-2 hover:ring-[#8B7355] transition-all"
                  onClick={() => onSelectItem(file, idx, pageFiles)}
                  onDoubleClick={() => openWithDefaultApp(file.path)}
                  title={`${file.filename}\n${(file.taken_date || file.mtime)?.slice(0, 16).replace('T', ' ')}\n클릭: 미리보기 / 더블클릭: 파일 열기`}
                >
                  {file.media_type === 'photo' ? (
                    <img
                      src={`http://127.0.0.1:8765/photo/thumbnail?path=${encodeURIComponent(file.path)}&size=150`}
                      alt={file.filename}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center bg-[#2D2A26]">
                      <Video className="w-8 h-8 text-white opacity-70" />
                    </div>
                  )}
                  {/* 타입 아이콘 오버레이 */}
                  <div className="absolute top-1 right-1 p-1 bg-black/50 rounded text-white">
                    {file.media_type === 'photo' ? (
                      <Camera size={10} />
                    ) : (
                      <Video size={10} />
                    )}
                  </div>
                  {/* 파일명 오버레이 (호버시) */}
                  <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <div className="text-[10px] text-white truncate">{file.filename}</div>
                    <div className="text-[8px] text-white/70">{(file.taken_date || file.mtime)?.slice(0, 10)}</div>
                  </div>
                </div>
              );})}
            </div>
          </div>
        </div>
      )}

      {/* 파일이 너무 많을 때 안내 */}
      {!show_files && stats?.file_count > 0 && (
        <div className="flex-1 flex items-center justify-center text-[#9B8B7A]">
          <div className="text-center">
            <ZoomIn className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>파일이 {stats.file_count.toLocaleString()}개 있습니다.</p>
            <p className="text-xs mt-1">더 좁은 기간을 선택하면 개별 파일을 볼 수 있습니다.</p>
          </div>
        </div>
      )}
    </div>
  );
}

// 중복 파일 뷰
function DuplicatesView({
  groups,
  stats
}: {
  groups: DuplicateGroup[];
  stats: { groups: number; total: number; wasted: number };
}) {
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      {/* 요약 */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-2xl font-bold text-[#5C5347]">{stats.groups}</div>
          <div className="text-sm text-[#9B8B7A]">중복 그룹</div>
        </div>
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-2xl font-bold text-[#5C5347]">{stats.total}</div>
          <div className="text-sm text-[#9B8B7A]">중복 파일</div>
        </div>
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-2xl font-bold text-[#D97706]">{stats.wasted.toLocaleString()} MB</div>
          <div className="text-sm text-[#9B8B7A]">낭비된 용량</div>
        </div>
      </div>

      {/* 중복 그룹 목록 */}
      {groups.length === 0 ? (
        <div className="text-center py-12 text-[#9B8B7A]">
          중복 파일이 없습니다
        </div>
      ) : (
        <div className="space-y-2">
          {groups.map((group) => (
            <div key={group.hash} className="bg-white rounded-lg border border-[#E8E4DC] overflow-hidden">
              <button
                onClick={() => setExpandedGroup(expandedGroup === group.hash ? null : group.hash)}
                className="w-full flex items-center justify-between p-3 hover:bg-[#FAF9F7] transition-colors"
              >
                <div className="flex items-center gap-3">
                  <Copy className="text-[#8B7355]" />
                  <span className="text-sm font-medium text-[#5C5347]">
                    {group.count}개 동일 파일
                  </span>
                  <span className="text-xs text-[#9B8B7A]">
                    ({group.hash})
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-[#D97706]">
                    {group.wasted_mb.toLocaleString()} MB 낭비
                  </span>
                  <ChevronRight
                    className={`text-[#9B8B7A] transition-transform ${expandedGroup === group.hash ? 'rotate-90' : ''}`}
                  />
                </div>
              </button>

              {expandedGroup === group.hash && (
                <div className="border-t border-[#E8E4DC] p-3 bg-[#FAF9F7]">
                  <div className="space-y-2">
                    {group.files.map((file, idx) => (
                      <div
                        key={file.id}
                        className={`flex items-center gap-3 p-2 rounded-lg ${idx === 0 ? 'bg-green-50 border border-green-200' : 'bg-white border border-[#E8E4DC]'}`}
                      >
                        <span className="text-xs text-[#9B8B7A] w-6">
                          {idx === 0 ? '원본' : `#${idx + 1}`}
                        </span>
                        <span className="flex-1 text-sm text-[#5C5347] truncate">
                          {file.path}
                        </span>
                        <span className="text-xs text-[#9B8B7A]">
                          {file.size_mb} MB
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// 통계 뷰
function StatsView({ data }: { data: any }) {
  if (!data) {
    return (
      <div className="text-center py-12 text-[#9B8B7A]">
        통계 데이터를 불러오는 중...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 요약 */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-2xl font-bold text-[#5C5347]">{(data.photo_count || 0).toLocaleString()}</div>
          <div className="text-sm text-[#9B8B7A]">사진</div>
        </div>
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-2xl font-bold text-[#5C5347]">{(data.video_count || 0).toLocaleString()}</div>
          <div className="text-sm text-[#9B8B7A]">동영상</div>
        </div>
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-2xl font-bold text-[#5C5347]">{(data.total_size_mb || 0).toLocaleString()} MB</div>
          <div className="text-sm text-[#9B8B7A]">총 용량</div>
        </div>
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-sm font-medium text-[#5C5347]">{data.last_scan ? new Date(data.last_scan).toLocaleDateString() : '-'}</div>
          <div className="text-sm text-[#9B8B7A]">마지막 스캔</div>
        </div>
      </div>

      {/* 확장자별 통계 */}
      {data.extensions && data.extensions.length > 0 && (
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <h3 className="text-sm font-semibold text-[#5C5347] mb-3">확장자별 분포</h3>
          <div className="space-y-2">
            {data.extensions.map((ext: any, idx: number) => (
              <div key={idx} className="flex items-center gap-3">
                <span className="w-16 text-sm font-mono text-[#6B5D4D]">.{ext.extension}</span>
                <div className="flex-1 h-4 bg-[#F0EDE8] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-[#8B7355] rounded-full"
                    style={{ width: `${Math.min(100, (ext.count / (data.photo_count + data.video_count)) * 100)}%` }}
                  />
                </div>
                <span className="w-16 text-right text-sm text-[#9B8B7A]">{ext.count}개</span>
                <span className="w-20 text-right text-sm text-[#9B8B7A]">{ext.size_mb} MB</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 카메라별 통계 */}
      {data.cameras && data.cameras.length > 0 && (
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <h3 className="text-sm font-semibold text-[#5C5347] mb-3">카메라별 분포</h3>
          <div className="grid grid-cols-2 gap-2">
            {data.cameras.map((cam: any, idx: number) => (
              <div key={idx} className="flex items-center justify-between p-2 bg-[#FAF9F7] rounded-lg">
                <span className="text-sm text-[#5C5347]">{cam.camera}</span>
                <span className="text-sm text-[#9B8B7A]">{cam.count}개</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// 브라우저에서 재생 가능한 동영상 확장자
const BROWSER_PLAYABLE_VIDEO = ['mp4', 'webm', 'ogg', 'm4v', 'mov'];

// 미디어 상세 모달 (풀스크린, 이전/다음 네비게이션)
function MediaDetailModal({
  item,
  currentIndex,
  totalCount,
  onPrev,
  onNext,
  onClose
}: {
  item: any;
  currentIndex: number;
  totalCount: number;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
}) {
  const [showInfo, setShowInfo] = useState(false);

  const canPlayInBrowser = item.media_type === 'video' &&
    BROWSER_PLAYABLE_VIDEO.includes(item.extension?.toLowerCase());

  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < totalCount - 1;

  const openInExternalPlayer = async () => {
    try {
      await fetch(`http://127.0.0.1:8765/photo/open-external?path=${encodeURIComponent(item.path)}`, {
        method: 'POST'
      });
    } catch (e) {
      console.error('외부 플레이어 열기 실패:', e);
    }
  };

  // 키보드 이벤트 핸들러
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowLeft':
          if (hasPrev) onPrev();
          break;
        case 'ArrowRight':
          if (hasNext) onNext();
          break;
        case 'Escape':
          onClose();
          break;
        case 'i':
        case 'I':
          setShowInfo(prev => !prev);
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [hasPrev, hasNext, onPrev, onNext, onClose]);

  return (
    <div
      className="fixed inset-0 bg-black z-[9999] flex flex-col"
      onClick={onClose}
    >
      {/* 상단 바 */}
      <div
        className="absolute top-0 left-0 right-0 h-14 bg-gradient-to-b from-black/70 to-transparent z-10 flex items-center px-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex-1 text-white text-sm truncate pr-4">
          {item.filename}
        </div>
        <div className="flex items-center gap-2 text-white/80 text-sm">
          <span>{currentIndex + 1} / {totalCount}</span>
          <button
            onClick={() => setShowInfo(!showInfo)}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors ml-2"
            title="정보 보기 (I)"
          >
            <Image size={18} />
          </button>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
            title="닫기 (ESC)"
          >
            <X size={20} />
          </button>
        </div>
      </div>

      {/* 이전 버튼 */}
      {hasPrev && (
        <button
          onClick={(e) => { e.stopPropagation(); onPrev(); }}
          className="absolute left-4 top-1/2 -translate-y-1/2 z-10 p-3 bg-black/50 hover:bg-black/70 rounded-full text-white transition-colors"
          title="이전 (←)"
        >
          <ChevronLeft size={32} />
        </button>
      )}

      {/* 다음 버튼 */}
      {hasNext && (
        <button
          onClick={(e) => { e.stopPropagation(); onNext(); }}
          className="absolute right-4 top-1/2 -translate-y-1/2 z-10 p-3 bg-black/50 hover:bg-black/70 rounded-full text-white transition-colors"
          title="다음 (→)"
        >
          <ChevronRight size={32} />
        </button>
      )}

      {/* 미디어 콘텐츠 (풀스크린) */}
      <div
        className="flex-1 flex items-center justify-center p-4"
        onClick={(e) => e.stopPropagation()}
      >
        {item.media_type === 'photo' ? (
          <img
            src={`http://127.0.0.1:8765/photo/image?path=${encodeURIComponent(item.path)}`}
            alt={item.filename}
            className="max-h-full max-w-full object-contain"
            style={{ maxHeight: 'calc(100vh - 80px)' }}
          />
        ) : canPlayInBrowser ? (
          <video
            key={item.path}
            src={`http://127.0.0.1:8765/photo/video?path=${encodeURIComponent(item.path)}`}
            controls
            autoPlay
            className="max-h-full max-w-full"
            style={{ maxHeight: 'calc(100vh - 80px)' }}
          >
            동영상을 재생할 수 없습니다
          </video>
        ) : (
          <div className="text-center text-white">
            <img
              src={`http://127.0.0.1:8765/photo/video-thumbnail?path=${encodeURIComponent(item.path)}&size=600`}
              alt={item.filename}
              className="max-h-[60vh] max-w-full object-contain mb-4 rounded"
            />
            <p className="text-gray-400 mb-4">이 형식(.{item.extension})은 브라우저에서 재생할 수 없습니다</p>
            <button
              onClick={openInExternalPlayer}
              className="px-6 py-2 bg-[#8B7355] text-white rounded-lg hover:bg-[#7A6349] transition-colors"
            >
              외부 플레이어로 열기
            </button>
          </div>
        )}
      </div>

      {/* 하단 정보 패널 (토글) */}
      {showInfo && (
        <div
          className="absolute bottom-0 left-0 right-0 bg-black/90 text-white p-4 max-h-[40vh] overflow-y-auto"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="max-w-3xl mx-auto">
            <h3 className="font-semibold mb-3">{item.filename}</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div className="col-span-2 md:col-span-4">
                <span className="text-gray-400">경로:</span>
                <p className="text-gray-200 break-all">{item.path}</p>
              </div>
              {item.size_mb && (
                <div>
                  <span className="text-gray-400">크기:</span>
                  <p className="text-gray-200">{item.size_mb} MB</p>
                </div>
              )}
              {item.mtime && (
                <div>
                  <span className="text-gray-400">파일 날짜:</span>
                  <p className="text-gray-200">{new Date(item.mtime).toLocaleString()}</p>
                </div>
              )}
              {item.width && item.height && (
                <div>
                  <span className="text-gray-400">해상도:</span>
                  <p className="text-gray-200">{item.width} x {item.height}</p>
                </div>
              )}
              {item.taken_date && (
                <div>
                  <span className="text-gray-400">촬영일:</span>
                  <p className="text-gray-200">{new Date(item.taken_date).toLocaleString()}</p>
                </div>
              )}
              {(item.camera_make || item.camera_model) && (
                <div>
                  <span className="text-gray-400">카메라:</span>
                  <p className="text-gray-200">{item.camera_make} {item.camera_model}</p>
                </div>
              )}
              {item.gps_lat && item.gps_lon && (
                <div>
                  <span className="text-gray-400">위치:</span>
                  <p className="text-gray-200">{item.gps_lat}, {item.gps_lon}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 하단 안내 */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 text-white/50 text-xs">
        ← → 이전/다음 | ESC 닫기 | I 정보
      </div>
    </div>
  );
}

// 지도 뷰
function MapView({
  apiUrl,
  selectedPath,
  onSelectItem
}: {
  apiUrl: string;
  selectedPath: string | null;
  onSelectItem: (item: any, index: number, items: any[]) => void;
}) {
  const [gpsPhotos, setGpsPhotos] = useState<GpsPhoto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!apiUrl || !selectedPath) return;

    const fetchGpsPhotos = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${apiUrl}/photo/gps-photos?path=${encodeURIComponent(selectedPath)}`);
        const data = await res.json();
        if (data.success) {
          setGpsPhotos(data.items);
        } else {
          setError(data.error || '데이터를 불러올 수 없습니다');
        }
      } catch (e) {
        setError('서버 연결 실패');
      } finally {
        setLoading(false);
      }
    };

    fetchGpsPhotos();
  }, [apiUrl, selectedPath]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-[#9B8B7A]">GPS 사진 로딩 중...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-red-500">{error}</div>
      </div>
    );
  }

  if (gpsPhotos.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <MapPin className="mx-auto text-5xl text-[#D4C8B8] mb-3" />
          <p className="text-[#9B8B7A]">위치 정보가 있는 사진이 없습니다</p>
        </div>
      </div>
    );
  }

  // 지도 중심 계산 (모든 사진의 평균 위치)
  const avgLat = gpsPhotos.reduce((sum, p) => sum + p.lat, 0) / gpsPhotos.length;
  const avgLon = gpsPhotos.reduce((sum, p) => sum + p.lon, 0) / gpsPhotos.length;

  return (
    <div className="flex-1 flex flex-col h-full">
      <div className="px-4 py-2 bg-[#F5F3F0] border-b border-[#E8E4DC] text-sm text-[#6B5D4D] flex-shrink-0">
        위치 정보가 있는 사진: {gpsPhotos.length}장
      </div>
      <div className="flex-1 relative">
        <MapContainer
          center={[avgLat, avgLon]}
          zoom={5}
          style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <MarkerClusterGroup
            chunkedLoading
            iconCreateFunction={createClusterCustomIcon}
            maxClusterRadius={80}
            spiderfyOnMaxZoom={true}
            showCoverageOnHover={false}
          >
            {gpsPhotos.map((photo) => (
              <Marker key={photo.id} position={[photo.lat, photo.lon]}>
                <Popup>
                  <div className="w-48">
                    <img
                      src={`${apiUrl}/photo/thumbnail?path=${encodeURIComponent(photo.path)}&size=150`}
                      alt={photo.filename}
                      className="w-full h-32 object-cover rounded mb-2 cursor-pointer"
                      onClick={() => {
                        const idx = gpsPhotos.findIndex(p => p.id === photo.id);
                        const items = gpsPhotos.map(p => ({
                          id: p.id,
                          path: p.path,
                          filename: p.filename,
                          media_type: 'photo',
                          gps_lat: p.lat,
                          gps_lon: p.lon,
                          taken_date: p.taken_date,
                          mtime: p.mtime
                        }));
                        onSelectItem(items[idx], idx, items);
                      }}
                    />
                    <p className="text-xs font-medium truncate">{photo.filename}</p>
                    {photo.taken_date && (
                      <p className="text-xs text-gray-500">
                        {new Date(photo.taken_date).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                </Popup>
              </Marker>
            ))}
          </MarkerClusterGroup>
        </MapContainer>
      </div>
    </div>
  );
}

