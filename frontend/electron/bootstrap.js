/**
 * bootstrap.js — 설치본 유저데이터 초기화·패키지 동기화·우클릭 메뉴
 * (main.js 에서 분리, 2026-08-06 1500줄 규칙)
 *
 * 창·백엔드 프로세스 상태를 일절 건드리지 않는 준비 작업만 산다.
 */
import { app, Menu } from 'electron';
import path from 'path';
import fs from 'fs';
import net from 'net';

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

export { setupContextMenu, isPortAvailable, syncDirOverwrite, makeCoreForceOverwrite,
         syncPackagesPreservingState, initUserData };
