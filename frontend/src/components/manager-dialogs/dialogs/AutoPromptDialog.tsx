/**
 * AutoPromptDialog - 자동 프롬프트 생성 다이얼로그
 */

import { X, Sparkles, Save } from 'lucide-react';
import type { Agent } from '../../../types';
import type { GeneratedPrompts } from '../types';

interface AutoPromptDialogProps {
  show: boolean;
  onClose: () => void;
  agents: Agent[];
  projectPurpose: string;
  setProjectPurpose: (purpose: string) => void;
  agentRoleDescriptions: Record<string, string>;
  setAgentRoleDescriptions: (descriptions: Record<string, string>) => void;
  autoPromptLoading: boolean;
  generatedPrompts: GeneratedPrompts | null;
  onGeneratePrompts: () => void;
  onSavePrompts: () => void;
  onSaveRoleDescriptions: () => void;
}

export function AutoPromptDialog({
  show,
  onClose,
  agents,
  projectPurpose,
  setProjectPurpose,
  agentRoleDescriptions,
  setAgentRoleDescriptions,
  autoPromptLoading,
  generatedPrompts,
  onGeneratePrompts,
  onSavePrompts,
  onSaveRoleDescriptions,
}: AutoPromptDialogProps) {
  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-[60]">
      <div className="bg-white rounded-xl shadow-2xl w-[800px] max-h-[85vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 shrink-0">
          <div className="flex items-center gap-3">
            <Sparkles size={24} className="text-amber-500" />
            <h2 className="text-xl font-bold text-gray-800">자동 프롬프트 생성</h2>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-200 rounded-lg">
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-6 space-y-6">
          {/* 프로젝트 목적 입력 */}
          <div>
            <label className="block text-sm font-semibold text-gray-900 mb-2">
              프로젝트 목적
            </label>
            <textarea
              value={projectPurpose}
              onChange={(e) => setProjectPurpose(e.target.value)}
              placeholder="프로젝트 목적을 입력하세요 (범용 프로젝트라면 '범용' 또는 비워둬도 됩니다)"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:border-amber-500 focus:outline-none resize-none text-gray-900 placeholder:text-gray-500"
              rows={3}
            />
          </div>

          {/* 에이전트별 역할 설명 입력 */}
          <div>
            <label className="block text-sm font-semibold text-gray-900 mb-2">
              에이전트별 역할 설명 ({agents.length}명)
            </label>
            <p className="text-sm text-gray-500 mb-3">
              각 에이전트의 역할을 간단히 설명해주세요. 비워두면 기본값이 사용됩니다.
            </p>
            <div className="space-y-3 max-h-64 overflow-y-auto">
              {agents.map(agent => (
                <div key={agent.id} className="flex items-start gap-3">
                  <div className={`shrink-0 px-3 py-1.5 rounded-lg text-sm ${
                    agent.type === 'external'
                      ? 'bg-cyan-100 text-cyan-700'
                      : 'bg-yellow-100 text-yellow-700'
                  }`}>
                    {agent.name}
                    <span className="text-xs ml-1 opacity-70">
                      ({agent.type === 'external' ? '외부' : '내부'})
                    </span>
                  </div>
                  <input
                    type="text"
                    value={agentRoleDescriptions[agent.name] || ''}
                    onChange={(e) => setAgentRoleDescriptions({
                      ...agentRoleDescriptions,
                      [agent.name]: e.target.value
                    })}
                    placeholder={`예: ${agent.type === 'external' ? '이메일로 사용자와 소통하는 비서' : '코드 작성과 실행을 담당하는 개발자'}`}
                    className="flex-1 px-3 py-1.5 border border-gray-300 rounded-lg focus:border-amber-500 focus:outline-none text-sm text-gray-900 placeholder:text-gray-400"
                  />
                </div>
              ))}
            </div>
            {/* 역할 설명 저장 버튼 */}
            <div className="flex justify-end mt-3">
              <button
                onClick={onSaveRoleDescriptions}
                className="text-sm px-3 py-1.5 text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <Save size={14} className="inline mr-1" />
                역할 설명 저장
              </button>
            </div>
          </div>

          {/* 생성 버튼 */}
          <div className="flex justify-center gap-3">
            <button
              onClick={onGeneratePrompts}
              disabled={autoPromptLoading}
              className="flex items-center gap-2 px-6 py-2.5 bg-amber-500 text-white rounded-lg hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {autoPromptLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  생성 중...
                </>
              ) : (
                <>
                  <Sparkles size={16} />
                  프롬프트 미리보기
                </>
              )}
            </button>
          </div>

          {/* 미리보기 결과 */}
          {generatedPrompts && (
            <div className="space-y-4">
              <div className="border-t pt-4">
                <h4 className="font-medium text-gray-800 mb-2">📝 공통 설정 (common_settings.txt)</h4>
                <pre className="bg-gray-50 p-4 rounded-lg text-sm text-gray-700 overflow-auto max-h-48 whitespace-pre-wrap">
                  {generatedPrompts.common_settings}
                </pre>
              </div>

              <div>
                <h4 className="font-medium text-gray-800 mb-2">👥 에이전트별 역할</h4>
                <div className="space-y-3">
                  {Object.entries(generatedPrompts.agent_roles).map(([agentName, role]) => (
                    <div key={agentName} className="bg-gray-50 p-4 rounded-lg">
                      <p className="font-medium text-gray-800 mb-1">{agentName}</p>
                      <pre className="text-sm text-gray-600 whitespace-pre-wrap">{role}</pre>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
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
            onClick={onSavePrompts}
            disabled={autoPromptLoading || !generatedPrompts}
            className="flex items-center gap-2 px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Save size={16} />
            프로젝트에 저장
          </button>
        </div>
      </div>
    </div>
  );
}
