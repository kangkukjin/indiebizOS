#!/usr/bin/env python3
"""seed_imagination_round_54.py — 54회차(시간 왕복) 시드 8건 (2026-09-02, 사용자 지시).

무엇을 가르치는가 (보고서 outputs/imagination_training/2026-09-02_54회차.md "시드 후보" + 수리로 살아난 발화 문장):
  ① **시간 어휘의 되읽기 통화** — `trigger list/history`·`manage_events list` 를 filter/select 에 물린다
     (시간 문형은 행동 지표 최저 2건 — 등록·되읽기가 파이프에 산 적이 없던 밭).
  ② **평일 cron** `0 9 * * 1-5` (F54-1 수리 전엔 정직 거절이던 가장 흔한 시간 의도).
  ③ **효과 봉투 되먹임** — `$t.trigger.id` 로 만들자마자 시각 변경.
  ④ **발화가 프로젝트 문맥을 갖는 do** — 트리거 do 안의 `[self:sheet]{append}`·`[self:write]`(B54-1 수리 전엔
     발화에서 전부 거절), `[self:manage_events]{do: IBL}` 실행 이벤트(B54-5), `[self:schedule]{minutes}` 지연 저장.

★시드는 교재다 — 전건 `/ibl/validate` 통과 + 스크래치 이름으로 라이브 실행 검증 8/8(2026-09-02 12:2x,
  등록물은 검증 직후 삭제). 경로·이름은 일반 이름으로 바꿔 넣는다.

실행: .venv/bin/python scripts/seed_imagination_round_54.py   (★_load_model_sync 뒤 add, intent dedupe)
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

Q = "[sense:stock]{op: 'quote', ticker: '005930'}"
SEL = "[table:select]{columns: ['symbol', 'current_price']}"

NEW = [
    ("켜져 있는 트리거만 이름·마지막 실행·실행 횟수 표로 보여줘",
     '[self:trigger]{op: "list"} >> [table:filter]{where: "enabled == true"} >> [table:select]{columns: ["name", "last_run", "run_count"]}',
     "self,table", "system", "시간,되읽기,trigger_list,filter,select"),
    ("캘린더에서 자동 실행 이벤트만 시각·반복·활성 여부 표로",
     '[self:manage_events]{op: "list"} >> [table:filter]{where: {field: "action", op: "eq", value: "run_pipeline"}} >> [table:select]{columns: ["title", "time", "repeat", "enabled"]}',
     "self,table", "system", "시간,되읽기,manage_events,구조형where,select"),
    ("아침 시세 트리거 실행 이력에서 실패한 것만 시각과 오류를 보여줘",
     '[self:trigger]{op: "history", id: "아침 시세", limit: 20} >> [table:filter]{where: "success == false"} >> [table:select]{columns: ["time", "error"]}',
     "self,table", "system", "시간,되읽기,trigger_history,filter,select"),
    ("매일 9시 삼성전자 시세 트리거를 만들고 바로 10시로 바꿔줘",
     '$t = [self:trigger]{op: "create", name: "아침 시세", cron: "0 9 * * *", do: "' + Q + '"}\n'
     '[self:trigger]{op: "update", id: "$t.trigger.id", cron: "0 10 * * *"}',
     "self,sense", "invest", "시간,trigger_create,id되먹임,update,cron"),
    ("평일 아침 9시마다 삼성전자 시세를 나에게 알려줘",
     '[self:trigger]{op: "create", name: "평일 시세 알림", cron: "0 9 * * 1-5", do: "' + Q + ' >> [self:notify_user]{message: \'삼성전자 시세\'}"}',
     "self,sense", "invest", "시간,trigger_create,cron평일,발신"),
    ("평일 장 마감 4시에 삼성전자 시세 한 줄을 시세 장부 xlsx 에 쌓아줘",
     '[self:trigger]{op: "create", name: "시세 장부", cron: "0 16 * * 1-5", do: "' + Q + ' >> ' + SEL + ' >> [self:sheet]{op: \'append\', path: \'시세장부.xlsx\'}"}',
     "self,sense,table", "invest", "시간,축적,trigger_create,cron평일,sheet_append"),
    ("10분 뒤에 삼성전자 시세를 JSON 파일로 저장해줘",
     '[self:schedule]{minutes: 10, title: "시세 저장", do: "' + Q + ' >> ' + SEL + ' >> [self:write]{path: \'시세.json\', format: \'json\'}"}',
     "self,sense,table", "invest", "시간,축적,schedule,지연,format_json"),
    ("내일 아침 9시에 삼성전자 시세를 파일로 남기는 실행 이벤트를 캘린더에 넣어줘",
     '[self:manage_events]{op: "create", title: "내일 시세 저장", date: "2026-09-03", time: "09:00", do: "' + Q + ' >> ' + SEL + ' >> [self:write]{path: \'내일시세.json\', format: \'json\'}"}',
     "self,sense,table", "invest", "시간,축적,manage_events,do실행이벤트,format_json"),
]

db = IBLUsageDB()
assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단(★_index_batch 는 실패를 삼킨다)"
import sqlite3
conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "..", "data", "ibl_usage.db"))
existing = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
conn.close()
batch = [{"intent": i, "ibl_code": c, "nodes": n, "category": cat, "difficulty": 2,
          "source": "manual_seed", "tags": t} for i, c, n, cat, t in NEW if i not in existing]
print(f"시드 추가: {db.add_examples_batch(batch)}건 (중복 스킵 {len(NEW) - len(batch)}건)")
dist_path = os.path.join(os.path.dirname(__file__), "..", "data", "training", "ibl_distilled.json")
with open(dist_path, encoding="utf-8") as f:
    dist = json.load(f)
have = {d.get("intent") for d in dist}
added = 0
for i, c, n, cat, t in NEW:
    if i not in have:
        dist.append({"intent": i, "ibl_code": c, "nodes": n, "category": cat, "difficulty": 2, "source": "manual_seed"})
        added += 1
with open(dist_path, "w", encoding="utf-8") as f:
    json.dump(dist, f, ensure_ascii=False, indent=2)
print(f"ibl_distilled: +{added}건 → {len(dist)}건")
