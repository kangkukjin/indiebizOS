/**
 * Launcher 관련 타입 정의
 */

import type { Project, Switch, SchedulerTask, SchedulerAction } from '../../types';

// 컨텍스트 메뉴 타입
export interface ContextMenuState {
  x: number;
  y: number;
  itemId?: string;
  itemType?: 'project' | 'switch';
}

// 클립보드 타입
export interface ClipboardItem {
  id: string;
  type: 'project' | 'switch';
}

// 드래그 아이템 타입
export interface DraggedItem {
  id: string;
  type: 'project' | 'switch';
}

// 선택된 아이템 타입
export interface SelectedItem {
  id: string;
  type: 'project' | 'switch';
}

// 이름 변경 아이템 타입
export interface RenamingItem {
  id: string;
  type: 'project' | 'switch';
  name: string;
}

// 휴지통 아이템 타입
export interface TrashItems {
  projects: Project[];
  switches: Switch[];
}

// 스케줄러 태스크 폼 타입
export interface TaskForm {
  name: string;
  description: string;
  time: string;
  action: string;
  enabled: boolean;
}

// 시스템 AI 설정 타입
export interface SystemAISettings {
  enabled: boolean;
  provider: string;
  model: string;
  apiKey: string;
}

// DraggableIcon props 타입
export interface DraggableIconProps {
  icon: React.ReactNode;
  label: string;
  position: [number, number];
  onDoubleClick: () => void;
  onPositionChange: (x: number, y: number) => void;
  onDragStart: () => void;
  onDragEnd: () => void;
  onDragMove: (x: number, y: number) => boolean;
  onDropOnTrash: () => void;
  onDropOnFolder?: (folderId: string) => void;
  trashHover: boolean;
  isSwitch?: boolean;
  isFolder?: boolean;
  isFolderHovered?: boolean;
  folderRef?: (el: HTMLDivElement | null) => void;
  hoveringFolderId?: string | null;
  onContextMenu?: (e: React.MouseEvent) => void;
  onSelect?: () => void;
  isSelected?: boolean;
  isRenaming?: boolean;
  onFinishRename?: (newName: string) => void;
  onCancelRename?: () => void;
}

// DraggableTrash props 타입
export interface DraggableTrashProps {
  trashRef: React.RefObject<HTMLDivElement | null>;
  trashHover: boolean;
  position: { x: number; y: number };
  onPositionChange: (x: number, y: number) => void;
  onDoubleClick: () => void;
  onContextMenu: (e: React.MouseEvent) => void;
  trashCount: number;
}

// 재내보내기
export type { Project, Switch, SchedulerTask, SchedulerAction };
