/**
 * Electron 메인 프로세스
 * Python 백엔드 관리 및 윈도우 생성
 */

import { app, BrowserWindow, ipcMain, shell, dialog, Menu } from 'electron';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
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
let multiChatWindows = new Map(); // 다중채팅방 창 관리
let indieNetWindow = null; // IndieNet 창
let businessWindow = null; // 비즈니스 관리 창
let pcManagerWindow = null; // PC Manager 창
let photoManagerWindow = null; // Photo Manager 창
let androidManagerWindow = null; // Android Manager 창
let logWindow = null; // 로그 뷰어 창

// 로그 버퍼 (최근 500줄 유지)
const MAX_LOG_LINES = 500;
let logBuffer = [];

// API 포트
const API_PORT = 8765;

/**
 * 로그 메시지 추가 및 브로드캐스트
 */
function addLog(message) {
  const timestamp = new Date().toLocaleTimeString('ko-KR', { hour12: false });
  const logEntry = `[${timestamp}] ${message}`;

  // 버퍼에 추가
  logBuffer.push(logEntry);
  if (logBuffer.length > MAX_LOG_LINES) {
    logBuffer.shift(); // 오래된 로그 제거
  }

  // 로그 창이 열려있으면 전송
  if (logWindow && !logWindow.isDestroyed()) {
    logWindow.webContents.send('log-message', logEntry);
  }
}

/**
 * 로그 뷰어 창 생성
 */
function createLogWindow() {
  // 이미 열려있으면 포커스
  if (logWindow && !logWindow.isDestroyed()) {
    logWindow.focus();
    return;
  }

  logWindow = new BrowserWindow({
    width: 800,
    height: 600,
    minWidth: 500,
    minHeight: 400,
    title: 'IndieBiz 로그',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    trafficLightPosition: process.platform === 'darwin' ? { x: 15, y: 15 } : undefined,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  if (isDev) {
    logWindow.loadURL('http://localhost:5173/#/log-viewer');
  } else {
    logWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      hash: '/log-viewer'
    });
  }

  // 창이 로드되면 기존 로그 전송
  logWindow.webContents.on('did-finish-load', () => {
    if (logWindow && !logWindow.isDestroyed()) {
      logWindow.webContents.send('log-history', logBuffer);
    }
  });

  logWindow.on('closed', () => {
    logWindow = null;
  });

  // 우클릭 컨텍스트 메뉴 설정
  setupContextMenu(logWindow);

  return logWindow;
}

/**
 * 우클릭 컨텍스트 메뉴 설정 (복사/붙여넣기 등)
 */
function setupContextMenu(window) {
  window.webContents.on('context-menu', (event, params) => {
    const contextMenu = Menu.buildFromTemplate([
      { role: 'undo', label: '실행 취소' },
      { role: 'redo', label: '다시 실행' },
      { type: 'separator' },
      { role: 'cut', label: '잘라내기' },
      { role: 'copy', label: '복사' },
      { role: 'paste', label: '붙여넣기' },
      { type: 'separator' },
      { role: 'selectAll', label: '전체 선택' }
    ]);
    contextMenu.popup(window);
  });
}

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
 * 번들(src)의 파일을 userData(dest)에 동기화
 * 앱 코드 파일만 덮어쓰고, 사용자 데이터는 모두 보존
 * 새 파일(dest에 없는 것)은 무조건 복사
 */
