/**
 * FolderView - 폴더 내용을 보여주는 창
 */

import { useEffect, useState, useRef } from 'react';
import { Folder, FolderPlus, Plus } from 'lucide-react';
import { api } from '../lib/api';
import type { Project } from '../types';

// 드롭 타겟 정보
interface DropTarget {
  type: 'launcher' | 'folder';
  folderId?: string;
}

interface FolderViewProps {
  folderId: string;
}

export function FolderView({ folderId }: FolderViewProps) {
  const [folder, setFolder] = useState<Project | null>(null);
  const [items, setItems] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draggedItem, setDraggedItem] = useState<{ id: string; type: 'project' | 'switch' } | null>(null);
  const [isOutsideWindow, setIsOutsideWindow] = useState(false);
  const [dropTarget, setDropTarget] = useState<DropTarget | null>(null);
  const [hoveringFolderId, setHoveringFolderId] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);
  const [showNewProjectDialog, setShowNewProjectDialog] = useState(false);
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newFolderName, setNewFolderName] = useState('');

  const folderRefs = useRef<{ [key: string]: HTMLDivElement | null }>({});

  // 폴더 목록 로드 함수
  const loadFolderItems = async () => {
    try {
      const folderItems = await api.getFolderItems(folderId);
      setItems(folderItems);
    } catch (err) {
      console.error('폴더 아이템 로드 실패:', err);
    }
  };

  // 폴더 정보 로드
  useEffect(() => {
    const loadFolder = async () => {
      try {
        setIsLoading(true);
        const projects = await api.getProjects();
        const folderData = projects.find((p: Project) => p.id === folderId);
        if (folderData) {
          setFolder(folderData);
        }
        const folderItems = await api.getFolderItems(folderId);
        setItems(folderItems);
        setError(null);
      } catch (err) {
        setError('폴더를 불러올 수 없습니다.');
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    };

    loadFolder();
  }, [folderId]);

  // 다른 폴더에서 아이템이 드롭되었을 때 이벤트 수신
  useEffect(() => {
    // 이벤트 핸들러 참조를 저장하여 정확히 같은 함수를 제거할 수 있도록 함
    const handleDropped = (data: { itemId: string; itemType: string; sourceFolderId: string }) => {
      console.log('이 폴더로 아이템 드롭됨:', data);
      // 목록 새로고침 (최신 folderId 사용)
      api.getFolderItems(folderId).then(setItems).catch(console.error);
    };

    if (window.electron?.onItemDroppedIntoFolder) {
      window.electron.onItemDroppedIntoFolder(handleDropped);
    }

    // 클린업: 컴포넌트 언마운트 시 이벤트 리스너 제거
    return () => {
      if (window.electron?.removeItemDroppedIntoFolder) {
        window.electron.removeItemDroppedIntoFolder();
      }
    };
  }, [folderId]);

  const handleOpenItem = async (item: Project) => {
    if (item.type === 'folder') {
      if (window.electron?.openFolderWindow) {
        window.electron.openFolderWindow(item.id, item.name);
      }
    } else {
      if (window.electron?.openProjectWindow) {
        window.electron.openProjectWindow(item.id, item.name);
      }
    }
  };

  const handleMoveToFolder = async (itemId: string, targetFolderId: string) => {
    try {
      await api.moveItem(itemId, targetFolderId);
      const folderItems = await api.getFolderItems(folderId);
      setItems(folderItems);
    } catch (error) {
      console.error('Failed to move item:', error);
    }
  };

  const handleMoveOutOfFolder = async (itemId: string, itemType: 'project' | 'switch') => {
    try {
      // 다른 창에 드롭된 경우
      if (dropTarget) {
        if (dropTarget.type === 'launcher') {
          // 런처로 드롭 - 루트로 이동
          await api.moveItem(itemId, undefined);
          // Electron IPC로 런처에 알림
          if (window.electron?.dropItemToLauncher) {
            await window.electron.dropItemToLauncher(itemId, itemType, folderId);
          }
        } else if (dropTarget.type === 'folder' && dropTarget.folderId) {
          // 다른 폴더로 드롭
          await api.moveItem(itemId, dropTarget.folderId);
          // Electron IPC로 해당 폴더 창에 알림
          if (window.electron?.dropItemToFolder) {
            await window.electron.dropItemToFolder(itemId, itemType, dropTarget.folderId, folderId);
          }
        }
      } else {
        // 단순히 창 밖으로 드래그 - 루트로 이동
        await api.moveItem(itemId, undefined);
      }

      // 현재 폴더 목록 갱신
      const folderItems = await api.getFolderItems(folderId);
      setItems(folderItems);
    } catch (error) {
      console.error('Failed to move item out:', error);
    }
  };

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return;
    try {
      await api.createProject(newProjectName, '기본', folderId);
      setNewProjectName('');
      setShowNewProjectDialog(false);
      const folderItems = await api.getFolderItems(folderId);
      setItems(folderItems);
    } catch (error) {
      console.error('Failed to create project:', error);
    }
  };

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return;
    try {
      await api.createFolder(newFolderName, folderId);
      setNewFolderName('');
      setShowNewFolderDialog(false);
      const folderItems = await api.getFolderItems(folderId);
      setItems(folderItems);
    } catch (error) {
      console.error('Failed to create folder:', error);
    }
  };

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY });
  };

  const closeContextMenu = () => {
    setContextMenu(null);
  };

  useEffect(() => {
    const handleClick = () => closeContextMenu();
    if (contextMenu) {
      document.addEventListener('click', handleClick);
      return () => document.removeEventListener('click', handleClick);
    }
  }, [contextMenu]);

  // 창 밖으로 드래그했는지 체크 및 드롭 타겟 감지
  const checkOutsideWindow = async (screenX: number, screenY: number, clientX: number, clientY: number) => {
    const margin = 10; // 창 가장자리 여유
    const isOutside = clientX < margin || clientY < margin ||
                      clientX > window.innerWidth - margin ||
                      clientY > window.innerHeight - margin;
    setIsOutsideWindow(isOutside);

    if (isOutside && window.electron) {
      // 스크린 좌표로 드롭 타겟 감지
      try {
        // 런처 창 위치 확인
        const launcherBounds = await window.electron.getLauncherBounds();
        if (launcherBounds &&
            screenX >= launcherBounds.x &&
            screenX <= launcherBounds.x + launcherBounds.width &&
            screenY >= launcherBounds.y &&
            screenY <= launcherBounds.y + launcherBounds.height) {
          setDropTarget({ type: 'launcher' });
          return true;
        }

        // 다른 폴더 창 위치 확인
        const openFolders = await window.electron.getOpenFolderWindows();
        for (const folderInfo of openFolders) {
          // 현재 폴더는 제외
          if (folderInfo.folderId === folderId) continue;

          const bounds = folderInfo.bounds;
          if (screenX >= bounds.x &&
              screenX <= bounds.x + bounds.width &&
              screenY >= bounds.y &&
              screenY <= bounds.y + bounds.height) {
            setDropTarget({ type: 'folder', folderId: folderInfo.folderId });
            return true;
          }
        }

        // 아무 창에도 해당하지 않으면 런처로 간주 (배경 드롭)
        setDropTarget({ type: 'launcher' });
      } catch (e) {
        console.error('Failed to check drop target:', e);
        setDropTarget({ type: 'launcher' });
      }
    } else {
      setDropTarget(null);
    }

    return isOutside;
  };

  const checkFolderHover = (x: number, y: number, draggedItemId: string): string | null => {
    const folderTargets = items.filter(item => item.type === 'folder' && item.id !== draggedItemId);
    for (const folderItem of folderTargets) {
      const ref = folderRefs.current[folderItem.id];
      if (ref) {
        const rect = ref.getBoundingClientRect();
        if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) {
          setHoveringFolderId(folderItem.id);
          return folderItem.id;
        }
      }
    }
    setHoveringFolderId(null);
    return null;
  };

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-[#F5F1EB]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#D97706]" />
      </div>
    );
  }

  if (error || !folder) {
    return (
      <div className="h-full flex items-center justify-center bg-[#F5F1EB] text-[#B45309]">
        <p>{error || '폴더를 찾을 수 없습니다.'}</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-[#F5F1EB]">
      {/* 상단 툴바 */}
      <div className="h-10 flex items-center justify-between px-4 drag bg-[#F5F1EB] border-b border-[#E5DFD5]">
        <div className="flex items-center gap-2 no-drag text-[#6B5B4F]">
          <Folder size={18} className="text-[#F59E0B]" />
          <span className="font-medium">{folder.name}</span>
          <span className="text-sm text-[#A09080]">({items.length}개 항목)</span>
        </div>
      </div>

      {/* 콘텐츠 영역 */}
      <div
        className="flex-1 relative p-4"
        style={{ overflow: draggedItem ? 'visible' : 'hidden' }}
        onContextMenu={handleContextMenu}
      >
        {items.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-[#A09080]">
            <Folder size={48} className="mb-4" />
            <p>폴더가 비어있습니다</p>
            <p className="text-sm mt-2">우클릭하여 새 항목을 만들 수 있습니다</p>
          </div>
        ) : (
          <>
            {items.map((item) => (
              <DraggableItem
                key={item.id}
                item={item}
                onDoubleClick={() => handleOpenItem(item)}
                onDragStart={() => setDraggedItem({ id: item.id, type: 'project' })}
                onDragEnd={() => {
                  setDraggedItem(null);
                  setHoveringFolderId(null);
                  setIsOutsideWindow(false);
                  setDropTarget(null);
                }}
                onDragMove={(screenX, screenY, clientX, clientY) => {
                  checkOutsideWindow(screenX, screenY, clientX, clientY);
                  checkFolderHover(clientX, clientY, item.id);
                }}
                onDropOutside={() => handleMoveOutOfFolder(item.id, 'project')}
                onDropOnFolder={(targetFolderId) => handleMoveToFolder(item.id, targetFolderId)}
                isOutsideWindow={isOutsideWindow && draggedItem?.id === item.id}
                isFolderHovered={hoveringFolderId === item.id}
                hoveringFolderId={hoveringFolderId}
                dropTarget={dropTarget}
                folderRef={(el) => {
                  if (item.type === 'folder') {
                    folderRefs.current[item.id] = el;
                  }
                }}
              />
            ))}
          </>
        )}

        {/* 창 밖으로 드래그 시 힌트 표시 */}
        {draggedItem && isOutsideWindow && (
          <div className="fixed inset-0 pointer-events-none z-40">
            <div className={`absolute inset-0 border-4 border-dashed ${
              dropTarget?.type === 'folder' ? 'border-blue-400 bg-blue-100/20' : 'border-green-400 bg-green-100/20'
            } animate-pulse`} />
            <div className={`absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 ${
              dropTarget?.type === 'folder' ? 'bg-blue-500' : 'bg-green-500'
            } text-white px-4 py-2 rounded-lg shadow-lg`}>
              {dropTarget?.type === 'folder'
                ? '다른 폴더로 이동'
                : '런처로 이동'}
            </div>
          </div>
        )}
      </div>

      {/* 컨텍스트 메뉴 */}
      {contextMenu && (
        <div
          className="fixed bg-white rounded-lg shadow-xl border border-gray-200 py-1 z-50 min-w-[180px]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => {
              setShowNewProjectDialog(true);
              closeContextMenu();
            }}
            className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-3"
          >
            <Plus size={16} className="text-green-600" />
            새 프로젝트
          </button>
          <button
            onClick={() => {
              setShowNewFolderDialog(true);
              closeContextMenu();
            }}
            className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-3"
          >
            <FolderPlus size={16} className="text-blue-600" />
            새 폴더
          </button>
        </div>
      )}

      {/* 새 프로젝트 다이얼로그 */}
      {showNewProjectDialog && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-96 shadow-2xl">
            <h2 className="text-xl font-bold mb-4 text-gray-800">새 프로젝트</h2>
            <input
              type="text"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              placeholder="프로젝트 이름"
              className="w-full px-4 py-2 bg-gray-50 rounded-lg border border-gray-300 focus:border-green-500 focus:outline-none text-gray-800"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreateProject();
                if (e.key === 'Escape') setShowNewProjectDialog(false);
              }}
            />
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => setShowNewProjectDialog(false)}
                className="px-4 py-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-600"
              >
                취소
              </button>
              <button
                onClick={handleCreateProject}
                className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors"
              >
                생성
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 새 폴더 다이얼로그 */}
      {showNewFolderDialog && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-96 shadow-2xl">
            <h2 className="text-xl font-bold mb-4 text-gray-800">새 폴더</h2>
            <input
              type="text"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="폴더 이름"
              className="w-full px-4 py-2 bg-gray-50 rounded-lg border border-gray-300 focus:border-blue-500 focus:outline-none text-gray-800"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreateFolder();
                if (e.key === 'Escape') setShowNewFolderDialog(false);
              }}
            />
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => setShowNewFolderDialog(false)}
                className="px-4 py-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-600"
              >
                취소
              </button>
              <button
                onClick={handleCreateFolder}
                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
              >
                생성
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// 드래그 가능한 아이템 컴포넌트
function DraggableItem({
  item,
  onDoubleClick,
  onDragStart,
  onDragEnd,
  onDragMove,
  onDropOutside,
  onDropOnFolder,
  isOutsideWindow,
  isFolderHovered,
  hoveringFolderId,
  dropTarget: _dropTarget,
  folderRef,
}: {
  item: Project;
  onDoubleClick: () => void;
  onDragStart: () => void;
  onDragEnd: () => void;
  onDragMove: (screenX: number, screenY: number, clientX: number, clientY: number) => void;
  onDropOutside: () => void;
  onDropOnFolder: (folderId: string) => void;
  isOutsideWindow: boolean;
  isFolderHovered: boolean;
  hoveringFolderId: string | null;
  dropTarget: DropTarget | null;
  folderRef?: (el: HTMLDivElement | null) => void;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const [pos, setPos] = useState({ x: item.icon_position[0], y: item.icon_position[1] });
  const [isSelected, setIsSelected] = useState(false);
  const [isNearEdge, setIsNearEdge] = useState(false);
  const dragOffset = useRef({ x: 0, y: 0 });
  const itemRef = useRef<HTMLDivElement>(null);
  const originalPos = useRef({ x: item.icon_position[0], y: item.icon_position[1] });

  const handlePointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    setIsDragging(true);
    setIsSelected(true);
    onDragStart();

    // 포인터 캡처 - 창 밖에서도 마우스 이벤트를 받을 수 있게 함
    if (itemRef.current) {
      itemRef.current.setPointerCapture(e.pointerId);
    }

    const rect = itemRef.current?.getBoundingClientRect();
    if (rect) {
      dragOffset.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }
    originalPos.current = { x: pos.x, y: pos.y };
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging) return;

    const parent = itemRef.current?.parentElement;
    if (!parent) return;

    const parentRect = parent.getBoundingClientRect();
    const newX = e.clientX - parentRect.left - dragOffset.current.x;
    const newY = e.clientY - parentRect.top - dragOffset.current.y;

    // 창 가장자리 감지
    const margin = 30;
    const nearEdge = e.clientX < margin || e.clientY < margin ||
                     e.clientX > window.innerWidth - margin ||
                     e.clientY > window.innerHeight - margin;
    setIsNearEdge(nearEdge);

    if (nearEdge) {
      // 창 가장자리 근처면 위치 제한 없이 자유롭게 이동 (시각적으로 창 밖으로 나가는 것처럼)
      setPos({ x: newX, y: newY });
    } else {
      // 창 안쪽이면 부모 컨테이너 내부로 제한
      setPos({
        x: Math.max(0, Math.min(newX, parentRect.width - 100)),
        y: Math.max(0, Math.min(newY, parentRect.height - 100)),
      });
    }

    onDragMove(e.screenX, e.screenY, e.clientX, e.clientY);
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (!isDragging) return;

    // 포인터 캡처 해제
    if (itemRef.current) {
      itemRef.current.releasePointerCapture(e.pointerId);
    }

    setIsDragging(false);
    setIsNearEdge(false);

    if (isOutsideWindow) {
      // 창 밖으로 드롭 - 원래 위치로 복원 (아이템은 이동됨)
      setPos(originalPos.current);
      onDropOutside();
    } else if (hoveringFolderId) {
      // 폴더 위에 드롭 - 원래 위치로 복원 (아이템은 이동됨)
      setPos(originalPos.current);
      onDropOnFolder(hoveringFolderId);
    }
    // 창 안쪽에 드롭하면 현재 위치 유지

    onDragEnd();
  };

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (itemRef.current && !itemRef.current.contains(e.target as Node)) {
        setIsSelected(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const setRef = (el: HTMLDivElement | null) => {
    (itemRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
    if (folderRef) folderRef(el);
  };

  const isFolder = item.type === 'folder';

  return (
    <div
      ref={setRef}
      className={`absolute flex flex-col items-center gap-1 p-2 rounded-xl cursor-pointer no-select ${
        isSelected ? 'bg-[#E5DFD5]' : 'hover:bg-[#EAE4DA]'
      } ${isDragging ? 'z-[9999]' : ''} ${
        isDragging && isNearEdge ? 'opacity-70 scale-95 shadow-2xl' : ''
      } ${isDragging && isOutsideWindow ? 'opacity-50 scale-90' : ''} ${
        isFolderHovered ? 'bg-[#BBF7D0] scale-110' : ''
      }`}
      style={{
        left: pos.x,
        top: pos.y,
        cursor: isDragging ? 'grabbing' : 'grab',
        // 드래그 중에는 transition 제거 (부드러운 움직임)
        transition: isDragging ? 'none' : 'all 0.15s ease',
        // 드래그 중 창 밖으로 나갈 때 포인터 이벤트 유지
        touchAction: 'none',
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onDoubleClick={onDoubleClick}
    >
      <div
        className={`w-14 h-14 rounded-xl flex items-center justify-center text-2xl shadow-sm transition-all ${
          isFolder ? 'bg-[#F59E0B] text-white' : 'bg-[#3B82F6] text-white'
        } ${isSelected ? 'ring-2 ring-[#D97706] ring-offset-2 ring-offset-[#F5F1EB]' : ''} ${
          isFolderHovered ? 'ring-4 ring-[#22C55E] ring-offset-2 ring-offset-[#F5F1EB]' : ''
        }`}
      >
        {isFolder ? <Folder size={32} /> : '📁'}
      </div>
      <span className="text-xs text-center max-w-16 truncate text-[#4A4035] font-medium">
        {item.name}
      </span>
    </div>
  );
}
