"""알림 제목 파생 회귀 — 빈 제목이 알림함에 빈칸으로 남지 않는가 (2026-08-22, F20-5 판정).

판정: `title` 을 **필수로 만드는 안은 기각**했다 — 부르는 쪽(모델 포함)이 message 를
title 에 그대로 복붙하고(형식만 채운 중복 토큰), `[self:notify_user]{message:}` 로 이미
쓰인 문장·코퍼스도 깨진다. 대신 message 앞머리를 제목으로 승격한다.

핵심은 **파생이 일어나는 자리**다: 알림 입구는 18곳이고 액션 쪽에서 고치면 나머지
우회 호출처는 여전히 빈 제목이다. 그래서 파생은 관문 `notification_manager.create()`
한 곳에만 있고, 전달(notify_dispatch)은 기록된 제목을 **되읽는다**(둘이 갈리면
알림함과 OS 알림의 제목이 달라진다). 여기서 지키는 불변식이 그것이다.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.abspath(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
    import boot_paths  # noqa: F401 — 층 디렉토리 등재

from notification_manager import NotificationManager, derive_title  # noqa: E402


# ───────── 파생 규칙 ─────────

def test_first_line_becomes_the_title():
    assert derive_title("스케줄 실행 완료\n수집 3건 · 실패 0") == "스케줄 실행 완료"


def test_short_message_is_used_whole():
    assert derive_title("백업이 끝났습니다") == "백업이 끝났습니다"


def test_punctuation_is_not_a_cut_point():
    """문장 부호로 자르면 '3.5% 올랐습니다' 가 소수점에서 잘린다 — 규칙 하나만 쓴다."""
    assert derive_title("3.5% 올랐습니다") == "3.5% 올랐습니다"


def test_long_line_is_marked_when_cut():
    long_line = "아주 긴 한 줄 알림입니다 " * 8
    t = derive_title(long_line)
    assert t.endswith("…") and len(t) <= 41, t


def test_empty_message_still_has_a_title():
    assert derive_title("") == "알림" and derive_title("   \n  ") == "알림"


# ───────── 파생 자리(관문) ─────────

def test_gate_derives_for_every_entry():
    """관문을 지나기만 하면 어느 입구든 제목이 생긴다 — 우회 호출처 14곳의 수리."""
    nm = NotificationManager()
    rec = nm.create(title="", message="자가점검 경고 — 응답 없는 손발 2개", deliver=False)
    assert rec["title"] == "자가점검 경고 — 응답 없는 손발 2개"


def test_explicit_title_is_never_overwritten():
    nm = NotificationManager()
    rec = nm.create(title="백업", message="파일 300개 복사 완료", deliver=False)
    assert rec["title"] == "백업"


def test_whitespace_title_counts_as_empty():
    nm = NotificationManager()
    rec = nm.create(title="   ", message="공백 제목도 빈 제목이다", deliver=False)
    assert rec["title"] == "공백 제목도 빈 제목이다"


def test_delivery_uses_the_recorded_title():
    """전달이 제 나름의 제목을 쓰면 알림함과 OS 알림이 갈린다 — 파생은 한 곳에서만."""
    import notification_manager as nm_mod
    import notify_dispatch

    seen = {}
    shared = NotificationManager()
    saved_get = nm_mod.get_notification_manager
    saved_deliver = notify_dispatch.deliver_notification
    nm_mod.get_notification_manager = lambda: shared
    notify_dispatch.deliver_notification = (
        lambda title, body, kind="info", command=None, command_params=None, badge=True:
        seen.update(title=title) or True)
    try:
        notify_dispatch.notify_user(title="", body="스케줄 실패 — 유튜브 팁 보고서\n원인: 타임아웃")
    finally:
        nm_mod.get_notification_manager = saved_get
        notify_dispatch.deliver_notification = saved_deliver

    assert seen["title"] == "스케줄 실패 — 유튜브 팁 보고서"
    assert shared.get_all(limit=1)[0]["title"] == seen["title"]


def test_title_survives_a_dead_notification_box():
    """알림함 기록이 죽어도 전달 제목은 산다(기록 실패와 전달은 독립 — 관문의 계약)."""
    import notification_manager as nm_mod
    import notify_dispatch

    seen = {}
    saved_get = nm_mod.get_notification_manager
    saved_deliver = notify_dispatch.deliver_notification

    def _boom():
        raise RuntimeError("알림함 고장")

    nm_mod.get_notification_manager = _boom
    notify_dispatch.deliver_notification = (
        lambda title, body, kind="info", command=None, command_params=None, badge=True:
        seen.update(title=title) or True)
    try:
        notify_dispatch.notify_user(title="", body="포털 가입 요청 1건")
    finally:
        nm_mod.get_notification_manager = saved_get
        notify_dispatch.deliver_notification = saved_deliver

    assert seen["title"] == "포털 가입 요청 1건"


def test_api_entry_title_is_optional():
    """POST /notifications — 백그라운드 러너·외부 프로세스의 유일한 입구."""
    from api_notifications import NotificationCreate
    assert NotificationCreate(message="본문만 있는 알림").title == ""


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
