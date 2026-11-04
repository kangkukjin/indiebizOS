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

현재 계약: 수집·자동 실행은 pytest 하나가 맡는다(R1·R3).
선택적으로 제공하는 직접 실행 진입점은 pytest로 위임한다(R2).
일반 pytest 모듈에는 __main__을 요구하지 않는다. 순찰도 이미 -m pytest를 사용한다.

실행: .venv/bin/python -m pytest backend/test_single_runner.py
"""
import ast
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

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


def test_r2_existing_direct_entrypoints_delegate_to_pytest():
    """직접 실행을 제공하는 파일만 같은 pytest 러너로 위임해야 한다."""
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
        if block is not None and not re.search(r"\bpytest\.main\(|_pytest\.main\(", block):
            bad.append((name, "__main__ 이 pytest 로 위임하지 않는다 — 두 번째 러너는 드리프트한다"))
    assert not bad, "거짓 초록 위험:\n" + "\n".join("  %s — %s" % b for b in bad)


@pytest.mark.parametrize('returncode', [0, 1, 5])
def test_r3_patrol_uses_pytest_and_rejects_failure_or_no_tests(monkeypatch, returncode):
    """실제 순찰 호출을 관측한다. 실패(1)와 수집 0건(5)은 성공이 아니다."""
    import subprocess
    import sys
    from health_probes import _run_silent_failure_regression

    calls = []

    def run(argv, **kwargs):
        assert argv[:3] == [sys.executable, '-m', 'pytest']
        path = Path(argv[3])
        assert path.is_file() and _test_funcs(path.read_text(encoding='utf-8'))
        assert kwargs['cwd'] == _ROOT
        calls.append(path)
        return SimpleNamespace(returncode=returncode, stdout='probe result', stderr='')

    monkeypatch.setattr(subprocess, 'run', run)
    result = _run_silent_failure_regression(Path(_ROOT))
    assert calls, '순찰이 실제 시험 러너를 한 번도 호출하지 않았다'
    assert result['success'] is (returncode == 0)
    if returncode:
        assert len(calls) == 1
        assert result['data_quality'] == 'regression_failure'
        assert f'rc={returncode}' in result['error_message']


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
