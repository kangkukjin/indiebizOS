"""사람-명령 표면은 전부 인지 파이프라인을 지난다 — 진입점 포크 관문 (2026-08-25).

사건(episode 1915, 08-24 23:58): 사용자가 폰 원격런처에서 프로젝트 에이전트에게
"커밋하고 남은 한계도 고쳐줘. **#repair**" 라고 명령했는데 `[self:edit]` 이 RED 에
거절됐다 — "이 턴은 REPAIR 경로로 발급된 적이 없습니다". 사용자는 태그를 붙였다.
붙였는데 **그 표면에는 태그를 읽는 코드가 없었다**: `api_agents._run_agent_command` 만
혼자 `cognitive_stream` 을 우회해 `process_message_with_history` 를 직접 불러,
분류(`_tag_override`)·의식 각성·모델 승격·RED 그랜트가 통째로 없었다.
실측 증거: 런타임 로그의 그 턴 구간에 `[무의식] 분류` 가 0줄.

이건 개별 버그가 아니라 부류다 — **사람이 말을 거는 표면이 하나 늘 때마다 파이프라인을
지나는지 아무도 안 물었다.** 그래서 사람이 고른 grep 이 아니라 관문으로 잠근다
(★pitfall_hand_picked_sweep_leaks: 부류 스윕은 관문을 먼저 쓴다).

계약: `set_task_origin("user")` 를 세우는 함수는 — 헌법(2026-08-05, 커밋 6caa2ea)이
RED 수리 그랜트의 첫째 조건으로 지목한 바로 그 표식이다 — 자기 호출 그래프 안에서
`cognitive_stream` 에 닿아야 한다. 한 홉 어댑터(`process_system_ai_message` →
`drain_stream(runner.cognitive_stream(...))`)는 허용하되, 어디에도 안 닿으면 실패.

  S1 origin='user' 를 세우는 함수가 실제로 존재한다 (표식이 사라지면 이 관문이 무의미해진다)
  S2 그 함수들은 전부 cognitive_stream 에 닿는다
  S3 관문 자신이 우회를 잡는다 (감지기 자기검증 — 가짜 우회 소스를 심어 실패를 확인)
"""
import ast
import os

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {"pylibs", "node_modules", "__pycache__", ".git"}
PIPELINE = "cognitive_stream"
MAX_HOPS = 4


def _py_files():
    for root, dirs, files in os.walk(BACKEND):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


def _callee_name(node: ast.Call) -> str:
    """호출의 이름 한 칸 — 리시버는 버린다(runner.cognitive_stream → cognitive_stream)."""
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return ""


def _origin_aliases(tree: ast.AST) -> set:
    """이 모듈에서 set_task_origin 을 가리키는 이름들(별칭 import 포함)."""
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("thread_context"):
            for a in n.names:
                if a.name == "set_task_origin":
                    names.add(a.asname or a.name)
    return names


def _build_index():
    """backend 전체를 한 번 훑어 (함수이름 → 그 몸이 부르는 이름들) 과 사람-표면 목록을 만든다."""
    calls_of = {}        # 함수 이름 → set(호출하는 이름들)   (동명이인은 합집합 — 보수적)
    surfaces = []        # (파일:줄, 함수 이름)
    for path in _py_files():
        try:
            src = open(path, encoding="utf-8").read()
            tree = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError):
            continue
        aliases = _origin_aliases(tree) or {"set_task_origin"}
        rel = os.path.relpath(path, BACKEND)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            names, is_surface = set(), False
            for c in ast.walk(fn):
                if not isinstance(c, ast.Call):
                    continue
                cn = _callee_name(c)
                names.add(cn)
                # 표식 ①: set_task_origin("user")  ②: actor_context(origin="user")
                if cn in aliases and c.args and _is_user(c.args[0]):
                    is_surface = True
                if cn == "actor_context":
                    for kw in c.keywords:
                        if kw.arg == "origin" and _is_user(kw.value):
                            is_surface = True
            calls_of.setdefault(fn.name, set()).update(names)
            if is_surface:
                surfaces.append((f"{rel}:{fn.lineno}", fn.name))
    return calls_of, surfaces


def _is_user(node) -> bool:
    return isinstance(node, ast.Constant) and node.value == "user"


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


def test_s1_surfaces_exist(index):
    """헌법의 표식(origin='user')이 코드에 실재한다 — 없으면 관문이 공회전한다."""
    _calls_of, surfaces = index
    assert len(surfaces) >= 4, (
        f"origin='user' 를 세우는 표면이 {len(surfaces)}곳뿐이다. 헌법(2026-08-05)은 넷을 "
        f"이름 붙였다(WS 채팅×2·/system-ai/chat·에이전트 명령 HTTP). 표식이 사라졌다면 "
        f"RED 그랜트의 첫째 조건이 통째로 무력해진 것이다: {surfaces}")


def test_s2_every_user_surface_reaches_pipeline(index):
    """사람이 말을 거는 표면은 전부 cognitive_stream 에 닿는다 (ep1915 재발 방지)."""
    calls_of, surfaces = index
    orphans = [(loc, fn) for loc, fn in surfaces if not _reaches(fn, calls_of)]
    assert not orphans, (
        "인지 파이프라인을 우회하는 사람-명령 표면:\n  "
        + "\n  ".join(f"{loc}  {fn}()" for loc, fn in orphans)
        + f"\n→ 이 표면의 턴은 #repair 태그가 읽히는 자리(_tag_override)를 지나지 않는다. "
          f"drain_stream(runner.cognitive_stream(...)) 로 합류시킬 것 "
          f"(전례: cognition/agent_communication.py, cognition/system_ai_core.py).")


def test_s3_gate_detects_a_bypass(tmp_path):
    """감지기 자기검증 — 가짜 우회 표면을 심으면 관문이 잡는가.

    ★관문이 '아무것도 못 잡는 관문'이 되는 것을 막는다(침묵 통과 방지)."""
    src = '''
from thread_context import set_task_origin as _so
def fake_surface(runner, msg):
    _so("user")
    return runner.ai.process_message_with_history(message_content=msg)
'''
    tree = ast.parse(src)
    aliases = _origin_aliases(tree)
    assert aliases == {"_so"}, "별칭 import 를 못 따라간다 — WS 경로가 통째로 안 보인다"
    fn = tree.body[1]
    names = {_callee_name(c) for c in ast.walk(fn) if isinstance(c, ast.Call)}
    assert "process_message_with_history" in names
    assert not _reaches(fn.name, {fn.name: names}), "우회를 통과시켰다"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
