"""에피소드를 여는 자리는 전부 인지 파이프라인을 지난다 — 진입점 포크 관문 ② (2026-08-31).

사건(ep2455 AI동향 04:00 · ep2456 부동산 05:00 · ep2457 AI팁 06:00): 매일 도는 세
보고서가 **인지 밖에서 살고 있었다**. 실측 —
  · 로그에 `[연상:실행기억]` 0줄 (해마 회상 미주입 → 코퍼스가 이미 아는 실수를 되풀이:
    IBL 에 C 스타일 `//` 주석을 넣어 파싱 실패)
  · episode_summary 의 hippocampus_score·unconscious_decision·evaluation_result 전부 NULL
  · trajectory_event 에 model.round·validation.completed 부재 (판정 없음)
  · 그날 증류된 코퍼스 4건 중 이 셋에서 온 것 0건
같은 날 다른 에피소드(2442·2449·2458·2461…)는 전부 채워져 있었다. 원인은 스케줄러
하달(`[others:delegate]{scope:system}`)이 지나는 유일한 통로인 SystemAIRunner 위임
루프가 `process_message_with_history` 를 직접 불러 파이프라인을 통째로 건너뛴 것.

**왜 기존 관문(test_user_surface_pipeline)이 못 잡았나.** 그 관문의 표식은
`set_task_origin("user")` 다 — 헌법이 RED 그랜트의 첫째 조건으로 지목한 자리라
*사람이 말을 거는* 표면만 잡는다. 스케줄러·위임 사슬은 origin 을 일부러 안 세우므로
(fail-closed 설계) 그물 밖이었다. 그런데 인지(연상·분류·평가·증류)는 사람이 시켰는지와
무관하게 **모든 진짜 턴**이 받아야 한다.

그래서 표식을 하나 더 세운다: **에피소드를 여는 함수**(`EpisodeLogger.start_episode`)는
그 턴이 주행기록에 남을 만한 진짜 턴이라고 코드가 이미 선언한 자리다. 그 선언을 한
함수는 자기 호출 그래프 안에서 `cognitive_stream` 에 닿아야 한다. 한 홉 어댑터
(`process_system_ai_message` → `drain_stream(runner.cognitive_stream(...))`,
`_process_via_cognition`)는 허용한다.

  S1 에피소드 진입점이 실재한다 (표식이 사라지면 관문이 공회전한다)
  S2 그 함수들은 전부 cognitive_stream 에 닿는다
  S3 관문 자신이 우회를 잡는다 (감지기 자기검증 — 가짜 우회 소스를 심어 실패 확인)

★자가점검(`__health_check__`)은 애초에 에피소드를 열지 않는다 — 이 관문의 표식이
곧 제외 규약이라, 예외 목록을 손으로 들고 있을 필요가 없다.
"""
import ast
import os

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {"pylibs", "node_modules", "__pycache__", ".git"}
PIPELINE = "cognitive_stream"
ENTRY = "start_episode"
MAX_HOPS = 4


def _py_files():
    for root, dirs, files in os.walk(BACKEND):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(".py") and not f.startswith("test_"):
                yield os.path.join(root, f)


def _callee_name(node: ast.Call) -> str:
    """호출의 이름 한 칸 — 리시버는 버린다(runner.cognitive_stream → cognitive_stream)."""
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return ""


def _build_index():
    """backend 전체를 한 번 훑어 (함수이름 → 부르는 이름들) 과 에피소드 진입점 목록을 만든다."""
    calls_of = {}   # 함수 이름 → set(호출하는 이름들)  (동명이인은 합집합 — 보수적)
    entries = []    # (파일:줄, 함수 이름)
    for path in _py_files():
        try:
            src = open(path, encoding="utf-8").read()
            tree = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = os.path.relpath(path, BACKEND)
        # 정의자 자신(episode_logger)은 표식의 집이지 진입점이 아니다.
        is_definer = os.path.basename(path) == "episode_logger.py"
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            names, is_entry = set(), False
            for c in ast.walk(fn):
                if not isinstance(c, ast.Call):
                    continue
                cn = _callee_name(c)
                names.add(cn)
                if cn == ENTRY and not is_definer:
                    is_entry = True
            calls_of.setdefault(fn.name, set()).update(names)
            if is_entry:
                entries.append((f"{rel}:{fn.lineno}", fn.name))
    return calls_of, entries


