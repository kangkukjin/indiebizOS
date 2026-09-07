"""디버그 로그는 접을 수 있어도 **조용히** 접을 수 없다 — 2026-09-07 (실측 추적).

발단: 기억 원장에 같은 내용이 두 행(500·501) 생겼다. 원인을 실행 경로에서 찾다가
런타임 로그를 봤더니 `[self:memory]{op:"save"…}` 가 **한 줄**뿐이라 "시스템이 한 번
실행하고 두 번 저장했나"로 읽혔다. 실제로는 `action_health` 에 5건(실패 2·성공 2·
삭제 1)이 남아 있었고 — 요청이 네 번 갔던 것이다. 로그의 30초 디듀프가 동일 코드
넷을 말없이 한 줄로 접었다.

디듀프의 목적(UI 폴링 도배 방지)은 정당하지만, 접히는 실제 대상에는 **실패 뒤 같은
명령 재시도**가 들어간다 — 로그를 가장 열심히 읽는 순간이고, 부작용 액션이라면
세계가 몇 번 바뀌었는지를 로그가 감추는 것이다(침묵 클램프 금지와 같은 부류).

계약: 창은 유지하되 창 만료 때 **접은 수를 한 줄로 신고**한다.

실행: .venv/bin/python -m pytest -q backend/test_ibl_debug_log_folding_2026_09_07.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).resolve().parent / "cognition"))
import system_tools_ibl as S  # noqa: E402


def _reset():
    S._ibl_log_seen.clear()
    S._ibl_log_folded.clear()


def _run(codes, capsys, clock=None):
    _reset()
    if clock is not None:
        S.time.monotonic = clock          # 창 만료를 시간 대신 값으로 몬다
    for c in codes:
        S._ibl_debug_log(c, c)
    return capsys.readouterr().out


def test_first_execution_is_logged(capsys):
    out = _run(["[table:take]{n: 1}"], capsys)
    assert "[IBL_DEBUG] code=[table:take]{n: 1}" in out


def test_repeat_inside_window_is_folded_not_lost(capsys, monkeypatch):
    """창 안 반복은 줄을 늘리지 않지만, 창이 지나면 **몇 번 접혔는지** 말한다."""
    t = [1000.0]
    monkeypatch.setattr(S.time, "monotonic", lambda: t[0])
    _reset()
    code = '[self:memory]{op: "save", content: "x"}'
    for _ in range(4):                     # 실측 모양: 같은 save 를 네 번
        S._ibl_debug_log(code, code)
        t[0] += 5                          # 15초 안에 넷
    out = capsys.readouterr().out
    assert out.count("[IBL_DEBUG] code=") == 1, out      # 도배는 여전히 막는다
    assert "생략" not in out                              # 아직 창 안 — 신고는 만료 때

    t[0] += 60                             # 창 만료 뒤 아무 코드나 한 번
    S._ibl_debug_log("[table:take]{n: 1}", "[table:take]{n: 1}")
    out = capsys.readouterr().out
    assert "(같은 코드 3회 생략 — 30s 창)" in out, out    # 첫 줄 외 3회가 접혔다
    assert 'self:memory' in out                          # 무엇이 접혔는지도 말한다


def test_distinct_codes_are_never_folded(capsys, monkeypatch):
    monkeypatch.setattr(S.time, "monotonic", lambda: 500.0)
    out = _run(['[table:take]{n: 1}', '[table:take]{n: 2}', '[table:sort]{by: "a"}'], capsys)
    assert out.count("[IBL_DEBUG] code=") == 3, out


def test_window_uses_last_printed_time_so_polling_still_reports(capsys, monkeypatch):
    """계속 도는 폴링도 30초마다 자기 존재를 밝힌다 — 영원한 침묵이 되지 않는다."""
    t = [0.0]
    monkeypatch.setattr(S.time, "monotonic", lambda: t[0])
    _reset()
    code = '[self:here]{}'
    for _ in range(20):                    # 5초 간격 100초 폴링
        S._ibl_debug_log(code, code)
        t[0] += 5
    out = capsys.readouterr().out
    assert out.count("[IBL_DEBUG] code=") >= 3, out       # 창마다 살아 있음을 보인다
    assert "생략" in out                                   # 접힌 수도 함께
    assert out.count("[IBL_DEBUG]") < 20, out             # 그래도 도배는 아니다


def test_folded_counter_does_not_grow_unbounded(capsys, monkeypatch):
    t = [0.0]
    monkeypatch.setattr(S.time, "monotonic", lambda: t[0])
    _reset()
    for i in range(300):
        S._ibl_debug_log(f"[table:take]{{n: {i}}}", "x")
        t[0] += 1                          # 1초 간격 — 300초 동안 300개 코드
    capsys.readouterr()
    assert len(S._ibl_log_seen) <= 40, len(S._ibl_log_seen)   # 창(30s) 안엣것만 남는다
    assert len(S._ibl_log_folded) <= 40, len(S._ibl_log_folded)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
