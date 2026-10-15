import { Eye, EyeOff } from 'lucide-react';
import { CodexModelPicker } from './CodexModelPicker';
import type { SystemAISettings } from './launcher-components/types';
import { isCliProvider, modelPlaceholder, modelFieldHint } from '../types';

export function ModelTierSettings({ title, description, settings, showApiKey, onSettingsChange, onToggleApiKey }: {
  title: string; description: string; settings: SystemAISettings; showApiKey: boolean;
  onSettingsChange: (value: SystemAISettings) => void; onToggleApiKey: () => void;
}) {
  type TierSettings = SystemAISettings;
  const switchProvider = <T extends TierSettings>(current: T, provider: string): T => {
    const providerModels = { ...(current.providerModels || {}) };
    if (current.model) providerModels[current.provider] = current.model;
    const providerApiKeys = { ...(current.providerApiKeys || {}) };
    if (current.apiKey) providerApiKeys[current.provider] = current.apiKey;
    return { ...current, provider, model: providerModels[provider] || '',
      apiKey: providerApiKeys[provider] || '', providerModels, providerApiKeys };
  };
  const changeModel = <T extends TierSettings>(current: T, model: string): T => ({
    ...current, model,
    providerModels: { ...(current.providerModels || {}), [current.provider]: model },
  });
  const changeApiKey = <T extends TierSettings>(current: T, apiKey: string): T => ({
    ...current, apiKey,
    providerApiKeys: { ...(current.providerApiKeys || {}), [current.provider]: apiKey },
  });
  const keyPlaceholder = (current: TierSettings) => isCliProvider(current.provider)
    ? 'API 키가 필요하지 않습니다'
    : current.providerHasApiKey?.[current.provider]
      ? '저장된 API 키 사용 중 — 새 키를 입력하면 교체됩니다'
      : 'API 키를 입력하세요';

  return <section className="min-w-0 space-y-4"><div><h2 className="text-base font-bold text-gray-900 mb-1">{title}</h2><p className="text-sm text-gray-700">{description}</p></div>
              <div className="bg-gray-50 rounded-lg p-5 space-y-4">
                {/* 제공자 */}
                <div>
                  <label className="block text-sm font-semibold text-gray-900 mb-1">AI 제공자</label>
                  <select
                    value={settings.provider}
                    onChange={(e) => onSettingsChange(switchProvider(settings, e.target.value))}
                    className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                  >
                    <option value="google">Google (Gemini)</option>
                    <option value="anthropic">Anthropic (Claude)</option>
                    <option value="openai">OpenAI (GPT)</option>
                    <option value="openrouter">OpenRouter (650+ 모델)</option>
                    <option value="deepseek">DeepSeek (V4 Pro/Flash)</option>
                    <option value="claude_code">Claude Code (Max 플랜, CLI 호출)</option>
                    <option value="codex">Codex (ChatGPT 구독, CLI 호출)</option>
                  </select>
                </div>

                {/* 모델 */}
                <div>
                  <label className="block text-sm font-semibold text-gray-900 mb-1">모델</label>
                  <input
                    type="text"
                    value={settings.model}
                    onChange={(e) => onSettingsChange(changeModel(settings, e.target.value))}
                    placeholder={modelPlaceholder(settings.provider, 'gemini-2.0-flash-exp')}
                    className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 placeholder:text-gray-500"
                  />
                  <CodexModelPicker provider={settings.provider} value={settings.model}
                    onChange={(model) => onSettingsChange(changeModel(settings, model))} />
                  {modelFieldHint(settings.provider) && (
                    <p className="text-xs text-gray-500 mt-1">{modelFieldHint(settings.provider)}</p>
                  )}
                </div>

                {/* API 키 */}
                <div>
                  <label className="block text-sm font-semibold text-gray-900 mb-1">API 키</label>
                  <div className="flex gap-2">
                    <input
                      type={showApiKey ? 'text' : 'password'}
                      value={settings.apiKey}
                      onChange={(e) => onSettingsChange(changeApiKey(settings, e.target.value))}
                      placeholder={keyPlaceholder(settings)}
                      className="min-w-0 flex-1 px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 placeholder:text-gray-500"
                    />
                    <button
                      aria-label={showApiKey ? "API 키 숨기기" : "API 키 보기"}
                      onClick={onToggleApiKey}
                      className="px-3 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 text-gray-700"
                    >
                      {showApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>
              </div>
  </section>;
}
