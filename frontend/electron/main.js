/**
 * Electron 메인 프로세스
 * Python 백엔드 관리 및 윈도우 생성
 */

import { app, BrowserWindow, ipcMain, shell, dialog } from 'electron';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import net from 'net';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 개발 모드 확인
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

// Python 프로세스
let pythonProcess = null;
let mainWindow = null;
let projectWindows = new Map(); // 프로젝트 창 관리
let folderWindows = new Map(); // 폴더 창 관리
let indieNetWindow = null; // IndieNet 창

// API 포트
const API_PORT = 8765;

/**
 * 포트 사용 가능 여부 확인
 */
function isPortAvailable(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => {
      server.close();
      resolve(true);
    });
    server.listen(port, '127.0.0.1');
  });
}

/**
 * Python 백엔드 시작
 */
async function startPythonBackend() {
  // 포트 확인
  const available = await isPortAvailable(API_PORT);
  if (!available) {
    console.log(`[Python] 포트 ${API_PORT} 이미 사용 중 - 기존 서버 사용`);
    return;
  }

  // 경로 설정
  let backendPath;
  let pythonPath;
  let pythonArgs;

  if (isDev) {
    // 개발 모드: 상대 경로
    backendPath = path.join(__dirname, '..', '..', 'backend');
    pythonPath = process.platform === 'win32' ? 'python' : 'python3';
    pythonArgs = [path.join(backendPath, 'api.py')];
  } else {
    // 프로덕션: extraResources에서
    backendPath = path.join(process.resourcesPath, 'backend');

    if (process.platform === 'win32') {
      // Windows: 임베디드 Python 사용
      pythonPath = path.join(process.resourcesPath, 'python', 'python.exe');
      pythonArgs = [path.join(backendPath, 'api.py')];
    } else if (process.platform === 'darwin') {
      // macOS: 시스템 Python 또는 번들된 Python
      const bundledPython = path.join(process.resourcesPath, 'python', 'bin', 'python3');
      const fs = require('fs');
      if (fs.existsSync(bundledPython)) {
        pythonPath = bundledPython;
      } else {
        pythonPath = 'python3';
      }
      pythonArgs = [path.join(backendPath, 'api.py')];
    } else {
      // Linux
      pythonPath = 'python3';
      pythonArgs = [path.join(backendPath, 'api.py')];
    }
  }

  console.log(`[Python] 백엔드 시작: ${pythonPath} ${pythonArgs.join(' ')}`);

  // Python 프로세스 시작
  pythonProcess = spawn(pythonPath, pythonArgs, {
    cwd: backendPath,
    env: {
      ...process.env,
      INDIEBIZ_API_PORT: API_PORT.toString(),
      PYTHONUNBUFFERED: '1'
    },
    stdio: ['ignore', 'pipe', 'pipe']
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Python] ${data.toString().trim()}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python Error] ${data.toString().trim()}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`[Python] 프로세스 종료: ${code}`);
    pythonProcess = null;
  });

  pythonProcess.on('error', (err) => {
    console.error(`[Python] 프로세스 에러: ${err.message}`);
  });

  // 서버 준비 대기
  await waitForServer();
}

/**
 * 서버 준비 대기
 */
async function waitForServer(maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const response = await fetch(`http://127.0.0.1:${API_PORT}/health`);
      if (response.ok) {
        console.log('[Python] 서버 준비 완료');
        return true;
      }
    } catch (e) {
      // 아직 준비 안됨
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  console.warn('[Python] 서버 준비 타임아웃');
  return false;
}

/**
 * Python 백엔드 종료
 */
function stopPythonBackend() {
  if (pythonProcess) {
    console.log('[Python] 백엔드 종료 중...');
    pythonProcess.kill('SIGTERM');
    pythonProcess = null;
  }
}

/**
 * 메인 윈도우 생성
 */
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: 'IndieBiz',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 15 },
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  // 개발/프로덕션에 따라 URL 로드
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    // DevTools는 필요할 때 Cmd+Option+I로 열기
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  // 외부 링크는 기본 브라우저에서 열기
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // 페이지 내 링크 클릭도 처리
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost:') && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

/**
 * 프로젝트 창 생성
 */
