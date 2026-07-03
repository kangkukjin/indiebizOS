#!/usr/bin/env python3
"""IBL 건강 점검 — 매뉴얼 §1 절차를 그대로 실행(외부 도구 의존 없이 /ibl/execute + 레지스트리만)."""
import json, urllib.request, subprocess, sys, os

BASE = "http://localhost:8765"
PID = "하드웨어"

def execute(code):
    body = json.dumps({"code": code, "project_id": PID}).encode()
    req = urllib.request.Request(BASE + "/ibl/execute", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            out = json.loads(r.read().decode())
    except Exception as e:
        return {"_transport_error": str(e)}
    d = out.get("result", out)
    if isinstance(d, str):
        try: d = json.loads(d)
        except Exception: return {"_string": d}
    return d

def final_of(d):
    """파이프 결과면 final_result를 dict로."""
    if isinstance(d, dict) and "final_result" in d:
        fr = d["final_result"]
        if isinstance(fr, str):
            try: return json.loads(fr)
            except Exception: return {"_string": fr}
        return fr
    return d

# 기기 미가용(폰/맥 오프라인)·파라미터 부족 = 액션 정상, 테스트 한계 → liveness 면제(SKIP).
# (backend world_pulse_health._evaluate_result 의 분류와 같은 취지 — 거짓 YELLOW 방지)
_BENIGN_ERR = [
    "필요합니다", "required", "missing", "파라미터", "입력해", "확인해", "확인하세요",
    "를 입력", "을 입력", "가 필요", "이 필요",
    "폰 네이티브", "폰에서", "phone_only", "맥에 연결", "INDIEBIZ_PHONE_URL",
    "INDIEBIZ_MAC", "Chaquopy", "offline", "연결할 수 없",
]

def classify_currency(d, declared):
    """returns 선언 대비 단언. declared=items면 통화 유효성 검사(단일 통화 이행 완료 — 옛
    records/table/currency/document 선언은 전부 items로 흡수됨).
    scalar/effect/transform은 통화 면제 — 단 liveness(에러 없이 살았나)는 본다(핸들러 크래시·
    param 키 불일치 검출). 통화 계약이 없으므로 RED 는 안 만든다(에러=YELLOW, 정상/한계=SKIP).
    아래 tbl/blk 읽기는 straggler(stock table·context7/report blocks 등 items 미선언 부가방출) 방어용."""
    if declared != "items":
        # 통화 면제 — liveness만 본다.
        if not isinstance(d, dict):
            return "SKIP", f"{declared} (값 반환)"          # 스칼라 raw 값 = 정상
        if d.get("_transport_error"):
            return "YELLOW", "transport:" + d["_transport_error"][:40]
        if d.get("_string") is not None:
            return "SKIP", f"{declared} (텍스트 반환)"        # 스칼라 문자열 = 정상
        if "error" in d:
            err = str(d.get("error") or "")
            if any(k in err for k in _BENIGN_ERR):
                return "SKIP", f"{declared} (테스트 한계: {err[:35]})"
            return "YELLOW", f"{declared} 에러: {err[:45]}"   # 핸들러 실제 실패 — 단 통화 RED 아님
        return "SKIP", f"{declared} (alive)"
    if not isinstance(d, dict):
        return "YELLOW", "non-dict"
    if d.get("_transport_error"): return "YELLOW", "transport:" + d["_transport_error"][:40]
    if d.get("_string") is not None: return "RED", f"{declared} 선언인데 문자열 반환(통화 파괴?)"
    tbl = d.get("table"); blk = d.get("blocks")
    # 단일 통화 items 우선 — 비어있지 않은 dict 리스트면 통화 유효(title 불요, 열린 항목).
    # derive_items(렌더러 경계)가 table/blocks도 items로 파생하므로 대부분 여기서 GREEN.
    itm = d.get("items")
    if isinstance(itm, list) and itm and all(isinstance(x, dict) for x in itm):
        return "GREEN", f"items[{len(itm)}]" + ("" if declared == "items" else f" (선언 {declared})")
    # 유효 통화 present → GREEN (선언과 다른 표현이 나와도 통화는 통화)
    if isinstance(tbl, dict) and tbl.get("columns") and tbl.get("rows") is not None:
        return "GREEN", f"table {len(tbl['rows'])}행" + ("" if declared == "table" else f" (선언 {declared})")
    # 문서IR {blocks} — crawl·read(docx/pdf) → table:document. type 키 가진 블록 리스트.
    if isinstance(blk, list) and blk and all(isinstance(x, dict) and "type" in x for x in blk):
        return "GREEN", f"document blocks[{len(blk)}]" + ("" if declared == "document" else f" (선언 {declared})")
    if isinstance(itm, list) and not itm: return "YELLOW", "items 빈(데이터 없음)"
    if "error" in d: return "YELLOW", "error:" + str(d.get("error"))[:45]
    # 통화 선언인데 통화 없음 — 목록형 산출이 있으면 명백한 계약 위반(통화 미부착)
    listed = [k for k, v in d.items() if k != "notes" and isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]
    if listed: return "RED", f"{declared} 선언인데 '{listed[0]}' 목록만(통화 미부착)"
    return "YELLOW", f"{declared} 선언인데 통화 없음(스칼라 응답? op 확인)"

# 레지스트리의 returns 선언 적재 (단언 기준)
import yaml as _yaml
_nodes = _yaml.safe_load(open("data/ibl_nodes.yaml"))
RETURNS = {f"{n}:{a}": (ad.get("returns") or "?")
           for n, nd in _nodes["nodes"].items() for a, ad in (nd.get("actions") or {}).items()}

# ── §1A 정적 정합성 ──
print("="*72); print("§1A 정적 정합성 (build --check)"); print("="*72)
r = subprocess.run([sys.executable, "scripts/build_ibl_nodes.py", "--check"],
                   capture_output=True, text=True, cwd=os.getcwd())
static_ok = "검증 통과" in r.stdout and "불일치" not in r.stdout
for line in r.stdout.splitlines():
    if any(w in line for w in ("통과","불일치","실패","✗","액션")): print("  " + line.strip())
print("  → 정적:", "GREEN ✅" if static_ok else "RED ❌")

# ── §1B 통화 무결성 (fixture 전수 probe) ──
# fixture(액션별 '올바른 파라미터 예 하나')는 data/ibl_fixtures.json 이 단일 진실 소스.
# build_ibl_nodes.py --check 가 items/scalar 액션의 fixture 완전성을 강제하므로(신규 액션이
# 빠질 수 없음), 여기서 그 목록을 그대로 실행하면 행동 건강 커버리지가 구성에 의해 완전하다.
_FIX = json.load(open("data/ibl_fixtures.json", encoding="utf-8"))
PRODUCERS = sorted(_FIX["fixtures"].items())   # [(name, code), ...]
EXEMPT = _FIX.get("exempt", {})
print("\n" + "="*72); print("§1B 통화 무결성 (returns 선언 대비 단언)"); print("="*72)
from collections import defaultdict
buckets = defaultdict(list)
for name, code in PRODUCERS:
    declared = RETURNS.get(name, "?")
    verdict, reason = classify_currency(execute(code), declared)
    buckets[verdict].append((name, reason))
    print(f"  [{verdict:6}] {name:24} returns:{declared:9} {reason}")
# 커버리지 — fixture 완전성(--check 강제)을 그대로 반영. 면제는 사유와 함께 명시.
exec_actions = sorted(k for k, v in RETURNS.items() if v in ("items", "scalar"))
covered = len(PRODUCERS) + len(EXEMPT)
print(f"\n  실행대상(items/scalar) {len(exec_actions)}개 = fixture {len(PRODUCERS)}개 + 면제 {len(EXEMPT)}개"
      f" {'✅ 완전' if covered == len(exec_actions) else '❌ 누락 ' + str(len(exec_actions) - covered)}")
if EXEMPT:
    print("  면제(실행 인자 의존):", ", ".join(f"{k}({v})" for k, v in sorted(EXEMPT.items())))

# ── §1C 골든 파이프 (문법+통화 흐름) ──
PIPES = [
  ("naver>>filter>>take", '[sense:search_naver]{query: "AI"} >> [table:filter]{where: "title != "} >> [table:take]{n: 3}', "items"),
  ("world_bank>>chart",   '[sense:world_bank]{indicator: "인구", country: "한국"} >> [table:chart]{chart_type: "line"}', "chart"),
  ("paper>>take>>document",'[sense:paper]{query: "transformer"} >> [table:take]{n: 5} >> [table:document]{format: "html"}', "doc"),
  ("legal>>dedup>>take",  '[sense:legal]{query: "도로교통법"} >> [table:dedup]{} >> [table:take]{n: 3}', "items"),
  ("kosis>>take",         '[sense:kosis]{query: "인구"} >> [table:take]{n: 5}', "items"),
]
print("\n" + "="*72); print("§1C 골든 파이프 (문법+통화 흐름)"); print("="*72)
pipe_pass = 0
for name, code, kind in PIPES:
    fr = final_of(execute(code))
    if kind == "items":
        ok = isinstance(fr, dict) and isinstance(fr.get("items"), list) and len(fr["items"]) > 0
    elif kind == "chart":
        ok = isinstance(fr, dict) and fr.get("success") is True
    else:  # doc
        ok = isinstance(fr, dict) and (fr.get("success") is True or fr.get("path") or fr.get("file"))
    pipe_pass += ok
    print(f"  [{'PASS' if ok else 'FAIL':4}] {name:24} {('items='+str(len(fr.get('items',[]))) if isinstance(fr,dict) and isinstance(fr.get('items'),list) else list(fr.keys())[:4] if isinstance(fr,dict) else fr)}")

# ── §1D 런타임 건강 ──
print("\n" + "="*72); print("§1D 런타임 건강 (world_pulse.db action_health, 실패율 상위)"); print("="*72)
try:
    import sqlite3
    c = sqlite3.connect("data/world_pulse.db")
    rows = c.execute("""SELECT node||':'||action AS a,
                               SUM(CASE WHEN success IN (1,'1','true','True') THEN 1 ELSE 0 END) AS ok,
                               COUNT(*) AS tot
                        FROM action_health GROUP BY a
                        HAVING tot-ok > 0
                        ORDER BY CAST(tot-ok AS FLOAT)/tot DESC LIMIT 10""").fetchall()
    if not rows: print("  (실패 기록 없음)")
    for a, ok, tot in rows:
        print(f"  {a:28} 실패 {tot-ok}/{tot} ({100*(tot-ok)/tot:.0f}%)")
    c.close()
except Exception as e:
    print("  (조회 실패:", e, ") — 스키마 다를 수 있음")

# ── 종합 ──
print("\n" + "="*72); print("종합 판정"); print("="*72)
print(f"  §1A 정적:        {'✅' if static_ok else '❌'}")
print(f"  §1B 통화:        GREEN {len(buckets['GREEN'])} / YELLOW {len(buckets['YELLOW'])} / RED {len(buckets['RED'])}")
print(f"  §1C 골든파이프:  {pipe_pass}/{len(PIPES)} PASS")
if buckets["RED"]:
    print("\n  ⚠️ RED (통화 결함 — 처리 필요):")
    for n, r in buckets["RED"]: print(f"     - {n}: {r}")
verdict = "건강 ✅" if (static_ok and not buckets["RED"] and pipe_pass == len(PIPES)) else "주의 ⚠️"
print(f"\n  ▶ IBL 구조 건강: {verdict}")

# ── 기계 판독 요약 — world_pulse_health.run_ibl_health_check 가 이 한 줄을 파싱한다.
# 사람용 로그의 문구가 바뀌어도 계약이 깨지지 않도록 구조화 출력을 병행(마커 없으면 파서가 fail 처리).
_summary = {
    "static_ok": bool(static_ok),
    "currency": {
        "green": len(buckets["GREEN"]), "yellow": len(buckets["YELLOW"]), "red": len(buckets["RED"]),
        "reds": [{"name": n, "reason": r} for n, r in buckets["RED"]],
    },
    "golden_pipes": {"passed": int(pipe_pass), "total": len(PIPES)},
}
print("\n@@HEALTH_JSON@@ " + json.dumps(_summary, ensure_ascii=False))
