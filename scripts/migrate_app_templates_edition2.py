#!/usr/bin/env python3
"""앱 블록(app:)·독립 매니페스트의 액션 템플릿을 판본 2 표면 바인딩으로 기계 변환한다 (2026-10-05 ①, 1회성).

무엇을 바꾸나 — 템플릿 문자열 안에서만:
  · "$key"(문자열 리터럴 전체가 입력 하나)      → $key              값이 타입 그대로 inputs 로 간다
  · "{field}" / "{a.b}"(리터럴 전체가 행 필드)    → $item.field       행·드릴 컨텍스트 레코드
  · 섞인 리터럴 "…$key…{f}…"                      → f"…${key}…${item.f}…"
  · 따옴표 밖 {field} (예: lat: {lat})            → $item.lat
  · 따옴표 밖 $key                                 → 그대로
  블록마다 `edition: 2` 를 선언한다. 판본 2 가 받지 않는 문법(@노드 지정 `}@hub`, 파이프 축약 `| sort:`)이 든
  블록은 변환하지 않고 `edition: 1` + `legacy_reason` 을 선언한다(지도·정기보고·신문).

왜 텍스트 변환인가: yaml 재직렬화는 주석·순서·따옴표를 잃는다. 템플릿은 한 줄 single-quoted 스칼라
(`action: '...'`)로만 쓰이므로(사전 조사) 그 줄만 바꾸고 나머지 바이트는 건드리지 않는다.

사용:  python3 scripts/migrate_app_templates_edition2.py [--check]   (--check = 변경 미리보기만)
멱등: 이미 edition 이 선언된 블록은 건너뛴다. 변환 뒤 `python3 scripts/build_ibl_nodes.py --check` 가 판본 2
컴파일러로 전수 검사한다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [*sorted((ROOT / "data/ibl_nodes_src").glob("*.yaml")),
           *sorted((ROOT / "data/packages/installed/tools").glob("*/ibl_actions.yaml"))]
STANDALONE = sorted((ROOT / "data/instruments").glob("*.yaml"))

TEMPLATE_KEYS = ("action", "options_action", "delete_action", "add_action", "remove_action", "search_here",
                 "moveend", "center_drag", "marker_click", "selection", "saved")
TEMPLATE_LINE = re.compile(r"^(\s*)(?:- )?([a-z_]+):\s*'(.*)'\s*(#.*)?$")
EDITION1_ONLY = re.compile(r"\|\s*(sort|take|filter)\s*:")   # @노드 지정은 판본 2 도 받는다(2026-10-05)
LEGACY_REASON = "판본 2 는 파이프 축약(| sort: / | take:)을 받지 않는다 — >> [table:sort]/[table:take] 조합으로 손 변환 뒤 edition 2 로"

STR_LIT = re.compile(r'"((?:\\.|[^"\\])*)"')
DOLLAR = re.compile(r"\$([A-Za-z_]\w*)")
FIELD = re.compile(r"\{([A-Za-z_][\w.]*)\}")


def convert_template(t: str) -> str:
    """IBL 템플릿 한 개를 판본 2 바인딩으로. 템플릿 밖 YAML 문법은 호출자가 지킨다."""
    out, last = [], 0
    for m in STR_LIT.finditer(t):
        out.append(_outside(t[last:m.start()]))
        out.append(_literal(m.group(1)))
        last = m.end()
    out.append(_outside(t[last:]))
    return "".join(out)


def _literal(body: str) -> str:
    """따옴표 안 — 전체가 $key 하나면 값 참조, 전체가 {field} 하나면 $item.field, 섞였으면 f-문자열, 없으면 그대로."""
    if not DOLLAR.search(body) and not FIELD.search(body):
        return f'"{body}"'
    if DOLLAR.fullmatch(body):
        return "$" + body[1:]
    if FIELD.fullmatch(body):
        return "$item." + body[1:-1]
    parts = body.replace("${", "$\u0000{")  # 이미 ${ 가 있으면 보존(없을 것으로 봄)
    parts = DOLLAR.sub(lambda m: "${" + m.group(1) + "}", parts)
    parts = FIELD.sub(lambda m: "${item." + m.group(1) + "}", parts)
    return 'f"' + parts.replace("$\u0000{", "${") + '"'


def _outside(seg: str) -> str:
    """따옴표 밖 — {field} 만 $item.field 로. $key 는 그대로. 레코드 {k: v} 는 콜론이 있어 FIELD 에 안 걸린다."""
    return FIELD.sub(lambda m: "$item." + m.group(1), seg)


def _block_spans(lines: list[str], key_pat: re.Pattern) -> list[tuple[int, int, int]]:
    """key_pat(예: ^\\s*app:$)에 맞는 줄에서 시작하는 블록의 (시작 줄, 끝 줄(배타), 들여쓰기)."""
    spans = []
    for i, line in enumerate(lines):
        m = key_pat.match(line)
        if not m:
            continue
        indent = len(m.group(1))
        j = i + 1
        while j < len(lines):
            s = lines[j]
            if s.strip() and not s.lstrip().startswith("#") and (len(s) - len(s.lstrip())) <= indent:
                break
            j += 1
        spans.append((i, j, indent))
    return spans


def migrate_text(text: str, block_pat: re.Pattern, decl_indent_extra: int, whole_file: bool = False) -> tuple[str, list[str]]:
    lines = text.split("\n")
    notes = []
    if whole_file:  # 독립 매니페스트 — instrument: 줄부터 파일 끝까지가 한 블록(들여쓰기 0 의 형제 키들이 블록을 끊지 않게)
        heads = [i for i, ln in enumerate(lines) if block_pat.match(ln)]
        spans = [(heads[0], len(lines), 0)] if heads else []
    else:
        spans = _block_spans(lines, block_pat)
    for start, end, indent in reversed(spans):
        block = lines[start:end]
        if any(re.match(rf"^\s{{{indent + decl_indent_extra}}}edition:\s*\d", ln) for ln in block):
            notes.append(f"skip(edition 선언 있음) @{start + 1}")
            continue
        templates = [(k, TEMPLATE_LINE.match(ln)) for k, ln in enumerate(block)]
        templates = [(k, m) for k, m in templates if m and m.group(2) in TEMPLATE_KEYS]
        pad = " " * (indent + decl_indent_extra)
        if any(EDITION1_ONLY.search(m.group(3)) for _, m in templates):
            lines[start + 1:start + 1] = [f"{pad}edition: 1   # 판본 1 유지 — 아래 legacy_reason", f"{pad}legacy_reason: '{LEGACY_REASON}'"]
            notes.append(f"legacy(edition 1) @{start + 1}")
            continue
        for k, m in templates:
            new = convert_template(m.group(3))
            if new != m.group(3):
                prefix = block[k][:m.start(3) - 1]  # 여는 따옴표 앞까지
                tail = block[k][m.end(3) + 1:]
                block[k] = f"{prefix}'{new}'{tail}"
        lines[start:end] = block
        lines[start + 1:start + 1] = [f"{pad}edition: 2   # 표면 바인딩 판본(2026-10-05): 치환 없이 원문+inputs, $item=행·드릴 레코드"]
        notes.append(f"edition 2 @{start + 1} ({len(templates)} templates)")
    return "\n".join(lines), notes


def main(argv: list[str]) -> int:
    check = "--check" in argv
    changed = 0
    for fp in SOURCES:
        text = fp.read_text(encoding="utf-8")
        new, notes = migrate_text(text, re.compile(r"^(\s*)app:\s*$"), 2)
        if new != text:
            changed += 1
            print(f"{fp.relative_to(ROOT)}: " + "; ".join(notes))
            if not check:
                fp.write_text(new, encoding="utf-8")
    for fp in STANDALONE:
        text = fp.read_text(encoding="utf-8")
        # 독립 매니페스트: 최상위 instrument: 줄이 블록 머리, 선언은 들여쓰기 0
        new, notes = migrate_text(text, re.compile(r"^(\s*)instrument:\s*\S"), 0, whole_file=True)
        if new != text:
            changed += 1
            print(f"{fp.relative_to(ROOT)}: " + "; ".join(notes))
            if not check:
                fp.write_text(new, encoding="utf-8")
    print(f"{'미리보기' if check else '변환'} 완료 — 파일 {changed}개")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
