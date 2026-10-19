"""보존된 실행·파일·대화 영수증의 결정론적 대조. 모델 호출·쓰기 재실행 없음."""
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ROUND = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-19_80회차"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(label):
    data = json.loads((OUT / "runs" / f"{label}.json").read_text())
    assert data["response"]["state"] == "succeeded", label
    return data


def main():
    checks = {}
    for path in (ROUND / "inputs").iterdir():
        assert digest(path) == digest(OUT / "inputs" / path.name)
        expected = path.read_bytes()
        if path.name == "north.txt":
            expected = expected.replace("R03: 정상반납 5개".encode(), "R03: 정상반납 8개".encode())
        assert (OUT / "inputs_changed" / path.name).read_bytes() == expected
    checks["all_input_versions_unchanged"] = True
    for name, total in [("good_total.md", 102), ("all_total.md", 114), ("changed_total.md", 117)]:
        assert (OUT / "ai" / name).read_text() == f"합계 {total}\n"
    checks["ai_totals"] = [102, 114, 117]
    for name, total in [("base", 102), ("variant", 114), ("new_variant", 117)]:
        record = json.loads((OUT / "runs" / f"post_{name}.json").read_text())
        assert record["response"]["value"]["total"] == total
        assert (OUT / "trainer_post" / name / "good_total.md").read_text() == f"합계 {total}\n"
    checks["trainer_totals"] = [102, 114, 117]
    for before, after, filename in [("A1", "A2", "good_total.md"), ("A3", "A4", "all_total.md"),
                                    ("P1", "P2", "good_total.md"), ("P3", "P4", "all_total.md"),
                                    ("N1", "N2", "changed_total.md")]:
        first, second = run(before), run(after)
        path = "ai/" + filename
        assert first["files_after"][path] == second["files_after"][path]
        assert first["files_after"][path]["sha256"] in second["response"]["result"]
        checks[f"{before}_{after}_sha_mtime"] = True
    # 조건 변경은 기존 산출물을 다시 저장하지 않는다.
    assert run("P2")["files_after"]["ai/good_total.md"] == run("P3")["files_after"]["ai/good_total.md"]
    for filename in ["good_total.md", "all_total.md"]:
        assert run("P4")["files_after"]["ai/" + filename] == run("N1")["files_after"]["ai/" + filename]
    checks["earlier_outputs_unchanged_by_variants"] = True
    with sqlite3.connect(f"file:{ROOT / 'data/system_ai_memory.db'}?mode=ro", uri=True) as conn:
        for first, second in [("P1", "P2"), ("P3", "P4"), ("N1", "N2")]:
            tids = [run(n)["submission"]["task_id"] for n in (first, second)]
            turns = [conn.execute("SELECT session_id,turn_id FROM conversation_task_links WHERE task_id=?",
                                  (tid,)).fetchone() for tid in tids]
            assert all(turns) and turns[0][0] == turns[1][0]
            events = []
            for session_id, turn_id in turns:
                assert conn.execute("SELECT state FROM conversation_turns WHERE id=?", (turn_id,)).fetchone()[0] == "completed"
                events.append([(row[0], json.loads(row[1])) for row in conn.execute(
                    "SELECT id,payload FROM conversation_events WHERE session_id=? AND turn_id=? ORDER BY id",
                    (session_id, turn_id))])
            receipts = [eid for eid, payload in events[0] if payload.get("type") == "reflex.result"]
            acks = [payload["through"] for _, payload in events[1] if payload.get("type") == "reflex.ack"]
            assert len(receipts) == 1 and acks == receipts
            checks[f"{first}_{second}_receipt"] = receipts[0]
    (ROUND / "evidence" / "verification.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    print(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
