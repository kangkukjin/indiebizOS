#!/usr/bin/env python3
"""연상 조립 관문 — 회상 공급원은 공통 흐름(associative_recall) 밖에서 부를 수 없고, 1상을 연 자리는 반드시 2상을 닫는다.

왜(2026-09-18 실측): 회상 조립이 세 곳(agent_pipeline·agent_communication·recall-preview)에서 각자 공급원의 부분집합을
불렀다 — 프리뷰는 세계 지도·세계의 기억을 통째로 못 받았고, 통신 경로는 파이프라인과 손으로 같은 두 단계를 다시 썼다.
새 기억을 하나 넣으면 세 곳을 고쳐야 하고 하나를 빠뜨리면 조용히 갈라진다. 사람이 grep 으로 지키는 규칙은 샌다
(pitfall hand-picked-sweep-leaks) — 그래서 관문이다.

규칙:
  A. 공급원 진입 함수(SOURCE_ENTRIES)는 `backend/cognition/associative_recall.py` 와 그 함수를 *정의한* 모듈 안에서만
     호출된다. `tree_recall.recall`(자동 주입용 가지 먼저 회상)은 associative_recall·catalog_recall 에서만.
     (`tree_recall.search` 는 AI 의 명시 조회·포식 장소 찾기용이라 자유.)
  B. `_associate(...)` 나 `associative_recall.begin(...)` 을 부른 함수는 같은 함수 안에서 `.route(...)` 도 부른다 —
     2상(세계 지도)이 빠진 주입은 정적 검사에서 막는다. (`text()` 도 런타임에 거부하지만, 여기서 먼저 잡는다.)

표면: backend/**/*.py (test_ 제외) + scripts/*.py (이 관문·고정물 스크립트 자신 제외).
사용: python3 scripts/check_recall_assembly.py            # 관문 (실패 시 exit 1)
      python3 scripts/check_recall_assembly.py --self-test
"""
import ast
import os
import sys
from typing import Dict, List, Set, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOW = "backend/cognition/associative_recall.py"

# 진입 함수 → 정의 모듈(자기 모듈 안의 호출은 허용). 자동 주입 공급원의 턴 단위 입구들이다.
SOURCE_ENTRIES: Dict[str, str] = {
    "build_execution_memory": "ibl_usage_rag",
    "build_execution_memory_from_hint": "ibl_usage_rag",
    "recall_for_turn": "catalog_recall",
    "world_memory_for_turn": "catalog_recall",
    "scent_xml": "decision_ledger",
    "pending_scent": "red_report",
    "guide_map_text": "hippo_tree",
}
TREE_RECALL_ALLOWED = {"associative_recall", "catalog_recall"}
SELF = {"scripts/check_recall_assembly.py", "scripts/recall_golden.py"}
# 평가 하네스는 회상 함수를 직접 재어야 한다 — 자동 주입 경로가 아니다.
EXEMPT = {"scripts/evaluate_tree_recall.py"}


def _module_name(rel: str) -> str:
    return os.path.splitext(os.path.basename(rel))[0]


def _called_name(node: ast.Call) -> Tuple[str, str]:
    """(이름, 소유자) — `a.b()` 는 ("b", "a"), `b()` 는 ("b", "")."""
    fn = node.func
    if isinstance(fn, ast.Attribute):
        owner = fn.value.id if isinstance(fn.value, ast.Name) else ""
        return fn.attr, owner
    if isinstance(fn, ast.Name):
        return fn.id, ""
    return "", ""


