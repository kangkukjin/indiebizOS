"""[self:ledger] — JSON 원장 원자 갱신·조회 (2026-09-04, 등록 스크립트에서 승격 — 옛 스크립트는 은퇴).

세계의 명사는 반증 가능한 데이터로 산다 — 그 데이터가 사는 곳이 원장이고, 이 낱말은 `{items}`
통화의 저장 반쪽이다. 네 관문은 전부 실사고에서 왔다(스키마를 가이드 산문이 아니라 관문이 집행):
  · set 은 target 필수 — target 없는 set 은 파일 전체를 value 로 갈아치우므로 거절(08-31: 순회 원장
    15KB → 105B, 봉투는 success). 정말 루트를 바꾸려면 replace_root:true. set 에 key 가 오면 거절(target 오타).
  · enum_fields{필드:[허용값]} — 밖의 값은 쓰지 않고 실패(09-02: verdict 가 문장이 되어 재방문 규칙 0회).
  · list_limits{필드:{max_items,max_item_len}} — 넘으면 쓰지 않고 실패(09-02: 태그 60자×70개 → 매일 63KB).
  · select 는 읽기 전용, 필요한 열·행만 items 로(09-02: 197KB 원장 통째 읽기 → id 585개를 문장에 박음).
경로는 `~workspace/`·절대·상대(저장소 루트 기준) — 저장소 밖 쓰기는 거절.
"""
import json
import os
import tempfile
from pathlib import Path

from runtime_utils import expand_body_path  # 경로 펼침 단일 해소점 (~workspace/·~)
from common.field_path import MISSING, parse_path, walk_path  # 점 경로 해석 단일 코어

_ROOT = Path(__file__).resolve().parents[5]  # indiebizOS/


def _target_path(raw):
    s = expand_body_path(str(raw or ""))
    path = Path(s)
    if not path.is_absolute():
        path = _ROOT / path
    path = path.resolve()
    try:
        path.relative_to(_ROOT)
    except ValueError as exc:
        raise ValueError("원장 경로는 indiebizOS 저장소 안이어야 합니다.") from exc
    return path


def _parts(raw):
    """target/key 의 점 경로 조각 — 해석은 common.field_path 한 벌. 슬래시 표기는 점 표기로 정규화만."""
    if raw in (None, "", "/"):
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    dotted = str(raw).strip("/").replace("/", ".")   # path-ok: 표기 정규화(슬래시→점)뿐, 해석은 아래 parse_path
    return [str(x) for x in parse_path(dotted)]


def _slot(root, parts, create=False):
    current = root
    for part in parts[:-1]:
        if not isinstance(current, dict):
            raise ValueError(f"target 중간값 '{part}'이 객체가 아닙니다.")
        if part not in current:
            if not create:
                raise ValueError(f"target을 찾을 수 없습니다: {'.'.join(parts)}")
            current[part] = {}
        current = current[part]
    return current, (parts[-1] if parts else None)


def _get_target(root, parts, create_list=False):
    if not parts:
        return root
    parent, key = _slot(root, parts, create=create_list)
    if not isinstance(parent, dict):
        raise ValueError("target의 부모가 객체가 아닙니다.")
    if key not in parent and create_list:
        parent[key] = []
    return parent.get(key)


def _key_value(item, dotted):
    """항목 안 점 경로 값 — 결측은 None(호출자 정책: upsert 키 부재·where 불일치)."""
    value = walk_path(item, ".".join(_parts(dotted)))
    return None if value is MISSING else value


def _check_list_limits(item, limits):
    """항목의 배열 필드에 개수·원소 길이 상한 — 넘으면 정직 실패(조용한 절단 금지)."""
    if not limits or not isinstance(item, dict):
        return
    if not isinstance(limits, dict):
        raise ValueError("list_limits 는 {필드: {max_items, max_item_len}} 객체여야 합니다.")
    for field, spec in limits.items():
        values = item.get(field)
        if values is None:
            continue
        if not isinstance(values, list):
            raise ValueError(f"'{field}' 는 배열이어야 합니다 (list_limits 적용 대상).")
        spec = spec or {}
        max_items = spec.get("max_items")
        max_len = spec.get("max_item_len")
        if max_items not in (None, "") and len(values) > int(max_items):
            raise ValueError(f"'{field}' 항목 수 {len(values)} 가 상한 {int(max_items)} 을 넘습니다 — "
                             f"태그는 호당 핵심 명사구만 남겨라.")
        if max_len not in (None, ""):
            bad = [str(v) for v in values if len(str(v)) > int(max_len)]
            if bad:
                raise ValueError(f"'{field}' 원소 {len(bad)}개가 {int(max_len)}자를 넘습니다 "
                                 f"(예: {bad[0][:40]}) — 문장이 아니라 명사구로 적어라.")


def _check_enum_fields(item, enums):
    """항목 필드의 값을 허용 집합에 가둔다 — 밖이면 정직 실패."""
    if not enums or not isinstance(item, dict):
        return
    if not isinstance(enums, dict):
        raise ValueError("enum_fields 는 {필드: [허용값…]} 객체여야 합니다.")
    for field, allowed in enums.items():
        if field not in item:
            continue
        if not isinstance(allowed, list) or not allowed:
            raise ValueError(f"enum_fields['{field}'] 는 비어 있지 않은 배열이어야 합니다.")
        value = item.get(field)
        if value not in allowed:
            raise ValueError(f"'{field}' 값 '{str(value)[:60]}' 은 허용값 {allowed} 밖입니다 — "
                             f"소지역별 판정은 sub_verdicts 에, 사유는 verdict_note 에 적어라.")


