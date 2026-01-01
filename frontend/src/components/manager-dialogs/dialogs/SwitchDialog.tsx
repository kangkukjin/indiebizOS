/**
 * SwitchDialog - 스위치 생성 다이얼로그
 */

import { X } from 'lucide-react';
import type { Agent } from '../../../types';
import type { SwitchForm } from '../types';

interface SwitchDialogProps {
  show: boolean;
  onClose: () => void;
  switchForm: SwitchForm;
  setSwitchForm: (form: SwitchForm) => void;
  agents: Agent[];
  onCreateSwitch: () => void;
}

export function SwitchDialog({
  show,
  onClose,
  switchForm,
  setSwitchForm,
  agents,
  onCreateSwitch,
}: SwitchDialogProps) {
  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-[500px] overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
          <h2 className="text-xl font-bold text-gray-800">⚡ 새 스위치 만들기</h2>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-200 rounded-lg">
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {/* 에이전트 선택 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">에이전트</label>
            <select
              value={switchForm.agentName}
              onChange={(e) => setSwitchForm({ ...switchForm, agentName: e.target.value })}
              className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
            >
              <option value="">선택하세요</option>
              {agents.map((a) => (
                <option key={a.id} value={a.name}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>

          {/* 스위치 이름 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">스위치 이름</label>
            <input
              type="text"
              value={switchForm.name}
              onChange={(e) => setSwitchForm({ ...switchForm, name: e.target.value })}
              placeholder="예: 블로그 보고서"
              className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
            />
          </div>

          {/* 아이콘 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">아이콘 (이모지)</label>
            <input
              type="text"
              value={switchForm.icon}
              onChange={(e) => setSwitchForm({ ...switchForm, icon: e.target.value })}
              className="w-24 px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
            />
          </div>

          {/* 명령어 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">명령어 (AI에게 보낼 내용)</label>
            <textarea
              value={switchForm.command}
              onChange={(e) => setSwitchForm({ ...switchForm, command: e.target.value })}
              placeholder="AI에게 보낼 명령을 입력하세요"
              className="w-full px-4 py-3 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800 resize-none"
              rows={4}
            />
          </div>
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg hover:bg-gray-200 transition-colors text-gray-600"
          >
            취소
          </button>
          <button
            onClick={onCreateSwitch}
            className="px-4 py-2 bg-[#D97706] text-white rounded-lg hover:bg-[#B45309] transition-colors"
          >
            ✅ 스위치 만들기
          </button>
        </div>
      </div>
    </div>
  );
}
