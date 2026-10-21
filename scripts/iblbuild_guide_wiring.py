"""
iblbuild_guide_wiring.py — 가이드 배선 가드 (iblbuild_validators.py 에서 분할, 2026-09-05 1500줄 관문).
guide_db 의 실존·코드 경로·고아 판정. build_ibl_nodes 는 iblbuild_validators 의 재수출 이름으로 부른다.
"""
from __future__ import annotations
from pathlib import Path


def markdown_references(source: str) -> list[str]:
    """코드 펜스/인라인 코드를 제외한 로컬 Markdown 문서 링크."""
    import re
    from urllib.parse import unquote, urlsplit
    source = re.sub(r"(?ms)^([ \t]*)(`{3,}|~{3,})[^\n]*\n.*?^\1(?:`{3,}|~{3,})[^\n]*$", "", source)
    source = re.sub(r"`+[^`\n]*`+", "", source)
    targets = re.findall(r"\[[^]\n]+\]\(<?([^\s)>]+)>?(?:\s+[^)]*)?\)", source)
    targets += re.findall(r"(?m)^\s*\[[^]]+\]:\s*<?([^\s>]+)", source)
    result = []
    for target in targets:
        parsed = urlsplit(target)
        if not parsed.scheme and not parsed.netloc and parsed.path.endswith(".md"):
            result.append(unquote(parsed.path))
    return result


# === 가이드 위생 가드 (2026-08-17) ===
# 가이드는 '절차 기억'이고 기억처럼 낡는다. 그런데 어휘 은퇴 절차에는 **코퍼스 이관 의무는
# 있어도(--check 코퍼스 param 가드가 실제로 강제한다) 가이드 정리 의무는 없었다.**
# 2026-08-17 정리에서 79→67개·81KB 를 걷어낸 것이 그 비대칭의 누적 청구서였다.
# 여기서 그 의무를 기계에 넘긴다 — 사실 관계는 하드 실패, 판단이 필요한 것은 비차단 경고.

def validate_guide_wiring(root: Path) -> list[str]:
    """가이드 배선 하드 검증 — 사실만, 판단 없음.

    ①guide_db 가 없는 파일을 가리킴(= read_guide 침묵 실패)
    ②가이드가 가리키는 backend 경로가 실존하지 않음(= 층 이동 후 끊긴 안내)

    ②를 넣는 이유: 2026-08-05 층 물리 이동 뒤 8건이 끊겨 있었는데, 모듈 이름이
    평면이라 import 는 안 깨져 **조용히** 낡았다. 가이드는 사람·AI 가 코드를 찾는
    지도라, 지도가 틀리면 자기 코드를 못 찾는다.
    """
    import json as _json
    import re as _re

    issues: list[str] = []
    guides_dir = root / "data" / "guides"
    if not guides_dir.is_dir():
        return issues
    files = {p.name for p in guides_dir.glob("*.md")}

    db_path = root / "data" / "guide_db.json"
    if db_path.exists():
        try:
            entries = _json.loads(db_path.read_text(encoding="utf-8")).get("guides", [])
        except Exception as e:
            return [f"가이드 가드: guide_db.json 을 읽지 못함 ({e})"]
        from guide_registry import guide_reference_owners, resolve_guide_reference
        try:
            owners = guide_reference_owners(entries)
            for name, indexes in owners.items():
                if len(indexes) > 1:
                    issues.append(f"가이드 참조 소유권 충돌: {name}")
            for entry in entries:
                result = resolve_guide_reference(entry["file"], entries, guides_dir, read=False)
                if not result or result.get("error"):
                    issues.append(f"guide_db 유령 등재/잘못된 대상: {entry.get('id')} → {entry.get('file')}")
        except (KeyError, TypeError, AttributeError):
            issues.append("가이드 목차 항목 형식 오류")
    else:
        issues.append("가이드 목차 guide_db.json 누락")

    path_re = _re.compile(r"`(backend/[A-Za-z0-9_/]+\.py)`")
    for name in sorted(files):
        try:
            src = (guides_dir / name).read_text(encoding="utf-8")
        except OSError:
            continue
        for rel in sorted(set(markdown_references(src))):
            target = (guides_dir / rel).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                issues.append(f"[{name}] 끊긴 문서 링크: {rel}")
        for rel in sorted(set(path_re.findall(src))):
            if not (root / rel).exists():
                base = Path(rel).name
                hit = ""
                for d in (root / "backend").rglob(base):
                    if "__pycache__" not in str(d):
                        hit = f" → 실제 위치 backend/{d.relative_to(root / 'backend')}"
                        break
                issues.append(f"[{name}] 끊긴 코드 경로: {rel}{hit}")
    return issues


