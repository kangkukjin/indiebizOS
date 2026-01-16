/**
 * ProfileDialog - 시스템 메모 다이얼로그
 */

import { X } from 'lucide-react';

interface ProfileDialogProps {
  show: boolean;
  content: string;
  onContentChange: (content: string) => void;
  onSave: () => void;
  onClose: () => void;
}

export function ProfileDialog({
  show,
  content,
  onContentChange,
  onSave,
  onClose,
}: ProfileDialogProps) {
  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{
          width: 'min(600px, 90vw)',
          height: 'min(500px, 80vh)',
          minWidth: '400px',
          minHeight: '300px',
          resize: 'both',
        }}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 shrink-0">
          <h2 className="text-xl font-bold text-gray-800">시스템 메모</h2>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
          >
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        {/* 내용 */}
        <div className="flex-1 flex flex-col p-6 overflow-hidden">
          <p className="text-sm text-gray-500 mb-4 shrink-0">
            시스템 AI에게 전달할 정보를 입력하세요. 이 정보는 시스템 AI가 참조합니다.
          </p>
          <textarea
            value={content}
            onChange={(e) => onContentChange(e.target.value)}
            placeholder="시스템 AI가 알아야 할 정보를 입력하세요..."
            className="flex-1 px-4 py-3 bg-gray-50 rounded-lg border border-gray-300 focus:border-purple-500 focus:outline-none text-gray-800 resize-none"
          />
        </div>

        {/* 푸터 */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg hover:bg-gray-200 transition-colors text-gray-600"
          >
            취소
          </button>
          <button
            onClick={onSave}
            className="px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors"
          >
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
