/**
 * SettingsDialog - 시스템 설정 다이얼로그
 *
 * 탭별 서브 컴포넌트:
 *   SettingsChannelsTab.tsx - 통신채널 설정
 *   SettingsRemoteTab.tsx   - 원격 Finder / 원격 런처 / Cloudflare 터널
 */

import { useCallback, useState, useRef } from 'react';
import { X, Settings, Brain, Eye, EyeOff, Save, Radio, Package, CheckCircle, AlertCircle, HardDrive, Download, Upload, Monitor, Cloud, FileText, Edit3, Globe, RefreshCw, KeyRound } from 'lucide-react';
import type { SystemAISettings, LightweightAISettings, MidtierAISettings } from '../types';
import { api } from '../../../lib/api';
import { useRetryingLoad } from '../../../lib/use-retrying-load';
import { SettingsChannelsTab } from './SettingsChannelsTab';
import { SettingsRemoteTab } from './SettingsRemoteTab';
import { SettingsEnvTab } from './SettingsEnvTab';

interface PromptTemplate {
  id: string;
  name: string;
  description: string;
  tokens: number;
  selected: boolean;
}

interface SettingsDialogProps {
  show: boolean;
  settings: SystemAISettings;
  showApiKey: boolean;
  onSettingsChange: (settings: SystemAISettings) => void;
  onToggleApiKey: () => void;
  lightweightSettings: LightweightAISettings;
  showLightweightApiKey: boolean;
  onLightweightSettingsChange: (settings: LightweightAISettings) => void;
  onToggleLightweightApiKey: () => void;
  midtierSettings: MidtierAISettings;
  showMidtierApiKey: boolean;
  onMidtierSettingsChange: (settings: MidtierAISettings) => void;
  onToggleMidtierApiKey: () => void;
  onSave: () => void;
  onClose: () => void;
}

