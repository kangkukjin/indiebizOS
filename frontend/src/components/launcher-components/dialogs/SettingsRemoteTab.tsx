/**
 * SettingsRemoteTab - 원격 접속 관련 설정 탭 (NAS, 런처, 터널)
 */

import { useCallback, useState } from 'react';
import { Save, HardDrive, FolderOpen, Plus, Trash2, Monitor, CheckCircle, AlertCircle, Globe, Package } from 'lucide-react';
import { useRetryingLoad } from '../../../lib/use-retrying-load';

interface SettingsRemoteTabProps {
  activeTab: 'nas' | 'launcher' | 'tunnel';
  show: boolean;
  finderHostname: string;
  launcherHostname: string;
  /** 이 몸의 오리진 호스트 — 값이 있으면 주소가 수기설정이 아니라 발급된 얼굴에서 파생됐다 */
  originHost?: string;
  /** 'cloudflare' | 'tailscale' — 주소 안내 문구를 프로바이더에 맞춘다 */
  tunnelProvider?: string;
}

export function SettingsRemoteTab({ activeTab, show, finderHostname, launcherHostname,
                                    originHost, tunnelProvider }: SettingsRemoteTabProps) {
  // 원격 주소가 창고 얼굴을 따라왔는지 / 아직 아무 얼굴도 없는지 — 두 안내 문구의 재료.
  // ★런처·파인더는 창고 공개주소(public_base)가 아니라 *오리진 호스트*를 따라간다.
  // Worker 얼굴은 공개주소가 CDN 이고 그 CDN 이 /launcher/app·/nas/* 를 라우팅하지 않기 때문.
  const isTailscale = tunnelProvider === 'tailscale';
  const originNote = originHost
    ? `${isTailscale ? 'Tailscale Funnel' : 'Cloudflare 터널'} 주소를 따라갑니다 (공유창고와 같은 얼굴)`
    : '';
  const noFaceHint = 'Cloudflare 터널 또는 Tailscale Funnel 로 주소를 발급하면 여기에 자동 표시됩니다';
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

  // 창고 신원(공개 얼굴) 자동 발급 상태 — /tunnel/provision/*
  const [provStatus, setProvStatus] = useState<any>(null);
  const [provZones, setProvZones] = useState<{ id: string; name: string }[]>([]);
  const [provDomain, setProvDomain] = useState('');
  const [provSub, setProvSub] = useState('');
  const [provBusy, setProvBusy] = useState<'' | 'ts' | 'cf'>('');
  const [provResult, setProvResult] = useState<{ success: boolean; message: string; url?: string } | null>(null);
  const [provSteps, setProvSteps] = useState<{ step: string; ok: boolean; detail: string }[]>([]);

  // NAS 설정 로드 — 실패는 throw 되어 useRetryingLoad 가 백오프 재시도한다.
  const loadNasConfig = useCallback(async () => {
    setIsLoadingNas(true);
    try {
      const response = await fetch('http://127.0.0.1:8765/nas/config');
      if (response.ok) {
        const data = await response.json();
        setNasEnabled(data.enabled || false);
        setNasHasPassword(data.has_password || false);
        setNasAllowedPaths(data.allowed_paths || []);
      }
    } finally {
      setIsLoadingNas(false);
    }
  }, []);
  useRetryingLoad(loadNasConfig, { enabled: show && activeTab === 'nas' });

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

  // 원격 런처 설정 로드
  const loadLauncherConfig = useCallback(async () => {
    setIsLoadingLauncher(true);
    try {
      const response = await fetch('http://127.0.0.1:8765/launcher/config');
      if (response.ok) {
        const data = await response.json();
        setLauncherEnabled(data.enabled || false);
        setLauncherHasPassword(data.has_password || false);
      }
    } finally {
      setIsLoadingLauncher(false);
    }
  }, []);
  useRetryingLoad(loadLauncherConfig, { enabled: show && activeTab === 'launcher' });

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

  const loadTunnelConfig = useCallback(async () => {
    setIsLoadingTunnel(true);
    try {
      const response = await fetch('http://127.0.0.1:8765/tunnel/config');
      if (response.ok) {
        const data = await response.json();
        setTunnelRunning(data.running || false);
        setTunnelAutoStart(data.auto_start || false);
        setTunnelName(data.tunnel_name || '');
        setTunnelHostname(data.hostname || '');
        setTunnelCloudflaredInstalled(data.cloudflared_installed || false);
      }
    } finally {
      setIsLoadingTunnel(false);
    }
  }, []);

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

  // ── 창고 신원 자동 발급 (새 몸 = 새 주소) ──────────────────────────────────

  const loadProvision = useCallback(async () => {
    const r = await fetch('http://127.0.0.1:8765/tunnel/provision/status');
    if (!r.ok) return;
    const d = await r.json();
    setProvStatus(d);
    setProvSub(prev => prev || d.machine_slug || '');
    if (d.cloudflare?.api_token_present) {
      try {
        const zr = await fetch('http://127.0.0.1:8765/tunnel/provision/zones');
        if (zr.ok) {
          const zd = await zr.json();
          if (zd.success) {
            setProvZones(zd.zones || []);
            setProvDomain(prev => prev || (zd.zones?.[0]?.name ?? ''));
          }
        }
      } catch { /* zone 조회 실패는 조용히 — 카드에서 토큰 안내로 대체 */ }
    }
  }, []);

  // 터널 설정 로드
  const loadTunnelTab = useCallback(async () => {
    await Promise.all([loadTunnelConfig(), loadProvision()]);
  }, [loadTunnelConfig, loadProvision]);
  useRetryingLoad(loadTunnelTab, { enabled: show && activeTab === 'tunnel' });

  const provisionTailscale = async () => {
    try {
      setProvBusy('ts');
      setProvResult(null);
      setProvSteps([]);
      const r = await fetch('http://127.0.0.1:8765/tunnel/provision/tailscale', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const d = await r.json();
      // needs_approval: Funnel 미승인 — CLI 가 찍은 관리 콘솔 승인 URL 을 링크로 승격
      setProvResult({ success: !!d.success, message: d.message || d.error || (d.success ? '발급 완료' : '발급 실패'), url: d.approval_url });
      if (d.success) { await Promise.all([loadProvision(), loadTunnelConfig()]).catch(() => {}); }
    } catch (err) {
      setProvResult({ success: false, message: '요청 실패: ' + (err as Error).message });
    } finally {
      setProvBusy('');
    }
  };

  // use=공식 주소로 전환(+열기) / open=서빙만 재개 / close=서빙 내림 — 전부 가역
  const provisionFaceAction = async (action: 'use' | 'open' | 'close', provider: 'cloudflare' | 'tailscale') => {
    try {
      setProvBusy(provider === 'tailscale' ? 'ts' : 'cf');
      setProvResult(null);
      const r = await fetch(`http://127.0.0.1:8765/tunnel/provision/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider }),
      });
      const d = await r.json();
      setProvResult({ success: !!d.success, message: d.message || d.error || (d.success ? '완료' : '실패') });
      if (d.success) { await Promise.all([loadProvision(), loadTunnelConfig()]).catch(() => {}); }
    } catch (err) {
      setProvResult({ success: false, message: '요청 실패: ' + (err as Error).message });
    } finally {
      setProvBusy('');
    }
  };
  const provisionUse = (p: 'cloudflare' | 'tailscale') => provisionFaceAction('use', p);

  const provisionCloudflare = async () => {
    if (!provDomain || !provSub.trim()) {
      setProvResult({ success: false, message: '도메인과 서브도메인을 입력하세요' });
      return;
    }
    try {
      setProvBusy('cf');
      setProvResult(null);
      setProvSteps([]);
      const r = await fetch('http://127.0.0.1:8765/tunnel/provision/cloudflare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: provDomain, subdomain: provSub.trim() }),
      });
      const d = await r.json();
      setProvSteps(d.steps || []);
      setProvResult({ success: !!d.success, message: d.message || d.error || (d.success ? '발급 완료' : '발급 실패') });
      if (d.success) { await Promise.all([loadProvision(), loadTunnelConfig()]).catch(() => {}); }
    } catch (err) {
      setProvResult({ success: false, message: '요청 실패: ' + (err as Error).message });
    } finally {
      setProvBusy('');
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
                      <>
                        <p className="text-sm text-green-700">
                          <strong>외부 주소:</strong> <code className="bg-green-100 px-1 rounded">https://{finderHostname}/nas/app</code>
                        </p>
                        {originNote && <p className="text-xs text-green-600">{originNote}</p>}
                      </>
                    ) : (
                      <p className="text-xs text-blue-600">{noFaceHint}</p>
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
                      <>
                        <p className="text-sm text-green-700">
                          <strong>외부 주소:</strong> <code className="bg-green-100 px-1 rounded">https://{launcherHostname}/launcher/app</code>
                        </p>
                        {originNote && <p className="text-xs text-green-600">{originNote}</p>}
                      </>
                    ) : (
                      <p className="text-xs text-blue-600">{noFaceHint}</p>
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
              공개 주소(터널)가 있어야 공유창고·원격 런처·원격 Finder가 외부에서 작동합니다.
              새 컴퓨터는 새 주소(새 신원)를 발급받아야 공유창고가 열립니다.
            </p>
          </div>

          {/* ── 창고 신원(공개 주소) 자동 발급 ── */}
          <div className="bg-gray-50 rounded-lg p-5 space-y-4">
            <div className="flex items-center gap-2">
              <Package size={18} className="text-[#D97706]" />
              <h3 className="font-semibold text-gray-900">이 컴퓨터의 창고 주소</h3>
            </div>

            {provStatus?.identity?.public_base ? (
              <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-800">
                현재 주소: <code className="bg-green-100 px-1 rounded">{provStatus.identity.public_base}</code>
                <span className="ml-2 text-xs text-green-700">
                  ({provStatus.identity.provider === 'tailscale' ? 'Tailscale Funnel' : 'Cloudflare'}
                  {provStatus.tunnel?.running ? ' · 실행 중' : ' · 중지됨'})
                </span>
              </div>
            ) : (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
                아직 이 컴퓨터의 창고 주소가 없습니다 — 아래 두 방법 중 하나로 발급하세요.
              </div>
            )}

            {/* 공식 주소 스위치 — 발급(주소 만들기)과 분리된 명시적 선택.
                발급된 주소들이 라디오로 나열되고, 고르는 쪽이 공식 주소(public_base)가 된다.
                반대쪽 주소도 계속 서빙(이사 공지 기간 공존). */}
            {(() => {
              const cfHost = provStatus?.cloudflare?.provisioned ? provStatus.cloudflare.hostname : '';
              const tsHost = provStatus?.tailscale?.logged_in ? provStatus.tailscale.dns_name : '';
              const faces = [
                ...(cfHost ? [{ key: 'cloudflare' as const, label: 'Cloudflare', host: cfHost, url: `https://${cfHost}` }] : []),
                ...(tsHost ? [{ key: 'tailscale' as const, label: 'Tailscale', host: tsHost, url: `https://${tsHost}` }] : []),
              ];
              if (faces.length === 0) return null;
              const activeBase = (provStatus?.identity?.public_base || '').replace(/\/$/, '');
              const directHosts: string[] = provStatus?.identity?.direct_hosts || [];
              return (
                <div className="border border-gray-200 bg-white rounded-lg p-3 space-y-1.5">
                  <p className="text-xs font-medium text-gray-500">
                    내 창고 주소들 — 공식 주소(이웃에게 알리는 주소)를 고르고, 각 주소는 자유롭게 열고 닫습니다
                  </p>
                  {faces.map(f => {
                    const active = f.url === activeBase;
                    const open = directHosts.includes(f.host);
                    return (
                      <div key={f.key} className="flex items-center gap-2 text-sm">
                        <span className={`w-3.5 h-3.5 rounded-full border-2 shrink-0 ${
                          active ? 'border-[#D97706] bg-[#D97706]' : 'border-gray-300 bg-white'
                        }`} />
                        <code className={`px-1 rounded truncate ${active ? 'bg-amber-50 text-gray-900' : 'text-gray-600'}`}>{f.url}</code>
                        <span className="text-xs text-gray-400 shrink-0">{f.label}</span>
                        <span className={`text-[11px] shrink-0 ${open ? 'text-green-600' : 'text-gray-400'}`}>
                          {open ? '● 열림' : '○ 닫힘'}
                        </span>
                        <div className="flex-1" />
                        {active ? (
                          <span className="text-xs text-[#B45309] font-medium shrink-0">공식 주소</span>
                        ) : (
                          <button
                            onClick={() => provisionUse(f.key)}
                            disabled={provBusy !== ''}
                            className={`shrink-0 px-2.5 py-1 rounded-lg text-xs font-medium ${
                              provBusy === '' ? 'bg-white border border-[#D97706] text-[#B45309] hover:bg-amber-50'
                                              : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                            }`}
                          >
                            이 주소 사용
                          </button>
                        )}
                        <button
                          onClick={() => {
                            if (open && !window.confirm(`${f.url} 창고 주소를 닫을까요? (언제든 다시 열 수 있습니다)`)) return;
                            provisionFaceAction(open ? 'close' : 'open', f.key);
                          }}
                          disabled={provBusy !== ''}
                          className={`shrink-0 px-2.5 py-1 rounded-lg text-xs font-medium ${
                            provBusy === '' ? (open ? 'bg-white border border-gray-300 text-gray-500 hover:bg-gray-50'
                                                    : 'bg-white border border-green-500 text-green-600 hover:bg-green-50')
                                            : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                          }`}
                        >
                          {open ? '닫기' : '열기'}
                        </button>
                      </div>
                    );
                  })}
                </div>
              );
            })()}

            {/* ① Tailscale — 원클릭, 도메인 불필요 */}
            <div className="border border-gray-200 bg-white rounded-lg p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium text-gray-900 flex items-center gap-2">
                    <Globe size={15} className="text-gray-500" /> Tailscale로 발급 (간단 — 도메인 불필요)
                  </h4>
                  <p className="text-xs text-gray-500 mt-1">
                    Tailscale 앱에 로그인만 되어 있으면 <code className="bg-gray-100 px-1 rounded">https://이컴퓨터.ts.net</code> 주소가 자동으로 생깁니다.
                  </p>
                </div>
                <button
                  onClick={provisionTailscale}
                  disabled={provBusy !== '' || !provStatus?.tailscale?.logged_in}
                  className={`shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium ${
                    provStatus?.tailscale?.logged_in && provBusy === ''
                      ? 'bg-[#D97706] text-white hover:bg-[#B45309]'
                      : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                  }`}
                >
                  {provBusy === 'ts' ? '발급 중…' : '주소 발급'}
                </button>
              </div>
              {!provStatus?.tailscale?.installed && (
                <p className="text-xs text-red-600">
                  Tailscale 미설치 — <code className="bg-red-50 px-1 rounded">{provStatus?.tailscale?.install_hint || 'https://tailscale.com/download'}</code>
                </p>
              )}
              {provStatus?.tailscale?.installed && !provStatus?.tailscale?.logged_in && (
                <p className="text-xs text-red-600">Tailscale 로그인 필요 — 앱을 열어 로그인하세요. {provStatus?.tailscale?.error}</p>
              )}
            </div>

            {/* ② Cloudflare — 내 도메인의 서브도메인으로 발급 */}
            <div className="border border-gray-200 bg-white rounded-lg p-4 space-y-3">
              <div>
                <h4 className="font-medium text-gray-900 flex items-center gap-2">
                  <Globe size={15} className="text-gray-500" /> Cloudflare로 발급 (내 도메인 사용)
                </h4>
                <p className="text-xs text-gray-500 mt-1">
                  API 토큰으로 터널 생성 → DNS 연결 → 실행까지 자동으로 처리합니다. (Worker 불필요)
                </p>
              </div>
              {!provStatus?.cloudflare?.api_token_present || !provStatus?.cloudflare?.account_id_present ? (
                <p className="text-xs text-red-600">
                  Cloudflare API 토큰·계정 ID가 필요합니다 — 설정의 'API 키' 탭에서
                  CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID를 등록하세요.
                </p>
              ) : (
                <>
                  {!provStatus?.cloudflare?.cloudflared_installed && (
                    <p className="text-xs text-red-600">
                      cloudflared 미설치 — <code className="bg-red-50 px-1 rounded">{provStatus?.cloudflare?.install_hint}</code>
                    </p>
                  )}
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={provSub}
                      onChange={(e) => setProvSub(e.target.value)}
                      placeholder="win"
                      className="w-32 px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 text-sm"
                    />
                    <span className="text-gray-500">.</span>
                    <select
                      value={provDomain}
                      onChange={(e) => setProvDomain(e.target.value)}
                      className="flex-1 px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 text-sm"
                    >
                      {provZones.length === 0 && <option value="">도메인 없음</option>}
                      {provZones.map(z => <option key={z.id} value={z.name}>{z.name}</option>)}
                    </select>
                    <button
                      onClick={provisionCloudflare}
                      disabled={provBusy !== '' || !provDomain || !provSub.trim() || !provStatus?.cloudflare?.cloudflared_installed}
                      className={`shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium ${
                        provBusy === '' && provDomain && provSub.trim() && provStatus?.cloudflare?.cloudflared_installed
                          ? 'bg-[#D97706] text-white hover:bg-[#B45309]'
                          : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                      }`}
                    >
                      {provBusy === 'cf' ? '발급 중…' : (provStatus?.cloudflare?.provisioned ? '재발급' : '주소 발급')}
                    </button>
                  </div>
                </>
              )}
              {provSteps.length > 0 && (
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-2 space-y-0.5">
                  {provSteps.map((s, i) => (
                    <p key={i} className={`text-xs ${s.ok ? 'text-gray-600' : 'text-red-600'}`}>
                      {s.ok ? '✓' : '✗'} {s.step}: {s.detail}
                    </p>
                  ))}
                </div>
              )}
            </div>

            {provResult && (
              <p className={`text-sm ${provResult.success ? 'text-green-600' : 'text-red-600'}`}>
                {provResult.success ? <CheckCircle size={16} className="inline mr-1" /> : <AlertCircle size={16} className="inline mr-1" />}
                {provResult.message}
                {provResult.url && (
                  <a
                    className="ml-1 underline text-[#D97706] hover:text-[#B45309] cursor-pointer break-all"
                    onClick={(e) => {
                      e.preventDefault();
                      const el = (window as any).electron;
                      if (el?.openExternal) el.openExternal(provResult.url);
                      else window.open(provResult.url, '_blank', 'noopener');
                    }}
                  >
                    {provResult.url}
                  </a>
                )}
              </p>
            )}
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
            <p className="text-xs text-gray-400 font-medium">수동 설정 (고급) — 이미 만든 터널을 직접 지정할 때만</p>
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
