/**
 * windows.js — 보조 창 생성기 (main.js 에서 분리, 2026-08-06 1500줄 규칙)
 *
 * 프로젝트·폴더·시스템AI·비즈니스·커뮤니티·메신저·PC·사진·안드로이드·강의·다중채팅 창.
 * 각 창의 참조(Map·싱글턴 변수)가 곧 상태라 생성기와 같은 모듈에 산다.
 * 메인 창(createWindow)은 main.js 잔류 — 앱 생명주기·트레이·런처 WS 가 직접 다룬다.
 */
import { app, BrowserWindow, shell } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';

import { setupContextMenu } from './bootstrap.js';
import { clearBadge } from './badge.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
const API_PORT = 8765;

let projectWindows = new Map(); // 프로젝트 창 관리
let folderWindows = new Map(); // 폴더 창 관리
let multiChatWindows = new Map(); // 다중채팅방 창 관리
let businessWindow = null; // 비즈니스 관리 창
let communityWindow = null; // 커뮤니티 창 (옛 IndieNet — IBL 커뮤니티 계기)
let messengerWindow = null; // 메신저 창 (옛 이웃관리·빠른 연락처 — IBL 메신저 계기)
let pcManagerWindow = null; // PC Manager 창
let photoManagerWindow = null; // Photo Manager 창
let androidManagerWindow = null; // Android Manager 창
let systemAIWindow = null; // 시스템 AI 창
let lectureWorkspaceWindow = null; // 강의 만들기 워크스페이스 창

/**
 * 이미 열린 창을 화면 맨앞으로 — focus()만으론 macOS에서 뒤에 깔린/최소화된 창이
 * 안 올라온다. 복원→show(앞으로 가져오며 포커스)→focus 순으로 확실히 끌어올린다.
 * (조종실 '액티브 프로젝트' 칩 클릭 등에서 사용)
 */
function raiseWindow(win) {
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

/**
 * 프로젝트 창 생성
 */
function createProjectWindow(projectId, projectName, agentName) {
  // 이미 열려있으면 맨앞으로
  if (projectWindows.has(projectId)) {
    const existingWindow = projectWindows.get(projectId);
    if (!existingWindow.isDestroyed()) {
      raiseWindow(existingWindow);
      // 이미 열린 창에 에이전트 선택 명령 전달 (스케줄 결과 등)
      if (agentName) {
        existingWindow.webContents.send('select-agent', agentName);
      }
      return;
    }
  }

  const projectWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: projectName || 'IndieBiz Project',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 15 },
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  // URL에 프로젝트 ID 전달 (한글 등 특수문자 인코딩)
  // agentName이 있으면 쿼리 파라미터로 전달 → 해당 에이전트 자동 선택
  const encodedProjectId = encodeURIComponent(projectId);
  const agentQuery = agentName ? `?agent=${encodeURIComponent(agentName)}` : '';
  if (isDev) {
    projectWindow.loadURL(`http://localhost:5173/#/project/${encodedProjectId}${agentQuery}`);
  } else {
    projectWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: `/project/${encodedProjectId}${agentQuery}`
    });
  }

  // 외부 링크는 기본 브라우저에서 열기
  projectWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // 페이지 내 링크 클릭도 처리
  projectWindow.webContents.on('will-navigate', (event, url) => {
    // 내부 URL이 아니면 외부 브라우저에서 열기
    if (!url.startsWith('http://localhost:') && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  projectWindows.set(projectId, projectWindow);

  projectWindow.on('closed', () => {
    // 프로젝트 창 닫을 때 해당 프로젝트의 모든 에이전트 중지
    fetch(`http://localhost:${API_PORT}/projects/${projectId}/stop_all`, {
      method: 'POST'
    }).then(() => {
      console.log(`[Electron] 프로젝트 ${projectId} 에이전트 중지됨`);
    }).catch(err => {
      console.warn(`[Electron] 에이전트 중지 실패: ${err.message}`);
    });
    projectWindows.delete(projectId);
  });

  return projectWindow;
}

/**
 * 폴더 창 생성
 */
function createFolderWindow(folderId, folderName) {
  // 이미 열려있으면 포커스
  if (folderWindows.has(folderId)) {
    const existingWindow = folderWindows.get(folderId);
    if (!existingWindow.isDestroyed()) {
      existingWindow.focus();
      return;
    }
  }

  const folderWindow = new BrowserWindow({
    width: 900,
    height: 600,
    minWidth: 600,
    minHeight: 400,
    title: folderName || '폴더',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 15 },
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  // URL에 폴더 ID 전달 (한글 등 특수문자 인코딩)
  const encodedFolderId = encodeURIComponent(folderId);
  if (isDev) {
    folderWindow.loadURL(`http://localhost:5173/#/folder/${encodedFolderId}`);
  } else {
    folderWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: `/folder/${encodedFolderId}`
    });
  }

  // 외부 링크는 기본 브라우저에서 열기
  folderWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // 페이지 내 링크 클릭도 처리
  folderWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost:') && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  folderWindows.set(folderId, folderWindow);

  folderWindow.on('closed', () => {
    folderWindows.delete(folderId);
  });

  return folderWindow;
}


/**
 * 시스템 AI 창 생성
 */
function createSystemAIWindow() {
  // 이미 열려있으면 맨앞으로
  if (systemAIWindow && !systemAIWindow.isDestroyed()) {
    raiseWindow(systemAIWindow);
    return;
  }

  systemAIWindow = new BrowserWindow({
    width: 700,
    height: 850,
    minWidth: 400,
    minHeight: 500,
    title: '시스템 AI',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 15 },
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  if (isDev) {
    systemAIWindow.loadURL('http://localhost:5173/#/system-ai');
  } else {
    systemAIWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: '/system-ai'
    });
  }

  // 외부 링크는 기본 브라우저에서 열기
  systemAIWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  systemAIWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost:') && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  systemAIWindow.on('closed', () => {
    systemAIWindow = null;
  });

  return systemAIWindow;
}

