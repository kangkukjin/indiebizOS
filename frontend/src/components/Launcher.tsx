/**
 * 런처 - 데스크탑 스타일 프로젝트/폴더/스위치 관리
 */

import { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { Zap, Settings, Clock, Folder, Globe, Bot, Package, Users, Contact, HelpCircle, Info, ChevronDown, BookOpen, ScanLine, Search, Gauge, LayoutGrid, Compass, X, Smartphone } from 'lucide-react';
import logoImage from '../assets/logo-indiebiz.png';
import { useAppStore } from '../stores/appStore';
import { api } from '../lib/api';
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
  ToolboxDialog,
  SwitchEditDialog,
} from './launcher-components';
import { GuideDialog } from './GuideDialog';
import { UserManualDialog } from './UserManualDialog';
import { ActionDesktop, STATIC_APP_META } from './ActionDesktop';
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
  warehouse: { label: '공유창고', icon: Package },
  autopilot: { label: '자율주행', icon: Compass },
  manual: { label: '조종실', icon: Gauge },
  app: { label: '앱', icon: LayoutGrid },
};

export function Launcher() {
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
  const [promotedIds, setPromotedIds] = useState<string[]>([]);
  // 승격 앱 아이콘·라벨 해소용 — static 도메인 메타 + 매니페스트(런타임) 병합.
  const [appMetaById, setAppMetaById] = useState<Record<string, { icon: string; label: string }>>({});

  const loadPromoted = useCallback(async () => {
    try {
      const layout = await api.getAppLayout();
      setPromotedIds(layout.promoted || []);
    } catch { /* 백엔드 미기동 시 무시 */ }
    try {
      const r = await fetch('http://127.0.0.1:8765/launcher/instruments');
      if (r.ok) {
        const d = await r.json();
        const map: Record<string, { icon: string; label: string }> = {};
        for (const m of STATIC_APP_META) map[m.id] = { icon: m.icon, label: m.label };
        for (const inst of (d.instruments || [])) map[inst.id] = { icon: inst.icon, label: inst.name };
        setAppMetaById(map);
      }
    } catch { /* 무시 */ }
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
  const modeMenuRef = useRef<HTMLDivElement>(null);
  // 검색 브라우저를 특정 URL로 열도록 넘기는 신호(예: X-Ray). ForageBrowser가 소비 후 null 복귀.
  const [pendingBrowserUrl, setPendingBrowserUrl] = useState<string | null>(null);
  const [showNewProjectDialog, setShowNewProjectDialog] = useState(false);
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  const [showNewMultiChatDialog, setShowNewMultiChatDialog] = useState(false);
  const [showSchedulerDialog, setShowSchedulerDialog] = useState(false);
  const [showToolboxDialog, setShowToolboxDialog] = useState(false);
  const [showSwitchEditDialog, setShowSwitchEditDialog] = useState(false);
  const [showGuideDialog, setShowGuideDialog] = useState(false);
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
      // 맥 클립보드 → 폰 클립보드 + 도착 알림. 직결(Wi-Fi) 우선, LTE 면 백엔드가
      // heartbeat 롱폴 푸시 큐로 폴백한다(ibl_engine._forward_to_phone).
      const clip = { op: 'clipboard', text };
      const noti = { op: 'notify', title: '📋 맥 클립보드 도착', body: '입력창을 길게 눌러 붙여넣기 하세요' };
      const code = `[limbs:phone]${JSON.stringify(clip)} >> [limbs:phone]${JSON.stringify(noti)}`;
      const r = await fetch('http://127.0.0.1:8765/ibl/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, project_id: '앱모드' }),
      });
      const data = await r.json().catch(() => ({}));
      const raw = JSON.stringify(data ?? {});
      if (raw.includes('"queued":true') || raw.includes('"queued": true')) done('queued');
      else if (r.ok && data?.success !== false && !raw.includes('phone_unreachable')) done('ok');
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

  useEffect(() => {
    loadProjects();
    loadSwitches();
    loadMultiChatRooms();
    loadPromoted();
  }, [loadProjects, loadSwitches, loadPromoted]);

  // 활성(승격) 앱 영속화 — 다음 실행 시 마지막으로 연 승격 앱으로 복귀.
  useEffect(() => {
    if (activeAppId) localStorage.setItem('indiebiz_launcher_app', activeAppId);
    else localStorage.removeItem('indiebiz_launcher_app');
  }, [activeAppId]);

  // 첫 실행 시 가이드 표시
  useEffect(() => {
    const hasSeenGuide = localStorage.getItem('indiebiz_has_seen_guide');
    if (!hasSeenGuide) {
      // 약간의 딜레이 후 가이드 표시 (앱이 로드된 후)
      const timer = setTimeout(() => {
        setShowGuideDialog(true);
        localStorage.setItem('indiebiz_has_seen_guide', 'true');
      }, 500);
      return () => clearTimeout(timer);
    }
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
    const pollPendingWindows = async () => {
      try {
        const response = await fetch('http://127.0.0.1:8765/pcmanager/pending-windows');
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
    const pollPhotoWindows = async () => {
      try {
        const response = await fetch('http://127.0.0.1:8765/photo/pending-windows');
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

  // Android Manager 창 열기 요청 폴링
  useEffect(() => {
    const pollAndroidWindows = async () => {
      try {
        const response = await fetch('http://127.0.0.1:8765/android/pending-windows');
        if (response.ok) {
          const data = await response.json();
          for (const req of data.requests || []) {
            if (window.electron?.openAndroidManagerWindow) {
              window.electron.openAndroidManagerWindow(req.device_id || null, req.project_id || null);
            }
          }
        }
      } catch {
        // 서버 연결 실패 무시
      }
    };

    const interval = setInterval(pollAndroidWindows, 300);
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

  const handleCreateProject = async (templateName: string) => {
    if (!newProjectName.trim()) return;

    try {
      await api.createProject(newProjectName, templateName);
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
      const config = await api.getSystemAI();
      setSystemAiSettings({
        enabled: config.enabled ?? true,
        provider: config.provider ?? 'google',
        model: config.model ?? 'gemini-2.0-flash-exp',
        apiKey: config.apiKey ?? '',
      });
      // 경량 AI 설정 로드
      try {
        const lConfig = await api.getLightweightAI();
        setLightweightAiSettings({
          enabled: lConfig.enabled ?? true,
          provider: lConfig.provider ?? 'google',
          model: lConfig.model ?? 'gemini-2.5-flash-lite',
          apiKey: lConfig.apiKey ?? '',
        });
      } catch { /* 경량 AI 설정 없으면 기본값 유지 */ }
      // 중급 AI 설정 로드
      try {
        const mConfig = await api.getMidtierAI();
        setMidtierAiSettings({
          enabled: mConfig.enabled ?? true,
          provider: mConfig.provider ?? 'google',
          model: mConfig.model ?? 'gemini-2.5-flash',
          apiKey: mConfig.apiKey ?? '',
        });
      } catch { /* 중급 AI 설정 없으면 기본값 유지 */ }
      setShowSettingsDialog(true);
    } catch (error) {
      console.error('Failed to load system AI settings:', error);
      setShowSettingsDialog(true);
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
  const selectPromoted = (id: string) => { setActiveAppId(id); setLauncherTab('app'); setShowModeMenu(false); setBrowserOpen(false); };
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
      loadPromoted();  // 실패 시 서버 상태로 되돌림
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#F5F1EB]">
      {/* 상단 툴바 */}
      <div className="h-11 flex items-center justify-end px-4 drag bg-gradient-to-b from-[#F7F3ED] to-[#F5F1EB] border-b border-[#E5DFD5]">
        <div className="flex items-center gap-1.5 no-drag">
          {/* 모드 선택기 — 네 표면(자율주행/조종실/앱/공유창고)을 오간다. X-Ray 앞. */}
          <div className="relative" ref={modeMenuRef}>
            <button
              onClick={() => setShowModeMenu((v) => { if (!v) loadPromoted(); return !v; })}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-colors text-[#6B5B4F] ${showModeMenu ? 'bg-[#EAE4DA]' : 'hover:bg-[#EAE4DA] active:bg-[#E0D9CC]'}`}
              title="모드 전환"
              aria-haspopup="true"
              aria-expanded={showModeMenu}
            >
              {showingApp
                ? <span className="text-[15px] leading-none">{activeMeta!.icon}</span>
                : <ActiveModeIcon size={15} />}
              <span className="text-[13px] font-medium">{showingApp ? activeMeta!.label : MODE_META[launcherTab].label}</span>
              <ChevronDown size={12} className={`transition-transform ${showModeMenu ? 'rotate-180' : ''}`} />
            </button>
            {showModeMenu && (
              <div className="absolute left-0 top-full mt-2 bg-white rounded-xl shadow-xl border border-stone-200 py-1.5 min-w-[190px] z-50 overflow-hidden">
                {LAUNCHER_MODES.map((m) => {
                  const Icon = MODE_META[m].icon;
                  const active = launcherTab === m && !(m === 'app' && showingApp);
                  return (
                    <button
                      key={m}
                      onClick={() => selectMode(m)}
                      className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${active ? 'bg-amber-50 text-amber-900' : 'text-[#4A4035] hover:bg-amber-50'}`}
                    >
                      <Icon size={16} className={active ? 'text-amber-600' : 'text-stone-500'} />
                      <span className="text-sm">{MODE_META[m].label}</span>
                    </button>
                  );
                })}
                {/* 구분선 아래 = 앱 모드에서 승격한 앱들. 선택하면 그 앱이 바로 열린다. */}
                {promotedApps.length > 0 && (
                  <>
                    <div className="border-t border-stone-100 my-1" />
                    {promotedApps.map((app) => {
                      const active = showingApp && activeAppId === app.id;
                      return (
                        <div
                          key={app.id}
                          className={`group flex items-center transition-colors ${active ? 'bg-amber-50' : 'hover:bg-amber-50'}`}
                        >
                          <button
                            onClick={() => selectPromoted(app.id)}
                            className={`flex-1 min-w-0 flex items-center gap-3 pl-4 pr-2 py-2.5 text-left ${active ? 'text-amber-900' : 'text-[#4A4035]'}`}
                          >
                            <span className="text-base leading-none w-4 text-center">{app.icon}</span>
                            <span className="text-sm truncate">{app.label}</span>
                          </button>
                          <button
                            onClick={() => demotePromoted(app.id)}
                            title="런처에서 빼기"
                            aria-label={`${app.label} 런처에서 빼기`}
                            className="shrink-0 mr-2 p-1 rounded-md text-stone-300 hover:text-red-600 hover:bg-red-50 transition-colors"
                          >
                            <X size={14} />
                          </button>
                        </div>
                      );
                    })}
                  </>
                )}
              </div>
            )}
          </div>

          <div className="w-px h-5 bg-[#D8D1C3] mx-1" aria-hidden="true" />

          {/* 그룹 A: 세계 / 감각 */}
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => {
                // 외부 브라우저 대신 검색 브라우저(포식) 오버레이의 한 탭으로 X-Ray 대시보드를 연다.
                setBrowserOpen(true);
                setPendingBrowserUrl('http://127.0.0.1:8765/xray/app');
              }}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg hover:bg-[#EAE4DA] active:bg-[#E0D9CC] transition-colors text-[#6B5B4F]"
              title="System X-Ray - 시스템 상태를 검색 브라우저 탭으로 연다"
            >
              <ScanLine size={15} />
              <span className="text-[13px]">X-Ray</span>
            </button>
            <button
              onClick={() => {
                // 커뮤니티 서비스(옛 IndieNet) — 표면과 무관하게 전용 창으로 진입.
                // 내용은 앱모드와 동일한 IBL 커뮤니티 계기(피드·게시판·내 계정).
                if (window.electron?.openCommunityWindow) {
                  window.electron.openCommunityWindow();
                } else {
                  window.location.hash = '#/community';  // 브라우저 폴백
                }
              }}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg hover:bg-[#EAE4DA] active:bg-[#E0D9CC] transition-colors text-[#6B5B4F]"
              title="IndieNet 커뮤니티"
            >
              <Globe size={15} />
              <span className="text-[13px]">IndieNet</span>
            </button>
          </div>

          <div className="w-px h-5 bg-[#D8D1C3] mx-1" aria-hidden="true" />

          {/* 그룹 B: 소통 */}
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => {
                // 메신저(=이웃관리 CRM) — 표면과 무관하게 전용 창으로 진입.
                // 옛 빠른 연락처(ContactsDialog)·이웃관리 창(NeighborManagerDialog)을 대체.
                if (window.electron?.openMessengerWindow) {
                  window.electron.openMessengerWindow();
                } else {
                  window.location.hash = '#/messenger';  // 브라우저 폴백
                }
              }}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg hover:bg-[#EAE4DA] active:bg-[#E0D9CC] transition-colors text-[#6B5B4F]"
              title="메신저 · 연락처"
            >
              <Contact size={15} />
              <span className="text-[13px]">연락처</span>
            </button>
            <button
              onClick={sendClipboardToPhone}
              disabled={clipToPhone === 'sending'}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-colors ${
                clipToPhone === 'ok' || clipToPhone === 'queued'
                  ? 'text-emerald-700 bg-emerald-50'
                  : clipToPhone === 'err'
                    ? 'text-red-600 bg-red-50'
                    : 'text-[#6B5B4F] hover:bg-[#EAE4DA] active:bg-[#E0D9CC]'
              }`}
              title="맥 클립보드를 폰으로 — 지금 복사(⌘C)된 내용을 폰 클립보드에 넣고 알림을 띄웁니다 (LTE 여도 푸시 큐로 전달)"
            >
              <Smartphone size={15} />
              <span className="text-[13px]">
                {clipToPhone === 'idle' && '폰으로'}
                {clipToPhone === 'sending' && '보내는 중…'}
                {clipToPhone === 'ok' && '도착 ✓'}
                {clipToPhone === 'queued' && '큐 대기 ✓'}
                {clipToPhone === 'err' && '실패'}
              </span>
            </button>
            <button
              onClick={() => { window.electron?.openSystemAIWindow?.(); }}
              className="ml-1 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-br from-amber-500 to-amber-600 text-white shadow-sm hover:shadow-md hover:from-amber-600 hover:to-amber-700 active:translate-y-[0.5px] transition-all"
              title="시스템 AI와 대화"
            >
              <Bot size={15} />
              <span className="text-[13px] font-semibold">시스템 AI</span>
            </button>
          </div>

          <div className="w-px h-5 bg-[#D8D1C3] mx-1" aria-hidden="true" />

          {/* 메인 메뉴 (드롭다운) — 예약작업 등 관리 항목을 펼친다 */}
          <div className="relative" ref={mainMenuRef}>
            <button
              onClick={() => setShowMainMenu(!showMainMenu)}
              className={`flex items-center gap-1 px-1.5 py-1 rounded-lg transition-all text-[#6B5B4F] ${
                showMainMenu ? 'bg-[#EAE4DA]' : 'hover:bg-[#EAE4DA]'
              }`}
              title="메뉴"
              aria-expanded={showMainMenu}
              aria-haspopup="true"
            >
              <img src={logoImage} alt="IndieBiz" className="w-9 h-9 object-contain" style={{ mixBlendMode: 'multiply' }} />
              <ChevronDown size={12} className={`transition-transform ${showMainMenu ? 'rotate-180' : ''}`} />
            </button>

            {showMainMenu && (
              <div className="absolute right-0 top-full mt-2 bg-white rounded-xl shadow-xl border border-stone-200 py-1.5 min-w-[200px] z-50 overflow-hidden">
                <button
                  onClick={() => {
                    handleOpenScheduler();
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-amber-50 text-left text-[#4A4035] transition-colors"
                >
                  <Clock size={16} className="text-stone-500" />
                  <span className="text-sm">예약작업</span>
                </button>
                <div className="border-t border-stone-100 my-1" />
                <button
                  onClick={() => {
                    setShowToolboxDialog(true);
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-amber-50 text-left text-[#4A4035] transition-colors"
                >
                  <Package size={16} className="text-amber-600" />
                  <span className="text-sm">도구 상점</span>
                </button>
                <button
                  onClick={() => {
                    handleOpenSettings();
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-amber-50 text-left text-[#4A4035] transition-colors"
                >
                  <Settings size={16} className="text-stone-500" />
                  <span className="text-sm">설정</span>
                </button>
                <div className="border-t border-stone-100 my-1" />
                <button
                  onClick={() => {
                    setShowGuideDialog(true);
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-amber-50 text-left text-[#4A4035] transition-colors"
                >
                  <HelpCircle size={16} className="text-stone-500" />
                  <span className="text-sm">시작 가이드</span>
                </button>
                <button
                  onClick={() => {
                    setShowUserManualDialog(true);
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-amber-50 text-left text-[#4A4035] transition-colors"
                >
                  <BookOpen size={16} className="text-stone-500" />
                  <span className="text-sm">사용자 메뉴얼</span>
                </button>
                <button
                  onClick={() => {
                    alert(`IndieBiz OS\n버전: 1.0.0\n\n개인과 소규모 비즈니스를 위한 AI 운영체제`);
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-amber-50 text-left text-[#4A4035] transition-colors"
                >
                  <Info size={16} className="text-stone-500" />
                  <span className="text-sm">버전 정보</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 데스크탑 + 포식 오버레이를 한 relative 래퍼로 — 포식 브라우저가 전체를 덮을 수 있게.
          (옛 자율주행/조종실/앱 3토글은 상단 툴바의 모드 선택기로 대체됨) */}
      <div className="relative flex-1 flex flex-col min-h-0">
      {/* 데스크탑 영역 */}
      <div
        ref={desktopRef}
        className="flex-1 relative overflow-hidden"
        onContextMenu={handleContextMenu}
      >
        {launcherTab === 'app' ? (
          // key 에 activeAppId 를 넣어 승격 앱 전환 시 깨끗이 remount(딥링크 재적용).
          <ActionDesktop key={`app:${activeAppId || ''}`} openAppId={activeAppId} />
        ) : launcherTab === 'warehouse' ? (
          <WarehouseView />
        ) : launcherTab === 'manual' ? (
          <ManualMode />
        ) : isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#D97706]" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full text-[#B45309]">
            <p>{error}</p>
            <button
              onClick={() => {
                loadProjects();
                loadSwitches();
              }}
              className="mt-4 px-4 py-2 bg-[#FEF3C7] rounded-lg hover:bg-[#FDE68A] text-[#92400E]"
            >
              다시 시도
            </button>
          </div>
        ) : (
          <>
            {/* 프로젝트 아이콘들 */}
            {displayProjects.map((project) => (
              <DraggableIcon
                key={project.id}
                icon={project.type === 'folder' ? <Folder size={40} /> : '📁'}
                label={project.name}
                position={project.icon_position}
                onDoubleClick={() => handleOpenProject(project)}
                onPositionChange={(x, y) =>
                  handlePositionChange(project.id, 'project', x, y)
                }
                onDragStart={() => handleDragStart(project.id, 'project')}
                onDragEnd={() => {
                  handleDragEnd();
                  setHoveringFolderId(null);
                }}
                onDragMove={(x, y) => {
                  checkTrashHover(x, y);
                  checkFolderHover(x, y, project.id);
                  return trashHover;
                }}
                onDropOnTrash={handleDropOnTrash}
                onDropOnFolder={(folderId) => handleMoveToFolder(project.id, folderId)}
                trashHover={trashHover}
                isFolder={project.type === 'folder'}
                whiteTile={project.type !== 'folder'}
                isFolderHovered={hoveringFolderId === project.id}
                folderRef={(el) => {
                  if (project.type === 'folder') {
                    folderRefs.current[project.id] = el;
                  }
                }}
                hoveringFolderId={hoveringFolderId}
                onContextMenu={(e) => handleItemContextMenu(e, project.id, 'project')}
                onSelect={() => handleSelect(project.id, 'project')}
                isSelected={selectedItem?.id === project.id && selectedItem?.type === 'project'}
                isRenaming={renamingItem?.id === project.id && renamingItem?.type === 'project'}
                onFinishRename={handleFinishRename}
                onCancelRename={handleCancelRename}
              />
            ))}

            {/* 스위치 아이콘들 */}
            {displaySwitches.map((sw) => (
              <DraggableIcon
                key={sw.id}
                icon={sw.icon || <Zap size={40} />}
                label={sw.name}
                position={sw.icon_position}
                onDoubleClick={() => handleExecuteSwitch(sw)}
                onPositionChange={(x, y) =>
                  handlePositionChange(sw.id, 'switch', x, y)
                }
                onDragStart={() => handleDragStart(sw.id, 'switch')}
                onDragEnd={() => {
                  handleDragEnd();
                  setHoveringFolderId(null);
                }}
                onDragMove={(x, y) => {
                  checkTrashHover(x, y);
                  return trashHover;
                }}
                onDropOnTrash={handleDropOnTrash}
                trashHover={trashHover}
                isSwitch
                onContextMenu={(e) => handleItemContextMenu(e, sw.id, 'switch')}
                onSelect={() => handleSelect(sw.id, 'switch')}
                isSelected={selectedItem?.id === sw.id && selectedItem?.type === 'switch'}
                isRenaming={renamingItem?.id === sw.id && renamingItem?.type === 'switch'}
                onFinishRename={handleFinishRename}
                onCancelRename={handleCancelRename}
              />
            ))}

            {/* 다중채팅방 아이콘들 */}
            {multiChatRooms.map((room) => (
              <DraggableIcon
                key={room.id}
                icon={<Users size={40} className="text-purple-500" />}
                label={room.name}
                position={room.icon_position || [600, 100]}
                onDoubleClick={() => handleOpenMultiChatRoom(room)}
                onPositionChange={async (x, y) => {
                  // 로컬 상태 업데이트
                  setMultiChatRooms(prev => prev.map(r =>
                    r.id === room.id ? { ...r, icon_position: [x, y] as [number, number] } : r
                  ));
                  // 서버에 위치 저장
                  try {
                    await api.updateMultiChatRoomPosition(room.id, x, y);
                  } catch (error) {
                    console.error('Failed to update multi-chat room position:', error);
                  }
                }}
                onDragStart={() => handleDragStart(room.id, 'project')}
                onDragEnd={() => {
                  handleDragEnd();
                }}
                onDragMove={(x, y) => {
                  checkTrashHover(x, y);
                  return trashHover;
                }}
                onDropOnTrash={async () => {
                  // 다중채팅방을 휴지통으로 이동
                  try {
                    await api.moveMultiChatRoomToTrash(room.id);
                    loadMultiChatRooms();
                    loadTrashItems();
                  } catch (error) {
                    console.error('Failed to move multi-chat room to trash:', error);
                  }
                }}
                trashHover={trashHover}
                isMultiChat
              />
            ))}

            {/* 휴지통 아이콘 - 드래그 가능 */}
            <DraggableTrash
              trashRef={trashRef}
              trashHover={trashHover}
              position={trashPosition}
              onPositionChange={(x, y) => setTrashPosition({ x, y })}
              onDoubleClick={handleOpenTrash}
              onContextMenu={(e) => {
                e.preventDefault();
                setContextMenu({ x: e.clientX, y: e.clientY, itemId: '__trash__', itemType: 'project' });
              }}
              trashCount={trashItems.projects.length + trashItems.switches.length + (trashItems.chat_rooms?.length || 0)}
            />
          </>
        )}
      </div>

        {/* 포식 브라우저 — 앱모드의 앱(forage 타일)이자 X-Ray·타 창 URL의 착지점. 상시 마운트해
            탭·사냥판 상태를 보존하고 open 으로 표시/숨김만 토글한다. ✕닫기는 현재 표면으로 복귀(오버레이). */}
        <ForageBrowser
          open={browserOpen}
          onClose={() => setBrowserOpen(false)}
          openUrl={pendingBrowserUrl}
          onUrlConsumed={() => setPendingBrowserUrl(null)}
        />
      </div>

      {/* 컨텍스트 메뉴 */}
      <ContextMenu
        contextMenu={contextMenu}
        clipboard={clipboard}
        onClose={closeContextMenu}
        onRename={handleStartRename}
        onCopy={handleCopy}
        onPaste={handlePaste}
        onNewProject={() => setShowNewProjectDialog(true)}
        onNewFolder={() => setShowNewFolderDialog(true)}
        onNewMultiChatRoom={() => setShowNewMultiChatDialog(true)}
        onOpenTrash={handleOpenTrash}
        onEmptyTrash={handleEmptyTrash}
        onArrangeIcons={handleArrangeIcons}
        getItemName={getItemName}
        onEditSwitch={handleEditSwitch}
      />

      {/* 새 프로젝트 다이얼로그 */}
      <NewProjectDialog
        show={showNewProjectDialog}
        name={newProjectName}
        onNameChange={setNewProjectName}
        onSubmit={handleCreateProject}
        onClose={() => setShowNewProjectDialog(false)}
      />

      {/* 새 폴더 다이얼로그 */}
      <NewFolderDialog
        show={showNewFolderDialog}
        name={newFolderName}
        onNameChange={setNewFolderName}
        onSubmit={handleCreateFolder}
        onClose={() => setShowNewFolderDialog(false)}
      />

      {/* 새 다중채팅방 다이얼로그 */}
      {showNewMultiChatDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-96 shadow-xl">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Users size={20} className="text-purple-500" />
              새 다중채팅방
            </h2>
            <input
              type="text"
              value={newMultiChatName}
              onChange={(e) => setNewMultiChatName(e.target.value)}
              placeholder="채팅방 이름"
              className="w-full px-4 py-2 border rounded-lg mb-4 focus:outline-none focus:ring-2 focus:ring-purple-500 text-gray-900"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreateMultiChatRoom();
                if (e.key === 'Escape') setShowNewMultiChatDialog(false);
              }}
            />
            <p className="text-sm text-gray-500 mb-4">
              여러 에이전트와 동시에 대화할 수 있는 토론방입니다.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowNewMultiChatDialog(false)}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleCreateMultiChatRoom}
                className="px-4 py-2 bg-purple-500 text-white hover:bg-purple-600 rounded-lg transition-colors"
              >
                만들기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 설정 다이얼로그 */}
      <SettingsDialog
        show={showSettingsDialog}
        settings={systemAiSettings}
        showApiKey={showApiKey}
        onSettingsChange={setSystemAiSettings}
        onToggleApiKey={() => setShowApiKey(!showApiKey)}
        lightweightSettings={lightweightAiSettings}
        showLightweightApiKey={showLightweightApiKey}
        onLightweightSettingsChange={setLightweightAiSettings}
        onToggleLightweightApiKey={() => setShowLightweightApiKey(!showLightweightApiKey)}
        midtierSettings={midtierAiSettings}
        showMidtierApiKey={showMidtierApiKey}
        onMidtierSettingsChange={setMidtierAiSettings}
        onToggleMidtierApiKey={() => setShowMidtierApiKey(!showMidtierApiKey)}
        onSave={handleSaveSystemAi}
        onClose={() => setShowSettingsDialog(false)}
      />

      {/* 휴지통 다이얼로그 */}
      <TrashDialog
        show={showTrashDialog}
        trashItems={trashItems}
        onRestore={handleRestoreFromTrash}
        onEmpty={handleEmptyTrash}
        onClose={() => setShowTrashDialog(false)}
      />

      {/* 예약작업 다이얼로그 (읽기 전용) */}
      <SchedulerDialog
        show={showSchedulerDialog}
        tasks={schedulerTasks}
        formatLastRun={formatLastRun}
        onClose={() => setShowSchedulerDialog(false)}
        onOpenCalendar={handleOpenCalendar}
      />

      {/* 도구함 다이얼로그 */}
      <ToolboxDialog
        show={showToolboxDialog}
        onClose={() => setShowToolboxDialog(false)}
      />

      {/* 스위치 편집 다이얼로그 */}
      <SwitchEditDialog
        show={showSwitchEditDialog}
        switchData={editingSwitchData}
        form={switchEditForm}
        onFormChange={setSwitchEditForm}
        onSave={handleSaveSwitchEdit}
        onClose={() => {
          setShowSwitchEditDialog(false);
          setEditingSwitchData(null);
        }}
      />

      {/* 시작 가이드 다이얼로그 */}
      <GuideDialog
        show={showGuideDialog}
        onClose={() => setShowGuideDialog(false)}
      />

      {/* 사용자 메뉴얼 다이얼로그 */}
      <UserManualDialog
        show={showUserManualDialog}
        onClose={() => setShowUserManualDialog(false)}
      />
    </div>
  );
}
