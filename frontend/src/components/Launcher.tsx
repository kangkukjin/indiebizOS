/**
 * 런처 - 데스크탑 스타일 프로젝트/폴더/스위치 관리
 */

import { useEffect, useState, useRef } from 'react';
import { Zap, Settings, User, Clock, Folder, Globe, Bot, Package, Building2, Users, Contact, ScrollText, HelpCircle, Info, ChevronDown, BookOpen, ScanLine } from 'lucide-react';
import logoImage from '../assets/logo-indiebiz.png';
import { useAppStore } from '../stores/appStore';
import { api } from '../lib/api';
import type { Project, Switch, SchedulerTask } from '../types';
import {
  DraggableIcon,
  DraggableTrash,
  ContextMenu,
  NewProjectDialog,
  NewFolderDialog,
  ProfileDialog,
  SettingsDialog,
  TrashDialog,
  SchedulerDialog,
  ToolboxDialog,
  SwitchEditDialog,
} from './launcher-components';
import { ContactsDialog } from './ContactsDialog';
import { GuideDialog } from './GuideDialog';
import { UserManualDialog } from './UserManualDialog';
import type {
  ContextMenuState,
  ClipboardItem,
  SelectedItem,
  RenamingItem,
  TrashItems,
  SystemAISettings,
  UnconsciousAISettings,
} from './launcher-components';

