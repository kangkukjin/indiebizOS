"""
notify_dispatch.py - 사용자 알림 전달 단일 관문 (A+B 조합, 2026-07-28)

목표: "어떤 OS든, 메신저 창을 안 띄워놔도, 백엔드만 살아 있으면 사용자가 알아차린다."

전달 순서:
  1) 알림함 기록 — notification_manager (조회용 이력)
  2) A. 런처 연결 시 — /ws/launcher 로 show_notification 명령
     → Electron 이 OS 네이티브 알림 + 배지 표시, 클릭하면 해당 창 열림 (크로스플랫폼)
  3) B. 런처 미연결 시 — desktop_notify 로 백엔드가 직접 OS 알림 (표시만, 클릭 연동 없음)

호출부: channel_poller(새 메시지), system_tools.execute_send_notification([self:notify_user]) 등.
워커 스레드에서 호출해도 안전하다 (send_launcher_command_sync 가 threadsafe 처리).
"""


def notify_user(title: str, body: str, kind: str = "info", source: str = "system",
                command: str = None, command_params: dict = None, badge: bool = True) -> bool:
    """사용자 알림 전달. 반환값 = 런처(Electron)로 전달됐는지 여부.

    Args:
        command: 알림 클릭 시 실행할 런처 명령 (예: "open_messenger_window"). 런처 경로에서만 유효.
        badge: 런처 배지 카운트 증가 여부 (독/트레이 미확인 표시)
    """
    # 1) 알림함 기록 (실패해도 전달은 계속)
    try:
        from notification_manager import get_notification_manager
        get_notification_manager().create(title=title, message=body, type=kind, source=source)
    except Exception as e:
        print(f"[알림] 알림함 기록 실패: {e}")

    # 2) A. Electron 런처 (연결돼 있으면 네이티브 알림 + 배지 + 클릭 연동)
    delivered = False
    try:
        from api_websocket import send_launcher_command_sync
        delivered = send_launcher_command_sync("show_notification", {
            "title": title,
            "body": body,
            "kind": kind,
            "command": command,
            "command_params": command_params or {},
            "badge": badge,
        })
    except Exception as e:
        print(f"[알림] 런처 전달 실패: {e}")
        delivered = False

    # 3) B. 폴백 — 백엔드가 직접 OS 네이티브 알림
    if not delivered:
        try:
            from desktop_notify import native_notify
            native_notify(title, body)
        except Exception as e:
            print(f"[알림] OS 알림 폴백 실패: {e}")

    return delivered


def notify_new_message(sender: str, subject: str, content: str, channel: str) -> bool:
    """메신저 새 메시지 알림 — 클릭하면 메신저 창이 열린다."""
    preview = " ".join((subject or content or "").split())
    if len(preview) > 80:
        preview = preview[:80] + "…"
    ch_label = {"email": "이메일", "nostr": "Nostr"}.get(channel, channel or "")
    title = f"💬 {sender}" + (f" ({ch_label})" if ch_label else "")
    return notify_user(title, preview or "(내용 없음)", kind="message", source="messenger",
                       command="open_messenger_window")
