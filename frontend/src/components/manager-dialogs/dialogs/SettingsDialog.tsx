/**
 * SettingsDialog - 설정 다이얼로그
 */

import {
  X,
  Bot,
  Radio,
  Wrench,
  Plus,
  Trash2,
  Edit2,
  Zap,
  Save,
} from 'lucide-react';
import type { Agent } from '../../../types';
import type { Tool, ToolSettings } from '../types';

interface SettingsDialogProps {
  show: boolean;
  onClose: () => void;
  settingsTab: 'channels' | 'tools' | 'agents';
  setSettingsTab: (tab: 'channels' | 'tools' | 'agents') => void;
  // 에이전트 탭
  agents: Agent[];
  runningAgents: Set<string>;
  onAddAgentSettings: () => void;
  onEditAgentSettings: (agent: Agent) => void;
  onDeleteAgentSettings: (agent: Agent) => void;
  onAutoAssignTools: () => void;
  // 도구 탭
  tools: Tool[];
  toolSettings: ToolSettings;
  onEditToolAI: (tool: Tool) => void;
  defaultTools: string[];
  onToggleDefaultTool: (toolName: string) => void;
  onSaveDefaultTools: () => void;
}

export function SettingsDialog({
  show,
  onClose,
  settingsTab,
  setSettingsTab,
  // 에이전트 탭
  agents,
  runningAgents,
  onAddAgentSettings,
  onEditAgentSettings,
  onDeleteAgentSettings,
  onAutoAssignTools,
  // 도구 탭
  tools,
  toolSettings,
  onEditToolAI,
  defaultTools,
  onToggleDefaultTool,
  onSaveDefaultTools,
}: SettingsDialogProps) {
  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{
          width: 'min(900px, 95vw)',
          height: 'min(700px, 90vh)',
          minWidth: '600px',
          minHeight: '500px',
          resize: 'both',
        }}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 shrink-0">
          <h2 className="text-xl font-bold text-gray-800">⚙️ 설정</h2>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-200 rounded-lg">
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        {/* 탭 + 내용 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 탭 사이드바 */}
          <div className="w-48 bg-gray-100 border-r border-gray-200 shrink-0">
            <nav className="p-2 space-y-1">
              <button
                onClick={() => setSettingsTab('agents')}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm transition-colors ${
                  settingsTab === 'agents' ? 'bg-[#D97706] text-white' : 'hover:bg-gray-200 text-gray-700'
                }`}
              >
                <Bot size={16} />
                에이전트
              </button>
              <button
                onClick={() => setSettingsTab('channels')}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm transition-colors ${
                  settingsTab === 'channels' ? 'bg-[#D97706] text-white' : 'hover:bg-gray-200 text-gray-700'
                }`}
              >
                <Radio size={16} />
                채널
              </button>
              <button
                onClick={() => setSettingsTab('tools')}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm transition-colors ${
                  settingsTab === 'tools' ? 'bg-[#D97706] text-white' : 'hover:bg-gray-200 text-gray-700'
                }`}
              >
                <Wrench size={16} />
                도구
              </button>
            </nav>
          </div>

          {/* 탭 내용 */}
          <div className="flex-1 overflow-auto p-6">
            {/* 채널 탭 */}
            {settingsTab === 'channels' && (
              <div className="space-y-6">
                <div>
                  <h3 className="text-lg font-bold text-gray-800 mb-2">통신 채널</h3>
                  <p className="text-sm text-gray-500">에이전트가 사용할 수 있는 통신 채널입니다. 각 에이전트 설정에서 채널을 활성화하세요.</p>
                </div>

                <div className="space-y-3">
                  <div className="bg-cyan-50 rounded-lg p-4 border border-cyan-200">
                    <div className="flex items-center gap-2 text-cyan-600 font-medium mb-2">
                      <Radio size={18} />
                      gui
                      <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded ml-2">기본</span>
                    </div>
                    <p className="text-sm text-gray-600">GUI를 통한 직접 통신 채널 (사용자와 대화)</p>
                  </div>
                  <div className="bg-yellow-50 rounded-lg p-4 border border-yellow-200">
                    <div className="flex items-center gap-2 text-yellow-600 font-medium mb-2">
                      <Radio size={18} />
                      internal
                      <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded ml-2">기본</span>
                    </div>
                    <p className="text-sm text-gray-600">내부 에이전트 간 통신 채널</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                    <div className="flex items-center gap-2 text-cyan-600 font-medium mb-2">
                      <Radio size={18} />
                      gmail
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded ml-2">외부 연동</span>
                    </div>
                    <p className="text-sm text-gray-600">Gmail을 통한 이메일 송수신 (OAuth 설정 필요)</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                    <div className="flex items-center gap-2 text-purple-600 font-medium mb-2">
                      <Radio size={18} />
                      nostr
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded ml-2">외부 연동</span>
                    </div>
                    <p className="text-sm text-gray-600">Nostr 프로토콜을 통한 탈중앙화 메시징</p>
                  </div>
                </div>

                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <p className="text-sm text-blue-700">
                    💡 <strong>채널 사용 방법:</strong> 에이전트를 편집할 때 "외부 에이전트" 타입으로 설정하면 Gmail이나 Nostr 채널을 활성화할 수 있습니다.
                  </p>
                </div>
              </div>
            )}

            {/* 도구 탭 */}
            {settingsTab === 'tools' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-gray-800 mb-2">프로젝트 기본 도구</h3>
                    <p className="text-sm text-gray-500">
                      체크한 도구는 모든 에이전트에게 기본으로 제공됩니다.
                    </p>
                  </div>
                  <button
                    onClick={onSaveDefaultTools}
                    className="flex items-center gap-2 px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600"
                  >
                    <Save size={16} />
                    저장
                  </button>
                </div>

                <div className="space-y-3">
                  {tools.length === 0 ? (
                    <div className="text-center py-8">
                      <p className="text-gray-500 mb-4">설치된 도구가 없습니다.</p>
                      <p className="text-sm text-gray-400">
                        런처로 돌아가서 <span className="font-semibold">🧰 도구상자</span>를 열고<br />
                        원하는 도구 패키지를 설치하세요.
                      </p>
                    </div>
                  ) : (
                    tools.filter(t => !t._is_system).map((tool) => {
                      const configKey = tool.ai_config_key || tool.name;
                      const aiConfig = toolSettings[configKey]?.report_ai;
                      const isDefault = defaultTools.includes(tool.name);
                      return (
                        <div
                          key={tool.name}
                          className={`rounded-lg p-4 border cursor-pointer transition-colors ${
                            isDefault
                              ? 'bg-green-50 border-green-300'
                              : 'bg-gray-50 border-gray-200 hover:border-gray-300'
                          }`}
                          onClick={() => onToggleDefaultTool(tool.name)}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-3">
                              <input
                                type="checkbox"
                                checked={isDefault}
                                onChange={() => onToggleDefaultTool(tool.name)}
                                onClick={(e) => e.stopPropagation()}
                                className="w-4 h-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
                              />
                              <Wrench size={16} className={tool.uses_ai ? 'text-cyan-600' : 'text-[#D97706]'} />
                              <span className={`font-medium ${tool.uses_ai ? 'text-cyan-600' : 'text-[#D97706]'}`}>
                                {tool.name}
                              </span>
                              {tool.uses_ai && (
                                <span className="text-xs bg-cyan-100 text-cyan-700 px-2 py-0.5 rounded">🤖 AI 사용</span>
                              )}
                              {isDefault && (
                                <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">기본</span>
                              )}
                            </div>
                            {tool.uses_ai && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onEditToolAI(tool);
                                }}
                                className="px-3 py-1 text-xs bg-green-500 text-white rounded hover:bg-green-600"
                              >
                                ⚙️ AI 설정
                              </button>
                            )}
                          </div>
                          <p className="text-sm text-gray-600 ml-7">{tool.description}</p>
                          {tool.uses_ai && aiConfig && (
                            <div className="mt-2 ml-7 p-2 bg-green-50 rounded text-xs text-green-700">
                              🤖 현재 AI: {aiConfig.provider} / {aiConfig.model}
                            </div>
                          )}
                          {tool.uses_ai && !aiConfig && (
                            <div className="mt-2 ml-7 p-2 bg-yellow-50 rounded text-xs text-yellow-700">
                              ⚠️ AI 설정이 없습니다. 설정을 추가해 주세요.
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>

                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <p className="text-sm text-blue-700">
                    💡 기본 도구는 모든 에이전트에게 자동으로 제공됩니다. 개별 에이전트에게 추가 도구를 할당하려면 에이전트 편집에서 설정하세요.
                  </p>
                </div>
              </div>
            )}

            {/* 에이전트 탭 */}
            {settingsTab === 'agents' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-gray-800 mb-2">에이전트 관리</h3>
                    <p className="text-sm text-gray-500">프로젝트에 등록된 에이전트를 관리합니다.</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={onAutoAssignTools}
                      className="flex items-center gap-1 px-3 py-1.5 bg-purple-500 text-white rounded-lg hover:bg-purple-600 text-sm"
                    >
                      <Zap size={14} />
                      도구 자동 배분
                    </button>
                    <button
                      onClick={onAddAgentSettings}
                      className="flex items-center gap-1 px-3 py-1.5 bg-green-500 text-white rounded-lg hover:bg-green-600 text-sm"
                    >
                      <Plus size={14} />
                      새 에이전트
                    </button>
                  </div>
                </div>

                <div className="space-y-3">
                  {agents.length === 0 ? (
                    <p className="text-gray-500 text-center py-8">등록된 에이전트가 없습니다.</p>
                  ) : (
                    agents.map((agent) => (
                      <div key={agent.id} className="bg-gray-50 rounded-lg p-4">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <div
                              className={`w-2 h-2 rounded-full ${runningAgents.has(agent.id) ? 'bg-green-500' : 'bg-gray-400'}`}
                            />
                            <span className="font-medium text-gray-800">{agent.name}</span>
                            <span
                              className={`text-xs px-2 py-0.5 rounded ${agent.type === 'external' ? 'bg-cyan-100 text-cyan-700' : 'bg-yellow-100 text-yellow-700'}`}
                            >
                              {agent.type === 'external' ? '외부' : '내부'}
                            </span>
                          </div>
                          <div className="flex gap-1">
                            <button
                              onClick={() => onEditAgentSettings(agent)}
                              className="p-1.5 text-[#D97706] hover:bg-[#D97706]/10 rounded"
                            >
                              <Edit2 size={16} />
                            </button>
                            <button
                              onClick={() => onDeleteAgentSettings(agent)}
                              className="p-1.5 text-red-500 hover:bg-red-50 rounded"
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        </div>
                        <div className="text-sm text-gray-600">
                          <p>
                            🤖 AI: {agent.ai?.provider || 'google'} / {agent.ai?.model || '미설정'}
                          </p>
                          {agent.allowed_tools && (
                            <p className="mt-1">
                              🛠️ 도구: {agent.allowed_tools.slice(0, 3).join(', ')}
                              {agent.allowed_tools.length > 3 && ` 외 ${agent.allowed_tools.length - 3}개`}
                            </p>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

          </div>
        </div>

        {/* 푸터 */}
        <div className="flex justify-end px-6 py-4 border-t border-gray-200 bg-gray-50 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg hover:bg-gray-200 transition-colors text-gray-600"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
