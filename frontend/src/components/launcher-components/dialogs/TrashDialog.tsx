/**
 * TrashDialog - 휴지통 다이얼로그
 */

import { X, Trash2, Trash, Folder, RotateCcw, MessageCircle } from 'lucide-react';
import type { TrashItems } from '../types';

interface TrashDialogProps {
  show: boolean;
  trashItems: TrashItems;
  onRestore: (itemId: string, itemType: 'project' | 'switch' | 'chat_room') => void;
  onEmpty: () => void;
  onClose: () => void;
}

export function TrashDialog({
  show,
  trashItems,
  onRestore,
  onEmpty,
  onClose,
}: TrashDialogProps) {
  if (!show) return null;

  const chatRooms = trashItems.chat_rooms || [];
  const totalCount = trashItems.projects.length + trashItems.switches.length + chatRooms.length;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{
          width: 'min(500px, 90vw)',
          height: 'min(400px, 70vh)',
          minWidth: '300px',
          minHeight: '200px',
        }}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 shrink-0">
          <div className="flex items-center gap-3">
            <Trash2 size={24} className="text-gray-600" />
            <h2 className="text-xl font-bold text-gray-800">휴지통</h2>
            <span className="text-sm text-gray-500">({totalCount}개 항목)</span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
          >
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        {/* 내용 */}
        <div className="flex-1 overflow-auto p-4">
          {totalCount === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-400">
              <Trash2 size={48} className="mb-2" />
              <p>휴지통이 비어 있습니다</p>
            </div>
          ) : (
            <div className="space-y-2">
              {/* 프로젝트/폴더 */}
              {trashItems.projects.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">
                      {item.type === 'folder' ? <Folder size={24} className="text-amber-500" /> : '📁'}
                    </span>
                    <div>
                      <p className="font-medium text-gray-800">{item.name}</p>
                      <p className="text-xs text-gray-500">
                        {item.type === 'folder' ? '폴더' : '프로젝트'}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => onRestore(item.id, 'project')}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm text-blue-600 hover:bg-blue-50 rounded-lg"
                  >
                    <RotateCcw size={14} />
                    복원
                  </button>
                </div>
              ))}
              {/* 스위치 */}
              {trashItems.switches.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{item.icon || '⚡'}</span>
                    <div>
                      <p className="font-medium text-gray-800">{item.name}</p>
                      <p className="text-xs text-gray-500">스위치</p>
                    </div>
                  </div>
                  <button
                    onClick={() => onRestore(item.id, 'switch')}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm text-blue-600 hover:bg-blue-50 rounded-lg"
                  >
                    <RotateCcw size={14} />
                    복원
                  </button>
                </div>
              ))}
              {/* 채팅방 */}
              {chatRooms.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100"
                >
                  <div className="flex items-center gap-3">
                    <MessageCircle size={24} className="text-purple-500" />
                    <div>
                      <p className="font-medium text-gray-800">{item.name}</p>
                      <p className="text-xs text-gray-500">다중채팅방</p>
                    </div>
                  </div>
                  <button
                    onClick={() => onRestore(item.id, 'chat_room')}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm text-blue-600 hover:bg-blue-50 rounded-lg"
                  >
                    <RotateCcw size={14} />
                    복원
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 푸터 */}
        <div className="flex justify-between gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50 shrink-0">
          <button
            onClick={onEmpty}
            disabled={totalCount === 0}
            className="px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <Trash size={16} />
            휴지통 비우기
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 transition-colors text-gray-700"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
