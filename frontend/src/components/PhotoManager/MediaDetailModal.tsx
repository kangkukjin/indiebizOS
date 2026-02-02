/**
 * MediaDetailModal - 미디어 상세 모달 (풀스크린, 이전/다음 네비게이션)
 */

import { useState, useEffect } from 'react';
import { Image, X, ChevronLeft, ChevronRight } from 'lucide-react';
import { BROWSER_PLAYABLE_VIDEO } from './types';

interface MediaDetailModalProps {
  item: any;
  currentIndex: number;
  totalCount: number;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
}

export function MediaDetailModal({
  item,
  currentIndex,
  totalCount,
  onPrev,
  onNext,
  onClose
}: MediaDetailModalProps) {
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
