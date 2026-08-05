#!/usr/bin/env python3
"""IBL 건강 점검 — 매뉴얼 §1 절차를 그대로 실행(외부 도구 의존 없이 /ibl/execute + 레지스트리만)."""
import json, urllib.request, subprocess, sys, os

BASE = "http://localhost:8765"
PID = "하드웨어"

def execute(code, pid=PID):
    # agent_id=__self_check__ — 이 점검의 실행이 action_health 에 source='self_check' 로
    # 기록되게 한다(없으면 'usage' 로 실려 §1D 실사용 통계를 자가 점검 실패로 오염 —
    # channel_read 97% 거짓 시그널의 진범). postprocess(AI 압축)도 함께 스킵돼 점검 AI 0.
    body = json.dumps({"code": code, "project_id": pid,
                       "agent_id": "__self_check__"}).encode()
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


# ── 단일-계기 verify (Phase 2, 앱 저술 튼튼함) ──
# 저술 직후 "이 앱의 액션을 1회 실제로 실행해 view 가 통화를 받는가"를 한 방으로 단언.
# 에피소드 656 에서 GoalEval 이 앱을 렌더하지 않고 편집 원장만으로 ACHIEVED 판정하던
# 약한 검증자 공백을, *선언형(Path A) 계기 범위 안에서* 닫는다.
#   · read-only 게이팅: /ibl/validate 와 같은 ibl_safety 파생 안전분류(safe=True만 실행)
#     → business_document regenerate·auto_response start/stop 같은 부작용 op 는 실행 없이 SKIP.
#   · 앱모드 PID: self:* 경로 해소를 실제 앱 컨텍스트(project_id='앱모드')와 일치.
#   · Path B(app: 블록 없는 커스텀 React)는 N/A — currency 개념 부재, tsc 로만 검증(GREEN 사칭 금지).
#   · 한계: currency GREEN = "액션이 통화를 냈다"까지. override 렌더 컴포넌트가 그걸 실제로
#     그리는지는 이 게이트 범위 밖(Phase 3 소관).
def _load_safety_map():
    """(node, action) → safe(bool). 판정은 backend/ibl_safety 단일 소스(api_ibl 과 같은 함수).

    옛 구현은 self_check_plan.json(LLM 분류 캐시)을 읽었으나 그 생성 경로가 삭제된 뒤
    낡은 목록으로 게이팅해 왔다 → 레지스트리 `returns:` 선언에서 파생으로 교체."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
        from ibl_safety import build_safety_map
        return build_safety_map(_nodes.get("nodes") or {})
    except Exception:
        return {}


def _load_op_safety_map():
    """(node, action, op) → safe(bool) — 감사 부채 ③ (2026-08-05).

    액션 롤업만 쓰면 `[self:music]{op:"library"}` 처럼 **쓰기 액션 안의 읽기 op** 가
    통째로 생략된다(실측: fixture 82개 중 32개가 그렇게 게이트에 걸려 있었다 —
    무인 루프의 행동 커버리지가 그만큼 비어 있었다는 뜻)."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
        from ibl_safety import build_op_safety_map
        return build_op_safety_map(_nodes.get("nodes") or {})
    except Exception:
        return {}


def _first_action(tmpl):
    import re
    m = re.search(r"\[(\w+):(\w+)\]", tmpl or "")
    return (m.group(1), m.group(2)) if m else None


def _first_op(tmpl, fa):
    """템플릿 첫 액션의 op (미지정이면 기본 op, op 축 없으면 None). ibl_ops 단일 소스."""
    if not fa:
        return None
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
        from ibl_parser import parse
        from ibl_ops import resolve_op
        adef = ((_nodes.get("nodes") or {}).get(fa[0], {}).get("actions") or {}).get(fa[1]) or {}
        st = (parse(tmpl) or [{}])[0]
        return resolve_op(adef, st.get("params") or {})
    except Exception:
        return None


