/**
 * NoteDialog - 노트 편집 다이얼로그
 */

import { X } from 'lucide-react';
import type { Agent } from '../../../types';

interface NoteDialogProps {
  show: boolean;
  onClose: () => void;
  editingAgent: Agent | null;
  noteContent: string;
  setNoteContent: (content: string) => void;
  onSaveNote: () => void;
}

export function NoteDialog({
  show,
  onClose,
  editingAgent,
  noteContent,
  setNoteContent,
  onSaveNote,
}: NoteDialogProps) {
  if (!show || !editingAgent) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-[500px] overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
          <h2 className="text-xl font-bold text-gray-800">{editingAgent.name} - 영구 메모</h2>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-200 rounded-lg">
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        <div className="p-6">
          <p className="text-sm text-gray-500 mb-4">
            이 메모는 에이전트가 항상 참조하는 영구적인 정보입니다.
          </p>
          <textarea
            value={noteContent}
            onChange={(e) => setNoteContent(e.target.value)}
            placeholder="에이전트에게 항상 기억시킬 내용을 입력하세요..."
            className="w-full px-4 py-3 bg-gray-50 rounded-lg border border-gray-300 focus:border-purple-500 focus:outline-none text-gray-800 resize-none"
            rows={8}
          />
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg hover:bg-gray-200 transition-colors text-gray-600"
          >
            취소
          </button>
          <button
            onClick={onSaveNote}
            className="px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors"
          >
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
