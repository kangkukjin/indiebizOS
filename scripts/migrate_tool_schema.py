#!/usr/bin/env python3
"""tool.json → ibl_actions.yaml `tool_json:` 블록 이관 하네스.

정합성을 검증에서 구조로 (2026-07-03): 손수 유지하던 패키지 tool.json 을
빌드 산출물로 뒤집는다. 이 스크립트는 그 이관을 기계적으로 수행한다 —
추론 없음, 이사만. (migrate_package_vocab.py 선례: 이관→재파생→의미 동일
단언→실패 시 롤백.)

패키지별 절차:
  1. tool.json 파싱 → header(최상위, tools 외) + tools 리스트
  2. ibl_actions.yaml 의 액션 소유 맵(action.tool == name)과 ops 대조
  3. op-bearing 소유 도구의 input_schema.properties.op 에서 enum/default 제거
     (actions 의 ops 가 단일 소스 — 빌드가 주입)
  4. `tool_json:` 블록을 ibl_actions.yaml 끝에 텍스트 append (기존 바이트 무교란)
  5. build_ibl_nodes.derive_tool_json_docs 로 재파생 → 원본 tool.json 과
     deep-equal 단언 (enum 은 집합 비교, _generated 마커 무시)
  6. 성공: 파생 canonical tool.json 로 덮어씀 / 실패: fragment 롤백

사용:
  python3 scripts/migrate_tool_schema.py investment      # 파일럿 1개
  python3 scripts/migrate_tool_schema.py --all           # 전체
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "data" / "packages" / "installed" / "tools"

_spec = importlib.util.spec_from_file_location(
    "build_ibl_nodes", Path(__file__).parent / "build_ibl_nodes.py"
)
_build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_build)


def _normalize(tj: dict) -> dict:
    """비교용 정규화: _generated 제거 + op enum 을 정렬 리스트로."""
    tj = copy.deepcopy(tj)
    tj.pop("_generated", None)
    for tool in tj.get("tools", []):
        op = (tool.get("input_schema") or {}).get("properties", {}).get("op")
        if isinstance(op, dict) and isinstance(op.get("enum"), list):
            op["enum"] = sorted(op["enum"])
    return tj


def _owned_ops(frag_doc: dict) -> dict:
    """fragment 에서 tool_name → ops 블록 맵 (형식 A/B 모두)."""
    owned: dict = {}
    node_defs = (
        list(frag_doc["nodes"].values()) if isinstance(frag_doc.get("nodes"), dict)
        else [{"actions": frag_doc.get("actions") or {}}]
    )
    for ndef in node_defs:
        for acfg in ((ndef or {}).get("actions") or {}).values():
            if isinstance(acfg, dict) and acfg.get("tool"):
                owned[acfg["tool"]] = acfg.get("ops")
    return owned


def migrate_package(pkg_dir: Path) -> str:
    """반환: 'migrated' | 'skipped:<이유>' | 'failed:<이유>'"""
    tj_path = pkg_dir / "tool.json"
    frag_path = pkg_dir / "ibl_actions.yaml"
    if not tj_path.is_file():
        return "skipped:tool.json 없음"
    if not frag_path.is_file():
        return "skipped:ibl_actions.yaml 없음 (예: ibl-core)"

    frag_text = frag_path.read_text(encoding="utf-8")
    frag_doc = yaml.safe_load(frag_text)
    if not isinstance(frag_doc, dict):
        return "failed:fragment 최상위가 매핑이 아님"
    if "tool_json" in frag_doc:
        return "skipped:이미 이관됨"

    original = json.loads(tj_path.read_text(encoding="utf-8"))
    if not isinstance(original, dict) or not isinstance(original.get("tools"), list):
        return "failed:tool.json 이 {…, tools:[…]} 형태가 아님"

    header = {k: v for k, v in original.items() if k != "tools"}
    owned = _owned_ops(frag_doc)

    stored_tools = []
    for entry in copy.deepcopy(original["tools"]):
        name = entry.get("name")
        ops = owned.get(name)
        if isinstance(ops, dict) and ops.get("values"):
            op_prop = (entry.get("input_schema") or {}).get("properties", {}).get("op")
            if not isinstance(op_prop, dict):
                return f"failed:{name} — 소유 액션에 ops 있는데 op property 없음"
            if set(op_prop.get("enum") or []) != set(ops["values"].keys()):
                return f"failed:{name} — 현재 enum 이 ops.values 와 불일치 (--check 먼저)"
            op_prop.pop("enum", None)
            op_prop.pop("default", None)
        stored_tools.append(entry)

    block = yaml.safe_dump(
        {"tool_json": {"header": header, "tools": stored_tools}},
        allow_unicode=True, sort_keys=False, width=120,
    )
    appended = (
        frag_text.rstrip("\n")
        + "\n\n# tool.json 파생 원본 (2026-07-03 이관) — 빌드가 이 블록과 위 actions 의 ops 로 tool.json 을 생성한다.\n"
        + "# op-bearing 도구의 op enum/default 는 여기 저장하지 않는다 (actions 의 ops 가 단일 소스).\n"
        + block
    )

    frag_path.write_text(appended, encoding="utf-8")
    try:
        docs, issues = _build.derive_tool_json_docs(ROOT, yaml)
        pkg_issues = [i for i in issues if i.startswith(pkg_dir.name)]
        if pkg_issues:
            raise RuntimeError("; ".join(pkg_issues))
        derived_text = docs.get(tj_path)
        if derived_text is None:
            raise RuntimeError("파생 결과에 이 패키지가 없음")
        if _normalize(json.loads(derived_text)) != _normalize(original):
            raise RuntimeError("deep-equal 실패 — 파생 결과가 원본과 의미 불일치")
    except Exception as e:  # noqa: BLE001
        frag_path.write_text(frag_text, encoding="utf-8")  # 롤백
        return f"failed:{e}"

    tj_path.write_text(derived_text, encoding="utf-8")
    return "migrated"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    targets = (
        sorted(p for p in TOOLS_DIR.iterdir() if p.is_dir())
        if argv[0] == "--all" else [TOOLS_DIR / argv[0]]
    )
    counts = {"migrated": 0, "skipped": 0, "failed": 0}
    for pkg in targets:
        result = migrate_package(pkg)
        kind = result.split(":")[0]
        counts[kind] += 1
        mark = {"migrated": "✓", "skipped": "-", "failed": "✗"}[kind]
        print(f"  {mark} {pkg.name}: {result}")
    print(f"\n이관 {counts['migrated']} / 건너뜀 {counts['skipped']} / 실패 {counts['failed']}")
    print("다음: python3 scripts/build_ibl_nodes.py --check")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