def _op_returns_of(fa, op):
    """이 호출의 통화 선언 — op 별 선언이 있으면 그것, 없으면 액션 returns (ibl_ops 규칙)."""
    if op:
        try:
            adef = ((_nodes.get("nodes") or {}).get(fa[0], {}).get("actions") or {}).get(fa[1]) or {}
            r = ((adef.get("ops") or {}).get("returns") or {}).get(op)
            if isinstance(r, str):
                return r
        except Exception:
            pass
    return RETURNS.get(f"{fa[0]}:{fa[1]}", "?")


def _is_safe(fa, op, action_map, op_map):
    """op 를 알면 op 판정, 못 짚으면 보수적인 액션 롤업. True/False/None(미분류)."""
    if op:
        s = op_map.get((fa[0], fa[1], op))
        if s is not None:
            return s
    return action_map.get(fa)


def _resolve_instrument_blocks(inst_id):
    """계기 id → [(label, action_template), ...]. 선언형 app:/standalone 만. 없으면 []."""
    import glob as _glob
    blocks = []
    for n, nd in _nodes["nodes"].items():
        for a, ad in (nd.get("actions") or {}).items():
            app = ad.get("app")
            if not isinstance(app, dict):
                continue
            if (app.get("instrument") or a) != inst_id:
                continue
            modes = [m for m in (app.get("modes") or []) if isinstance(m, dict)] or [app]
            for bi, blk in enumerate(modes):
                if isinstance(blk.get("action"), str):
                    blocks.append((f"{inst_id}:{n}:{a}#{bi}", blk["action"]))
    for fp in sorted(_glob.glob("data/instruments/*.yaml")):
        try:
            m = _yaml.safe_load(open(fp, encoding="utf-8")) or {}
        except Exception:
            continue
        if (m.get("instrument") or os.path.splitext(os.path.basename(fp))[0]) != inst_id:
            continue
        for mi, mode in enumerate(m.get("modes") or []):
            if isinstance(mode, dict) and isinstance(mode.get("action"), str):
                blocks.append((f"{inst_id}:instruments/{os.path.basename(fp)}#{mi}", mode["action"]))
    return blocks


def verify_instrument(inst_id):
    """단일 계기 verify. (worst_verdict, [(label, verdict, reason), ...]) 반환.
    verdict ∈ GREEN/YELLOW/RED/SKIP/N_A. 종료코드: YELLOW/RED 만 실패(1)."""
    blocks = _resolve_instrument_blocks(inst_id)
    if not blocks:
        return "N_A", [(inst_id, "N_A",
                        "선언형 app: 블록 없음 — Path B(커스텀 React)이거나 미존재. "
                        "이 게이트 범위 밖(tsc 로만 검증).")]
    safety = _load_safety_map()
    op_safety = _load_op_safety_map()
    order = {"RED": 4, "YELLOW": 3, "N_A": 2, "SKIP": 1, "GREEN": 0}
    results = []
    for label, tmpl in blocks:
        fa = _first_action(tmpl)
        if fa is None:
            results.append((label, "SKIP", "실행 액션 없음")); continue
        if "$" in tmpl:
            results.append((label, "SKIP", "런타임 입력($var) 필요 — 자동 실행 불가")); continue
        op = _first_op(tmpl, fa)
        safe = _is_safe(fa, op, safety, op_safety)
        if safe is not True:
            tag = "부작용 가능" if safe is False else "안전 미분류"
            _t = f"[{fa[0]}:{fa[1]}]" + (f"{{op:{op}}}" if op else "")
            results.append((label, "SKIP",
                            f"{tag} {_t} — read-only 게이트로 실행 생략")); continue
        declared = _op_returns_of(fa, op)
        d = execute(tmpl, pid="앱모드")
        verdict, reason = classify_currency(d, declared if declared != "?" else "items")
        results.append((label, verdict, f"returns:{declared} {reason}"))
    worst = max((v for _, v, _ in results), key=lambda v: order.get(v, 0))
    return worst, results


