/**
 * ToolboxDialog - 도구 패키지 관리
 *
 * 기능:
 * - 도구 패키지 설치/제거
 * - AI로 폴더 분석하여 패키지 등록
 * - 등록된 패키지 삭제
 */

import { useState, useEffect } from 'react';
import { X, Package, Download, Trash2, Check, AlertCircle, FolderOpen, ChevronDown, ChevronRight, FolderPlus, XCircle, Sparkles, Loader2 } from 'lucide-react';
import { api } from '../../../lib/api';

interface PackageInfo {
  id: string;
  name: string;
  description: string;
  version?: string;
  author?: string;
  type: 'tools';
  icon?: string;
  installed: boolean;
  package_type?: string;
  files?: string[];
  tools?: Array<{ name: string; description: string }>;
}

interface ToolboxDialogProps {
  show: boolean;
  onClose: () => void;
}

interface AIAnalysisResult {
  valid: boolean | null;
  folder_name?: string;
  folder_path?: string;
  files?: string[];
  error?: string;
  reason?: string;
  package_name?: string;
  package_description?: string;
  tools?: Array<{ name: string; description: string }>;
  readme_content?: string;
  can_auto_generate?: boolean;
}

interface RegisterDialogState {
  show: boolean;
  folderPath: string;
  step: 'input' | 'analyzing' | 'result';
  analysis: AIAnalysisResult | null;
  name: string;
  description: string;
  readmeContent: string;
}

