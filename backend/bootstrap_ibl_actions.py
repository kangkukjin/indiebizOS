"""
bootstrap_ibl_actions.py - 기존 패키지에 ibl_actions.yaml 자동 생성

1회성 마이그레이션 스크립트.
ibl_nodes.yaml의 router: handler 액션들을 역추적하여
각 패키지에 ibl_actions.yaml을 생성하고,
_ibl_provenance.yaml을 초기화합니다.

사용법:
    cd backend
    python3 bootstrap_ibl_actions.py
    python3 bootstrap_ibl_actions.py --dry-run    # 실제 파일 생성 없이 미리보기
"""

import sys
import yaml
from pathlib import Path
from collections import defaultdict

# backend 경로
_backend = Path(__file__).parent
sys.path.insert(0, str(_backend))

from tool_loader import build_tool_package_map


def _get_data_path() -> Path:
    return _backend.parent / "data"


def bootstrap(dry_run: bool = False):
    """기존 패키지에 ibl_actions.yaml 생성 + _ibl_provenance.yaml 초기화"""

    nodes_path = _get_data_path() / "ibl_nodes.yaml"
    with open(nodes_path, 'r', encoding='utf-8') as f:
        nodes_data = yaml.safe_load(f)

    nodes = nodes_data.get("nodes", {})

    # tool_name → package_id 매핑
    pkg_map = build_tool_package_map(force=True)

    # 패키지별 수집: {package_id: {node_name: {action_name: action_def}}}
    pkg_actions = defaultdict(lambda: defaultdict(dict))
    # 패키지별 guides: {package_id: {node_name: [guide_paths]}}
    pkg_guides = defaultdict(lambda: defaultdict(list))
    # provenance: {node_name: {action_name: package_id}}
    provenance = defaultdict(dict)

    # 통계
    total_handler = 0
    total_mapped = 0
    unmapped = []

    for node_name, node_def in nodes.items():
        actions = node_def.get("actions", {})
        guides = node_def.get("guides", [])

        for action_name, action_def in actions.items():
            router = action_def.get("router", "")
            if router != "handler":
                continue

            total_handler += 1
            tool_name = action_def.get("tool", "")

            if not tool_name:
                unmapped.append(f"  {node_name}:{action_name} — tool 필드 없음")
                continue

            package_id = pkg_map.get(tool_name)
            if not package_id:
                unmapped.append(f"  {node_name}:{action_name} — tool '{tool_name}' 매핑 없음")
                continue

            pkg_actions[package_id][node_name][action_name] = action_def
            provenance[node_name][action_name] = package_id
            total_mapped += 1

        # guides를 해당 노드의 패키지들에 분배
        for guide_path in guides:
            # 가이드 경로에서 패키지 추측 (예: "real-estate/real_estate_guide.md" → "real-estate")
            parts = guide_path.split("/")
            if len(parts) >= 2:
                guide_pkg = parts[0]
                # 이 패키지가 이 노드에 액션을 가지고 있으면 가이드도 포함
                if guide_pkg in pkg_actions and node_name in pkg_actions[guide_pkg]:
                    pkg_guides[guide_pkg][node_name].append(guide_path)

    # 결과 출력
    print(f"\n=== 부트스트랩 결과 ===")
    print(f"총 handler 액션: {total_handler}")
    print(f"매핑 성공: {total_mapped}")
    print(f"매핑 실패: {len(unmapped)}")
    if unmapped:
        print("매핑 실패 목록:")
        for u in unmapped:
            print(u)

    print(f"\n패키지별 액션 수:")
    for pkg_id in sorted(pkg_actions.keys()):
        total = sum(len(actions) for actions in pkg_actions[pkg_id].values())
        node_list = ", ".join(pkg_actions[pkg_id].keys())
        print(f"  {pkg_id}: {total}개 ({node_list})")

    if dry_run:
        print("\n[DRY RUN] 파일 생성 건너뜀")
        return

    # ibl_actions.yaml 생성
    created = 0
    for pkg_id, node_dict in pkg_actions.items():
        pkg_path = _get_data_path() / "packages" / "installed" / "tools" / pkg_id
        if not pkg_path.exists():
            print(f"  경고: {pkg_id} 폴더 없음, 건너뜀")
            continue

        actions_file = pkg_path / "ibl_actions.yaml"

        # 단일 노드인지 복수 노드인지
        node_names = list(node_dict.keys())

        if len(node_names) == 1:
            # 단일 노드 형식
            node_name = node_names[0]
            output = {"node": node_name, "actions": node_dict[node_name]}
            guides = pkg_guides.get(pkg_id, {}).get(node_name, [])
            if guides:
                output["guides"] = guides
        else:
            # 복수 노드 형식
            output = {"nodes": {}}
            for node_name, actions in node_dict.items():
                entry = {"actions": actions}
                guides = pkg_guides.get(pkg_id, {}).get(node_name, [])
                if guides:
                    entry["guides"] = guides
                output["nodes"][node_name] = entry

        with open(actions_file, 'w', encoding='utf-8') as f:
            yaml.dump(output, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        created += 1

    print(f"\nibl_actions.yaml 생성: {created}개 패키지")

    # _ibl_provenance.yaml 생성
    prov_path = _get_data_path() / "_ibl_provenance.yaml"
    prov_data = dict(provenance)  # defaultdict → dict
    for k, v in prov_data.items():
        prov_data[k] = dict(v)

    with open(prov_path, 'w', encoding='utf-8') as f:
        f.write("# 자동 생성 - 직접 편집하지 마세요\n# 액션 출처 추적: {node: {action: package_id}}\n")
        yaml.dump(prov_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"_ibl_provenance.yaml 생성 완료 ({sum(len(v) for v in prov_data.values())}개 항목)")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    bootstrap(dry_run=dry)
