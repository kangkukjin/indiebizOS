/**
 * SettingsDialog - 시스템 설정 다이얼로그
 *
 * 탭별 서브 컴포넌트:
 *   SettingsChannelsTab.tsx - 통신채널 설정
 *   SettingsRemoteTab.tsx   - 원격 Finder / 원격 런처 / Cloudflare 터널
 */

import { useEffect, useState, useRef } from 'react';
import { X, Settings, Brain, Eye, EyeOff, Save, Radio, Package, CheckCircle, AlertCircle, HardDrive, Download, Upload, Monitor, Cloud, FileText, Edit3 } from 'lucide-react';
import type { SystemAISettings } from '../types';
import { api } from '../../../lib/api';
import { SettingsChannelsTab } from './SettingsChannelsTab';
import { SettingsRemoteTab } from './SettingsRemoteTab';

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
  const [activeTab, setActiveTab] = useState<'ai' | 'channels' | 'data' | 'nas' | 'launcher' | 'tunnel'>('ai');

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

  // 프롬프트 템플릿 로드
  useEffect(() => {
    if (show && activeTab === 'ai') {
      loadPromptTemplates();
    }
  }, [show, activeTab]);

  // 터널 설정 로드 (다이얼로그가 열릴 때 항상 로드 - 외부 URL 표시를 위해)
  useEffect(() => {
    if (show) {
      loadTunnelHostnames();
    }
  }, [show]);

  const loadTunnelHostnames = async () => {
    try {
      const response = await fetch('http://127.0.0.1:8765/tunnel/config');
      if (response.ok) {
        const data = await response.json();
        setFinderHostname(data.finder_hostname || '');
        setLauncherHostname(data.launcher_hostname || '');
      }
    } catch (err) {
      console.error('Failed to load tunnel config:', err);
    }
  };

  const loadPromptTemplates = async () => {
    try {
      setIsLoadingTemplates(true);
      const data = await api.getPromptTemplates();
      setTemplates(data.templates);
      setSelectedTemplate(data.selected_template);
    } catch (err) {
      console.error('Failed to load prompt templates:', err);
    } finally {
      setIsLoadingTemplates(false);
    }
  };

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
          width: 'min(600px, 90vw)',
          height: 'min(550px, 85vh)',
          minWidth: '350px',
          minHeight: '400px',
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
            { key: 'ai', icon: Brain, label: '시스템 AI' },
            { key: 'channels', icon: Radio, label: '통신채널' },
            { key: 'data', icon: Package, label: '데이터' },
            { key: 'nas', icon: HardDrive, label: '원격 Finder' },
            { key: 'launcher', icon: Monitor, label: '원격 런처' },
            { key: 'tunnel', icon: Cloud, label: '터널' },
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
        <div className="flex-1 overflow-auto p-6">
          {activeTab === 'ai' && (
            <div className="space-y-6">
              <div>
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

          {/* 통신채널 탭 */}
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
            />
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
          {activeTab === 'ai' && (
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
