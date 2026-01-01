/**
 * TaskEditDialog - 작업 편집 다이얼로그
 */

import type { TaskForm, SchedulerAction } from '../types';

interface TaskEditDialogProps {
  show: boolean;
  isEditing: boolean;
  form: TaskForm;
  actions: SchedulerAction[];
  onFormChange: (form: TaskForm) => void;
  onSave: () => void;
  onClose: () => void;
}

export function TaskEditDialog({
  show,
  isEditing,
  form,
  actions,
  onFormChange,
  onSave,
  onClose,
}: TaskEditDialogProps) {
  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-[60]">
      <div className="bg-white rounded-xl shadow-2xl w-[480px] overflow-hidden">
        {/* 헤더 */}
        <div className="px-6 py-4 border-b border-gray-200 bg-gray-50">
          <h2 className="text-xl font-bold text-gray-800">
            {isEditing ? '작업 편집' : '작업 추가'}
          </h2>
        </div>

        {/* 폼 */}
        <div className="p-6 space-y-5">
          {/* 작업 이름 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">작업 이름</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => onFormChange({ ...form, name: e.target.value })}
              placeholder="작업 이름 입력"
              className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
            />
          </div>

          {/* 설명 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">설명</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => onFormChange({ ...form, description: e.target.value })}
              placeholder="작업 설명"
              className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
            />
          </div>

          {/* 실행 시간 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">실행 시간 (HH:MM)</label>
            <input
              type="text"
              value={form.time}
              onChange={(e) => onFormChange({ ...form, time: e.target.value })}
              placeholder="06:00"
              pattern="[0-2][0-9]:[0-5][0-9]"
              className="w-36 px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
            />
          </div>

          {/* 작업 종류 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">작업 종류</label>
            <select
              value={form.action}
              onChange={(e) => onFormChange({ ...form, action: e.target.value })}
              className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
            >
              {actions.map((action) => (
                <option key={action.id} value={action.id}>
                  {action.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* 푸터 */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg hover:bg-gray-200 transition-colors text-gray-600"
          >
            취소
          </button>
          <button
            onClick={onSave}
            className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors"
          >
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
