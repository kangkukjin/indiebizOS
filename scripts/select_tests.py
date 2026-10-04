#!/usr/bin/env python3
"""변경 파일 → 관련 회귀 시험 선택기 (2026-10-04, docs/REGRESSION_TESTING.md '개발 중').

왜: 수리마다 backend 전수(직렬 13분)를 도는 관행이 문서를 이기고 있었다. 전수가 필요한지는
"변경이 import 그래프에서 얼마나 번지는가"로 기계가 판정할 수 있다 — 허브(episode_logger·
agent_pipeline 류)를 건드리면 전수, 아니면 전이 폐포에 든 시험 파일만.

판정 재료 (stdlib 만, backend 를 import 하지 않는다):
  ① backend/**/*.py 의 import 그래프를 **역방향**으로 따라가 변경 모듈의 전이 소비자를 모은다
     (`from x import y`·`import x`·`from backend.a.b import c` 를 모듈 기준명으로 정규화).
  ② 시험 파일이 **문자열로 가리키는 경로**(`scripts/check_x.py`·`data/guides/x.md` 등)도 의존으로
     센다 — 관문 스크립트·데이터 파일 변경이 시험을 고르게.
  ③ 변경된 시험 파일 자체는 항상 포함.

출력: stdout 에 pytest 인수(시험 파일 목록 또는 전수 `backend/`), stderr 에 근거.
  .venv/bin/python3 -m pytest $(scripts/select_tests.py) -n auto --dist loadfile
선택 비율이 --threshold(기본 0.4)를 넘으면 전수를 출력하고 허브 모듈을 stderr 에 이름 부른다.
변경 목록 기본값 = 작업 트리(미커밋 + 스테이지 + 추적 안 된 파일). `--commit REV`·`--range A..B`·
`--files ...` 로 바꾼다. 선택은 영향 분석의 **하한**이지 통과 증명이 아니다 — 문서가 정한 대로
언어·격리·부트스트랩 변경은 전수.
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"pylibs", "node_modules", "__pycache__", ".venv", "build", "outputs"}
IMPORT_RE = re.compile(r"^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import\s+\(?([^\n)]*)|import\s+([A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)*))", re.M)
PATH_RE = re.compile(r"(?:scripts|data|docs|frontend|helper|templates)/[\w./-]+")


def backend_modules(root: Path) -> dict[str, Path]:
    """모듈 기준명(파일 basename, .py 제외) → 경로. 같은 이름이 둘이면 둘 다 한 이름으로 합친다(보수적)."""
    out: dict[str, Path] = {}
    for p in sorted((root / "backend").rglob("*.py")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out.setdefault(p.stem, p)
    return out


def _imported_names(text: str) -> set[str]:
    names: set[str] = set()
    for m in IMPORT_RE.finditer(text):
        # from A.B import c, d as e  → A, B, c, d  /  import A.B, C → A, B, C
        raw = ",".join(g for g in (m.group(1), m.group(2), m.group(3)) if g)
        for item in raw.split(","):
            dotted = item.strip().split(" as ")[0].strip()
            if not dotted:
                continue
            parts = dotted.split(".")
            names.add(parts[0])
            names.add(parts[-1])
    return names


def reverse_graph(modules: dict[str, Path]) -> dict[str, set[str]]:
    """모듈 → 그 모듈을 import 하는 모듈들."""
    rdeps: dict[str, set[str]] = collections.defaultdict(set)
    for name, path in modules.items():
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for dep in _imported_names(text):
            if dep in modules and dep != name:
                rdeps[dep].add(name)
    return rdeps


def closure(seeds, rdeps: dict[str, set[str]]) -> set[str]:
    seen = set(seeds)
    stack = list(seeds)
    while stack:
        m = stack.pop()
        for consumer in rdeps.get(m, ()):
            if consumer not in seen:
                seen.add(consumer)
                stack.append(consumer)
    return seen


def changed_files(args, root: Path) -> list[str]:
    if args.files:
        return [str(Path(f)) for f in args.files]
    if args.commit:
        cmd = ["git", "show", "--name-only", "--format=", "--diff-filter=ACMR", args.commit]
    elif args.range:
        cmd = ["git", "diff", "--name-only", "--diff-filter=ACMR", args.range]
    else:
        cmd = ["git", "status", "--porcelain", "--untracked-files=all"]
    out = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False).stdout
    files = []
    for line in out.splitlines():
        if not line.strip():
            continue
        if cmd[1] == "status":
            if line[:2] == " D" or line[:2] == "D ":
                continue
            line = line[3:]
            if " -> " in line:
                line = line.split(" -> ", 1)[1]
        files.append(line.strip())
    return files


def select(changed: list[str], root: Path = ROOT, threshold: float = 0.4):
    modules = backend_modules(root)
    rdeps = reverse_graph(modules)
    tests = sorted(n for n, p in modules.items() if n.startswith("test_") and p.parent == root / "backend")
    test_paths = {n: modules[n] for n in tests}

    seeds = []
    direct_tests: set[str] = set()
    path_hits: dict[str, set[str]] = collections.defaultdict(set)
    changed_norm = [c.replace("\\", "/") for c in changed]
    for c in changed_norm:
        stem = Path(c).stem
        if c.startswith("backend/") and c.endswith(".py") and stem in modules:
            if stem.startswith("test_"):
                direct_tests.add(stem)
            else:
                seeds.append(stem)
    # ② 문자열 경로 참조
    for t, p in test_paths.items():
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        refs = set(PATH_RE.findall(text))
        for c in changed_norm:
            if c.startswith("backend/"):
                continue
            if c in refs or any(r.endswith("/" + Path(c).name) for r in refs):
                path_hits[t].add(c)

    cl = closure(seeds, rdeps)
    selected = {t for t in tests if t in cl} | direct_tests | set(path_hits)
    hubs = sorted(m for m in seeds if len([t for t in tests if t in closure([m], rdeps)]) > threshold * max(len(tests), 1))
    ratio = len(selected) / max(len(tests), 1)
    return {
        "changed": changed_norm,
        "seeds": seeds,
        "selected": sorted(selected),
        "total": len(tests),
        "ratio": ratio,
        "hubs": hubs,
        "full": ratio > threshold,
        "path_hits": {k: sorted(v) for k, v in path_hits.items()},
        "paths": test_paths,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--commit", help="이 커밋의 변경 파일로 선택")
    ap.add_argument("--range", help="git diff 범위(A..B)로 선택")
    ap.add_argument("--files", nargs="*", help="변경 파일을 직접 지정")
    ap.add_argument("--threshold", type=float, default=0.4, help="이 비율을 넘으면 전수(기본 0.4)")
    ap.add_argument("--explain", action="store_true", help="파일별 선택 근거를 stderr 에")
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args(argv)
    root = Path(args.root)
    changed = changed_files(args, root)
    if not changed:
        print("변경 파일 없음 — 선택할 시험이 없다(전수 통과로 읽지 말 것).", file=sys.stderr)
        return 5
    r = select(changed, root, args.threshold)
    err = sys.stderr
    print(f"변경 {len(r['changed'])} 파일, backend 모듈 {len(r['seeds'])}개 → 전이 시험 파일 {len(r['selected'])}/{r['total']} ({r['ratio']:.0%})", file=err)
    if r["hubs"]:
        print("허브 모듈(혼자서 임계 초과): " + ", ".join(r["hubs"]), file=err)
    if args.explain:
        for t in r["selected"]:
            why = "변경된 시험" if t in {Path(c).stem for c in r['changed']} else ("경로 참조 " + ", ".join(r["path_hits"][t]) if t in r["path_hits"] else "import 전이")
            print(f"  {t}: {why}", file=err)
    if r["full"]:
        print(f"임계 {args.threshold:.0%} 초과 → 전수 권장", file=err)
        print("backend/")
    elif r["selected"]:
        print(" ".join(os.path.relpath(r["paths"][t], root) for t in r["selected"]))
    else:
        print("backend .py 변경이 시험에 닿지 않음 — 데이터·문서 변경이면 해당 관문으로 검증.", file=err)
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