/**
 * 비즈니스 관리 창 생성
 */
function createBusinessWindow() {
  // 이미 열려있으면 포커스
  if (businessWindow && !businessWindow.isDestroyed()) {
    businessWindow.focus();
    return;
  }

  businessWindow = new BrowserWindow({
    width: 1100,
    height: 700,
    minWidth: 800,
    minHeight: 500,
    title: '비즈니스 관리',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 15 },
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  if (isDev) {
    businessWindow.loadURL('http://localhost:5173/#/business');
  } else {
    businessWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: '/business'
    });
  }

  // 외부 링크는 기본 브라우저에서 열기
  businessWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // 페이지 내 링크 클릭도 처리
  businessWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost:') && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  businessWindow.on('closed', () => {
    businessWindow = null;
  });

  return businessWindow;
}

/**
 * 커뮤니티 창 생성 (옛 IndieNet 전용 창 대체 — IBL 커뮤니티 계기를 전용 창으로 렌더)
 */
function createCommunityWindow() {
  if (communityWindow && !communityWindow.isDestroyed()) {
    communityWindow.focus();
    return;
  }

  communityWindow = new BrowserWindow({
    width: 600,
    height: 800,
    minWidth: 400,
    minHeight: 600,
    title: '커뮤니티',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 15 },
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  if (isDev) {
    communityWindow.loadURL('http://localhost:5173/#/community');
  } else {
    communityWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: '/community'
    });
  }

  communityWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  communityWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost:') && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  communityWindow.on('closed', () => {
    communityWindow = null;
  });

  return communityWindow;
}

function createMessengerWindow() {
  if (messengerWindow && !messengerWindow.isDestroyed()) {
    messengerWindow.focus();
    return;
  }

  messengerWindow = new BrowserWindow({
    width: 900,
    height: 760,
    minWidth: 480,
    minHeight: 600,
    title: '메신저',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 15 },
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  if (isDev) {
    messengerWindow.loadURL('http://localhost:5173/#/messenger');
  } else {
    messengerWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: '/messenger'
    });
  }

  messengerWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  messengerWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost:') && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  messengerWindow.on('closed', () => {
    messengerWindow = null;
  });

  // 메신저를 보면 미확인 배지 해소 (열림·재포커스 모두)
  clearBadge();
  messengerWindow.on('focus', () => clearBadge());

  return messengerWindow;
}

/**
 * PC Manager 창 생성
 */
function createPCManagerWindow(initialPath = null) {
  // 이미 열려있으면 포커스
  if (pcManagerWindow && !pcManagerWindow.isDestroyed()) {
    pcManagerWindow.focus();
    return;
  }

  pcManagerWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: 'PC Manager',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 15 },
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  // URL에 초기 경로 전달
  const hashPath = initialPath
    ? `/pcmanager?path=${encodeURIComponent(initialPath)}`
    : '/pcmanager';

  if (isDev) {
    pcManagerWindow.loadURL(`http://localhost:5173/#${hashPath}`);
  } else {
    pcManagerWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: hashPath
    });
  }

  // 외부 링크는 기본 브라우저에서 열기
  pcManagerWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  pcManagerWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost:') && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  pcManagerWindow.on('closed', () => {
    pcManagerWindow = null;
  });

  return pcManagerWindow;
}

/**
 * Photo Manager 창 생성
 */
function createPhotoManagerWindow(initialPath = null) {
  // 이미 열려있으면 포커스
  if (photoManagerWindow && !photoManagerWindow.isDestroyed()) {
    photoManagerWindow.focus();
    return;
  }

  photoManagerWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    title: 'Photo Manager',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 15 },
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  // URL에 초기 경로 전달
  const hashPath = initialPath
    ? `/photo?path=${encodeURIComponent(initialPath)}`
    : '/photo';

  if (isDev) {
    photoManagerWindow.loadURL(`http://localhost:5173/#${hashPath}`);
  } else {
    photoManagerWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: hashPath
    });
  }

  // 외부 링크는 기본 브라우저에서 열기
  photoManagerWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  photoManagerWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost:') && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  photoManagerWindow.on('closed', () => {
    photoManagerWindow = null;
  });

  return photoManagerWindow;
}