if "--instrument" in sys.argv:
    _idx = sys.argv.index("--instrument")
    _inst = sys.argv[_idx + 1] if _idx + 1 < len(sys.argv) else ""
    if not _inst:
        print("사용법: python scripts/ibl_health_check.py --instrument <id>", file=sys.stderr)
        sys.exit(2)
    _worst, _rows = verify_instrument(_inst)
    print("=" * 72)
    print(f"단일-계기 verify: {_inst}")
    print("=" * 72)
    for _label, _v, _r in _rows:
        print(f"  [{_v:6}] {_label:36} {_r}")
    _fail = _worst in ("YELLOW", "RED")
    print(f"\n  ▶ 판정: {_worst}  {'❌ 실패' if _fail else ('⚠️ 검증 밖' if _worst == 'N_A' else '✅ 통과')}")
    sys.exit(1 if _fail else 0)


# ── §1A 정적 정합성 ──
print("="*72); print("§1A 정적 정합성 (build --check)"); print("="*72)
r = subprocess.run([sys.executable, "scripts/build_ibl_nodes.py", "--check"],
                   capture_output=True, text=True, cwd=os.getcwd())
# ★판정=returncode 단일 소스. 옛 문구 스크레이핑("검증 통과" in stdout and "불일치" not in
# stdout)은 --check 의 실패 출력이 전부 stderr 로 가므로 "불일치" 검사가 공허하게 항상 참 —
# 게이트 1(validate 롤업)의 성공 문구 유무만 봤고, 나머지 가드(코퍼스 param·fixture 완전성·
# enum·포크/OS·launcher·교재·뷰·앱-템플릿·파생물 바이트 비교)가 실패해도 GREEN 이 샜다.
# world_pulse_health.run_ibl_health_check 의 검증자 튼튼화(2026-07-03, 스크레이핑→계약)와 동류.
static_ok = (r.returncode == 0)
for line in r.stdout.splitlines():
    if any(w in line for w in ("통과","불일치","실패","✗","액션")): print("  " + line.strip())
if not static_ok:  # 실패 사유는 stderr 에 있다 — RED 인데 이유가 안 보이는 로그 방지
    _err = [l for l in (r.stderr or "").splitlines() if any(w in l for w in ("불일치","실패","✗"))]
    for line in _err[:40]: print("  " + line.strip())
print("  → 정적:", "GREEN ✅" if static_ok else "RED ❌")

# ── §1B 통화 무결성 (fixture 전수 probe) ──
# fixture('올바른 파라미터 예 하나')는 data/ibl_fixtures.json 이 단일 진실 소스.
# build_ibl_nodes.py --check 가 items/scalar 액션의 fixture 완전성을 강제하므로(신규 액션이
# 빠질 수 없음), 여기서 그 목록을 그대로 실행하면 행동 건강 커버리지가 구성에 의해 완전하다.
# ★op 축(2026-08-05 감사 ⑤): 키가 `node:action#op` 인 항목은 **한 액션 안의 다른 읽기 op**다.
# 액션당 fixture 하나로는 op 하나만 증명된다 — `[self:music]` 의 fixture 가 sources 를 돌 때
# library·track·folders·playlists·playlist 는 한 번도 안 돌았다. 읽기 op 전수 커버리지도
# --check 가 강제하므로(fixture 또는 사유 있는 exempt) 여기 실행 목록이 곧 op 축 커버리지다.
# ★read-only 게이트(2026-08-05): 이 절은 일일 무인 루프(world_pulse self-check)에서 돌므로
# side_effect 액션의 fixture 는 실행하지 않는다(--instrument 경로와 같은 ibl_safety 게이트).
# 현행 32개는 전부 읽기 op(list/status/search…)로 실측 확인됐지만 그건 저술 관습일 뿐 코드가
# 보증하지 않는다 — 무인 실행은 관습이 아니라 구조가 막는다(자가점검 계약 "부작용 없는 액션").
# 그 32개의 행동 검사는 수동 전수 실행 --all-fixtures 로(어휘 저술·커밋 전 점검용).
_FIX = json.load(open("data/ibl_fixtures.json", encoding="utf-8"))
PRODUCERS = sorted(_FIX["fixtures"].items())   # [(name, code), ...] — name = node:action[#op]
EXEMPT = _FIX.get("exempt", {})