export function Launcher() {
  const {
    projects,
    switches,
    loadProjects,
    loadSwitches,
    setCurrentProject,
    setCurrentView,
    isLoading,
    error,
  } = useAppStore();

  const [showNewProjectDialog, setShowNewProjectDialog] = useState(false);
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  const [showNewMultiChatDialog, setShowNewMultiChatDialog] = useState(false);
  const [showProfileDialog, setShowProfileDialog] = useState(false);
  const [showSchedulerDialog, setShowSchedulerDialog] = useState(false);
  const [showToolboxDialog, setShowToolboxDialog] = useState(false);
  const [showSwitchEditDialog, setShowSwitchEditDialog] = useState(false);
  const [showContactsDialog, setShowContactsDialog] = useState(false);
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

  // 다중채팅방 목록
  interface MultiChatRoom {
    id: string;
    name: string;
    description: string;
    participant_count: number;
    icon_position?: [number, number];
  }
  const [multiChatRooms, setMultiChatRooms] = useState<MultiChatRoom[]>([]);
  const [profileContent, setProfileContent] = useState('');
  const [trashHover, setTrashHover] = useState(false);
  const [draggedItem, setDraggedItem] = useState<{ id: string; type: 'project' | 'switch' } | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);

  // 클립보드 (복사/붙여넣기)
  const [clipboard, setClipboard] = useState<ClipboardItem | null>(null);

  // 선택된 아이템
  const [selectedItem, setSelectedItem] = useState<SelectedItem | null>(null);

  // 이름 변경 모드
  const [renamingItem, setRenamingItem] = useState<RenamingItem | null>(null);

  // 휴지통 관련 상태
  const [showTrashDialog, setShowTrashDialog] = useState(false);
  const [trashItems, setTrashItems] = useState<TrashItems>({ projects: [], switches: [], chat_rooms: [] });
  const [trashPosition, setTrashPosition] = useState({ x: -1, y: -1 }); // -1은 우하단 기본 위치

  // 폴더 드래그 앤 드롭 관련 상태
  const [hoveringFolderId, setHoveringFolderId] = useState<string | null>(null);
  const folderRefs = useRef<{ [key: string]: HTMLDivElement | null }>({});

  // 스케줄러 관련 상태
  const [schedulerTasks, setSchedulerTasks] = useState<SchedulerTask[]>([]);

  // 설정 다이얼로그 상태
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [systemAiSettings, setSystemAiSettings] = useState<SystemAISettings>({
    enabled: true,
    provider: 'google',
    model: 'gemini-2.0-flash-exp',
    apiKey: '',
  });
  const [unconsciousAiSettings, setUnconsciousAiSettings] = useState<UnconsciousAISettings>({
    enabled: true,
    provider: 'google',
    model: 'gemini-2.0-flash-lite',
    apiKey: '',
  });
  const [showUnconsciousApiKey, setShowUnconsciousApiKey] = useState(false);

  const trashRef = useRef<HTMLDivElement>(null);
  const desktopRef = useRef<HTMLDivElement>(null);

  const loadMultiChatRooms = async () => {
    try {
      const rooms = await api.getMultiChatRooms();
      // 아이콘 위치가 없으면 기본 위치 할당
      const roomsWithPosition: MultiChatRoom[] = rooms.map((room, index) => ({
        id: room.id,
        name: room.name,
        description: room.description,
        participant_count: room.participant_count,
        icon_position: room.icon_position || [600 + (index % 5) * 100, 100 + Math.floor(index / 5) * 100] as [number, number],
      }));
      setMultiChatRooms(roomsWithPosition);
    } catch (error) {
      console.error('Failed to load multi-chat rooms:', error);
    }
  };

  useEffect(() => {
    loadProjects();
    loadSwitches();
    loadMultiChatRooms();
  }, [loadProjects, loadSwitches]);

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

  // 루트 레벨 아이템만 표시 (휴지통 제외)
  const displayProjects = projects.filter((p) => !p.parent_folder && !p.in_trash);
  const displaySwitches = switches.filter((s) => !s.parent_folder && !s.in_trash);

  // 폴더 아이템만 필터 (드롭 타겟용)
  const folderTargets = displayProjects.filter(p => p.type === 'folder');

  const handleOpenProject = (project: Project) => {
    if (project.type === 'folder') {
      if (window.electron?.openFolderWindow) {
        window.electron.openFolderWindow(project.id, project.name);
      } else {
        window.location.hash = `/folder/${project.id}`;
      }
    } else {
      if (window.electron?.openProjectWindow) {
        window.electron.openProjectWindow(project.id, project.name);
      } else {
        setCurrentProject(project);
        setCurrentView('manager');
      }
    }
  };

  const handleMoveToFolder = async (itemId: string, targetFolderId: string) => {
    try {
      await api.moveItem(itemId, targetFolderId);
      loadProjects();
    } catch (error) {
      console.error('Failed to move item:', error);
    }
  };

  const handleExecuteSwitch = async (sw: Switch) => {
    try {
      await api.executeSwitch(sw.id);
      console.log('Switch executed:', sw.name);
    } catch (error) {
      console.error('Failed to execute switch:', error);
    }
  };

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

  const handleOpenMultiChatRoom = (room: MultiChatRoom) => {
    if (window.electron?.openMultiChatWindow) {
      window.electron.openMultiChatWindow(room.id, room.name);
    } else {
      window.location.hash = `/multichat/${room.id}`;
    }
  };

  const handleOpenMyProfile = async () => {
    try {
      const content = await api.getProfile();
      setProfileContent(content || '');
      setShowProfileDialog(true);
    } catch (error) {
      console.error('Failed to load profile:', error);
      setProfileContent('');
      setShowProfileDialog(true);
    }
  };

  const handleSaveProfile = async () => {
    try {
      await api.updateProfile(profileContent);
      setShowProfileDialog(false);
    } catch (error) {
      console.error('Failed to save profile:', error);
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
      // 무의식 AI 설정도 로드
      try {
        const uConfig = await api.getUnconsciousAI();
        setUnconsciousAiSettings({
          enabled: uConfig.enabled ?? true,
          provider: uConfig.provider ?? 'google',
          model: uConfig.model ?? 'gemini-2.0-flash-lite',
          apiKey: uConfig.apiKey ?? '',
        });
      } catch { /* 무의식 AI 설정 없으면 기본값 유지 */ }
      setShowSettingsDialog(true);
    } catch (error) {
      console.error('Failed to load system AI settings:', error);
      setShowSettingsDialog(true);
    }
  };

  const handleSaveSystemAi = async () => {
    try {
      await api.updateSystemAI(systemAiSettings);
      await api.updateUnconsciousAI(unconsciousAiSettings);
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

  const handlePositionChange = async (
    id: string,
    type: 'project' | 'switch',
    x: number,
    y: number
  ) => {
    try {
      if (type === 'project') {
        await api.updateProjectPosition(id, x, y);
      } else {
        await api.updateSwitchPosition(id, x, y);
      }
    } catch (error) {
      console.error('Failed to update position:', error);
    }
  };

  // 아이콘 격자 정렬 (가장 가까운 격자점으로 스냅)
  const handleArrangeIcons = async () => {
    // 최신 데이터를 서버에서 직접 가져오기
    let latestProjects: Project[] = [];
    let latestSwitches: Switch[] = [];
    let latestMultiChatRooms: MultiChatRoom[] = [];
    try {
      latestProjects = await api.getProjects();
      latestSwitches = await api.getSwitches();
      latestMultiChatRooms = await api.getMultiChatRooms();
      console.log('[아이콘정렬] 다중채팅방:', latestMultiChatRooms);
    } catch (error) {
      console.error('Failed to fetch latest data:', error);
      return;
    }

    const GRID_SIZE = 100; // 격자 크기 (아이콘 간격)
    const PADDING = 20;    // 좌상단 여백

    // 가장 가까운 격자점 계산
    const snapToGrid = (x: number, y: number): { x: number; y: number } => {
      const col = Math.round((x - PADDING) / GRID_SIZE);
      const row = Math.round((y - PADDING) / GRID_SIZE);
      return {
        x: PADDING + Math.max(0, col) * GRID_SIZE,
        y: PADDING + Math.max(0, row) * GRID_SIZE,
      };
    };

    // 루트 레벨 아이템만 필터링
    const rootProjects = latestProjects.filter((p: Project & { in_trash?: boolean }) => !p.parent_folder && !p.in_trash);
    const rootSwitches = latestSwitches.filter((s: Switch) => !s.parent_folder && !s.in_trash);

    // 모든 아이템 수집 (icon_position은 [x, y] 배열)
    const allItems: { id: string; type: 'project' | 'switch' | 'multichat'; x: number; y: number }[] = [
      ...rootProjects.map(p => ({
        id: p.id,
        type: 'project' as const,
        x: Array.isArray(p.icon_position) ? p.icon_position[0] : 100,
        y: Array.isArray(p.icon_position) ? p.icon_position[1] : 100,
      })),
      ...rootSwitches.map(s => ({
        id: s.id,
        type: 'switch' as const,
        x: Array.isArray(s.icon_position) ? s.icon_position[0] : 100,
        y: Array.isArray(s.icon_position) ? s.icon_position[1] : 100,
      })),
      ...latestMultiChatRooms.map(r => ({
        id: r.id,
        type: 'multichat' as const,
        x: Array.isArray(r.icon_position) ? r.icon_position[0] : 100,
        y: Array.isArray(r.icon_position) ? r.icon_position[1] : 100,
      })),
    ];

    // 점유된 격자점 추적 (충돌 방지)
    const occupiedGrids = new Set<string>();

    // 가까운 격자점 찾기 (충돌 시 다른 빈 격자점 찾기)
    const findNearestFreeGrid = (x: number, y: number): { x: number; y: number } => {
      const snapped = snapToGrid(x, y);
      const key = `${snapped.x},${snapped.y}`;

      if (!occupiedGrids.has(key)) {
        return snapped;
      }

      // 충돌 시 주변 빈 격자점 탐색 (나선형으로)
      for (let radius = 1; radius <= 20; radius++) {
        for (let dx = -radius; dx <= radius; dx++) {
          for (let dy = -radius; dy <= radius; dy++) {
            if (Math.abs(dx) !== radius && Math.abs(dy) !== radius) continue;
            const newX = PADDING + (Math.round((x - PADDING) / GRID_SIZE) + dx) * GRID_SIZE;
            const newY = PADDING + (Math.round((y - PADDING) / GRID_SIZE) + dy) * GRID_SIZE;
            if (newX < PADDING || newY < PADDING) continue;
            const newKey = `${newX},${newY}`;
            if (!occupiedGrids.has(newKey)) {
              return { x: newX, y: newY };
            }
          }
        }
      }
      return snapped; // fallback
    };

    // 각 아이템을 가까운 격자점으로 이동
    const updatePromises = allItems.map((item) => {
      const newPos = findNearestFreeGrid(item.x, item.y);
      occupiedGrids.add(`${newPos.x},${newPos.y}`);

      if (item.type === 'project') {
        return api.updateProjectPosition(item.id, newPos.x, newPos.y);
      } else if (item.type === 'switch') {
        return api.updateSwitchPosition(item.id, newPos.x, newPos.y);
      } else {
        console.log(`[아이콘정렬] 다중채팅방 위치 업데이트: ${item.id} -> (${newPos.x}, ${newPos.y})`);
        return api.updateMultiChatRoomPosition(item.id, newPos.x, newPos.y);
      }
    });

    try {
      await Promise.all(updatePromises);
      loadProjects();
      loadSwitches();
      loadMultiChatRooms();
    } catch (error) {
      console.error('Failed to arrange icons:', error);
    }
  };

  // 복사 기능
  const handleCopy = (id: string, type: 'project' | 'switch') => {
    setClipboard({ id, type });
    console.log(`복사됨: ${type} - ${id}`);
  };

  // 붙여넣기 기능
  const handlePaste = async () => {
    if (!clipboard) return;

    try {
      if (clipboard.type === 'project') {
        await api.copyProject(clipboard.id);
        loadProjects();
      } else if (clipboard.type === 'switch') {
        await api.copySwitch(clipboard.id);
        loadSwitches();
      }
      console.log(`붙여넣기 완료: ${clipboard.type} - ${clipboard.id}`);
    } catch (error) {
      console.error('붙여넣기 실패:', error);
    }
  };

  // 선택 핸들러
  const handleSelect = (id: string, type: 'project' | 'switch') => {
    setSelectedItem({ id, type });
  };

  // 이름 변경 시작
  const handleStartRename = (id: string, type: 'project' | 'switch', currentName: string) => {
    setRenamingItem({ id, type, name: currentName });
  };

  // 이름 변경 완료
  const handleFinishRename = async (newName: string) => {
    if (!renamingItem) return;

    const trimmedName = newName.trim();
    if (!trimmedName || trimmedName === renamingItem.name) {
      setRenamingItem(null);
      return;
    }

    try {
      if (renamingItem.type === 'project') {
        await api.renameProject(renamingItem.id, trimmedName);
        loadProjects();
      } else if (renamingItem.type === 'switch') {
        await api.renameSwitch(renamingItem.id, trimmedName);
        loadSwitches();
      }
      console.log(`이름 변경 완료: ${renamingItem.name} → ${trimmedName}`);
    } catch (error) {
      console.error('이름 변경 실패:', error);
    }

    setRenamingItem(null);
  };

  // 이름 변경 취소
  const handleCancelRename = () => {
    setRenamingItem(null);
  };

  // 휴지통 아이템 로드
  const loadTrashItems = async () => {
    try {
      const data = await api.getTrash();
      setTrashItems({ projects: data.projects, switches: data.switches, chat_rooms: data.chat_rooms || [] });
    } catch (error) {
      console.error('휴지통 로드 실패:', error);
    }
  };

  // 휴지통 열기
  const handleOpenTrash = async () => {
    await loadTrashItems();
    setShowTrashDialog(true);
  };

  // 휴지통에서 복원
  const handleRestoreFromTrash = async (itemId: string, itemType: 'project' | 'switch' | 'chat_room') => {
    try {
      await api.restoreFromTrash(itemId, itemType);
      const data = await api.getTrash();
      setTrashItems({ projects: data.projects, switches: data.switches, chat_rooms: data.chat_rooms || [] });
      loadProjects();
      loadSwitches();
      if (itemType === 'chat_room') {
        loadMultiChatRooms();
      }
    } catch (error) {
      console.error('복원 실패:', error);
    }
  };

  // 휴지통 비우기
  const handleEmptyTrash = async () => {
    if (!confirm('휴지통을 비우시겠습니까? 모든 항목이 영구 삭제됩니다.')) return;

    try {
      await api.emptyTrash();
      setTrashItems({ projects: [], switches: [], chat_rooms: [] });
      setShowTrashDialog(false);
    } catch (error) {
      console.error('휴지통 비우기 실패:', error);
    }
  };

  const handleDragStart = (id: string, type: 'project' | 'switch') => {
    setDraggedItem({ id, type });
  };

  const handleDragEnd = () => {
    setDraggedItem(null);
    setTrashHover(false);
  };

  const handleDropOnTrash = async () => {
    if (!draggedItem) return;

    try {
      if (draggedItem.type === 'project') {
        await api.moveProjectToTrash(draggedItem.id);
        loadProjects();
      } else {
        await api.moveSwitchToTrash(draggedItem.id);
        loadSwitches();
      }
    } catch (error) {
      console.error('Failed to move to trash:', error);
    }

    setDraggedItem(null);
    setTrashHover(false);
  };

  const checkTrashHover = (x: number, y: number) => {
    if (!trashRef.current) return false;
    const rect = trashRef.current.getBoundingClientRect();
    const isOver = x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
    setTrashHover(isOver);
    return isOver;
  };

  // 폴더 위에 드래그 중인지 체크
  const checkFolderHover = (x: number, y: number, draggedItemId: string): string | null => {
    for (const folder of folderTargets) {
      if (folder.id === draggedItemId) continue;

      const ref = folderRefs.current[folder.id];
      if (ref) {
        const rect = ref.getBoundingClientRect();
        if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) {
          setHoveringFolderId(folder.id);
          return folder.id;
        }
      }
    }
    setHoveringFolderId(null);
    return null;
  };

  // 컨텍스트 메뉴 (오른쪽 클릭) - 빈 영역
  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY });
  };

  // 아이템 컨텍스트 메뉴 (오른쪽 클릭) - 아이콘 위
  const handleItemContextMenu = (e: React.MouseEvent, id: string, type: 'project' | 'switch') => {
    e.preventDefault();
    e.stopPropagation();
    setSelectedItem({ id, type });
    setContextMenu({ x: e.clientX, y: e.clientY, itemId: id, itemType: type });
  };

  const closeContextMenu = () => {
    setContextMenu(null);
  };

  // 아이템 이름 가져오기 (컨텍스트 메뉴에서 사용)
  const getItemName = (id: string, type: 'project' | 'switch'): string => {
    if (type === 'project') {
      const project = projects.find(p => p.id === id);
      return project?.name || '';
    } else {
      const sw = switches.find(s => s.id === id);
      return sw?.name || '';
    }
  };

  // 컨텍스트 메뉴 외부 클릭 시 닫기
  useEffect(() => {
    const handleClick = () => closeContextMenu();
    if (contextMenu) {
      document.addEventListener('click', handleClick);
      return () => document.removeEventListener('click', handleClick);
    }
  }, [contextMenu]);

  // 키보드 단축키 (Cmd+C / Cmd+V / Ctrl+C / Ctrl+V / F2)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (renamingItem) return;

      if (showNewProjectDialog || showNewFolderDialog || showProfileDialog || showSchedulerDialog) {
        return;
      }

      const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
      const modifier = isMac ? e.metaKey : e.ctrlKey;

      if (modifier && e.key === 'c') {
        if (selectedItem) {
          e.preventDefault();
          handleCopy(selectedItem.id, selectedItem.type);
        }
      } else if (modifier && e.key === 'v') {
        if (clipboard) {
          e.preventDefault();
          handlePaste();
        }
      } else if (e.key === 'F2') {
        if (selectedItem) {
          e.preventDefault();
          const currentName = getItemName(selectedItem.id, selectedItem.type);
          if (currentName) {
            handleStartRename(selectedItem.id, selectedItem.type, currentName);
          }
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [selectedItem, clipboard, renamingItem, projects, switches, showNewProjectDialog, showNewFolderDialog, showProfileDialog, showSchedulerDialog]);

  return (
    <div className="h-full flex flex-col bg-[#F5F1EB]">
      {/* 상단 툴바 */}
      <div className="h-10 flex items-center justify-end px-4 drag bg-[#F5F1EB] border-b border-[#E5DFD5]">
        <div className="flex items-center gap-1 no-drag">
          <button
            onClick={() => {
              if (window.electron?.openIndieNetWindow) {
                window.electron.openIndieNetWindow();
              } else {
                console.log('IndieNet: Electron API 없음');
              }
            }}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-[#EAE4DA] transition-colors text-[#6B5B4F]"
            title="IndieNet 커뮤니티"
          >
            <Globe size={16} />
            <span className="text-sm">IndieNet</span>
          </button>
          <button
            onClick={() => {
              if (window.electron?.openBusinessWindow) {
                window.electron.openBusinessWindow();
              } else {
                console.log('Business: Electron API 없음');
              }
            }}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-[#EAE4DA] transition-colors text-[#6B5B4F]"
            title="비즈니스 관리"
          >
            <Building2 size={16} />
            <span className="text-sm">비즈니스</span>
          </button>
          <button
            onClick={() => setShowContactsDialog(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-[#EAE4DA] transition-colors text-[#6B5B4F]"
            title="빠른 연락처"
          >
            <Contact size={16} />
            <span className="text-sm">빠른 연락처</span>
          </button>
          <button
            onClick={() => { window.electron?.openSystemAIWindow?.(); }}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-[#EAE4DA] transition-colors text-[#6B5B4F] bg-gradient-to-r from-amber-50 to-orange-50"
            title="시스템 AI와 대화"
          >
            <Bot size={16} className="text-amber-600" />
            <span className="text-sm font-medium text-amber-700">시스템 AI</span>
          </button>
          <button
            onClick={handleOpenScheduler}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-[#EAE4DA] transition-colors text-[#6B5B4F]"
            title="예약작업"
          >
            <Clock size={16} />
            <span className="text-sm">예약작업</span>
          </button>
          <button
            onClick={handleOpenMyProfile}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-[#EAE4DA] transition-colors text-[#6B5B4F]"
            title="시스템 메모"
          >
            <User size={16} />
            <span className="text-sm">시스템 메모</span>
          </button>
          {/* 메인 메뉴 (드롭다운) */}
          <div className="relative" ref={mainMenuRef}>
            <button
              onClick={() => setShowMainMenu(!showMainMenu)}
              className="flex items-center gap-1 px-2 py-1.5 rounded-lg hover:bg-[#EAE4DA] transition-colors text-[#6B5B4F]"
              title="메뉴"
            >
              <img src={logoImage} alt="IndieBiz" className="w-12 h-12 object-contain" style={{ mixBlendMode: 'multiply' }} />
              <ChevronDown size={12} className={`transition-transform ${showMainMenu ? 'rotate-180' : ''}`} />
            </button>

            {showMainMenu && (
              <div className="absolute right-0 top-full mt-1 bg-white rounded-lg shadow-lg border border-gray-200 py-1 min-w-[180px] z-50">
                <button
                  onClick={() => {
                    setShowToolboxDialog(true);
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2 hover:bg-[#FEF3C7] text-left text-[#6B5B4F]"
                >
                  <Package size={16} />
                  <span className="text-sm">도구 상점</span>
                </button>
                <button
                  onClick={() => {
                    handleOpenSettings();
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2 hover:bg-[#FEF3C7] text-left text-[#6B5B4F]"
                >
                  <Settings size={16} />
                  <span className="text-sm">설정</span>
                </button>
                <button
                  onClick={() => {
                    window.electron?.openLogWindow?.();
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2 hover:bg-[#FEF3C7] text-left text-[#6B5B4F]"
                >
                  <ScrollText size={16} />
                  <span className="text-sm">로그 보기</span>
                </button>
                <button
                  onClick={() => {
                    window.electron?.openExternal('http://127.0.0.1:8765/xray/app');
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2 hover:bg-[#FEF3C7] text-left text-[#6B5B4F]"
                >
                  <ScanLine size={16} />
                  <span className="text-sm">System X-Ray</span>
                </button>
                <div className="border-t border-gray-200 my-1" />
                <button
                  onClick={() => {
                    setShowGuideDialog(true);
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2 hover:bg-[#FEF3C7] text-left text-[#6B5B4F]"
                >
                  <HelpCircle size={16} />
                  <span className="text-sm">시작 가이드</span>
                </button>
                <button
                  onClick={() => {
                    setShowUserManualDialog(true);
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2 hover:bg-[#FEF3C7] text-left text-[#6B5B4F]"
                >
                  <BookOpen size={16} />
                  <span className="text-sm">사용자 메뉴얼</span>
                </button>
                <button
                  onClick={() => {
                    alert(`IndieBiz OS\n버전: 1.0.0\n\n개인과 소규모 비즈니스를 위한 AI 운영체제`);
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2 hover:bg-[#FEF3C7] text-left text-[#6B5B4F]"
                >
                  <Info size={16} />
                  <span className="text-sm">버전 정보</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 데스크탑 영역 */}
      <div
        ref={desktopRef}
        className="flex-1 relative overflow-hidden"
        onContextMenu={handleContextMenu}
      >
        {isLoading ? (
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

      {/* 시스템 메모 다이얼로그 */}
      <ProfileDialog
        show={showProfileDialog}
        content={profileContent}
        onContentChange={setProfileContent}
        onSave={handleSaveProfile}
        onClose={() => setShowProfileDialog(false)}
      />

      {/* 설정 다이얼로그 */}
      <SettingsDialog
        show={showSettingsDialog}
        settings={systemAiSettings}
        showApiKey={showApiKey}
        onSettingsChange={setSystemAiSettings}
        onToggleApiKey={() => setShowApiKey(!showApiKey)}
        unconsciousSettings={unconsciousAiSettings}
        showUnconsciousApiKey={showUnconsciousApiKey}
        onUnconsciousSettingsChange={setUnconsciousAiSettings}
        onToggleUnconsciousApiKey={() => setShowUnconsciousApiKey(!showUnconsciousApiKey)}
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

      {/* 연락처 다이얼로그 */}
      <ContactsDialog
        show={showContactsDialog}
        onClose={() => setShowContactsDialog(false)}
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
