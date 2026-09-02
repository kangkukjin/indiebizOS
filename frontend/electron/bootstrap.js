/**
 * bootstrap.js — 설치본 유저데이터 초기화·우클릭 메뉴
 * (main.js 에서 분리, 2026-08-06 1500줄 규칙 · 동기화 본체는 userdata_sync.js 로 2026-09-02)
 *
 * 창·백엔드 프로세스 상태를 일절 건드리지 않는 준비 작업만 산다.
 */
import { app, Menu } from 'electron';
import path from 'path';
import fs from 'fs';
import net from 'net';
import { syncUserData } from './userdata_sync.js';

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
 * 프로덕션 데이터 디렉토리 초기화
 * 앱 번들(resources/) 내의 데이터를 사용자 폴더(userData)로 동기화.
 * 실제 동기화는 userdata_sync.js(electron 무의존, 저널 트랜잭션·은퇴 격리) — 2026-09-02.
 *  - 코어 소유 파일만 갱신, 사용자 것(.db·설정 json·미추적 패키지·자작 앱) 불가침
 *  - 패키지는 설치 상태(폴더 배치) 보존
 *  - 도중에 죽으면 다음 기동이 저널로 되감는다(data/.upgrade_pending)
 */
let _userDataReady = null;   // 프로세스당 1회 — getBasePath() 가 여러 자리에서 부른다(종료 정리 포함)
function initUserData() {
  if (_userDataReady) return _userDataReady;
  const userDataPath = app.getPath('userData'); // Windows: %APPDATA%/IndieBiz, macOS: ~/Library/Application Support/IndieBiz
  const resourcesPath = process.resourcesPath;

  console.log(`[Init] userData 경로: ${userDataPath}`);
  console.log(`[Init] resources 경로: ${resourcesPath}`);

  syncUserData({ resourcesPath, userDataPath, version: app.getVersion(), log: console.log });
  _userDataReady = userDataPath;
  return userDataPath;
}

export { setupContextMenu, isPortAvailable, initUserData };
