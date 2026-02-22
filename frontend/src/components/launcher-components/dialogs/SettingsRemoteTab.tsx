/**
 * SettingsRemoteTab - 원격 접속 관련 설정 탭 (NAS, 런처, 터널)
 */

import { useEffect, useState } from 'react';
import { Save, HardDrive, FolderOpen, Plus, Trash2, Monitor, CheckCircle, AlertCircle } from 'lucide-react';

interface SettingsRemoteTabProps {
  activeTab: 'nas' | 'launcher' | 'tunnel';
  show: boolean;
  finderHostname: string;
  launcherHostname: string;
}

export function SettingsRemoteTab({ activeTab, show, finderHostname, launcherHostname }: SettingsRemoteTabProps) {
  // NAS 설정 상태
  const [nasEnabled, setNasEnabled] = useState(false);
  const [nasHasPassword, setNasHasPassword] = useState(false);
  const [nasPassword, setNasPassword] = useState('');
  const [nasAllowedPaths, setNasAllowedPaths] = useState<string[]>([]);
  const [nasNewPath, setNasNewPath] = useState('');
  const [isLoadingNas, setIsLoadingNas] = useState(false);
  const [nasSaveResult, setNasSaveResult] = useState<{ success: boolean; message: string } | null>(null);

  // 원격 런처 설정 상태
  const [launcherEnabled, setLauncherEnabled] = useState(false);
  const [launcherHasPassword, setLauncherHasPassword] = useState(false);
  const [launcherPassword, setLauncherPassword] = useState('');
  const [isLoadingLauncher, setIsLoadingLauncher] = useState(false);
  const [launcherSaveResult, setLauncherSaveResult] = useState<{ success: boolean; message: string } | null>(null);

  // Cloudflare 터널 설정 상태
  const [tunnelRunning, setTunnelRunning] = useState(false);
  const [tunnelAutoStart, setTunnelAutoStart] = useState(false);
  const [tunnelName, setTunnelName] = useState('');
  const [tunnelHostname, setTunnelHostname] = useState('');
  const [tunnelCloudflaredInstalled, setTunnelCloudflaredInstalled] = useState(false);
  const [isLoadingTunnel, setIsLoadingTunnel] = useState(false);
  const [isTunnelToggling, setIsTunnelToggling] = useState(false);
  const [tunnelSaveResult, setTunnelSaveResult] = useState<{ success: boolean; message: string } | null>(null);

  // NAS 설정 로드
  useEffect(() => {
    if (show && activeTab === 'nas') {
      loadNasConfig();
    }
  }, [show, activeTab]);

  // 원격 런처 설정 로드
  useEffect(() => {
    if (show && activeTab === 'launcher') {
      loadLauncherConfig();
    }
  }, [show, activeTab]);

  // 터널 설정 로드
  useEffect(() => {
    if (show && activeTab === 'tunnel') {
      loadTunnelConfig();
    }
  }, [show, activeTab]);

  const loadNasConfig = async () => {
    try {
      setIsLoadingNas(true);
      const response = await fetch('http://127.0.0.1:8765/nas/config');
      if (response.ok) {
        const data = await response.json();
        setNasEnabled(data.enabled || false);
        setNasHasPassword(data.has_password || false);
        setNasAllowedPaths(data.allowed_paths || []);
      }
    } catch (err) {
      console.error('Failed to load NAS config:', err);
    } finally {
      setIsLoadingNas(false);
    }
  };

  const saveNasConfig = async () => {
    try {
      setNasSaveResult(null);
      const body: any = {
        enabled: nasEnabled,
        allowed_paths: nasAllowedPaths,
      };
      if (nasPassword) {
        body.password = nasPassword;
      }

      const response = await fetch('http://127.0.0.1:8765/nas/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (response.ok) {
        setNasSaveResult({ success: true, message: '설정이 저장되었습니다' });
        setNasPassword('');
        setNasHasPassword(true);
        setTimeout(() => setNasSaveResult(null), 3000);
      } else {
        const err = await response.json();
        setNasSaveResult({ success: false, message: err.detail || '저장 실패' });
      }
    } catch (err) {
      setNasSaveResult({ success: false, message: '저장 실패: ' + (err as Error).message });
    }
  };

  const addNasPath = () => {
    if (nasNewPath.trim() && !nasAllowedPaths.includes(nasNewPath.trim())) {
      setNasAllowedPaths([...nasAllowedPaths, nasNewPath.trim()]);
      setNasNewPath('');
    }
  };

  const addNasPathByDialog = async () => {
    if (window.electron?.selectFolder) {
      const folderPath = await window.electron.selectFolder();
      if (folderPath && !nasAllowedPaths.includes(folderPath)) {
        setNasAllowedPaths([...nasAllowedPaths, folderPath]);
      }
    }
  };

  const removeNasPath = (path: string) => {
    setNasAllowedPaths(nasAllowedPaths.filter(p => p !== path));
  };

  const loadLauncherConfig = async () => {
    try {
      setIsLoadingLauncher(true);
      const response = await fetch('http://127.0.0.1:8765/launcher/config');
      if (response.ok) {
        const data = await response.json();
        setLauncherEnabled(data.enabled || false);
        setLauncherHasPassword(data.has_password || false);
      }
    } catch (err) {
      console.error('Failed to load launcher config:', err);
    } finally {
      setIsLoadingLauncher(false);
    }
  };

  const saveLauncherConfig = async () => {
    try {
      setLauncherSaveResult(null);
      const body: any = {
        enabled: launcherEnabled,
      };
      if (launcherPassword) {
        body.password = launcherPassword;
      }

      const response = await fetch('http://127.0.0.1:8765/launcher/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (response.ok) {
        setLauncherSaveResult({ success: true, message: '설정이 저장되었습니다' });
        setLauncherPassword('');
        setLauncherHasPassword(true);
        setTimeout(() => setLauncherSaveResult(null), 3000);
      } else {
        const err = await response.json();
        setLauncherSaveResult({ success: false, message: err.detail || '저장 실패' });
      }
    } catch (err) {
      setLauncherSaveResult({ success: false, message: '저장 실패: ' + (err as Error).message });
    }
  };

  const loadTunnelConfig = async () => {
    try {
      setIsLoadingTunnel(true);
      const response = await fetch('http://127.0.0.1:8765/tunnel/config');
      if (response.ok) {
        const data = await response.json();
        setTunnelRunning(data.running || false);
        setTunnelAutoStart(data.auto_start || false);
        setTunnelName(data.tunnel_name || '');
        setTunnelHostname(data.hostname || '');
        setTunnelCloudflaredInstalled(data.cloudflared_installed || false);
      }
    } catch (err) {
      console.error('Failed to load tunnel config:', err);
    } finally {
      setIsLoadingTunnel(false);
    }
  };

  const saveTunnelConfig = async () => {
    try {
      setTunnelSaveResult(null);
      const response = await fetch('http://127.0.0.1:8765/tunnel/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          auto_start: tunnelAutoStart,
          tunnel_name: tunnelName,
          hostname: tunnelHostname,
        }),
      });

      if (response.ok) {
        setTunnelSaveResult({ success: true, message: '설정이 저장되었습니다' });
        setTimeout(() => setTunnelSaveResult(null), 3000);
      } else {
        const err = await response.json();
        setTunnelSaveResult({ success: false, message: err.detail || '저장 실패' });
      }
    } catch (err) {
      setTunnelSaveResult({ success: false, message: '저장 실패: ' + (err as Error).message });
    }
  };

  const toggleTunnel = async () => {
    try {
      setIsTunnelToggling(true);
      setTunnelSaveResult(null);

      const endpoint = tunnelRunning ? '/tunnel/stop' : '/tunnel/start';
      const response = await fetch(`http://127.0.0.1:8765${endpoint}`, {
        method: 'POST',
      });

      const data = await response.json();
      if (data.success) {
        setTunnelRunning(!tunnelRunning);
        setTunnelSaveResult({
          success: true,
          message: tunnelRunning ? '터널이 종료되었습니다' : '터널이 시작되었습니다'
        });
      } else {
        const errorMsg = data.details
          ? `${data.error}: ${data.details}`
          : (data.error || '실패');
        setTunnelSaveResult({ success: false, message: errorMsg });
      }
      setTimeout(() => setTunnelSaveResult(null), 5000);
    } catch (err) {
      setTunnelSaveResult({ success: false, message: '요청 실패: ' + (err as Error).message });
    } finally {
      setIsTunnelToggling(false);
    }
  };

  // NAS 탭
  if (activeTab === 'nas') {
    return (
      <div className="space-y-6">
        <div>
          <p className="text-sm text-gray-700 mb-4">
            원격 Finder를 활성화하면 외부에서 Cloudflare Tunnel을 통해 PC의 파일에 접근할 수 있습니다.
          </p>
        </div>

        {isLoadingNas ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[#D97706]" />
          </div>
        ) : (
          <>
            {/* 활성화 토글 */}
            <div className="bg-gray-50 rounded-lg p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <HardDrive size={20} className="text-gray-600" />
                  <div>
                    <h3 className="font-semibold text-gray-900">원격 Finder 활성화</h3>
                    <p className="text-xs text-gray-500">외부에서 파일 접근 허용</p>
                  </div>
                </div>
                <button
                  onClick={() => setNasEnabled(!nasEnabled)}
                  className={`relative w-12 h-6 rounded-full transition-colors ${
                    nasEnabled ? 'bg-[#D97706]' : 'bg-gray-300'
                  }`}
                >
                  <div
                    className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                      nasEnabled ? 'translate-x-6' : ''
                    }`}
                  />
                </button>
              </div>

              {nasEnabled && (
                <div className="pt-3 border-t border-gray-200 space-y-4">
                  {/* 비밀번호 설정 */}
                  <div>
                    <label className="block text-sm font-semibold text-gray-900 mb-1">
                      접근 비밀번호 {nasHasPassword ? '(설정됨)' : '(미설정)'}
                    </label>
                    <input
                      type="password"
                      value={nasPassword}
                      onChange={(e) => setNasPassword(e.target.value)}
                      placeholder={nasHasPassword ? '새 비밀번호로 변경' : '비밀번호 설정'}
                      className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                    />
                    <p className="text-xs text-gray-500 mt-1">외부 접속 시 이 비밀번호가 필요합니다</p>
                  </div>

                  {/* 허용 경로 */}
                  <div>
                    <label className="block text-sm font-semibold text-gray-900 mb-1">
                      접근 허용 경로
                    </label>
                    <p className="text-xs text-gray-500 mb-2">이 경로들만 외부에서 접근할 수 있습니다</p>

                    {nasAllowedPaths.length > 0 ? (
                      <div className="space-y-2 mb-3">
                        {nasAllowedPaths.map((path, idx) => (
                          <div key={idx} className="flex items-center gap-2 bg-white p-2 rounded-lg border border-gray-200">
                            <FolderOpen size={16} className="text-amber-600 shrink-0" />
                            <span className="flex-1 text-sm text-gray-700 font-mono truncate">{path}</span>
                            <button
                              onClick={() => removeNasPath(path)}
                              className="p-1 hover:bg-red-100 rounded text-red-500"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-amber-600 mb-3">⚠️ 경로 미지정 시 홈 디렉토리 전체가 접근됩니다</p>
                    )}

                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={nasNewPath}
                        onChange={(e) => setNasNewPath(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && addNasPath()}
                        placeholder="/Users/username/Videos"
                        className="flex-1 px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 font-mono text-sm"
                      />
                      {nasNewPath.trim() && (
                        <button
                          onClick={addNasPath}
                          className="px-3 py-2 bg-[#D97706] rounded-lg hover:bg-[#B45309] text-white"
                          title="입력한 경로 추가"
                        >
                          <Plus size={18} />
                        </button>
                      )}
                      <button
                        onClick={addNasPathByDialog}
                        className="px-3 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 text-gray-700"
                        title="폴더 선택"
                      >
                        <FolderOpen size={18} />
                      </button>
                    </div>
                  </div>

                  {/* 웹앱 URL 안내 */}
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 space-y-1">
                    <p className="text-sm text-blue-800">
                      <strong>내부 주소:</strong> <code className="bg-blue-100 px-1 rounded">http://localhost:8765/nas/app</code>
                    </p>
                    {finderHostname ? (
                      <p className="text-sm text-green-700">
                        <strong>외부 주소:</strong> <code className="bg-green-100 px-1 rounded">https://{finderHostname}/nas/app</code>
                      </p>
                    ) : (
                      <p className="text-xs text-blue-600">
                        Cloudflare Tunnel 설정 후 외부 주소가 자동으로 표시됩니다
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* 저장 버튼 */}
            <div className="flex items-center gap-3">
              <button
                onClick={saveNasConfig}
                className="flex items-center gap-2 px-4 py-2 bg-[#D97706] text-white rounded-lg hover:bg-[#B45309]"
              >
                <Save size={16} />
                설정 저장
              </button>
              {nasSaveResult && (
                <span className={`text-sm ${nasSaveResult.success ? 'text-green-600' : 'text-red-600'}`}>
                  {nasSaveResult.success ? <CheckCircle size={16} className="inline mr-1" /> : <AlertCircle size={16} className="inline mr-1" />}
                  {nasSaveResult.message}
                </span>
              )}
            </div>
          </>
        )}
      </div>
    );
  }

  // Launcher 탭
  if (activeTab === 'launcher') {
    return (
      <div className="space-y-6">
        <div>
          <p className="text-sm text-gray-700 mb-4">
            원격 런처를 활성화하면 외부에서 Cloudflare Tunnel을 통해 시스템 AI와 프로젝트 에이전트를 제어할 수 있습니다.
          </p>
        </div>

        {isLoadingLauncher ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[#D97706]" />
          </div>
        ) : (
          <>
            {/* 활성화 토글 */}
            <div className="bg-gray-50 rounded-lg p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Monitor size={20} className="text-gray-600" />
                  <div>
                    <h3 className="font-semibold text-gray-900">원격 런처 활성화</h3>
                    <p className="text-xs text-gray-500">외부에서 시스템 AI 및 에이전트 제어 허용</p>
                  </div>
                </div>
                <button
                  onClick={() => setLauncherEnabled(!launcherEnabled)}
                  className={`relative w-12 h-6 rounded-full transition-colors ${
                    launcherEnabled ? 'bg-[#D97706]' : 'bg-gray-300'
                  }`}
                >
                  <div
                    className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                      launcherEnabled ? 'translate-x-6' : ''
                    }`}
                  />
                </button>
              </div>

              {launcherEnabled && (
                <div className="pt-3 border-t border-gray-200 space-y-4">
                  {/* 비밀번호 설정 */}
                  <div>
                    <label className="block text-sm font-semibold text-gray-900 mb-1">
                      접근 비밀번호 {launcherHasPassword ? '(설정됨)' : '(미설정)'}
                    </label>
                    <input
                      type="password"
                      value={launcherPassword}
                      onChange={(e) => setLauncherPassword(e.target.value)}
                      placeholder={launcherHasPassword ? '새 비밀번호로 변경' : '비밀번호 설정'}
                      className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                    />
                    <p className="text-xs text-gray-500 mt-1">외부 접속 시 이 비밀번호가 필요합니다</p>
                  </div>

                  {/* 기능 안내 */}
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-2">
                    <p className="text-sm font-medium text-amber-800">원격 런처 기능:</p>
                    <ul className="text-xs text-amber-700 space-y-1 ml-4 list-disc">
                      <li>시스템 AI와 채팅</li>
                      <li>프로젝트 에이전트와 채팅</li>
                      <li>스위치 원클릭 실행</li>
                    </ul>
                  </div>

                  {/* 웹앱 URL 안내 */}
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 space-y-1">
                    <p className="text-sm text-blue-800">
                      <strong>내부 주소:</strong> <code className="bg-blue-100 px-1 rounded">http://localhost:8765/launcher/app</code>
                    </p>
                    {launcherHostname ? (
                      <p className="text-sm text-green-700">
                        <strong>외부 주소:</strong> <code className="bg-green-100 px-1 rounded">https://{launcherHostname}/launcher/app</code>
                      </p>
                    ) : (
                      <p className="text-xs text-blue-600">
                        Cloudflare Tunnel 설정 후 외부 주소가 자동으로 표시됩니다
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* 저장 버튼 */}
            <div className="flex items-center gap-3">
              <button
                onClick={saveLauncherConfig}
                className="flex items-center gap-2 px-4 py-2 bg-[#D97706] text-white rounded-lg hover:bg-[#B45309]"
              >
                <Save size={16} />
                설정 저장
              </button>
              {launcherSaveResult && (
                <span className={`text-sm ${launcherSaveResult.success ? 'text-green-600' : 'text-red-600'}`}>
                  {launcherSaveResult.success ? <CheckCircle size={16} className="inline mr-1" /> : <AlertCircle size={16} className="inline mr-1" />}
                  {launcherSaveResult.message}
                </span>
              )}
            </div>
          </>
        )}
      </div>
    );
  }

  // Tunnel 탭
  return (
    <div className="space-y-6">
      {isLoadingTunnel ? (
        <div className="text-center py-8 text-gray-500">로딩 중...</div>
      ) : (
        <>
          <div className="bg-sky-50 border border-sky-200 rounded-lg p-4">
            <p className="text-sm text-sky-800">
              Cloudflare Tunnel을 통해 외부에서 안전하게 IndieBiz OS에 접근할 수 있습니다.
              터널이 실행 중이어야 원격 Finder와 원격 런처가 외부에서 작동합니다.
            </p>
          </div>

          {/* cloudflared 설치 상태 */}
          {!tunnelCloudflaredInstalled && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex items-center gap-2">
                <AlertCircle className="text-red-600" size={20} />
                <p className="text-sm font-medium text-red-800">cloudflared가 설치되지 않았습니다</p>
              </div>
              <p className="text-xs text-red-600 mt-2">
                터미널에서 설치하세요: <code className="bg-red-100 px-1 rounded">brew install cloudflared</code> (macOS)
              </p>
            </div>
          )}

          <div className="bg-gray-50 rounded-lg p-5 space-y-4">
            {/* 터널 실행 토글 */}
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-gray-900">터널 실행</h3>
                <p className="text-sm text-gray-600">
                  {tunnelRunning ? (
                    <span className="text-green-600 font-medium">● 실행 중</span>
                  ) : (
                    <span className="text-gray-500">○ 중지됨</span>
                  )}
                </p>
              </div>
              <button
                onClick={toggleTunnel}
                disabled={isTunnelToggling || !tunnelCloudflaredInstalled || !tunnelName.trim()}
                className={`relative w-14 h-7 rounded-full transition-colors ${
                  tunnelRunning ? 'bg-green-500' : 'bg-gray-300'
                } ${(isTunnelToggling || !tunnelCloudflaredInstalled || !tunnelName.trim()) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
              >
                <div
                  className={`absolute top-0.5 w-6 h-6 bg-white rounded-full shadow transition-transform ${
                    tunnelRunning ? 'translate-x-7' : 'translate-x-0.5'
                  }`}
                />
              </button>
            </div>

            {/* 자동 시작 */}
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-gray-900">자동 시작</h3>
                <p className="text-sm text-gray-600">IndieBiz OS 시작 시 터널 자동 실행</p>
              </div>
              <button
                onClick={() => setTunnelAutoStart(!tunnelAutoStart)}
                className={`relative w-14 h-7 rounded-full transition-colors ${
                  tunnelAutoStart ? 'bg-[#D97706]' : 'bg-gray-300'
                }`}
              >
                <div
                  className={`absolute top-0.5 w-6 h-6 bg-white rounded-full shadow transition-transform ${
                    tunnelAutoStart ? 'translate-x-7' : 'translate-x-0.5'
                  }`}
                />
              </button>
            </div>

            {/* 터널 이름 */}
            <div>
              <label className="block text-sm font-semibold text-gray-900 mb-1">터널 이름</label>
              <input
                type="text"
                value={tunnelName}
                onChange={(e) => setTunnelName(e.target.value)}
                placeholder="my-tunnel"
                className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
              />
              <p className="text-xs text-gray-500 mt-1">cloudflared tunnel create로 생성한 터널 이름</p>
            </div>

            {/* 호스트명 */}
            <div>
              <label className="block text-sm font-semibold text-gray-900 mb-1">호스트명 (메모용)</label>
              <input
                type="text"
                value={tunnelHostname}
                onChange={(e) => setTunnelHostname(e.target.value)}
                placeholder="home.mydomain.com"
                className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
              />
              <p className="text-xs text-gray-500 mt-1">외부에서 접속할 도메인 (참고용)</p>
            </div>

            {/* 접속 URL 안내 */}
            {tunnelHostname && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 space-y-1">
                <p className="text-sm text-blue-800 font-medium">외부 접속 URL:</p>
                <p className="text-xs text-blue-700">
                  원격 Finder: <code className="bg-blue-100 px-1 rounded">https://{tunnelHostname}/nas/app</code>
                </p>
                <p className="text-xs text-blue-700">
                  원격 런처: <code className="bg-blue-100 px-1 rounded">https://{tunnelHostname}/launcher/app</code>
                </p>
              </div>
            )}
          </div>

          {/* 저장 버튼 */}
          <div className="flex items-center gap-3">
            <button
              onClick={saveTunnelConfig}
              className="flex items-center gap-2 px-4 py-2 bg-[#D97706] text-white rounded-lg hover:bg-[#B45309]"
            >
              <Save size={16} />
              설정 저장
            </button>
            {tunnelSaveResult && (
              <span className={`text-sm ${tunnelSaveResult.success ? 'text-green-600' : 'text-red-600'}`}>
                {tunnelSaveResult.success ? <CheckCircle size={16} className="inline mr-1" /> : <AlertCircle size={16} className="inline mr-1" />}
                {tunnelSaveResult.message}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
