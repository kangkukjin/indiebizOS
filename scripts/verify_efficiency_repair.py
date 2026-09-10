#!/usr/bin/env python3
"""3364/3377의 저장된 도구 결과를 새 모델 표시기로 재생. 모델·도구 재실행 없음."""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "backend"))
import boot_paths  # noqa: E402,F401
import json  # noqa: E402
from tempfile import TemporaryDirectory  # noqa: E402
from unittest.mock import patch  # noqa: E402
from supervision_store import TurnStore  # noqa: E402
from ibl_access import build_environment  # noqa: E402
from model_result_view import project_result  # noqa: E402

STORES = {3364: "e86355a39150493eb434c62da37e1679", 3377: "4a04131d8b924251a8af988416ffc069"}


def replay():
    result = {"scope": "offline saved-result character counts; not end-to-end tokens or latency"}
    full = build_environment(expose_idioms=False)
    compact = build_environment(expose_idioms=False, compact=True)
    result["environment"] = {"before_chars": len(full), "after_chars": len(compact), "listen_present": "sense:listen" in compact}
    for episode, key in STORES.items():
        directory = BASE / "data/spill/supervision" / key
        rows = []
        if not directory.is_dir():
            result[str(episode)] = {"error": "historical evidence unavailable"}
            continue
        with TemporaryDirectory() as temp, patch("episode_logger.record_trajectory_event"), patch("model_result_view.evidence_store", return_value=TurnStore(Path(temp))):
            for line in (directory / "events.jsonl").read_text().splitlines():
                event = json.loads(line)
                if event.get("kind") != "tool.finished" or "execute_ibl" not in event.get("name", ""):
                    continue
                ref = event.get("evidence", {})
                raw = (directory / (ref["id"] + ".txt")).read_text()
                try:
                    value = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(value, dict):
                    continue
                out = project_result(value, verbose=True)
                if out.get("result_ref"):
                    from model_result_view import evidence_store
                    recovered = evidence_store().read_evidence(out["result_ref"]["id"], 0, out["result_ref"]["chars"])
                    assert json.loads(recovered["text"]) == value
                rows.append({"seq": event["seq"], "before_chars": len(raw), "after_chars": len(json.dumps(out, ensure_ascii=False)),
                             "raw_equal": True})
        result[str(episode)] = {"count": len(rows), "before_chars": sum(r["before_chars"] for r in rows),
                                "after_chars": sum(r["after_chars"] for r in rows), "rows": rows}
    return result


if __name__ == "__main__":
    result = replay()
    path = BASE / "outputs/research/efficiency-repair-20260911.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: {a: b for a, b in v.items() if a != "rows"} if isinstance(v, dict) else v for k, v in result.items()}, ensure_ascii=False))
    print(path)
