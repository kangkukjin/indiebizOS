"""가지 문서 기질 — 세 트리 기억(실행 hippo_tree · 심층 memory_tree · 포식 forage_doc)의 문서 공통부.

문서가 정본, DB 는 색인. 세 기억은 같은 원리로 문서를 다룬다 — 머리의 `<!-- 표식 -->`, `## 절` 하나에 기계가 읽는 줄들,
`> 한 줄 요약`, `## 갱신 기록`, 문서가 색인보다 새로우면(사람·AI 가 고쳤으면) 절을 읽어 색인을 맞추는 동기화, 다시 그린 뒤
mtime 도장. 2026-09-18 판정(사용자: 같은 원리로 작동하는 부분은 구현까지 공유): 그 공통부를 여기 한 벌로 두고 세 모듈은
자기 것만 남긴다 — **줄의 문법**(후보의 뜻: 용례·기억·단언), **식별**(id 냐 (장소·종류·문장) 냐), **검증**(IBL 구문·몸 명사·
관용구 문장 수), **저장**(어느 표·어느 색인). 그것들은 호출자가 인자·콜백으로 준다. 이 모듈은 파일과 문자열만 안다.

정본 설계: docs/ASSOCIATIVE_RECALL_COMMON_FLOW_2026_09_18.md §9.
"""
import os
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

LEDGER = "## 갱신 기록"
GIST_PLACEHOLDER_PREFIX = "(한 줄 요약"


# ─────────────────────────── 표식 ───────────────────────────

def marker_line(kind: str, **attrs: str) -> str:
    """`<!-- kind a="v" b="w" -->` — 속성 순서는 준 순서."""
    body = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return f"<!-- {kind} {body} -->" if body else f"<!-- {kind} -->"


def marker_re(kind: str, *keys: str) -> "re.Pattern[str]":
    """표식 정규식 — keys 순서대로 값을 잡는다. 뒤에 붙은 다른 속성(옛 dir_id 같은 것)은 허용한다."""
    parts = "".join(rf'\s+{re.escape(k)}="([^"]*)"' for k in keys)
    return re.compile(rf'<!--\s*{re.escape(kind)}{parts}(?:\s+\w+="[^"]*")*\s*-->')


def read_marker(source: str, kind: str, keys: Sequence[str], *, head_chars: int = 2000) -> Optional[Tuple[str, ...]]:
    """파일 경로면 머리만 읽고, 아니면 그 문자열에서 표식을 찾는다. 없으면 None."""
    text = source
    if "\n" not in source and os.path.exists(source):
        try:
            with open(source, encoding="utf-8") as f:
                text = f.read(head_chars)
        except OSError:
            return None
    m = marker_re(kind, *keys).search(text[:head_chars] if len(text) > head_chars else text)
    return tuple(m.groups()) if m else None


def ensure_marker(text: str, line: str, pattern: "re.Pattern[str]", *, head_chars: int = 2000) -> str:
    """머리에 표식이 없으면 맨 앞에 붙인다(있으면 그대로)."""
    return text if pattern.search(text[:head_chars]) else line + "\n" + text


# ─────────────────────────── 절 ───────────────────────────

def split_section(text: str, heading: str, anchors: Sequence[str] = (LEDGER,)) -> Tuple[str, str, str]:
    """(앞, 절, 뒤). 절 = `^## 제목$` 부터 다음 `^## ` 앞까지. 절이 없으면 절='' 이고 뒤는 첫 anchor(기본 갱신 기록)부터 —
    그 자리가 새 절이 들어갈 곳이다. anchor 도 없으면 (전부, '', '')."""
    m = re.search(rf"(?m)^{re.escape(heading)}\s*$", text)
    if m:
        nxt = re.search(r"(?m)^## ", text[m.end():])
        end = m.end() + nxt.start() if nxt else len(text)
        return text[:m.start()], text[m.start():end], text[end:]
    for a in anchors:
        am = re.search(rf"(?m)^{re.escape(a)}\s*$", text)
        if am:
            return text[:am.start()], "", text[am.start():]
    return text, "", ""


def replace_section(text: str, heading: str, section: str, anchors: Sequence[str] = (LEDGER,)) -> str:
    """절을 통째로 바꾼다(없으면 anchor 앞에 넣는다). 앞은 빈 줄로 띄우고, 뒤가 바로 이어지면 줄바꿈 하나를 둔다."""
    head, _old, tail = split_section(text, heading, anchors)
    if head and not head.endswith("\n\n"):
        head = head.rstrip("\n") + "\n\n"
    if tail and not tail.startswith("\n"):
        section = section + "\n"
    return head + section + tail


