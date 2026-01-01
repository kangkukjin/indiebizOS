/**
 * ToolAIDialog - 도구 AI 설정 다이얼로그
 */

import { X, Wrench } from 'lucide-react';
import type { ToolAIForm } from '../types';

interface ToolAIDialogProps {
  show: boolean;
  onClose: () => void;
  editingToolAI: { name: string; config_key: string } | null;
  toolAIForm: ToolAIForm;
  setToolAIForm: (form: ToolAIForm) => void;
  onSaveToolAI: () => void;
}

export function ToolAIDialog({
  show,
  onClose,
  editingToolAI,
  toolAIForm,
  setToolAIForm,
  onSaveToolAI,
}: ToolAIDialogProps) {
  if (!show || !editingToolAI) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-[60]">
      <div className="bg-white rounded-xl shadow-2xl w-[500px] overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
          <div className="flex items-center gap-3">
            <Wrench size={24} className="text-cyan-600" />
            <h2 className="text-xl font-bold text-gray-800">{editingToolAI.name} AI 설정</h2>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-200 rounded-lg">
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {/* Provider */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">AI 제공자</label>
            <select
              value={toolAIForm.provider}
              onChange={(e) => setToolAIForm({ ...toolAIForm, provider: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:border-cyan-500 focus:outline-none text-gray-900"
            >
              <option value="gemini">Google (Gemini)</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </div>

          {/* Model */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">모델</label>
            <input
              type="text"
              value={toolAIForm.model}
              onChange={(e) => setToolAIForm({ ...toolAIForm, model: e.target.value })}
              placeholder="gemini-2.0-flash"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:border-cyan-500 focus:outline-none text-gray-900"
            />
            <p className="text-xs text-gray-500 mt-1">
              예: gemini-2.0-flash, gemini-3-flash-preview, gpt-4o, claude-3-5-sonnet-20241022
            </p>
          </div>

          {/* API Key */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">API Key</label>
            <input
              type="password"
              value={toolAIForm.apiKey}
              onChange={(e) => setToolAIForm({ ...toolAIForm, apiKey: e.target.value })}
              placeholder="API Key를 입력하세요"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:border-cyan-500 focus:outline-none text-gray-900"
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
            onClick={onSaveToolAI}
            className="px-4 py-2 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 transition-colors"
          >
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