def _qual_action(name):
    """fixture 키 'node:action[#op]' → (node, action). op 축(감사 ⑤) 도입 후 필요."""
    base = name.split("#", 1)[0]
    return tuple(base.split(":", 1))
print("\n" + "="*72); print("§1B 통화 무결성 (returns 선언 대비 단언)"); print("="*72)
from collections import defaultdict
buckets = defaultdict(list)
_ALL_FIXTURES = "--all-fixtures" in sys.argv
_safety = _load_safety_map()
_op_safety = _load_op_safety_map()
if not _safety and not _ALL_FIXTURES:
    # 안전 지도 적재 실패 = 전 fixture 생략 — 침묵하면 §1B 가 아무것도 안 재고도 '건강'으로 보인다
    buckets["YELLOW"].append(("__safety_map__", "ibl_safety 적재 실패 — read-only 게이트 판정 불가(전 fixture 생략)"))
gated = 0
for name, code in PRODUCERS:
    fa = _qual_action(name)
    # ★op 단위 게이트(2026-08-05 감사 ③): fixture 코드가 고른 op 로 판정한다.
    # 액션 롤업으로 재면 읽기 op fixture 가 쓰기 액션에 갇혀 통째로 생략됐다.
    _op = _first_op(code, fa)
    declared = _op_returns_of(fa, _op)
    if not _ALL_FIXTURES and _is_safe(fa, _op, _safety, _op_safety) is not True:
        gated += 1
        verdict, reason = "SKIP", "부작용 op — read-only 게이트로 실행 생략(수동: --all-fixtures)"
    else:
        verdict, reason = classify_currency(execute(code), declared)
    buckets[verdict].append((name, reason))
    print(f"  [{verdict:6}] {name:24} returns:{declared:9} {reason}")
# 커버리지 — fixture 완전성(--check 강제)을 그대로 반영. 면제는 사유와 함께 명시.
# 액션 축(returns:items|scalar 전수)과 op 축(읽기 op 전수)을 따로 센다 — 둘 다 --check 가
# 강제하므로 여기 숫자는 "구성에 의해 완전"이고, 늘어나는 건 저술량뿐이다(감사 ⑤).
exec_actions = sorted(k for k, v in RETURNS.items() if v in ("items", "scalar"))
act_fx = [k for k in _FIX["fixtures"] if "#" not in k]
act_ex = [k for k in EXEMPT if "#" not in k]
op_fx = [k for k in _FIX["fixtures"] if "#" in k]
op_ex = [k for k in EXEMPT if "#" in k]
covered = len(act_fx) + len(act_ex)
print(f"\n  액션 축: 실행대상(items/scalar) {len(exec_actions)}개 = fixture {len(act_fx)}개 + 면제 {len(act_ex)}개"
      f" {'✅ 완전' if covered == len(exec_actions) else '❌ 누락 ' + str(len(exec_actions) - covered)}")
print(f"  op 축: 읽기 op 추가 커버 {len(op_fx) + len(op_ex)}개 = fixture {len(op_fx)}개 + 면제 {len(op_ex)}개"
      f" (--check 의 읽기-op 완전성 가드가 강제)")
if gated:
    print(f"  read-only 게이트 생략 {gated}개 (부작용 op — 행동 검사는 --all-fixtures 수동 실행)")
if EXEMPT:
    print("  면제(실행 인자·기기 의존):", ", ".join(f"{k}({v})" for k, v in sorted(EXEMPT.items())))

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
        # bool() 필수 — or 체인이 None(실패)이나 경로 문자열(성공)을 그대로 반환해 += 가 터진다
        ok = bool(isinstance(fr, dict) and (fr.get("success") is True or fr.get("path") or fr.get("file")))
    pipe_pass += ok
    print(f"  [{'PASS' if ok else 'FAIL':4}] {name:24} {('items='+str(len(fr.get('items',[]))) if isinstance(fr,dict) and isinstance(fr.get('items'),list) else list(fr.keys())[:4] if isinstance(fr,dict) else fr)}")

