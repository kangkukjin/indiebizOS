/**
 * IndieBiz 타입 정의
 */

// 프로젝트
export interface Project {
  id: string;
  name: string;
  type: 'project' | 'folder';
  path?: string;
  created_at: string;
  icon_position: [number, number];
  parent_folder: string | null;
  last_opened: string | null;
  items?: string[]; // 폴더인 경우
  in_trash?: boolean; // 휴지통 여부
}

// 스위치
export interface Switch {
  id: string;
  name: string;
  type: 'switch';
  icon: string;
  description: string;
  command: string;
  created: string;
  last_run: string | null;
  run_count: number;
  icon_position: [number, number];
  parent_folder: string | null;
  in_trash: boolean;
  config: Record<string, unknown>;
}

// 에이전트
export interface Agent {
  id: string;
  name: string;
  type: 'internal' | 'external';
  email?: string;
  active: boolean;
  ai: {
    provider: 'anthropic' | 'openai' | 'google';
    api_key?: string;
    model: string;
  };
  allowed_tools?: string[];   // deprecated (하위 호환)
  allowed_nodes?: string[];   // Phase 16: IBL 노드 기반
  ibl_only?: boolean;
  channels?: Channel[];
  // 단일 채널 형식 (기존 호환)
  channel?: 'gmail' | 'nostr' | null;
  gmail?: GmailConfig;
  nostr?: NostrConfig;
  // 역할 (개별 프롬프트)
  role?: string;
  // 자동 프롬프트용 역할 설명
  role_description?: string;
}

// Gmail 채널 설정
export interface GmailConfig {
  client_id: string;
  client_secret: string;
  token_file?: string;
}

// Nostr 채널 설정
export interface NostrConfig {
  key_name: string;
  private_key?: string;
  relays: string[];
}

// 채널
export interface Channel {
  type: 'gmail' | 'nostr';
  email?: string;
  client_id?: string;
  client_secret?: string;
  token_file?: string;
  key_name?: string;
  private_key?: string;
  relays?: string[];
}

// 도구 (확장)
export interface ToolInfo {
  name: string;
  description: string;
  uses_ai?: boolean;
  is_base_tool?: boolean;
}

// 메시지
export interface Message {
  id: number;
  from_agent_id: number;
  to_agent_id: number;
  content: string;
  timestamp: string;
  tool_calls?: ToolCall[];
}

// 도구 호출
export interface ToolCall {
  id: string;
  name: string;
  input: Record<string, unknown>;
}

// 도구
export interface Tool {
  name: string;
  description: string;
  uses_ai?: boolean;
  ai_config_key?: string;
  is_base_tool?: boolean;
}

// 통합 이벤트 (캘린더 + 스케줄러)
export interface SchedulerTask {
  id: string;
  title?: string;        // 통합 이벤트 제목
  name?: string;         // 하위 호환 (title과 동일)
  description?: string;
  time?: string;         // HH:MM format
  date?: string;         // YYYY-MM-DD
  type?: string;         // anniversary, birthday, appointment, reminder, schedule, other
  enabled?: boolean;
  action?: string;       // null이면 순수 캘린더, 있으면 실행 가능
  last_run?: string | null;
  repeat?: string;       // none, daily, weekly, monthly, yearly, interval
  weekdays?: number[];   // 0=월 ~ 6=일 (weekly용)
  month?: number;        // 1-12 (yearly용)
  day?: number;          // 1-31 (yearly용)
  interval_hours?: number;  // 시간 간격 (interval용)
  action_params?: Record<string, any>;
  created_at?: string;
}

// 스케줄러 작업 종류
export interface SchedulerAction {
  id: string;
  name: string;
}

// 데스크탑 아이템 (프로젝트, 폴더, 스위치 통합)
export type DesktopItem = Project | Switch;

// 앱 뷰
export type AppView = 'launcher' | 'manager' | 'chat';

// 창 위치 정보
export interface WindowBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

// 열린 폴더 창 정보
export interface OpenFolderInfo {
  folderId: string;
  bounds: WindowBounds;
}

// 드롭된 아이템 정보
export interface ItemDroppedData {
  itemId: string;
  itemType: string;
  sourceFolderId: string;
}

// Electron API
export interface ElectronAPI {
  getApiPort: () => Promise<number>;
  openExternal: (url: string) => Promise<void>;
  getAppInfo: () => Promise<{
    version: string;
    name: string;
    isDev: boolean;
  }>;
  openProjectWindow: (projectId: string, projectName: string) => Promise<void>;
  openFolderWindow: (folderId: string, folderName: string) => Promise<void>;
  openIndieNetWindow: () => Promise<void>;
  openBusinessWindow: () => Promise<void>;
  openMultiChatWindow: (roomId: string, roomName: string) => Promise<void>;
  openPCManagerWindow: (initialPath?: string | null) => Promise<void>;
  openPhotoManagerWindow: (initialPath?: string | null) => Promise<void>;
  openAndroidManagerWindow: (deviceId?: string | null, projectId?: string | null) => Promise<void>;
  openPath: (path: string) => Promise<void>;

  // 런처 새로고침
  refreshLauncher: () => Promise<boolean>;
  onLauncherRefresh: (callback: () => void) => void;
  removeLauncherRefresh: () => void;

  // 창 간 드래그 드롭 API
  dropItemToLauncher: (itemId: string, itemType: string, sourceFolderId: string) => Promise<boolean>;
  dropItemToFolder: (itemId: string, itemType: string, targetFolderId: string, sourceFolderId: string) => Promise<boolean>;
  getOpenFolderWindows: () => Promise<OpenFolderInfo[]>;
  getLauncherBounds: () => Promise<WindowBounds | null>;

  // 이벤트 리스너
  onItemDroppedFromFolder: (callback: (data: ItemDroppedData) => void) => void;
  onItemDroppedIntoFolder: (callback: (data: ItemDroppedData) => void) => void;
  removeItemDroppedFromFolder: () => void;
  removeItemDroppedIntoFolder: () => void;

  platform: string;

  // 폴더 선택 다이얼로그
  selectFolder: () => Promise<string | null>;

  // 이미지 파일 선택 다이얼로그 (다중 선택)
  selectImages: () => Promise<string[] | null>;

  // 로그 뷰어 관련
  openLogWindow?: () => Promise<void>;
  onLogMessage?: (callback: (message: string) => void) => void;
  onLogHistory?: (callback: (logs: string[]) => void) => void;
  onLogCleared?: (callback: () => void) => void;
  removeLogListeners?: () => void;
  clearLogs?: () => Promise<void>;
  copyToClipboard?: (text: string) => void;
}

declare global {
  interface Window {
    electron?: ElectronAPI;
  }
}
