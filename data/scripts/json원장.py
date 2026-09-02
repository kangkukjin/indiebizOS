#!/usr/bin/env python3
"""JSON 배열 원장의 append/upsert/set을 원자적으로 수행한다.

경로는 저장소 루트 기준이며 루트 밖 쓰기는 거절한다. args 예:
  {"path":"outputs/x.json", "op":"append", "item":{...}, "max_items":10}
  {"path":"outputs/x.json", "op":"upsert", "target":"covered", "key":"id", "items":[...]}
  {"path":"outputs/x.json", "op":"set", "target":"cursor", "value":3}
  {"path":"outputs/x.json", "op":"append", "item":{...},
   "list_limits":{"tags":{"max_items":25, "max_item_len":24}}}
     — list_limits: 항목 안 배열 필드의 개수·원소 길이 상한. 넘으면 쓰지 않고 실패한다.
       (2026-09-02: 커버리지 원장 태그가 60자 문장 × 호당 70개로 자라 매일 63KB 를 읽게
       된 자리 — "명사구 태그" 규약을 가이드 산문이 아니라 이 관문이 집행한다.)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _target_path(raw):
    path = Path(str(raw or ""))
    if not path.is_absolute():
        path = _ROOT / path
    path = path.resolve()
    try:
        path.relative_to(_ROOT)
    except ValueError as exc:
        raise ValueError("JSON 원장 경로는 indiebizOS 저장소 안이어야 합니다.") from exc
    return path


def _parts(raw):
    if raw in (None, "", "/"):
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return [x for x in str(raw).strip("/.").replace("/", ".").split(".") if x]


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
    value = item
    for part in _parts(dotted):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _check_list_limits(item, limits):
    """항목의 배열 필드에 개수·원소 길이 상한을 건다 — 넘으면 정직 실패(조용한 절단 금지)."""
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
            raise ValueError(
                f"'{field}' 항목 수 {len(values)} 가 상한 {int(max_items)} 을 넘습니다 — "
                f"태그는 호당 핵심 명사구만 남겨라.")
        if max_len not in (None, ""):
            bad = [str(v) for v in values if len(str(v)) > int(max_len)]
            if bad:
                raise ValueError(
                    f"'{field}' 원소 {len(bad)}개가 {int(max_len)}자를 넘습니다 "
                    f"(예: {bad[0][:40]}) — 문장이 아니라 명사구로 적어라.")


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


def main():
    try:
        args = json.loads(sys.stdin.read() or "{}")
        path = _target_path(args.get("path"))
        op = str(args.get("op") or "append").lower()
        target = _parts(args.get("target"))
        if path.exists():
            root = json.loads(path.read_text(encoding="utf-8"))
        else:
            root = [] if not target and op in ("append", "upsert") else {}

        changed = []
        if op in ("append", "upsert"):
            array = _get_target(root, target, create_list=True)
            if not isinstance(array, list):
                raise ValueError("append/upsert target은 JSON 배열이어야 합니다.")
            incoming = args.get("items")
            if incoming is None:
                incoming = [args.get("item")]
            if not isinstance(incoming, list):
                incoming = [incoming]
            if any(item is None for item in incoming):
                raise ValueError("item 또는 items가 필요합니다.")
            for item in incoming:
                _check_list_limits(item, args.get("list_limits"))

            if op == "append":
                array.extend(incoming)
                changed = incoming
            else:
                key = str(args.get("key") or "id")
                for item in incoming:
                    if not isinstance(item, dict) or _key_value(item, key) is None:
                        raise ValueError(f"upsert 항목마다 key '{key}'가 필요합니다.")
                    value = _key_value(item, key)
                    index = next((i for i, row in enumerate(array)
                                  if isinstance(row, dict)
                                  and _key_value(row, key) == value), None)
                    old = array.pop(index) if index is not None else None
                    # 갱신된 행도 이번 관측의 최신 행이다. 끝으로 보내야 max_items
                    # 롤링이 방금 갱신한 항목을 오래된 위치에서 잘라내지 않는다.
                    array.append({**old, **item} if isinstance(old, dict) else item)
                    changed.append(item)
            max_items = args.get("max_items")
            if max_items not in (None, ""):
                keep = max(0, int(max_items))
                if len(array) > keep:
                    del array[:len(array) - keep]
            count = len(array)
        elif op == "set":
            # 키 부재와 명시적 null 은 다르다 — get() 으로 읽으면 value 를 빠뜨린
            # 호출이 대상을(target 없으면 파일 전체를) 조용히 null 로 덮고 성공을
            # 보고한다. null 을 정말 쓰려면 {"value": null} 로 명시할 것.
            if "value" not in args:
                raise ValueError("set 에는 value 키가 필요합니다 (item/items 는 append/upsert 전용).")
            value = args["value"]
            if not target:
                root = value
            else:
                parent, key = _slot(root, target, create=True)
                if not isinstance(parent, dict):
                    raise ValueError("set target의 부모가 객체가 아닙니다.")
                parent[key] = value
            changed = [{"target": ".".join(target) or "/", "value": value}]
            count = 1
        else:
            raise ValueError("op은 append|upsert|set 중 하나여야 합니다.")

        _atomic_json(path, root)
        print(json.dumps({"success": True, "op": op, "path": str(path),
                          "count": count, "items": changed}, ensure_ascii=False))
    except (OSError, ValueError, TypeError) as exc:
        # 사유는 stderr 로도 낸다 — 러너가 실패 봉투에 싣는 것은 stderr_tail 이라,
        # stdout 에만 두면 호출부가 로그 파일을 열어야 이유를 안다.
        print(str(exc), file=sys.stderr)
        print(json.dumps({"success": False, "items": [], "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
