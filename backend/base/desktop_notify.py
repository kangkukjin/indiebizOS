"""
desktop_notify.py - 백엔드가 직접 띄우는 OS 네이티브 데스크탑 알림 (Electron 폴백)

런처(Electron)가 안 떠 있어도 백엔드만 살아 있으면 데스크탑 알림이 보이게 한다.
notify_dispatch 가 런처 WS 미연결일 때만 이 경로로 폴백한다.

의존성 없이 OS 표준 도구만 사용:
  - macOS: osascript display notification
  - Windows: PowerShell + WinRT 토스트
  - Linux: notify-send (libnotify)

클릭 연동은 없다(순수 표시) — 클릭→창 열기는 Electron 경로(show_notification)가 담당.
도구가 없거나 실패하면 조용히 무시한다(알림은 최선노력, 본 작업을 막지 않는다).
"""

import subprocess
import sys
import threading

# 윈도우 콘솔 창 깜빡임 방지 플래그 (CREATE_NO_WINDOW)
_WIN_NO_WINDOW = 0x08000000

# WinRT 토스트 — Win10/11 표준, 외부 모듈 불요. {title}/{body}는 PS 단일따옴표 이스케이프 후 치환.
_WIN_TOAST_PS = (
    "$null=[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime];"
    "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
    "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
    "$x=$t.GetElementsByTagName('text');"
    "$null=$x.Item(0).AppendChild($t.CreateTextNode('{title}'));"
    "$null=$x.Item(1).AppendChild($t.CreateTextNode('{body}'));"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
    "'IndieBiz OS').Show([Windows.UI.Notifications.ToastNotification]::new($t));"
)


def _osa_str(s: str) -> str:
    """AppleScript 문자열 리터럴 이스케이프"""
    return '"' + (s or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ps_str(s: str) -> str:
    """PowerShell 단일따옴표 리터럴 이스케이프"""
    return (s or "").replace("'", "''")


def _notify_blocking(title: str, body: str):
    try:
        if sys.platform == "darwin":
            script = f"display notification {_osa_str(body)} with title {_osa_str(title)}"
            subprocess.run(["osascript", "-e", script], timeout=10, capture_output=True)
        elif sys.platform.startswith("win"):
            ps = _WIN_TOAST_PS.replace("{title}", _ps_str(title)).replace("{body}", _ps_str(body))
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                timeout=15, capture_output=True, creationflags=_WIN_NO_WINDOW,
            )
        else:
            # Linux 데스크탑 (안드로이드 폰 몸에선 notify-send 부재 → FileNotFoundError → 조용히 무시)
            subprocess.run(["notify-send", title or "IndieBiz", body or ""],
                           timeout=10, capture_output=True)
    except Exception:
        pass  # 알림 실패는 본 작업을 막지 않는다


def native_notify(title: str, body: str) -> None:
    """OS 네이티브 알림 발사 (fire-and-forget, 논블로킹)"""
    threading.Thread(target=_notify_blocking, args=(title, body),
                     daemon=True, name="desktop-notify").start()
