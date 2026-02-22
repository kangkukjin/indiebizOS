/**
 * SettingsDialog - 설정 다이얼로그
 * Phase 16: 도구 탭 → 노드 탭 (프로젝트 기본 노드)
 */

import { useEffect, useMemo, useState } from 'react';
import {
  X,
  Bot,
  Radio,
  Settings,
  Plus,
  Trash2,
  Edit2,
  Zap,
  Save,
} from 'lucide-react';
import type { Agent } from '../../../types';
import type { IBLNode } from '../types';
import { api } from '../../../lib/api';

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
  // 설정 탭 (기본 노드)
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
  // 설정 탭
  defaultTools,
  onToggleDefaultTool,
  onSaveDefaultTools,
}: SettingsDialogProps) {
  const [iblNodes, setIblNodes] = useState<IBLNode[]>([]);

  // IBL 노드 목록 로드
  useEffect(() => {
    if (show && settingsTab === 'tools') {
      api.getNodes().then((data) => {
        setIblNodes(data.nodes || []);
      }).catch(() => {
        setIblNodes([]);
      });
    }
  }, [show, settingsTab]);

  // 인프라 노드와 선택 가능 노드 분리
  const { infraNodes, selectableNodes } = useMemo(() => {
    const infra = iblNodes.filter(n => n.always_allowed);
    const selectable = iblNodes.filter(n => !n.always_allowed);
    return { infraNodes: infra, selectableNodes: selectable };
  }, [iblNodes]);

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
          <h2 className="text-xl font-bold text-gray-800">설정</h2>
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
                <Settings size={16} />
                노드
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
                    <strong>채널 사용 방법:</strong> 에이전트를 편집할 때 "외부 에이전트" 타입으로 설정하면 Gmail이나 Nostr 채널을 활성화할 수 있습니다.
                  </p>
                </div>
              </div>
            )}

            {/* 설정 탭 - 프로젝트 기본 노드 */}
            {settingsTab === 'tools' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-gray-800 mb-2">프로젝트 기본 노드</h3>
                    <p className="text-sm text-gray-500">
                      체크한 노드는 새 에이전트 생성 시 기본으로 할당됩니다.
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

                {iblNodes.length === 0 ? (
                  <div className="text-center py-8">
                    <p className="text-gray-500">노드 목록을 불러오는 중...</p>
                  </div>
                ) : (
                  <div className="border border-gray-200 rounded-lg bg-gray-50">
                    {/* 인프라 노드 (항상 활성) */}
                    {infraNodes.length > 0 && (
                      <div className="px-4 py-3 bg-blue-50 border-b border-gray-200">
                        <div className="flex items-center gap-2">
                          <input type="checkbox" checked disabled className="w-4 h-4 rounded" />
                          <span className="text-sm font-medium text-blue-700">
                            인프라 노드 ({infraNodes.length})
                          </span>
                          <span className="text-xs text-blue-500 ml-auto">항상 활성</span>
                        </div>
                        <div className="mt-1 pl-6 text-xs text-blue-600">
                          {infraNodes.map(n => `${n.id} (${n.description.split(' ')[0]})`).join(', ')}
                        </div>
                      </div>
                    )}

                    {/* 선택 가능한 도메인 노드 */}
                    {selectableNodes.map((node) => {
                      const isDefault = defaultTools.includes(node.id);
                      return (
                        <label
                          key={node.id}
                          className={`flex items-center gap-3 px-4 py-2.5 border-b border-gray-100 last:border-b-0 cursor-pointer transition-colors ${
                            isDefault ? 'bg-green-50 hover:bg-green-100' : 'hover:bg-gray-100'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={isDefault}
                            onChange={() => onToggleDefaultTool(node.id)}
                            className="w-4 h-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className={`text-sm font-medium ${isDefault ? 'text-green-700' : 'text-gray-800'}`}>
                                {node.id}
                              </span>
                              <span className="text-xs text-gray-400">({node.action_count})</span>
                              {isDefault && (
                                <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">기본</span>
                              )}
                            </div>
                            <p className="text-xs text-gray-500 truncate">{node.description}</p>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                )}

                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <p className="text-sm text-blue-700">
                    인프라 노드(system, workflow, automation, output)는 모든 에이전트에게 항상 제공됩니다. 개별 에이전트에게 접근 노드를 제한하려면 에이전트 편집에서 설정하세요.
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
                      노드 자동 배분
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
                            AI: {agent.ai?.provider || 'google'} / {agent.ai?.model || '미설정'}
                          </p>
                          {agent.allowed_nodes && agent.allowed_nodes.length > 0 && (
                            <p className="mt-1">
                              노드: {agent.allowed_nodes.slice(0, 4).join(', ')}
                              {agent.allowed_nodes.length > 4 && ` 외 ${agent.allowed_nodes.length - 4}개`}
                            </p>
                          )}
                          {!agent.allowed_nodes && agent.allowed_tools && (
                            <p className="mt-1 text-orange-500">
                              구형 도구: {agent.allowed_tools.slice(0, 3).join(', ')}
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
