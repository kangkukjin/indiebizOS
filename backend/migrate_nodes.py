#!/usr/bin/env python3
"""
Phase 22 노드 마이그레이션 스크립트
10노드 → 6노드 통합을 위한 agents.yaml 자동 변환

사용법:
  python migrate_nodes.py --step 1          # stream (youtube+radio)
  python migrate_nodes.py --step 2          # interface (browser+android+desktop)
  python migrate_nodes.py --step 3          # source (informant+librarian)
  python migrate_nodes.py --step 4          # rename (orchestrator→system, creator→forge)
  python migrate_nodes.py --step all        # 전체
  python migrate_nodes.py --step 1 --dry-run  # 미리보기
  python migrate_nodes.py --step 1 --reverse  # 되돌리기
"""

import argparse
import glob
import os
import sys
import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_DIR = os.path.join(BASE, "projects")

# 각 Step별 매핑 (old → new)
STEP_MAPPINGS = {
    1: {"youtube": "stream", "radio": "stream"},
    2: {"browser": "interface", "android": "interface", "desktop": "interface"},
    3: {"informant": "source", "librarian": "source"},
    4: {"orchestrator": "system", "creator": "forge"},
}


def find_agents_files():
    """모든 agents.yaml 경로 반환"""
    pattern = os.path.join(PROJECTS_DIR, "*", "agents.yaml")
    return sorted(glob.glob(pattern))


def migrate_file(filepath, mapping, dry_run=False, reverse=False):
    """단일 agents.yaml 파일 마이그레이션"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "agents" not in data:
        return []

    if reverse:
        # 역방향: new → old (1:N 역매핑이므로 첫 번째 old 값으로 복원)
        rev_map = {}
        for old, new in mapping.items():
            if new not in rev_map:
                rev_map[new] = old
        mapping = rev_map

    changes = []
    for agent in data["agents"]:
        nodes = agent.get("allowed_nodes", [])
        if not nodes:
            continue

        original = list(nodes)
        new_nodes = []
        changed = False

        for node in nodes:
            if node in mapping:
                replacement = mapping[node]
                if replacement not in new_nodes:
                    new_nodes.append(replacement)
                changed = True
            else:
                if node not in new_nodes:
                    new_nodes.append(node)

        if changed:
            new_nodes.sort()
            agent["allowed_nodes"] = new_nodes
            project = os.path.basename(os.path.dirname(filepath))
            agent_name = agent.get("name", agent.get("id", "?"))
            changes.append({
                "project": project,
                "agent": agent_name,
                "before": original,
                "after": new_nodes,
            })

    if changes and not dry_run:
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return changes


def run_migration(step, dry_run=False, reverse=False):
    """마이그레이션 실행"""
    if step == "all":
        steps = [1, 2, 3, 4]
    else:
        steps = [int(step)]

    files = find_agents_files()
    total_changes = []

    for s in steps:
        mapping = STEP_MAPPINGS.get(s)
        if not mapping:
            print(f"  알 수 없는 Step: {s}")
            continue

        direction = "역방향" if reverse else "정방향"
        print(f"\n{'='*60}")
        print(f"  Step {s}: {direction} 마이그레이션")
        print(f"  매핑: {mapping}")
        print(f"{'='*60}")

        for filepath in files:
            changes = migrate_file(filepath, mapping, dry_run, reverse)
            for c in changes:
                mode = "[DRY-RUN] " if dry_run else ""
                print(f"  {mode}{c['project']}/{c['agent']}")
                print(f"    before: {c['before']}")
                print(f"    after:  {c['after']}")
            total_changes.extend(changes)

    print(f"\n총 {len(total_changes)}개 에이전트 변경" + (" (dry-run)" if dry_run else ""))
    return total_changes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 22 노드 마이그레이션")
    parser.add_argument("--step", required=True, help="1|2|3|4|all")
    parser.add_argument("--dry-run", action="store_true", help="미리보기만")
    parser.add_argument("--reverse", action="store_true", help="되돌리기")
    args = parser.parse_args()

    run_migration(args.step, args.dry_run, args.reverse)
