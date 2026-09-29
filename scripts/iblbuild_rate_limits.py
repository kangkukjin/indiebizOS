"""원천 요청 한도 관문 (2026-09-29, 상상훈련 77회차 F77-2 밭 이관).

질문 하나 — 패키지가 HTTP 429 를 알아보는 자리는 공통 봉투(`common.api_client.rate_limited_failure`
또는 `RateLimitedError`)로 실패를 내는가?
  77회차: Semantic Scholar·OpenAlex 의 429 가 일반 실패 문구로 나가 판본 2 에서 `TOOL` 이 됐다 —
  프로그램은 "잠시 뒤 같은 원천"과 "원천을 바꿔라"를 문자열로만 가를 수 있었다. 공통 봉투는
  `error_type:"rate_limited"`·`retry_after` 를 싣고, 판본 2 어댑터가 `RATE_LIMITED` 로 올린다.

판정(AST, 파일 단위): 상수 429 와 비교(`==`·`in (…, 429)`)하는 파일은 공통 봉투 이름을 참조해야 한다.
재시도만 하고 마지막 응답을 호출자에게 넘기는 헬퍼(백오프)는 호출자가 판정하므로 `ALLOW` 에 사유를 적는다.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_ENVELOPE_NAMES = {"rate_limited_failure", "RateLimitedError"}

# 검토한 예외 — 키 = "패키지/파일.py", 값 = 사유(필수)
ALLOW: dict[str, str] = {
    "web/tool_webcrawl.py": "임의 웹 페이지 수집의 403·429·503 은 봇 차단 분류(bot_blocked)로 판정하는 별도 계약 — 원천 API 한도가 아니다.",
}


def _mentions_429(tree) -> list[int]:
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            consts = [c for c in [node.left, *node.comparators] for c in ([c] if not isinstance(c, (ast.Tuple, ast.List, ast.Set)) else c.elts)]
            if any(isinstance(c, ast.Constant) and c.value == 429 for c in consts):
                lines.append(node.lineno)
    return lines


def validate_rate_limits(root: Path) -> list[str]:
    tools = root / "data" / "packages" / "installed" / "tools"
    issues = []
    for path in sorted(tools.rglob("*.py")):
        if "__pycache__" in path.parts or path.name.startswith("test_"):
            continue
        rel = str(path.relative_to(tools))
        if rel in ALLOW:
            continue
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError):
            continue
        lines = _mentions_429(tree)
        if not lines:
            continue
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
            a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        if not names & _ENVELOPE_NAMES:
            issues.append(f"{rel}:{lines[0]} HTTP 429 를 알아보지만 공통 봉투(rate_limited_failure·RateLimitedError)를 "
                          f"쓰지 않는다 — 판본 2 에서 일반 TOOL 실패가 된다(백오프 헬퍼면 ALLOW 에 사유)")
    return issues


if __name__ == "__main__":
    found = validate_rate_limits(Path(__file__).resolve().parents[1])
    for i in found:
        print(" ", i)
    print(f"원천 요청 한도 봉투: {len(found)}건")
    sys.exit(1 if found else 0)