def _reaches(start: str, calls_of: dict, target: str = PIPELINE) -> bool:
    """이름 기반 호출 그래프를 MAX_HOPS 깊이까지 걸어 target 에 닿는지 본다."""
    seen, frontier = {start}, [start]
    for _ in range(MAX_HOPS):
        nxt = []
        for name in frontier:
            for callee in calls_of.get(name, ()):
                if callee == target:
                    return True
                if callee not in seen:
                    seen.add(callee)
                    nxt.append(callee)
        frontier = nxt
        if not frontier:
            break
    return False


@pytest.fixture(scope="module")
def index():
    return _build_index()


def test_s1_episode_entries_exist(index):
    """에피소드 진입점이 코드에 실재한다 — 없으면 관문이 공회전한다."""
    _calls_of, entries = index
    assert len(entries) >= 5, (
        f"start_episode 를 부르는 진입점이 {len(entries)}곳뿐이다. 주행기록 배선이 "
        f"사라졌다면 이 관문 이전에 그 사실부터 조사할 것: {entries}")


def test_s2_every_episode_entry_reaches_pipeline(index):
    """에피소드를 여는 자리는 전부 cognitive_stream 에 닿는다 (ep2455~2457 재발 방지)."""
    calls_of, entries = index
    orphans = [(loc, fn) for loc, fn in entries if not _reaches(fn, calls_of)]
    assert not orphans, (
        "인지 파이프라인을 우회하는 에피소드 진입점:\n  "
        + "\n  ".join(f"{loc}  {fn}()" for loc, fn in orphans)
        + "\n→ 이 턴은 연상(해마)·분류(무의식)·평가(GoalEval)·증류를 통째로 못 받는다. "
          "drain_stream(runner.cognitive_stream(...)) 로 합류시킬 것 "
          "(전례: cognition/system_ai_runner._process_via_cognition, "
          "cognition/agent_communication.py, surface/api_agents.py).")


def test_s3_gate_detects_a_bypass():
    """감지기 자기검증 — 가짜 우회 진입점을 심으면 관문이 잡는가.

    ★관문이 '아무것도 못 잡는 관문'이 되는 것을 막는다(침묵 통과 방지)."""
    src = '''
from episode_logger import EpisodeLogger
def fake_entry(runner, msg):
    EpisodeLogger.start_episode("system_ai", msg)
    return runner.ai.process_message_with_history(message_content=msg)
'''
    tree = ast.parse(src)
    fn = tree.body[1]
    names = {_callee_name(c) for c in ast.walk(fn) if isinstance(c, ast.Call)}
    assert ENTRY in names, "start_episode 호출을 못 본다 — 표식 추출이 깨졌다"
    assert "process_message_with_history" in names
    assert not _reaches(fn.name, {fn.name: names}), "우회를 통과시켰다"

    # 대조군: 한 홉 어댑터를 거치는 진입점은 통과해야 한다(과잉 차단 방지).
    ok_src = '''
def real_entry(runner, msg):
    EpisodeLogger.start_episode("system_ai", msg)
    return _process_via_cognition(msg)
def _process_via_cognition(msg):
    return drain_stream(get_system_ai_runner().cognitive_stream(msg))
'''
    ok_tree = ast.parse(ok_src)
    ok_calls = {}
    for f in ok_tree.body:
        ok_calls[f.name] = {_callee_name(c) for c in ast.walk(f) if isinstance(c, ast.Call)}
    assert _reaches("real_entry", ok_calls), "한 홉 어댑터를 우회로 오판했다"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
