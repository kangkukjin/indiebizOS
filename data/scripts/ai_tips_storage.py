"""AI 팁 보고서의 JSON 통화와 원장 저장. 모델의 내용 심사는 수행하지 않는다."""
import copy
import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
from common.pkg_utils import load_sibling

ROOT = Path(__file__).resolve().parents[2]
file_lock = load_sibling(str(ROOT / "data/packages/installed/tools/system_essentials/ledger_ops.py"),
                         "essentials_file_io").file_lock

def unpack(value):
    for _ in range(8):
        if isinstance(value, str):
            try:
                value = json.loads(value)
                continue
            except ValueError:
                return value
        if isinstance(value, dict) and "value" in value and "items" not in value:
            if value.get("success") is False:
                break
            value = value["value"]
            continue
        break
    return value


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else copy.deepcopy(default)


def atomic(path, value, text=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tips-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(value if text else json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def rows(value, *, failures=False):
    value = unpack(value)
    if isinstance(value, list):
        result = value
    else:
        require(isinstance(value, dict), "통화 봉투가 필요합니다")
        require(value.get("success") is not False, "상류 실패: " + str(value.get("error")))
        for key in ("rows_dropped", "rows_unprocessed", "unprocessed"):
            require(not value.get(key), key + "가 있어 완료로 처리할 수 없습니다")
        if "rows_requested" in value and "rows_processed" in value:
            require(value["rows_requested"] == value["rows_processed"], "each 미처리 행")
        require(not value.get("truncated"), "입력이 잘렸습니다")
        if not failures:
            require(not value.get("partial") and not value.get("error_count")
                    and not value.get("errors"), "부분 실패를 완료로 처리할 수 없습니다")
        result = value.get("items")
    require(isinstance(result, list), "items 목록이 필요합니다")
    result = [unpack(r) for r in result]
    require(all(isinstance(r, dict) for r in result), "모든 행은 객체여야 합니다")
    if not failures:
        require(not any(r.get("_error") for r in result), "실패 행이 있습니다")
    return result


def keyed(records, key, expected=None):
    ids = [r.get(key) for r in records]
    require(all(isinstance(k, str) and k for k in ids), key + " 누락")
    require(len(set(ids)) == len(ids), key + " 중복")
    if expected is not None:
        require(set(ids) == set(expected), key + " 누락 또는 추가: 전체 입력을 판정해야 합니다")
    return dict(zip(ids, records))


def answer(value):
    records = rows(value)
    require(len(records) == 1, "AI 결과는 원래 요청 1행을 보존해야 합니다")
    result = unpack(records[0].get("result"))
    require(isinstance(result, dict), "AI result 객체 누락")
    return result


def date(value):
    require(isinstance(value, str), "날짜는 YYYY-MM-DD 문자열이어야 합니다")
    return dt.date.fromisoformat(value)


def text_field(row, name, empty=False):
    value = row.get(name)
    require(isinstance(value, str) and (empty or value.strip()), name + " 문자열 누락")
    return value


def state_snapshot(root):
    covered = load_json(root / "_covered_videos.json", {"covered": [], "recent_topics": []})
    tips = load_json(root / "db/tips.json", [])
    require(isinstance(covered, dict) and isinstance(covered.get("covered"), list),
            "covered 원장 형식 오류")
    require(isinstance(tips, list), "tips 원장은 JSON 목록이어야 합니다")
    return {"covered": covered, "tips": tips}


def safe_inline(value):
    return str(value).replace("\n", " ").replace("[", "［").replace("]", "］")


def recover_transaction(root, transaction):
    # 동일 경로 쓰기 사이 중단되면 저널의 정확한 전/후 상태만 이어서 적용한다.
    for part in transaction["parts"]:
        path = root / part["path"]
        current = path.read_text(encoding="utf-8") if path.exists() else None
        require(current in (part["before"], part["after"]), "중단된 커밋 이후 다른 쓰기가 있어 복구 중단")
    for part in transaction["parts"]:
        atomic(root / part["path"], part["after"], text=True)
    transaction["done"] = True
    atomic(root / "_report_transaction.json", transaction)


def commit(state):
    root = Path(state["root"])
    journal = root / "_report_transaction.json"
    pending = load_json(journal)
    if pending and not pending.get("done"):
        require(pending.get("run") == state["run"], "다른 보고서의 중단된 커밋 복구가 먼저 필요합니다")
        recover_transaction(root, pending)
        return
    if pending and pending.get("run") == state["run"] and pending.get("done"):
        return
    require(digest(state_snapshot(root)) == state["snapshot_hash"],
            "조사 중 원장이 변경됐습니다. 최신 원장과 중복·통계를 재검토해야 합니다")
    targets = {"_covered_videos.json": json.dumps(state["projected"]["covered"], ensure_ascii=False, indent=2) + "\n",
               "db/tips.json": json.dumps(state["projected"]["tips"], ensure_ascii=False, indent=2) + "\n",
               state["report_name"]: state["markdown"]}
    report = root / state["report_name"]
    require(not report.exists(), "같은 이름의 보고서가 이미 있습니다. 덮어쓰지 않습니다")
    transaction = {"run": state["run"], "report_hash": state["report_hash"], "parts": []}
    for name, after in targets.items():
        path = root / name
        transaction["parts"].append({"path": name, "before": path.read_text(encoding="utf-8")
                                      if path.exists() else None, "after": after})
    atomic(journal, transaction)
    recover_transaction(root, transaction)
