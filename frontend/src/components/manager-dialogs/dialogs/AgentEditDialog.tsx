/**
 * AgentEditDialog - 에이전트 편집 다이얼로그
 * Phase 16: IBL 노드 기반 접근 제어 (allowed_nodes)
 */

import { useEffect, useMemo, useState } from 'react';
import { X, Eye, EyeOff } from 'lucide-react';
import type { Agent } from '../../../types';
import type { AgentForm, IBLNode } from '../types';
import { api } from '../../../lib/api';

interface AgentEditDialogProps {
  show: boolean;
  onClose: () => void;
  editingAgentData: Agent | null;
  agentForm: AgentForm;
  setAgentForm: (form: AgentForm) => void;
  onSaveAgentSettings: () => void;
}

export function AgentEditDialog({
  show,
  onClose,
  editingAgentData,
  agentForm,
  setAgentForm,
  onSaveAgentSettings,
}: AgentEditDialogProps) {
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [ollamaRunning, setOllamaRunning] = useState(false);
  const [iblNodes, setIblNodes] = useState<IBLNode[]>([]);
  const [showApiKey, setShowApiKey] = useState(false);

  // Ollama 선택 시 모델 목록 로드
  useEffect(() => {
    if (show && agentForm.provider === 'ollama') {
      api.getOllamaModels().then((data) => {
        setOllamaModels(data.models);
        setOllamaRunning(data.running);
        if (data.models.length === 1 && !agentForm.model) {
          setAgentForm({ ...agentForm, model: data.models[0] });
        }
      }).catch(() => {
        setOllamaModels([]);
        setOllamaRunning(false);
      });
    }
  }, [show, agentForm.provider]);

  // IBL 노드 목록 로드
  useEffect(() => {
    if (show) {
      api.getNodes().then((data) => {
        setIblNodes(data.nodes || []);
      }).catch(() => {
        setIblNodes([]);
      });
    }
  }, [show]);

  // 인프라 노드와 선택 가능 노드 분리
  const { infraNodes, selectableNodes } = useMemo(() => {
    const infra = iblNodes.filter(n => n.always_allowed);
    const selectable = iblNodes.filter(n => !n.always_allowed);
    return { infraNodes: infra, selectableNodes: selectable };
  }, [iblNodes]);

  // 노드 토글
  const handleNodeToggle = (nodeId: string, checked: boolean) => {
    if (checked) {
      setAgentForm({ ...agentForm, allowedNodes: [...agentForm.allowedNodes, nodeId] });
    } else {
      setAgentForm({ ...agentForm, allowedNodes: agentForm.allowedNodes.filter(n => n !== nodeId) });
    }
  };

  // 전체 선택 (인프라 노드 제외)
  const selectAll = () => {
    const allSelectableIds = selectableNodes.map(n => n.id);
    setAgentForm({ ...agentForm, allowedNodes: allSelectableIds });
  };

  // 전체 해제
  const deselectAll = () => {
    setAgentForm({ ...agentForm, allowedNodes: [] });
  };

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-[60]">
      <div className="bg-white rounded-xl shadow-2xl w-[700px] max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 shrink-0">
          <h2 className="text-xl font-bold text-gray-800">
            {editingAgentData ? '에이전트 편집' : '새 에이전트'}
          </h2>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-200 rounded-lg">
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-6 space-y-6">
          {/* 기본 정보 */}
          <div className="border border-gray-200 rounded-lg p-4">
            <h3 className="text-sm font-bold text-gray-700 mb-3">기본 정보</h3>
            <div className="grid grid-cols-2 gap-4">
              {/* 이름 */}
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">에이전트 이름</label>
                <input
                  type="text"
                  value={agentForm.name}
                  onChange={(e) => setAgentForm({ ...agentForm, name: e.target.value })}
                  placeholder="에이전트 이름"
                  className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                />
              </div>

              {/* 타입 */}
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">타입</label>
                <select
                  value={agentForm.type}
                  onChange={(e) => setAgentForm({ ...agentForm, type: e.target.value })}
                  className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                >
                  <option value="internal">내부 워커</option>
                  <option value="external">외부 에이전트</option>
                </select>
              </div>
            </div>
          </div>

          {/* AI 설정 */}
          <div className="border border-gray-200 rounded-lg p-4">
            <h3 className="text-sm font-bold text-gray-700 mb-3">AI 설정</h3>
            <div className="grid grid-cols-2 gap-4">
              {/* AI 제공자 */}
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">AI 제공자</label>
                <select
                  value={agentForm.provider}
                  onChange={(e) => setAgentForm({ ...agentForm, provider: e.target.value, model: '' })}
                  className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                >
                  <option value="google">Google (Gemini)</option>
                  <option value="anthropic">Anthropic (Claude)</option>
                  <option value="openai">OpenAI (GPT)</option>
                  <option value="openrouter">OpenRouter (650+ 모델)</option>
                  <option value="ollama">Ollama (로컬)</option>
                  <option value="claude_code">Claude Code (Max 플랜, CLI 호출)</option>
                </select>
              </div>

              {/* 모델 */}
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">모델</label>
                {agentForm.provider === 'ollama' ? (
                  ollamaModels.length > 0 ? (
                    <select
                      value={agentForm.model}
                      onChange={(e) => setAgentForm({ ...agentForm, model: e.target.value })}
                      className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                    >
                      <option value="">모델 선택</option>
                      {ollamaModels.map((model) => (
                        <option key={model} value={model}>{model}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={agentForm.model}
                      onChange={(e) => setAgentForm({ ...agentForm, model: e.target.value })}
                      placeholder={ollamaRunning ? "설치된 모델 없음" : "Ollama 서버 확인 중..."}
                      className="w-full px-3 py-2 bg-gray-100 border border-gray-300 rounded-lg text-gray-500"
                      disabled
                    />
                  )
                ) : (
                  <input
                    type="text"
                    value={agentForm.model}
                    onChange={(e) => setAgentForm({ ...agentForm, model: e.target.value })}
                    placeholder="gemini-2.0-flash-exp"
                    className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                  />
                )}
              </div>

              {/* API 키 (Ollama가 아닐 때만) */}
              {agentForm.provider !== 'ollama' && (
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-800 mb-1">API 키</label>
                  <div className="flex gap-2">
                    <input
                      type={showApiKey ? 'text' : 'password'}
                      value={agentForm.apiKey}
                      onChange={(e) => setAgentForm({ ...agentForm, apiKey: e.target.value })}
                      placeholder="API 키 (비워두면 공통 설정 사용)"
                      className="flex-1 px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                    />
                    <button
                      type="button"
                      onClick={() => setShowApiKey(!showApiKey)}
                      className="px-3 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 text-gray-700"
                    >
                      {showApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>
              )}

              {/* Ollama 안내 */}
              {agentForm.provider === 'ollama' && (
                <div className="col-span-2 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <p className="text-sm text-blue-800">
                    <strong>Ollama</strong>는 로컬에서 실행되므로 API 키가 필요 없습니다.
                  </p>
                  {!ollamaRunning && (
                    <p className="text-xs text-orange-600 mt-1">
                      Ollama 서버가 실행 중이 아닙니다. Manager에서 Ollama를 시작하세요.
                    </p>
                  )}
                  {ollamaRunning && ollamaModels.length === 0 && (
                    <p className="text-xs text-orange-600 mt-1">
                      설치된 모델이 없습니다. 터미널에서 `ollama pull qwen2.5:3b` 등으로 모델을 설치하세요.
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* 채널 설정 (외부 에이전트인 경우만) */}
          {agentForm.type === 'external' && (
            <div className="border border-gray-200 rounded-lg p-4">
              <h3 className="text-sm font-bold text-gray-700 mb-3">정보 채널 (복수 선택 가능)</h3>
              <div className="space-y-4">
                {/* Gmail 채널 */}
                <div className={`border rounded-lg p-3 ${agentForm.hasGmail ? 'border-cyan-400 bg-cyan-50' : 'border-gray-200'}`}>
                  <label className="flex items-center gap-2 cursor-pointer mb-2">
                    <input
                      type="checkbox"
                      checked={agentForm.hasGmail}
                      onChange={(e) => setAgentForm({ ...agentForm, hasGmail: e.target.checked })}
                      className="rounded"
                    />
                    <span className="font-medium text-gray-900">Gmail 채널</span>
                  </label>
                  {agentForm.hasGmail && (
                    <div className="space-y-3 mt-3">
                      <div>
                        <label className="block text-sm font-medium text-gray-800 mb-1">이메일</label>
                        <input
                          type="email"
                          value={agentForm.email}
                          onChange={(e) => setAgentForm({ ...agentForm, email: e.target.value })}
                          placeholder="agent@gmail.com"
                          className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                        />
                      </div>
                      <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                        <p className="text-sm text-blue-800">
                          <strong>OAuth 인증</strong>은 전역 Gmail 설정(설정 → 채널 → Gmail)을 사용합니다.
                          에이전트별로 별도 OAuth 설정은 필요 없습니다.
                        </p>
                        <p className="text-xs text-blue-600 mt-1">
                          처음 이메일 발송 시 브라우저에서 해당 이메일 계정으로 인증이 필요합니다.
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Nostr 채널 */}
                <div className={`border rounded-lg p-3 ${agentForm.hasNostr ? 'border-purple-400 bg-purple-50' : 'border-gray-200'}`}>
                  <label className="flex items-center gap-2 cursor-pointer mb-2">
                    <input
                      type="checkbox"
                      checked={agentForm.hasNostr}
                      onChange={(e) => setAgentForm({ ...agentForm, hasNostr: e.target.checked })}
                      className="rounded"
                    />
                    <span className="font-medium text-gray-900">Nostr 채널</span>
                  </label>
                  {agentForm.hasNostr && (
                    <div className="space-y-3 mt-3">
                      <div>
                        <label className="block text-sm font-medium text-gray-800 mb-1">키 이름</label>
                        <input
                          type="text"
                          value={agentForm.nostrKeyName}
                          onChange={(e) => setAgentForm({ ...agentForm, nostrKeyName: e.target.value })}
                          placeholder="my_key"
                          className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-800 mb-1">Private Key (hex)</label>
                        <input
                          type="password"
                          value={agentForm.nostrPrivateKey}
                          onChange={(e) => setAgentForm({ ...agentForm, nostrPrivateKey: e.target.value })}
                          placeholder="nsec 또는 hex 형식"
                          className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-800 mb-1">Relay 서버 (쉼표 구분)</label>
                        <input
                          type="text"
                          value={agentForm.nostrRelays}
                          onChange={(e) => setAgentForm({ ...agentForm, nostrRelays: e.target.value })}
                          placeholder="wss://relay.damus.io,wss://relay.nostr.band"
                          className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 개별 역할 */}
          <div className="border border-gray-200 rounded-lg p-4">
            <h3 className="text-sm font-bold text-gray-700 mb-3">개별 역할 (프롬프트)</h3>
            <textarea
              value={agentForm.role}
              onChange={(e) => setAgentForm({ ...agentForm, role: e.target.value })}
              placeholder="이 에이전트의 역할과 행동 지침을 입력하세요..."
              className="w-full h-32 px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 resize-none"
            />
          </div>

          {/* IBL 노드 설정 (Phase 16) */}
          <div className="border border-gray-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-gray-700">접근 노드</h3>
              <div className="flex gap-2">
                <button
                  onClick={selectAll}
                  className="px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600"
                >
                  전체 선택
                </button>
                <button
                  onClick={deselectAll}
                  className="px-2 py-1 text-xs bg-gray-500 text-white rounded hover:bg-gray-600"
                >
                  전체 해제
                </button>
              </div>
            </div>
            <div className="max-h-64 overflow-auto border border-gray-200 rounded-lg bg-gray-50">
              {/* 인프라 노드 (항상 활성) */}
              {infraNodes.length > 0 && (
                <div className="px-3 py-2 bg-blue-50 border-b border-gray-200">
                  <div className="flex items-center gap-2">
                    <input type="checkbox" checked disabled className="rounded" />
                    <span className="text-sm font-medium text-blue-700">
                      인프라 노드 ({infraNodes.length})
                    </span>
                    <span className="text-xs text-blue-500 ml-auto">항상 활성</span>
                  </div>
                  <div className="mt-1 pl-6 text-xs text-blue-600">
                    {infraNodes.map(n => n.id).join(', ')}
                  </div>
                </div>
              )}

              {/* 선택 가능한 도메인 노드 */}
              {selectableNodes.map((node) => {
                const isChecked = agentForm.allowedNodes.includes(node.id);
                return (
                  <label
                    key={node.id}
                    className="flex items-center gap-3 px-3 py-2 border-b border-gray-100 last:border-b-0 hover:bg-gray-100 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={(e) => handleNodeToggle(node.id, e.target.checked)}
                      className="rounded shrink-0"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-800">{node.id}</span>
                        <span className="text-xs text-gray-400">({node.action_count})</span>
                      </div>
                      <p className="text-xs text-gray-500 truncate">{node.description}</p>
                    </div>
                  </label>
                );
              })}
            </div>
            <p className="mt-2 text-xs text-gray-500">
              비워두면 모든 노드에 접근할 수 있습니다. 노드를 선택하면 선택한 노드만 사용 가능합니다.
            </p>
          </div>
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg hover:bg-gray-200 transition-colors text-gray-600"
          >
            취소
          </button>
          <button
            onClick={onSaveAgentSettings}
            className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors"
          >
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