function createProjectWindow(projectId, projectName) {
  // 이미 열려있으면 포커스
  if (projectWindows.has(projectId)) {
    const existingWindow = projectWindows.get(projectId);
    if (!existingWindow.isDestroyed()) {
      existingWindow.focus();
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
  const encodedProjectId = encodeURIComponent(projectId);
  if (isDev) {
    projectWindow.loadURL(`http://localhost:5173/#/project/${encodedProjectId}`);
  } else {
    projectWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: `/project/${encodedProjectId}`
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
 * IndieNet 창 생성
 */
function createIndieNetWindow() {
  // 이미 열려있으면 포커스
  if (indieNetWindow && !indieNetWindow.isDestroyed()) {
    indieNetWindow.focus();
    return;
  }

  indieNetWindow = new BrowserWindow({
    width: 600,
    height: 800,
    minWidth: 400,
    minHeight: 600,
    title: 'IndieNet',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 15 },
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  if (isDev) {
    indieNetWindow.loadURL('http://localhost:5173/#/indienet');
  } else {
    indieNetWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: '/indienet'
    });
  }

  // 외부 링크는 기본 브라우저에서 열기
  indieNetWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // 페이지 내 링크 클릭도 처리
  indieNetWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost:') && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  indieNetWindow.on('closed', () => {
    indieNetWindow = null;
  });

  return indieNetWindow;
}

/**
 * IPC 핸들러 등록
 */
function setupIPC() {
  // API 포트 정보
  ipcMain.handle('get-api-port', () => API_PORT);

  // 외부 URL 열기
  ipcMain.handle('open-external', (_, url) => {
    shell.openExternal(url);
  });

  // 앱 정보
  ipcMain.handle('get-app-info', () => ({
    version: app.getVersion(),
    name: app.getName(),
    isDev
  }));

  // 프로젝트 창 열기
  ipcMain.handle('open-project-window', (_, projectId, projectName) => {
    createProjectWindow(projectId, projectName);
  });

  // 폴더 창 열기
  ipcMain.handle('open-folder-window', (_, folderId, folderName) => {
    createFolderWindow(folderId, folderName);
  });

  // IndieNet 창 열기
  ipcMain.handle('open-indienet-window', () => {
    createIndieNetWindow();
  });

  // 폴더에서 아이템을 밖으로 드래그할 때 (런처에 드롭)
  ipcMain.handle('drop-item-to-launcher', (event, itemId, itemType, sourceFolderId) => {
    // 런처 창에 이벤트 전송
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('item-dropped-from-folder', { itemId, itemType, sourceFolderId });
      return true;
    }
    return false;
  });

  // 폴더 창에서 다른 폴더로 드래그할 때
  ipcMain.handle('drop-item-to-folder', (event, itemId, itemType, targetFolderId, sourceFolderId) => {
    // 타겟 폴더 창에 이벤트 전송
    if (folderWindows.has(targetFolderId)) {
      const targetWindow = folderWindows.get(targetFolderId);
      if (!targetWindow.isDestroyed()) {
        targetWindow.webContents.send('item-dropped-into-folder', { itemId, itemType, sourceFolderId });
        return true;
      }
    }
    return false;
  });

  // 현재 열려있는 폴더 창 목록
  ipcMain.handle('get-open-folder-windows', () => {
    const openFolders = [];
    for (const [folderId, window] of folderWindows) {
      if (!window.isDestroyed()) {
        const bounds = window.getBounds();
        openFolders.push({ folderId, bounds });
      }
    }
    return openFolders;
  });

  // 런처 창 위치 정보
  ipcMain.handle('get-launcher-bounds', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      return mainWindow.getBounds();
    }
    return null;
  });

  // 폴더 선택 다이얼로그
  ipcMain.handle('select-folder', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory'],
      title: '패키지 폴더 선택',
      buttonLabel: '선택'
    });

    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }

    return result.filePaths[0];
  });
}

// 앱 준비
app.whenReady().then(async () => {
  console.log('[Electron] 앱 시작');

  // IPC 설정
  setupIPC();

  // Python 백엔드 시작
  await startPythonBackend();

  // 윈도우 생성
  createWindow();

  // macOS: 독에서 클릭 시 윈도우 재생성
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// 모든 윈도우 닫힘
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// 앱 종료 전
app.on('before-quit', () => {
  stopPythonBackend();
});

// 앱 종료
app.on('quit', () => {
  stopPythonBackend();
});
