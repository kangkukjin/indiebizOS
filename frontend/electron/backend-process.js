/**
 * backend-process.js — 단일 재기동 제어자의 시작·의도적 종료 입구
 * (main.js 에서 분리, 2026-08-06 1500줄 규칙)
 *
 * 창=시스템 손잡이: 창을 다 닫으면 fullSystemCleanup 이 종료 의도를 기록하고
 * 제어자의 소유 프로세스 정리가 끝나기를 기다린다.
 */
import { app, dialog } from 'electron';
import { spawn, execFileSync } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

import { initUserData } from './bootstrap.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
const API_PORT = Number(process.env.INDIEBIZ_API_PORT || 8765);

// 이 창이 시작한 제어자 프로세스와 공통 요청 명령. 워커 상태는 제어자가 소유한다.
let pythonProcess = null;
let backendCommand = null;

/**
 * Python 백엔드 시작
 */
async function startPythonBackend() {
  // 경로 설정
  let backendPath;
  let pythonPath;
  let pythonArgs;
  let basePath; // 데이터가 저장될 기본 경로

  if (isDev) {
    // 개발 모드: 상대 경로
    backendPath = path.join(__dirname, '..', '..', 'backend');
    basePath = path.join(__dirname, '..', '..'); // indiebizOS root
    // 소스 경로의 몸은 .venv 하나로 고정 (start.sh·backend_keeper.sh 와 동일 규칙,
    // 2026-08-22). 조용히 시스템 파이썬으로 떨어지면 "다른 몸으로 도는데 아무도
    // 모르는" 상태가 된다 — playwright 처럼 버전이 다르게 깔린 의존은 시끄럽게
    // 죽지도 않고 반쪽으로 돈다.
    const venvPy = process.platform === 'win32'
      ? path.join(basePath, '.venv', 'Scripts', 'python.exe')
      : path.join(basePath, '.venv', 'bin', 'python3');
    if (fs.existsSync(venvPy)) {
      pythonPath = venvPy;
    } else if (process.platform === 'win32') {
      // 윈도우 개발 환경은 아직 실측되지 않았다 — 막지 않되 조용히 넘어가지도 않는다.
      console.warn(`[Python] ⚠️ .venv 없음(${venvPy}) — 시스템 파이썬으로 뜹니다. ` +
                   `의존성 버전이 저장소와 어긋날 수 있습니다: python scripts/bootstrap.py`);
      pythonPath = 'python';
    } else {
      throw new Error(
        `.venv 가 없습니다 (${venvPy}) — 소스 경로는 저장소 가상환경 하나로 고정입니다.\n` +
        `  python3 scripts/bootstrap.py   # venv + 의존성 + .env 시드`
      );
    }
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

  // 백엔드 stdout → 파일 (2026-08-05 시작방식 개편: 아이콘 실행 = 터미널 없음.
  // 에피소드 메모리가 못 담는 로그 — 부팅 에러·백그라운드 서비스·500 traceback —
  // 를 여기 남기고, 조종실 '시스템 로그' 뷰어(/config/system-logs)가 읽는다.)
  const runtimeLogPath = path.join(basePath, 'data', 'backend_runtime.log');
  let backendLog = null;
  try {
    fs.mkdirSync(path.dirname(runtimeLogPath), { recursive: true });
    if (fs.existsSync(runtimeLogPath) && fs.statSync(runtimeLogPath).size > 50 * 1024 * 1024) {
      fs.renameSync(runtimeLogPath, runtimeLogPath + '.old');  // 50MB 회전
    }
    backendLog = fs.createWriteStream(runtimeLogPath, { flags: 'a' });
    backendLog.write(`\n===== [${new Date().toISOString()}] 백엔드 기동 (Electron) =====\n`);
  } catch (e) {
    console.warn('[Python] 런타임 로그 파일 열기 실패:', e.message);
  }

  // 창과 분리된 제어자가 워커의 죽음을 넘어 정리·복구를 완료한다.
  backendCommand = { pythonPath, pythonArgs, backendPath, basePath };
  pythonProcess = spawn(pythonPath, pythonArgs, {
    cwd: backendPath,
    detached: process.platform !== 'win32',
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
      if (backendLog) backendLog.write(data);
    } catch (e) {
      // 파이프 에러 무시
    }
  });

  pythonProcess.stderr.on('data', (data) => {
    try {
      const msg = `[Python Error] ${data.toString().trim()}`;
      console.error(msg);
      if (backendLog) backendLog.write(data);
    } catch (e) {
      // 파이프 에러 무시
    }
  });

  pythonProcess.on('close', (code) => {
    const msg = `[Python] 프로세스 종료: ${code}`;
    console.log(msg);
    try {
      if (backendLog) { backendLog.write(`===== 백엔드 종료 (code=${code}) =====\n`); backendLog.end(); backendLog = null; }
    } catch (e) { /* 무시 */ }

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
  if (!await waitForServer()) {
    throw new Error("백엔드 실행 준비를 확인하지 못했습니다. 재기동 제어 상태와 시스템 로그를 확인하세요.");
  }
}

/**
 * 서버 준비 대기
 */
async function waitForServer(timeoutMs = 330000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const state = JSON.parse(fs.readFileSync(path.join(getBasePath(), 'data', 'restart_control', 'state.json'), 'utf8'));
      if (state.phase === 'FAILED') return false;
      const response = await fetch(`http://127.0.0.1:${API_PORT}/runtime/status`, {
        headers: { 'X-Runtime-Control': state.control_token },
        signal: AbortSignal.timeout(2000)
      });
      const status = response.ok ? await response.json() : {};
      if (status.generation === state.generation && status.code_digest === state.code_digest &&
          status.accepting && ['ready', 'degraded'].includes(status.readiness)) {
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
  // 종료 요청을 보낸 프로세스가 죽어도 의도와 정리 절차는 제어자가 소유한다.
  const command = backendCommand;
  if (!command) return;
  execFileSync(command.pythonPath, [...command.pythonArgs, 'shutdown', '--wait'], {
    cwd: command.backendPath,
    env: { ...process.env, INDIEBIZ_BASE_PATH: command.basePath },
    timeout: 45000,
    stdio: 'pipe'
  });
  pythonProcess = null;
}

/**
 * 데이터 기본 경로 (백엔드 미스폰 시에도 필요 — keeper·로그·정리)
 */
function getBasePath() {
  return isDev ? path.join(__dirname, '..', '..') : initUserData();
}

/**
 * 기존 호출부 호환. 감독은 startPythonBackend가 시작한 제어자가 맡는다.
 */
function ensureKeeper() {
  // startPythonBackend가 동일 제어자를 시작한다. 경쟁 감시 데몬을 추가하지 않는다.
}

/**
 * 종료 의도를 먼저 내구 기록하고 제어자가 실제 종료를 확인할 때까지 기다린다.
 */
let _systemCleaned = false;
function fullSystemCleanup() {
  if (_systemCleaned) return;
  _systemCleaned = true;
  console.log('[Electron] 시스템 전체 정리 시작');
  const basePath = getBasePath();
  try {
    fs.mkdirSync(path.join(basePath, 'data'), { recursive: true });
    const marker = path.join(basePath, 'data', '.intentional_shutdown');
    const temporary = marker + '.' + process.pid + '.tmp';
    const fd = fs.openSync(temporary, 'w', 0o600);
    try {
      fs.writeFileSync(fd, new Date().toISOString());
      fs.fsyncSync(fd);
    } finally { fs.closeSync(fd); }
    fs.renameSync(temporary, marker);
    if (process.platform !== 'win32') {
      const directory = fs.openSync(path.dirname(marker), 'r');
      try { fs.fsyncSync(directory); } finally { fs.closeSync(directory); }
    }
    stopPythonBackend();
    console.log('[Electron] 시스템 전체 정리 완료');
  } catch (e) {
    console.error('[Electron] 제어자 종료 확인 실패:', e.message);
    // 의도 표식은 남는다. 재개된 제어자는 새 현역을 띄우기 전에 종료를 완수한다.
  }
}

/**
 * 시스템 정리를 미리 잠근다 — 둘째 인스턴스가 quit 할 때 *첫 인스턴스의* 백엔드를
 * 죽이지 않게(단일 인스턴스 잠금 실패 경로에서 main.js 가 부른다).
 */
function suppressSystemCleanup() { _systemCleaned = true; }

export { suppressSystemCleanup };

export { startPythonBackend, waitForServer, stopPythonBackend, getBasePath,
         ensureKeeper, fullSystemCleanup };