function syncDirOverwrite(srcDir, destDir) {
  const skipDirs = new Set(['node_modules', '__pycache__', '.git', '_temp_']);
  // 덮어쓸 확장자 (앱 코드만)
  const overwriteExtensions = new Set([
    '.py', '.js', '.ts', '.jsx', '.tsx',  // 코드
    '.html', '.css', '.scss',              // 웹
    '.md',                                  // 문서 (패키지 README 등)
  ]);
  // 확장자와 무관하게 항상 덮어쓸 특정 파일명 (패키지 메타데이터)
  const alwaysOverwriteFiles = new Set([
    'tool.json',          // 패키지 정의
    'requirements.txt',   // Python 의존성
    'package.json',       // Node 의존성 (패키지 내부용)
  ]);

  if (!fs.existsSync(destDir)) {
    fs.mkdirSync(destDir, { recursive: true });
  }

  const entries = fs.readdirSync(srcDir, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(srcDir, entry.name);
    const destPath = path.join(destDir, entry.name);

    if (entry.isDirectory()) {
      if (skipDirs.has(entry.name)) continue;
      syncDirOverwrite(srcPath, destPath);
    } else if (entry.isFile()) {
      // dest에 없으면 무조건 복사 (새 파일)
      if (!fs.existsSync(destPath)) {
        fs.copyFileSync(srcPath, destPath);
        continue;
      }
      // 이미 있으면 코드 파일 또는 패키지 메타데이터만 덮어쓰기
      const ext = path.extname(entry.name).toLowerCase();
      if (overwriteExtensions.has(ext) || alwaysOverwriteFiles.has(entry.name)) {
        fs.copyFileSync(srcPath, destPath);
      }
    }
  }
}

/**
 * 프로덕션 데이터 디렉토리 초기화
 * 앱 번들(resources/) 내의 데이터를 사용자 폴더(userData)로 동기화
 * - 재설치 시 무조건 최신 파일로 덮어쓰기
 * - .db 파일만 보존 (사용자 데이터)
 */
function initUserData() {
  const userDataPath = app.getPath('userData'); // Windows: %APPDATA%/IndieBiz, macOS: ~/Library/Application Support/IndieBiz
  const resourcesPath = process.resourcesPath;

  console.log(`[Init] userData 경로: ${userDataPath}`);
  console.log(`[Init] resources 경로: ${resourcesPath}`);

  // 1. 기본 폴더들 - 무조건 덮어쓰기 (.db 파일만 보존)
  const dirsToSync = ['data', 'projects', 'templates', 'tokens'];

  for (const dir of dirsToSync) {
    const src = path.join(resourcesPath, dir);
    const dest = path.join(userDataPath, dir);

    if (fs.existsSync(src)) {
      console.log(`[Init] 데이터 동기화: ${dir}`);
      syncDirOverwrite(src, dest);
    }
  }

  // 2. 패키지 폴더 동기화 - 무조건 덮어쓰기 (.db 파일만 보존)
  const packageTypes = ['tools', 'extensions'];
  for (const pkgType of packageTypes) {
    const packagesSrc = path.join(resourcesPath, 'data', 'packages', 'installed', pkgType);
    const packagesDest = path.join(userDataPath, 'data', 'packages', 'installed', pkgType);

    if (!fs.existsSync(packagesSrc)) continue;

    if (!fs.existsSync(packagesDest)) {
      fs.mkdirSync(packagesDest, { recursive: true });
    }

    const srcPackages = fs.readdirSync(packagesSrc);
    for (const pkg of srcPackages) {
      const pkgSrc = path.join(packagesSrc, pkg);
      const pkgDest = path.join(packagesDest, pkg);

      if (!fs.statSync(pkgSrc).isDirectory()) continue;

      console.log(`[Init] 패키지 동기화: ${pkgType}/${pkg}`);
      syncDirOverwrite(pkgSrc, pkgDest);
    }
  }

  // 3. common_prompts 폴더 동기화 (항상 최신으로 덮어쓰기)
  const promptsSrc = path.join(resourcesPath, 'data', 'common_prompts');
  const promptsDest = path.join(userDataPath, 'data', 'common_prompts');

  if (fs.existsSync(promptsSrc)) {
    if (fs.existsSync(promptsDest)) {
      fs.rmSync(promptsDest, { recursive: true });
    }
    fs.cpSync(promptsSrc, promptsDest, { recursive: true });
    console.log('[Init] 프롬프트 파일 업데이트 완료');
  }

  // 4. .env 파일 복사 (없으면)
  const envSrc = path.join(resourcesPath, 'backend', '.env');
  const envDest = path.join(userDataPath, '.env');
  if (!fs.existsSync(envDest) && fs.existsSync(envSrc)) {
    fs.copyFileSync(envSrc, envDest);
  }

  return userDataPath;
}

/**
 * Python 백엔드 시작
 */
