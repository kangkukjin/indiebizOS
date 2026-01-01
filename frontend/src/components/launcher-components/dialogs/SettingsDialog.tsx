/**
 * SettingsDialog - 시스템 설정 다이얼로그
 */

import { X, Settings, Brain, Eye, EyeOff, Save } from 'lucide-react';
import type { SystemAISettings } from '../types';

interface SettingsDialogProps {
  show: boolean;
  settings: SystemAISettings;
  showApiKey: boolean;
  onSettingsChange: (settings: SystemAISettings) => void;
  onToggleApiKey: () => void;
  onSave: () => void;
  onClose: () => void;
}

export function SettingsDialog({
  show,
  settings,
  showApiKey,
  onSettingsChange,
  onToggleApiKey,
  onSave,
  onClose,
}: SettingsDialogProps) {
  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{
          width: 'min(500px, 90vw)',
          height: 'min(420px, 80vh)',
          minWidth: '300px',
          minHeight: '300px',
        }}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 shrink-0">
          <div className="flex items-center gap-3">
            <Settings size={24} className="text-gray-600" />
            <h2 className="text-xl font-bold text-gray-800">설정</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
          >
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        {/* 내용 */}
        <div className="flex-1 overflow-auto p-6">
          <div className="space-y-6">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Brain size={20} className="text-amber-600" />
                <h3 className="text-lg font-bold text-gray-900">시스템 AI 설정</h3>
              </div>
              <p className="text-sm text-gray-700 mb-4">
                프로그램 전체에서 사용하는 AI 설정입니다. 프로젝트 시작 시 에이전트들의 도구를 배분하거나 자동 프롬프트 생성에 활용됩니다.
              </p>
            </div>

            <div className="bg-gray-50 rounded-lg p-5 space-y-4">
              {/* 제공자 */}
              <div>
                <label className="block text-sm font-semibold text-gray-900 mb-1">AI 제공자</label>
                <select
                  value={settings.provider}
                  onChange={(e) => onSettingsChange({ ...settings, provider: e.target.value })}
                  className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                >
                  <option value="google">Google (Gemini)</option>
                  <option value="anthropic">Anthropic (Claude)</option>
                  <option value="openai">OpenAI (GPT)</option>
                </select>
              </div>

              {/* 모델 */}
              <div>
                <label className="block text-sm font-semibold text-gray-900 mb-1">모델</label>
                <input
                  type="text"
                  value={settings.model}
                  onChange={(e) => onSettingsChange({ ...settings, model: e.target.value })}
                  placeholder="gemini-2.0-flash-exp"
                  className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 placeholder:text-gray-500"
                />
              </div>

              {/* API 키 */}
              <div>
                <label className="block text-sm font-semibold text-gray-900 mb-1">API 키</label>
                <div className="flex gap-2">
                  <input
                    type={showApiKey ? 'text' : 'password'}
                    value={settings.apiKey}
                    onChange={(e) => onSettingsChange({ ...settings, apiKey: e.target.value })}
                    placeholder="API 키를 입력하세요"
                    className="flex-1 px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 placeholder:text-gray-500"
                  />
                  <button
                    onClick={onToggleApiKey}
                    className="px-3 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 text-gray-700"
                  >
                    {showApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

            </div>
          </div>
        </div>

        {/* 푸터 */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 transition-colors text-gray-700"
          >
            취소
          </button>
          <button
            onClick={onSave}
            className="flex items-center gap-2 px-4 py-2 bg-[#D97706] text-white rounded-lg hover:bg-[#B45309]"
          >
            <Save size={16} />
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
