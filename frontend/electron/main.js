/**
 * Electron 메인 프로세스
 * Python 백엔드 관리 및 윈도우 생성
 */

import { app, BrowserWindow, ipcMain, shell, dialog, Menu, clipboard } from 'electron';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import net from 'net';
import * as foragePw from './forage-passwords.js';

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
let businessWindow = null; // 비즈니스 관리 창
let communityWindow = null; // 커뮤니티 창 (옛 IndieNet — IBL 커뮤니티 계기)
let messengerWindow = null; // 메신저 창 (옛 이웃관리·빠른 연락처 — IBL 메신저 계기)
let pcManagerWindow = null; // PC Manager 창
let photoManagerWindow = null; // Photo Manager 창
let androidManagerWindow = null; // Android Manager 창
let systemAIWindow = null; // 시스템 AI 창
let lectureWorkspaceWindow = null; // 강의 만들기 워크스페이스 창

// API 포트
const API_PORT = 8765;

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

  // macOS에서 Ctrl+C(윈도우 습관)도 복사가 되게 메운다.
  // 애플리케이션 메뉴 accelerator(CmdOrCtrl+C)는 macOS에서 Cmd+C만 매핑하므로,
  // <pre> 등 비입력 영역에서 Ctrl+C는 무시된다 → 선택해도 복사 안 됨. 그 틈만 직접 처리한다.
  // 복사만: Ctrl+A(줄 처음)·Ctrl+V 등은 macOS 텍스트 필드의 기본 이동 바인딩이라 건드리지 않는다.
  // (Windows/Linux는 메뉴가 이미 Ctrl+C를 처리하므로 추가하지 않는다 — 중복 방지.)
  if (process.platform === 'darwin') {
    window.webContents.on('before-input-event', (event, input) => {
      if (input.type !== 'keyDown' || !input.control || input.meta || input.alt) return;
      if ((input.key || '').toLowerCase() === 'c') window.webContents.copy();
    });
  }
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
 *
 * forceOverwrite(destPath) 술어가 true 를 반환하면 확장자와 무관하게 덮어쓴다.
 * 표준 코어 어휘 산출물(ibl_nodes.yaml, 코어 패키지 ibl_actions.yaml, 코어 앱 매니페스트)을
 * 갱신하기 위한 것 — 이 파일들은 코어 소유라 git pull 경로에선 늘 덮어써지는데,
 * DMG 경로에선 .yaml 이라 보존돼 어휘가 stale 해지던 증상을 core_manifest 기준으로 교정.
 */
function syncDirOverwrite(srcDir, destDir, forceOverwrite = null, skipPaths = null) {
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
      if (skipPaths && skipPaths.has(srcPath)) continue;  // 별도 처리되는 하위트리(예: packages)
      syncDirOverwrite(srcPath, destPath, forceOverwrite, skipPaths);
    } else if (entry.isFile()) {
      // dest에 없으면 무조건 복사 (새 파일)
      if (!fs.existsSync(destPath)) {
        fs.copyFileSync(srcPath, destPath);
        continue;
      }
      // 이미 있으면 코드 파일 / 패키지 메타데이터 / 코어 어휘 산출물만 덮어쓰기
      const ext = path.extname(entry.name).toLowerCase();
      const isCore = forceOverwrite ? forceOverwrite(destPath) : false;
      if (isCore || overwriteExtensions.has(ext) || alwaysOverwriteFiles.has(entry.name)) {
        fs.copyFileSync(srcPath, destPath);
      }
    }
  }
}

/**
 * 번들된 core_manifest.json 을 읽어 "코어 소유 어휘 산출물"을 판정하는 술어를 만든다.
 * 매니페스트가 없으면 null → syncDirOverwrite 는 기존(보수적) 동작 유지.
 */
