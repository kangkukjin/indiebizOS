/**
 * DraggableIcon - 드래그 가능한 데스크탑 아이콘 컴포넌트
 */

import { useState, useEffect, useRef } from 'react';
import type { DraggableIconProps } from './types';

export function DraggableIcon({
  icon,
  label,
  position,
  onDoubleClick,
  onPositionChange,
  onDragStart,
  onDragEnd,
  onDragMove,
  onDropOnTrash,
  onDropOnFolder,
  trashHover,
  isSwitch = false,
  isFolder = false,
  isMultiChat = false,
  isFolderHovered = false,
  folderRef,
  hoveringFolderId,
  onContextMenu,
  onSelect,
  isSelected: externalIsSelected,
  isRenaming = false,
  onFinishRename,
  onCancelRename,
}: DraggableIconProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [pos, setPos] = useState({ x: position[0], y: position[1] });
  const [isSelected, setIsSelected] = useState(false);
  const [renameValue, setRenameValue] = useState(label);
  const dragOffset = useRef({ x: 0, y: 0 });
  const iconRef = useRef<HTMLDivElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const lastMousePos = useRef({ x: 0, y: 0 });

  // 외부에서 전달된 선택 상태 사용
  const finalIsSelected = externalIsSelected !== undefined ? externalIsSelected : isSelected;

  // 이름 변경 모드 시작 시 입력 필드에 포커스
  useEffect(() => {
    if (isRenaming && renameInputRef.current) {
      setRenameValue(label);
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [isRenaming, label]);

  const handleRenameKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      onFinishRename?.(renameValue);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onCancelRename?.();
    }
  };

  const handleRenameBlur = () => {
    onFinishRename?.(renameValue);
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;

    e.preventDefault();
    setIsDragging(true);
    setIsSelected(true);
    onSelect?.();
    onDragStart();

    const rect = iconRef.current?.getBoundingClientRect();
    if (rect) {
      dragOffset.current = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      };
    }
  };

  const handleRightClick = (e: React.MouseEvent) => {
    onSelect?.();
    onContextMenu?.(e);
  };

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const parent = iconRef.current?.parentElement;
      if (!parent) return;

      lastMousePos.current = { x: e.clientX, y: e.clientY };

      const parentRect = parent.getBoundingClientRect();
      const newX = e.clientX - parentRect.left - dragOffset.current.x;
      const newY = e.clientY - parentRect.top - dragOffset.current.y;

      const maxX = parentRect.width - 100;
      const maxY = parentRect.height - 100;

      setPos({
        x: Math.max(0, Math.min(newX, maxX)),
        y: Math.max(0, Math.min(newY, maxY)),
      });

      onDragMove(e.clientX, e.clientY);
    };

    const handleMouseUp = () => {
      setIsDragging(false);

      const isOnTrash = onDragMove(lastMousePos.current.x, lastMousePos.current.y);
      if (isOnTrash) {
        onDropOnTrash();
      } else if (hoveringFolderId && onDropOnFolder) {
        // 폴더 위에 드롭
        onDropOnFolder(hoveringFolderId);
      } else {
        onPositionChange(Math.round(pos.x), Math.round(pos.y));
      }

      onDragEnd();
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, pos, onPositionChange, onDragEnd, onDragMove, onDropOnTrash, hoveringFolderId, onDropOnFolder]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (iconRef.current && !iconRef.current.contains(e.target as Node)) {
        setIsSelected(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // folderRef 설정을 위한 콜백
  const setRef = (el: HTMLDivElement | null) => {
    (iconRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
    if (folderRef) {
      folderRef(el);
    }
  };

  return (
    <div
      ref={setRef}
      className={`absolute flex flex-col items-center gap-1 p-2 rounded-xl cursor-pointer transition-all no-select ${
        finalIsSelected ? 'bg-[#E5DFD5]' : 'hover:bg-[#EAE4DA]'
      } ${isDragging ? 'z-50' : ''} ${isDragging && trashHover ? 'opacity-50 scale-90' : ''} ${
        isFolderHovered ? 'bg-[#BBF7D0] scale-110' : ''
      }`}
      style={{
        left: pos.x,
        top: pos.y,
        cursor: isDragging ? 'grabbing' : 'grab',
      }}
      onMouseDown={handleMouseDown}
      onDoubleClick={onDoubleClick}
      onContextMenu={handleRightClick}
    >
      <div
        className={`w-14 h-14 rounded-xl flex items-center justify-center text-2xl shadow-sm transition-all ${
          isSwitch
            ? 'bg-[#D97706] text-white'
            : isFolder
              ? 'bg-[#F59E0B] text-white'
              : isMultiChat
                ? 'bg-[#8B5CF6] text-white'
                : 'bg-[#3B82F6] text-white'
        } ${finalIsSelected ? 'ring-2 ring-[#D97706] ring-offset-2 ring-offset-[#F5F1EB]' : ''} ${
          isFolderHovered ? 'ring-4 ring-[#22C55E] ring-offset-2 ring-offset-[#F5F1EB]' : ''
        }`}
      >
        {typeof icon === 'string' ? icon : icon}
      </div>
      {isRenaming ? (
        <input
          ref={renameInputRef}
          type="text"
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onKeyDown={handleRenameKeyDown}
          onBlur={handleRenameBlur}
          onClick={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
          className="text-xs text-center w-20 px-1 py-0.5 bg-white border border-blue-500 rounded outline-none text-[#4A4035] font-medium"
        />
      ) : (
        <span className="text-xs text-center max-w-16 truncate text-[#4A4035] font-medium">{label}</span>
      )}
    </div>
  );
}