def _atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _load_root(path, target, op):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return [] if not target and op in ("append", "upsert") else {}


def _incoming(args):
    """item | items | items_file(JSON 파일 — 큰 payload 는 [self:write] 로 고정한 뒤 가리킨다)."""
    if args.get("items_file"):
        p = _target_path(args["items_file"])
        incoming = json.loads(p.read_text(encoding="utf-8"))
    else:
        incoming = args.get("items")
        if incoming is None:
            incoming = [args.get("item")]
    if not isinstance(incoming, list):
        incoming = [incoming]
    if any(item is None for item in incoming):
        raise ValueError("item 또는 items(또는 items_file)가 필요합니다.")
    return incoming


def _fail(exc):
    return {"success": False, "items": [], "error": str(exc)}


def op_select(tool_input):
    try:
        args = tool_input or {}
        path = _target_path(args.get("path"))
        target = _parts(args.get("target"))
        if not path.exists():
            return {"success": False, "items": [], "error": f"원장이 없습니다: {path}"}
        array = _get_target(json.loads(path.read_text(encoding="utf-8")), target, create_list=False)
        if not isinstance(array, list):
            raise ValueError("select target 은 JSON 배열이어야 합니다.")
        fields = args.get("fields")
        if fields is not None and not isinstance(fields, list):
            raise ValueError("fields 는 배열이어야 합니다.")
        where = args.get("where") or {}
        if not isinstance(where, dict):
            raise ValueError("where 는 {필드: 값} 객체여야 합니다.")
        rows = [r for r in array if isinstance(r, dict)
                and all(_key_value(r, k) == v for k, v in where.items())]
        total = len(rows)
        limit = args.get("limit")
        if limit not in (None, ""):
            rows = rows[:max(0, int(limit))]
        if fields:
            rows = [{k: _key_value(r, k) for k in fields} for r in rows]
        # 봉투 규모 불변식: total 은 where 를 통과한 모집단, limit 으로 덜 냈으면 표본
        return {"success": True, "op": "select", "path": str(path), "count": len(rows),
                "total": total, "truncated": total > len(rows), "items": rows}
    except (OSError, ValueError, TypeError) as exc:
        return _fail(exc)


def _write_rows(tool_input, op):
    try:
        args = tool_input or {}
        path = _target_path(args.get("path"))
        target = _parts(args.get("target"))
        root = _load_root(path, target, op)
        array = _get_target(root, target, create_list=True)
        if not isinstance(array, list):
            raise ValueError("append/upsert target은 JSON 배열이어야 합니다.")
        incoming = _incoming(args)
        for item in incoming:
            _check_list_limits(item, args.get("list_limits"))
            _check_enum_fields(item, args.get("enum_fields"))
        changed = []
        if op == "append":
            array.extend(incoming)
            changed = list(incoming)
        else:
            key = str(args.get("key") or "id")
            for item in incoming:
                if not isinstance(item, dict) or _key_value(item, key) is None:
                    raise ValueError(f"upsert 항목마다 key '{key}'가 필요합니다.")
                value = _key_value(item, key)
                index = next((i for i, row in enumerate(array)
                              if isinstance(row, dict) and _key_value(row, key) == value), None)
                old = array.pop(index) if index is not None else None
                # 갱신된 행도 이번 관측의 최신 행 — 끝으로 보내야 max_items 롤링이 방금 갱신한 항목을 안 자른다
                array.append({**old, **item} if isinstance(old, dict) else item)
                changed.append(item)
        max_items = args.get("max_items")
        if max_items not in (None, ""):
            keep = max(0, int(max_items))
            if len(array) > keep:
                del array[:len(array) - keep]
        _atomic_json(path, root)
        return {"success": True, "op": op, "path": str(path), "count": len(array), "items": changed}
    except (OSError, ValueError, TypeError) as exc:
        return _fail(exc)


def op_append(tool_input):
    return _write_rows(tool_input, "append")


def op_upsert(tool_input):
    return _write_rows(tool_input, "upsert")


def op_set(tool_input):
    try:
        args = tool_input or {}
        path = _target_path(args.get("path"))
        target = _parts(args.get("target"))
        root = _load_root(path, target, "set")
        # 키 부재와 명시적 null 은 다르다 — value 를 빠뜨린 호출이 대상을 조용히 null 로 덮지 않게.
        if "value" not in args:
            raise ValueError("set 에는 value 키가 필요합니다 (item/items 는 append/upsert 전용).")
        if "key" in args:
            raise ValueError(f"set 은 key 를 받지 않습니다 — target: \"{args['key']}\" 을 뜻했습니까? "
                             "(set 은 target 의 값을 바꾸는 연산, key 는 upsert 의 식별 필드)")
        value = args["value"]
        if not target:
            if args.get("replace_root") is not True:
                raise ValueError("target 없는 set 은 파일 전체를 value 로 갈아치웁니다 — 거절합니다. "
                                 "특정 키를 바꾸려면 target 을 주고, 정말 루트를 교체하려면 replace_root: true 를 명시하세요.")
            root = value
        else:
            parent, key = _slot(root, target, create=True)
            if not isinstance(parent, dict):
                raise ValueError("set target의 부모가 객체가 아닙니다.")
            parent[key] = value
        _atomic_json(path, root)
        return {"success": True, "op": "set", "path": str(path), "count": 1,
                "items": [{"target": ".".join(target) or "/", "value": value}]}
    except (OSError, ValueError, TypeError) as exc:
        return _fail(exc)
