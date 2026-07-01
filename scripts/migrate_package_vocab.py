#!/usr/bin/env python3
"""패키지 어휘 자기완결화 마이그레이션 하네스 (Phase 0-③).

중앙 `data/ibl_nodes_src/<node>.yaml` 에 있는, 지정한 패키지 소유 액션들을
그 패키지 폴더의 `ibl_actions.yaml` 로 옮긴다(텍스트 수술로 중앙 소스에서 제거 +
fragment 파일 생성). 마이그레이션 전후 `data/ibl_nodes.yaml` 의 의미(파싱된 dict)가
동일함을 단언하고, 실패 시 백업에서 롤백한다.

사용:
  python3 scripts/migrate_package_vocab.py <package_name> [--dry-run]

절차 (docs/CAPABILITY_SELF_CONTAINMENT_HANDOFF.md §4):
  1) 마이그레이션 전 data/ibl_nodes.yaml 파싱(= before, 의미 동일 단언의 기준)
  2) build_tool_index 로 패키지 소유 tool 집합 계산
  3) 중앙 src 각 노드에서 그 tool 을 쓰는 액션을 찾아 그룹
  4) 패키지 ibl_actions.yaml 작성(단일/다중 노드 형식)
  5) 중앙 노드 src 파일에서 텍스트 수술로 해당 액션 블록 제거
  6) 재빌드 → 파싱된 data 가 before 와 deep-equal 인지 확인
  7) --check 통과 확인
  실패 시 백업에서 원복.
"""
from __future__ import annotations
import argparse
import copy
import importlib.util
import re
import shutil
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "build_ibl_nodes", Path(__file__).resolve().parent / "build_ibl_nodes.py"
)
build_ibl_nodes = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(build_ibl_nodes)

import yaml  # noqa: E402


def find_owned_actions(root: Path, package: str) -> dict[str, dict[str, dict]]:
    """{node: {action_name: action_def}} — 패키지가 소유한(tool 필드 기준) 액션들."""
    tool_index = build_ibl_nodes.build_tool_index(root)
    owned_tools = {
        name for name, (pkg_dir, _tool) in tool_index.items() if pkg_dir.name == package
    }
    if not owned_tools:
        raise SystemExit(f"패키지 '{package}' 소유 tool 없음 (tool.json 확인)")

    current = yaml.safe_load((root / "data" / "ibl_nodes.yaml").read_text(encoding="utf-8"))
    nodes = current.get("nodes", {})

    result: dict[str, dict[str, dict]] = {}
    for node, ndef in nodes.items():
        actions = ndef.get("actions", {}) if isinstance(ndef, dict) else {}
        for aname, adef in actions.items():
            if isinstance(adef, dict) and adef.get("tool") in owned_tools:
                result.setdefault(node, {})[aname] = adef
    return result


def build_fragment_doc(owned: dict[str, dict[str, dict]]) -> dict:
    """owned={node: {action: def}} → ibl_actions.yaml 최상위 문서(형식 A/B)."""
    if len(owned) == 1:
        node, actions = next(iter(owned.items()))
        return {"node": node, "actions": actions}
    return {"nodes": {node: {"actions": actions} for node, actions in owned.items()}}


_ACTION_KEY_RE = "^      {name}:\\n(?:.*\\n)*?(?=^      \\S|^    \\S)"


def remove_action_block(text: str, action_name: str) -> str:
    """노드 src 텍스트에서 6칸-들여쓴 액션 블록 하나를 텍스트 수술로 제거."""
    pattern = re.compile(_ACTION_KEY_RE.format(name=re.escape(action_name)), re.MULTILINE)
    new_text, n = pattern.subn("", text, count=1)
    if n != 1:
        raise SystemExit(f"액션 블록 경계를 찾지 못함: {action_name!r} (수동 확인 필요)")
    return new_text