export function ToolboxDialog({ show, onClose }: ToolboxDialogProps) {
  const [packages, setPackages] = useState<PackageInfo[]>([]);
  const [selectedPackage, setSelectedPackage] = useState<PackageInfo | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [installedExpanded, setInstalledExpanded] = useState(true);
  const [availableExpanded, setAvailableExpanded] = useState(true);

  // 폴더 등록 다이얼로그 상태
  const [registerDialog, setRegisterDialog] = useState<RegisterDialogState>({
    show: false,
    folderPath: '',
    step: 'input',
    analysis: null,
    name: '',
    description: '',
    readmeContent: '',
  });

  useEffect(() => {
    if (show) {
      loadPackages();
    }
  }, [show]);

  const loadPackages = async () => {
    setIsLoading(true);
    try {
      const response = await api.getPackages();
      const allPackages = [...response.available];
      setPackages(allPackages);
    } catch (error) {
      console.error('패키지 로드 실패:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleInstall = async (pkg: PackageInfo) => {
    setActionLoading(pkg.id);
    setMessage(null);
    try {
      await api.installPackage(pkg.id);
      setMessage({ type: 'success', text: `'${pkg.name}' 설치 완료` });
      await loadPackages();
      if (selectedPackage?.id === pkg.id) {
        setSelectedPackage({ ...selectedPackage, installed: true });
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || '설치 실패' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleUninstall = async (pkg: PackageInfo) => {
    setActionLoading(pkg.id);
    setMessage(null);
    try {
      await api.uninstallPackage(pkg.id);
      setMessage({ type: 'success', text: `'${pkg.name}' 제거 완료` });
      await loadPackages();
      if (selectedPackage?.id === pkg.id) {
        setSelectedPackage({ ...selectedPackage, installed: false });
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || '제거 실패' });
    } finally {
      setActionLoading(null);
    }
  };

  // 패키지 삭제 (목록에서 완전히 제거)
  const handleRemovePackage = async (pkg: PackageInfo) => {
    if (!confirm(`'${pkg.name}' 패키지를 목록에서 완전히 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없습니다.`)) {
      return;
    }

    setActionLoading(pkg.id);
    setMessage(null);
    try {
      await api.removePackage(pkg.id);
      setMessage({ type: 'success', text: `'${pkg.name}' 패키지가 삭제되었습니다` });
      setSelectedPackage(null);
      await loadPackages();
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || '삭제 실패' });
    } finally {
      setActionLoading(null);
    }
  };

  // 폴더 등록 다이얼로그 열기
  const openRegisterDialog = () => {
    setRegisterDialog({
      show: true,
      folderPath: '',
      step: 'input',
      analysis: null,
      name: '',
      description: '',
      readmeContent: '',
    });
  };

  // AI로 폴더 분석
  const analyzeWithAI = async () => {
    if (!registerDialog.folderPath.trim()) return;

    setRegisterDialog(prev => ({ ...prev, step: 'analyzing' }));

    try {
      const result = await api.analyzeFolderWithAI(registerDialog.folderPath);
      setRegisterDialog(prev => ({
        ...prev,
        step: 'result',
        analysis: result,
        name: result.package_name || result.folder_name || '',
        description: result.package_description || '',
        readmeContent: result.readme_content || '',
      }));
    } catch (error: any) {
      setRegisterDialog(prev => ({
        ...prev,
        step: 'result',
        analysis: { valid: false, error: error.message || '분석 실패' },
      }));
    }
  };

  // 폴더 등록 실행
  const handleRegisterFolder = async () => {
    const { folderPath, name, description, readmeContent } = registerDialog;

    setActionLoading('register');
    try {
      await api.registerFolder(folderPath, name, description, readmeContent);
      setMessage({ type: 'success', text: `'${name}' 패키지가 등록되었습니다` });
      setRegisterDialog(prev => ({ ...prev, show: false }));
      await loadPackages();
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || '등록 실패' });
    } finally {
      setActionLoading(null);
    }
  };

  if (!show) return null;

  const installedPackages = packages.filter(p => p.installed);
  const availablePackages = packages.filter(p => !p.installed);

  const renderPackageItem = (pkg: PackageInfo) => (
    <div
      key={pkg.id}
      onClick={() => setSelectedPackage(pkg)}
      className={`p-3 rounded-lg cursor-pointer transition-all ${
        selectedPackage?.id === pkg.id
          ? 'bg-indigo-50 border-2 border-indigo-300'
          : 'bg-white border border-gray-200 hover:border-gray-300 hover:shadow-sm'
      }`}
    >
      <div className="flex items-center gap-3">
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
          pkg.installed
            ? 'bg-green-100 text-green-600'
            : 'bg-gray-100 text-gray-500'
        }`}>
          <Package size={20} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-medium text-gray-800 text-sm truncate">{pkg.name}</h3>
          <p className="text-xs text-gray-500 truncate">{pkg.description || '설명 없음'}</p>
        </div>
        {/* 빠른 액션 버튼 */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            pkg.installed ? handleUninstall(pkg) : handleInstall(pkg);
          }}
          disabled={actionLoading === pkg.id}
          className={`p-1.5 rounded-lg shrink-0 transition-colors ${
            pkg.installed
              ? 'text-red-500 hover:bg-red-50'
              : 'text-green-500 hover:bg-green-50'
          } ${actionLoading === pkg.id ? 'opacity-50' : ''}`}
          title={pkg.installed ? '제거' : '설치'}
        >
          {actionLoading === pkg.id ? (
            <Loader2 size={16} className="animate-spin" />
          ) : pkg.installed ? (
            <Trash2 size={16} />
          ) : (
            <Download size={16} />
          )}
        </button>
      </div>
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{
          width: 'min(850px, 90vw)',
          height: 'min(650px, 85vh)',
        }}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-indigo-50 to-purple-50 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <Package size={22} className="text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-800">도구 관리</h2>
              <p className="text-xs text-gray-500">패키지 설치 및 관리</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={openRegisterDialog}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors"
              title="폴더에서 패키지 등록"
            >
              <FolderPlus size={16} />
              <span>등록</span>
            </button>
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-200 rounded-lg transition-colors"
            >
              <X size={20} className="text-gray-500" />
            </button>
          </div>
        </div>

        {/* 메시지 */}
        {message && (
          <div className={`mx-4 mt-3 p-2.5 rounded-lg flex items-center gap-2 ${
            message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          }`}>
            {message.type === 'success' ? <Check size={16} /> : <AlertCircle size={16} />}
            <span className="text-sm">{message.text}</span>
          </div>
        )}

        {/* 컨텐츠 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 패키지 목록 */}
          <div className="w-1/2 border-r border-gray-200 overflow-y-auto p-4 bg-gray-50">
            {isLoading ? (
              <div className="flex items-center justify-center h-full text-gray-400">
                <Loader2 size={24} className="animate-spin mr-2" />
                로딩 중...
              </div>
            ) : packages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-400">
                <Package size={48} className="mb-3 opacity-50" />
                <p className="text-sm">패키지가 없습니다</p>
                <button
                  onClick={openRegisterDialog}
                  className="mt-3 text-sm text-indigo-500 hover:text-indigo-600"
                >
                  폴더에서 등록하기
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {/* 설치됨 섹션 */}
                <div>
                  <button
                    onClick={() => setInstalledExpanded(!installedExpanded)}
                    className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2 hover:text-gray-900"
                  >
                    {installedExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    <span className="flex items-center gap-2">
                      설치됨
                      <span className="text-xs px-1.5 py-0.5 bg-green-100 text-green-600 rounded">
                        {installedPackages.length}
                      </span>
                    </span>
                  </button>
                  {installedExpanded && (
                    <div className="space-y-2 ml-1">
                      {installedPackages.length === 0 ? (
                        <p className="text-xs text-gray-400 py-2">설치된 패키지가 없습니다</p>
                      ) : (
                        installedPackages.map(renderPackageItem)
                      )}
                    </div>
                  )}
                </div>

                {/* 설치 가능 섹션 */}
                <div>
                  <button
                    onClick={() => setAvailableExpanded(!availableExpanded)}
                    className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2 hover:text-gray-900"
                  >
                    {availableExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    <span className="flex items-center gap-2">
                      설치 가능
                      <span className="text-xs px-1.5 py-0.5 bg-gray-200 text-gray-600 rounded">
                        {availablePackages.length}
                      </span>
                    </span>
                  </button>
                  {availableExpanded && (
                    <div className="space-y-2 ml-1">
                      {availablePackages.length === 0 ? (
                        <p className="text-xs text-gray-400 py-2">모든 패키지가 설치되어 있습니다</p>
                      ) : (
                        availablePackages.map(renderPackageItem)
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* 패키지 상세 */}
          <div className="w-1/2 overflow-y-auto p-4">
            {selectedPackage ? (
              <div className="space-y-4">
                {/* 헤더 */}
                <div className="flex items-start gap-4">
                  <div className={`w-14 h-14 rounded-xl flex items-center justify-center ${
                    selectedPackage.installed
                      ? 'bg-green-100 text-green-600'
                      : 'bg-indigo-100 text-indigo-600'
                  }`}>
                    <Package size={28} />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-xl font-bold text-gray-800">{selectedPackage.name}</h3>
                      {selectedPackage.installed && (
                        <span className="text-xs px-2 py-0.5 bg-green-100 text-green-600 rounded-full">
                          설치됨
                        </span>
                      )}
                    </div>
                    {selectedPackage.version && (
                      <p className="text-sm text-gray-500">v{selectedPackage.version}</p>
                    )}
                  </div>
                </div>

                {/* 설명 */}
                <p className="text-sm text-gray-700 leading-relaxed">
                  {selectedPackage.description || '설명이 없습니다.'}
                </p>

                {/* 파일 목록 */}
                {selectedPackage.files && selectedPackage.files.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 mb-2">포함된 파일</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedPackage.files.slice(0, 10).map((file, idx) => (
                        <span key={idx} className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
                          {file}
                        </span>
                      ))}
                      {selectedPackage.files.length > 10 && (
                        <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-500 rounded">
                          +{selectedPackage.files.length - 10}개
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* 도구 목록 */}
                {selectedPackage.tools && selectedPackage.tools.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 mb-2">제공하는 도구</h4>
                    <ul className="space-y-1.5">
                      {selectedPackage.tools.map((tool, idx) => (
                        <li key={idx} className="text-sm text-gray-600 flex items-start gap-2">
                          <span className="text-indigo-500 mt-1">•</span>
                          <div>
                            <span className="font-medium">{tool.name}</span>
                            <span className="text-gray-400"> - {tool.description}</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 액션 버튼 */}
                <div className="pt-4 border-t border-gray-200 space-y-2">
                  {selectedPackage.installed ? (
                    <button
                      onClick={() => handleUninstall(selectedPackage)}
                      disabled={actionLoading === selectedPackage.id}
                      className="w-full px-4 py-2.5 bg-red-100 text-red-600 rounded-lg hover:bg-red-200 disabled:opacity-50 flex items-center justify-center gap-2 transition-colors font-medium"
                    >
                      {actionLoading === selectedPackage.id ? (
                        <Loader2 size={18} className="animate-spin" />
                      ) : (
                        <Trash2 size={18} />
                      )}
                      {actionLoading === selectedPackage.id ? '제거 중...' : '제거하기'}
                    </button>
                  ) : (
                    <button
                      onClick={() => handleInstall(selectedPackage)}
                      disabled={actionLoading === selectedPackage.id}
                      className="w-full px-4 py-2.5 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 disabled:opacity-50 flex items-center justify-center gap-2 transition-colors font-medium"
                    >
                      {actionLoading === selectedPackage.id ? (
                        <Loader2 size={18} className="animate-spin" />
                      ) : (
                        <Download size={18} />
                      )}
                      {actionLoading === selectedPackage.id ? '설치 중...' : '설치하기'}
                    </button>
                  )}

                  {/* 패키지 삭제 버튼 */}
                  <button
                    onClick={() => handleRemovePackage(selectedPackage)}
                    disabled={actionLoading === selectedPackage.id}
                    className="w-full px-4 py-2 text-gray-500 rounded-lg hover:bg-gray-100 disabled:opacity-50 flex items-center justify-center gap-2 transition-colors text-sm"
                  >
                    <XCircle size={16} />
                    목록에서 삭제
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-gray-400">
                <Package size={48} className="mb-3 opacity-50" />
                <p className="text-sm">패키지를 선택하세요</p>
                <p className="text-xs mt-1 text-center">
                  에이전트가 사용할 도구를 관리합니다
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 폴더 등록 다이얼로그 */}
      {registerDialog.show && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-60">
          <div className="bg-white rounded-xl shadow-2xl w-[550px] max-w-[90vw]">
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <div className="flex items-center gap-2">
                <Sparkles size={20} className="text-indigo-500" />
                <h3 className="font-bold text-gray-800">AI로 도구 패키지 등록</h3>
              </div>
              <button
                onClick={() => setRegisterDialog(prev => ({ ...prev, show: false }))}
                className="p-1 hover:bg-gray-100 rounded"
              >
                <X size={18} className="text-gray-500" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* Step 1: 폴더 경로 입력 */}
              {registerDialog.step === 'input' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      폴더 경로
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={registerDialog.folderPath}
                        onChange={(e) => setRegisterDialog(prev => ({ ...prev, folderPath: e.target.value }))}
                        placeholder="/path/to/tool/folder"
                        className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                      />
                      <button
                        onClick={async () => {
                          if (window.electron?.selectFolder) {
                            const folderPath = await window.electron.selectFolder();
                            if (folderPath) {
                              setRegisterDialog(prev => ({ ...prev, folderPath }));
                            }
                          }
                        }}
                        className="px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors flex items-center gap-1.5 text-gray-700 shrink-0"
                        title="폴더 선택"
                      >
                        <FolderOpen size={18} />
                        <span className="text-sm">찾아보기</span>
                      </button>
                    </div>
                  </div>
                  <p className="text-xs text-gray-500">
                    AI가 폴더 내용을 분석하여 도구 패키지로 등록 가능한지 판별하고, README를 자동 생성합니다.
                  </p>
                </>
              )}

              {/* Step 2: 분석 중 */}
              {registerDialog.step === 'analyzing' && (
                <div className="flex flex-col items-center py-8">
                  <Loader2 size={40} className="animate-spin text-indigo-500 mb-4" />
                  <p className="text-gray-700 font-medium">AI가 폴더를 분석하고 있습니다...</p>
                  <p className="text-sm text-gray-500 mt-1">잠시만 기다려 주세요</p>
                </div>
              )}

              {/* Step 3: 분석 결과 */}
              {registerDialog.step === 'result' && registerDialog.analysis && (
                <>
                  {registerDialog.analysis.valid === false ? (
                    <div className="p-4 bg-red-50 rounded-lg">
                      <div className="flex items-start gap-3">
                        <AlertCircle size={20} className="text-red-500 shrink-0 mt-0.5" />
                        <div>
                          <p className="text-red-700 font-medium">등록할 수 없는 폴더입니다</p>
                          <p className="text-sm text-red-600 mt-1">
                            {registerDialog.analysis.error || registerDialog.analysis.reason}
                          </p>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="p-4 bg-green-50 rounded-lg">
                        <div className="flex items-start gap-3">
                          <Check size={20} className="text-green-500 shrink-0 mt-0.5" />
                          <div>
                            <p className="text-green-700 font-medium">등록 가능한 패키지입니다</p>
                            <p className="text-sm text-green-600 mt-1">
                              {registerDialog.analysis.reason}
                            </p>
                          </div>
                        </div>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          패키지 이름
                        </label>
                        <input
                          type="text"
                          value={registerDialog.name}
                          onChange={(e) => setRegisterDialog(prev => ({ ...prev, name: e.target.value }))}
                          className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          설명
                        </label>
                        <input
                          type="text"
                          value={registerDialog.description}
                          onChange={(e) => setRegisterDialog(prev => ({ ...prev, description: e.target.value }))}
                          className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                        />
                      </div>

                      {registerDialog.analysis.tools && registerDialog.analysis.tools.length > 0 && (
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            발견된 도구
                          </label>
                          <ul className="space-y-1">
                            {registerDialog.analysis.tools.map((tool, idx) => (
                              <li key={idx} className="text-sm text-gray-600 flex items-center gap-2">
                                <span className="text-indigo-500">•</span>
                                <span className="font-medium">{tool.name}</span>
                                <span className="text-gray-400">- {tool.description}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {registerDialog.readmeContent && (
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            README (AI 생성)
                          </label>
                          <textarea
                            value={registerDialog.readmeContent}
                            onChange={(e) => setRegisterDialog(prev => ({ ...prev, readmeContent: e.target.value }))}
                            rows={5}
                            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 resize-none font-mono text-xs"
                          />
                        </div>
                      )}
                    </>
                  )}
                </>
              )}
            </div>

            <div className="flex justify-end gap-2 px-5 py-4 border-t bg-gray-50">
              {registerDialog.step === 'input' && (
                <>
                  <button
                    onClick={() => setRegisterDialog(prev => ({ ...prev, show: false }))}
                    className="px-4 py-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors"
                  >
                    취소
                  </button>
                  <button
                    onClick={analyzeWithAI}
                    disabled={!registerDialog.folderPath.trim()}
                    className="px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                  >
                    <Sparkles size={16} />
                    AI로 분석
                  </button>
                </>
              )}

              {registerDialog.step === 'result' && (
                <>
                  <button
                    onClick={() => setRegisterDialog(prev => ({ ...prev, step: 'input', analysis: null }))}
                    className="px-4 py-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors"
                  >
                    다시 선택
                  </button>
                  {registerDialog.analysis?.valid !== false && (
                    <button
                      onClick={handleRegisterFolder}
                      disabled={actionLoading === 'register' || !registerDialog.name}
                      className="px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                    >
                      {actionLoading === 'register' ? (
                        <>
                          <Loader2 size={16} className="animate-spin" />
                          등록 중...
                        </>
                      ) : (
                        <>
                          <FolderPlus size={16} />
                          등록
                        </>
                      )}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
