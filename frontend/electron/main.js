/**
 * Electron 메인 프로세스
 * 앱 생명주기·메인 창·IPC·트레이·런처 WebSocket
 *
 * 2026-08-06(1500줄 규칙) 분리: 유저데이터 준비=bootstrap.js / 백엔드 프로세스 생명주기=
 * backend-process.js / 보조 창 생성기=windows.js / 알림 배지=badge.js.
 * ★런처 창 명령 switch(handleLauncherCommand)는 이 파일에 남는다 — build --check 의
 * launcher-가드가 여기서 case 'open_*_window' 를 스캔해 좀비 창을 막는다.
 */

import { app, BrowserWindow, ipcMain, shell, dialog, Menu, clipboard, session, nativeImage, Notification, Tray } from 'electron';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import crypto from 'crypto';
import { Readable } from 'stream';
import { pipeline } from 'stream/promises';
import * as foragePw from './forage-passwords.js';

import { setupContextMenu } from './bootstrap.js';
import {
  startPythonBackend, getBasePath, ensureKeeper, fullSystemCleanup,
  suppressSystemCleanup,
} from './backend-process.js';
import {
  folderWindows,
  createProjectWindow, createFolderWindow, createSystemAIWindow,
  createBusinessWindow, createCommunityWindow, createMessengerWindow,
  createPCManagerWindow, createPhotoManagerWindow, createAndroidManagerWindow,
  createLectureWorkspaceWindow, createMultiChatWindow,
} from './windows.js';
import { setTray, bumpBadge } from './badge.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 개발 모드 확인
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

let mainWindow = null;
let tray = null; // 트레이 (win/linux — 실행 중 빠른 열기·종료 편의)

