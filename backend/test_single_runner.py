"""러너는 하나 — 거짓 초록 가드 (2026-08-23)

재현하는 결함(실측):
  ① `python backend/test_X.py` 로 돌린 배터리 4개가 **0바이트 출력 + 종료코드 0** 을 냈고,
     27·28회차 상상훈련 보고서가 그것을 "회귀 확인: 전부 통과"로 적었다.
     그 파일들엔 `__main__` 이 아예 없어 **시험을 한 건도 안 돌리고** 정상 종료했다.
     전수 측정: 배터리 44개·시험 303건 중 **147건**(49%)이 직접 실행에서 한 번도 안 돌았다.
  ② 거울상 — 정본 러너(pytest.ini·CI `python -m pytest -m "not local"`)가 스크립트형 배터리
     3개에서 **0건을 수집하고 조용히 지나갔다**(그중 `test_repair_staging.py` 는 자기수정
     안전 63검사다). 그 파일들은 CI 에서 한 번도 안 돌았다.

두 증상의 뿌리는 하나다: **러너가 둘이면 한쪽은 반드시 조용히 0건이 된다.**
손으로 적은 러너는 드리프트한다 — 새 시험 함수를 러너에 안 적으면 그 시험만 빠진다.
실제로 "러너가 아무 시험도 안 부르는" 파일들은 "전부 부르는" 파일들의 미래였다.

★그리고 **0건은 '통과'가 아니라 '아무것도 안 봤다'** 이다. 러너가 그 둘을 같은 초록으로
보여주는 한, 읽는 쪽은 무엇이 증명됐는지 알 수 없다(같은 규율: 침묵 절단에 표식을 세운
1cedf7c, 빈손을 부재로 단정하지 않는 B28-1).

처방: 수집은 pytest 하나가 하고(R1), 직접 실행은 그 pytest 로 위임한다(R2).
그러면 어느 문으로 들어와도 같은 집합이 돌고, 드리프트할 두 번째 목록이 없다.

실행: .venv/bin/python -m pytest backend/test_single_runner.py -q
"""
import ast
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

# 명시적 opt-out — 모듈 레벨 스킵으로 **이유를 말하고** 빠진 것은 침묵이 아니다.
# (모듈 레벨에서 sys.modules 스텁을 설치해 공유 프로세스를 오염시키는 스크립트형 배터리,
#  개인 데이터·playwright 등 로컬 전용 의존이 있는 것들 — 각 파일 머리말에 근거가 있다.)
_OPT_OUT_MARK = "allow_module_level=True"

# 스크립트형 배터리 — `__main__` 이 배터리 전체를 돌리고 실패 시 종료코드≠0 을 낸다.
# pytest 는 다리 시험(별도 프로세스)으로 그것을 보므로 조용한 0건이 아니다. 위임하면
# 다리가 자기를 다시 불러 무한 재귀한다. ★면제는 추론이 아니라 **선언**으로만 얻는다.
_SCRIPT_BATTERY_MARK = "RUNNER: script-battery"


def _battery_files():
    out = []
    for name in sorted(os.listdir(_HERE)):
        if name.startswith("test_") and name.endswith(".py") and name != os.path.basename(__file__):
            out.append(name)
    return out


def _read(name):
    with open(os.path.join(_HERE, name), encoding="utf-8") as f:
        return f.read()


