"""
House Designer v4 - Undo/Redo & 스냅샷 시스템
변경 전 상태를 스택에 저장하여 되돌리기/다시하기 지원
명명 스냅샷으로 특정 시점 저장/비교
"""
import copy

MAX_UNDO_STACK = 50


def _ensure_history(design):
    """_history 구조 초기화 (없으면 생성)"""
    if "_history" not in design:
        design["_history"] = {
            "undo_stack": [],
            "redo_stack": [],
            "snapshots": {},
        }
    h = design["_history"]
    if "undo_stack" not in h:
        h["undo_stack"] = []
    if "redo_stack" not in h:
        h["redo_stack"] = []
    if "snapshots" not in h:
        h["snapshots"] = {}
    return h


def _design_state(design):
    """_history를 제외한 설계 데이터의 deep copy"""
    state = {}
    for k, v in design.items():
        if k == "_history":
            continue
        state[k] = copy.deepcopy(v)
    return state


def _restore_state(design, state):
    """저장된 상태를 design에 복원 (_history 유지)"""
    history = design.get("_history")
    keys_to_remove = [k for k in design if k != "_history"]
    for k in keys_to_remove:
        del design[k]
    for k, v in state.items():
        if k == "_history":
            continue
        design[k] = copy.deepcopy(v)
    if history:
        design["_history"] = history


def push_state(design, label=""):
    """현재 상태를 undo 스택에 저장. action 실행 전에 호출."""
    h = _ensure_history(design)
    state = _design_state(design)
    h["undo_stack"].append({"label": label, "state": state})
    # 스택 크기 제한
    if len(h["undo_stack"]) > MAX_UNDO_STACK:
        h["undo_stack"] = h["undo_stack"][-MAX_UNDO_STACK:]
    # 새 변경이 발생하면 redo 스택 초기화
    h["redo_stack"].clear()


def undo(design):
    """마지막 변경을 되돌림"""
    h = _ensure_history(design)
    if not h["undo_stack"]:
        return {"success": False, "error": "되돌릴 작업이 없습니다."}

    # 현재 상태를 redo에 저장
    current_state = _design_state(design)
    entry = h["undo_stack"].pop()
    h["redo_stack"].append({"label": entry["label"], "state": current_state})

    # 이전 상태 복원
    _restore_state(design, entry["state"])

    remaining = len(h["undo_stack"])
    label_msg = f" ({entry['label']})" if entry["label"] else ""
    return {
        "success": True,
        "message": f"작업 되돌림{label_msg}. 남은 실행취소: {remaining}개",
        "remaining_undo": remaining,
        "remaining_redo": len(h["redo_stack"]),
    }


def redo(design):
    """되돌린 변경을 다시 적용"""
    h = _ensure_history(design)
    if not h["redo_stack"]:
        return {"success": False, "error": "다시 실행할 작업이 없습니다."}

    # 현재 상태를 undo에 저장
    current_state = _design_state(design)
    entry = h["redo_stack"].pop()
    h["undo_stack"].append({"label": entry["label"], "state": current_state})

    # 다음 상태 복원
    _restore_state(design, entry["state"])

    remaining = len(h["redo_stack"])
    label_msg = f" ({entry['label']})" if entry["label"] else ""
    return {
        "success": True,
        "message": f"작업 다시 실행{label_msg}. 남은 다시실행: {remaining}개",
        "remaining_undo": len(h["undo_stack"]),
        "remaining_redo": remaining,
    }


def create_snapshot(design, name):
    """현재 상태를 명명 스냅샷으로 저장"""
    if not name:
        return {"success": False, "error": "스냅샷 이름이 필요합니다."}
    h = _ensure_history(design)
    h["snapshots"][name] = _design_state(design)
    return {
        "success": True,
        "message": f"스냅샷 '{name}' 저장됨",
        "snapshot_count": len(h["snapshots"]),
    }


def restore_snapshot(design, name):
    """명명 스냅샷으로 복원"""
    h = _ensure_history(design)
    if name not in h.get("snapshots", {}):
        available = list(h.get("snapshots", {}).keys())
        return {"success": False, "error": f"스냅샷 '{name}'을(를) 찾을 수 없습니다. 사용 가능: {available}"}

    # 복원 전 현재 상태를 undo에 저장
    push_state(design, f"restore_snapshot:{name}")
    _restore_state(design, h["snapshots"][name])

    return {"success": True, "message": f"스냅샷 '{name}'으로 복원됨"}


def list_history(design):
    """히스토리 상태 조회"""
    h = _ensure_history(design)
    undo_labels = [e["label"] for e in h["undo_stack"]]
    redo_labels = [e["label"] for e in h["redo_stack"]]
    snapshot_names = list(h.get("snapshots", {}).keys())

    return {
        "success": True,
        "undo_count": len(undo_labels),
        "redo_count": len(redo_labels),
        "undo_labels": undo_labels[-10:],  # 최근 10개만
        "redo_labels": redo_labels[-10:],
        "snapshots": snapshot_names,
        "message": f"실행취소: {len(undo_labels)}개, 다시실행: {len(redo_labels)}개, 스냅샷: {len(snapshot_names)}개",
    }


def compare_snapshots(design, name_a, name_b):
    """두 스냅샷 간 차이 비교"""
    h = _ensure_history(design)
    snapshots = h.get("snapshots", {})

    if name_a not in snapshots:
        return {"success": False, "error": f"스냅샷 '{name_a}'을(를) 찾을 수 없습니다."}
    if name_b not in snapshots:
        return {"success": False, "error": f"스냅샷 '{name_b}'을(를) 찾을 수 없습니다."}

    a = snapshots[name_a]
    b = snapshots[name_b]
    diffs = _diff_designs(a, b)

    return {
        "success": True,
        "snapshot_a": name_a,
        "snapshot_b": name_b,
        "differences": diffs,
        "message": f"{len(diffs)}개 차이 발견",
    }


def _diff_designs(a, b):
    """두 설계 상태 간 주요 차이점 추출"""
    diffs = []

    # 기본 정보 비교
    for key in ["name", "site", "roof", "facade_defaults"]:
        va = a.get(key)
        vb = b.get(key)
        if va != vb:
            diffs.append({"field": key, "a": str(va)[:100], "b": str(vb)[:100]})

    # 층수 비교
    floors_a = a.get("floors", [])
    floors_b = b.get("floors", [])
    if len(floors_a) != len(floors_b):
        diffs.append({"field": "floor_count", "a": len(floors_a), "b": len(floors_b)})

    # 층별 비교
    a_map = {f["id"]: f for f in floors_a}
    b_map = {f["id"]: f for f in floors_b}
    all_ids = set(a_map.keys()) | set(b_map.keys())

    for fid in sorted(all_ids):
        fa = a_map.get(fid)
        fb = b_map.get(fid)
        if fa is None:
            diffs.append({"field": f"{fid}", "a": "없음", "b": "존재"})
            continue
        if fb is None:
            diffs.append({"field": f"{fid}", "a": "존재", "b": "없음"})
            continue

        for elem_type in ["rooms", "walls", "doors", "windows", "furniture", "stairs", "columns", "beams"]:
            ca = len(fa.get(elem_type, []))
            cb = len(fb.get(elem_type, []))
            if ca != cb:
                diffs.append({"field": f"{fid}.{elem_type}", "a": ca, "b": cb})

    return diffs
