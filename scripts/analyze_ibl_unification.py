#!/usr/bin/env python3
"""IBL 통합 분석 — 패키지 ibl_actions.yaml vs src 액션 비교.

출력:
- 양쪽 정의 (src ∩ 패키지)
- 패키지 only (위험: src에 없으면 폐기 시 사라짐)
- src only
- description 불일치
- 패키지 only에 대한 src 통합 액션 후보 매핑
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "data" / "ibl_nodes_src"
PKG_DIR = ROOT / "data" / "packages" / "installed" / "tools"

NODES = ["sense", "self", "limbs", "others", "engines"]


def load_src() -> dict[tuple[str, str], dict]:
    """Returns {(node, action_name): action_def}."""
    out: dict[tuple[str, str], dict] = {}
    for node in NODES:
        path = SRC_DIR / f"{node}.yaml"
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text())
        # Structure: {node: {actions: {name: def}}}
        actions = (data.get(node) or {}).get("actions") or {}
        for name, defn in actions.items():
            out[(node, name)] = defn or {}
    return out


def load_packages() -> dict[tuple[str, str], dict]:
    """Returns {(node, action_name): {**def, '_pkg': pkg_name}}."""
    out: dict[tuple[str, str], dict] = {}
    for pkg in sorted(PKG_DIR.iterdir()):
        path = pkg / "ibl_actions.yaml"
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except Exception as e:
            print(f"WARN load {pkg.name}: {e}", file=sys.stderr)
            continue
        node = data.get("node")
        actions = data.get("actions") or {}
        if not node:
            continue
        for name, defn in actions.items():
            d = dict(defn or {})
            d["_pkg"] = pkg.name
            key = (node, name)
            if key in out:
                # 충돌: 같은 액션을 여러 패키지가 정의
                out[key].setdefault("_extra_pkgs", []).append(pkg.name)
            else:
                out[key] = d
    return out


def similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def suggest_src_candidates(
    pkg_key: tuple[str, str],
    pkg_def: dict,
    src_index: dict[tuple[str, str], dict],
) -> list[tuple[float, tuple[str, str], dict, str]]:
    """패키지 only 액션에 대한 src 통합 액션 후보. Returns sorted list of (score, src_key, src_def, reason)."""
    node, name = pkg_key
    pkg_tool = (pkg_def.get("tool") or "").lower()
    pkg_desc = pkg_def.get("description") or ""
    pkg_pkg = pkg_def.get("_pkg", "")

    cands: list[tuple[float, tuple[str, str], dict, str]] = []
    for src_key, src_def in src_index.items():
        s_node, s_name = src_key
        if s_node != node:  # 다른 노드는 후보 아님
            continue
        score = 0.0
        reasons = []

        # 같은 tool 이름 → 강력 신호
        src_tool = (src_def.get("tool") or "").lower()
        if src_tool and pkg_tool:
            if src_tool == pkg_tool:
                score += 0.8
                reasons.append(f"same tool={src_tool}")
            elif pkg_tool in src_tool or src_tool in pkg_tool:
                score += 0.4
                reasons.append(f"tool overlap")
            elif src_tool.endswith("_op") and pkg_tool.split("_")[0] in src_tool:
                # legal_op vs legal_lookup 같은 패턴
                score += 0.3
                reasons.append("op-pattern match")

        # 액션명 substring (예: pkg=health_query, src=health)
        if s_name in name or name in s_name:
            score += 0.4
            reasons.append(f"name overlap: {s_name}~{name}")
        # 액션명 첫 단어 매칭 (legal_search vs legal)
        first_pkg = name.split("_")[0]
        first_src = s_name.split("_")[0]
        if first_pkg == first_src and len(first_pkg) >= 3:
            score += 0.2
            reasons.append(f"first-word: {first_pkg}")

        # description 유사도
        src_desc = src_def.get("description") or ""
        sim = similar(pkg_desc[:100], src_desc[:100])
        if sim > 0.3:
            score += sim * 0.3
            reasons.append(f"desc sim={sim:.2f}")

        if score >= 0.3:
            cands.append((score, src_key, src_def, "; ".join(reasons)))

    cands.sort(reverse=True, key=lambda x: x[0])
    return cands[:3]


def main() -> int:
    src = load_src()
    pkg = load_packages()

    src_keys = set(src.keys())
    pkg_keys = set(pkg.keys())
    common = src_keys & pkg_keys
    pkg_only = pkg_keys - src_keys
    src_only = src_keys - pkg_keys

    print(f"=== Baseline ===")
    print(f"src actions       : {len(src)}")
    print(f"pkg actions       : {len(pkg)}")
    print(f"common (both)     : {len(common)}")
    print(f"pkg_only          : {len(pkg_only)}")
    print(f"src_only          : {len(src_only)}")

    # description 불일치 (common 중)
    mismatched = []
    for key in common:
        sd = (src[key].get("description") or "").strip()
        pd = (pkg[key].get("description") or "").strip()
        if sd != pd:
            mismatched.append(key)
    print(f"desc mismatch     : {len(mismatched)} (in common)")
    print()

    # pkg_only 분류
    print(f"=== pkg_only 후보 매핑 ({len(pkg_only)}) ===")
    by_pkg: dict[str, list] = defaultdict(list)
    for key in sorted(pkg_only):
        by_pkg[pkg[key].get("_pkg", "?")].append(key)

    output_rows = []
    for pkg_name, keys in sorted(by_pkg.items()):
        print(f"\n--- [{pkg_name}] {len(keys)} actions ---")
        for key in keys:
            node, action = key
            pdef = pkg[key]
            cands = suggest_src_candidates(key, pdef, src)
            line = f"  [{node}:{action}] tool={pdef.get('tool','?')}"
            print(line)
            for sc, ck, _, reason in cands:
                print(f"      → [{ck[0]}:{ck[1]}] score={sc:.2f} ({reason})")
            if not cands:
                print(f"      → NO CANDIDATES (probable new/missed action)")
            output_rows.append({
                "node": node,
                "action": action,
                "pkg": pkg_name,
                "tool": pdef.get("tool"),
                "desc": pdef.get("description"),
                "candidates": [
                    {"key": f"{ck[0]}:{ck[1]}", "score": round(sc, 2), "reason": reason}
                    for sc, ck, _, reason in cands
                ],
            })

    # JSON 출력 (사람 검토용)
    out_path = ROOT / "data" / "_ibl_pkg_only_analysis.json"
    out_path.write_text(json.dumps(output_rows, ensure_ascii=False, indent=2))
    print(f"\n[wrote {out_path.relative_to(ROOT)}]")

    # desc mismatch도 별도 출력
    if mismatched:
        mm_path = ROOT / "data" / "_ibl_desc_mismatch.json"
        mm_rows = []
        for key in sorted(mismatched):
            mm_rows.append({
                "key": f"{key[0]}:{key[1]}",
                "src_desc": (src[key].get("description") or "").strip(),
                "pkg_desc": (pkg[key].get("description") or "").strip(),
                "pkg": pkg[key].get("_pkg"),
            })
        mm_path.write_text(json.dumps(mm_rows, ensure_ascii=False, indent=2))
        print(f"[wrote {mm_path.relative_to(ROOT)}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