// API 포트
const API_PORT = 8765;

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

    // 웹뷰 안 우클릭 — 링크 위면 "내 창고에 리트윗"을 얹는다. 이웃 창고를 내부 브라우저로
    // 방문했을 때 파일 링크가 주 대상이지만, 어떤 웹 링크든 된다(포인터 .url = 어디든 가리킴).
    // 레벨·모드 선택과 실제 POST 는 렌더러(ForageBrowser)가 잇는다 — 여기선 신호만.
    guest.on('context-menu', (_event, params) => {
      const linkURL = params.linkURL || '';
      const template = [];
      if (/^https?:\/\//i.test(linkURL)) {
        template.push(
          {
            label: '내 창고에 리트윗…',
            click: () => mainWindow?.webContents.send('forage-retweet-link', {
              url: linkURL,
              text: (params.linkText || '').trim(),
            }),
          },
          { label: '링크 주소 복사', click: () => clipboard.writeText(linkURL) },
          { type: 'separator' },
        );
      }
      if (params.isEditable) template.push({ role: 'cut', label: '잘라내기' }, { role: 'paste', label: '붙여넣기' });
      if (params.selectionText) template.push({ role: 'copy', label: '복사' });
      template.push({ role: 'selectAll', label: '전체 선택' });
      Menu.buildFromTemplate(template).popup({ window: mainWindow });
    });
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // 우클릭 컨텍스트 메뉴 설정
  setupContextMenu(mainWindow);
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

  // ── 파일 드래그 아웃: 창 안의 파일을 창 밖(파인더·바탕화면)으로 끌어 저장 ──
  // HTML5 dnd 는 브라우저 밖으로 파일을 못 내보낸다 → 네이티브 startDrag 로 전환하는데,
  // startDrag 는 *로컬 파일*이 필요하다. 그래서 두 갈래다:
  //   path = 이미 이 컴퓨터에 있는 파일(내 사진 등) → 받지 않고 그대로 집는다.
  //   url  = 여기 없는 파일(이웃 창고·USB 폰 사진) → 받아서 임시폴더에 놓고 집는다.
  // 창고의 회원 레벨 파일은 익명 요청이면 404("no such file")라 포식 세션
  // (persist:forage — 창고 로그인 pk 쿠키가 산다)으로 받는다.
  // 캐시 키=url+mtime: 다운로드 중 버튼을 놓으면(렌더러가 cancel) 드래그는 접되 받은
  // 파일은 남겨 — 큰 파일도 두 번째 끌기는 즉시 집힌다.
  const dragOutDir = path.join(app.getPath('temp'), 'indiebiz-drag-out');
  let dragSeq = 0;          // 드래그 시도 일련번호
  let dragCancelledUpTo = 0; // 이 번호 이하의 시도는 취소됨(버튼을 놓았다 = 드래그 종료)
  app.on('will-quit', () => {  // 캐시는 세션 한정 — 종료 때 비워 임시폴더가 안 쌓이게
    try { fs.rmSync(dragOutDir, { recursive: true, force: true }); } catch { /* 무시 */ }
  });

  ipcMain.on('drag-out-file', async (event, payload) => {
    const token = ++dragSeq;
    try {
      const { url, path: localPath, paths, name, mtime } = payload || {};

      // 갈래 1 — 이미 이 컴퓨터에 있는 것: 복사도 다운로드도 없이 원본을 집는다.
      // paths=여러 개(창고 다중 선택), path=한 개. 폴더도 집는다(창고 폴더 통째 꺼내기).
      const wanted = Array.isArray(paths) && paths.length ? paths : (localPath ? [localPath] : []);
      const local = wanted.filter((p) => {
        try { return typeof p === 'string' && p && fs.existsSync(p); } catch { return false; }
      });
      if (local.length) {
        let icon0 = null;
        try { icon0 = await app.getFileIcon(local[0]); } catch { /* 아이콘 실패는 드래그를 안 막는다 */ }
        event.sender.startDrag({
          file: local[0],                                  // 구버전 호환 필드(둘 다 실어야 안전)
          files: local,
          icon: icon0 || nativeImage.createEmpty(),
        });
        return;
      }

      // 갈래 2 — 여기 없는 파일: 받아서 임시폴더에 놓고 집는다.
      if (!/^https?:\/\//.test(String(url || ''))) return;
      const safeName = String(name || '파일').replace(/[\\/:*?"<>|\x00-\x1f]/g, '_') || '파일';
      const key = crypto.createHash('md5').update(`${url}|${mtime || ''}`).digest('hex').slice(0, 16);
      const dest = path.join(dragOutDir, key, safeName);
      if (!(fs.existsSync(dest) && fs.statSync(dest).size > 0)) {
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        const ses = session.fromPartition('persist:forage');
        const res = await ses.fetch(url, { credentials: 'include' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const tmp = dest + '.part';
        await pipeline(Readable.fromWeb(res.body), fs.createWriteStream(tmp));
        fs.renameSync(tmp, dest); // 원자 교체 — 반쪽 파일이 캐시로 남지 않게
      }
      if (token <= dragCancelledUpTo) return; // 받는 동안 버튼을 놓았다 — 캐시만 남긴다
      let icon = null;
      try { icon = await app.getFileIcon(dest); } catch { /* 아이콘 실패는 드래그를 안 막는다 */ }
      event.sender.startDrag({ file: dest, icon: icon || nativeImage.createEmpty() });
    } catch (e) {
      console.error('[Electron] 드래그 아웃 실패:', e?.message || e);
    }
  });

  // 버튼을 놓았다 = 아직 안 시작한 드래그는 전부 접는다(시작된 건 OS 가 이미 가져감).
  ipcMain.on('drag-out-cancel', () => { dragCancelledUpTo = dragSeq; });

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

  // 임의 파일 선택 다이얼로그 (다중 선택, 확장자 무필터 — 공유창고 넣기)
  ipcMain.handle('select-files', async () => {
    const result = await dialog.showOpenDialog({
      // 폴더도 고를 수 있다 — 창고는 폴더를 구조 그대로 받는다(안의 파일이 각각 공개 항목).
      properties: ['openFile', 'openDirectory', 'multiSelections'],
      title: '파일 · 폴더 선택',
      buttonLabel: '선택'
    });
    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }
    return result.filePaths;
  });
}

// ─── 알림 · 트레이 (배지 카운트는 badge.js 가 소유) ───

function showNativeNotification(params = {}) {
  if (!Notification.isSupported()) return;
  try {
    const notif = new Notification({
      title: params.title || 'IndieBiz',
      body: params.body || ''
    });
    notif.on('click', () => {
      // 클릭 → 런처 명령과 같은 어휘로 창 열기 (예: open_messenger_window)
      if (params.command) {
        handleLauncherCommand(params.command, params.command_params || {});
      } else if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.show();
        mainWindow.focus();
      }
    });
    notif.show();
  } catch (e) {
    console.error('[알림] 네이티브 알림 실패:', e);
  }
  if (params.badge !== false) bumpBadge();
}

// 트레이 아이콘 (내장 32px PNG — 별도 자산 없이 자립)
const TRAY_ICON_DATA_URL = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAqUlEQVR4nO2XQQ6EIAxFPz+eQ9d6hZnjj1fQtV5EV2Mao6AorQn+FW2avk9JCAC5y4UKyvozXQGMfetluFTgo0aoAff1pAbc15ta8D0GYSxq7n6LRRiLrwHkbqAIFQzdb1lXzTc6HzWBQTST8dl8tAEN8dEGqtUZ/uOzeZ+cxVUs3weEsfgawFMMjIHX652SLMJYlIHGFNYMhgpSwjcNpDKx19NZf82QvWbq9ks3SZ7+MAAAAABJRU5ErkJggg==';

function createTray() {
  // win/linux — 실행 중 빠른 열기·종료 편의용. ★상주 목적 폐지(2026-08-05 사용자 확정:
  // "창을 닫으면 백엔드도 죽는다" — window-all-closed 가 전 플랫폼 전체 종료를 부른다).
  if (tray || process.platform === 'darwin') return;
  try {
    const icon = nativeImage.createFromDataURL(TRAY_ICON_DATA_URL);
    tray = new Tray(icon);
    tray.setToolTip('IndieBiz OS');
    tray.setContextMenu(Menu.buildFromTemplate([
      { label: '열기', click: () => showMainWindow() },
      { type: 'separator' },
      { label: '종료', click: () => app.quit() }
    ]));
    tray.on('click', () => showMainWindow());
    setTray(tray);  // 배지 툴팁 갱신용 참조 주입
  } catch (e) {
    console.error('[트레이] 생성 실패:', e);
    tray = null;
    setTray(null);
  }
}

function showMainWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show();
    mainWindow.focus();
  } else {
    createWindow();
  }
}