# 2026-08-17 동결 — 이 시점에 남아 있는 '설명된 죽은 참조'(은퇴 기록·가상의 제안)와
# 코드가 경로로 직접 읽는 고아 셋. 새 진입만 경고한다.
_GUIDE_ORPHAN_BASELINE = {
    "world_pulse.md",     # 런타임 산출물 — world_pulse.py 가 쓰고 prompt_builder 가 읽음
    "forage_search.md",   # api_system_ai.py 가 경로로 직접 읽음
}


def guide_staleness_warnings(data: dict, root: Path) -> list[str]:
    """가이드 부패 경고(비차단) — 판단이 필요한 신호만.

    ①죽은 어휘 참조: 은퇴/제안임을 밝히는 문맥이면 면제(그건 기록이지 오류가 아니다).
    ②살아있는 어휘 0 + 죽은 어휘 ≥1: 은퇴·미설치 능력의 가이드 냄새.
    ③고아: guide_db·노드 yaml 어디도 안 가리킴(= 검색으로 못 찾는 파일).

    ★전부 경고인 이유: 2026-08-17 정리에서 `remotion.md` 를 묘비로 남길지 지울지는
    기계가 못 정했고 실제로 사용자 판정으로 뒤집혔다. 검출은 시스템, 결정은 사람.
    """
    import json as _json
    import re as _re

    warns: list[str] = []
    guides_dir = root / "data" / "guides"
    if not guides_dir.is_dir():
        return warns
    files = sorted(p.name for p in guides_dir.glob("*.md"))

    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    live = {f"{n}:{a}" for n, v in nodes.items()
            if isinstance(v, dict) for a in (v.get("actions") or {})}
    if not live:
        return warns

    referenced = set()
    db_path = root / "data" / "guide_db.json"
    if db_path.exists():
        try:
            for e in _json.loads(db_path.read_text(encoding="utf-8")).get("guides", []):
                referenced.add(Path(str(e.get("file") or "")).name)
                referenced.update(Path(alias).name for alias in e.get("aliases", [])
                                  if isinstance(alias, str) and alias.endswith(".md"))
        except Exception:
            pass
    for _n, v in nodes.items():
        if isinstance(v, dict):
            referenced.update(str(g) for g in (v.get("guides") or []))
            for a in (v.get("actions") or {}).values():
                if isinstance(a, dict):
                    referenced.update(str(g) for g in (a.get("guides") or []))

    for filename in files:
        for rel in markdown_references((guides_dir / filename).read_text(encoding="utf-8")):
            target = (guides_dir / rel).resolve()
            if target.parent == guides_dir.resolve():
                referenced.add(target.name)

    act_re = _re.compile(r"\[([a-z_]+):([a-z_]+)\]")
    # 은퇴/제안임을 밝히는 말 — 이런 문맥의 죽은 이름은 기록이지 오류가 아니다
    excused = _re.compile(r"구 |은퇴|폐지|개명|흡수|승격|부활|아직 없는|가상의|제안|통합|합병|없습니다|아니다|자리표시자")

    for name in files:
        try:
            lines = (guides_dir / name).read_text(encoding="utf-8").split("\n")
        except OSError:
            continue
        dead_unexcused, dead_all, live_hits = set(), set(), 0
        for i, line in enumerate(lines):
            ctx = " ".join(lines[max(0, i - 1): i + 4])
            for node, act in act_re.findall(line):
                if node not in nodes:
                    continue
                ref = f"{node}:{act}"
                if ref in live:
                    live_hits += 1
                    continue
                dead_all.add(ref)
                if not excused.search(ctx):
                    dead_unexcused.add(ref)
        if dead_unexcused:
            warns.append(
                f"[{name}] 설명 없는 죽은 어휘 참조: {', '.join(sorted(dead_unexcused))} "
                "(후계 어휘로 고치거나, 은퇴 기록임을 문장으로 밝힐 것)"
            )
        if dead_all and live_hits == 0:
            warns.append(
                f"[{name}] 살아있는 어휘를 하나도 안 부른다 (죽은 참조만 {len(dead_all)}종) "
                "— 은퇴·미설치 능력의 가이드일 수 있다"
            )
        if name not in referenced and name not in _GUIDE_ORPHAN_BASELINE:
            warns.append(
                f"[{name}] 고아 — guide_db·노드 yaml·가이드 링크 어디도 안 가리킨다 "
                "(직접 이름 조회는 가능; 발견 경로가 필요한지 검토)"
            )
    return warns
