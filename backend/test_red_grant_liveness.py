"""RED 그랜트 만료 배터리 — 시계가 아니라 주인에게 묻는가 (2026-08-23, episode 1746).

사건: `#repair` 로 연 8배 규모 상상훈련 턴(15:51~16:36, 45분)이 16:04 에 4파일을 격리에
쌓고 16:26 에 `[self:patch]{op:"apply"}` 를 불렀는데, 그 사이 16:22 에 **발급 시각부터 재던
30분 시계**가 살아 있는 턴의 그랜트를 처형해 apply 가 거절됐다. 라이브 미반영 4건.
게다가 거절 문구가 만료·미발급을 구별하지 않아, 막힌 턴이 자기를 '수리 경로 밖 세션'으로
오진하고 사용자에게 없는 사실을 보고했다.

  G1 발급 턴이 살아 있으면 옛 한도를 한참 넘겨도 만료되지 않는다 (사고 재현)
  G2 턴이 닫힌 뒤에는 유휴 한도로 회수된다 (finally 누수 방지 — 시계의 진짜 용도)
  G3 유휴는 **마지막 사용**부터 잰다 — 일하는 그랜트는 데워진다
  G4 신원 매칭은 종전 그대로 (무임승차 거부·양쪽 미상은 fail-closed)
  G5 사유를 구별해 말한다 (만료 / 미발급 / 주인 아님)
  G6 판정 불능인 몸(폰·분리 수행자 red_apply — 열린 턴 원장이 없다)에서는 종전대로 시계로 회수
"""
import time

import pytest

import episode_logger as el
import red_grant as rg


@pytest.fixture(autouse=True)
def _clean():
    rg.revoke_grant()
    with el._live_lock:
        _saved = set(el._live_episode_ids)
        el._live_episode_ids.clear()
    yield
    rg.revoke_grant()
    with el._live_lock:
        el._live_episode_ids.clear()
        el._live_episode_ids.update(_saved)


def _open_turn(eid=90001):
    """이 프로세스가 턴 하나를 열고 있는 상태 — /health 의 live_turns 와 같은 출처."""
    with el._live_lock:
        el._live_episode_ids.add(eid)
    return eid


def _close_turn(eid):
    with el._live_lock:
        el._live_episode_ids.discard(eid)


def _age(seconds):
    """시간을 앞으로 감는다(sleep 없이) — 발급·마지막 사용을 함께 뒤로 민다."""
    g = rg._grant
    g["issued_at"] -= seconds
    g["last_used_at"] -= seconds


def test_g1_live_turn_keeps_grant_past_old_ttl():
    """★사고 재현: 45분짜리 턴의 apply 가 34분째에 왔다. 옛 코드는 여기서 None 을 냈다."""
    eid = _open_turn()
    rg.issue_grant(agent_id="system_ai", task_id="task_sysai_7ef2c1a4", reason="상상훈련 33회차")
    assert rg._grant["episode_ids"] == {eid}          # 발급이 주인을 붙잡았다
    _age(34 * 60)
    assert rg.active_grant(task_id="task_sysai_7ef2c1a4") is not None
    _age(4 * 60 * 60)                                  # 4시간 더 — 턴이 살아 있는 한 안 죽는다
    assert rg.active_grant(task_id="task_sysai_7ef2c1a4") is not None
    assert rg.denial_note(task_id="task_sysai_7ef2c1a4") == ""


def test_g2_closed_turn_expires_after_idle_limit():
    """시계의 진짜 용도 — finally 가 못 돈 채 프로세스가 살아 있는 누수만 회수한다."""
    eid = _open_turn()
    rg.issue_grant(agent_id="system_ai", task_id="task_leak", reason="누수")
    _age(rg._IDLE_TTL_SEC + 60)
    assert rg.active_grant(task_id="task_leak") is not None   # 아직 턴이 열려 있다
    _close_turn(eid)                                          # 턴이 닫혔다(= finally 누수 상태)
    assert rg.active_grant(task_id="task_leak") is not None   # 방금 쓴 그랜트는 아직 산다
    _age(rg._IDLE_TTL_SEC + 60)                               # 그 뒤로 아무도 안 쓰면
    assert rg.active_grant(task_id="task_leak") is None
    assert "만료" in rg.denial_note(task_id="task_leak")