export function SettingsDialog({
  show,
  settings,
  showApiKey,
  onSettingsChange,
  onToggleApiKey,
  lightweightSettings,
  showLightweightApiKey,
  onLightweightSettingsChange,
  onToggleLightweightApiKey,
  midtierSettings,
  showMidtierApiKey,
  onMidtierSettingsChange,
  onToggleMidtierApiKey,
  onSave,
  onClose,
}: SettingsDialogProps) {
  const [activeTab, setActiveTab] = useState<'models' | 'apikeys' | 'persona' | 'channels' | 'data' | 'nas' | 'launcher' | 'tunnel' | 'world'>('models');

  // 데이터 내보내기/가져오기 상태
  const [isExporting, setIsExporting] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [exportResult, setExportResult] = useState<{ success: boolean; message: string } | null>(null);
  const [importResult, setImportResult] = useState<{ success: boolean; message: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 프롬프트 템플릿 상태
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);
  const [showRolePromptModal, setShowRolePromptModal] = useState(false);
  const [rolePromptContent, setRolePromptContent] = useState('');
  const [isSavingRolePrompt, setIsSavingRolePrompt] = useState(false);

  // Cloudflare 터널 정보 (외부 URL 표시용)
  const [finderHostname, setFinderHostname] = useState('');
  const [launcherHostname, setLauncherHostname] = useState('');
  // 오리진 호스트(=이 몸의 얼굴)에서 파생된 주소인지 / 어느 프로바이더인지 — 주소 안내 문구용
  const [originHost, setOriginHost] = useState('');
  const [tunnelProvider, setTunnelProvider] = useState('');
  // 지금 열려 있는 주소 전부 — 얼굴 전환이 반대쪽을 닫지 않아 여럿일 수 있다
  const [openHosts, setOpenHosts] = useState<Array<{ host: string; provider: string; official: boolean }>>([]);

  // World Pulse 설정 상태
  const [worldConfig, setWorldConfig] = useState<any>(null);
  const [isLoadingWorld, setIsLoadingWorld] = useState(false);
  const [isSavingWorld, setIsSavingWorld] = useState(false);
  const [isRefreshingWorld, setIsRefreshingWorld] = useState(false);
  const [worldSaveResult, setWorldSaveResult] = useState<{ success: boolean; message: string } | null>(null);

  // 시스템 메모(my_profile) — '시스템 AI 역할' 탭에서 편집 (옛 런처 '메모' 버튼 이관)
  const [systemMemo, setSystemMemo] = useState('');
  const [isSavingMemo, setIsSavingMemo] = useState(false);
  const handleSaveMemo = async () => {
    setIsSavingMemo(true);
    try { await api.updateProfile(systemMemo); } catch (e) { console.error('Failed to save memo:', e); }
    setIsSavingMemo(false);
  };

  // 터널 설정 로드 (다이얼로그가 열릴 때 항상 로드 - 외부 URL 표시를 위해)
  // 실패는 throw 되어 useRetryingLoad 가 백오프 재시도한다.
  const loadTunnelHostnames = useCallback(async () => {
    const response = await fetch('http://127.0.0.1:8765/tunnel/config');
    if (response.ok) {
      const data = await response.json();
      setFinderHostname(data.finder_hostname || '');
      setLauncherHostname(data.launcher_hostname || '');
      setOriginHost(data.origin_host || '');
      // 얼굴 축(origin_provider)을 쓴다 — data.provider 는 프로세스 축이라 어긋날 수 있다
      setTunnelProvider(data.origin_provider || data.provider || '');
      setOpenHosts(Array.isArray(data.open_hosts) ? data.open_hosts : []);
    }
  }, []);
  useRetryingLoad(loadTunnelHostnames, { enabled: show });

  // World Pulse 설정 로드
  const loadWorldConfig = useCallback(async () => {
    setIsLoadingWorld(true);
    try {
      const response = await fetch('http://127.0.0.1:8765/world-pulse/config');
      if (response.ok) {
        const data = await response.json();
        setWorldConfig(data);
      }
    } finally {
      setIsLoadingWorld(false);
    }
  }, []);
  useRetryingLoad(loadWorldConfig, { enabled: show && activeTab === 'world' });

  const saveWorldConfig = async () => {
    if (!worldConfig) return;
    try {
      setIsSavingWorld(true);
      const response = await fetch('http://127.0.0.1:8765/world-pulse/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(worldConfig),
      });
      if (response.ok) {
        setWorldSaveResult({ success: true, message: '설정이 저장되었습니다.' });
      } else {
        setWorldSaveResult({ success: false, message: '저장에 실패했습니다.' });
      }
    } catch (err) {
      setWorldSaveResult({ success: false, message: '저장 오류: ' + (err as Error).message });
    } finally {
      setIsSavingWorld(false);
      setTimeout(() => setWorldSaveResult(null), 3000);
    }
  };

  const refreshWorldPulse = async () => {
    try {
      setIsRefreshingWorld(true);
      const response = await fetch('http://127.0.0.1:8765/world-pulse/refresh', { method: 'POST' });
      if (response.ok) {
        setWorldSaveResult({ success: true, message: '세계 상태가 새로 수집되었습니다.' });
      }
    } catch (err) {
      setWorldSaveResult({ success: false, message: '수집 실패: ' + (err as Error).message });
    } finally {
      setIsRefreshingWorld(false);
      setTimeout(() => setWorldSaveResult(null), 3000);
    }
  };

  const loadPromptTemplates = useCallback(async () => {
    setIsLoadingTemplates(true);
    try {
      const data = await api.getPromptTemplates();
      setTemplates(data.templates);
      setSelectedTemplate(data.selected_template);
    } finally {
      setIsLoadingTemplates(false);
    }
  }, []);

  // '시스템 AI 역할' 탭: 프롬프트 템플릿 + 시스템 메모 로드
  const loadPersona = useCallback(async () => {
    await Promise.all([
      loadPromptTemplates(),
      api.getProfile().then(c => setSystemMemo(c || '')),
    ]);
  }, [loadPromptTemplates]);
  useRetryingLoad(loadPersona, { enabled: show && activeTab === 'persona' });

  const handleTemplateChange = async (templateId: string) => {
    try {
      await api.updatePromptConfig({ selected_template: templateId });
      setSelectedTemplate(templateId);
      setTemplates(prev => prev.map(t => ({ ...t, selected: t.id === templateId })));
    } catch (err) {
      console.error('Failed to change template:', err);
    }
  };

  const openRolePromptModal = async () => {
    try {
      const data = await api.getRolePrompt();
      setRolePromptContent(data.content);
      setShowRolePromptModal(true);
    } catch (err) {
      console.error('Failed to load role prompt:', err);
    }
  };

  const saveRolePrompt = async () => {
    try {
      setIsSavingRolePrompt(true);
      await api.updateRolePrompt(rolePromptContent);
      setShowRolePromptModal(false);
    } catch (err) {
      console.error('Failed to save role prompt:', err);
    } finally {
      setIsSavingRolePrompt(false);
    }
  };

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{
          width: 'min(750px, 90vw)',
          height: 'min(650px, 88vh)',
          minWidth: '400px',
          minHeight: '450px',
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

        {/* 탭 */}
        <div className="flex border-b border-gray-200 bg-gray-50 shrink-0">
          {([
            { key: 'models', icon: Brain, label: '모델 설정' },
            { key: 'apikeys', icon: KeyRound, label: 'API 키' },
            { key: 'persona', icon: FileText, label: '시스템 AI 역할' },
            { key: 'channels', icon: Radio, label: '통신채널' },
            { key: 'data', icon: Package, label: '데이터' },
            { key: 'nas', icon: HardDrive, label: '원격 Finder' },
            { key: 'launcher', icon: Monitor, label: '원격 런처' },
            { key: 'tunnel', icon: Cloud, label: '터널' },
            { key: 'world', icon: Globe, label: '월드센싱' },
          ] as const).map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex-1 py-3 text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? 'text-[#D97706] border-b-2 border-[#D97706] bg-white'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              <div className="flex items-center justify-center gap-2">
                <tab.icon size={16} />
                {tab.label}
              </div>
            </button>
          ))}
        </div>

        {/* 내용 */}
        <div className="flex-1 overflow-auto p-6 flex flex-col gap-8">
          {activeTab === 'models' && (
            <div className="space-y-6" style={{ order: 3 }}>
              <div>
                <h2 className="text-base font-bold text-gray-900 mb-1">고급 (실행·의식 — '최대' 기어)</h2>
                <p className="text-sm text-gray-700 mb-4">
                  심사숙고·고품질 실행에 쓰는 본격 모델입니다(옛 '시스템 AI'). 기어 '최대'에서 실행·의식 축이 이 모델을 씁니다. 프로젝트 시작 시 도구 배분·자동 프롬프트 생성에도 활용됩니다.
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
                    <option value="openrouter">OpenRouter (650+ 모델)</option>
                    <option value="claude_code">Claude Code (Max 플랜, CLI 호출)</option>
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
          )}

          {/* 역할 프롬프트 편집 모달 */}
          {showRolePromptModal && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]">
              <div className="bg-white rounded-xl shadow-2xl w-[600px] max-h-[80vh] flex flex-col">
                <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
                  <h3 className="font-semibold text-gray-900">역할 프롬프트 편집</h3>
                  <button
                    onClick={() => setShowRolePromptModal(false)}
                    className="p-1 hover:bg-gray-100 rounded"
                  >
                    <X size={18} className="text-gray-500" />
                  </button>
                </div>
                <div className="flex-1 p-5 overflow-auto">
                  <p className="text-xs text-gray-600 mb-3">
                    시스템 AI의 개별역할을 정의합니다. 프로젝트 에이전트의 role_description과 동일한 개념입니다.
                  </p>
                  <textarea
                    value={rolePromptContent}
                    onChange={(e) => setRolePromptContent(e.target.value)}
                    className="w-full h-80 px-3 py-2 bg-gray-50 border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 font-mono text-sm resize-none"
                    placeholder="역할 프롬프트를 입력하세요..."
                  />
                </div>
                <div className="flex justify-end gap-3 px-5 py-4 border-t border-gray-200">
                  <button
                    onClick={() => setShowRolePromptModal(false)}
                    className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 text-gray-700"
                  >
                    취소
                  </button>
                  <button
                    onClick={saveRolePrompt}
                    disabled={isSavingRolePrompt}
                    className="flex items-center gap-2 px-4 py-2 bg-[#D97706] text-white rounded-lg hover:bg-[#B45309] disabled:opacity-50"
                  >
                    {isSavingRolePrompt ? (
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                    ) : (
                      <Save size={16} />
                    )}
                    저장
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 경량 — 분류·평가·백그라운드 */}
          {activeTab === 'models' && (
            <div className="space-y-6" style={{ order: 1 }}>
              <div>
                <h2 className="text-base font-bold text-gray-900 mb-1">경량 (분류·평가·백그라운드)</h2>
                <p className="text-sm text-gray-700 mb-4">
                  요청 분류, 달성 기준 평가 등 원샷 판단에 쓰는 가장 싸고 빠른 모델입니다. 모든 기어에서 분류·평가는 이 티어를 권장합니다.
                </p>
              </div>

              <div className="bg-gray-50 rounded-lg p-5 space-y-4">
                {/* 제공자 */}
                <div>
                  <label className="block text-sm font-semibold text-gray-900 mb-1">AI 제공자</label>
                  <select
                    value={lightweightSettings.provider}
                    onChange={(e) => onLightweightSettingsChange({ ...lightweightSettings, provider: e.target.value })}
                    className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                  >
                    <option value="google">Google (Gemini)</option>
                    <option value="anthropic">Anthropic (Claude)</option>
                    <option value="openai">OpenAI (GPT)</option>
                    <option value="openrouter">OpenRouter (650+ 모델)</option>
                    <option value="claude_code">Claude Code (Max 플랜, CLI 호출)</option>
                  </select>
                </div>

                {/* 모델 */}
                <div>
                  <label className="block text-sm font-semibold text-gray-900 mb-1">모델</label>
                  <input
                    type="text"
                    value={lightweightSettings.model}
                    onChange={(e) => onLightweightSettingsChange({ ...lightweightSettings, model: e.target.value })}
                    placeholder="gemini-2.5-flash-lite"
                    className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 placeholder:text-gray-500"
                  />
                </div>

                {/* API 키 */}
                <div>
                  <label className="block text-sm font-semibold text-gray-900 mb-1">API 키</label>
                  <div className="flex gap-2">
                    <input
                      type={showLightweightApiKey ? 'text' : 'password'}
                      value={lightweightSettings.apiKey}
                      onChange={(e) => onLightweightSettingsChange({ ...lightweightSettings, apiKey: e.target.value })}
                      placeholder="API 키를 입력하세요 (비워두면 시스템 AI 키 사용)"
                      className="flex-1 px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 placeholder:text-gray-500"
                    />
                    <button
                      onClick={onToggleLightweightApiKey}
                      className="px-3 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 text-gray-700"
                    >
                      {showLightweightApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    비워두면 시스템 AI의 프로바이더를 공유합니다. 별도 모델을 사용하면 비용과 속도를 최적화할 수 있습니다.
                  </p>
                </div>
              </div>

              <div className="bg-blue-50 rounded-lg p-4">
                <p className="text-sm text-blue-800">
                  <strong>경량 AI의 역할:</strong> 사용자 요청이 들어오면 1초 이내에 "실행형(바로 수행)"인지 "판단형(분석 필요)"인지 분류합니다.
                  또한 실행 결과의 달성 기준 평가에도 사용됩니다.
                </p>
              </div>
            </div>
          )}

          {/* 중급 — '균형' 기어의 실행·의식 */}
          {activeTab === 'models' && (
            <div className="space-y-6" style={{ order: 2 }}>
              <div>
                <h2 className="text-base font-bold text-gray-900 mb-1">중급 ('균형' 기어의 실행·의식)</h2>
                <p className="text-sm text-gray-700 mb-4">
                  경량과 고급 사이. 기어 '균형'에서 실행·의식 축이 이 모델을 씁니다. 일상 작업을 빠르되 너무 가볍지 않게.
                </p>
              </div>

              <div className="bg-gray-50 rounded-lg p-5 space-y-4">
                {/* 제공자 */}
                <div>
                  <label className="block text-sm font-semibold text-gray-900 mb-1">AI 제공자</label>
                  <select
                    value={midtierSettings.provider}
                    onChange={(e) => onMidtierSettingsChange({ ...midtierSettings, provider: e.target.value })}
                    className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                  >
                    <option value="google">Google (Gemini)</option>
                    <option value="anthropic">Anthropic (Claude)</option>
                    <option value="openai">OpenAI (GPT)</option>
                    <option value="openrouter">OpenRouter (650+ 모델)</option>
                    <option value="claude_code">Claude Code (Max 플랜, CLI 호출)</option>
                  </select>
                </div>

                {/* 모델 */}
                <div>
                  <label className="block text-sm font-semibold text-gray-900 mb-1">모델</label>
                  <input
                    type="text"
                    value={midtierSettings.model}
                    onChange={(e) => onMidtierSettingsChange({ ...midtierSettings, model: e.target.value })}
                    placeholder="gemini-2.5-flash"
                    className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 placeholder:text-gray-500"
                  />
                </div>

                {/* API 키 */}
                <div>
                  <label className="block text-sm font-semibold text-gray-900 mb-1">API 키</label>
                  <div className="flex gap-2">
                    <input
                      type={showMidtierApiKey ? 'text' : 'password'}
                      value={midtierSettings.apiKey}
                      onChange={(e) => onMidtierSettingsChange({ ...midtierSettings, apiKey: e.target.value })}
                      placeholder="API 키를 입력하세요 (비워두면 시스템 AI 키 사용)"
                      className="flex-1 px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 placeholder:text-gray-500"
                    />
                    <button
                      onClick={onToggleMidtierApiKey}
                      className="px-3 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 text-gray-700"
                    >
                      {showMidtierApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    비워두면 시스템 AI의 키를 사용합니다. 설정하지 않으면 시스템 AI 모델이 그대로 사용됩니다.
                  </p>
                </div>
              </div>

              <div className="bg-amber-50 rounded-lg p-4">
                <p className="text-sm text-amber-800">
                  <strong>중급 AI의 역할:</strong> 단순 실행형 요청(음악 재생, 날씨 확인 등)에서 의식 에이전트를 거치지 않고 바로 실행할 때 사용합니다.
                  복잡한 분석이나 보고서 작성 등 판단형 요청에는 시스템 AI(본격 모델)가 사용됩니다.
                </p>
              </div>
            </div>
          )}

          {/* 시스템 AI 역할 탭 — 프롬프트 템플릿/개별역할 + 시스템 메모 */}
          {activeTab === 'persona' && (
            <div className="space-y-6">
              <div>
                <h2 className="text-base font-bold text-gray-900 mb-1">시스템 AI 역할</h2>
                <p className="text-sm text-gray-700 mb-4">시스템 AI의 프롬프트 템플릿·개별역할과, 에이전트가 늘 참고하는 시스템 메모를 한 곳에서 설정합니다.</p>
              </div>

              {/* 프롬프트 템플릿 설정 */}
              <div className="bg-gray-50 rounded-lg p-5 space-y-4">
                <div className="flex items-center gap-2 mb-3">
                  <FileText size={18} className="text-gray-600" />
                  <h3 className="text-sm font-semibold text-gray-900">프롬프트 템플릿</h3>
                </div>

                {isLoadingTemplates ? (
                  <div className="flex items-center justify-center py-4">
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-[#D97706]" />
                  </div>
                ) : (
                  <>
                    {/* 템플릿 선택 */}
                    <div className="space-y-2">
                      {templates.map(template => (
                        <label
                          key={template.id}
                          className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                            selectedTemplate === template.id
                              ? 'bg-amber-50 border border-amber-200'
                              : 'bg-white border border-gray-200 hover:border-gray-300'
                          }`}
                        >
                          <input
                            type="radio"
                            name="template"
                            value={template.id}
                            checked={selectedTemplate === template.id}
                            onChange={() => handleTemplateChange(template.id)}
                            className="mt-1 accent-[#D97706]"
                          />
                          <div className="flex-1">
                            <div className="flex items-center justify-between">
                              <span className="font-medium text-gray-900">{template.name}</span>
                              <span className="text-xs text-gray-500">{template.tokens.toLocaleString()} 토큰</span>
                            </div>
                            <p className="text-xs text-gray-600 mt-0.5">{template.description}</p>
                          </div>
                        </label>
                      ))}
                    </div>

                    {/* 역할 프롬프트 (개별역할) */}
                    <div className="flex items-center justify-between pt-3 border-t border-gray-200">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-gray-700">역할 프롬프트</span>
                        <span className="text-xs text-gray-500">(시스템 AI의 개별역할)</span>
                      </div>
                      <button
                        onClick={openRolePromptModal}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors text-[#D97706] hover:bg-amber-50"
                      >
                        <Edit3 size={14} />
                        편집
                      </button>
                    </div>
                  </>
                )}
              </div>

              {/* 시스템 메모 (옛 런처 '메모' 버튼 이관) */}
              <div className="bg-gray-50 rounded-lg p-5 space-y-3">
                <div className="flex items-center gap-2">
                  <FileText size={18} className="text-gray-600" />
                  <h3 className="text-sm font-semibold text-gray-900">시스템 메모</h3>
                </div>
                <p className="text-xs text-gray-500">에이전트가 대화 시작 시 늘 참고하는 자유 메모입니다.</p>
                <textarea
                  value={systemMemo}
                  onChange={(e) => setSystemMemo(e.target.value)}
                  placeholder="시스템 AI에게 늘 알려둘 정보를 자유롭게 적으세요..."
                  className="w-full h-48 px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 font-mono text-sm resize-none"
                />
                <div className="flex justify-end">
                  <button
                    onClick={handleSaveMemo}
                    disabled={isSavingMemo}
                    className="flex items-center gap-2 px-4 py-2 bg-[#D97706] text-white rounded-lg hover:bg-[#B45309] disabled:opacity-50"
                  >
                    {isSavingMemo ? <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" /> : <Save size={16} />}
                    메모 저장
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 통신채널 탭 */}
          {activeTab === 'apikeys' && (
            <SettingsEnvTab show={show} />
          )}

          {activeTab === 'channels' && (
            <SettingsChannelsTab show={show} />
          )}

          {/* 데이터 탭 */}
          {activeTab === 'data' && (
            <div className="space-y-6">
              <p className="text-sm text-gray-700">
                설정과 프로젝트를 내보내거나 가져와서 다른 PC에서 동일한 환경을 구성할 수 있습니다.
              </p>

              {/* 내보내기 섹션 */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-5 space-y-4">
                <div className="flex items-center gap-2">
                  <Download size={20} className="text-blue-600" />
                  <h3 className="font-semibold text-gray-900">설정 내보내기</h3>
                </div>
                <p className="text-sm text-gray-600">
                  프로젝트, 에이전트 설정, 역할 프롬프트를 ZIP 파일로 내보냅니다.
                </p>
                <div className="text-xs text-gray-500 space-y-1">
                  <p>✓ 프로젝트 폴더 (에이전트 설정, 역할 프롬프트)</p>
                  <p>✓ 시스템 AI 역할 프롬프트</p>
                  <p>✓ 소유자 정보 (이메일, Nostr 주소)</p>
                  <p className="text-red-500">✗ API 키, OAuth 토큰 (보안상 제외)</p>
                </div>
                <button
                  onClick={async () => {
                    try {
                      setIsExporting(true);
                      setExportResult(null);
                      const response = await fetch('http://127.0.0.1:8765/config/export', { method: 'POST' });
                      if (!response.ok) throw new Error('내보내기 실패');

                      const blob = await response.blob();
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `indiebiz-config-${new Date().toISOString().split('T')[0]}.zip`;
                      a.click();
                      URL.revokeObjectURL(url);

                      setExportResult({ success: true, message: '설정이 내보내졌습니다!' });
                    } catch (err) {
                      console.error('Export failed:', err);
                      setExportResult({ success: false, message: '내보내기 실패: ' + (err as Error).message });
                    } finally {
                      setIsExporting(false);
                    }
                  }}
                  disabled={isExporting}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                  {isExporting ? (
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                  ) : (
                    <Download size={16} />
                  )}
                  ZIP 파일로 내보내기
                </button>
                {exportResult && (
                  <div className={`flex items-center gap-2 text-sm ${exportResult.success ? 'text-green-600' : 'text-red-600'}`}>
                    {exportResult.success ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
                    {exportResult.message}
                  </div>
                )}
              </div>

              {/* 가져오기 섹션 */}
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-5 space-y-4">
                <div className="flex items-center gap-2">
                  <Upload size={20} className="text-amber-600" />
                  <h3 className="font-semibold text-gray-900">설정 가져오기</h3>
                </div>
                <p className="text-sm text-gray-600">
                  다른 PC에서 내보낸 설정 파일을 가져와 적용합니다.
                </p>
                <div className="text-xs text-amber-700 bg-amber-100 p-2 rounded">
                  가져오면 기존 프로젝트와 병합됩니다. 같은 이름의 프로젝트가 있으면 덮어씁니다.
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip"
                  className="hidden"
                  onChange={async (e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;

                    try {
                      setIsImporting(true);
                      setImportResult(null);

                      const formData = new FormData();
                      formData.append('file', file);

                      const response = await fetch('http://127.0.0.1:8765/config/import', {
                        method: 'POST',
                        body: formData,
                      });

                      const result = await response.json();

                      if (response.ok) {
                        setImportResult({
                          success: true,
                          message: `가져오기 완료! ${result.projects_imported || 0}개 프로젝트 추가됨. API 키를 설정해주세요.`
                        });
                      } else {
                        throw new Error(result.detail || '가져오기 실패');
                      }
                    } catch (err) {
                      console.error('Import failed:', err);
                      setImportResult({ success: false, message: '가져오기 실패: ' + (err as Error).message });
                    } finally {
                      setIsImporting(false);
                      if (fileInputRef.current) fileInputRef.current.value = '';
                    }
                  }}
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isImporting}
                  className="flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 transition-colors"
                >
                  {isImporting ? (
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                  ) : (
                    <Upload size={16} />
                  )}
                  ZIP 파일에서 가져오기
                </button>
                {importResult && (
                  <div className={`flex items-center gap-2 text-sm ${importResult.success ? 'text-green-600' : 'text-red-600'}`}>
                    {importResult.success ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
                    {importResult.message}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 원격 Finder / 원격 런처 / 터널 탭 */}
          {(activeTab === 'nas' || activeTab === 'launcher' || activeTab === 'tunnel') && (
            <SettingsRemoteTab
              activeTab={activeTab}
              show={show}
              finderHostname={finderHostname}
              launcherHostname={launcherHostname}
              originHost={originHost}
              tunnelProvider={tunnelProvider}
              openHosts={openHosts}
            />
          )}

          {/* 월드센싱 탭 */}
          {activeTab === 'world' && (
            <div className="space-y-6">
              {isLoadingWorld ? (
                <div className="text-center py-8 text-gray-500">설정 로드 중...</div>
              ) : worldConfig ? (
                <>
                  {/* 활성화 토글 */}
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold text-gray-900">월드센싱</h3>
                      <p className="text-sm text-gray-500 mt-1">하루 1회 세계 상태를 자동 수집하여 에이전트에게 배경 지식으로 제공합니다.</p>
                    </div>
                    <button
                      onClick={() => setWorldConfig({ ...worldConfig, enabled: !worldConfig.enabled })}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                        worldConfig.enabled ? 'bg-[#D97706]' : 'bg-gray-300'
                      }`}
                    >
                      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        worldConfig.enabled ? 'translate-x-6' : 'translate-x-1'
                      }`} />
                    </button>
                  </div>

                  {/* 사용자 프로필 */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">사용자 프로필</label>
                    <p className="text-xs text-gray-400 mb-2">에이전트가 대화 시작 시 참고하는 기본 정보입니다.</p>
                    <div className="space-y-2">
                      {[
                        { key: 'name', label: '이름', placeholder: '홍길동' },
                        { key: 'occupation', label: '직업/역할', placeholder: '개발자, 사업가 등' },
                        { key: 'interests', label: '관심사', placeholder: 'AI, 투자, 음악 등' },
                      ].map(field => (
                        <div key={field.key} className="flex items-center gap-2">
                          <span className="text-sm text-gray-600 w-20 shrink-0">{field.label}</span>
                          <input
                            type="text"
                            value={worldConfig.profile?.[field.key] || ''}
                            onChange={(e) => setWorldConfig({
                              ...worldConfig,
                              profile: { ...worldConfig.profile, [field.key]: e.target.value }
                            })}
                            placeholder={field.placeholder}
                            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-[#D97706] focus:border-transparent"
                          />
                        </div>
                      ))}
                      <div className="flex items-start gap-2">
                        <span className="text-sm text-gray-600 w-20 shrink-0 pt-1.5">메모</span>
                        <textarea
                          value={worldConfig.profile?.memo || ''}
                          onChange={(e) => setWorldConfig({
                            ...worldConfig,
                            profile: { ...worldConfig.profile, memo: e.target.value }
                          })}
                          placeholder="에이전트에게 알려줄 기타 정보"
                          rows={2}
                          className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-[#D97706] focus:border-transparent resize-none"
                        />
                      </div>
                    </div>
                  </div>

                  {/* 위치 설정 */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">위치 (날씨 기준)</label>
                    <input
                      type="text"
                      value={worldConfig.location || ''}
                      onChange={(e) => setWorldConfig({ ...worldConfig, location: e.target.value })}
                      placeholder="Cheongju"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#D97706] focus:border-transparent"
                    />
                  </div>

                  {/* 카테고리별 토글 */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-3">수집 카테고리</label>
                    <div className="space-y-3">
                      {[
                        { key: 'economy', label: '경제 지표', desc: '코스피, 나스닥, 환율, 금, 유가' },
                        { key: 'news', label: '주요 뉴스', desc: '구글 뉴스 헤드라인' },
                        { key: 'tech', label: '기술 동향', desc: 'AI/기술 뉴스' },
                        { key: 'weather', label: '날씨', desc: '설정된 위치의 현재 날씨' },
                      ].map(cat => (
                        <div key={cat.key} className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg">
                          <div>
                            <span className="text-sm font-medium text-gray-900">{cat.label}</span>
                            <span className="text-xs text-gray-500 ml-2">{cat.desc}</span>
                          </div>
                          <button
                            onClick={() => setWorldConfig({
                              ...worldConfig,
                              [cat.key]: { ...worldConfig[cat.key], enabled: !worldConfig[cat.key]?.enabled }
                            })}
                            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                              worldConfig[cat.key]?.enabled !== false ? 'bg-[#D97706]' : 'bg-gray-300'
                            }`}
                          >
                            <span className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                              worldConfig[cat.key]?.enabled !== false ? 'translate-x-5' : 'translate-x-1'
                            }`} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* 경제 지표 커스터마이즈 */}
                  {worldConfig.economy?.enabled !== false && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">경제 지표 심볼</label>
                      <p className="text-xs text-gray-500 mb-2">key=표시이름, value=Yahoo Finance 심볼. 쉼표로 구분하여 추가/제거 가능.</p>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(worldConfig.economy?.symbols || {}).map(([label, symbol]) => (
                          <span key={label} className="inline-flex items-center gap-1 px-2 py-1 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
                            {label}: {symbol as string}
                            <button
                              onClick={() => {
                                const newSymbols = { ...worldConfig.economy.symbols };
                                delete newSymbols[label];
                                setWorldConfig({
                                  ...worldConfig,
                                  economy: { ...worldConfig.economy, symbols: newSymbols }
                                });
                              }}
                              className="ml-1 text-amber-600 hover:text-red-600"
                            >
                              <X size={12} />
                            </button>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 뉴스 검색어 */}
                  {worldConfig.news?.enabled !== false && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">뉴스 검색 키워드</label>
                      <input
                        type="text"
                        value={worldConfig.news?.query || ''}
                        onChange={(e) => setWorldConfig({
                          ...worldConfig,
                          news: { ...worldConfig.news, query: e.target.value }
                        })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#D97706] focus:border-transparent"
                      />
                    </div>
                  )}

                  {/* 기술 검색어 */}
                  {worldConfig.tech?.enabled !== false && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">기술 뉴스 검색 키워드</label>
                      <input
                        type="text"
                        value={worldConfig.tech?.query || ''}
                        onChange={(e) => setWorldConfig({
                          ...worldConfig,
                          tech: { ...worldConfig.tech, query: e.target.value }
                        })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#D97706] focus:border-transparent"
                      />
                    </div>
                  )}

                  {/* 액션 버튼 */}
                  <div className="flex items-center gap-3 pt-2">
                    <button
                      onClick={saveWorldConfig}
                      disabled={isSavingWorld}
                      className="flex items-center gap-2 px-4 py-2 bg-[#D97706] text-white rounded-lg hover:bg-[#B45309] disabled:opacity-50 transition-colors"
                    >
                      <Save size={16} />
                      {isSavingWorld ? '저장 중...' : '설정 저장'}
                    </button>
                    <button
                      onClick={refreshWorldPulse}
                      disabled={isRefreshingWorld}
                      className="flex items-center gap-2 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 transition-colors"
                    >
                      <RefreshCw size={16} className={isRefreshingWorld ? 'animate-spin' : ''} />
                      {isRefreshingWorld ? '수집 중...' : '지금 수집'}
                    </button>
                    {worldSaveResult && (
                      <div className={`flex items-center gap-1 text-sm ${worldSaveResult.success ? 'text-green-600' : 'text-red-600'}`}>
                        {worldSaveResult.success ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
                        {worldSaveResult.message}
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="text-center py-8 text-gray-500">설정을 불러올 수 없습니다.</div>
              )}
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
          {activeTab === 'models' && (
            <button
              onClick={onSave}
              className="flex items-center gap-2 px-4 py-2 bg-[#D97706] text-white rounded-lg hover:bg-[#B45309]"
            >
              <Save size={16} />
              저장
            </button>
          )}
        </div>
      </div>
    </div>
  );
}