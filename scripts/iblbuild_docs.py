"""iblbuild_docs.py — 문서 파생: 레지스트리 실측을 마커 구간에 재기입 (2026-08-21 신설)

## 왜 있나 — 자기상 가드의 승격 (검사 → 재생성)
check_self_image(iblbuild_guards)는 SELF_IMAGE 한 줄을 *검사만* 했다 — 두 번 재발이
증명했듯 손 수정은 답이 아니고, 검사는 위반을 알릴 뿐 소멸시키지 못한다. 이 모듈은
같은 실측을 **재기입**한다: 어휘·코드를 바꾸면 빌드 꼬리가 문서를 같은 커밋에서
갱신하고, --check 는 문서가 실측과 일치하는지 대조한다(파생 산출물 4종과 동급 시민).

## 원칙 — 수치는 기계가, 산문은 문서가 소유한다
마커 구간 안에서도 전체를 다시 쓰지 않고 **수치 토큰만 외과적으로 치환**한다
(문서의 산문·설명 열은 문서 소유 — 산문을 코드로 옮기면 문서가 코드에 종속된다).
치환 패턴이 안 잡히면 조용히 통과하지 않고 **issue 로 시끄럽게 실패**한다 —
패턴 드리프트(grep 방언 부류)를 빌드가 즉시 잡게. 예외 둘: SELF_IMAGE 한 줄과
packages.md 패키지 표는 순수 기계 소유라 전체 재발행.

## CI 안정성 — 파일 계수는 git 추적 집합
backend .py·가이드 수는 디스크가 아니라 `git ls-files` 로 센다: 로컬의 미추적
스크래치 파일이 수치에 섞이면 신선 clone CI 의 --check 가 영구 빨간불이 된다
(2026-07-26 신선 clone 게이트와 같은 부류). 패키지 수는 기존 자기상 가드와 같은
디렉토리 실측 유지(설치 상태가 곧 진실).

대상 문서·마커는 DOC_TARGETS 가 단일 진실 — 새 문서에 파생 구간을 만들면 여기 등재.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

IBL_STATS_START = "<!-- IBL_STATS:START -->"
IBL_STATS_END = "<!-- IBL_STATS:END -->"
SELF_IMAGE_START = "<!-- SELF_IMAGE:START -->"
SELF_IMAGE_END = "<!-- SELF_IMAGE:END -->"
PKG_TABLE_START = "<!-- PACKAGES_TABLE:START -->"
PKG_TABLE_END = "<!-- PACKAGES_TABLE:END -->"


# ── 실측 수집 ────────────────────────────────────────────────────────────────

def _git_ls(root: Path, pathspec: str) -> list[str] | None:
    try:
        out = subprocess.run(
            ["git", "ls-files", "--", pathspec],
            cwd=root, capture_output=True, text=True, timeout=20,
        )
        if out.returncode != 0:
            return None
        return [ln for ln in out.stdout.splitlines() if ln.strip()]
    except Exception:
        return None


def _count_pkg_dirs(root: Path, rel: str) -> int:
    d = root / rel
    if not d.is_dir():
        return 0
    return len([p for p in d.iterdir() if p.is_dir() and not p.name.startswith("__")])


def collect_doc_facts(root: Path, data: dict | None) -> dict | None:
    """문서에 기입할 실측 한 벌. data 파싱 실패 시 None(파생 스킵 — 추측 기입 금지)."""
    if not isinstance(data, dict):
        return None
    nodes = data.get("nodes") or {}
    if not nodes:
        return None
    per = {n: len(b.get("actions") or {}) for n, b in nodes.items() if isinstance(b, dict)}

    # backend .py — git 추적 + 테스트(test_*) 제외 (CI 안정성: 미추적 스크래치 배제)
    tracked = _git_ls(root, "backend/*.py") or []
    if not tracked:  # git 불가 폴백 — 있는 그대로 세되, 같은 규칙
        tracked = [str(p.relative_to(root)) for p in root.glob("backend/**/*.py")
                   if "__pycache__" not in p.parts]
    py_files = [p for p in tracked if not Path(p).name.startswith("test_")]
    layers = {}
    for layer in ("base", "datastore", "ibl", "cognition", "services", "surface",
                  "common", "providers", "channels", "drivers"):
        prefix = f"backend/{layer}/"
        layers[layer] = len([p for p in py_files
                             if p.startswith(prefix) and "/" not in p[len(prefix):]])

    guides = _git_ls(root, "data/guides/*.md")
    guides_n = len(guides) if guides is not None else len(list((root / "data/guides").glob("*.md")))
    guide_db_n = None
    try:
        gdb = json.loads((root / "data/guide_db.json").read_text(encoding="utf-8"))
        entries = gdb.get("guides", gdb) if isinstance(gdb, dict) else gdb
        guide_db_n = len(entries)
    except Exception:
        pass

    ops_actions = 0
    se = {"true": 0, "false": 0, "none": 0}
    runs_on = {"anywhere": 0, "pc_only": 0, "phone_only": 0}
    for b in nodes.values():
        for a in (b.get("actions") or {}).values():
            if not isinstance(a, dict):
                continue
            if a.get("ops"):
                ops_actions += 1
            v = a.get("side_effect")
            se["none" if v is None else ("true" if v else "false")] += 1
            ro = a.get("runs_on") or "anywhere"
            runs_on[ro] = runs_on.get(ro, 0) + 1

    tools_dir = root / "data/packages/installed/tools"
    op_pkgs = 0
    packages = []  # (id, name, desc) — packages.md 표 재발행용
    if tools_dir.is_dir():
        for p in sorted(tools_dir.iterdir()):
            if not p.is_dir() or p.name.startswith("__"):
                continue
            name, desc = p.name, ""
            try:
                tj = json.loads((p / "tool.json").read_text(encoding="utf-8"))
                name = tj.get("name") or p.name
                desc = (tj.get("description") or "").replace("\n", " ").replace("|", "/").strip()
            except Exception:
                pass
            packages.append((p.name, name, desc))
            try:
                if "_OP_DISPATCHERS" in (p / "handler.py").read_text(encoding="utf-8"):
                    op_pkgs += 1
            except Exception:
                pass

    return {
        "nodes": per,
        "node_count": len(per),
        "total": sum(per.values()),
        "tools_n": _count_pkg_dirs(root, "data/packages/installed/tools"),
        "exts_n": _count_pkg_dirs(root, "data/packages/installed/extensions"),
        "backend_py": len(py_files),
        "layers": layers,
        "guides_n": guides_n,
        "guide_db_n": guide_db_n,
        "ops_actions": ops_actions,
        "op_pkgs": op_pkgs,
        "side_effect": se,
        "runs_on": runs_on,
        "packages": packages,
    }


# ── 치환 도구 ────────────────────────────────────────────────────────────────

def _sub(span: str, pattern: str, repl, label: str, issues: list[str]) -> str:
    """패턴 1회 이상 치환. 불발이면 issue — 조용한 무시는 드리프트의 시작이다."""
    new, n = re.subn(pattern, repl, span)
    if n == 0:
        issues.append(f"{label}: 치환 패턴 불발 — /{pattern}/")
    return new


def _sub_node_counts(span: str, facts: dict, dialect: str, label: str, issues: list[str]) -> str:
    """노드별 액션 수 치환. dialect: 'compact'=`sense 40` / 'paren'=`sense`(…, 40) /
    'table'=| **sense** | 40 |"""
    doc_nodes = set()
    for node, count in facts["nodes"].items():
        if dialect == "compact":
            pat = rf"(?<![a-z_])({node})\s+(\d+)"
            rep = rf"\g<1> {count}"
        elif dialect == "paren":
            pat = rf"(`?{node}`?\(([^)0-9]*))(\d+)(\))"
            rep = rf"\g<1>{count}\g<4>"
        else:  # table
            pat = rf"(\|\s*\*\*{node}\*\*\s*\|\s*)(\d+)(\s*\|)"
            rep = rf"\g<1>{count}\g<3>"
        new, n = re.subn(pat, rep, span)
        if n == 0:
            issues.append(f"{label}: 노드 '{node}' 수치 자리 불발({dialect})")
        else:
            doc_nodes.add(node)
        span = new
    return span


# ── 구간 렌더러 (문서별) ─────────────────────────────────────────────────────

def _render_self_image(span: str, facts: dict, issues: list[str]) -> str:
    # 순수 기계 소유 한 줄 — 전체 재발행 (형식은 check_self_image 의 파서와 계약)
    per = "·".join(f"{n} {c}" for n, c in facts["nodes"].items())
    return (f"**현 상태 = {facts['node_count']}노드 {facts['total']} 액션({per})"
            f"·{facts['tools_n']} 도구 패키지 + {facts['exts_n']} extensions"
            f"·backend .py {facts['backend_py']}(test 제외)**")


def _render_readme_en(span: str, f: dict, issues: list[str]) -> str:
    span = _sub(span, r"\*\*(\d+) nodes, (\d+) composable actions\*\*",
                f"**{f['node_count']} nodes, {f['total']} composable actions**",
                "README.md 총계", issues)
    span = _sub(span, r"not (\d+) schemas", f"not {f['total']} schemas",
                "README.md 스키마 수", issues)
    span = _sub_node_counts(span, f, "table", "README.md", issues)
    span = _sub(span, r"\((\d+) installed, plus (\d+) backend core modules\)",
                f"({f['tools_n']} installed, plus {f['exts_n']} backend core modules)",
                "README.md 패키지", issues)
    return span


def _render_readme_ko(span: str, f: dict, issues: list[str]) -> str:
    span = _sub(span, r"\*\*(\d+)개 노드, (\d+)개 조합 가능한 액션\*\*",
                f"**{f['node_count']}개 노드, {f['total']}개 조합 가능한 액션**",
                "README.ko.md 총계", issues)
    span = _sub(span, r"(\d+)개 스키마가", f"{f['total']}개 스키마가",
                "README.ko.md 스키마 수", issues)
    span = _sub_node_counts(span, f, "table", "README.ko.md", issues)
    span = _sub(span, r"설치 (\d+)개 \+ 백엔드 코어 모듈 (\d+)개",
                f"설치 {f['tools_n']}개 + 백엔드 코어 모듈 {f['exts_n']}개",
                "README.ko.md 패키지", issues)
    return span


def _render_anatomy(span: str, f: dict, issues: list[str]) -> str:
    span = _sub(span, r"\*\*(\d+)개 노드 (\d+) 액션\*\*",
                f"**{f['node_count']}개 노드 {f['total']} 액션**", "anatomy.md 총계", issues)
    span = _sub_node_counts(span, f, "paren", "anatomy.md", issues)
    return span


def _render_architecture(span: str, f: dict, issues: list[str]) -> str:
    L, se = f["layers"], f["side_effect"]
    span = _sub(span, r"도구 패키지: \*\*(\d+)개\*\* \(\+ 백엔드 extensions \*\*(\d+)개\*\*\)",
                f"도구 패키지: **{f['tools_n']}개** (+ 백엔드 extensions **{f['exts_n']}개**)",
                "architecture.md 패키지", issues)
    per = "·".join(f"{n} {c}" for n, c in f["nodes"].items())
    span = _sub(span, r"\*\*(\d+)노드 (\d+) 액션\*\* \([^)]*\)",
                f"**{f['node_count']}노드 {f['total']} 액션** ({per})",
                "architecture.md IBL", issues)
    # ★치환 결과는 매치와 같은 모양이어야 멱등이다 — "(test 제외)" 같은 부가 문구는
    #   문서 산문에 두고, 여기서는 숫자만 갈아끼운다.
    span = _sub(span, r"backend \*\*\.py (\d+)개\*\*",
                f"backend **.py {f['backend_py']}개**",
                "architecture.md backend", issues)
    span = _sub(span, r"base (\d+) · datastore (\d+) · ibl (\d+) · cognition (\d+) · services (\d+) · surface (\d+)",
                f"base {L['base']} · datastore {L['datastore']} · ibl {L['ibl']} · "
                f"cognition {L['cognition']} · services {L['services']} · surface {L['surface']}",
                "architecture.md 층", issues)
    span = _sub(span, r"common (\d+)·providers (\d+)·channels (\d+)·drivers (\d+)",
                f"common {L['common']}·providers {L['providers']}·channels {L['channels']}·drivers {L['drivers']}",
                "architecture.md 층밖", issues)
    if f["guide_db_n"] is not None:
        span = _sub(span, r"가이드 \*\*(\d+)개\*\*\(guide_db 등록 \*\*(\d+)\*\*\)",
                    f"가이드 **{f['guides_n']}개**(guide_db 등록 **{f['guide_db_n']}**)",
                    "architecture.md 가이드", issues)
    span = _sub(span, r"op 분기 액션 \*\*(\d+)개\*\*",
                f"op 분기 액션 **{f['ops_actions']}개**", "architecture.md op액션", issues)
    span = _sub(span, r"\*\*(\d+)개 패키지\*\*",
                f"**{f['op_pkgs']}개 패키지**", "architecture.md op패키지", issues)
    span = _sub(span, r"true (\d+)·false (\d+)·미선언 (\d+)",
                f"true {se['true']}·false {se['false']}·미선언 {se['none']}",
                "architecture.md side_effect", issues)
    return span


def _render_technical(span: str, f: dict, issues: list[str]) -> str:
    L = f["layers"]
    span = _sub(span,
                r"`base`\((\d+)\) → `datastore`\((\d+)\) → `ibl`\((\d+)\) → `cognition`\((\d+)\) → `services`\((\d+)\) → `surface`\((\d+)\)",
                f"`base`({L['base']}) → `datastore`({L['datastore']}) → `ibl`({L['ibl']}) → "
                f"`cognition`({L['cognition']}) → `services`({L['services']}) → `surface`({L['surface']})",
                "technical.md 층", issues)
    span = _sub(span, r"`\.py` 총 (\d+)개",
                f"`.py` 총 {f['backend_py']}개", "technical.md backend", issues)
    span = _sub(span, r"`backend/common/`\((\d+)\) · `backend/providers/`\((\d+)([^)]*)\) · `backend/channels/`\((\d+)\) · `backend/drivers/`\((\d+)\)",
                f"`backend/common/`({L['common']}) · `backend/providers/`({L['providers']}, AI 프로바이더 스트리밍) · "
                f"`backend/channels/`({L['channels']}) · `backend/drivers/`({L['drivers']})",
                "technical.md 층밖", issues)
    span = _sub(span, r"설치된 도구 패키지 \(\*\*(\d+)개\*\* — op 분기 \*\*(\d+)개\*\*",
                f"설치된 도구 패키지 (**{f['tools_n']}개** — op 분기 **{f['op_pkgs']}개**",
                "technical.md 패키지", issues)
    span = _sub(span, r"백엔드 코어 모듈 \(\*\*(\d+)개\*\*\)",
                f"백엔드 코어 모듈 (**{f['exts_n']}개**)", "technical.md extensions", issues)
    if f["guide_db_n"] is not None:
        span = _sub(span, r"가이드 (\d+)개 \(guide_db 등록 (\d+)\)",
                    f"가이드 {f['guides_n']}개 (guide_db 등록 {f['guide_db_n']})",
                    "technical.md 가이드", issues)
    return span


def _render_ibl(span: str, f: dict, issues: list[str]) -> str:
    span = _sub(span, r"총 \*\*(\d+) 액션\*\*", f"총 **{f['total']} 액션**",
                "ibl.md 총계", issues)
    span = _sub_node_counts(span, f, "compact", "ibl.md", issues)
    return span


def _render_ibl_runs_on(span: str, f: dict, issues: list[str]) -> str:
    r = f["runs_on"]
    return _sub(span, r"`anywhere` (\d+) · `pc_only` (\d+) · `phone_only` (\d+)",
                f"`anywhere` {r['anywhere']} · `pc_only` {r['pc_only']} · `phone_only` {r['phone_only']}",
                "ibl.md runs_on", issues)


def _render_inventory(span: str, f: dict, issues: list[str]) -> str:
    per = " · ".join(f"{n} {c}" for n, c in f["nodes"].items())
    span = _sub(span, r"\*\*(\d+)노드 (\d+) 액션\*\* — [^\n]*",
                f"**{f['node_count']}노드 {f['total']} 액션** — {per}",
                "inventory.md 총계", issues)
    span = _sub(span, r"op 분기 액션 (\d+)개 / op 분기 패키지 (\d+)개",
                f"op 분기 액션 {f['ops_actions']}개 / op 분기 패키지 {f['op_pkgs']}개",
                "inventory.md op", issues)
    return span


def _render_packages_head(span: str, f: dict, issues: list[str]) -> str:
    span = _sub(span, r"## 현재 설치된 도구 패키지 \((\d+)개",
                f"## 현재 설치된 도구 패키지 ({f['tools_n']}개",
                "packages.md 헤더", issues)
    span = _sub(span, r"\*\*op 분기 (\d+) 패키지\*\*",
                f"**op 분기 {f['op_pkgs']} 패키지**", "packages.md op패키지", issues)
    span = _sub(span, r"op 분기 액션은 \*\*(\d+)개\*\*",
                f"op 분기 액션은 **{f['ops_actions']}개**", "packages.md op액션", issues)
    return span


def _render_packages_table(span: str, f: dict, issues: list[str]) -> str:
    """행 *집합*만 기계가 관리 — 설명 산문은 문서 소유(불가침).
    은퇴 패키지 행은 삭제, 누락 행은 tool.json 설명으로 추가(사람이 나중에 풍부화)."""
    installed = {pid: (name, desc) for pid, name, desc in f["packages"]}
    kept: dict[str, str] = {}
    header: list[str] = []
    for line in span.splitlines():
        m = re.match(r"\|\s*([a-z0-9_-]+)\s*\|", line)
        if line.strip().startswith("| ID") or line.strip().startswith("|--"):
            header.append(line)
        elif m:
            pid = m.group(1)
            if pid in installed:
                kept[pid] = line  # 큐레이션 산문 보존
            # 미설치 id 행은 버린다(은퇴 행 자동 소멸)
    if not header:
        header = ["| ID | 이름 | 설명 |", "|----|------|------|"]
    lines = list(header)
    for pid in sorted(installed):
        if pid in kept:
            lines.append(kept[pid])
        else:
            name, desc = installed[pid]
            lines.append(f"| {pid} | {name} | {desc[:80]} |")
    return "\n" + "\n".join(lines) + "\n"


def _render_packages_ext(span: str, f: dict, issues: list[str]) -> str:
    return _sub(span, r"## 백엔드 코어 모듈 \(extensions/\) — (\d+)개",
                f"## 백엔드 코어 모듈 (extensions/) — {f['exts_n']}개",
                "packages.md extensions", issues)


# 대상 목록 — (상대경로, START 마커, END 마커, 렌더러). 같은 문서에 구간 여러 개 가능.
DOC_TARGETS = [
    ("data/system_docs/system_structure.md", SELF_IMAGE_START, SELF_IMAGE_END, _render_self_image),
    ("README.md", IBL_STATS_START, IBL_STATS_END, _render_readme_en),
    ("README.ko.md", IBL_STATS_START, IBL_STATS_END, _render_readme_ko),
    ("data/system_docs/anatomy.md", IBL_STATS_START, IBL_STATS_END, _render_anatomy),
    ("data/system_docs/architecture.md", IBL_STATS_START, IBL_STATS_END, _render_architecture),
    ("data/system_docs/technical.md", IBL_STATS_START, IBL_STATS_END, _render_technical),
    ("data/system_docs/ibl.md", IBL_STATS_START, IBL_STATS_END, _render_ibl),
    ("data/system_docs/ibl.md", "<!-- RUNS_ON:START -->", "<!-- RUNS_ON:END -->", _render_ibl_runs_on),
    ("data/system_docs/inventory.md", IBL_STATS_START, IBL_STATS_END, _render_inventory),
    ("data/system_docs/packages.md", IBL_STATS_START, IBL_STATS_END, _render_packages_head),
    ("data/system_docs/packages.md", PKG_TABLE_START, PKG_TABLE_END, _render_packages_table),
    ("data/system_docs/packages.md", "<!-- EXT_COUNT:START -->", "<!-- EXT_COUNT:END -->", _render_packages_ext),
]


# ── 적용/검사 ────────────────────────────────────────────────────────────────

def _render_doc(root: Path, rel: str, facts: dict) -> tuple[str | None, list[str]]:
    """한 문서의 모든 파생 구간을 렌더한 전체 텍스트와 issue 목록."""
    fp = root / rel
    if not fp.is_file():
        return None, [f"{rel}: 문서 부재"]
    text = fp.read_text(encoding="utf-8")
    issues: list[str] = []
    for path, start, end, renderer in DOC_TARGETS:
        if path != rel:
            continue
        if start not in text or end not in text:
            issues.append(f"{rel}: 마커 부재 — {start}…{end}")
            continue
        pre, rest = text.split(start, 1)
        span, post = rest.split(end, 1)
        new_span = renderer(span, facts, issues)
        text = pre + start + new_span + end + post
    return text, issues


def apply_docs(root: Path, data: dict | None) -> tuple[list[str], list[str]]:
    """빌드 꼬리: 파생 구간 재기입. (쓴 문서 목록, issue 목록) 반환 — 멱등 diff-write."""
    facts = collect_doc_facts(root, data)
    if facts is None:
        return [], ["실측 수집 불가(data 없음) — 문서 파생 스킵"]
    written, issues = [], []
    for rel in dict.fromkeys(t[0] for t in DOC_TARGETS):
        new_text, doc_issues = _render_doc(root, rel, facts)
        issues.extend(doc_issues)
        if new_text is None:
            continue
        fp = root / rel
        if fp.read_text(encoding="utf-8") != new_text:
            fp.write_text(new_text, encoding="utf-8")
            written.append(rel)
    return written, issues


def check_docs(root: Path, data: dict | None) -> list[str]:
    """--check: 파생 구간이 실측과 일치하는지. 불일치·패턴 불발 전부 issue."""
    facts = collect_doc_facts(root, data)
    if facts is None:
        return []  # data 파싱 실패는 삼각 검증이 이미 잡는다 — 이중 보고 안 함
    issues: list[str] = []
    for rel in dict.fromkeys(t[0] for t in DOC_TARGETS):
        new_text, doc_issues = _render_doc(root, rel, facts)
        issues.extend(doc_issues)
        if new_text is None:
            continue
        if (root / rel).read_text(encoding="utf-8") != new_text:
            issues.append(f"{rel}: 파생 구간 stale — `python3 scripts/build_ibl_nodes.py` 로 재생성 필요")
    return issues
