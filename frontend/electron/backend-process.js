/**
 * backend-process.js — 파이썬 백엔드 프로세스 생명주기 + keeper + 시스템 전체 정리
 * (main.js 에서 분리, 2026-08-06 1500줄 규칙)
 *
 * 창=시스템 손잡이(2026-08-05 개편): 창을 다 닫으면 fullSystemCleanup 이 백엔드·keeper·
 * 터널까지 정리한다. pythonProcess 전역이 곧 그 상태라 이 모듈이 통째로 소유한다.
 */
import { app, dialog } from 'electron';
import { spawn, execSync } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

import { initUserData, isPortAvailable } from './bootstrap.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
const API_PORT = 8765;

// Python 프로세스 — 이 전역이 곧 백엔드 상태다.
let pythonProcess = null;

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
    // 저장소 가상환경 우선 — 시스템 파이썬엔 fastapi 등이 없다 (start.sh 와 동일 규칙)
    const venvPy = path.join(basePath, '.venv', 'bin', 'python3');
    if (process.platform !== 'win32' && fs.existsSync(venvPy)) {
      pythonPath = venvPy;
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

  // Python 프로세스 시작 — detached=자기 프로세스 그룹 (uvicorn 워커·multiprocessing
  // 자식까지 그룹 킬로 한 번에 정리하기 위함. "시스템이 꺼지면 다 정리하고 죽는다")
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
      // detached 스폰이라 자기 프로세스 그룹 — 그룹 킬로 uvicorn 워커·
      // multiprocessing 자식까지 한 번에 (음수 pid = 그룹).
      // ★SIGTERM 만으론 uvicorn 우아한 종료가 30초+ 끌린다(실측) — 2초 유예 후
      // SIGKILL 추격으로 "즉시 깨끗이"를 보장한다. (절대경로 스폰이라 잔여 소탕의
      // "python3 api.py" 패턴에 안 걸리므로 여기서 확정해야 한다.)
      const gpid = pythonProcess.pid;
      try {
        process.kill(-gpid, 'SIGTERM');
      } catch (e) {
        try { pythonProcess.kill('SIGTERM'); } catch (e2) { /* 이미 죽음 */ }
      }
      try { execSync('sleep 2'); } catch (e) { /* 무시 */ }
      try { process.kill(-gpid, 'SIGKILL'); } catch (e) { /* 이미 죽음 — 정상 */ }
    }
    pythonProcess = null;
  }
}

/**
 * 데이터 기본 경로 (백엔드 미스폰 시에도 필요 — keeper·로그·정리)
 */
function getBasePath() {
  return isDev ? path.join(__dirname, '..', '..') : initUserData();
}

/**
 * 감독 데몬(keeper) 보장 — 앱이 떠 있는 동안 백엔드가 죽으면 1분 내 재기동.
 * 멱등(스크립트가 pid 파일로 중복 방지). 종료 시 fullSystemCleanup 이 keeper 부터 죽인다.
 */
function ensureKeeper() {
  if (process.platform === 'win32') return;  // bash 스크립트 — 윈도우는 후속
  try {
    const script = path.join(getBasePath(), 'scripts', 'backend_keeper.sh');
    if (!fs.existsSync(script)) return;
    const kp = spawn('bash', [script], { detached: true, stdio: 'ignore' });
    kp.unref();
    console.log('[Electron] keeper 보장');
  } catch (e) {
    console.warn('[Electron] keeper 기동 실패 (무시):', e.message);
  }
}

/**
 * 시스템 전체 정리 — "시스템이 꺼지면 다 정리하고 죽는다. 뭘 남기지 말고."
 * (사용자 확정 2026-08-05. 옛 start.sh trap cleanup 의 Electron 이식판.)
 * 순서가 중요: ①keeper 먼저(안 그러면 죽인 백엔드를 1분 내 부활시킨다)
 * ②내가 스폰한 백엔드 그룹 ③잔여 소탕(start.sh 가 띄운 백엔드·유령 워커·터널).
 * "cloudflared tunnel run" 패턴은 원격관리 터널(--config 낀 명령)과 안 겹친다(07-20 검증).
 */
let _systemCleaned = false;
function fullSystemCleanup() {
  if (_systemCleaned) return;
  _systemCleaned = true;
  console.log('[Electron] 시스템 전체 정리 시작');
  const basePath = getBasePath();
  // 0) 의도 표식 — 수리 워치독(red_watchdog)·keeper 가 "의도된 종료"임을 알게 한다.
  //    없으면 워치독이 죽은 /health 를 보고 방금 한 정상 수리를 오판 롤백한다(충돌 봉합 08-05).
  //    다음 시작(whenReady)이 표식을 지운다.
  try {
    fs.writeFileSync(path.join(basePath, 'data', '.intentional_shutdown'),
                     new Date().toISOString());
  } catch (e) { /* 무시 */ }
  // 1) keeper
  try {
    const pidf = path.join(basePath, 'data', 'backend_keeper.pid');
    if (fs.existsSync(pidf)) {
      const kpid = parseInt(fs.readFileSync(pidf, 'utf-8').trim(), 10);
      if (kpid) { try { process.kill(kpid, 'SIGKILL'); } catch (e) { /* 이미 없음 */ } }
      fs.unlinkSync(pidf);
    }
  } catch (e) { /* 무시 */ }
  if (process.platform !== 'win32') {
    try { execSync('pkill -f "scripts/backend_keepe[r].sh" 2>/dev/null; true', { shell: '/bin/bash' }); } catch (e) { /* 무시 */ }
  }
  // 2) 내가 스폰한 백엔드 그룹
  stopPythonBackend();
  // 3) 잔여 소탕
  try {
    if (process.platform === 'win32') {
      execSync(
        `powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort ${API_PORT} -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { taskkill /F /T /PID $_ }"`,
        { timeout: 15000 });
    } else {
      // ★진범 봉합(08-05): 아이콘 PATH 에 /usr/sbin 없음→lsof 폴백 / pkill -f 자기셸 매칭→브래킷 트릭.
      execSync(
        `$(command -v lsof || echo /usr/sbin/lsof) -ti :${API_PORT} -sTCP:LISTEN | xargs kill -9 2>/dev/null; ` +
        'pkill -9 -f "(python3|Python) ap[i].py" 2>/dev/null; ' +
        'pkill -f "cloudflared tunnel ru[n]" 2>/dev/null; true',
        { shell: '/bin/bash', timeout: 15000 });
    }
  } catch (e) { /* 무시 */ }
  console.log('[Electron] 시스템 전체 정리 완료');
}

/**
 * 시스템 정리를 미리 잠근다 — 둘째 인스턴스가 quit 할 때 *첫 인스턴스의* 백엔드를
 * 죽이지 않게(단일 인스턴스 잠금 실패 경로에서 main.js 가 부른다).
 */
function suppressSystemCleanup() { _systemCleaned = true; }

export { suppressSystemCleanup };

export { startPythonBackend, waitForServer, stopPythonBackend, getBasePath,
         ensureKeeper, fullSystemCleanup };
