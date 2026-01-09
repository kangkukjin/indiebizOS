/**
 * ContextMenu - 컨텍스트 메뉴 컴포넌트
 */

import { Plus, FolderPlus, Pencil, Copy, Clipboard, Folder, Trash, Grid3X3 } from 'lucide-react';
import type { ContextMenuState, ClipboardItem } from './types';

interface ContextMenuProps {
  contextMenu: ContextMenuState | null;
  clipboard: ClipboardItem | null;
  onClose: () => void;
  onRename: (id: string, type: 'project' | 'switch', name: string) => void;
  onCopy: (id: string, type: 'project' | 'switch') => void;
  onPaste: () => void;
  onNewProject: () => void;
  onNewFolder: () => void;
  onOpenTrash: () => void;
  onEmptyTrash: () => void;
  onArrangeIcons: () => void;
  getItemName: (id: string, type: 'project' | 'switch') => string;
}

export function ContextMenu({
  contextMenu,
  clipboard,
  onClose,
  onRename,
  onCopy,
  onPaste,
  onNewProject,
  onNewFolder,
  onOpenTrash,
  onEmptyTrash,
  onArrangeIcons,
  getItemName,
}: ContextMenuProps) {
  if (!contextMenu) return null;

  const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;

  return (
    <div
      className="fixed bg-white rounded-lg shadow-xl border border-gray-200 py-1 z-50 min-w-[180px]"
      style={{ left: contextMenu.x, top: contextMenu.y }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* 휴지통 우클릭한 경우 */}
      {contextMenu.itemId === '__trash__' && (
        <>
          <button
            onClick={() => {
              onOpenTrash();
              onClose();
            }}
            className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-3"
          >
            <Folder size={16} className="text-gray-600" />
            휴지통 열기
          </button>
          <button
            onClick={() => {
              onEmptyTrash();
              onClose();
            }}
            className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-3"
          >
            <Trash size={16} />
            휴지통 비우기
          </button>
        </>
      )}
      {/* 아이템 위에서 우클릭한 경우 */}
      {contextMenu.itemId && contextMenu.itemType && contextMenu.itemId !== '__trash__' && (
        <>
          <button
            onClick={() => {
              const currentName = getItemName(contextMenu.itemId!, contextMenu.itemType!);
              if (currentName) {
                onRename(contextMenu.itemId!, contextMenu.itemType!, currentName);
              }
              onClose();
            }}
            className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-3"
          >
            <Pencil size={16} className="text-orange-600" />
            이름 변경
            <span className="ml-auto text-xs text-gray-400">F2</span>
          </button>
          <button
            onClick={() => {
              onCopy(contextMenu.itemId!, contextMenu.itemType!);
              onClose();
            }}
            className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-3"
          >
            <Copy size={16} className="text-blue-600" />
            복사
            <span className="ml-auto text-xs text-gray-400">
              {isMac ? '⌘C' : 'Ctrl+C'}
            </span>
          </button>
          <div className="border-t border-gray-100 my-1" />
        </>
      )}
      {/* 붙여넣기 (클립보드에 뭔가 있을 때) */}
      {clipboard && (
        <>
          <button
            onClick={() => {
              onPaste();
              onClose();
            }}
            className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-3"
          >
            <Clipboard size={16} className="text-green-600" />
            붙여넣기
            <span className="ml-auto text-xs text-gray-400">
              {isMac ? '⌘V' : 'Ctrl+V'}
            </span>
          </button>
          <div className="border-t border-gray-100 my-1" />
        </>
      )}
      <button
        onClick={() => {
          onNewProject();
          onClose();
        }}
        className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-3"
      >
        <Plus size={16} className="text-green-600" />
        새 프로젝트
      </button>
      <button
        onClick={() => {
          onNewFolder();
          onClose();
        }}
        className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-3"
      >
        <FolderPlus size={16} className="text-blue-600" />
        새 폴더
      </button>
      <div className="border-t border-gray-100 my-1" />
      <button
        onClick={() => {
          onArrangeIcons();
          onClose();
        }}
        className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-3"
      >
        <Grid3X3 size={16} className="text-purple-600" />
        아이콘 정렬
      </button>
    </div>
  );
}