def section_body(text: str, heading: str) -> str:
    """절의 본문(제목 줄·`<!-- -->` 주석 줄 제외)."""
    sec = split_section(text, heading)[1]
    lines = sec.splitlines()[1:] if sec else []
    return "\n".join(l for l in lines if not l.startswith("<!--")).strip("\n")


def append_ledger(text: str, line: str) -> str:
    """`## 갱신 기록` 에 한 줄(절이 없으면 만든다). 갱신 기록은 문서의 마지막 절이다."""
    if LEDGER not in text:
        text = text.rstrip() + "\n\n" + LEDGER + "\n"
    return text.rstrip("\n") + "\n" + line + "\n"


# ─────────────────────────── 머리 ───────────────────────────

def gist_of(path: str, *, head_chars: int = 3000) -> str:
    """표식 뒤 첫 `> ` 줄 = 목차에 실리는 한 줄 요약. 자리표는 요약이 아니다."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(head_chars)
    except OSError:
        return ""
    m = re.search(r"(?m)^>\s*(.+?)\s*$", text)
    g = m.group(1).strip() if m else ""
    return "" if g.startswith(GIST_PLACEHOLDER_PREFIX) else g


def skeleton(marker: str, title: str, gist_placeholder: str, *, extra: Iterable[str] = (),
             ledger_first: str = "가지 생성", today: Optional[str] = None) -> str:
    """새 가지 문서의 껍데기 — 표식·제목·요약 자리표·(추가 머리 줄)·갱신 기록 첫 줄. 기계 절은 호출자가 replace_section 으로 넣는다."""
    from datetime import datetime
    day = today or datetime.now().strftime("%Y-%m-%d")
    lines = [marker, f"# {title}", f"> {gist_placeholder}"]
    lines.extend(x for x in extra if x)
    return "\n".join(lines) + f"\n\n{LEDGER}\n- {day} {ledger_first}\n"


# ─────────────────────────── 줄 ───────────────────────────

def one_line(text: Any) -> str:
    return re.sub(r"\s*\n+\s*", " ", str(text or "").strip())


def meta(parts: Iterable[Any]) -> str:
    """줄 꼬리의 `‹a · b›` — 빈 조각은 뺀다."""
    return "‹" + " · ".join(str(p) for p in parts if p) + "›"


# ─────────────────────────── 도장(mtime) ───────────────────────────

def stamp_value(path: str) -> str:
    return str(os.path.getmtime(path))


def is_stale(path: str, stamp: Any) -> bool:
    """문서가 마지막 렌더 도장보다 새로운가 — 우리 쓰기는 정확히 그 mtime 으로 도장 찍으므로 그 뒤의 편집만 잡는다.
    도장이 없으면 새것으로 본다. 파일이 없으면 거짓."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return False
    try:
        return mtime > float(stamp) + 1e-6
    except (TypeError, ValueError):
        return True


# ─────────────────────────── 동기화 계획 (문서 → 색인) ───────────────────────────

def plan_sync(known: List[Dict[str, Any]], fresh: List[Dict[str, Any]], existing: List[Dict[str, Any]], *,
              key: Callable[[Dict[str, Any]], Any], changed: Callable[[Dict[str, Any], Dict[str, Any]], bool]) -> Dict[str, list]:
    """세 갈래 계획 — 실행은 호출자(기억별 SQL·색인·검증)가 한다.

    known: 문서에서 읽은, 식별자를 가진 줄. fresh: 식별자 없는 새 줄. existing: 색인의 현재 행.
    key(row) 는 양쪽에 같은 식별자를 준다(심층·실행 = id, 포식 = (장소·종류·문장)). changed(parsed, row) 가 참이면 갱신.
    반환 {"update": [(parsed, row)], "delete": [row], "insert": [parsed], "unchanged": n}.
    문서에는 있는데 색인에 없는 식별자(옛 id·다른 곳에서 온 줄)는 새 줄로 본다 — 사람이 적은 것은 잃지 않는다.
    """
    by_key = {key(r): r for r in existing}
    seen = set()
    update, insert, unchanged = [], [], 0
    for k in known:
        kk = key(k)
        row = by_key.get(kk)
        if row is None:
            insert.append(k)
            continue
        seen.add(kk)
        if changed(k, row):
            update.append((k, row))
        else:
            unchanged += 1
    delete = [row for kk, row in by_key.items() if kk not in seen]
    insert.extend(fresh)
    return {"update": update, "delete": delete, "insert": insert, "unchanged": unchanged}