// ─── Launcher WS 브릿지 (메인 프로세스 상주) ───
let _launcherWS = null;
let _launcherReconnectTimer = null;

function handleLauncherCommand(command, params) {
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
    case 'show_notification':
      // 백엔드 발신 사용자 알림 (새 메시지·notify_user 등) → OS 네이티브 알림 + 배지
      showNativeNotification(params || {});
      break;
    default:
      console.warn('[Launcher WS] 알 수 없는 명령:', command);
  }
}

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
        handleLauncherCommand(command, params);
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

// 단일 인스턴스 — 아이콘 더블클릭 중복 실행 방지 (둘째 인스턴스는 즉시 종료,
// 첫 인스턴스가 second-instance 이벤트로 창을 앞으로 가져온다)
// ★둘째 인스턴스의 quit 이 fullSystemCleanup 을 부르면 *첫 인스턴스의* 백엔드를
// 죽인다 — _systemCleaned 를 미리 잠가 정리를 무력화한 채 조용히 물러난다.
const _gotSingleLock = app.requestSingleInstanceLock();
if (!_gotSingleLock) {
  suppressSystemCleanup();  // 정리 금지 — 시스템은 첫 인스턴스의 것
  app.quit();
} else {
  app.on('second-instance', () => {
    showMainWindow();
  });
}

