/**
 * Electron Preload 스크립트
 * 렌더러 프로세스에서 안전하게 사용할 수 있는 API 노출
 */

const { contextBridge, ipcRenderer } = require('electron');

// 렌더러 프로세스에 노출할 API
contextBridge.exposeInMainWorld('electron', {
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

  // IndieNet 창 열기
  openIndieNetWindow: () =>
    ipcRenderer.invoke('open-indienet-window'),

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
  selectFolder: () => ipcRenderer.invoke('select-folder')
});
