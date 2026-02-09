/**
 * TaskEditDialog - 작업 편집 다이얼로그
 */

import type { TaskForm, SchedulerAction } from '../types';

const REPEAT_OPTIONS = [
  { value: 'daily', label: '매일' },
  { value: 'weekly', label: '매주' },
  { value: 'once', label: '1회' },
  { value: 'yearly', label: '매년' },
  { value: 'interval', label: '간격 반복' },
];

const WEEKDAY_NAMES = ['월', '화', '수', '목', '금', '토', '일'];

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

  const toggleWeekday = (day: number) => {
    const current = form.weekdays || [];
    const updated = current.includes(day)
      ? current.filter(d => d !== day)
      : [...current, day].sort();
    onFormChange({ ...form, weekdays: updated });
  };

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-[60]">
      <div className="bg-white rounded-xl shadow-2xl w-[520px] overflow-hidden max-h-[80vh] flex flex-col">
        {/* 헤더 */}
        <div className="px-6 py-4 border-b border-gray-200 bg-gray-50 shrink-0">
          <h2 className="text-xl font-bold text-gray-800">
            {isEditing ? '작업 편집' : '작업 추가'}
          </h2>
        </div>

        {/* 폼 */}
        <div className="p-6 space-y-5 overflow-y-auto flex-1">
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

          {/* 실행 시간 + 반복 유형 */}
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-2">실행 시간</label>
              <input
                type="time"
                value={form.time}
                onChange={(e) => onFormChange({ ...form, time: e.target.value })}
                className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
              />
            </div>
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-2">반복 유형</label>
              <select
                value={form.repeat}
                onChange={(e) => onFormChange({ ...form, repeat: e.target.value })}
                className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
              >
                {REPEAT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* 반복 유형별 추가 필드 */}
          {form.repeat === 'weekly' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">요일 선택</label>
              <div className="flex gap-2">
                {WEEKDAY_NAMES.map((name, idx) => {
                  const isSelected = (form.weekdays || []).includes(idx);
                  return (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => toggleWeekday(idx)}
                      className={`w-10 h-10 rounded-lg text-sm font-medium transition-colors ${
                        isSelected
                          ? 'bg-purple-500 text-white'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}
                    >
                      {name}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {form.repeat === 'once' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">실행 날짜</label>
              <input
                type="date"
                value={form.date || ''}
                onChange={(e) => onFormChange({ ...form, date: e.target.value })}
                className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
              />
            </div>
          )}

          {form.repeat === 'yearly' && (
            <div className="flex gap-4">
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-700 mb-2">월</label>
                <select
                  value={form.month || 1}
                  onChange={(e) => onFormChange({ ...form, month: parseInt(e.target.value) })}
                  className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
                >
                  {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
                    <option key={m} value={m}>{m}월</option>
                  ))}
                </select>
              </div>
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-700 mb-2">일</label>
                <select
                  value={form.day || 1}
                  onChange={(e) => onFormChange({ ...form, day: parseInt(e.target.value) })}
                  className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
                >
                  {Array.from({ length: 31 }, (_, i) => i + 1).map(d => (
                    <option key={d} value={d}>{d}일</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {form.repeat === 'interval' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">반복 간격 (시간)</label>
              <input
                type="number"
                min={1}
                max={168}
                value={form.interval_hours || 1}
                onChange={(e) => onFormChange({ ...form, interval_hours: parseInt(e.target.value) || 1 })}
                className="w-32 px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
              />
              <span className="ml-2 text-sm text-gray-500">시간마다 반복</span>
            </div>
          )}

          {/* 작업 종류 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">작업 종류</label>
            <select
              value={form.action}
              onChange={(e) => onFormChange({ ...form, action: e.target.value, action_params: undefined })}
              className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
            >
              {actions.map((action) => (
                <option key={action.id} value={action.id}>
                  {action.name}
                </option>
              ))}
            </select>
          </div>

          {/* 알림 전송 파라미터 */}
          {form.action === 'send_notification' && (
            <div className="space-y-3 pl-4 border-l-2 border-amber-300">
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">알림 제목</label>
                <input
                  type="text"
                  value={form.action_params?.title || ''}
                  onChange={(e) => onFormChange({
                    ...form,
                    action_params: { ...form.action_params, title: e.target.value }
                  })}
                  placeholder="알림 제목"
                  className="w-full px-3 py-2 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">알림 내용</label>
                <textarea
                  value={form.action_params?.message || ''}
                  onChange={(e) => onFormChange({
                    ...form,
                    action_params: { ...form.action_params, message: e.target.value }
                  })}
                  placeholder="알림 내용"
                  rows={2}
                  className="w-full px-3 py-2 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800 text-sm resize-none"
                />
              </div>
            </div>
          )}

          {/* 스위치 실행 파라미터 */}
          {form.action === 'run_switch' && (
            <div className="pl-4 border-l-2 border-blue-300">
              <label className="block text-sm font-medium text-gray-600 mb-1">스위치 ID</label>
              <input
                type="text"
                value={form.action_params?.switch_id || ''}
                onChange={(e) => onFormChange({
                  ...form,
                  action_params: { ...form.action_params, switch_id: e.target.value }
                })}
                placeholder="switch_xxx"
                className="w-full px-3 py-2 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800 text-sm"
              />
              <p className="mt-1 text-xs text-gray-400">시스템 AI에게 스위치 등록을 요청하면 자동으로 설정됩니다</p>
            </div>
          )}
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
            className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors"
          >
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
