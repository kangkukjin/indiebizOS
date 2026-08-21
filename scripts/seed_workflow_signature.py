#!/usr/bin/env python3
"""seed_workflow_signature.py — 워크플로우 시그니처·params_default·${이름} 괄호 표기 시드 (2026-08-22).

커밋 18aaaf2 로 들어온 세 가지를 해마에 앉힌다.
  ① 시그니처 — 몸통의 미할당 `$이름` = 인자. save 가 params_required 로 보고하고,
     저장본 run 은 인자 누락을 정직 거절한다(즉석 run 은 경고).
  ② params_default — 늘 같은 기본값은 저장본에 둔다(호출자가 이김).
  ③ `${이름}` 괄호 표기 — 한글 조사·단위가 이름에 먹히는 자리의 경계
     (`"$n건"`=변수 n건 / `"${n}건"`=변수 n + 글자 건).

★모델이 아직 괄호형을 짓지 않아, "인자를 받는 워크플로우" 용례를 **한글 뒤에 붙는 자리**
위주로 골랐다 — 그 자리가 정확히 괄호가 필요한 자리다.

실행: .venv/bin/python3 scripts/seed_workflow_signature.py  (★_load_model_sync 뒤 add, intent dedupe)
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    # ── ① 시그니처: 인자를 받는 워크플로우를 만든다 ──────────────────────────
    ("도시 이름만 바꿔 쓰는 맛집 검색 워크플로우로 저장해줘",
     '[self:workflow]{op: "save", name: "동네 맛집", do: "[sense:search]{source: \'naver\', query: \'$city 맛집\'} >> [table:take]{n: 10}"}',
     "self,sense,table", "workflow", "workflow,save,시그니처,인자"),
    ("저장한 동네 맛집 워크플로우를 청주로 돌려줘",
     '[self:workflow]{op: "run", name: "동네 맛집", params: {city: "청주"}}',
     "self", "workflow", "workflow,run,params,인자"),
    ("그 워크플로우가 뭘 받아야 하는지 알려줘",
     '[self:workflow]{op: "get", name: "동네 맛집"}',
     "self", "workflow", "workflow,get,시그니처,params_required"),
    ("저장된 워크플로우들 이름이랑 필요한 인자 보여줘",
     '[self:workflow]{op: "list"}',
     "self", "workflow", "workflow,list,시그니처"),

    # ── ② 괄호 표기: 한글이 뒤에 붙는 자리 ─────────────────────────────────
    ("건수만 바꿔 쓰는 뉴스 요약 워크플로우 만들어줘",
     '[self:workflow]{op: "save", name: "뉴스 요약", do: "[sense:search]{source: \'gnews\', query: \'${topic}\'} >> [table:take]{n: \'${count}\'} >> [table:brief]{instruction: \'상위 ${count}건 요지\'} >> [self:notify_user]{}"}',
     "self,sense,table", "workflow", "workflow,save,괄호표기,시그니처"),
    ("뉴스 요약 워크플로우를 AI 주제로 5건만 돌려줘",
     '[self:workflow]{op: "run", name: "뉴스 요약", params: {topic: "AI", count: 5}}',
     "self", "workflow", "workflow,run,params,괄호표기"),
    ("월 이름을 받아서 그 달 지출 합계를 알려주는 워크플로우로 저장해줘",
     '[self:workflow]{op: "save", name: "월 지출 합계", do: "[self:finance]{op: \'summary\', month: \'${month}\'} >> [table:reduce]{init: 0, step: \'acc + amount\'} >> [self:notify_user]{message: \'${month}월 지출\'}"}',
     "self,table", "finance", "workflow,save,괄호표기,시그니처"),
    ("전세 워크플로우 만들어줘 — 동네랑 최대 보증금을 인자로",
     '[self:workflow]{op: "save", name: "전세 훑기", do: "[sense:realty]{source: \'naver\', region: \'${region}\', deal: \'lease\'} >> [table:filter]{where: {보증금: {lte: \'${budget}\'}}} >> [table:sort]{by: \'보증금\'} >> [table:spreadsheet]{path: \'${region}_전세.xlsx\'}"}',
     "self,sense,table", "realty", "workflow,save,괄호표기,시그니처"),

    # ── ③ params_default: 늘 같은 값은 저장본에 ────────────────────────────
    ("뉴스 요약 워크플로우 기본값을 AI 5건으로 정해줘",
     '[self:workflow]{op: "save", name: "뉴스 요약", params_default: {topic: "AI", count: 5}, do: "[sense:search]{source: \'gnews\', query: \'${topic}\'} >> [table:take]{n: \'${count}\'} >> [table:brief]{instruction: \'상위 ${count}건 요지\'} >> [self:notify_user]{}"}',
     "self,sense,table", "workflow", "workflow,save,params_default,기본값"),
    ("뉴스 요약 그냥 기본값으로 돌려줘",
     '[self:workflow]{op: "run", name: "뉴스 요약"}',
     "self", "workflow", "workflow,run,params_default"),

    # ── 경로 참조·즉석 실행·파이프 ─────────────────────────────────────────
    ("보고서 만들어서 그 파일 열어줘",
     '$r = [sense:search]{source: "gnews", query: "청주 부동산"} >> [table:brief]{instruction: "5문장 요지"} >> [self:write]{path: "청주_부동산.md"}\n[limbs:os_open]{path: "${r.path}"}',
     "sense,table,self,limbs", "web", "변수,괄호표기,경로,열기"),
    ("저장 안 하고 이번만 도시 두 곳 날씨 비교해줘",
     '[self:workflow]{op: "run", do: "[sense:weather]{city: \'${a}\'} & [sense:weather]{city: \'${b}\'} >> [table:brief]{instruction: \'두 도시 날씨 비교 3문장\'}", params: {a: "청주", b: "서울"}}',
     "self,sense,table", "workflow", "workflow,즉석실행,params,괄호표기"),
    ("동네 맛집 워크플로우 결과에서 상위 3개만 텔레그램으로",
     '[self:workflow]{op: "run", name: "동네 맛집", params: {city: "청주"}} >> [table:take]{n: 3} >> [others:channel_send]{channel_type: "telegram"}',
     "self,table,others", "workflow", "workflow,run,파이프,통화"),

    # ── 재귀 대신 반복 (순환 거절의 대안) ───────────────────────────────────
    ("도시 목록을 한 번에 돌려서 각각 맛집 찾아줘",
     '[table:each]{items: [{"city": "청주"}, {"city": "대전"}, {"city": "세종"}], do: "[self:workflow]{op: \'run\', name: \'동네 맛집\', params: {city: \'${it.city}\'}}"}',
     "table,self", "workflow", "each,workflow,반복,괄호표기"),
    ("워크플로우를 세 번 반복 실행해서 결과 모아줘",
     '[repeat: 3, collect: true]{[self:workflow]{op: "run", name: "뉴스 요약"}} >> [table:dedup]{by: "title"}',
     "self,table", "workflow", "repeat,workflow,반복,collect"),

    # ── 짧은 표현 (2차 배치) ────────────────────────────────────────────────
    # ★1차 시딩 후 회상 실측: "워크플로우 실행할 때 값 넘기려면" 같은 짧은 질의가
    # 옛 무인자 용례(`{op:"run", name:"일일리포트"}`)를 물었다 — 긴 intent 는 짧은
    # 질의와 겨루지 못한다. 사람이 실제로 치는 길이로 같은 패턴을 다시 앉힌다.
    ("워크플로우 청주로 돌려",
     '[self:workflow]{op: "run", name: "동네 맛집", params: {city: "청주"}}',
     "self", "workflow", "workflow,run,params,짧은표현"),
    ("값 바꿔서 워크플로우 실행",
     '[self:workflow]{op: "run", name: "뉴스 요약", params: {topic: "반도체", count: 3}}',
     "self", "workflow", "workflow,run,params,짧은표현"),
    ("인자 넘겨서 돌려줘",
     '[self:workflow]{op: "run", name: "월 지출 합계", params: {month: "2026-08"}}',
     "self", "workflow", "workflow,run,params,짧은표현"),
    ("이 워크플로우 뭐 필요해",
     '[self:workflow]{op: "get", name: "뉴스 요약"}',
     "self", "workflow", "workflow,get,시그니처,짧은표현"),
    ("워크플로우 기본값 정해줘",
     '[self:workflow]{op: "save", name: "뉴스 요약", params_default: {topic: "AI", count: 5}, do: "[sense:search]{source: \'gnews\', query: \'${topic}\'} >> [table:take]{n: \'${count}\'} >> [self:notify_user]{}"}',
     "self,sense,table", "workflow", "workflow,params_default,짧은표현"),
    ("다른 지역으로 다시 돌려",
     '[self:workflow]{op: "run", name: "전세 훑기", params: {region: "봉명동", budget: 20000}}',
     "self", "workflow", "workflow,run,params,짧은표현"),
]

db = IBLUsageDB()
assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단"
import sqlite3
db_path = os.path.join(os.path.dirname(__file__), "..", "data", "ibl_usage.db")
conn = sqlite3.connect(db_path)
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
