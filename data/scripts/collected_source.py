"""수집한 웹 원문의 저장본(crawl의 source_ref.path)을 다시 읽는다.

수집과 읽기가 다른 호출로 갈라졌을 때, 같은 주소를 다시 받거나 저장 JSON을 매번 새 코드로
파싱하지 않기 위한 값 연산이다. 저장본을 그대로 읽으며 네트워크·모델을 부르지 않는다.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # 문맥 선택은 수집관용구의 것을 쓴다
import boot_paths  # noqa: E402,F401


def _integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name}은 {minimum} 이상의 정수여야 합니다.")
    return value


def _paths(args):
    paths = args.get("paths")
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list) or not paths or any(not isinstance(p, str) or not p.strip() for p in paths):
        raise ValueError("paths에는 저장본 경로(source_ref.path 또는 sources의 source_path) 목록이 필요합니다.")
    seen, unique = set(), []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def _load(path):
    """저장 폴더 안의 수집 원문만 연다. 못 여는 이유는 주소별로 돌려준다."""
    from common.spill import spill_dir
    root = os.path.realpath(spill_dir())
    real = os.path.realpath(path)
    if os.path.commonpath([root, real]) != root:
        return None, "수집 저장 폴더 밖의 경로입니다."
    if not os.path.isfile(real):
        return None, "저장본이 없습니다(보존 기간이 지났을 수 있습니다). 같은 주소를 다시 수집하세요."
    try:
        with open(real, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, f"저장본을 읽지 못했습니다: {exc}"
    if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not isinstance(data.get("text"), str):
        return None, "수집 원문 저장본 형식이 아닙니다."
    return data, None


def _summary(path, data):
    return {"source_path": path, "ok": True, "url": data.get("resolved_url") or data.get("url"),
            "title": data.get("title") or "", "paragraphs": len(data["items"]), "chars": len(data["text"]),
            "source_truncated": bool(data.get("truncated"))}


def _rows(path, items):
    return [{"source_path": path, **row} for row in items if isinstance(row, dict)]


def run(args):
    op = args.get("op")
    if op not in ("info", "find", "range"):
        raise ValueError("op는 info·find·range 중 하나입니다.")
    paths = _paths(args)
    if op == "find":
        pattern = args.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("find에는 pattern(정규식)이 필요합니다.")
        context = _integer(args.get("context", 0), "context")
        limit = _integer(args.get("limit", 8), "limit")
        from collection_idioms import match_context
    if op == "range":
        start = _integer(args.get("start", 1), "start", 1)
        end = _integer(args.get("end", start), "end", 1)
        if end < start:
            raise ValueError("end는 start 이상이어야 합니다.")
    items, sources, omitted = [], [], 0
    for path in paths:
        data, problem = _load(path)
        if problem:
            sources.append({"source_path": path, "ok": False, "error": problem})
            continue
        summary = _summary(path, data)
        if op == "find":
            found = match_context({"source": {"items": data["items"]}, "pattern": pattern,
                                   "limit": limit, "context": context})
            info = found.get("match_info") or {}
            summary["match_info"] = info
            omitted += info.get("omitted_matches") or 0
            items.extend(_rows(path, found.get("items") or []))
        elif op == "range":
            chosen = [row for row in data["items"]
                      if isinstance(row, dict) and start <= (row.get("paragraph_index") or 0) <= end]
            summary["returned"] = len(chosen)
            items.extend(_rows(path, chosen))
        sources.append(summary)
    failed = sum(not row["ok"] for row in sources)
    out = {"items": items, "count": len(items), "sources": sources, "ok": failed == 0, "failed": failed}
    if omitted:
        # 호출자가 고른 개수다. 원천 잘림과 구별되도록 selection으로 표시한다.
        out.update(truncated=True, truncations=[{"scope": "selection", "source": "collected_source.find",
                                                 "unit": "matches", "omitted": omitted}])
    return out


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.load(sys.stdin)), ensure_ascii=False, allow_nan=False))
    except (KeyError, ValueError, TypeError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