async function startPythonBackend() {
  // 포트 확인 - 이미 사용 중이면 기존 서버를 그대로 사용 (start.sh가 먼저 띄운 경우)
  const available = await isPortAvailable(API_PORT);
  if (!available) {
    console.log(`[Python] 포트 ${API_PORT} 사용 중 - 기존 서버 사용`);
    return;
  }

  // 경로 설정
  let backendPath;
  let pythonPath;
  let pythonArgs;
  let basePath; // 데이터가 저장될 기본 경로

  if (isDev) {
    // 개발 모드: 상대 경로
    backendPath = path.join(__dirname, '..', '..', 'backend');
    basePath = path.join(__dirname, '..', '..'); // indiebizOS root
    pythonPath = process.platform === 'win32' ? 'python' : 'python3';
    pythonArgs = [path.join(backendPath, 'api.py')];
  } else {
    // 프로덕션: extraResources에서
    backendPath = path.join(process.resourcesPath, 'backend');
    // 데이터는 사용자 폴더에 저장 (권한 문제 방지, 업데이트 시 보존)
    basePath = initUserData();

    if (process.platform === 'win32') {
      // Windows: 임베디드 Python 우선, 없으면 시스템 Python
      const embeddedPython = path.join(process.resourcesPath, 'runtime', 'python', 'python.exe');
      console.log(`[Python] 임베디드 Python 경로: ${embeddedPython}`);
      console.log(`[Python] 임베디드 Python 존재 여부: ${fs.existsSync(embeddedPython)}`);
      if (fs.existsSync(embeddedPython)) {
        pythonPath = embeddedPython;
        console.log('[Python] 임베디드 Python 사용');
      } else {
        // 시스템 Python 사용 (python 또는 python3)
        pythonPath = 'python';
        console.log('[Python] 시스템 Python으로 폴백');
      }
      pythonArgs = [path.join(backendPath, 'api.py')];
    } else if (process.platform === 'darwin') {
      // macOS: 번들된 Python 우선, 없으면 시스템 Python
      const bundledPython = path.join(process.resourcesPath, 'runtime', 'python', 'bin', 'python3');
      if (fs.existsSync(bundledPython)) {
        pythonPath = bundledPython;
        console.log('[Python] 번들된 Python 사용');
      } else {
        pythonPath = 'python3';
        console.log('[Python] 시스템 Python 사용');
      }
      pythonArgs = [path.join(backendPath, 'api.py')];
    } else {
      // Linux
      pythonPath = 'python3';
      pythonArgs = [path.join(backendPath, 'api.py')];
    }
  }

  console.log(`[Python] ========== 백엔드 시작 디버그 ==========`);
  console.log(`[Python] resourcesPath: ${process.resourcesPath}`);
  console.log(`[Python] pythonPath: ${pythonPath}`);
  console.log(`[Python] pythonPath 존재: ${fs.existsSync(pythonPath)}`);
  console.log(`[Python] backendPath: ${backendPath}`);
  console.log(`[Python] backendPath 존재: ${fs.existsSync(backendPath)}`);
  console.log(`[Python] api.py 경로: ${pythonArgs[0]}`);
  console.log(`[Python] api.py 존재: ${fs.existsSync(pythonArgs[0])}`);
  console.log(`[Python] basePath: ${basePath}`);
  console.log(`[Python] ===========================================`);

  // 런타임 경로 (번들된 Python/Node 위치)
  const runtimePath = isDev
    ? path.join(__dirname, '..', '..', 'runtime')  // 개발: indiebizOS/runtime
    : path.join(process.resourcesPath, 'runtime');  // 프로덕션: resources/runtime

  // Node.js 경로 계산 (도구 핸들러용)
  let nodePath = 'node';  // 기본값
  if (process.platform === 'win32') {
    const embeddedNode = path.join(runtimePath, 'node', 'node.exe');
    if (fs.existsSync(embeddedNode)) {
      nodePath = embeddedNode;
    }
  } else if (process.platform === 'darwin') {
    const bundledNode = path.join(runtimePath, 'node', 'bin', 'node');
    if (fs.existsSync(bundledNode)) {
      nodePath = bundledNode;
    }
  }

  // Python 프로세스 시작
  pythonProcess = spawn(pythonPath, pythonArgs, {
    cwd: backendPath,
    env: {
      ...process.env,
      INDIEBIZ_API_PORT: API_PORT.toString(),
      INDIEBIZ_BASE_PATH: basePath,
      INDIEBIZ_RUNTIME_PATH: runtimePath,  // 도구 핸들러가 번들 런타임 찾을 때 사용
      INDIEBIZ_PYTHON_PATH: pythonPath,    // 직접 Python 경로 전달
      INDIEBIZ_NODE_PATH: nodePath,        // 직접 Node.js 경로 전달
      INDIEBIZ_PRODUCTION: isDev ? '' : '1',
      PYTHONUNBUFFERED: '1',
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1'
    },
    stdio: ['ignore', 'pipe', 'pipe']
  });

  pythonProcess.stdout.on('data', (data) => {
    try {
      const msg = `[Python] ${data.toString().trim()}`;
      console.log(msg);
      addLog(msg);
    } catch (e) {
      // 파이프 에러 무시
    }
  });

  pythonProcess.stderr.on('data', (data) => {
    try {
      const msg = `[Python Error] ${data.toString().trim()}`;
      console.error(msg);
      addLog(msg);
    } catch (e) {
      // 파이프 에러 무시
    }
  });

  pythonProcess.on('close', (code) => {
    const msg = `[Python] 프로세스 종료: ${code}`;
    console.log(msg);
    addLog(msg);

    // 비정상 종료 시 사용자에게 알림 (앱 시작 직후 종료된 경우)
    if (code !== 0 && code !== null) {
      console.error(`[Python] 백엔드가 비정상 종료되었습니다 (코드: ${code})`);

      // 모듈 에러일 가능성 (의존성 미설치)
      dialog.showErrorBox(
        '백엔드 시작 실패',
        `Python 백엔드가 시작되지 않았습니다 (종료 코드: ${code}).\n\n` +
        '필요한 Python 패키지가 설치되어 있는지 확인해주세요:\n' +
        'pip install fastapi uvicorn aiofiles python-dotenv\n\n' +
        '또는 requirements.txt를 사용하여 설치:\n' +
        'pip install -r backend/requirements-core.txt'
      );
    }

    pythonProcess = null;
  });

  pythonProcess.on('error', (err) => {
    console.error(`[Python] 프로세스 에러: ${err.message}`);

    // Python을 찾을 수 없는 경우 사용자에게 알림
    if (err.code === 'ENOENT') {
      dialog.showErrorBox(
        'Python을 찾을 수 없습니다',
        'IndieBiz를 실행하려면 Python이 설치되어 있어야 합니다.\n\n' +
        'Python 3.8 이상을 설치한 후 다시 시도해주세요.\n' +
        'https://www.python.org/downloads/'
      );
    }
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
    if (process.platform === 'win32') {
      // Windows: SIGTERM이 지원되지 않으므로 taskkill로 프로세스 트리 전체 종료
      spawn('taskkill', ['/pid', pythonProcess.pid.toString(), '/f', '/t']);
    } else {
      pythonProcess.kill('SIGTERM');
    }
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

  // 우클릭 컨텍스트 메뉴 설정
  setupContextMenu(mainWindow);
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
    // 다중채팅방 창 닫을 때 해당 방의 모든 에이전트 비활성화
    fetch(`http://localhost:${API_PORT}/multi-chat/rooms/${roomId}/deactivate-all`, {
      method: 'POST'
    }).then(() => {
      console.log(`[Electron] 다중채팅방 ${roomId} 에이전트 비활성화됨`);
    }).catch(err => {
      console.warn(`[Electron] 에이전트 비활성화 실패: ${err.message}`);
    });
    multiChatWindows.delete(roomId);
  });

  return multiChatWindow;
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

  // 비즈니스 관리 창 열기
  ipcMain.handle('open-business-window', () => {
    createBusinessWindow();
  });

  // 다중채팅방 창 열기
  ipcMain.handle('open-multichat-window', (_, roomId, roomName) => {
    createMultiChatWindow(roomId, roomName);
  });

  // PC Manager 창 열기
  ipcMain.handle('open-pcmanager-window', (_, initialPath) => {
    createPCManagerWindow(initialPath);
  });

  // Photo Manager 창 열기
  ipcMain.handle('open-photo-manager-window', (_, initialPath) => {
    createPhotoManagerWindow(initialPath);
  });

  // Android Manager 창 열기
  ipcMain.handle('open-android-manager-window', (_, deviceId, projectId) => {
    createAndroidManagerWindow(deviceId, projectId);
  });

  // 로그 뷰어 창 열기
  ipcMain.handle('open-log-window', () => {
    createLogWindow();
  });

  // 로그 버퍼 클리어
  ipcMain.handle('clear-logs', () => {
    logBuffer = [];
    if (logWindow && !logWindow.isDestroyed()) {
      logWindow.webContents.send('log-cleared');
    }
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

  // 이미지 파일 선택 다이얼로그 (다중 선택)
  ipcMain.handle('select-images', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openFile', 'multiSelections'],
      title: '이미지 파일 선택',
      buttonLabel: '선택',
      filters: [
        { name: '이미지', extensions: ['jpg', 'jpeg', 'png', 'gif', 'webp'] }
      ]
    });

    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }

    return result.filePaths;
  });
}

