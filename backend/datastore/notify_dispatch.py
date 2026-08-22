"""
notify_dispatch.py - 사용자 알림 전달 단일 관문 (A+B 조합, 2026-07-28)

목표: "어떤 OS든, 메신저 창을 안 띄워놔도, 백엔드만 살아 있으면 사용자가 알아차린다."

전달 순서:
  1) 알림함 기록 — notification_manager (조회용 이력)
  2) A. 런처 연결 시 — /ws/launcher 로 show_notification 명령
     → Electron 이 OS 네이티브 알림 + 배지 표시, 클릭하면 해당 창 열림 (크로스플랫폼)
  3) B. 런처 미연결 시 — desktop_notify 로 백엔드가 직접 OS 알림 (표시만, 클릭 연동 없음)

※C(웹푸시, 다른 기기 도달)는 2026-08-01 시도 후 같은 날 은퇴 — 같은 origin 다중 PWA
(런처·IBFind)의 안드로이드 알림 위임 얽힘으로 실기기 도달 실패(사용자 결정: 반복 안 함).
재활 조건 = 런처 서브도메인 분리. 당시 코드는 커밋 이력 없이 제거(RFC 8291 직접 구현은
CLAUDE.md 2026-08-01 항목에 기록).

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
    # 1) 알림함 기록. deliver=False — 전달은 아래에서 command/badge 까지 실어
    #    한 번만 한다(create 안의 전달과 이중이 되지 않게).
    try:
        from notification_manager import get_notification_manager
        get_notification_manager().create(title=title, message=body, type=kind,
                                          source=source, deliver=False)
    except Exception as e:
        print(f"[알림] 알림함 기록 실패: {e}")

    # 2) 전달 (기록 실패와 무관하게 계속)
    return deliver_notification(title, body, kind, command, command_params, badge)


def deliver_notification(title: str, body: str, kind: str = "info",
                         command: str = None, command_params: dict = None,
                         badge: bool = True) -> bool:
    """전달만 — 알림함 기록 없이 런처 푸시(A) → 실패 시 OS 네이티브(B).

    ★2026-08-22 분리: notification_manager.create() 가 기록 직후 이 함수를 부른다.
    그래서 **어느 입구로 들어온 알림이든** 사용자에게 닿는다 — '관문을 지나라'는
    규약을 문서가 아니라 구조가 강제한다(옛 규약은 호출처 18곳 중 17곳이 어겼고,
    그 알림들은 알림함에만 쌓인 채 조용히 유실됐다).
    """
    # A. Electron 런처 (연결돼 있으면 네이티브 알림 + 배지 + 클릭 연동)
    delivered = False
    try:
        from websocket_manager import send_launcher_command_sync
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

    # B. 폴백 — 백엔드가 직접 OS 네이티브 알림
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