def migrate(package: str, dry_run: bool = False) -> int:
    root = build_ibl_nodes.repo_root()
    src_dir = root / "data" / "ibl_nodes_src"
    nodes_yaml = root / "data" / "ibl_nodes.yaml"
    phone_manifest = root / "data" / "phone_manifest.json"

    pkg_dirs = [
        root / rel / package
        for rel in build_ibl_nodes.PACKAGE_DIRS
        if (root / rel / package).is_dir()
    ]
    if not pkg_dirs:
        raise SystemExit(f"패키지 폴더 없음: {package}")
    pkg_dir = pkg_dirs[0]
    frag_path = pkg_dir / "ibl_actions.yaml"
    if frag_path.is_file():
        raise SystemExit(f"이미 fragment 존재: {frag_path} (재이관 방지)")

    before = yaml.safe_load(nodes_yaml.read_text(encoding="utf-8"))
    before_copy = copy.deepcopy(before)

    owned = find_owned_actions(root, package)
    if not owned:
        raise SystemExit(f"패키지 '{package}' 소유 액션 없음 — 이관 대상 0건")

    total = sum(len(a) for a in owned.values())
    print(f"[migrate] {package}: {len(owned)}개 노드, {total}개 액션 이관 대상")
    for node, actions in owned.items():
        print(f"  {node}: {sorted(actions)}")

    fragment_doc = build_fragment_doc(owned)

    if dry_run:
        print("[migrate] --dry-run: 파일 변경 없이 종료")
        print(yaml.safe_dump(fragment_doc, allow_unicode=True, sort_keys=False))
        return 0

    # --- 백업 ---
    backups: dict[Path, str] = {}
    node_paths = {node: src_dir / f"{node}.yaml" for node in owned}
    for p in list(node_paths.values()) + [nodes_yaml] + (
        [phone_manifest] if phone_manifest.is_file() else []
    ):
        backups[p] = p.read_text(encoding="utf-8")

    def rollback(reason: str) -> int:
        print(f"[migrate] 실패 — 롤백: {reason}", file=sys.stderr)
        for p, text in backups.items():
            p.write_text(text, encoding="utf-8")
        if frag_path.is_file():
            frag_path.unlink()
        return 1

    try:
        # --- fragment 파일 작성 ---
        frag_text = yaml.safe_dump(
            fragment_doc, allow_unicode=True, sort_keys=False, default_flow_style=False,
            width=1 << 20,
        )
        frag_path.write_text(frag_text, encoding="utf-8")
        print(f"[migrate] 작성: {frag_path}")

        # --- 중앙 src 텍스트 수술 ---
        for node, actions in owned.items():
            node_path = node_paths[node]
            text = node_path.read_text(encoding="utf-8")
            for aname in actions:
                text = remove_action_block(text, aname)
            node_path.write_text(text, encoding="utf-8")
            print(f"[migrate] 수정: {node_path} (-{len(actions)} 액션)")

        # --- 재빌드 ---
        rc = build_ibl_nodes.build(check=False)
        if rc != 0:
            return rollback("빌드 실패")

        after = yaml.safe_load(nodes_yaml.read_text(encoding="utf-8"))
        if after != before_copy:
            return rollback("의미 동일성 깨짐 (파싱된 dict 불일치)")
        print("[migrate] 의미 동일 확인 ✓ (마이그레이션 전후 dict 일치)")

        # --- --check ---
        rc = build_ibl_nodes.build(check=True)
        if rc != 0:
            return rollback("--check 실패")
        print(f"[migrate] {package} 이관 완료 + --check 통과 ✓")
        return 0
    except SystemExit as e:
        return rollback(str(e))
    except Exception as e:  # noqa: BLE001
        return rollback(f"예외: {e}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="패키지 이름 (예: radio)")
    parser.add_argument("--dry-run", action="store_true", help="파일 변경 없이 대상만 출력")
    args = parser.parse_args(argv)
    return migrate(args.package, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