def _test_funcs(src):
    """중첩(try 블록 안 정의 등)까지 포함해 시험 함수를 센다 — tree.body 만 보면 놓친다."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    return {n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")}


def _main_block(src):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    for n in ast.walk(tree):
        if isinstance(n, ast.If):
            try:
                if ast.unparse(n.test).replace('"', "'") == "__name__ == '__main__'":
                    return "\n".join(src.splitlines()[n.lineno - 1:n.end_lineno])
            except Exception:
                continue
    return None


def test_r1_every_battery_is_visible_to_pytest():
    """수집 0건인 파일이 있으면 CI 는 그 파일을 '통과'로 보여주면서 아무것도 안 본다."""
    invisible = []
    for name in _battery_files():
        src = _read(name)
        if _OPT_OUT_MARK in src:
            continue                      # 이유를 말하고 빠진 것 — 침묵이 아니다
        if not _test_funcs(src):
            invisible.append(name)
    assert not invisible, (
        "pytest 가 0건을 수집하는 배터리 — CI 가 조용히 지나친다: %s\n"
        "  → `def test_*` 를 하나 두어 판정을 노출하거나(스크립트형은 다리 시험),\n"
        "     빠질 이유가 있으면 pytest.skip(..., allow_module_level=True) 로 **말하고** 빠질 것."
        % ", ".join(invisible))


def test_r2_direct_run_delegates_to_pytest():
    """직접 실행이 시험을 조용히 건너뛰지 못하게 — `__main__` 은 pytest 로 위임한다."""
    bad = []
    for name in _battery_files():
        src = _read(name)
        if _OPT_OUT_MARK in src:
            continue                      # 직접 실행 전용이라고 스스로 밝힌 것
        if not _test_funcs(src):
            continue                      # R1 이 잡는다
        if _SCRIPT_BATTERY_MARK in src:
            # 선언한 이상 계약을 지키는지도 본다 — 다리 없이 표식만 달면 그게 새 침묵이다.
            assert "subprocess" in src and "__file__" in src, \
                f"{name}: script-battery 를 선언했는데 다리 시험(별도 프로세스 실행)이 없다"
            continue
        block = _main_block(src)
        if block is None:
            bad.append((name, "__main__ 없음 — 직접 실행이 0건 통과(종료코드 0)"))
        elif not re.search(r"\bpytest\.main\(|_pytest\.main\(", block):
            bad.append((name, "__main__ 이 pytest 로 위임하지 않는다 — 두 번째 러너는 드리프트한다"))
    assert not bad, "거짓 초록 위험:\n" + "\n".join("  %s — %s" % b for b in bad)


def test_r3_patrol_batteries_are_collected():
    """12시간 순찰(§1E)이 부르는 배터리가 pytest 에도 보이는가.

    순찰은 `[sys.executable, 파일]` 로 직접 실행한다 — R2 덕분에 그 호출은 이제 pytest 로
    위임되지만, 배터리 자신이 수집 0건이면 순찰은 **아무것도 안 돌고 rc 0** 을 받는다.
    (그 조합이 정확히 이 파일이 막으려는 사고다.)
    """
    health = os.path.join(_ROOT, "backend", "cognition", "world_pulse_health.py")
    src = open(health, encoding="utf-8").read()
    m = re.search(r'suites\s*=\s*\[([^\]]+)\]', src)
    assert m, "순찰의 배터리 목록(suites)을 찾지 못했다 — 이름이 바뀌었으면 이 가드도 갱신할 것"
    rels = re.findall(r'"([^"]+\.py)"', m.group(1))
    assert rels, "순찰 배터리 목록이 비었다"
    for rel in rels:
        path = os.path.join(_ROOT, rel)
        assert os.path.exists(path), f"순찰이 없는 파일을 부른다: {rel}"
        assert _test_funcs(open(path, encoding="utf-8").read()), \
            f"순찰 대상 {rel} 이 pytest 수집 0건 — 순찰이 빈 초록을 받는다"


def test_r4_zero_is_not_pass_is_written_down():
    """가이드에 규약이 적혀 있는가 — 사람·에이전트가 같은 함정에 다시 들어가지 않도록."""
    guide = os.path.join(_ROOT, "data", "guides", "imagination_training.md")
    src = open(guide, encoding="utf-8").read()
    assert "pytest" in src, "훈련 가이드에 러너 규약이 없다"
    assert "0건" in src or "빈 초록" in src or "거짓 초록" in src, \
        "훈련 가이드에 '0건 = 통과 아님' 조항이 없다"


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