# ── §1C-2 연산자 (문법 자체 — 최종 통화가 아니라 *동작*을 본다) ──
# 왜 별도 절인가: §1C 는 final_result 의 모양만 보므로 "폴백을 탔는가/단축했는가" 를 못 본다.
# `??` 가 몇 달간 죽은 채 살아 있던 이유가 정확히 이 사각지대였다(NameError → 아무도 안 봄).
# 각 케이스는 시도 로그(attempts)·분기 수를 직접 단언한다.
def _attempts_of(d):
    """파이프 결과에서 fallback step 의 시도 로그를 꺼낸다(없으면 [])."""
    for r in (d.get("results") or []) if isinstance(d, dict) else []:
        if r.get("type") == "fallback":
            return r.get("attempts") or []
    return []

def _op_fallback_string_err(d):
    """앞이 **문자열** 에러여도 폴백해야 한다 — 실패 판정 단일화(_is_error_result)의 회귀 테스트.
    이전엔 `??` 만 문자열 에러를 성공으로 세어, 1차가 status:ok 로 기록되고 폴백을 안 탔다."""
    a = _attempts_of(d)
    return (len(a) == 2 and a[0].get("status") == "error" and a[1].get("status") == "ok",
            f"attempts={[x.get('status') for x in a]}")

def _op_fallback_shortcut(d):
    """앞이 성공하면 폴백을 타지 않아야 한다(단축 평가)."""
    a = _attempts_of(d)
    return (len(a) == 1 and a[0].get("status") == "ok",
            f"attempts={[x.get('status') for x in a]}")

def _op_parallel_merge(d):
    """병렬 두 분기가 실제로 합류해 단일 통화가 되는지."""
    fr = final_of(d)
    n = len(fr.get("items", [])) if isinstance(fr, dict) and isinstance(fr.get("items"), list) else 0
    return (n > 0, f"merged items={n}")

def _op_seq_continues(d):
    """`;` — 앞 문장이 실패해도 뒤 문장이 실행돼야 한다("되든 안 되든 다음").
    동시에 실패를 숨기지 않아야 한다(success=False + statements_failed)."""
    if not isinstance(d, dict):
        return False, f"파이프 결과 아님: {str(d)[:60]}"
    done, tot = d.get("steps_completed"), d.get("steps_total")
    return (done == tot and tot == 2 and d.get("statements_failed") == 1
            and d.get("success") is False,
            f"steps={done}/{tot} failed={d.get('statements_failed')} success={d.get('success')}")

def _op_seq_boundary_isolates(d):
    """`;` 경계=독립 — 앞 문장이 **성공**해도 그 결과가 뒤 문장으로 넘어가면 안 된다.
    프로브: 성공하는 검색 ; 빈 입력의 take. 누수면 take 가 앞 문장의 items 를 받아
    성공해 버리고(2/2 success=True), 단절돼 있으면 take 가 입력 통화 없음으로 실패한다
    (1/2 success=False — 실패가 정답인 단언). _op_seq_continues 는 실패 경로만 보므로
    이 사각(성공 경로 누수)은 이 케이스만 잡는다(2026-07-19 실측으로 발견된 회귀 가드)."""
    if not isinstance(d, dict):
        return False, f"파이프 결과 아님: {str(d)[:60]}"
    done, tot = d.get("steps_completed"), d.get("steps_total")
    return (d.get("success") is False and done == 1 and tot == 2,
            f"steps={done}/{tot} success={d.get('success')} (뒤 문장이 앞 결과를 못 받아 실패=정답)")

def _op_pipe_still_stops(d):
    """회귀 가드 — `>>` 는 문장 *안*에서 여전히 실패 시 중단해야 한다(`;` 와 뒤섞이면 안 됨)."""
    if not isinstance(d, dict):
        return False, f"파이프 결과 아님: {str(d)[:60]}"
    return (d.get("success") is False and d.get("steps_completed") == 0,
            f"steps={d.get('steps_completed')}/{d.get('steps_total')} success={d.get('success')}")