// 앱 준비
app.whenReady().then(async () => {
  console.log('[Electron] 앱 시작');

  // Windows 토스트 알림 발신자 식별 (electron-builder appId와 동일)
  if (process.platform === 'win32') {
    app.setAppUserModelId('com.indiebiz.app');
  }

  // win/linux 트레이 상주 — 창을 다 닫아도 백엔드·수신·알림 유지
  createTray();

  // ── 창고 자격 캡처: 포식 브라우저(persist:forage)에서 창고 가입/로그인 POST 를 관찰해
  //    아이디·비밀번호를 백엔드 창고 자격 저장소로 흘린다 — 다음 방문의 로그인 상태는
  //    이 세션의 pk 쿠키(1년)가, 시스템 탐색은 폴러가 이 자격으로 맡는다.
  //    범위=루트 /login·/join(창고 계약 경로)만. 백엔드가 실로그인으로 '정말 창고인지'
  //    검증하므로 일반 사이트의 우연한 일치는 저장되지 않는다. ★일반 사이트 비밀번호
  //    금고(forage-passwords, 평문은 백엔드로 안 나감)와 별개 축 — 창고 자격은 폴러가
  //    서버측 로그인에 써야 해서 백엔드 저장이 승인된 예외(🔑 수동 등록과 같은 저장소).
  try {
    const forage = session.fromPartition('persist:forage');
    forage.webRequest.onBeforeRequest(
      { urls: ['*://*/login', '*://*/join'] },
      (details, cb) => {
        cb({});
        try {
          if (details.method !== 'POST' || !details.uploadData?.length) return;
          const raw = Buffer.concat(
            details.uploadData.map((d) => d.bytes).filter(Boolean)
          ).toString('utf8');
          const body = JSON.parse(raw);
          const userId = String(body.user_id || '').trim();
          const password = String(body.password || '');
          if (!userId || !password) return;
          const origin = new URL(details.url).origin;
          if (/^https?:\/\/(127\.0\.0\.1|localhost)(:|$)/.test(origin)) return; // 자기 백엔드 제외
          fetch('http://127.0.0.1:8765/warehouse-feed/capture', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: origin, user_id: userId, password }),
          }).catch(() => {});
          // 포식 금고에도 — 로그아웃 후 재로그인 때 자동 채움이 되도록 (host 단위)
          try { foragePw.upsert(origin, userId, password); } catch { /* 키체인 불가 등 — 무시 */ }
        } catch { /* 캡처 실패는 조용히 — 탐색을 막지 않는다 */ }
      }
    );
  } catch (e) {
    console.error('[Electron] 창고 자격 캡처 배선 실패:', e);
  }

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

  // 의도 표식 제거 — 시스템이 다시 살아났다 (수리 워치독·keeper 정상 작동 재개)
  try {
    const marker = path.join(getBasePath(), 'data', '.intentional_shutdown');
    if (fs.existsSync(marker)) fs.unlinkSync(marker);
  } catch (e) { /* 무시 */ }

  // Python 백엔드 시작
  try {
    console.log('[Electron] Python 백엔드 시작 시도...');
    await startPythonBackend();
    console.log('[Electron] Python 백엔드 시작 완료');
    ensureKeeper();  // 앱이 떠 있는 동안 백엔드 크래시 자동 소생 (종료 시 함께 정리)
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

// 모든 윈도우 닫힘 = 시스템 종료 (전 플랫폼 — 사용자 확정 2026-08-05: 창=시스템 손잡이.
// "창을 닫으면 백엔드도 죽는다. 시스템이 꺼지면 다 정리하고 죽는다, 뭘 남기지 말고.")
// macOS 독 상주·win/linux 트레이 상주 폐지. 시스템을 계속 살리려면 창을 닫지 말고
// 최소화(또는 macOS Cmd+H 숨기기)한다.
app.on('window-all-closed', () => {
  app.quit();
});

// 앱 종료 전 — 전체 정리(keeper→백엔드 그룹→잔여 소탕: start.sh가 띄운 것·유령·터널)
app.on('before-quit', () => {
  // Launcher WS 정리
  if (_launcherReconnectTimer) clearTimeout(_launcherReconnectTimer);
  if (_launcherWS) {
    _launcherWS.onclose = null;
    _launcherWS.close();
    _launcherWS = null;
  }
  fullSystemCleanup();
});

// 앱 종료 (백스톱 — fullSystemCleanup 은 멱등)
app.on('quit', () => {
  fullSystemCleanup();
});
