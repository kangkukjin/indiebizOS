#!/usr/bin/env python3
"""ibl_nodes.yaml 빌드 — 편집용 소스 6개를 단일 yaml로 병합.

편집 워크플로:
1) `data/ibl_nodes_src/<name>.yaml` 중 하나를 편집
2) `python scripts/build_ibl_nodes.py` 실행
3) `data/ibl_nodes.yaml`이 갱신됨 (런타임이 읽는 단일 파일)

런타임 코드는 단일 ibl_nodes.yaml만 읽는다 (ibl_access / tool_loader /
tool_selector / system_tools).

병합 방식: 바이트-단위 연결. 소스 파일들의 내용은 원본 yaml의 해당 span에서
잘라낸 바이트 그대로이므로, 정상 워크플로에서는 byte-identical 라운드트립이
보장된다 (소스 편집 후엔 그 부분만 달라짐).
"""
from __future__ import annotations
import argparse
import hashlib
import sys
from pathlib import Path


# 순서가 중요 — 원본 yaml의 노드 순서와 동일해야 함.
NODE_ORDER = ["sense", "self", "limbs", "others", "engines"]


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def build(check: bool = False) -> int:
    root = repo_root()
    src_dir = root / "data" / "ibl_nodes_src"
    target = root / "data" / "ibl_nodes.yaml"

    if not src_dir.is_dir():
        print(f"[build_ibl_nodes] 소스 디렉토리 없음: {src_dir}", file=sys.stderr)
        return 2

    parts: list[str] = []

    meta_path = src_dir / "meta.yaml"
    if not meta_path.is_file():
        print(f"[build_ibl_nodes] 누락: {meta_path}", file=sys.stderr)
        return 2
    parts.append(meta_path.read_text(encoding="utf-8"))

    # `nodes:` 헤더를 명시적으로 삽입 (소스 파일 어디에도 두지 않는다).
    parts.append("nodes:\n")

    for node in NODE_ORDER:
        node_path = src_dir / f"{node}.yaml"
        if not node_path.is_file():
            print(f"[build_ibl_nodes] 누락: {node_path}", file=sys.stderr)
            return 2
        parts.append(node_path.read_text(encoding="utf-8"))

    merged = "".join(parts)

    # YAML 파싱으로 sanity check — 노드/액션 수가 정상인지.
    try:
        import yaml as _yaml
    except ImportError:
        _yaml = None
    if _yaml is not None:
        data = _yaml.safe_load(merged)
        nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
        total_actions = sum(
            len(n.get("actions", {})) for n in nodes.values() if isinstance(n, dict)
        )
        print(
            f"[build_ibl_nodes] 노드 {len(nodes)}개, 액션 {total_actions}개 "
            f"({sum(1 for _ in merged.splitlines())}줄, {len(merged.encode('utf-8'))}바이트)"
        )

    if check:
        if not target.is_file():
            print(f"[build_ibl_nodes] check: 타깃 부재 — {target}", file=sys.stderr)
            return 1
        current = target.read_text(encoding="utf-8")
        if current == merged:
            print("[build_ibl_nodes] check: 일치 ✓")
            return 0
        # 해시 차이 안내
        h_cur = hashlib.sha256(current.encode("utf-8")).hexdigest()[:12]
        h_new = hashlib.sha256(merged.encode("utf-8")).hexdigest()[:12]
        print(
            f"[build_ibl_nodes] check: 불일치 — 빌드 결과가 현재 yaml과 다름\n"
            f"  현재 {h_cur} / 빌드 {h_new}",
            file=sys.stderr,
        )
        return 1

    target.write_text(merged, encoding="utf-8")
    print(f"[build_ibl_nodes] 작성: {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--check",
        action="store_true",
        help="작성하지 않고 현재 data/ibl_nodes.yaml과 일치하는지만 확인 (CI/pre-commit용)",
    )
    args = ap.parse_args(argv)
    return build(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