/**
 * Android Manager 창 생성
 */
function createAndroidManagerWindow(deviceId = null, projectId = null) {
  // 이미 열려있으면 포커스
  if (androidManagerWindow && !androidManagerWindow.isDestroyed()) {
    androidManagerWindow.focus();
    return;
  }

  androidManagerWindow = new BrowserWindow({
    width: 450,
    height: 700,
    minWidth: 400,
    minHeight: 600,
    title: 'Android Manager',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    trafficLightPosition: process.platform === 'darwin' ? { x: 15, y: 15 } : undefined,
    frame: process.platform !== 'darwin',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  // URL에 device_id, project_id 파라미터 전달
  const params = [];
  if (deviceId) params.push(`device_id=${encodeURIComponent(deviceId)}`);
  if (projectId) params.push(`project_id=${encodeURIComponent(projectId)}`);
  const hashPath = params.length > 0 ? `/android?${params.join('&')}` : '/android';

  if (isDev) {
    androidManagerWindow.loadURL(`http://localhost:5173/#${hashPath}`);
  } else {
    androidManagerWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: hashPath
    });
  }

  // 외부 링크는 기본 브라우저에서 열기
  androidManagerWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  androidManagerWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost:') && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  androidManagerWindow.on('closed', () => {
    androidManagerWindow = null;
  });

  // 우클릭 컨텍스트 메뉴 설정
  setupContextMenu(androidManagerWindow);

  return androidManagerWindow;
}

/**
 * 강의 만들기 워크스페이스 창 생성
 * lectureId가 주어지면 해당 강의를 선택한 상태로, 미지정 시 강의 목록 화면.
 */
function createLectureWorkspaceWindow(lectureId = null) {
  // 이미 열려있으면 포커스 + (다른 강의 요청이면) 라우트 갱신
  if (lectureWorkspaceWindow && !lectureWorkspaceWindow.isDestroyed()) {
    lectureWorkspaceWindow.focus();
    if (lectureId) {
      lectureWorkspaceWindow.webContents.send('lecture-workspace-select', lectureId);
    }
    return lectureWorkspaceWindow;
  }

  lectureWorkspaceWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1200,
    minHeight: 700,
    title: '강의 만들기',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    trafficLightPosition: process.platform === 'darwin' ? { x: 15, y: 15 } : undefined,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  const hashPath = lectureId
    ? `/lecture-workspace?lecture_id=${encodeURIComponent(lectureId)}`
    : '/lecture-workspace';

  if (isDev) {
    lectureWorkspaceWindow.loadURL(`http://localhost:5173/#${hashPath}`);
  } else {
    lectureWorkspaceWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: hashPath
    });
  }

  // 외부 링크는 기본 브라우저에서
  lectureWorkspaceWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  lectureWorkspaceWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost:') && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  lectureWorkspaceWindow.on('closed', () => {
    lectureWorkspaceWindow = null;
  });

  setupContextMenu(lectureWorkspaceWindow);
  return lectureWorkspaceWindow;
}

/**
 * 다중채팅방 창 생성
 */
function createMultiChatWindow(roomId, roomName) {
  // 이미 열려있으면 포커스
  if (multiChatWindows.has(roomId)) {
    const existingWindow = multiChatWindows.get(roomId);
    if (!existingWindow.isDestroyed()) {
      existingWindow.focus();
      return;
    }
  }

  const multiChatWindow = new BrowserWindow({
    width: 1100,
    height: 700,
    minWidth: 900,
    minHeight: 600,
    title: roomName || '다중채팅방',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 15 },
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  // URL에 채팅방 ID 전달 (한글 등 특수문자 인코딩)
  const encodedRoomId = encodeURIComponent(roomId);
  if (isDev) {
    multiChatWindow.loadURL(`http://localhost:5173/#/multichat/${encodedRoomId}`);
  } else {
    multiChatWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: `/multichat/${encodedRoomId}`
    });
  }

  // 외부 링크는 기본 브라우저에서 열기
  multiChatWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // 페이지 내 링크 클릭도 처리
  multiChatWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost:') && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  multiChatWindows.set(roomId, multiChatWindow);

  multiChatWindow.on('closed', () => {
    multiChatWindows.delete(roomId);
  });

  return multiChatWindow;
}

// ★folderWindows 는 main.js 의 setupIPC 도 읽는다(폴더 간 드래그드롭·열린 창 목록).
// 레지스트리 자체를 내보낸다 — 소유자는 여기 하나, 읽는 쪽은 여럿.
export { folderWindows };

export { raiseWindow, createProjectWindow, createFolderWindow, createSystemAIWindow,
         createBusinessWindow, createCommunityWindow, createMessengerWindow,
         createPCManagerWindow, createPhotoManagerWindow, createAndroidManagerWindow,
         createLectureWorkspaceWindow, createMultiChatWindow };
