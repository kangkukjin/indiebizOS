/**
 * SwitchEditDialog - 스위치 편집 다이얼로그
 */

import { X } from 'lucide-react';
import type { Switch } from '../../../types';

interface SwitchEditDialogProps {
  show: boolean;
  switchData: Switch | null;
  form: {
    name: string;
    icon: string;
    command: string;
  };
  onFormChange: (form: { name: string; icon: string; command: string }) => void;
  onSave: () => void;
  onClose: () => void;
}

export function SwitchEditDialog({
  show,
  switchData,
  form,
  onFormChange,
  onSave,
  onClose,
}: SwitchEditDialogProps) {
  if (!show || !switchData) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-[500px] overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
          <h2 className="text-xl font-bold text-gray-800">
            ✏️ 스위치 편집
          </h2>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-200 rounded-lg">
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {/* 스위치 이름 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">스위치 이름</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => onFormChange({ ...form, name: e.target.value })}
              placeholder="예: 블로그 보고서"
              className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
            />
          </div>

          {/* 아이콘 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">아이콘 (이모지)</label>
            <input
              type="text"
              value={form.icon}
              onChange={(e) => onFormChange({ ...form, icon: e.target.value })}
              className="w-24 px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800 text-center text-xl"
            />
          </div>

          {/* 명령어 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">명령어 (AI에게 보낼 내용)</label>
            <textarea
              value={form.command}
              onChange={(e) => onFormChange({ ...form, command: e.target.value })}
              placeholder="AI에게 보낼 명령을 입력하세요"
              className="w-full px-4 py-3 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800 resize-none"
              rows={5}
            />
          </div>

          {/* 추가 정보 (읽기 전용) */}
          {switchData.config && (
            <div className="bg-gray-100 rounded-lg p-3 text-sm text-gray-600">
              <div>프로젝트: {(switchData.config.projectId as string) || '-'}</div>
              <div>에이전트: {(switchData.config.agent_name as string) || (switchData.config.agentName as string) || '-'}</div>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg hover:bg-gray-200 transition-colors text-gray-600"
          >
            취소
          </button>
          <button
            onClick={onSave}
            className="px-4 py-2 bg-[#D97706] text-white rounded-lg hover:bg-[#B45309] transition-colors"
          >
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
