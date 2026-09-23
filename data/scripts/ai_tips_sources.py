"""긴 원문: 전 구간 추출 → 후보별 관련 구간 색인 → 원문 근거 인계.

모델은 위치를 고른다. 원문·구간 범위·완료 영수증은 코드가 소유한다.
짧은 자료와 이미 완료된 이전 회차의 계약은 바꾸지 않는다.
"""
import copy
from pathlib import Path

LONG_CHARS = 36000
CHUNK_CHARS = 40000
UNIT_CHARS = 2000
EVIDENCE_CHARS = 36000


def envelope(items):
    return {"items": items, "count": len(items)}


def timed(units):
    return "\n".join(str(u["start"]) + "s " + u["text"] for u in units)


def units(segs):
    """긴 단일 세그먼트도 무손실 분할. 가상의 시간은 만들지 않는다."""
    result = []
    for i, seg in enumerate(segs):
        text = seg["text"]
        offset = 0
        while offset < len(text) or (offset == 0 and not text):
            end = min(len(text), offset + UNIT_CHARS)
            if end < len(text):
                boundary = text.rfind(" ", offset + UNIT_CHARS // 2, end)
                if boundary >= 0:
                    end = boundary + 1
            result.append({"unit_id": f"s{i}:{offset}", "segment": i, "offset": offset,
                           "start": seg["start"], "text": text[offset:end]})
            if not text:
                break
            offset = end
    return result


def source_rows(selected):
    """같은 원 세그먼트의 연속 문자 조각은 공백을 새로 넣지 않고 합친다."""
    result, previous = [], None
    for unit in selected:
        adjacent = (previous and previous["segment"] == unit["segment"]
                    and previous["offset"] + len(previous["text"]) == unit["offset"])
        if adjacent:
            result[-1]["text"] += unit["text"]
        else:
            result.append({"start": unit["start"], "text": unit["text"]})
        previous = unit
    return result


def chunks(source):
    """핵심 구간은 겹치지 않는다. 경계 양옆 두 단위는 문맥으로 한 번 더 읽는다."""
    groups, start, size = [], 0, 0
    for i, unit in enumerate(source):
        cost = len(unit["text"]) + len(unit["unit_id"]) + len(str(unit["start"])) + 50
        if i > start and size + cost > CHUNK_CHARS:
            groups.append((start, i))
            start, size = i, 0
        size += cost
    groups.append((start, len(source)))
    return [{"first": a, "last": b, "units": source[max(0, a - 2):min(len(source), b + 2)]}
            for a, b in groups]


def make_plan(h, state, requests):
    long = [vid for vid in state["sources"] if len(timed(h.source_segments(state, vid))) > LONG_CHARS]
    if not long:
        return envelope(requests)
    plan = {"version": 1, "long": long, "jobs": {}, "sources": {
        vid: state["sources"][vid]["hash"] for vid in state["sources"]}}
    for request in requests:
        vid = request["video_id"]
        source = units(h.source_segments(state, vid))
        parts = chunks(source) if vid in long else [{"first": 0, "last": len(source), "units": source}]
        for n, part in enumerate(parts):
            jid = vid + "-" + str(n + 1)
            path = Path(state["run"]) / ("chunk-" + jid + ".json")
            rows = source_rows(part["units"])
            h.atomic(path, h.transcript_document(rows))
            job = {**request, "job_id": jid, "path": str(path)}
            if vid in long:
                # 중복 판정은 후보를 다 모은 뒤 한다. 같은 원장 전체를 구간마다 반복 주입하지 않는다.
                job["known"] = []
                job["instruction"] += " 이번 파일은 전체 자막의 한 구간이다. 경계 문맥도 읽되 근거 없는 완결을 추측하지 마라."
            plan["jobs"][jid] = {"request": job, "first": part["first"], "last": part["last"],
                                 "units": part["units"], "hash": h.digest(rows)}
    plan["hash"] = h.digest(plan)
    state["source_plan"] = plan
    return pending_extraction(h, state)


def validate_plan(h, state):
    plan = state["source_plan"]
    h.require(plan["hash"] == h.digest({k: v for k, v in plan.items() if k != "hash"}), "자막 분할 계획 변경")
    for vid, fingerprint in plan["sources"].items():
        h.require(h.digest(h.source_segments(state, vid)) == fingerprint, "분할 원문 변경")
    for job in plan["jobs"].values():
        rows = h.load_json(Path(job["request"]["path"]), {}).get("items")
        h.require(h.digest(rows) == job["hash"], "자막 구간 파일 변경")
    return plan


def checked_receipts(h, state, name, jobs):
    receipts = state.get(name, {})
    for key, receipt in receipts.items():
        h.require(key in jobs and receipt["hash"] == h.digest(receipt["response"])
                  and receipt["request_hash"] == h.digest(jobs[key]), "구간 영수증·요청 변경")
    return receipts


def pending_extraction(h, state):
    jobs = validate_plan(h, state)["jobs"]
    done = checked_receipts(h, state, "source_extractions", jobs)
    return envelope([r["request"] for key, r in jobs.items() if key not in done])


def accept_extraction(h, state, data):
    if not state.get("source_plan"):
        return data
    jobs = validate_plan(h, state)["jobs"]
    done = checked_receipts(h, state, "source_extractions", jobs)
    value = h.unpack(data)
    received = [value] if isinstance(value, dict) and "video_id" in value else h.rows(value)
    h.require(len(received) == 1, "추출 구간 영수증은 한 건씩")
    row = received[0]
    jid = row.get("job_id")
    h.require(jid in jobs and row.get("video_id") == jobs[jid]["request"]["video_id"], "추출 구간·영상 변경")
    output = h.unpack(row.get("data"))
    h.require(isinstance(output, dict) and output.get("grounded") is True, "grounded 검증 누락")
    text = h.clean(" ".join(u["text"] for u in source_rows(jobs[jid]["units"])))
    for record in h.rows(output):
        h.text_field(record, "tip")
        h.grounded(state, row["video_id"], record)
        h.require(h.clean(record["_quote"]) in text, "추출 구간 밖의 인용")
    if jid in done:
        h.require(done[jid]["hash"] == h.digest(row), "완료된 구간 추출 변경")
    else:
        state.setdefault("source_extractions", {})[jid] = {
            "hash": h.digest(row), "request_hash": h.digest(jobs[jid]), "response": copy.deepcopy(row)}
    return envelope(received)


def candidates(h, state, data):
    for row in h.rows(data):
        accept_extraction(h, state, envelope([row]))
    jobs = validate_plan(h, state)["jobs"]
    done = checked_receipts(h, state, "source_extractions", jobs)
    h.require(set(done) == set(jobs), "자막 추출 구간 누락")
    result, seen = [], {}
    for jid in jobs:
        wrapper = done[jid]["response"]
        for row in h.rows(wrapper["data"]):
            key = h.digest([wrapper["video_id"], row["timestamp"], h.clean(row["tip"]), h.clean(row["_quote"])])
            if key in seen:
                seen[key]["source_jobs"].append(jid)
                continue
            record = {**row, "video_id": wrapper["video_id"], "source_jobs": [jid]}
            result.append(record)
            seen[key] = record
    return result


def scan_requests(h, state):
    if not state.get("source_plan") or "compared" in state.get("receipts", {}):
        return envelope([])
    plan = validate_plan(h, state)
    h.require("candidates" in state.get("receipts", {}), "후보 추출이 먼저 필요합니다")
    scope = h.digest([plan["hash"], state["candidates"]])
    scan = state.get("source_scan")
    if scan:
        h.require(scan["scope"] == scope and scan["hash"] == h.digest(scan["jobs"]), "원문 색인 범위 변경")
    else:
        jobs = {}
        for jid, part in plan["jobs"].items():
            vid = part["request"]["video_id"]
            if vid not in plan["long"]:
                continue
            selected = [{k: r[k] for k in ("candidate_id", "tip", "timestamp", "_quote")}
                        for r in state["candidates"] if r["video_id"] == vid]
            def request(group, number):
                sid = jid + "-scan-" + str(number)
                payload = {"scan_id": sid, "video_id": vid, "candidates": group,
                           "units": [{k: u[k] for k in ("unit_id", "start", "text")} for u in part["units"]]}
                item = h.task(state, "source_scan",
                    "전체 원문 색인의 한 구간이다. 후보 각각에 관련된 원문 위치를 모두 고른다. "
                    "실행 방법·선행 조건·예외·반례·주장 철회·다른 구간으로의 참조와 이해에 필요한 이웃 문맥을 포함한다. "
                    "후보 제목을 입증된 사실로 믿지 마라. 관련성이 애매하면 위치를 포함하고 uncertain=true로 표시한다. "
                    "무관한 단위는 제외하며, 내용을 요약하거나 새 문장을 만들지 않는다. "
                    "result={scan_id,decisions:[{candidate_id,unit_ids:[unit_id],uncertain:boolean,reason}]}. "
                    "모든 후보에 판정 한 건씩. 관련 구간이 없으면 unit_ids=[]와 그 이유를 적는다.", payload)["items"][0]
                return {"scan_id": sid, **item}
            group, number = [], 1
            for candidate in selected:
                if h.request_size(request(group + [candidate], number)) >= h.REQUEST_CAP:
                    h.require(group, "원문 구간과 후보 한 건이 입력 상한을 넘습니다")
                    item = request(group, number)
                    jobs[item["scan_id"]] = item
                    group, number = [], number + 1
                group.append(candidate)
                h.require(h.request_size(request(group, number)) < h.REQUEST_CAP, "원문 색인 입력 상한")
            if group:
                item = request(group, number)
                jobs[item["scan_id"]] = item
        scan = state["source_scan"] = {"scope": scope, "jobs": jobs, "hash": h.digest(jobs)}
    done = checked_receipts(h, state, "source_scans", scan["jobs"])
    return envelope([r for key, r in scan["jobs"].items() if key not in done])


def accept_scan(h, state, data):
    scan_requests(h, state)
    jobs = state["source_scan"]["jobs"]
    received = h.rows(data)
    h.require(len(received) == 1, "원문 색인 영수증은 한 건씩")
    row = received[0]
    sid = row.get("scan_id")
    h.require(sid in jobs and all(row.get(k) == jobs[sid][k] for k in ("task", "input")), "색인 요청 변경")
    result = h.unpack(row.get("result"))
    h.require(isinstance(result, dict) and result.get("scan_id") == sid, "색인 응답 ID 변경")
    expected = {r["candidate_id"] for r in jobs[sid]["input"]["candidates"]}
    decisions = h.keyed(result.get("decisions", []), "candidate_id", expected)
    ids = {r["unit_id"] for r in jobs[sid]["input"]["units"]}
    for decision in decisions.values():
        selected = decision.get("unit_ids")
        h.require(isinstance(selected, list) and all(isinstance(i, str) for i in selected)
                  and len(set(selected)) == len(selected) and set(selected) <= ids, "색인 원문 위치 변경·중복")
        h.require(type(decision.get("uncertain")) is bool, "색인 불확실성 판정 누락")
        h.text_field(decision, "reason")
    done = state.setdefault("source_scans", {})
    if sid in done:
        h.require(done[sid]["hash"] == h.digest(row), "완료된 원문 색인 변경")
    else:
        done[sid] = {"request_hash": h.digest(jobs[sid]), "hash": h.digest(row), "response": copy.deepcopy(row)}
    return envelope([{"scan_id": sid, "status": "accepted"}])


def indexed(h, state):
    if not state.get("source_plan"):
        return
    scan_requests(h, state)
    jobs = state["source_scan"]["jobs"]
    receipts = checked_receipts(h, state, "source_scans", jobs)
    h.require(set(receipts) == set(jobs), "전체 원문 색인 구간 누락")
    if "source_evidence" in state:
        for cid in state["source_evidence"]:
            evidence(h, state, cid)
        return
    collected = {}
    for candidate in state["candidates"]:
        vid, cid = candidate["video_id"], candidate["candidate_id"]
        if vid not in state["source_plan"]["long"]:
            continue
        source = units(h.source_segments(state, vid))
        decisions = [d for r in receipts.values() for d in r["response"]["result"]["decisions"]
                     if d["candidate_id"] == cid]
        selected = {u for d in decisions for u in d["unit_ids"]}
        # 첫 추출의 인용 주변은 색인 모델이 빠뜨려도 남긴다.
        for i, unit in enumerate(source):
            anchor = " ".join(r["text"] for r in source_rows(source[i:i + 2]))
            if h.clean(candidate["_quote"]) in h.clean(anchor):
                selected.update(u["unit_id"] for u in source[max(0, i - 2):i + 4])
        chosen = [u for u in source if u["unit_id"] in selected]
        h.require(chosen, "후보 원문 근거가 없습니다: " + cid)
        h.require(len(timed(chosen)) <= EVIDENCE_CHARS,
                  "한 후보의 관련 원문이 근거 묶음 상한을 넘습니다. 후보 범위를 분리해야 합니다: " + cid)
        path = Path(state["run"]) / ("evidence-" + cid + ".json")
        rows = source_rows(chosen)
        doc = h.transcript_document(rows)
        h.atomic(path, doc)
        collected[cid] = {"path": str(path), "hash": h.digest(rows), "video_id": vid,
                         "scope": "full_source_scan_selected_verbatim_evidence", "source_hash": state["sources"][vid]["hash"],
                         "scanned_units": len(source), "selected_units": [u["unit_id"] for u in chosen],
                         "uncertain": any(d["uncertain"] for d in decisions),
                         "scan_hash": h.digest(receipts)}
    old = state.get("source_evidence")
    h.require(old is None or old == collected, "확정 원문 근거 묶음 변경")
    state["source_evidence"] = collected
    state["source_evidence_hash"] = h.digest(collected)


def evidence(h, state, cid):
    validate_plan(h, state)
    h.require(state["source_evidence_hash"] == h.digest(state["source_evidence"]), "원문 근거 계획 변경")
    scan = state["source_scan"]
    h.require(scan["hash"] == h.digest(scan["jobs"]), "원문 색인 요청 변경")
    h.require(scan["scope"] == h.digest([state["source_plan"]["hash"], state["candidates"]]),
              "원문 색인의 후보 범위 변경")
    done = checked_receipts(h, state, "source_scans", scan["jobs"])
    record = state["source_evidence"][cid]
    h.require(record["scan_hash"] == h.digest(done) and set(done) == set(scan["jobs"]), "원문 색인 증거 변경")
    rows = h.load_json(Path(record["path"]), {}).get("items")
    h.require(h.digest(rows) == record["hash"], "원문 근거 묶음 변경")
    return rows, {k: v for k, v in record.items() if k not in ("path", "selected_units")}


def coverage(h, state):
    if not state.get("source_plan"):
        return {"mode": "complete_transcripts"}
    plan = validate_plan(h, state)
    done = checked_receipts(h, state, "source_extractions", plan["jobs"])
    h.require(set(done) == set(plan["jobs"]), "최종 검수의 추출 구간 증거 누락")
    scan = state["source_scan"]
    h.require(scan["scope"] == h.digest([plan["hash"], state["candidates"]])
              and scan["hash"] == h.digest(scan["jobs"]), "최종 검수의 색인 범위 변경")
    scanned = checked_receipts(h, state, "source_scans", scan["jobs"])
    h.require(set(scanned) == set(scan["jobs"]), "최종 검수의 색인 구간 증거 누락")
    return {"mode": "full_extraction_and_relevance_scan_then_verbatim_evidence",
            "long_videos": plan["long"], "extraction_parts": len(done), "scan_parts": len(scanned),
            "plan_hash": plan["hash"], "scan_hash": h.digest(scanned),
            "note": "관련 위치는 AI 의미 판단. 후속 내용 검토가 자막 전체를 다시 읽었다는 뜻이 아니다."}


def detail_requests(h, state, requests):
    if not state.get("source_plan"):
        return envelope(requests)
    result = []
    for request in requests:
        vid = request["video_id"]
        if vid not in state["source_plan"]["long"]:
            result.append({**request, "detail_id": vid})
            continue
        for candidate in state["chosen"]:
            if candidate["video_id"] != vid:
                continue
            cid = candidate["candidate_id"]
            evidence(h, state, cid)
            result.append({"video_id": vid, "detail_id": cid, "path": state["source_evidence"][cid]["path"],
                           "instruction": "전체 자막의 모든 구간을 후보와 대조해 모은 원문이다. "
                           "지정 후보 정확히 한 행. candidate_id 보존. 명시된 방법만 how에 적고 없으면 빈 문자열. "
                           "조건·반례를 hype에 반영. 생략된 구간을 추측하지 마라. 후보: " + h.canonical(candidate)})
    state["source_detail_jobs"] = {r["detail_id"]: r for r in result}
    return envelope(result)


def detail_records(h, state, data):
    jobs = state["source_detail_jobs"]
    received = h.keyed(h.rows(data), "detail_id", jobs)
    result = []
    for key, wrapper in received.items():
        vid = jobs[key]["video_id"]
        h.require(wrapper["video_id"] == vid, "상세 원문 영상 변경")
        records = h.extraction(state, envelope([wrapper]), [vid])
        expected = {key} if key in state["source_evidence"] else {
            r["candidate_id"] for r in state["chosen"] if r["video_id"] == vid}
        h.keyed(records, "candidate_id", expected)
        if key in state["source_evidence"]:
            source, _ = evidence(h, state, key)
            text = h.clean(" ".join(r["text"] for r in source))
            h.require(all(h.clean(r["_quote"]) in text for r in records), "상세 근거 묶음 밖의 인용")
        result.extend(records)
    return result


def review_groups(h, state):
    result = []
    for vid in sorted({r["video_id"] for r in state["details"]}):
        subset = [r for r in state["details"] if r["video_id"] == vid]
        if vid in state.get("source_plan", {}).get("long", []):
            for row in subset:
                source, scope = evidence(h, state, row["candidate_id"])
                result.append((vid, [row], timed(source), scope))
        else:
            result.append((vid, subset, h.source_text(state, vid), {"scope": "complete"}))
    return result


def review_rows(h, state, data):
    if not state.get("source_plan"):
        return h.rows(data)
    expected = state["source_review_jobs"]
    received = h.keyed(h.rows(data), "source_review_id", expected)
    merged = {}
    for key, wrapper in received.items():
        plan = expected[key]
        h.require(h.digest(wrapper.get("input")) == plan["hash"], "내용 검토 원문·범위 변경")
        result = h.unpack(wrapper.get("result"))
        h.require(isinstance(result, dict) and result.get("video_id") == plan["video_id"], "검토 영상 변경")
        decisions = h.keyed(result.get("decisions", []), "candidate_id", plan["ids"])
        vid = plan["video_id"]
        merged.setdefault(vid, {"video_id": vid, "result": {"video_id": vid, "decisions": []}})
        merged[vid]["result"]["decisions"].extend(decisions.values())
    return list(merged.values())
