"""대상별좁혀읽기의 값 처리. 파일 접근은 IBL self:grep/read가 맡는다."""
import hashlib
import json
import re
import sys


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name}: {minimum}~{maximum} 정수가 필요합니다")
    return value


def prepare(args):
    targets = args.get("targets")
    if not isinstance(targets, list) or not 1 <= len(targets) <= 64:
        raise ValueError("targets: 1~64개의 {name,pattern} 목록이 필요합니다")
    names = set()
    result = []
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError("대상은 {name,pattern} 객체여야 합니다")
        name, pattern = target.get("name"), target.get("pattern")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("대상 name은 비어 있지 않고 중복되지 않아야 합니다")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(f"{name}: 비어 있지 않은 정규식 pattern이 필요합니다")
        names.add(name)
        problem = ""
        try:
            re.compile(pattern)
        except re.error as exc:
            problem = f"잘못된 정규식: {exc}"
        result.append({"name": name, "pattern": pattern, "problem": problem})
    return {"targets": result,
            "before": integer(args.get("before", 2), "before", 0, 100),
            "after": integer(args.get("after", 29), "after", 0, 200),
            "limit": integer(args.get("limit", 20), "limit", 1, 200)}


def plan(args):
    config, searches = args["config"], args["searches"]
    if len(searches) != len(config["targets"]):
        raise ValueError("대상과 검색 결과의 수가 다릅니다")
    reports, windows = [], []
    for target, search in zip(config["targets"], searches):
        report = {"name": target["name"], "pattern": target["pattern"],
                  "status": "pending", "reason": "", "matches": []}
        reports.append(report)
        if search["name"] != target["name"]:
            raise ValueError("검색 결과의 대상 순서가 다릅니다")
        if search.get("problem"):
            report.update(status="search_failed", reason=search["problem"])
            continue
        data = search["result"]
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("검색 결과는 items 봉투여야 합니다")
        report["search_scope"] = data.get("excluded", "")
        report["total_matches"] = data.get("total")
        report["search_complete"] = not bool(data.get("truncated") or data.get("partial"))
        if not report["search_complete"]:
            report.update(status="partial", reason="검색이 잘렸습니다. 루트·패턴을 좁히거나 검색상한을 늘리세요")
        hits = data["items"]
        # grep의 상한 경계 감지를 위해 한 건 여유 있게 요청한다. 초과는 숨기지 않는다.
        if len(hits) > config["limit"]:
            report.update(status="partial", reason="대상별 검색상한 초과. 루트·패턴을 좁히거나 검색상한을 늘리세요",
                          search_complete=False)
        seen = set()
        for hit in hits[:config["limit"]]:
            path, line, text = hit["파일"], hit["줄번호"], hit["내용"]
            if not isinstance(path, str) or not path or type(line) is not int or line < 1 or not isinstance(text, str):
                raise ValueError("검색 위치의 경로·줄번호·내용이 올바르지 않습니다")
            if (path, line) in seen:
                continue
            seen.add((path, line))
            match = {"path": path, "line": line, "matched_text": text}
            report["matches"].append(match)
            windows.append({"path": path, "start_line": max(1, line - config["before"]),
                            "end_line": line + config["after"], "matches": [match]})
        if not report["matches"] and report["status"] == "pending":
            report.update(status="not_found", reason="지정한 검색 범위에서 일치 없음(저장소 전체의 부재를 뜻하지 않음)")
    merged = []
    for window in sorted(windows, key=lambda row: (row["path"], row["start_line"], row["end_line"])):
        if merged and merged[-1]["path"] == window["path"] and window["start_line"] <= merged[-1]["end_line"] + 1:
            merged[-1]["end_line"] = max(merged[-1]["end_line"], window["end_line"])
            merged[-1]["matches"].extend(window["matches"])
        else:
            merged.append(window)
    for index, window in enumerate(merged):
        window["id"] = f"range-{index + 1}"
        for match in window.pop("matches"):
            match["range_id"] = window["id"]
    return {"items": reports, "ranges": merged,
            "unmerged_ranges": len(windows), "read_requests": len(merged)}


def finish(args):
    planned, reads = args["plan"], args["reads"]
    if len(reads) != len(planned["ranges"]):
        raise ValueError("읽기 범위와 결과의 수가 다릅니다")
    snippets = []
    for window, read in zip(planned["ranges"], reads):
        if read["id"] != window["id"]:
            raise ValueError("읽기 결과의 범위 순서가 다릅니다")
        snippet = {**window, "status": "read", "reason": ""}
        if read.get("problem"):
            snippet.update(status="read_failed", reason=read["problem"])
        else:
            value = read["result"]
            text = value.get("text")
            if not isinstance(text, str):
                raise ValueError("읽기 결과에 text가 없습니다")
            # 경로와 실제 범위는 재열람에, 지문은 반환한 발췌의 동일성 확인에 쓴다.
            metadata = value.get("data", {})
            total = metadata.get("total_lines")
            end = min(window["end_line"], total) if type(total) is int else window["end_line"]
            lines = text.splitlines()
            snippet.update(text=text, end_line=end,
                           source_path=metadata.get("path", window["path"]),
                           excerpt_sha256=hashlib.sha256(text.encode()).hexdigest())
            expected = max(0, end - window["start_line"] + 1)
            if (len(lines) < expected or metadata.get("start_line", window["start_line"]) != window["start_line"]
                    or metadata.get("partial") or metadata.get("truncated")):
                snippet.update(status="partial", reason="요청 범위의 본문이 완전히 확인되지 않았습니다")
        snippets.append(snippet)
    by_id = {row["id"]: row for row in snippets}
    for report in planned["items"]:
        problems = []
        for match in report["matches"]:
            snippet = by_id[match["range_id"]]
            if snippet["status"] != "read":
                problems.append(snippet["reason"])
                continue
            offset = match["line"] - snippet["start_line"]
            lines = snippet["text"].splitlines()
            # 검색 뒤 파일 수정/줄 이동을 확인한다. grep의 긴 줄 표시는 접두로 대조한다.
            expected = match["matched_text"]
            shortened = expected.endswith(" …(줄 잘림)")
            if shortened:
                expected = expected[:-len(" …(줄 잘림)")]
            actual = lines[offset].rstrip() if 0 <= offset < len(lines) else None
            if actual is None or (not actual.startswith(expected) if shortened else actual != expected):
                problems.append("검색 뒤 일치 줄이 달라졌습니다. 해당 대상을 다시 조회하세요")
        if problems:
            report["status"] = "partial"
            report["reason"] = "; ".join(dict.fromkeys(filter(None, [report["reason"], *problems])))
        elif report["status"] == "pending":
            report["status"] = "read"
    return {**planned, "ranges": snippets,
            "all_targets_read": all(row["status"] == "read" for row in planned["items"]),
            "scope": "지정한 정규식과 검색 범위의 일치 주변만 확인. 함수 전체·의미 판단·제외 파일은 미검증"}


def run(args):
    return {"prepare": prepare, "plan": plan, "finish": finish}[args["op"]](args)


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.load(sys.stdin)), ensure_ascii=False, allow_nan=False))
    except (KeyError, ValueError, TypeError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
