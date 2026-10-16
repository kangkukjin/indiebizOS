import * as __uiTools from '../i18n/ui';
import * as React from 'react';
import { LauncherDisplay } from './LauncherDisplay';
import { toolNavigation, openTool, openSystemAI } from '../lib/surface-navigation';
/**
 * 런처 - 데스크탑 스타일 프로젝트/폴더/스위치 관리
 */
import { BACKEND_ORIGIN, IS_WEB_SURFACE } from '../lib/backend-origin';
import { LanguagePicker, UiText, uiMessage, useLocale, ui } from '../i18n/ui';

import { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { Laptop, Zap, Boxes, Settings, Clock, Folder, Globe, Bot, Package, Users, Contact, HelpCircle, Info, ChevronDown, BookOpen, ScanLine, Search, Gauge, LayoutGrid, Compass, X, Smartphone, Layers, FileText } from 'lucide-react';
import logoImage from '../assets/logo-indiebiz.png';
import { useAppStore } from '../stores/appStore';
import { api } from '../lib/api';
import { useRetryingLoad } from '../lib/use-retrying-load';
import type { Switch, SchedulerTask } from '../types';
import {
  DraggableIcon,
  DraggableTrash,
  ContextMenu,
  NewProjectDialog,
  NewFolderDialog,
  SettingsDialog,
  TrashDialog,
  SchedulerDialog,
  SwitchEditDialog,
} from './launcher-components';
import { GuideDialog } from './GuideDialog';
import { OnboardingDialog } from './OnboardingDialog';
import { UserManualDialog } from './UserManualDialog';
import { ActionDesktop, STATIC_APP_META, staticAppLabel } from './ActionDesktop';
import ManualMode from './ManualMode';
import { ForageBrowser } from './ForageBrowser';
import { WarehouseView } from './WarehouseView';
import { useLauncherDesktop } from './launcher-components/useLauncherDesktop';
import type {
  SystemAISettings,
  LightweightAISettings,
  MidtierAISettings,
} from './launcher-components';

// 런처 상단 모드 선택기의 네 표면 (순서 = 드롭다운 표시 순서 — 공유창고가 맨 위: 목적 우선).
// 검색 브라우저는 모드가 아니라 앱모드의 앱(ActionDesktop 'forage' 타일) — 오버레이로 뜬다.
// 비즈니스는 모드가 아니라 공유창고의 탭(2026-07-19 이동) — 창고를 채우는 관리 기능이라서.
const LAUNCHER_MODES = ['warehouse', 'autopilot', 'manual', 'app'] as const;
type LauncherMode = typeof LAUNCHER_MODES[number];
const MODE_META: Record<LauncherMode, { label: string; icon: typeof Search }> = {
  warehouse: { label: uiMessage('launcher.mode', '공유창고'), icon: Package },
  autopilot: { label: uiMessage('launcher.mode', '자율주행'), icon: Compass },
  manual: { label: uiMessage('launcher.mode', '조종실'), icon: Gauge },
  app: { label: uiMessage('launcher.mode', '앱'), icon: LayoutGrid },
};

export function useLauncherHost() {
  useLocale();
  const {
    switches,
    loadProjects,
    loadSwitches,
    isLoading,
    error,
  } = useAppStore();

  // 런처는 하나의 모드 전환 버튼(상단 X-Ray 앞)으로 오가는 표면들이다:
  //   autopilot(자율주행) = 데스크탑 아이콘  ·  manual(조종실) = IBL 번역·검수·실행
  //   app(앱) = 아이콘 GUI 계기  ·  warehouse(공유창고 — 비즈니스 관리는 이 안의 탭)
  // 내 어휘는 안경 메뉴에서 독립 창으로 연다.
  // 검색 브라우저(공동 포식 크로미움)는 모드에서 빠져 앱모드의 앱 — browserOpen 오버레이로 뜬다.
  // (옛 3토글 자율주행/조종실/앱은 이 단일 모드 선택기로 대체됨)
  const [launcherTab, setLauncherTab] = useState<LauncherMode>(() => {
    const saved = localStorage.getItem('indiebiz_launcher_mode');
    return (saved && (LAUNCHER_MODES as readonly string[]).includes(saved))
      ? (saved as LauncherMode) : 'autopilot';
  });
  // 승격된 앱 — 모드 선택기 구분선 아래에 뜨는 바로가기. 선택하면 앱 모드로 딥링크(그 앱을 바로 연다).
  // 앱 모드를 승격 없이 열면 null(일반 앱 홈).
  const [activeAppId, setActiveAppId] = useState<string | null>(() =>
    localStorage.getItem('indiebiz_launcher_app') || null
  );
  // 승격 앱 열기 신호 — 선택할 때마다 증가. 같은 앱 재선택도 새 열기가 되게 하는 유일한 근거.
  const [appOpenNonce, setAppOpenNonce] = useState(0);
  const [promotedIds, setPromotedIds] = useState<string[]>([]);
  // 승격 앱 아이콘·라벨 해소용 — static 도메인 메타 + 매니페스트(런타임) 병합.
  const [appMetaById, setAppMetaById] = useState<Record<string, { icon: string; label: string }>>({});

  const loadPromoted = useCallback(async () => {
    // 두 조회는 독립 실행 — 실패는 throw 해서 useRetryingLoad 가 백오프 재시도
    await Promise.all([
      api.getAppLayout().then((layout) => setPromotedIds(layout.promoted || [])),
      fetch(`${BACKEND_ORIGIN}/launcher/instruments`).then(async (r) => {
        if (!r.ok) return;
        const d = await r.json();
        const map: Record<string, { icon: string; label: string }> = {};
        for (const m of STATIC_APP_META) map[m.id] = { icon: m.icon, label: m.label };
        for (const inst of (d.instruments || [])) map[inst.id] = { icon: inst.icon, label: inst.name };
        setAppMetaById(map);
      }),
    ]);
  }, []);

  // 승격 목록에서 실제로 해소되는(카탈로그에 존재하는) 앱만 바에 표시.
  const promotedApps = useMemo(
    () => promotedIds
      .map((id) => { const m = appMetaById[id]; return m ? { id, ...m } : null; })
      .filter((x): x is { id: string; icon: string; label: string } => !!x),
    [promotedIds, appMetaById]
  );

  // 검색 브라우저 오버레이 — 모드가 아니라 현재 표면 위를 덮는다(닫으면 그 표면 그대로).
  const [browserOpen, setBrowserOpen] = useState(false);
  const [showModeMenu, setShowModeMenu] = useState(false);
  const [mobileToolsOpen, setMobileToolsOpen] = useState(false);
  const [projectQuery, setProjectQuery] = useState('');
  const modeMenuRef = useRef<HTMLDivElement>(null);
  // 검색 브라우저를 특정 URL로 열도록 넘기는 신호(예: X-Ray). ForageBrowser가 소비 후 null 복귀.
  const [pendingBrowserUrl, setPendingBrowserUrl] = useState<string | null>(null);
  const [showNewProjectDialog, setShowNewProjectDialog] = useState(false);
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  const [showNewMultiChatDialog, setShowNewMultiChatDialog] = useState(false);
  const [showSchedulerDialog, setShowSchedulerDialog] = useState(false);
  const [showSwitchEditDialog, setShowSwitchEditDialog] = useState(false);
  const [showGuideDialog, setShowGuideDialog] = useState(false);
  const [showOnboardingDialog, setShowOnboardingDialog] = useState(false);
  const [showUserManualDialog, setShowUserManualDialog] = useState(false);
  const [showMainMenu, setShowMainMenu] = useState(false);
  const mainMenuRef = useRef<HTMLDivElement>(null);
  const [newProjectName, setNewProjectName] = useState('');
  const [newFolderName, setNewFolderName] = useState('');
  const [newMultiChatName, setNewMultiChatName] = useState('');

  // 스위치 편집 상태
  const [editingSwitchData, setEditingSwitchData] = useState<Switch | null>(null);
  const [switchEditForm, setSwitchEditForm] = useState({
    name: '',
    icon: '⚡',
    command: '',
  });

  // 데스크탑 아이콘 상호작용(다중채팅방·휴지통·드래그·복사/이름변경·컨텍스트 메뉴·단축키)은
  // useLauncherDesktop 훅으로 이동 (2026-07-18 모듈화) — 구조분해로 JSX 식별자 무변경.
  const {
    multiChatRooms, setMultiChatRooms,
    trashHover,
    contextMenu, setContextMenu,
    clipboard,
    selectedItem,
    renamingItem,
    showTrashDialog, setShowTrashDialog,
    trashItems,
    trashPosition, setTrashPosition,
    hoveringFolderId, setHoveringFolderId,
    folderRefs,
    trashRef,
    displayProjects,
    displaySwitches,
    loadMultiChatRooms,
    loadTrashItems,
    handleOpenProject,
    handleMoveToFolder,
    handleExecuteSwitch,
    handleOpenMultiChatRoom,
    handlePositionChange,
    handleArrangeIcons,
    handleCopy,
    handlePaste,
    handleSelect,
    handleStartRename,
    handleFinishRename,
    handleCancelRename,
    handleOpenTrash,
    handleRestoreFromTrash,
    handleEmptyTrash,
    handleDragStart,
    handleDragEnd,
    handleDropOnTrash,
    checkTrashHover,
    checkFolderHover,
    handleContextMenu,
    handleItemContextMenu,
    closeContextMenu,
    getItemName,
  } = useLauncherDesktop({
    launcherTab,
    showNewProjectDialog,
    showNewFolderDialog,
    showSchedulerDialog,
  });

  // 스케줄러 관련 상태
  const [schedulerTasks, setSchedulerTasks] = useState<SchedulerTask[]>([]);

  // "클립보드→폰" 버튼 상태 (idle → sending → ok/queued/err → idle)
  const [clipToPhone, setClipToPhone] = useState<'idle' | 'sending' | 'ok' | 'queued' | 'err'>('idle');
  const sendClipboardToPhone = useCallback(async () => {
    if (clipToPhone === 'sending') return;
    const done = (s: 'ok' | 'queued' | 'err') => {
      setClipToPhone(s);
      setTimeout(() => setClipToPhone('idle'), 3000);
    };
    // 클립보드 읽기: navigator.clipboard(렌더러 표준, Electron 기본 권한으로 동작) 우선.
    // ★preload 의 readFromClipboard 는 폴백일 뿐 — Electron 20+ 기본 샌드박스 렌더러의
    // preload 에는 clipboard 모듈이 없어서 호출 시 throw 한다(조용한 클릭 실패의 원인).
    let text = '';
    try {
      text = await navigator.clipboard.readText();
    } catch { /* 아래 폴백 */ }
    if (!text.trim() && window.electron?.readClipboardText) {
      try { text = (await window.electron.readClipboardText()) ?? ''; } catch { text = ''; }
    }
    if (!text.trim()) {
      try { text = window.electron?.readFromClipboard?.() ?? ''; } catch { text = ''; }
    }
    if (!text.trim()) { done('err'); return; }
    setClipToPhone('sending');
    try {
      // 맥 클립보드 → 폰 클립보드 + 도착 알림 (2026-07-28 원복 — clipbox 철회).
      // ★사전 물리 분리 후 맥 엔진엔 limbs:phone 이 없으므로 /ibl/execute 가 아니라
      // 전용 라우트로 — 백엔드가 폰 사전의 고정 봉투를 직결(Wi-Fi) 또는 heartbeat
      // 롱폴 푸시 큐(LTE)로 전달한다(api_launcher_web.clip_to_phone).
      const r = await fetch(`${BACKEND_ORIGIN}/launcher/clip-to-phone`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok && data?.success && data?.queued) done('queued');
      else if (r.ok && data?.success) done('ok');
      else done('err');
    } catch {
      done('err');
    }
  }, [clipToPhone]);

  // 설정 다이얼로그 상태
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [systemAiSettings, setSystemAiSettings] = useState<SystemAISettings>({
    enabled: true,
    provider: 'google',
    model: 'gemini-2.0-flash-exp',
    apiKey: '',
  });
  const [lightweightAiSettings, setLightweightAiSettings] = useState<LightweightAISettings>({
    enabled: true,
    provider: 'google',
    model: 'gemini-2.5-flash-lite',
    apiKey: '',
  });
  const [showLightweightApiKey, setShowLightweightApiKey] = useState(false);
  const [midtierAiSettings, setMidtierAiSettings] = useState<MidtierAISettings>({
    enabled: true,
    provider: 'google',
    model: 'gemini-2.5-flash',
    apiKey: '',
  });
  const [showMidtierApiKey, setShowMidtierApiKey] = useState(false);

  const desktopRef = useRef<HTMLDivElement>(null);

  // 마운트 조회 — 스토어 로더들은 실패를 내부에서 삼키므로(error 상태만 남김),
  // 조회 후 error 가 있으면 throw 해서 useRetryingLoad 가 백오프 재시도하게 둔다.
  const loadLauncherData = useCallback(async () => {
    await Promise.all([loadProjects(), loadSwitches(), loadMultiChatRooms(), loadPromoted()]);
    const storeError = useAppStore.getState().error;
    if (storeError) throw new Error(storeError);
    // loadMultiChatRooms 는 useLauncherDesktop 이 렌더마다 재생성 — deps 에 넣으면 무한 재조회
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadProjects, loadSwitches, loadPromoted]);
  const { retry: retryLauncherData } = useRetryingLoad(loadLauncherData);

  // 활성(승격) 앱 영속화 — 다음 실행 시 마지막으로 연 승격 앱으로 복귀.
  useEffect(() => {
    if (activeAppId) localStorage.setItem('indiebiz_launcher_app', activeAppId);
    else localStorage.removeItem('indiebiz_launcher_app');
  }, [activeAppId]);

  // 첫 실행: ① 첫 성공 온보딩(서버 상태 — 시스템 AI 가 실제로 답한 적이 없고 건너뛴 적도 없으면)
  //         ② 그 다음에 가이드(로컬 1회). 온보딩 상태는 서버 원장이라 3표면이 같은 것을 본다.
  const showGuideOnce = () => {
    const hasSeenGuide = localStorage.getItem('indiebiz_has_seen_guide');
    if (!hasSeenGuide) {
      setShowGuideDialog(true);
      localStorage.setItem('indiebiz_has_seen_guide', 'true');
    }
  };
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const ob = await api.getOnboarding();
        if (cancelled) return;
        if (!ob.completed && !ob.state.dismissed_at) { setShowOnboardingDialog(true); return; }
      } catch { /* 백엔드가 아직이면 가이드만 */ }
      if (!cancelled) showGuideOnce();
    }, 500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, []);

  // 메인 메뉴 외부 클릭 시 닫기
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (mainMenuRef.current && !mainMenuRef.current.contains(event.target as Node)) {
        setShowMainMenu(false);
      }
    };
    if (showMainMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showMainMenu]);

  // 모드 선택 드롭다운 외부 클릭 시 닫기
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (modeMenuRef.current && !modeMenuRef.current.contains(event.target as Node)) {
        setShowModeMenu(false);
      }
    };
    if (showModeMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showModeMenu]);

  // 선택 모드 영속화
  useEffect(() => {
    localStorage.setItem('indiebiz_launcher_mode', launcherTab);
  }, [launcherTab]);

  // PC Manager 창 열기 요청 폴링
  useEffect(() => {
    if (!window.electron?.openPCManagerWindow) return;
    const pollPendingWindows = async () => {
      try {
        const response = await fetch(`${BACKEND_ORIGIN}/pcmanager/pending-windows`);
        if (response.ok) {
          const data = await response.json();
          for (const req of data.requests || []) {
            if (window.electron?.openPCManagerWindow) {
              window.electron.openPCManagerWindow(req.path || null);
            }
          }
        }
      } catch {
        // 서버 연결 실패 무시
      }
    };

    const interval = setInterval(pollPendingWindows, 300);
    return () => clearInterval(interval);
  }, []);

  // Photo Manager 창 열기 요청 폴링
  useEffect(() => {
    if (!window.electron?.openPhotoManagerWindow) return;
    const pollPhotoWindows = async () => {
      try {
        const response = await fetch(`${BACKEND_ORIGIN}/photo/pending-windows`);
        if (response.ok) {
          const data = await response.json();
          for (const req of data.requests || []) {
            if (window.electron?.openPhotoManagerWindow) {
              window.electron.openPhotoManagerWindow(req.path || null);
            }
          }
        }
      } catch {
        // 서버 연결 실패 무시
      }
    };

    const interval = setInterval(pollPhotoWindows, 300);
    return () => clearInterval(interval);
  }, []);

  // ─── Launcher WS: Electron 메인 프로세스로 이전됨 (Phase 27) ───
  // 백엔드 → Electron 창 제어는 main.js의 startLauncherWS()에서 처리
  // 컴포넌트 lifecycle과 무관하게 항상 연결 유지

  // 폴더에서 아이템이 드롭되었을 때 이벤트 수신
  useEffect(() => {
    if (window.electron?.onItemDroppedFromFolder) {
      window.electron.onItemDroppedFromFolder((data: { itemId: string; itemType: string; sourceFolderId: string }) => {
        console.log('폴더에서 아이템 드롭됨:', data);
        loadProjects();
        loadSwitches();
      });
    }

    return () => {
      if (window.electron?.removeItemDroppedFromFolder) {
        window.electron.removeItemDroppedFromFolder();
      }
    };
  }, [loadProjects, loadSwitches]);

  // 프로젝트 창에서 스위치 변경 시 런처 새로고침
  useEffect(() => {
    if (window.electron?.onLauncherRefresh) {
      window.electron.onLauncherRefresh(() => {
        loadSwitches();
      });
    }

    return () => {
      if (window.electron?.removeLauncherRefresh) {
        window.electron.removeLauncherRefresh();
      }
    };
  }, [loadSwitches]);

  // 다른 창(커뮤니티·메신저 등)의 메시지에서 URL 을 클릭하면 포식 브라우저 오버레이로 연다.
  useEffect(() => {
    if (!window.electron?.onOpenForageUrl) return;
    window.electron.onOpenForageUrl((url: string) => {
      setBrowserOpen(true);
      setPendingBrowserUrl(url);
    });
    return () => window.electron?.removeOpenForageUrl?.();
  }, []);

  // 앱모드의 검색브라우저 타일(ActionDesktop 'forage')이 쏘는 열기 신호 — 같은 창 내 CustomEvent.
  useEffect(() => {
    const openForage = () => setBrowserOpen(true);
    window.addEventListener('indiebiz:open-forage', openForage);
    return () => window.removeEventListener('indiebiz:open-forage', openForage);
  }, []);

  // 같은 창의 표면(공유창고 등)이 특정 URL을 포식 브라우저로 열도록 쏘는 신호 — detail=url.
  // 이웃 창고를 내부 브라우저로 열어야 창틀이 내 것이라 우클릭 리트윗이 산다.
  useEffect(() => {
    const openForageUrl = (e: Event) => {
      const url = (e as CustomEvent<string>).detail;
      if (!url) return;
      setBrowserOpen(true);
      setPendingBrowserUrl(url);
    };
    window.addEventListener('indiebiz:open-forage-url', openForageUrl);
    return () => window.removeEventListener('indiebiz:open-forage-url', openForageUrl);
  }, []);

  const handleCreateProject = async (templateName: string, projectKind: 'general' | 'research') => {
    if (!newProjectName.trim()) return;

    try {
      await api.createProject(newProjectName, templateName, undefined, projectKind);
      setNewProjectName('');
      setShowNewProjectDialog(false);
      loadProjects();
    } catch (error) {
      console.error('Failed to create project:', error);
    }
  };

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return;

    try {
      await api.createFolder(newFolderName);
      setNewFolderName('');
      setShowNewFolderDialog(false);
      loadProjects();
    } catch (error) {
      console.error('Failed to create folder:', error);
    }
  };

  const handleCreateMultiChatRoom = async () => {
    if (!newMultiChatName.trim()) return;

    try {
      await api.createMultiChatRoom(newMultiChatName);
      setNewMultiChatName('');
      setShowNewMultiChatDialog(false);
      loadMultiChatRooms();
    } catch (error) {
      console.error('Failed to create multi-chat room:', error);
    }
  };

  const handleOpenSettings = async () => {
    try {
      // 모두 읽은 뒤에만 편집한다. 조회 실패를 초기값으로 저장하면 다른 티어까지 덮어쓴다.
      const [config, lConfig, mConfig] = await Promise.all([
        api.getSystemAI(), api.getLightweightAI(), api.getMidtierAI(),
      ]);
      setSystemAiSettings({
        enabled: config.enabled ?? true,
        provider: config.provider ?? 'google',
        model: config.model ?? 'gemini-2.0-flash-exp',
        apiKey: config.apiKey ?? '',
        providerModels: config.providerModels ?? {},
        providerHasApiKey: config.providerHasApiKey ?? {},
      });
      setLightweightAiSettings({
        enabled: lConfig.enabled ?? true,
        provider: lConfig.provider ?? 'google',
        model: lConfig.model ?? 'gemini-2.5-flash-lite',
        apiKey: lConfig.apiKey ?? '',
        providerModels: lConfig.providerModels ?? {},
        providerHasApiKey: lConfig.providerHasApiKey ?? {},
      });
      setMidtierAiSettings({
        enabled: mConfig.enabled ?? true,
        provider: mConfig.provider ?? 'google',
        model: mConfig.model ?? 'gemini-2.5-flash',
        apiKey: mConfig.apiKey ?? '',
        providerModels: mConfig.providerModels ?? {},
        providerHasApiKey: mConfig.providerHasApiKey ?? {},
      });
      setShowSettingsDialog(true);
    } catch (error) {
      console.error('Failed to load system AI settings:', error);
      alert('모델 설정을 불러오지 못했습니다. 기존 설정은 유지됩니다. 잠시 후 다시 열어주세요.');
    }
  };

  const handleSaveSystemAi = async () => {
    try {
      await api.updateSystemAI(systemAiSettings);
      await api.updateLightweightAI(lightweightAiSettings);
      await api.updateMidtierAI(midtierAiSettings);
      setShowSettingsDialog(false);
    } catch (error) {
      console.error('Failed to save settings:', error);
    }
  };

  const handleOpenScheduler = async () => {
    try {
      const events = await api.getAllEvents();
      setSchedulerTasks(events);
      setShowSchedulerDialog(true);
    } catch (error) {
      console.error('Failed to load events:', error);
      setSchedulerTasks([]);
      setShowSchedulerDialog(true);
    }
  };

  const handleOpenCalendar = async () => {
    try {
      await api.openCalendar();
    } catch (error) {
      console.error('Failed to open calendar:', error);
    }
  };

  const formatLastRun = (lastRun: string | null | undefined): string => {
    if (!lastRun) return '-';
    try {
      const date = new Date(lastRun);
      return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
    } catch {
      return '-';
    }
  };

  // 스위치 편집 시작
  const handleEditSwitch = (switchId: string) => {
    const sw = switches.find(s => s.id === switchId);
    if (!sw) return;

    setEditingSwitchData(sw);
    setSwitchEditForm({
      name: sw.name,
      icon: sw.icon || '⚡',
      command: sw.command,
    });
    setShowSwitchEditDialog(true);
  };

  // 스위치 편집 저장
  const handleSaveSwitchEdit = async () => {
    if (!editingSwitchData) return;
    if (!switchEditForm.name || !switchEditForm.command) {
      alert('이름과 명령어를 입력하세요.');
      return;
    }

    try {
      await api.updateSwitch(editingSwitchData.id, {
        name: switchEditForm.name,
        icon: switchEditForm.icon,
        command: switchEditForm.command,
      });
      setShowSwitchEditDialog(false);
      setEditingSwitchData(null);
      loadSwitches();  // 목록 새로고침
    } catch (error) {
      console.error('스위치 수정 실패:', error);
      alert('스위치 수정에 실패했습니다.');
    }
  };

  const ActiveModeIcon = MODE_META[launcherTab].icon;
  // 승격 앱이 활성일 때(앱 모드 + activeAppId) 선택기 라벨을 그 앱의 아이콘·이름으로 표시.
  const activeMeta = activeAppId ? appMetaById[activeAppId] : null;
  const showingApp = launcherTab === 'app' && !!activeMeta;

  // 기본 다섯 모드 선택 — 승격 딥링크 해제. 검색 브라우저 오버레이도 닫는다(모드가 가려지는 사고 방지).
  const selectMode = (m: LauncherMode) => { setActiveAppId(null); setLauncherTab(m); setShowModeMenu(false); setBrowserOpen(false); };
  // 승격 앱 선택 — 앱 모드로 전환하고 그 앱을 딥링크로 연다.
  // ★열기는 '상태'가 아니라 '행위'다: 이미 activeAppId 인 앱을 다시 골라도 열려야 한다.
  //   (네이티브 창 앱은 창을 닫아도 activeAppId 가 그대로 남고 localStorage 로 재시작까지 살아남아,
  //    id 동일성만 보면 두 번째부터 영영 no-op 이 된다 — 시스템(files) 앱이 안 열리던 원인.)
  //   nonce 를 올려 매 선택이 새 열기 신호가 되게 한다. 매니페스트 재조회 같은 무관한 리렌더는
  //   nonce 가 그대로라 여전히 앱을 다시 열지 않는다.
  const selectPromoted = (id: string) => {
    setActiveAppId(id);
    setAppOpenNonce((n) => n + 1);
    setLauncherTab('app');
    setShowModeMenu(false);
    setBrowserOpen(false);
  };
  // 승격 앱 빼기 — 드롭다운 ✕에서 바로. 레이아웃을 읽어 promoted 만 걷어내고 다시 저장(다른 필드 보존).
  const demotePromoted = async (id: string) => {
    setPromotedIds((prev) => prev.filter((x) => x !== id));  // 낙관적
    if (activeAppId === id) setActiveAppId(null);             // 열려있던 앱이면 앱 홈으로
    try {
      const layout = await api.getAppLayout();
      const next = { ...layout, promoted: (layout.promoted || []).filter((x) => x !== id) };
      await api.saveAppLayout(next);
    } catch (e) {
      console.error('승격 해제 실패:', e);
      loadPromoted().catch(() => {});  // 실패 시 서버 상태로 되돌림
    }
  };

  return { __uiTools, React, ActionDesktop, ActiveModeIcon, BACKEND_ORIGIN, BookOpen, Bot, Boxes, ChevronDown, Clock, Contact, ContextMenu, DraggableIcon, DraggableTrash, FileText, Folder, ForageBrowser, Globe, GuideDialog, HelpCircle, IS_WEB_SURFACE, Info, LAUNCHER_MODES, LanguagePicker, Laptop, Layers, MODE_META, ManualMode, NewFolderDialog, NewProjectDialog, OnboardingDialog, ScanLine, SchedulerDialog, Settings, SettingsDialog, Smartphone, SwitchEditDialog, TrashDialog, UiText, UserManualDialog, Users, WarehouseView, X, Zap, activeAppId, activeMeta, alert, api, appOpenNonce, browserOpen, checkFolderHover, checkTrashHover, clipToPhone, clipboard, closeContextMenu, console, contextMenu, demotePromoted, desktopRef, displayProjects, displaySwitches, editingSwitchData, error, folderRefs, formatLastRun, getItemName, handleArrangeIcons, handleCancelRename, handleContextMenu, handleCopy, handleCreateFolder, handleCreateMultiChatRoom, handleCreateProject, handleDragEnd, handleDragStart, handleDropOnTrash, handleEditSwitch, handleEmptyTrash, handleExecuteSwitch, handleFinishRename, handleItemContextMenu, handleMoveToFolder, handleOpenCalendar, handleOpenMultiChatRoom, handleOpenProject, handleOpenScheduler, handleOpenSettings, handleOpenTrash, handlePaste, handlePositionChange, handleRestoreFromTrash, handleSaveSwitchEdit, handleSaveSystemAi, handleSelect, handleStartRename, hoveringFolderId, isLoading, launcherTab, lightweightAiSettings, loadMultiChatRooms, loadPromoted, loadTrashItems, logoImage, mainMenuRef, midtierAiSettings, mobileToolsOpen, modeMenuRef, multiChatRooms, newFolderName, newMultiChatName, newProjectName, openSystemAI, openTool, pendingBrowserUrl, projectQuery, promotedApps, renamingItem, retryLauncherData, schedulerTasks, selectMode, selectPromoted, selectedItem, sendClipboardToPhone, setBrowserOpen, setContextMenu, setEditingSwitchData, setHoveringFolderId, setLightweightAiSettings, setMidtierAiSettings, setMobileToolsOpen, setMultiChatRooms, setNewFolderName, setNewMultiChatName, setNewProjectName, setPendingBrowserUrl, setProjectQuery, setShowApiKey, setShowGuideDialog, setShowLightweightApiKey, setShowMainMenu, setShowMidtierApiKey, setShowModeMenu, setShowNewFolderDialog, setShowNewMultiChatDialog, setShowNewProjectDialog, setShowOnboardingDialog, setShowSchedulerDialog, setShowSettingsDialog, setShowSwitchEditDialog, setShowTrashDialog, setShowUserManualDialog, setSwitchEditForm, setSystemAiSettings, setTrashPosition, showApiKey, showGuideDialog, showGuideOnce, showLightweightApiKey, showMainMenu, showMidtierApiKey, showModeMenu, showNewFolderDialog, showNewMultiChatDialog, showNewProjectDialog, showOnboardingDialog, showSchedulerDialog, showSettingsDialog, showSwitchEditDialog, showTrashDialog, showUserManualDialog, showingApp, staticAppLabel, switchEditForm, systemAiSettings, toolNavigation, trashHover, trashItems, trashPosition, trashRef, ui, window };
}
export type LauncherDisplayBindings = ReturnType<typeof useLauncherHost>;
export function Launcher() { return <LauncherDisplay bindings={useLauncherHost()}/>; }
