/**
 * DraggableTrash - 드래그 가능한 휴지통 컴포넌트
 */

import { useState, useEffect, useRef } from 'react';
import { Trash2 } from 'lucide-react';
import type { DraggableTrashProps } from './types';

export function DraggableTrash({
  trashRef,
  trashHover,
  position,
  onPositionChange,
  onDoubleClick,
  onContextMenu,
  trashCount,
}: DraggableTrashProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [pos, setPos] = useState(position);
  const dragOffset = useRef({ x: 0, y: 0 });
  const iconRef = useRef<HTMLDivElement>(null);

  // position이 -1이면 우하단 기본 위치 사용
  const useDefaultPosition = position.x === -1 && position.y === -1;

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;

    e.preventDefault();
    setIsDragging(true);

    const rect = iconRef.current?.getBoundingClientRect();
    if (rect) {
      dragOffset.current = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      };
      // 기본 위치였다면 현재 위치로 초기화
      if (useDefaultPosition) {
        const parent = iconRef.current?.parentElement;
        if (parent) {
          const parentRect = parent.getBoundingClientRect();
          setPos({
            x: rect.left - parentRect.left,
            y: rect.top - parentRect.top,
          });
        }
      }
    }
  };

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const parent = iconRef.current?.parentElement;
      if (!parent) return;

      const parentRect = parent.getBoundingClientRect();
      const newX = e.clientX - parentRect.left - dragOffset.current.x;
      const newY = e.clientY - parentRect.top - dragOffset.current.y;

      const maxX = parentRect.width - 100;
      const maxY = parentRect.height - 100;

      setPos({
        x: Math.max(0, Math.min(newX, maxX)),
        y: Math.max(0, Math.min(newY, maxY)),
      });
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      onPositionChange(Math.round(pos.x), Math.round(pos.y));
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, pos, onPositionChange]);

  // ref 병합
  const setRef = (el: HTMLDivElement | null) => {
    (iconRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
    if (trashRef && 'current' in trashRef) {
      (trashRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
    }
  };

  const style: React.CSSProperties = useDefaultPosition && !isDragging
    ? { right: 30, bottom: 30 }
    : { left: pos.x, top: pos.y };

  return (
    <div
      ref={setRef}
      className={`absolute flex flex-col items-center gap-2 p-3 rounded-xl transition-all no-select ${
        trashHover
          ? 'bg-[#FECACA] scale-110'
          : 'hover:bg-[#EAE4DA]'
      } ${isDragging ? 'z-50' : ''}`}
      style={{
        ...style,
        cursor: isDragging ? 'grabbing' : 'grab',
      }}
      onMouseDown={handleMouseDown}
      onDoubleClick={onDoubleClick}
      onContextMenu={onContextMenu}
    >
      <div
        className={`w-14 h-14 rounded-xl flex items-center justify-center transition-all shadow-sm relative ${
          trashHover
            ? 'bg-[#EF4444] text-white'
            : 'bg-[#E5DFD5] text-[#6B5B4F]'
        }`}
      >
        <Trash2 size={32} className={trashHover ? 'animate-pulse' : ''} />
        {trashCount > 0 && (
          <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs w-5 h-5 rounded-full flex items-center justify-center font-bold">
            {trashCount > 9 ? '9+' : trashCount}
          </span>
        )}
      </div>
      <span className="text-xs text-center text-[#6B5B4F]">휴지통</span>
    </div>
  );
}