function makeCoreForceOverwrite(resourcesPath) {
  let manifest;
  try {
    const p = path.join(resourcesPath, 'data', 'core_manifest.json');
    if (!fs.existsSync(p)) return null;
    manifest = JSON.parse(fs.readFileSync(p, 'utf-8'));
  } catch (e) {
    console.log(`[Init] core_manifest 로드 실패 (보수적 동기화 유지): ${e}`);
    return null;
  }
  const core = manifest.core || {};
  const vocabArtifacts = new Set(core.vocab_artifacts || []);   // 예: ibl_nodes.yaml
  const coreInstruments = new Set(core.instruments || []);       // basename (확장자 제외)
  const corePackages = new Set([
    ...((core.packages || {}).tools || []),
    ...((core.packages || {}).extensions || []),
  ]);

  return (destPath) => {
    const norm = destPath.split(path.sep).join('/');
    const base = path.basename(norm);
    // 1) 빌드 산출 어휘 카탈로그
    if (vocabArtifacts.has(base)) return true;
    // 2) 코어 앱 매니페스트 (data/instruments/<name>.yaml)
    const instMatch = norm.match(/\/data\/instruments\/([^/]+)\.yaml$/);
    if (instMatch && coreInstruments.has(instMatch[1])) return true;
    // 3) 코어 패키지의 어휘 정의 (installed|not_installed/<type>/<pkg>/ibl_actions.yaml)
    if (base === 'ibl_actions.yaml') {
      const pkgMatch = norm.match(/\/packages\/(?:installed|not_installed)\/(?:tools|extensions)\/([^/]+)\//);
      if (pkgMatch && corePackages.has(pkgMatch[1])) return true;
    }
    return false;
  };
}

/**
 * 패키지 동기화 — ★설치 상태(installed/not_installed 폴더 배치)를 사용자 소유로 보존.
 *
 * 불변식2: 업데이트/재설치가 사용자의 켜고/끈 선택을 덮으면 안 된다.
 * package_manager 의 진실은 "폴더 위치"(installed=활성 / not_installed=비활성)인데,
 * 번들은 자기 기본 배치를 갖는다. 그대로 복사하면 사용자가 끈 걸 되켜거나(번들 installed→덮음)
 * 켠 걸 중복 생성(번들 not_installed 되살림)한다.
 *
 * 그래서: 각 코어 패키지를 userData 의 *현재 위치*(둘 중 어디든)에서 찾아 그 자리에서
 * 파일만 갱신한다. userData 어디에도 없을 때만(=이 릴리스의 새 패키지) 번들 기본 폴더에 추가.
 * → 사용자의 활성/비활성 선택이 업데이트를 살아남는다. 동시에 "배포를 비활성으로 내보내기"는
 *   단지 리포에서 패키지를 not_installed/ 에 두는 데이터 결정이 된다(불변식1의 토대).
 *
 * 사용자가 *직접 만든*(미추적) 패키지는 번들에 없어 여기서 순회조차 안 됨 = 보존.
 */
function syncPackagesPreservingState(resourcesPath, userDataPath, coreForceOverwrite) {
  const kinds = ['tools', 'extensions'];
  const states = ['installed', 'not_installed'];
  for (const kind of kinds) {
    for (const bundleState of states) {
      const bundleDir = path.join(resourcesPath, 'data', 'packages', bundleState, kind);
      if (!fs.existsSync(bundleDir)) continue;
      for (const pkg of fs.readdirSync(bundleDir)) {
        const pkgSrc = path.join(bundleDir, pkg);
        if (!fs.statSync(pkgSrc).isDirectory()) continue;

        // 사용자가 이 패키지를 어디에 두었나? (현재 배치 = 사용자 소유 상태)
        const userInstalled = path.join(userDataPath, 'data', 'packages', 'installed', kind, pkg);
        const userNotInstalled = path.join(userDataPath, 'data', 'packages', 'not_installed', kind, pkg);

        let pkgDest;
        if (fs.existsSync(userInstalled)) {
          pkgDest = userInstalled;          // 사용자가 켜둠 → 그 자리에서 갱신
        } else if (fs.existsSync(userNotInstalled)) {
          pkgDest = userNotInstalled;       // 사용자가 꺼둠 → 그 자리에서 갱신
        } else {
          // 사용자에게 없음 = 이 릴리스의 새 패키지 → 번들 기본 상태로 추가
          pkgDest = path.join(userDataPath, 'data', 'packages', bundleState, kind, pkg);
        }
        console.log(`[Init] 패키지 동기화(상태보존): ${kind}/${pkg} → ${path.basename(path.dirname(path.dirname(pkgDest)))}`);
        syncDirOverwrite(pkgSrc, pkgDest, coreForceOverwrite);
      }
    }
  }
}

/**
 * 프로덕션 데이터 디렉토리 초기화
 * 앱 번들(resources/) 내의 데이터를 사용자 폴더(userData)로 동기화
 * - 재설치 시 무조건 최신 파일로 덮어쓰기
 * - .db 파일만 보존 (사용자 데이터)
 * - 패키지는 설치 상태(폴더 배치) 보존 (syncPackagesPreservingState)
 */
function initUserData() {
  const userDataPath = app.getPath('userData'); // Windows: %APPDATA%/IndieBiz, macOS: ~/Library/Application Support/IndieBiz
  const resourcesPath = process.resourcesPath;

  console.log(`[Init] userData 경로: ${userDataPath}`);
  console.log(`[Init] resources 경로: ${resourcesPath}`);

  // 표준 코어 경계 술어 (core_manifest.json 기준) — 코어 어휘 산출물 강제 갱신용.
  // 번들(=배포 집합)에는 코어 소유 콘텐츠만 담기므로, 여기서 판정하는 대상은
  // 이미 코어다. 사용자가 자기 머신에서 더한 패키지/앱은 번들에 없어 이 동기화가
  // 아예 순회하지 않는다(=보존).
  const coreForceOverwrite = makeCoreForceOverwrite(resourcesPath);

  // 1. 기본 폴더들 - 무조건 덮어쓰기 (.db 파일만 보존)
  //    ★ packages 하위트리는 제외 — 설치 상태 보존을 위해 2에서 따로 처리.
  const dirsToSync = ['data', 'projects', 'templates', 'tokens'];
  const skipPaths = new Set([path.join(resourcesPath, 'data', 'packages')]);

  for (const dir of dirsToSync) {
    const src = path.join(resourcesPath, dir);
    const dest = path.join(userDataPath, dir);

    if (fs.existsSync(src)) {
      console.log(`[Init] 데이터 동기화: ${dir}`);
      syncDirOverwrite(src, dest, coreForceOverwrite, skipPaths);
    }
  }

  // 2. 패키지 동기화 - ★설치 상태(installed/not_installed 배치)를 사용자 소유로 보존
  //    (installed·not_installed 양쪽 카탈로그 갱신, 사용자의 활성/비활성 선택 불가침)
  syncPackagesPreservingState(resourcesPath, userDataPath, coreForceOverwrite);

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
    } catch (e) {
      // 파이프 에러 무시
    }
  });

  pythonProcess.stderr.on('data', (data) => {
    try {
      const msg = `[Python Error] ${data.toString().trim()}`;
      console.error(msg);
    } catch (e) {
      // 파이프 에러 무시
    }
  });

  pythonProcess.on('close', (code) => {
    const msg = `[Python] 프로세스 종료: ${code}`;
    console.log(msg);

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
      preload: path.join(__dirname, 'preload.js'),
      // 포식 브라우저(ForageBrowser) — 계기판 안에 진짜 크로미움을 박기 위한 <webview> 허용.
      // 외골격형 공동 포식의 '도로'. DOM 접근(executeJavaScript)이 나중에 AI '곁눈'이 붙을 이음매다.
      webviewTag: true
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

  // 포식 브라우저 <webview> 안에서 target=_blank / window.open 으로 뜨려는 새 창을 막고,
  // 같은 webview 안에서 그 URL 로 이동시킨다 — 별도 OS 창 대신 인플레이스(브라우저 안에서 열림).
  // (Electron 39 는 렌더러 'new-window' 이벤트가 제거돼 메인에서 guest webContents 로 처리해야 한다.)
  mainWindow.webContents.on('did-attach-webview', (_e, guest) => {
    guest.setWindowOpenHandler(({ url }) => {
      if (url && /^https?:\/\//i.test(url)) guest.loadURL(url);
      return { action: 'deny' };
    });

    // 크롬식 Ctrl(⌘) +/-/0 줌 — 페이지에 포커스가 있어도 먹도록 guest 에서 직접 잡는다(탭별 독립).
    guest.on('before-input-event', (event, input) => {
      if (input.type !== 'keyDown' || !(input.control || input.meta)) return;
      const k = input.key;
      if (k === '=' || k === '+') { guest.setZoomLevel(Math.min(guest.getZoomLevel() + 0.5, 5)); event.preventDefault(); }
      else if (k === '-' || k === '_') { guest.setZoomLevel(Math.max(guest.getZoomLevel() - 0.5, -3)); event.preventDefault(); }
      else if (k === '0') { guest.setZoomLevel(0); event.preventDefault(); }
    });
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // 우클릭 컨텍스트 메뉴 설정
  setupContextMenu(mainWindow);
}

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

/**
 * IPC 핸들러 등록
 */
function setupIPC() {
  // API 포트 정보
  ipcMain.handle('get-api-port', () => API_PORT);

  // 클립보드 읽기 — 메인 프로세스 경유. ★샌드박스 렌더러(Electron 20+ 기본)의 preload 엔
  // clipboard 모듈이 없어서 preload 직접 호출은 throw 한다 → IPC 가 유일하게 확실한 경로.
  ipcMain.handle('read-clipboard-text', () => clipboard.readText());

  // 외부 URL 열기
  ipcMain.handle('open-external', (_, url) => {
    shell.openExternal(url);
  });

  // 메시지 등의 URL 을 런처(메인 창)의 인앱 포식 브라우저 탭으로 연다.
  // 커뮤니티·메신저 등 별도 창에서 클릭해도 런처 창을 앞으로 세우고 그 안 브라우저에 띄운다.
  ipcMain.handle('open-in-launcher-browser', (_, url) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
      mainWindow.webContents.send('open-forage-url', url);
    } else {
      shell.openExternal(url);  // 런처 창이 없으면 외부 브라우저 폴백
    }
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

  // 시스템 AI 창 열기
  ipcMain.handle('open-system-ai-window', () => {
    createSystemAIWindow();
  });

  // 커뮤니티 창 열기 (옛 IndieNet 대체)
  ipcMain.handle('open-community-window', () => {
    createCommunityWindow();
  });

  // 메신저 창 열기 (옛 이웃관리·빠른 연락처 대체)
  ipcMain.handle('open-messenger-window', () => {
    createMessengerWindow();
  });

  // 다중채팅방 창 열기
  ipcMain.handle('open-multichat-window', (_, roomId, roomName) => {
    createMultiChatWindow(roomId, roomName);
  });

  // 강의 만들기 워크스페이스 창 열기
  ipcMain.handle('open-lecture-workspace-window', (_, lectureId) => {
    createLectureWorkspaceWindow(lectureId);
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

  // 런처 새로고침 요청 (프로젝트 창에서 스위치 생성/수정/삭제 시)
  ipcMain.handle('refresh-launcher', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('refresh-launcher');
      return true;
    }
    return false;
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
      title: '폴더 선택',
      buttonLabel: '선택'
    });

    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }

    return result.filePaths[0];
  });

  // ─── 포식 브라우저 비밀번호 금고 (safeStorage = OS 키체인) ───
  // 평문 비밀번호는 여기(main)와 renderer 사이 IPC 안에서만 흐른다. HTTP/백엔드로 안 나간다.
  ipcMain.handle('forage-pw-list-host', (_, url) => {
    try { return foragePw.listForHost(url); } catch { return []; }
  });
  ipcMain.handle('forage-pw-get', (_, url, username) => {
    try { return foragePw.getCredential(url, username ?? null); } catch { return null; }
  });
  ipcMain.handle('forage-pw-save', (_, origin, username, password) => {
    try { return foragePw.upsert(origin, username, password); }
    catch (e) { return { error: e.message }; }
  });
  ipcMain.handle('forage-pw-remove', (_, origin, username) => {
    try { return foragePw.remove(origin, username); } catch { return false; }
  });
  ipcMain.handle('forage-pw-list-all', () => {
    try { return foragePw.listAll(); } catch { return []; }
  });
  ipcMain.handle('forage-pw-import-chrome', () => {
    try { return foragePw.importFromChrome(); }
    catch (e) { return { error: e.message }; }
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

// ─── Launcher WS 브릿지 (메인 프로세스 상주) ───
let _launcherWS = null;
let _launcherReconnectTimer = null;

function startLauncherWS() {
  if (_launcherWS) return;

  try {
    _launcherWS = new WebSocket('ws://127.0.0.1:8765/ws/launcher');
  } catch (e) {
    console.log('[Launcher WS] WebSocket 생성 실패, 3초 후 재시도');
    _launcherReconnectTimer = setTimeout(startLauncherWS, 3000);
    return;
  }

  _launcherWS.onopen = () => {
    console.log('[Launcher WS] 메인 프로세스 연결됨');
  };

  _launcherWS.onmessage = (event) => {
    try {
      const data = JSON.parse(typeof event.data === 'string' ? event.data : event.data.toString());
      if (data.type === 'pong') return;

      if (data.type === 'launcher_command') {
        const { command, params } = data;
        console.log('[Launcher WS] 명령 수신:', command, params);

        switch (command) {
          case 'open_project_window':
            createProjectWindow(
              params?.project_id || '',
              params?.project_name || params?.project_id || '',
              params?.agent_name || ''
            );
            break;
          case 'open_system_ai_window':
            createSystemAIWindow();
            break;
          case 'open_messenger_window':
            // 메신저 창 (옛 이웃관리·빠른 연락처 → IBL 메신저 계기).
            createMessengerWindow();
            break;
          case 'open_community_window':
            // 커뮤니티 창 (옛 IndieNet — 공개 피드·게시판). 레거시 app:"indienet"도 여기로.
            createCommunityWindow();
            break;
          case 'open_business_window':
            createBusinessWindow();
            break;
          case 'open_multichat_window':
            createMultiChatWindow(
              params?.room_id || '',
              params?.room_name || ''
            );
            break;
          case 'open_folder_window':
            createFolderWindow(
              params?.folder_id || '',
              params?.folder_name || ''
            );
            break;
          case 'open_lecture_workspace':
            createLectureWorkspaceWindow(params?.lecture_id || null);
            break;
          default:
            console.warn('[Launcher WS] 알 수 없는 명령:', command);
        }
      }
    } catch (e) {
      console.error('[Launcher WS] 메시지 파싱 오류:', e);
    }
  };

  _launcherWS.onclose = () => {
    console.log('[Launcher WS] 연결 끊김, 3초 후 재연결...');
    _launcherWS = null;
    _launcherReconnectTimer = setTimeout(startLauncherWS, 3000);
  };

  _launcherWS.onerror = () => {
    // onclose에서 재연결 처리
  };

  // 30초마다 ping으로 연결 유지
  const pingInterval = setInterval(() => {
    if (_launcherWS?.readyState === WebSocket.OPEN) {
      _launcherWS.send(JSON.stringify({ type: 'ping' }));
    } else {
      clearInterval(pingInterval);
    }
  }, 30000);
}

// 앱 준비
app.whenReady().then(async () => {
  console.log('[Electron] 앱 시작');

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
    console.log('[Electron] Python 백엔드 시작 시도...');
    await startPythonBackend();
    console.log('[Electron] Python 백엔드 시작 완료');
  } catch (err) {
    console.error('[Electron] Python 백엔드 시작 실패:', err);
    dialog.showErrorBox(
      '백엔드 시작 오류',
      `Python 백엔드를 시작하는 중 오류가 발생했습니다.\n\n${err.message}`
    );
  }

  // 윈도우 생성
  createWindow();

  // Launcher WS 브릿지: 백엔드 → Electron 메인 프로세스 직접 연결
  // 메인 프로세스에서 유지하므로 어떤 창이 열려있든 항상 활성화
  startLauncherWS();

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
  // Launcher WS 정리
  if (_launcherReconnectTimer) clearTimeout(_launcherReconnectTimer);
  if (_launcherWS) {
    _launcherWS.onclose = null;
    _launcherWS.close();
    _launcherWS = null;
  }
  stopPythonBackend();
});

// 앱 종료
app.on('quit', () => {
  stopPythonBackend();
});
