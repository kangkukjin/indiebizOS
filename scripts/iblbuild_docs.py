"""iblbuild_docs.py — 문서 파생: 레지스트리 실측을 마커 구간에 재기입 (2026-08-21 신설)

## 왜 있나 — 자기상 가드의 승격 (검사 → 재생성)
check_self_image(iblbuild_guards)는 SELF_IMAGE 한 줄을 *검사만* 했다 — 두 번 재발이
증명했듯 손 수정은 답이 아니고, 검사는 위반을 알릴 뿐 소멸시키지 못한다. 이 모듈은
같은 실측을 **재기입**한다: 어휘·코드를 바꾸면 빌드 꼬리가 문서를 같은 커밋에서
갱신하고, --check 는 문서가 실측과 일치하는지 대조한다(파생 산출물 4종과 동급 시민).

## 원칙 — 편집 원문과 파생 구간을 분리한다
`docs/generated_templates/`가 산문·설명 열의 정본이다. 마커 안은 그 템플릿과 레지스트리
실측으로 통째 생성한다. 기존 문장의 표현·숫자 자리를 정규식으로 추측하지 않는다.
알 수 없는 슬롯·빠진 템플릿·중복/역순 마커는 빌드 실패이며 마커 밖 산문은 보존한다.

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
import yaml
from pathlib import Path
from functools import partial
from iblbuild_common import atomic_write_text

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
    routers: dict = {}
    for b in nodes.values():
        for a in (b.get("actions") or {}).values():
            if not isinstance(a, dict):
                continue
            if a.get("ops"):
                ops_actions += 1
            routers[a.get("router") or "(미지정)"] = routers.get(a.get("router") or "(미지정)", 0) + 1
            v = a.get("side_effect")
            se["none" if v is None else ("true" if v else "false")] += 1
            ro = a.get("runs_on") or "anywhere"
            runs_on[ro] = runs_on.get(ro, 0) + 1

    tools_dir = root / "data/packages/installed/tools"
    op_packages = []
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
                    op_packages.append(p.name)
            except Exception:
                pass

    api_tools = None
    try:
        api_tools = yaml.safe_load((root / "data/api_registry.yaml").read_text(encoding="utf-8"))["tools"]
    except (OSError, KeyError, TypeError, yaml.YAMLError):
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
        "op_pkgs": len(op_packages),
        "op_package_names": " · ".join(op_packages),
        "node_descriptions": {n: b.get("description", "") for n, b in nodes.items()},
        "api_tools_n": len(api_tools) if isinstance(api_tools, dict) else None,
        "api_bound_n": sum(bool(t.get("node")) for t in api_tools.values()) if isinstance(api_tools, dict) else None,
        "side_effect": se,
        "runs_on": runs_on,
        "routers": routers,
        "packages": packages,
    }


# ── 템플릿 렌더링 ─────────────────────────────────────────────────────────────

def _template_values(f: dict, curation: dict, grammar: dict) -> dict:
    """집합·표시값만 코드가 파생하고 저술 설명은 별도 원문에서 가져온다."""
    values = dict(f)
    for key in ("nodes", "layers", "side_effect", "runs_on"):
        values.update({f"{key}_{name}": value for name, value in f[key].items()})
    per = [f"{n} {c}" for n, c in f["nodes"].items()]
    values["nodes_compact"] = "·".join(per)
    values["nodes_spaced"] = " · ".join(per)
    descriptions = curation.get("nodes", {})
    values["nodes_labeled"] = " · ".join(
        f"`{n}`({descriptions.get(n, {}).get('short_ko', n)}, {c})"
        for n, c in f["nodes"].items())
    for lang in ("en", "ko"):
        rows = []
        for n, count in f["nodes"].items():
            desc = descriptions.get(n, {}).get(lang)
            if desc is None:
                desc = _cell(f["node_descriptions"].get(n, ""))
            rows.append(f"| **{n}** | {count} | {desc} |")
        values[f"node_rows_{lang}"] = "\n".join(rows)
    order = ["handler", "system", "channel_engine", "driver", "workflow_engine", "trigger_engine"]
    routers = f["routers"]
    order = [k for k in order if k in routers] + sorted(set(routers) - set(order))
    values["routers"] = " · ".join(f"{k} {routers[k]}" for k in order)
    rows = []
    for pid, name, desc in f["packages"]:
        entry = curation.get("packages", {}).get(pid, {})
        name = entry.get("name", _cell(name))
        desc = entry.get("description", _cell(desc))
        rows.append(f"| {pid} | {name} | {desc} |")
    values["package_rows"] = "\n".join(rows)
    operators = grammar["operators"]
    values["operator_spec_rows"] = "\n".join(
        f"| `{o['symbol']}` | {o['name']} | {o['meaning']} |" for o in operators)
    values["operator_full_rows"] = "\n".join(
        f"| `{o['symbol']}` | {o.get('prompt_name', o['name'])} | `{o['example']}` |" for o in operators)
    values["operator_brief"] = "; ".join(f"`{o['symbol']}`: {o['brief']}" for o in operators) + "."
    return values


def _cell(value):
    return str(value).replace("\n", " ").replace("|", "\\|").strip()


def _render_template(name: str, span: str, facts: dict, issues: list[str]) -> str:
    try:
        template_dir = facts["_template_dir"]
        template = (template_dir / f"{name}.md").read_text(encoding="utf-8")
        curation = json.loads((template_dir / "descriptions.json").read_text(encoding="utf-8"))
        grammar = json.loads((template_dir / "ibl_grammar.json").read_text(encoding="utf-8"))
        values = _template_values(facts, curation, grammar)

        def slot(match):
            key = match[1]
            if key not in values or values[key] is None:
                raise ValueError(f"실측 또는 템플릿 슬롯 부재: {key}")
            return str(values[key])
        return re.sub(r"\{\{([a-zA-Z0-9_]+)\}\}", slot, template)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        issues.append(f"{name}: 문서 템플릿 생성 실패 — {exc}")
        return span


# 대상 목록 — (상대경로, START 마커, END 마커, 렌더러). 같은 문서에 구간 여러 개 가능.
DOC_TARGETS = [
    ("data/system_docs/ibl.md", "<!-- GRAMMAR_OPERATORS:START -->", "<!-- GRAMMAR_OPERATORS:END -->",
     partial(_render_template, "grammar_spec")),
    ("data/common_prompts/fragments/12_ibl_only.md", "<!-- GRAMMAR_OPERATORS:START -->", "<!-- GRAMMAR_OPERATORS:END -->",
     partial(_render_template, "grammar_full")),
    ("data/common_prompts/fragments/12_ibl_compact.md", "<!-- GRAMMAR_OPERATORS:START -->", "<!-- GRAMMAR_OPERATORS:END -->",
     partial(_render_template, "grammar_compact")),
    ("data/system_docs/system_structure.md", SELF_IMAGE_START, SELF_IMAGE_END, partial(_render_template, "self_image")),
    ("README.md", IBL_STATS_START, IBL_STATS_END, partial(_render_template, "readme_en")),
    ("README.ko.md", IBL_STATS_START, IBL_STATS_END, partial(_render_template, "readme_ko")),
    ("data/system_docs/anatomy.md", IBL_STATS_START, IBL_STATS_END, partial(_render_template, "anatomy")),
    ("data/system_docs/architecture.md", IBL_STATS_START, IBL_STATS_END, partial(_render_template, "architecture")),
    ("data/system_docs/architecture.md", "<!-- ROUTERS:START -->", "<!-- ROUTERS:END -->",
     partial(_render_template, "architecture_routers")),
    ("data/system_docs/technical.md", IBL_STATS_START, IBL_STATS_END, partial(_render_template, "technical")),
    ("data/system_docs/ibl.md", IBL_STATS_START, IBL_STATS_END, partial(_render_template, "ibl")),
    ("data/system_docs/ibl.md", "<!-- RUNS_ON:START -->", "<!-- RUNS_ON:END -->", partial(_render_template, "ibl_runs_on")),
    ("data/system_docs/inventory.md", IBL_STATS_START, IBL_STATS_END, partial(_render_template, "inventory")),
    ("data/system_docs/packages.md", IBL_STATS_START, IBL_STATS_END, partial(_render_template, "packages_head")),
    ("data/system_docs/packages.md", PKG_TABLE_START, PKG_TABLE_END, partial(_render_template, "packages_table")),
    ("data/system_docs/packages.md", "<!-- EXT_COUNT:START -->", "<!-- EXT_COUNT:END -->", partial(_render_template, "packages_ext")),
]


# ── 적용/검사 ────────────────────────────────────────────────────────────────

def _render_doc(root: Path, rel: str, facts: dict) -> tuple[str | None, list[str]]:
    """한 문서의 모든 파생 구간을 렌더한 전체 텍스트와 issue 목록."""
    fp = root / rel
    if not fp.is_file():
        return None, [f"{rel}: 문서 부재"]
    text = fp.read_text(encoding="utf-8")
    issues: list[str] = _residue_issues(rel, text)
    facts = {**facts, "_template_dir": root / "docs/generated_templates"}
    if issues:
        return None, issues
    for path, start, end, renderer in DOC_TARGETS:
        if path != rel:
            continue
        if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
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
        if new_text is None or doc_issues:
            continue
        fp = root / rel
        if fp.read_text(encoding="utf-8") != new_text:
            atomic_write_text(fp, new_text)
            written.append(rel)
    return written, issues


_CONFLICT_MARKS = ("<<<<<<< ", "=======", ">>>>>>> ")


def _residue_issues(rel: str, text: str) -> list[str]:
    """머지 충돌 잔재 관문 (2026-09-06 실측): 커밋 재쌓기(cherry-pick)가 마커 구간에서 충돌하면
    구간이 두 벌이 되고 `<<<<<<<`/`>>>>>>>` 가 그 사이에 남는다. 렌더러는 첫 START~END 한 벌만 다시
    쓰므로 나머지 한 벌은 내용이 같아 '일치'로 통과했고, 표식은 구간 밖이라 아무도 대조하지 않았다 —
    그대로 커밋·푸시됐다. 파생 대상 문서 안의 충돌 표식과 중복 START 는 stale 과 같은 급의 실패다."""
    out = []
    lines = text.split("\n")
    if any(l.startswith(_CONFLICT_MARKS[0]) or l.startswith(_CONFLICT_MARKS[2]) or l == _CONFLICT_MARKS[1]
           for l in lines):
        out.append(f"{rel}: 머지 충돌 표식(<<<<<<< / ======= / >>>>>>>)이 남아 있다 — 손으로 풀고 재생성")
    starts = [l for l in lines if "<!-- " in l and ":START -->" in l]
    dup = sorted({l.strip() for l in starts if starts.count(l) > 1})
    if dup:
        out.append(f"{rel}: 파생 구간 START 마커 중복 {dup} — 구간이 두 벌이면 한 벌만 재생성된다")
    return out


def check_docs(root: Path, data: dict | None) -> list[str]:
    """--check: 파생 구간이 실측과 일치하는지. 불일치·템플릿 오류·충돌 잔재 전부 issue."""
    facts = collect_doc_facts(root, data)
    if facts is None:
        return []  # data 파싱 실패는 삼각 검증이 이미 잡는다 — 이중 보고 안 함
    issues: list[str] = []
    for rel in dict.fromkeys(t[0] for t in DOC_TARGETS):
        new_text, doc_issues = _render_doc(root, rel, facts)
        issues.extend(doc_issues)
        if new_text is None or doc_issues:
            continue
        if (root / rel).read_text(encoding="utf-8") != new_text:
            issues.append(f"{rel}: 파생 구간 stale — `python3 scripts/build_ibl_nodes.py` 로 재생성 필요")
    return issues