def test_g3_idle_clock_counts_from_last_use():
    """일하는 그랜트는 데워진다 — 격리 적재로 쓰는 동안은 시계가 다시 0 부터."""
    eid = _open_turn()
    rg.issue_grant(agent_id="system_ai", task_id="task_warm", reason="적재 중")
    _close_turn(eid)                                           # 턴은 닫혔다 — 이제 시계가 산다
    _age(rg._IDLE_TTL_SEC - 60)
    assert rg.active_grant(task_id="task_warm") is not None     # 한도 직전 — 이 조회가 데운다
    _age(rg._IDLE_TTL_SEC - 60)                                 # 마지막 사용 이후로는 아직 미달
    assert rg.active_grant(task_id="task_warm") is not None
    _age(rg._IDLE_TTL_SEC + 60)                                 # 그 뒤로 손 놓으면 회수된다
    assert rg.active_grant(task_id="task_warm") is None


def test_g4_identity_matching_unchanged():
    """무회귀 — 만료 규칙만 바뀌고 '누가 주인인가'는 종전 그대로여야 한다."""
    _open_turn()
    rg.issue_grant(agent_id="system_ai", task_id="task_owner", reason="주인")
    assert rg.active_grant(task_id="task_owner") is not None
    assert rg.active_grant(task_id="task_other") is None                 # 병행 자율 태스크 무임승차 거부
    assert rg.active_grant(task_id=None, agent_id="system_ai") is not None  # 신원 유실 심 폴백
    assert rg.active_grant(task_id=None, agent_id="다른몸") is None
    assert rg.active_grant() is None                                     # 둘 다 없으면 fail-closed


def test_g5_denial_note_tells_which_refusal_it_is():
    """★거절은 fail-closed 그대로, 사유만 정직하게 — 세 사건이 한 문장으로 뭉개지지 않는다."""
    assert "발급된 적이 없" in rg.denial_note(task_id="task_x", agent_id="system_ai")

    eid = _open_turn()
    rg.issue_grant(agent_id="system_ai", task_id="task_owner", reason="주인")
    assert "주인이 아닙니다" in rg.denial_note(task_id="task_other", agent_id="system_ai")

    _close_turn(eid)
    _age(rg._IDLE_TTL_SEC + 60)
    note = rg.denial_note(task_id="task_owner", agent_id="system_ai")
    assert "만료" in note and "유휴 한도" in note and "발급 턴은 이미 닫혔습니다" in note


def test_g6_bodies_without_a_turn_ledger_still_expire():
    """열린 턴을 물어볼 곳이 없는 몸(폰·red_apply 분리 수행자)은 종전대로 시계가 회수한다 —
    판정 불능이 '무기한 유효'로 번지지 않는다(거절 방향은 언제나 안전한 쪽)."""
    rg.issue_grant(agent_id="system_ai", task_id="task_headless", reason="분리 수행자")
    assert rg._grant["episode_ids"] == set()                   # 물어볼 곳 없음
    assert rg._issuer_alive(rg._grant) is None
    assert rg.active_grant(task_id="task_headless") is not None
    _age(rg._IDLE_TTL_SEC + 60)
    assert rg.active_grant(task_id="task_headless") is None
    assert "판정 불능" in rg.denial_note(task_id="task_headless")


if __name__ == "__main__":
    # ★러너는 하나 — 직접 실행도 pytest 로 위임한다(2026-08-23 28회차: 직접 실행이
    #   수집을 건너뛰어 배터리가 조용히 0건이 되는 거짓 초록).
    raise SystemExit(pytest.main([__file__]))
