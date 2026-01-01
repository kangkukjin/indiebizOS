/**
 * 런처 - 데스크탑 스타일 프로젝트/폴더/스위치 관리
 */

import { useEffect, useState, useRef } from 'react';
import { Zap, Settings, RefreshCw, User, Clock, Folder, Globe, Bot, Package } from 'lucide-react';
import { useAppStore } from '../stores/appStore';
import { api } from '../lib/api';
import type { Project, Switch, SchedulerTask, SchedulerAction } from '../types';
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
  TaskEditDialog,
  SystemAIChatDialog,
  ToolboxDialog,
} from './launcher-components';
import type {
  ContextMenuState,
  ClipboardItem,
  SelectedItem,
  RenamingItem,
  TrashItems,
  TaskForm,
  SystemAISettings,
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
  const [showProfileDialog, setShowProfileDialog] = useState(false);
  const [showSchedulerDialog, setShowSchedulerDialog] = useState(false);
  const [showTaskEditDialog, setShowTaskEditDialog] = useState(false);
  const [showSystemAIChatDialog, setShowSystemAIChatDialog] = useState(false);
  const [showToolboxDialog, setShowToolboxDialog] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newFolderName, setNewFolderName] = useState('');
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
  const [trashItems, setTrashItems] = useState<TrashItems>({ projects: [], switches: [] });
  const [trashPosition, setTrashPosition] = useState({ x: -1, y: -1 }); // -1은 우하단 기본 위치

  // 폴더 드래그 앤 드롭 관련 상태
  const [hoveringFolderId, setHoveringFolderId] = useState<string | null>(null);
  const folderRefs = useRef<{ [key: string]: HTMLDivElement | null }>({});

  // 스케줄러 관련 상태
  const [schedulerTasks, setSchedulerTasks] = useState<SchedulerTask[]>([]);
  const [schedulerActions, setSchedulerActions] = useState<SchedulerAction[]>([]);
  const [editingTask, setEditingTask] = useState<SchedulerTask | null>(null);
  const [taskForm, setTaskForm] = useState<TaskForm>({
    name: '',
    description: '',
    time: '06:00',
    action: 'blog_sync',
    enabled: true,
  });

  // 설정 다이얼로그 상태
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [systemAiSettings, setSystemAiSettings] = useState<SystemAISettings>({
    enabled: true,
    provider: 'google',
    model: 'gemini-2.0-flash-exp',
    apiKey: '',
  });

  const trashRef = useRef<HTMLDivElement>(null);
  const desktopRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadProjects();
    loadSwitches();
  }, [loadProjects, loadSwitches]);

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

  const handleRefresh = () => {
    loadProjects();
    loadSwitches();
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
      setShowSettingsDialog(true);
    } catch (error) {
      console.error('Failed to load system AI settings:', error);
      setShowSettingsDialog(true);
    }
  };

  const handleSaveSystemAi = async () => {
    try {
      await api.updateSystemAI(systemAiSettings);
      setShowSettingsDialog(false);
    } catch (error) {
      console.error('Failed to save system AI settings:', error);
    }
  };

  const handleOpenScheduler = async () => {
    try {
      const [tasks, actions] = await Promise.all([
        api.getSchedulerTasks(),
        api.getSchedulerActions(),
      ]);
      setSchedulerTasks(tasks);
      setSchedulerActions(actions);
      setShowSchedulerDialog(true);
    } catch (error) {
      console.error('Failed to load scheduler:', error);
      setSchedulerTasks([]);
      setSchedulerActions([]);
      setShowSchedulerDialog(true);
    }
  };

  const handleAddTask = () => {
    setEditingTask(null);
    setTaskForm({
      name: '',
      description: '',
      time: '06:00',
      action: schedulerActions[0]?.id || 'blog_sync',
      enabled: true,
    });
    setShowTaskEditDialog(true);
  };

  const handleEditTask = (task: SchedulerTask) => {
    setEditingTask(task);
    setTaskForm({
      name: task.name,
      description: task.description,
      time: task.time,
      action: task.action,
      enabled: task.enabled,
    });
    setShowTaskEditDialog(true);
  };

  const handleSaveTask = async () => {
    try {
      if (editingTask) {
        await api.updateSchedulerTask(editingTask.id, taskForm);
      } else {
        await api.createSchedulerTask(taskForm);
      }
      const tasks = await api.getSchedulerTasks();
      setSchedulerTasks(tasks);
      setShowTaskEditDialog(false);
    } catch (error) {
      console.error('Failed to save task:', error);
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    if (!confirm('이 작업을 삭제하시겠습니까?')) return;
    try {
      await api.deleteSchedulerTask(taskId);
      setSchedulerTasks(schedulerTasks.filter(t => t.id !== taskId));
    } catch (error) {
      console.error('Failed to delete task:', error);
    }
  };

  const handleToggleTask = async (taskId: string) => {
    try {
      const result = await api.toggleSchedulerTask(taskId);
      setSchedulerTasks(schedulerTasks.map(t =>
        t.id === taskId ? { ...t, enabled: result.enabled } : t
      ));
    } catch (error) {
      console.error('Failed to toggle task:', error);
    }
  };

  const handleRunTask = async (taskId: string) => {
    try {
      await api.runSchedulerTask(taskId);
      console.log('Task started:', taskId);
    } catch (error) {
      console.error('Failed to run task:', error);
    }
  };

  const formatLastRun = (lastRun: string | null): string => {
    if (!lastRun) return '-';
    try {
      const date = new Date(lastRun);
      return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
    } catch {
      return '-';
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

  // 휴지통 열기
  const handleOpenTrash = async () => {
    try {
      const data = await api.getTrash();
      setTrashItems({ projects: data.projects, switches: data.switches });
      setShowTrashDialog(true);
    } catch (error) {
      console.error('휴지통 로드 실패:', error);
    }
  };

  // 휴지통에서 복원
  const handleRestoreFromTrash = async (itemId: string, itemType: 'project' | 'switch') => {
    try {
      await api.restoreFromTrash(itemId, itemType);
      const data = await api.getTrash();
      setTrashItems({ projects: data.projects, switches: data.switches });
      loadProjects();
      loadSwitches();
    } catch (error) {
      console.error('복원 실패:', error);
    }
  };

  // 휴지통 비우기
  const handleEmptyTrash = async () => {
    if (!confirm('휴지통을 비우시겠습니까? 모든 항목이 영구 삭제됩니다.')) return;

    try {
      await api.emptyTrash();
      setTrashItems({ projects: [], switches: [] });
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

      if (showNewProjectDialog || showNewFolderDialog || showProfileDialog || showSchedulerDialog || showTaskEditDialog) {
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
  }, [selectedItem, clipboard, renamingItem, projects, switches, showNewProjectDialog, showNewFolderDialog, showProfileDialog, showSchedulerDialog, showTaskEditDialog]);

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
            onClick={() => setShowSystemAIChatDialog(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-[#EAE4DA] transition-colors text-[#6B5B4F] bg-gradient-to-r from-amber-50 to-orange-50"
            title="시스템 AI와 대화"
          >
            <Bot size={16} className="text-amber-600" />
            <span className="text-sm font-medium text-amber-700">시스템 AI</span>
          </button>
          <button
            onClick={() => setShowToolboxDialog(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-[#EAE4DA] transition-colors text-[#6B5B4F]"
            title="설치/제거 - 패키지 관리"
          >
            <Package size={16} />
            <span className="text-sm">설치/제거</span>
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
            title="나의 정보"
          >
            <User size={16} />
            <span className="text-sm">나의 정보</span>
          </button>
          <button
            onClick={handleRefresh}
            className="p-2 rounded-lg hover:bg-[#EAE4DA] transition-colors text-[#6B5B4F]"
            title="새로고침"
          >
            <RefreshCw size={16} />
          </button>
          <button
            onClick={handleOpenSettings}
            className="p-2 rounded-lg hover:bg-[#EAE4DA] transition-colors text-[#6B5B4F]"
            title="설정"
          >
            <Settings size={16} />
          </button>
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
              trashCount={trashItems.projects.length + trashItems.switches.length}
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
        onOpenTrash={handleOpenTrash}
        onEmptyTrash={handleEmptyTrash}
        getItemName={getItemName}
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

      {/* 나의 정보 다이얼로그 */}
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

      {/* 예약작업 다이얼로그 */}
      <SchedulerDialog
        show={showSchedulerDialog}
        tasks={schedulerTasks}
        onAddTask={handleAddTask}
        onEditTask={handleEditTask}
        onDeleteTask={handleDeleteTask}
        onToggleTask={handleToggleTask}
        onRunTask={handleRunTask}
        formatLastRun={formatLastRun}
        onClose={() => setShowSchedulerDialog(false)}
      />

      {/* 작업 편집 다이얼로그 */}
      <TaskEditDialog
        show={showTaskEditDialog}
        isEditing={!!editingTask}
        form={taskForm}
        actions={schedulerActions}
        onFormChange={setTaskForm}
        onSave={handleSaveTask}
        onClose={() => setShowTaskEditDialog(false)}
      />

      {/* 시스템 AI 대화 다이얼로그 */}
      <SystemAIChatDialog
        show={showSystemAIChatDialog}
        onClose={() => setShowSystemAIChatDialog(false)}
      />

      {/* 도구함 다이얼로그 */}
      <ToolboxDialog
        show={showToolboxDialog}
        onClose={() => setShowToolboxDialog(false)}
      />
    </div>
  );
}