def _tree_recall_aliases(tree: ast.AST) -> Set[str]:
    """`from tree_recall import recall [as x]` 로 들어온 이름들."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "tree_recall":
            for a in node.names:
                if a.name == "recall":
                    names.add(a.asname or a.name)
    return names


def violations_in(rel: str, source: str) -> List[str]:
    out: List[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"{rel}: 구문 오류 {e}"]
    mod = _module_name(rel)
    is_flow = rel == FLOW
    tr_aliases = _tree_recall_aliases(tree)

    # A. 공급원 진입 함수 호출
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name, owner = _called_name(node)
        if name in SOURCE_ENTRIES and not is_flow and mod != SOURCE_ENTRIES[name]:
            out.append(f"{rel}:{node.lineno}: 공급원 `{name}` 을 공통 흐름 밖에서 부른다 — associative_recall 의 공급원으로 옮겨라")
        if ((name == "recall" and owner == "tree_recall") or (name in tr_aliases and not owner)) \
                and mod not in TREE_RECALL_ALLOWED:
            out.append(f"{rel}:{node.lineno}: `tree_recall.recall`(가지 먼저 회상)은 associative_recall·catalog_recall 에서만")

    # B. 1상을 연 함수는 2상을 닫는다
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        opens, closes = [], False
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            name, owner = _called_name(node)
            if name == "_associate" or (name == "begin" and (owner == "associative_recall" or _imports_begin(tree))):
                if not (is_flow and fn.name in ("stub", "begin")) and fn.name != "_associate":   # 러너 훅은 위임만 한다
                    opens.append(node.lineno)
            if name == "route":
                closes = True
        if opens and not closes:
            out.append(f"{rel}:{opens[0]}: `{fn.name}` 이 1상(_associate/begin)을 열고 `.route(request_type)` 로 닫지 않는다")
    return out


def _imports_begin(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "associative_recall":
            if any(a.name == "begin" for a in node.names):
                return True
    return False


def _surface() -> List[str]:
    rels = []
    for root, dirs, files in os.walk(os.path.join(ROOT, "backend")):
        dirs[:] = [d for d in dirs if d not in {"__pycache__", "node_modules", ".venv"}]
        for f in files:
            if f.endswith(".py") and not f.startswith("test_"):
                rels.append(os.path.relpath(os.path.join(root, f), ROOT))
    for f in os.listdir(os.path.join(ROOT, "scripts")):
        rel = os.path.join("scripts", f)
        if f.endswith(".py") and rel not in SELF and rel not in EXEMPT:
            rels.append(rel)
    return sorted(rels)


def run() -> int:
    problems: List[str] = []
    for rel in _surface():
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            problems += violations_in(rel, f.read())
    if problems:
        print(f"[FAIL] 연상 조립 관문 — {len(problems)}건")
        for p in problems:
            print("  " + p)
        return 1
    print("[OK] 연상 조립 관문 통과 — 공급원 호출은 associative_recall 안에만, 1상을 연 자리는 전부 2상을 닫는다")
    return 0


def self_test() -> int:
    bad_a = "from ibl_usage_rag import build_execution_memory\ndef f(m):\n    return build_execution_memory(m)\n"
    assert any("공급원" in v for v in violations_in("backend/cognition/x.py", bad_a))
    assert not violations_in("backend/cognition/ibl_usage_rag.py", "def g(m):\n    return build_execution_memory(m)\n")
    bad_tr = "import tree_recall\ndef f(s, q):\n    return tree_recall.recall(s, q)\n"
    assert any("tree_recall" in v for v in violations_in("backend/datastore/y.py", bad_tr))
    assert not violations_in("backend/datastore/y.py", "import tree_recall\ndef f(s, q):\n    return tree_recall.search(s, q)\n")
    bad_alias = "from tree_recall import recall as rc\ndef f(s, q):\n    return rc(s, q)\n"
    assert any("tree_recall" in v for v in violations_in("backend/cognition/z.py", bad_alias))
    bad_b = "def turn(self, m):\n    r = self._associate(m)\n    return r.reflex\n"
    assert any("닫지 않는다" in v for v in violations_in("backend/cognition/p.py", bad_b))
    ok_b = "def turn(self, m):\n    r = self._associate(m)\n    r.route('THINK')\n    return r.text()\n"
    assert not violations_in("backend/cognition/p.py", ok_b)
    ok_chain = "def turn(self, m):\n    return self._associate(m).route(None).text()\n"
    assert not violations_in("backend/cognition/p.py", ok_chain)
    bad_begin = "from associative_recall import begin\ndef turn(m):\n    return begin(None, m).text()\n"
    assert any("닫지 않는다" in v for v in violations_in("backend/cognition/q.py", bad_begin))
    print("[OK] self-test")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else run())
