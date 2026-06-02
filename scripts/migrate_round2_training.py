#!/usr/bin/env python3
"""라운드 2 액션 통합을 학습 데이터·ibl_usage.db에 일괄 적용.

2026-05-28: 라운드 2 작업으로 30+개 액션이 단일 액션 + op 파라미터로 통합됐지만
학습 데이터(data/training/*.json)와 ibl_usage.db는 옛 액션 이름이 남아있어
해마 재학습 시 stale 패턴을 학습하게 된다. 이 스크립트가 양쪽을 동시 변환.

변환 규칙:
- (node, old_action) → (new_action, {파라미터 주입})
- 기존 파라미터는 보존, 주입 파라미터를 앞에 추가
- 빈도 가장 높은 30+종 매핑 (sense의 복잡한 단일 액션은 제외 — 별칭으로 처리)

실행: python3 scripts/migrate_round2_training.py [--apply]
  --apply 없으면 dry-run (변경 없이 통계만)
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 라운드 2 액션 통합 매핑.
# 값: (new_action, dict_of_params_to_inject)
ACTION_MIGRATIONS: dict[tuple[str, str], tuple[str, dict[str, str]]] = {
    # self 노드
    ("self", "list_switches"): ("switch", {"op": "list"}),
    ("self", "run_switch"): ("switch", {"op": "run"}),
    ("self", "list_triggers"): ("trigger", {"op": "list"}),
    ("self", "create_trigger"): ("trigger", {"op": "create"}),
    ("self", "enable_trigger"): ("trigger", {"op": "enable"}),
    ("self", "disable_trigger"): ("trigger", {"op": "disable"}),
    ("self", "update_trigger"): ("trigger", {"op": "update"}),
    ("self", "delete_trigger"): ("trigger", {"op": "delete"}),
    ("self", "get_trigger"): ("trigger", {"op": "get"}),
    ("self", "trigger_status"): ("trigger", {"op": "status"}),
    ("self", "trigger_history"): ("trigger", {"op": "history"}),
    ("self", "list_workflows"): ("workflow", {"op": "list"}),
    ("self", "save_workflow"): ("workflow", {"op": "save"}),
    ("self", "get_workflow"): ("workflow", {"op": "get"}),
    ("self", "delete_workflow"): ("workflow", {"op": "delete"}),
    ("self", "list_goals"): ("goal", {"op": "list"}),
    ("self", "goal_status"): ("goal", {"op": "status"}),
    ("self", "goal_kill"): ("goal", {"op": "kill"}),
    ("self", "log_attempt"): ("goal", {"op": "log"}),
    ("self", "get_attempts"): ("goal", {"op": "attempts"}),
    ("self", "memory_save"): ("memory", {"op": "save"}),
    ("self", "memory_search"): ("memory", {"op": "search"}),
    ("self", "memory_read"): ("memory", {"op": "read"}),
    ("self", "memory_delete"): ("memory", {"op": "delete"}),
    ("self", "health_save"): ("health", {"op": "save"}),
    ("self", "health_query"): ("health", {"op": "query"}),
    ("self", "photo_scan"): ("photo", {"op": "scan"}),
    ("self", "list_scans"): ("photo", {"op": "list_scans"}),
    ("self", "get_gallery"): ("photo", {"op": "gallery"}),
    ("self", "find_duplicates"): ("photo", {"op": "duplicates"}),
    ("self", "get_stats"): ("photo", {"op": "stats"}),
    ("self", "get_timeline"): ("photo", {"op": "timeline"}),
    ("self", "search_photos"): ("photo", {"op": "search"}),
    ("self", "photo_detail"): ("photo", {"op": "detail"}),
    # others 노드
    ("others", "delegate_project"): ("delegate", {"scope": "cross"}),
    ("others", "ask_sync"): ("delegate", {"mode": "sync"}),
    ("others", "delegate_workflow"): ("delegate", {"mode": "workflow"}),
    ("others", "agent_info"): ("agents", {}),
    ("others", "list_projects"): ("agents", {}),
    ("others", "neighbor_detail"): ("neighbors", {}),
    # limbs - browser-action
    ("limbs", "dblclick"): ("click", {"op": "double"}),
    ("limbs", "rightclick"): ("click", {"op": "right"}),
    # limbs - youtube
    ("limbs", "play"): ("music", {"op": "play"}),
    ("limbs", "queue_add"): ("music", {"op": "add"}),
    ("limbs", "skip"): ("music", {"op": "skip"}),
    ("limbs", "stop"): ("music", {"op": "stop"}),
    ("limbs", "youtube_download"): ("music", {"op": "download"}),
    # limbs - radio
    ("limbs", "radio_play"): ("radio", {"op": "play"}),
    ("limbs", "radio_stop"): ("radio", {"op": "stop"}),
    # limbs - cctv
    ("limbs", "cctv_open"): ("cctv", {"op": "open"}),
    ("limbs", "cctv_capture"): ("cctv", {"op": "capture"}),
}

# 모든 [node:action] 매칭 — 파라미터 블록은 별도로
ACTION_RE = re.compile(r'\[(\w+):(\w+)\]')


def _format_inject(inject: dict[str, str]) -> str:
    """{op: "list"} 형태 문자열로."""
    return ", ".join(f'{k}: "{v}"' for k, v in inject.items())


def migrate_code(code: str, stats: dict) -> str:
    """ibl 코드에서 옛 액션을 새 형식으로 변환.

    [self:run_switch]{switch_id: "x"} → [self:switch]{op: "run", switch_id: "x"}
    [self:list_switches] → [self:switch]{op: "list"}
    """
    if not isinstance(code, str):
        return code

    # 옛 액션 위치 + 그 뒤 파라미터 블록을 함께 처리.
    # 파이프라인(>>, &, ??)이 있어도 각 [node:action] 단위로 독립 처리.
    out = []
    pos = 0
    for m in ACTION_RE.finditer(code):
        node, action = m.group(1), m.group(2)
        key = (node, action)
        out.append(code[pos:m.start()])

        if key in ACTION_MIGRATIONS:
            new_action, inject = ACTION_MIGRATIONS[key]
            # 액션 헤더 변환
            new_header = f"[{node}:{new_action}]"

            # 파라미터 블록 처리 — m.end() 이후에 {로 시작하면 그 블록을 찾기.
            after = code[m.end():]
            param_block = ""
            if after.startswith("{"):
                # 중괄호 매칭 (간단한 depth count)
                depth = 0
                end_idx = -1
                for i, ch in enumerate(after):
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            end_idx = i
                            break
                if end_idx >= 0:
                    param_block = after[:end_idx + 1]

            # 파라미터 주입 + 기존 파라미터 결합
            if inject:
                inject_str = _format_inject(inject)
                if param_block:
                    inner = param_block[1:-1].strip()
                    if inner:
                        new_block = f"{{{inject_str}, {inner}}}"
                    else:
                        new_block = f"{{{inject_str}}}"
                else:
                    new_block = f"{{{inject_str}}}"
            else:
                new_block = param_block

            out.append(new_header + new_block)
            pos = m.end() + len(param_block)
            stats[f"{node}:{action}"] = stats.get(f"{node}:{action}", 0) + 1
        else:
            out.append(m.group(0))
            pos = m.end()

    out.append(code[pos:])
    return "".join(out)


def migrate_json_file(path: Path, apply: bool, stats: dict) -> tuple[int, int]:
    """학습 데이터 JSON 파일 변환. (전체 entry, 변환된 entry) 반환."""
    if not path.is_file():
        return (0, 0)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return (0, 0)

    changed = 0
    for entry in data:
        if not isinstance(entry, dict):
            continue
        code = entry.get("ibl_code", "")
        new_code = migrate_code(code, stats)
        if new_code != code:
            entry["ibl_code"] = new_code
            changed += 1

    if apply and changed > 0:
        # 백업
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_suffix(path.suffix + f".bak.migrate_{ts}")
        shutil.copy(path, backup)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  ✓ 백업: {backup.name}")

    return (len(data), changed)


def migrate_sqlite(db_path: Path, apply: bool, stats: dict) -> tuple[int, int]:
    """ibl_usage.db의 ibl_examples 테이블 변환."""
    if not db_path.is_file():
        return (0, 0)

    conn = sqlite3.connect(str(db_path))
    cur = conn.execute("SELECT id, ibl_code FROM ibl_examples")
    rows = cur.fetchall()

    updates = []
    for row_id, code in rows:
        new_code = migrate_code(code or "", stats)
        if new_code != (code or ""):
            updates.append((new_code, row_id))

    if apply and updates:
        # 백업
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = db_path.with_suffix(f".db.bak.migrate_{ts}")
        shutil.copy(db_path, backup)
        print(f"  ✓ DB 백업: {backup.name}")

        conn.executemany(
            "UPDATE ibl_examples SET ibl_code = ? WHERE id = ?",
            updates
        )
        conn.commit()

    conn.close()
    return (len(rows), len(updates))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제 적용 (기본 dry-run)")
    args = ap.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== 라운드 2 학습 데이터 마이그레이션 ({mode}) ===\n")

    json_stats: dict[str, int] = {}
    db_stats: dict[str, int] = {}

    # 학습 JSON 파일들
    training_dir = REPO / "data" / "training"
    print("--- 학습 데이터 JSON ---")
    for jf in sorted(training_dir.glob("*.json")):
        if ".bak." in jf.name:
            continue
        total, changed = migrate_json_file(jf, args.apply, json_stats)
        print(f"  {jf.name}: {changed}/{total} 변환")

    # ibl_usage.db
    print("\n--- ibl_usage.db ---")
    db_path = REPO / "data" / "ibl_usage.db"
    total, changed = migrate_sqlite(db_path, args.apply, db_stats)
    print(f"  ibl_examples: {changed}/{total} 변환")

    # 통계
    print("\n--- 변환 통계 (옛 액션별) ---")
    print("JSON:")
    for action, n in sorted(json_stats.items(), key=lambda x: -x[1]):
        print(f"  {action}: {n}")
    print("DB:")
    for action, n in sorted(db_stats.items(), key=lambda x: -x[1]):
        print(f"  {action}: {n}")

    if not args.apply:
        print("\n[DRY-RUN] 변경 없음. --apply 로 실제 적용.")


if __name__ == "__main__":
    main()