// 앱 준비
app.whenReady().then(async () => {
  console.log('[Electron] 앱 시작');
  addLog('[Electron] IndieBiz 앱 시작');

  // macOS 기본 메뉴 설정 (복사/붙여넣기 등)
  const template = [
    {
      label: 'IndieBiz',
      submenu: [
        { role: 'about' },
        { type: 'separator' },
        { role: 'services' },
        { type: 'separator' },
        { role: 'hide' },
        { role: 'hideOthers' },
        { role: 'unhide' },
        { type: 'separator' },
        { role: 'quit' }
      ]
    },
    {
      label: '편집',
      submenu: [
        { role: 'undo', label: '실행 취소', accelerator: 'CmdOrCtrl+Z' },
        { role: 'redo', label: '다시 실행', accelerator: 'Shift+CmdOrCtrl+Z' },
        { type: 'separator' },
        { role: 'cut', label: '잘라내기', accelerator: 'CmdOrCtrl+X' },
        { role: 'copy', label: '복사', accelerator: 'CmdOrCtrl+C' },
        { role: 'paste', label: '붙여넣기', accelerator: 'CmdOrCtrl+V' },
        { role: 'pasteAndMatchStyle', label: '스타일 맞춰 붙여넣기', accelerator: 'Shift+CmdOrCtrl+V' },
        { role: 'delete', label: '삭제' },
        { role: 'selectAll', label: '전체 선택', accelerator: 'CmdOrCtrl+A' }
      ]
    },
    {
      label: '보기',
      submenu: [
        { role: 'reload', label: '새로고침' },
        { role: 'forceReload', label: '강제 새로고침' },
        { role: 'toggleDevTools', label: '개발자 도구' },
        { type: 'separator' },
        { role: 'resetZoom', label: '확대/축소 초기화' },
        { role: 'zoomIn', label: '확대' },
        { role: 'zoomOut', label: '축소' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: '전체 화면' }
      ]
    },
    {
      label: '윈도우',
      submenu: [
        { role: 'minimize', label: '최소화' },
        { role: 'zoom', label: '확대/축소' },
        { type: 'separator' },
        { role: 'front', label: '앞으로 가져오기' },
        { type: 'separator' },
        { role: 'window', label: '윈도우' }
      ]
    }
  ];
  
  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);

  // IPC 설정
  setupIPC();

  // Python 백엔드 시작
  try {
    addLog('[Electron] Python 백엔드 시작 시도...');
    await startPythonBackend();
    addLog('[Electron] Python 백엔드 시작 완료');
  } catch (err) {
    addLog(`[Electron] Python 백엔드 시작 실패: ${err.message}`);
    console.error('[Electron] Python 백엔드 시작 실패:', err);
    dialog.showErrorBox(
      '백엔드 시작 오류',
      `Python 백엔드를 시작하는 중 오류가 발생했습니다.\n\n${err.message}`
    );
  }

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
