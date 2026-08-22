"""원샷 낱말(ai-ops) 배터리 — [self:struct] · [table:ai] · [table:brief]

모델 호출은 oneshot_facade.execution_oneshot 를 가짜로 갈아끼워 토큰 0 으로 검증한다
(관문 로직 = 파싱·재시도·정직 실패·행 수 신고·grounded 대조·provenance 가 시험 대상).
정본 설계 = docs/ONESHOT_VOCAB_DESIGN.md §11-1.

실행: python3 backend/test_ai_ops_words.py
"""
import importlib.util
import json
import os
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

_PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "packages", "installed", "tools")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_aiops = _load("_t_aiops", os.path.join(_PKG, "ai-ops", "handler.py"))
import oneshot_facade as _fac  # noqa: E402


class _Ctx:
    def __init__(self, tool_name):
        self.tool_name = tool_name
        self.project_path = "/tmp"

    def output_dir(self, name=None):
        return "/tmp"


_FAKE = {"queue": [], "calls": 0}


def _fake_oneshot(prompt, system_prompt=None, images=None, role="execution"):
    _FAKE["calls"] += 1
    if _FAKE["queue"]:
        return _FAKE["queue"].pop(0)
    return None


def _arm(*responses):
    _FAKE["queue"] = list(responses)
    _FAKE["calls"] = 0


_fac.execution_oneshot = _fake_oneshot

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  ✓ " if cond else "  ✗ ") + name + (f" — {detail}" if detail and not cond else ""))


def run(tool, inp):
    out = _aiops.execute(inp, _Ctx(tool))
    return json.loads(out)


print("[table:ai — ai_transform]")
items3 = [{"title": "a", "price": 1}, {"title": "b", "price": 2}, {"title": "c", "price": 3}]

_arm(json.dumps([{"title": "a", "price": 1, "note": "싸다"},
                 {"title": "b", "price": 2, "note": "중간"},
                 {"title": "c", "price": 3, "note": "비싸다"}], ensure_ascii=False))
r = run("ai_transform", {"instruction": "note 추가", "_prev_result": json.dumps({"items": items3})})
check("T1 정상 변환 — items·행수 보존·_ai", r.get("success") and r["rows_in"] == 3 and r["rows_out"] == 3
      and all(row.get("_ai") for row in r["items"]))

_arm("이건 JSON 이 아님", json.dumps([{"title": "a"}]))
r = run("ai_transform", {"instruction": "x", "items": items3})
check("T2 파싱 실패 → 재시도 1회로 회복", r.get("success") and r["rows_out"] == 1 and _FAKE["calls"] == 2)

_arm("쓰레기1", "쓰레기2")
r = run("ai_transform", {"instruction": "x", "items": items3})
check("T3 재시도도 실패 → 정직 실패", not r.get("success") and "JSON" in r.get("error", ""))

_arm(json.dumps([{"title": "a"}]))
r = run("ai_transform", {"instruction": "하나만 남겨", "items": items3})
check("T4 행 감소 → rows_dropped 신고", r.get("success") and r.get("rows_dropped") == 2)

_arm()
r = run("ai_transform", {"instruction": "x", "_prev_result": json.dumps({"items": []})})
check("T5 0행 → AI 호출 생략(비용 0)", r.get("success") and r["rows_out"] == 0 and _FAKE["calls"] == 0)

r = run("ai_transform", {"instruction": "x"})
check("T6 통화 없음 → 정직 입구 오류", not r.get("success") and "파이프" in r.get("error", ""))

big = [{"t": "x" * 100} for _ in range(700)]
r = run("ai_transform", {"instruction": "x", "items": big})
check("T7 입력 상한 초과 → take/filter 안내 거절", not r.get("success") and "take" in r.get("error", ""))

_arm(json.dumps([{"title": "a", "price": 1, "junk": 9}]))
r = run("ai_transform", {"instruction": "x", "items": items3[:1], "fields": ["title", "price"]})
check("T8 fields 강제 — 투영", r.get("success") and set(r["items"][0]) == {"title", "price", "_ai"})

r = run("ai_transform", {"_prev_result": json.dumps({"items": items3})})
check("T9 instruction 누락 → 정직 거절", not r.get("success"))

print("[table:brief — ai_brief]")
_arm("첫째로 a 가 가장 싸고, 둘째로 c 가 가장 비쌉니다.\n전체 평균은 2 입니다.")
r = run("ai_brief", {"instruction": "요약", "_prev_result": json.dumps({"items": items3})})
check("B1 정상 — message=산문 정본", r.get("success") and "\n" in r["message"] and r["rows_in"] == 3)
check("B2 write 싱크 추출 계약 — items 밖 dict/list 페이로드 없음",
      not any(isinstance(v, (dict, list)) and v for k, v in r.items() if k != "items"))

