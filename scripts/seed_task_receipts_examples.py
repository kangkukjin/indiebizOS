#!/usr/bin/env python3
"""[self:task] 용례 시딩 (2026-10-05 ③) — 해마 합성 용례 + 훈련 코퍼스. 단일 경로 add_examples_batch."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
from ibl_usage_db import IBLUsageDB  # noqa: E402

EXAMPLES = [
    {"intent": "백그라운드로 돌린 스크립트가 끝날 때까지 기다렸다가 결과를 받아줘",
     "ibl_code": '#!ibl edition=2\n$job = [self:script]{op: "run", id: "나레이션생성", args: {lecture_id: "x"}, background: true}\n$r = [self:task]{op: "wait", ref: $job.task_ref, timeout: 120}\nreturn $r.result'},
    {"intent": "위임한 작업의 지금 상태만 확인해줘",
     "ibl_code": '[self:task]{op: "status", ref: $receipt.task_ref}'},
    {"intent": "조사 위임과 신문 발행을 둘 다 기다려서 결과를 합쳐줘",
     "ibl_code": '#!ibl edition=2\n$a = [others:delegate]{agent_id: "조사", message: "오늘 AI 뉴스 요약"}\n$b = [engines:newspaper]{}\n$ra = [self:task]{op: "wait", ref: $a.task_ref, timeout: 240}\n$rb = [self:task]{op: "wait", ref: $b.task_ref, timeout: 120}\nreturn {report: $ra.result, paper: $rb.result}'},
    {"intent": "아직 기기가 가져가지 않은 손발 명령을 취소해줘",
     "ibl_code": '[self:task]{op: "cancel", ref: $job.task_ref}'},
    {"intent": "강의 동영상 렌더가 끝났는지 기다렸다가 알려줘",
     "ibl_code": '$v = [self:deck]{op: "video", lecture_id: "x"}; [self:task]{op: "wait", ref: $v.task_ref, timeout: 240}'},
    {"intent": "시트 저장을 접수한 뒤 편집기에서 완료됐는지 기다려줘",
     "ibl_code": '$sv = [self:workspace]{op: "save", resource: $res, message: "정리"}; [self:task]{op: "wait", ref: $sv.task_ref, timeout: 30}'},
]


def main():
    import sqlite3
    from ibl_usage_db import DB_PATH
    with sqlite3.connect(DB_PATH) as conn:   # 멱등: 이미 있는 (intent, code) 는 다시 넣지 않는다(재실행이 중복을 만들지 않게)
        present = set(conn.execute("SELECT intent, ibl_code FROM ibl_examples WHERE ibl_code LIKE '%self:task%'").fetchall())
    fresh = [e for e in EXAMPLES if (e["intent"], e["ibl_code"]) not in present]
    count = IBLUsageDB().add_examples_batch([
        dict(example, nodes="self", source="synthetic", tags="task_receipts,self:task")
        for example in fresh
    ]) if fresh else 0
    path = ROOT / "data/training/ibl_distilled.json"
    rows = json.loads(path.read_text())
    known = {(r.get("intent"), r.get("ibl_code")) for r in rows}
    additions = [r for r in EXAMPLES if (r["intent"], r["ibl_code"]) not in known]
    if additions:
        path.write_text(json.dumps(rows + additions, ensure_ascii=False, indent=2) + "\n")
    print(f"self:task examples: DB added {count}; training added {len(additions)}")


if __name__ == "__main__":
    main()
