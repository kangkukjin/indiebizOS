/**
 * GalleryView - 갤러리 뷰 컴포넌트
 */

import { Check, Video } from 'lucide-react';
import type { MediaItem } from './types';
import { dragOutMedia, thumbUrl } from './utils';

interface GalleryViewProps {
  items: MediaItem[];
  totalItems: number;
  currentPage: number;
  onPageChange: (page: number) => void;
  onSelectItem: (item: MediaItem, index: number, items: MediaItem[]) => void;
  /** 저장하려고 고른 것들(경로 집합). 없으면 선택 UI 자체를 안 그린다. */
  picked?: Set<string>;
  /** 체크 클릭 — shift 면 직전 클릭부터 여기까지 범위 선택. */
  onPick?: (item: MediaItem, index: number, shift: boolean) => void;
}

export function GalleryView({
  items,
  totalItems,
  currentPage,
  onPageChange,
  onSelectItem,
  picked,
  onPick
}: GalleryViewProps) {
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
        {items.map((item, index) => {
          const isPicked = !!picked?.has(item.path);
          return (
          <div
            key={item.id}
            onClick={() => onSelectItem(item, index, items)}
            draggable
            onDragStart={(e) => dragOutMedia(e, item)}
            title="끌어서 바탕화면·폴더에 저장"
            className={`aspect-square bg-[#F0EDE8] rounded-lg overflow-hidden cursor-pointer transition-all relative group ${
              isPicked ? 'ring-2 ring-[#8B7355]' : 'hover:ring-2 hover:ring-[#8B7355]'
            }`}
          >
            {item.media_type === 'photo' ? (
              <img
                src={thumbUrl(item, 200)}
                alt={item.filename}
                className="w-full h-full object-cover"
                loading="lazy"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = 'none';
                }}
              />
            ) : (
              <div className="w-full h-full relative bg-[#2D2D2D]">
                <img
                  src={thumbUrl(item, 200)}
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

            {/* 고르기 — 클릭은 상세 보기라, 선택은 별도 과녁(좌상단 체크)으로 가른다.
                shift 클릭이 "몇 번부터 몇 번까지"에 해당한다. */}
            {onPick && (
              <button
                onClick={(e) => { e.stopPropagation(); onPick(item, index, e.shiftKey); }}
                title={isPicked ? '선택 해제' : '선택 (shift = 여기까지 한꺼번에)'}
                className={`absolute top-1.5 left-1.5 w-6 h-6 rounded-md flex items-center justify-center border transition-all ${
                  isPicked
                    ? 'bg-[#8B7355] border-[#8B7355] text-white'
                    : 'bg-black/30 border-white/70 text-transparent opacity-0 group-hover:opacity-100'
                }`}
              >
                <Check size={14} />
              </button>
            )}
          </div>
          );
        })}
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
