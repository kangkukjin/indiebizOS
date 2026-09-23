"""보고서 검색의 질의별 결과 보존. 빈 결과·장애·잘못된 통화를 구분한다."""
import copy
import hashlib
import json
import re


class SearchIncomplete(ValueError):
    """질의 일부가 실제로 실패했다. 성공/빈 결과는 이미 보존되어 있다."""


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def requests(state):
    outcomes = state.get("search_outcomes", {})
    expected = {q["stratum"]: q["query"] for q in state["queries"]}
    for s, result in outcomes.items():
        require(s in expected and result.get("query") == expected[s]
                and result.get("receipt_hash") == digest({k: v for k, v in result.items() if k != "receipt_hash"}),
                "저장된 검색 범위·결과 지문 변경")
    return [{**q, "attempt": len(outcomes.get(q["stratum"], {}).get("attempts", [])) + 1}
            for q in state["queries"]
            if outcomes.get(q["stratum"], {}).get("status") not in ("ok", "empty")]


def wrappers(state, records):
    """옛 평탄화 결과도 원래 질의와 대조해 보존한다. 오류 문구를 성공으로 바꾸지 않는다."""
    if not records or any("data" in r or "attempt" in r for r in records):
        return records
    expected = {q["stratum"]: q["query"] for q in state["queries"]}
    grouped = {}
    for row in records:
        s = row.get("stratum")
        require(s in expected and row.get("query") == expected[s], "검색 질의·층 변경")
        grouped.setdefault(s, []).append(row)
    out = []
    for s, group in grouped.items():
        failed = [r for r in group if r.get("_error")]
        require(not failed or len(group) == 1, "같은 검색의 성공·오류 혼합")
        item = {"stratum": s, "query": expected[s], "attempt": 1}
        if failed:
            item["_error"] = failed[0]["_error"]
        else:
            item["data"] = {"success": True, "items": group}
        out.append(item)
    return out


def accept(state, records):
    expected = {q["stratum"]: q["query"] for q in state["queries"]}
    records = wrappers(state, records)
    scopes = [r.get("stratum") for r in records]
    require(len(scopes) == len(set(scopes)) and set(scopes) <= set(expected),
            "검색 층 누락·중복 또는 미등록 층")
    outcomes = copy.deepcopy(state.get("search_outcomes", {}))
    pending = {q["stratum"] for q in requests(state)}
    require(pending <= set(scopes), "미완료 검색 층의 응답 누락")
    for row in records:
        s = row["stratum"]
        require(row.get("query") == expected[s], "검색 질의 변경")
        attempt = row.get("attempt")
        require(type(attempt) is int and attempt > 0, "검색 시도 번호 누락")
        old = outcomes.get(s, {})
        history = copy.deepcopy(old.get("attempts", []))
        fingerprint = digest(row)
        if attempt <= len(history):
            require(history[attempt - 1]["input_hash"] == fingerprint,
                    "확정된 검색 시도의 입력 변경")
            continue
        require(attempt == len(history) + 1 and old.get("status") not in ("ok", "empty"),
                "성공 검색 재실행 또는 검색 시도 순서 오류")
        data = row.get("data")
        error = row.get("_error")
        if not error:
            require(isinstance(data, dict), "검색 결과 봉투 누락")
            error = (data.get("error") or data.get("message") or "검색 도구 실패") if data.get("success") is False else None
        if error:
            status, items = "error", []
        else:
            require(not any(data.get(k) for k in ("partial", "error_count", "errors", "rows_dropped",
                                                   "rows_unprocessed", "unprocessed")),
                    "검색 내부의 부분 처리·누락을 빈 결과로 수용할 수 없습니다")
            items = data.get("items")
            require(isinstance(items, list) and len(items) <= 12, "검색 items 목록 또는 12건 상한 오류")
            require(data.get("count") is None or data["count"] == len(items), "검색 결과 count 불일치")
            require(all(isinstance(r, dict) and not r.get("_error")
                        and isinstance(r.get("video_id"), str)
                        and re.fullmatch(r"[A-Za-z0-9_-]{11}", r["video_id"]) for r in items),
                    "검색 영상 ID 또는 실패 행 오류")
            status = "ok" if items else "empty"
        history.append({"attempt": attempt, "input_hash": fingerprint, "status": status,
                        "response": copy.deepcopy(row),
                        **({"error": str(error)} if error else {})})
        outcomes[s] = {"query": expected[s], "status": status, "items": copy.deepcopy(items),
                       "attempts": history}
        outcomes[s]["receipt_hash"] = digest(outcomes[s])
    require(set(outcomes) == set(expected), "검색 5개 층의 실행 증거 누락")
    state["search_outcomes"] = outcomes
    failed = [s for s, result in outcomes.items() if result["status"] == "error"]
    if failed:
        raise SearchIncomplete("검색 장애가 남았습니다(성공 결과 보존): " + ", ".join(failed))
    return [{**r, "stratum": s, "query": result["query"]}
            for s, result in outcomes.items() for r in result["items"]]


def retry(state):
    failure = state.get("last_failure", {})
    require(failure.get("stage") == "search" and failure.get("kind") == "search_incomplete",
            "자동 재검색 대상인 검색 장애가 아닙니다")
    pending = requests(state)
    require(pending and all(q["attempt"] <= 2 for q in pending),
            "검색별 자동 재시도 1회를 사용했습니다. 성공 결과는 보존되어 있습니다")
    return {"items": pending, "count": len(pending), "run": state["run"]}
