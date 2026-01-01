/**
 * AgentEditDialog - 에이전트 편집 다이얼로그
 */

import { X } from 'lucide-react';
import type { Agent } from '../../../types';
import type { AgentForm, Tool } from '../types';

interface AgentEditDialogProps {
  show: boolean;
  onClose: () => void;
  editingAgentData: Agent | null;
  agentForm: AgentForm;
  setAgentForm: (form: AgentForm) => void;
  allTools: Tool[];
  baseTools: string[];
  onSaveAgentSettings: () => void;
}

export function AgentEditDialog({
  show,
  onClose,
  editingAgentData,
  agentForm,
  setAgentForm,
  allTools,
  baseTools,
  onSaveAgentSettings,
}: AgentEditDialogProps) {
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
                  onChange={(e) => setAgentForm({ ...agentForm, provider: e.target.value })}
                  className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                >
                  <option value="google">Google (Gemini)</option>
                  <option value="anthropic">Anthropic (Claude)</option>
                  <option value="openai">OpenAI (GPT)</option>
                  <option value="ollama">Ollama (로컬)</option>
                </select>
              </div>

              {/* 모델 */}
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">모델</label>
                <input
                  type="text"
                  value={agentForm.model}
                  onChange={(e) => setAgentForm({ ...agentForm, model: e.target.value })}
                  placeholder="gemini-2.0-flash-exp"
                  className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                />
              </div>

              {/* API 키 (Ollama가 아닐 때만) */}
              {agentForm.provider !== 'ollama' && (
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-800 mb-1">API 키</label>
                  <input
                    type="password"
                    value={agentForm.apiKey}
                    onChange={(e) => setAgentForm({ ...agentForm, apiKey: e.target.value })}
                    placeholder="API 키 (비워두면 공통 설정 사용)"
                    className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                  />
                </div>
              )}

              {/* Ollama 안내 */}
              {agentForm.provider === 'ollama' && (
                <div className="col-span-2 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <p className="text-sm text-blue-800">
                    <strong>Ollama</strong>는 로컬에서 실행되므로 API 키가 필요 없습니다.
                  </p>
                  <p className="text-xs text-blue-600 mt-1">
                    Ollama 서버가 실행 중이어야 합니다. 모델 예시: llama3.2, qwen2.5:7b, mistral
                  </p>
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
                    <div className="grid grid-cols-2 gap-4 mt-3">
                      <div className="col-span-2">
                        <label className="block text-sm font-medium text-gray-800 mb-1">이메일</label>
                        <input
                          type="email"
                          value={agentForm.email}
                          onChange={(e) => setAgentForm({ ...agentForm, email: e.target.value })}
                          placeholder="agent@gmail.com"
                          className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-800 mb-1">Client ID</label>
                        <input
                          type="text"
                          value={agentForm.gmailClientId}
                          onChange={(e) => setAgentForm({ ...agentForm, gmailClientId: e.target.value })}
                          placeholder="Google OAuth Client ID"
                          className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-800 mb-1">Client Secret</label>
                        <input
                          type="password"
                          value={agentForm.gmailClientSecret}
                          onChange={(e) => setAgentForm({ ...agentForm, gmailClientSecret: e.target.value })}
                          placeholder="Google OAuth Client Secret"
                          className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                        />
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

          {/* 도구 설정 */}
          <div className="border border-gray-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-gray-700">사용 도구</h3>
              <div className="flex gap-2">
                <button
                  onClick={() => setAgentForm({ ...agentForm, allowedTools: allTools.map(t => t.name) })}
                  className="px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600"
                >
                  전체 선택
                </button>
                <button
                  onClick={() => setAgentForm({ ...agentForm, allowedTools: [] })}
                  className="px-2 py-1 text-xs bg-gray-500 text-white rounded hover:bg-gray-600"
                >
                  전체 해제
                </button>
              </div>
            </div>
            <div className="max-h-40 overflow-auto border border-gray-200 rounded-lg p-2 bg-gray-50">
              <div className="grid grid-cols-2 gap-2">
                {allTools.map((tool) => {
                  const isBase = baseTools.includes(tool.name);
                  const isChecked = isBase || agentForm.allowedTools.includes(tool.name);
                  return (
                    <label
                      key={tool.name}
                      className={`flex items-center gap-2 p-2 rounded ${isBase ? 'bg-blue-50' : 'hover:bg-gray-100'} cursor-pointer`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        disabled={isBase}
                        onChange={(e) => {
                          if (isBase) return;
                          if (e.target.checked) {
                            setAgentForm({ ...agentForm, allowedTools: [...agentForm.allowedTools, tool.name] });
                          } else {
                            setAgentForm({ ...agentForm, allowedTools: agentForm.allowedTools.filter(t => t !== tool.name) });
                          }
                        }}
                        className="rounded"
                      />
                      <span className={`text-sm ${isBase ? 'text-blue-700' : 'text-gray-800'}`}>
                        {tool.name}
                        {isBase && <span className="ml-1 text-xs text-blue-500">(기초)</span>}
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-500">기초 도구는 항상 제공되며 비활성화할 수 없습니다.</p>
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
