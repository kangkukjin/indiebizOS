/**
 * Electron Preload 스크립트
 * 렌더러 프로세스에서 안전하게 사용할 수 있는 API 노출
 */

const { contextBridge, ipcRenderer, clipboard } = require('electron');

// 렌더러 프로세스에 노출할 API
contextBridge.exposeInMainWorld('electron', {
  // 클립보드 기능
  copyToClipboard: (text) => clipboard.writeText(text),
  readFromClipboard: () => clipboard.readText(),

  // API 포트 가져오기
  getApiPort: () => ipcRenderer.invoke('get-api-port'),

  // 외부 URL 열기
  openExternal: (url) => ipcRenderer.invoke('open-external', url),

  // 앱 정보
  getAppInfo: () => ipcRenderer.invoke('get-app-info'),

  // 프로젝트 창 열기
  openProjectWindow: (projectId, projectName) =>
    ipcRenderer.invoke('open-project-window', projectId, projectName),

  // 폴더 창 열기
  openFolderWindow: (folderId, folderName) =>
    ipcRenderer.invoke('open-folder-window', folderId, folderName),

  // 커뮤니티 창 열기 (옛 IndieNet — IBL 커뮤니티 계기를 전용 창으로)
  openCommunityWindow: () =>
    ipcRenderer.invoke('open-community-window'),

  // 메신저 창 열기 (옛 이웃관리·빠른 연락처 — IBL 메신저 계기를 전용 창으로)
  openMessengerWindow: () =>
    ipcRenderer.invoke('open-messenger-window'),

  // 시스템 AI 창 열기
  openSystemAIWindow: () =>
    ipcRenderer.invoke('open-system-ai-window'),

  // 다중채팅방 창 열기
  openMultiChatWindow: (roomId, roomName) =>
    ipcRenderer.invoke('open-multichat-window', roomId, roomName),

  // PC Manager 창 열기
  openPCManagerWindow: (initialPath) =>
    ipcRenderer.invoke('open-pcmanager-window', initialPath),

  // Photo Manager 창 열기
  openPhotoManagerWindow: (initialPath) =>
    ipcRenderer.invoke('open-photo-manager-window', initialPath),

  // Android Manager 창 열기
  openAndroidManagerWindow: (deviceId, projectId) =>
    ipcRenderer.invoke('open-android-manager-window', deviceId, projectId),

  // 강의 만들기 워크스페이스 창 열기
  openLectureWorkspaceWindow: (lectureId) =>
    ipcRenderer.invoke('open-lecture-workspace-window', lectureId),

  // 강의 워크스페이스: 다른 강의 선택 신호 수신
  onLectureWorkspaceSelect: (callback) => {
    ipcRenderer.on('lecture-workspace-select', (_, lectureId) => callback(lectureId));
  },
  removeLectureWorkspaceSelectListener: () => {
    ipcRenderer.removeAllListeners('lecture-workspace-select');
  },

  // 런처 새로고침 요청
  refreshLauncher: () => ipcRenderer.invoke('refresh-launcher'),
  onLauncherRefresh: (callback) => {
    ipcRenderer.on('refresh-launcher', () => callback());
  },
  removeLauncherRefresh: () => {
    ipcRenderer.removeAllListeners('refresh-launcher');
  },

  // 폴더에서 아이템을 런처로 드롭
  dropItemToLauncher: (itemId, itemType, sourceFolderId) =>
    ipcRenderer.invoke('drop-item-to-launcher', itemId, itemType, sourceFolderId),

  // 폴더에서 다른 폴더로 아이템 드롭
  dropItemToFolder: (itemId, itemType, targetFolderId, sourceFolderId) =>
    ipcRenderer.invoke('drop-item-to-folder', itemId, itemType, targetFolderId, sourceFolderId),

  // 열려있는 폴더 창 목록
  getOpenFolderWindows: () =>
    ipcRenderer.invoke('get-open-folder-windows'),

  // 런처 창 위치 정보
  getLauncherBounds: () =>
    ipcRenderer.invoke('get-launcher-bounds'),

  // 폴더에서 아이템 드롭 이벤트 수신 (런처용)
  onItemDroppedFromFolder: (callback) => {
    ipcRenderer.on('item-dropped-from-folder', (_, data) => callback(data));
  },

  // 아이템이 이 폴더로 드롭됨 이벤트 수신 (폴더용)
  onItemDroppedIntoFolder: (callback) => {
    ipcRenderer.on('item-dropped-into-folder', (_, data) => callback(data));
  },

  // 이벤트 리스너 제거
  removeItemDroppedFromFolder: () => {
    ipcRenderer.removeAllListeners('item-dropped-from-folder');
  },
  removeItemDroppedIntoFolder: () => {
    ipcRenderer.removeAllListeners('item-dropped-into-folder');
  },

  // 플랫폼 정보
  platform: process.platform,

  // 폴더 선택 다이얼로그
  selectFolder: () => ipcRenderer.invoke('select-folder'),

  // 이미지 파일 선택 다이얼로그 (다중 선택)
  selectImages: () => ipcRenderer.invoke('select-images'),

  // === 포식 브라우저 비밀번호 금고 (크롬 비번 채우기) ===
  foragePwListHost: (url) => ipcRenderer.invoke('forage-pw-list-host', url),
  foragePwGet: (url, username) => ipcRenderer.invoke('forage-pw-get', url, username),
  foragePwSave: (origin, username, password) =>
    ipcRenderer.invoke('forage-pw-save', origin, username, password),
  foragePwRemove: (origin, username) =>
    ipcRenderer.invoke('forage-pw-remove', origin, username),
  foragePwListAll: () => ipcRenderer.invoke('forage-pw-list-all'),
  foragePwImportChrome: () => ipcRenderer.invoke('forage-pw-import-chrome'),

  // === 에이전트 선택 IPC (스케줄 결과 전달용) ===
  onSelectAgent: (callback) => {
    ipcRenderer.on('select-agent', (_, agentName) => callback(agentName));
  },
  removeSelectAgentListener: () => {
    ipcRenderer.removeAllListeners('select-agent');
  }
});
