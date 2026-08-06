/**
 * badge.js — 미확인 알림 배지 상태 (main.js 에서 분리, 2026-08-06 1500줄 규칙)
 *
 * 이 작은 모듈이 따로 있는 이유: 창 생성기(windows.js)가 메신저 창 포커스에서
 * clearBadge 를 부르는데 배지가 main.js 에 있으면 main→windows→main 순환이 된다.
 * 배지 카운트가 곧 상태라 소유자는 하나여야 한다(트레이 참조는 setTray 로 주입).
 */
import { app } from 'electron';

let _badgeCount = 0;
let _tray = null;

function setTray(tray) { _tray = tray; }

function updateBadge() {
  // macOS 독 / Linux(Unity) 배지 — 미지원 플랫폼은 조용히 무시
  try { app.setBadgeCount(_badgeCount); } catch { /* 미지원 */ }
  if (_tray) {
    try { _tray.setToolTip(_badgeCount > 0 ? `IndieBiz — 새 알림 ${_badgeCount}건` : 'IndieBiz OS'); } catch { /* 무시 */ }
  }
}

function bumpBadge(n = 1) { _badgeCount += n; updateBadge(); }

function clearBadge() {
  if (_badgeCount === 0) return;
  _badgeCount = 0;
  updateBadge();
}

export { setTray, updateBadge, bumpBadge, clearBadge };