# ★F20-3 판정 (2026-08-22): 0행은 고장이 아니라 정당한 빈손 — 옛 B3("정직 거절")을
# 뒤집었다. 감시자 문형 `[table:since] >> [table:brief]` 이 첫 실행마다 error 로 끝나던
# 원인이고, brief 는 F17 빈손 계약(each·flatten·groupby·filter·take·table:ai)의 유일한 예외였다.
_calls_before = _FAKE["calls"]
r = run("ai_brief", {"instruction": "요약", "_prev_result": json.dumps({"items": []})})
check("B3 0행 → 빈손 성공(고장 아님)", r.get("success") is True and r.get("rows_in") == 0)
check("B3-a 0행 → AI 호출 생략(비용 0)", _FAKE["calls"] == _calls_before)
check("B3-b 0행 → 조용한 성공 금지(note 로 말한다)", "0행" in (r.get("note") or ""))
check("B3-c 0행 → message(산문 정본) 없음 — 행이 없으면 산문도 없다", "message" not in r)
check("B3-d 0행 → items:[] 라 `??` 폴백이 빈손을 알아본다", r.get("items") == [])

r = run("ai_brief", {"instruction": "요약", "_prev_result": "그냥 긴 평문 텍스트..."})
check("B4 평문 입력 → self:ask 안내", not r.get("success") and "self:ask" in r.get("error", ""))

# ★구분 유지(F20-3 의 절반) — 0행을 통과시키되 **통화 없음**은 여전히 에러여야 한다.
r = run("ai_brief", {"instruction": "요약", "_prev_result": json.dumps({"ok": True})})
check("B4-a 통화 없음 → 여전히 정직 거절(0행과 다른 갈래)",
      not r.get("success") and "통화" in r.get("error", ""))

_arm(None, None)
r = run("ai_brief", {"instruction": "요약", "items": items3})
check("B5 빈 응답 재시도 후 정직 실패", not r.get("success") and _FAKE["calls"] == 2)

print("[self:struct — ai_struct]")
SRC = "8월 1일 카페라떼 5,500원 결제. 8월 2일 김밥 3,000원 결제."
_arm(json.dumps([
    {"date": "2026-08-01", "item": "카페라떼", "amount": 5500, "_quote": "카페라떼 5,500원"},
    {"date": "2026-08-02", "item": "김밥", "amount": 3000, "_quote": "존재하지 않는 발췌"},
], ensure_ascii=False))
r = run("ai_struct", {"schema": "finance", "text": SRC})
check("S1 grounded 기본 on(finance) — 대조 탈락 신고",
      r.get("success") and r.get("grounded") and r["count"] == 1 and r.get("dropped_ungrounded") == 1
      and r["items"][0]["item"] == "카페라떼" and r["items"][0].get("_ai"))

_arm(json.dumps([{"date": "2026-08-01", "item": "카페라떼", "amount": 5500, "_quote": "환각"},
                 {"date": "2026-08-02", "item": "김밥", "amount": 3000, "_quote": "환각2"}], ensure_ascii=False))
r = run("ai_struct", {"schema": "finance", "text": SRC})
check("S2 근거 대조 전멸 → 정직 실패", not r.get("success") and "전멸" in r.get("error", ""))

_arm(json.dumps([{"행사명": "야시장", "날짜": "2026-08-20"}], ensure_ascii=False))
r = run("ai_struct", {"schema": "행사명, 날짜", "text": "8월 20일 야시장이 열린다"})
check("S3 일반 스키마 — grounded 기본 off", r.get("success") and not r.get("grounded") and r["count"] == 1)

_arm(json.dumps({"items": [{"a": 1}]}))
r = run("ai_struct", {"schema": "a", "_prev_result": "파이프로 흘러온 본문 텍스트"})
check("S4 파이프 본문 수용 + items 봉투 승격", r.get("success") and r["count"] == 1
      and r.get("source") == "파이프 본문")

r = run("ai_struct", {"schema": "a", "_prev_result": json.dumps({"items": items3})})
check("S5 items 통화 입력 → table:ai 안내 거절", not r.get("success") and "table:ai" in r.get("error", ""))

r = run("ai_struct", {"schema": "a"})
check("S6 입력 없음 → 정직 거절", not r.get("success"))

r = run("ai_struct", {"text": "본문"})
check("S7 schema 누락 → 정직 거절", not r.get("success") and "schema" in r.get("error", ""))

r = run("ai_struct", {"schema": "a", "file": "/no/such/file.pdf"})
check("S8 없는 파일 → extract_source 정직 오류", not r.get("success") and "파일" in r.get("error", ""))

print("[게이트·플래그]")
sys.path.insert(0, os.path.join(_PKG, "community-portal"))
_pc = _load("_t_portal_core", os.path.join(_PKG, "community-portal", "portal_core.py"))
ok, why = _pc.action_allowed('[table:ai]{instruction: "x"}', ['[table:ai]{instruction: "{q}"}'])
check("G1 포털 게이트 — AI 낱말 템플릿이 있어도 거부", not ok and "AI" in why)
ok2, _ = _pc.action_allowed('[table:filter]{where: "a"}', ['[table:filter]{where: "{q}"}'])
check("G2 포털 게이트 — 결정론 낱말 회귀 무손상", ok2)

import yaml as _yaml
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_nodes = _yaml.safe_load(open(os.path.join(_ROOT, 'data', 'ibl_nodes.yaml')))
_acts = _nodes["nodes"]
check("F1 레지스트리 — 세 낱말 ai_call 플래그",
      _acts["self"]["actions"]["struct"].get("ai_call") is True
      and _acts["table"]["actions"]["ai"].get("ai_call") is True
      and _acts["table"]["actions"]["brief"].get("ai_call") is True)

print(f"\n결과: PASS {len(PASS)} / FAIL {len(FAIL)}")
if FAIL:
    print("실패:", FAIL)
    sys.exit(1)