def _op_json_string_failure(d):
    """handler 도구의 실패는 `format_json` 때문에 **JSON 문자열**로 온다 — 그것도 실패로 봐야 한다.
    이 판정이 없던 동안 handler 실패가 전부 성공으로 샜다(2026-07-18 블로그 파이프에서 실측).
    `[table:document]` 에 입력 통화를 안 주면 `{"success": false, "message": …}` 문자열을 낸다
    (error 키가 아니라 message 라, 옛 판정은 이 실패를 볼 방법이 아예 없었다)."""
    if not isinstance(d, dict):
        return False, f"파이프 결과 아님: {str(d)[:60]}"
    return (d.get("success") is False and d.get("steps_completed") == 0,
            f"steps={d.get('steps_completed')}/{d.get('steps_total')} success={d.get('success')}")

OPERATORS = [
  ("JSON문자열 실패감지", '[table:document]{} >> [table:take]{n: 1}', _op_json_string_failure),
  ("; 실패해도 다음문장", '[self:read]{path: "__없는파일__.md"} ; [sense:search_naver]{query: "AI"}', _op_seq_continues),
  ("; 경계=prev 단절",    '[sense:search_naver]{query: "AI"} ; [table:take]{n: 3}', _op_seq_boundary_isolates),
  (">> 실패시 중단(회귀)", '[self:read]{path: "__없는파일__.md"} >> [table:take]{n: 1}', _op_pipe_still_stops),
  ("?? 문자열에러→폴백", '[self:read]{path: "__없는파일__.md"} ?? [sense:search_naver]{query: "AI"}', _op_fallback_string_err),
  ("?? 성공→단축평가",   '[sense:search_naver]{query: "AI"} ?? [self:read]{path: "__없는파일__.md"}', _op_fallback_shortcut),
  ("& 병렬 합류",        '[sense:search_naver]{query: "AI"} & [sense:search_ddg]{query: "AI"} >> [table:merge]{by: "title"}', _op_parallel_merge),
]
print("\n" + "="*72); print("§1C-2 연산자 (?? · & — 동작 단언)"); print("="*72)
op_pass = 0
for name, code, assertion in OPERATORS:
    try:
        ok, detail = assertion(execute(code))
    except Exception as e:
        ok, detail = False, f"단언 예외: {e}"
    ok = bool(ok)
    op_pass += ok
    print(f"  [{'PASS' if ok else 'FAIL':4}] {name:22} {detail}")

# ── §1D 런타임 건강 ──
# 최근 7일 + 실사용(usage)만 — 백엔드 대시보드(get_action_health_summary)와 같은 창.
# 필터가 없던 동안 전 역사를 무기한 합산해 화석이 영원히 상위에 남았다(run_pipeline 86%
# = 은퇴한 옛 12h sweep 의 5~6월 잔재, 6주간 호출 0건인데 계속 표시 — 2026-08-04 실측).
print("\n" + "="*72); print("§1D 런타임 건강 (최근 7일 실사용, 실패율 상위)"); print("="*72)
try:
    import sqlite3
    c = sqlite3.connect("data/world_pulse.db")
    rows = c.execute("""SELECT node||':'||action AS a,
                               SUM(CASE WHEN success IN (1,'1','true','True') THEN 1 ELSE 0 END) AS ok,
                               COUNT(*) AS tot
                        FROM action_health
                        WHERE source = 'usage'
                          AND timestamp >= strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime', '-7 days')
                        GROUP BY a
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
print(f"  §1C-2 연산자:    {op_pass}/{len(OPERATORS)} PASS")
if buckets["RED"]:
    print("\n  ⚠️ RED (통화 결함 — 처리 필요):")
    for n, r in buckets["RED"]: print(f"     - {n}: {r}")
verdict = "건강 ✅" if (static_ok and not buckets["RED"] and pipe_pass == len(PIPES)
                      and op_pass == len(OPERATORS)) else "주의 ⚠️"
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
    "operators": {"passed": int(op_pass), "total": len(OPERATORS)},
}
print("\n@@HEALTH_JSON@@ " + json.dumps(_summary, ensure_ascii=False))
