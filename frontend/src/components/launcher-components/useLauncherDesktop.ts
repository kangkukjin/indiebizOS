/**
 * 자율주행 데스크탑 상호작용 훅 (2026-07-18 모듈화 — 1500줄 규칙)
 *
 * Launcher.tsx 에서 verbatim 이동: 데스크탑 아이콘(프로젝트/스위치/다중채팅방)
 * 열기·드래그·폴더드롭·휴지통·복사/붙여넣기·이름변경·컨텍스트 메뉴·키보드 단축키의
 * 상태+핸들러+이펙트. Launcher 가 반환값을 구조분해해 JSX 식별자는 전부 무변경.
 * (GenericInstrument 분할의 프론트 선례 — 상태 묶음 이동은 커스텀 훅이 믹스인 대응물)
 */
import { useEffect, useState, useRef } from 'react';
import type * as React from 'react';
import { useAppStore } from '../../stores/appStore';
import { api } from '../../lib/api';
import type { Project, Switch } from '../../types';
import type {
  ContextMenuState,
  ClipboardItem,
  SelectedItem,
  RenamingItem,
  TrashItems,
} from './types';

// 다중채팅방 목록
export interface MultiChatRoom {
  id: string;
  name: string;
  description: string;
  participant_count: number;
  icon_position?: [number, number];
}

export function useLauncherDesktop(opts: {
  launcherTab: string;
  showNewProjectDialog: boolean;
  showNewFolderDialog: boolean;
  showSchedulerDialog: boolean;
}) {
  const { launcherTab, showNewProjectDialog, showNewFolderDialog, showSchedulerDialog } = opts;
  const {
    projects,
    switches,
    loadProjects,
    loadSwitches,
    setCurrentProject,
    setCurrentView,
  } = useAppStore();

  const [multiChatRooms, setMultiChatRooms] = useState<MultiChatRoom[]>([]);
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

  const trashRef = useRef<HTMLDivElement>(null);

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

  // 수동/앱 모드 표면이 IBL 컨텍스트로 쓰는 시스템 프로젝트 — 데스크탑에선 숨긴다.
  // (프로젝트 자체는 존재해 경로 해소는 계속 동작. 토글과 이름이 겹쳐 혼동·삭제 위험 방지)
  const SYSTEM_PROJECT_IDS = new Set(['수동모드', '앱모드']);

  // 루트 레벨 아이템만 표시 (휴지통 + 시스템 프로젝트 제외)
  const displayProjects = projects.filter(
    (p) => !p.parent_folder && !p.in_trash && !SYSTEM_PROJECT_IDS.has(p.id)
  );
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

  const handleOpenMultiChatRoom = (room: MultiChatRoom) => {
    if (window.electron?.openMultiChatWindow) {
      window.electron.openMultiChatWindow(room.id, room.name);
    } else {
      window.location.hash = `/multichat/${room.id}`;
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
    // 프로젝트 데스크탑(자율주행)에서만 런처 메뉴(새 프로젝트/붙여넣기 등)를 띄운다.
    // 수동·앱 모드에서는 막지 않고 그대로 둬서 네이티브 복사 메뉴만 뜨게 한다.
    if (launcherTab !== 'autopilot') return;
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

      if (showNewProjectDialog || showNewFolderDialog || showSchedulerDialog) {
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
  }, [selectedItem, clipboard, renamingItem, projects, switches, showNewProjectDialog, showNewFolderDialog, showSchedulerDialog]);

  return {
    // 상태 + setter (JSX 가 직접 쓰는 것들)
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
    // 파생 목록
    displayProjects,
    displaySwitches,
    // 로더
    loadMultiChatRooms,
    loadTrashItems,
    // 핸들러
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
  };
}
