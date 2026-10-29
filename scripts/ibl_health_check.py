#!/usr/bin/env python3
"""IBL 건강 점검 — 매뉴얼 §1 절차를 그대로 실행(외부 도구 의존 없이 /ibl/execute + 레지스트리만)."""
import json, time, urllib.request, urllib.error, subprocess, sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401
from ibl_v2_ir import unpack

BASE = "http://localhost:8765"
PID = "하드웨어"
_STARTED = time.monotonic()


def progress(stage, item=""):
    """타임아웃에도 마지막 실행 위치가 부모에게 남도록 즉시 내보낸다."""
    print("@@HEALTH_PROGRESS@@ " + json.dumps({
        "stage": stage, "item": item,
        "elapsed_s": round(time.monotonic() - _STARTED, 1),
    }, ensure_ascii=False), flush=True)

def _abort_admission(detail):
    """실행 접수가 닫혀 호출이 거절됐다(재기동 drain·세대 불일치) — 거절은 어휘 결함이 아니다.

    남은 절을 계속 돌리면 모든 항목이 즉시 503 으로 실패해 '골든파이프 0/5·연산자 0/7' 가짜 RED 가
    된다(2026-09-15 09:29 실측 — 09:28:26 development_files 재기동 요청의 drain 과 겹침). 여기서
    점검을 **중단**하고 러너에게 '미완'을 알린다(러너는 audit_incomplete 로 적는다). 부모 자격을
    물려받은 정상 경로(execute 의 X-Runtime-Parent)에선 오지 않는 길 — 자격 없는 수동 실행이
    drain 과 겹쳤을 때의 정직한 종료."""
    print(f"\n‼ 점검 중단 — 실행 접수가 닫혀 있음(재기동 대기): {detail}")
    print("@@HEALTH_JSON@@ " + json.dumps({"aborted": "admission_closed", "detail": detail},
                                          ensure_ascii=False))
    sys.exit(0)

from ibl_check_client import execute as execute_checked, final_of, request, value_of, CheckFailure, item_rows


def _request(fields, pid):
    return request(fields, pid, base=BASE, timeout=45, on_admission=_abort_admission)


def execute(code, pid=PID):
    return execute_checked(code, pid, request_page=_request)


def classify_currency(result, declared):
    """실행 상태와 업무 값을 분리하고 현행 returns 선언만 대조한다."""
    try:
        value = value_of(result)
    except CheckFailure as exc:
        level = "YELLOW" if exc.key == "_execution_error" and exc.result.get("executed") is True else "RED"
        return level, str(exc)[:160]
    if declared != "items":
        return "SKIP", f"{declared} (값 반환)"
    items = item_rows(value)
    if items is None:
        return "RED", "items 선언인데 List 또는 Record.items List가 없습니다."
    if not all(isinstance(row, dict) for row in items):
        return "RED", "items의 각 행은 Record여야 합니다."
    return ("GREEN", f"items[{len(items)}]") if items else ("YELLOW", "items 빈(데이터 없음)")

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
        import boot_paths  # noqa: F401 — 층 디렉토리 등재

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
        import boot_paths  # noqa: F401 — 층 디렉토리 등재
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
        import boot_paths  # noqa: F401 — 층 디렉토리 등재
        from ibl_v2_learning import call_sites, call_parameters
        from ibl_ops import resolve_op
        adef = ((_nodes.get("nodes") or {}).get(fa[0], {}).get("actions") or {}).get(fa[1]) or {}
        calls = call_sites(tmpl)
        return resolve_op(adef, call_parameters(calls[0]) if calls else {})
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


from ibl_health_programs import PIPES, OPERATORS, pipe_ok, operator_result

def run_contract_drift():
    """§1B-2 — 등록 스크립트·관용구의 선언 반환 계약을 실측과 대조(검사기 해소·판정 재사용).

    컴파일은 현행 관용구 원장과 같은 읽기 관점(compile_current), 실행은 검사기가 pure 로 판정한
    표본만 이 프로세스에서 한다(외부 호출·쓰기 없음). 어느 단계가 죽어도 점검 전체를 죽이지 않고
    error 로 보고한다 — 침묵하면 '대조 0건'이 건강처럼 보인다."""
    try:
        from ibl_contract_drift import collect, summarize
        from function_library import compile_current
        from ibl_v2_runtime import Runtime
        root = os.getcwd()
        samples = json.load(open("data/ibl_contract_samples.json", encoding="utf-8"))
        scripts = _yaml.safe_load(open("data/scripts/registry.yaml", encoding="utf-8")) or {}
        rows = collect(samples, scripts, lambda code: compile_current(code, root),
                       lambda plan: Runtime(plan).run())
        return {**summarize(rows), "rows": rows}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:300], "compared": 0}


from ibl_contract_drift import describe as _drift_line  # noqa: E402


def main():
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
    progress("정적 검사", "build --check")
    print("="*72); print("§1A 정적 정합성 (build --check)"); print("="*72)
    try:
        r = subprocess.run([sys.executable, "scripts/build_ibl_nodes.py", "--check"],
                           capture_output=True, text=True, cwd=os.getcwd(), timeout=600)
    except subprocess.TimeoutExpired:
        print("정적 검사 제한시간 초과 (600초): build --check", file=sys.stderr, flush=True)
        sys.exit(1)
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
            progress("fixture", name)
            _d = execute(code)
            verdict, reason = classify_currency(_d, declared)
            # 봉투 규모 불변식(ibl_honesty.scope_violation): total>items 인데 truncated 침묵 = YELLOW.
            # 원천 명사의 결함이라 GREEN 통화라도 건강하지 않다 — 하류가 매 파이프에 거짓 절단 경고를 단다.
            try:
                from ibl_honesty import scope_violation as _scope_violation
                _sv = _scope_violation(final_of(_d))
                if _sv and verdict == "GREEN":
                    verdict, reason = "YELLOW", f"봉투 규모 불변식: {_sv}"
            except Exception:
                pass
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

    # ── §1B-2 계약 대조 (선언 반환 계약 ↔ 실측 값) ──
    # §1B 는 returns(items|scalar) 수준만 단언한다. 검사기가 믿는 callable_contract 의 반환형과 실제 값은
    # 아무도 대조하지 않아, 판정관용구가 {items,count}를 돌려주는데 계약은 필드 없는 Record 인 결함을
    # 사람이 손으로 찾았다(31ea17f0). 표본을 검사기로 컴파일해 Plan.result_type 을 얻고, 검사기가 pure 로
    # 판정한 표본만 실행해 같은 타입 규칙으로 대조한다. 실행하지 않은 대상은 사유와 함께 세어 남긴다.
    print("\n" + "="*72); print("§1B-2 계약 대조 (선언 반환 계약 ↔ 실측)"); print("="*72)
    progress("계약 대조")
    contract_drift = run_contract_drift()
    for row in contract_drift.get("rows", []):
        detail = row.get("reason") or ", ".join(row.get("paths") or []) or ""
        print(f"  [{row['verdict']:14}] {row['target']:28} {detail}")
    contract_drift.pop("rows", None)
    print(f"  → {_drift_line(contract_drift)}")

    # ── §1C 골든 파이프 (문법+통화 흐름) ──
    print("\n" + "="*72); print("§1C 골든 파이프 (명시 값 흐름)"); print("="*72)
    pipe_pass = 0
    pipe_fails = []
    for name, code, kind in PIPES:
        progress("골든 파이프", name)
        fr = final_of(execute(code))
        ok = pipe_ok(fr, kind)
        if not ok:
            # 외부 API 일시 블립 흡수 — 1회 재시도. 이 절의 목적은 문법·통화 흐름 회귀지
            # 외부 API liveness 가 아니다(arXiv 가 00:05 UTC 인덱스 갱신 창에서 상습 블립
            # → 아침 09:05 KST 점검마다 4/5 거짓 경보, 2026-08-06 진단). 진짜 회귀는
            # 결정론적이라 재시도로 안 사라진다.
            time.sleep(3)
            fr = final_of(execute(code))
            ok = pipe_ok(fr, kind)
            if ok:
                print(f"  [RETRY] {name} — 1차 블립, 재시도로 통과")
        pipe_pass += ok
        if not ok:
            pipe_fails.append(name + ": " + str(fr)[:160])
        print(f"  [{'PASS' if ok else 'FAIL':4}] {name:24} {('items='+str(len(fr.get('items',[]))) if isinstance(fr,dict) and isinstance(fr.get('items'),list) else list(fr.keys())[:4] if isinstance(fr,dict) else fr)}")

    print("\n" + "="*72); print("§1C-2 연산자 (?? · & — 동작 단언)"); print("="*72)
    op_pass = 0
    for name, code, expected in OPERATORS:
        progress("연산자", name)
        try:
            ok, detail = operator_result(execute(code), expected)
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
    progress("런타임 기록 조회")
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
        # 호출 통로 내역 (2026-08-21 ③ 조사 — channel 컬럼 신설 이후 행만. agent=에이전트
        # 도구 루프 / app=앱·조종실·원격 직접 실행 / scheduler=캘린더 발화 / ?=신설 전 구 행).
        try:
            ch = c.execute("""SELECT COALESCE(channel,'?') AS ch,
                                     SUM(CASE WHEN success IN (1,'1','true','True') THEN 0 ELSE 1 END) AS bad,
                                     COUNT(*) AS tot
                              FROM action_health
                              WHERE source = 'usage'
                                AND timestamp >= strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime', '-7 days')
                              GROUP BY ch ORDER BY tot DESC""").fetchall()
            if ch:
                print("  통로별: " + " · ".join(f"{name} 실패 {bad}/{tot}" for name, bad, tot in ch))
        except Exception:
            pass  # channel 컬럼 이전 스키마
        c.close()
    except Exception as e:
        print("  (조회 실패:", e, ") — 스키마 다를 수 있음")

    # ── 종합 ──
    print("\n" + "="*72); print("종합 판정"); print("="*72)
    print(f"  §1A 정적:        {'✅' if static_ok else '❌'}")
    print(f"  §1B 통화:        GREEN {len(buckets['GREEN'])} / YELLOW {len(buckets['YELLOW'])} / RED {len(buckets['RED'])}")
    print(f"  §1C 골든파이프:  {pipe_pass}/{len(PIPES)} PASS")
    print(f"  §1C-2 연산자:    {op_pass}/{len(OPERATORS)} PASS")
    print(f"  §1B-2 계약대조:  {_drift_line(contract_drift)}")
    if buckets["RED"]:
        print("\n  ⚠️ RED (통화 결함 — 처리 필요):")
        for n, r in buckets["RED"]: print(f"     - {n}: {r}")
    verdict = "건강 ✅" if (static_ok and buckets["GREEN"] and not buckets["RED"] and pipe_pass == len(PIPES)
                          and op_pass == len(OPERATORS)) else "주의 ⚠️"
    print(f"\n  ▶ IBL 구조 건강: {verdict}")

    # ── 기계 판독 요약 — world_pulse_health.run_ibl_health_check 가 이 한 줄을 파싱한다.
    # 사람용 로그의 문구가 바뀌어도 계약이 깨지지 않도록 구조화 출력을 병행(마커 없으면 파서가 fail 처리).
    _summary = {
        "elapsed_s": round(time.monotonic() - _STARTED, 1),
        "static_ok": bool(static_ok),
        "currency": {
            "green": len(buckets["GREEN"]), "yellow": len(buckets["YELLOW"]), "red": len(buckets["RED"]),
            "reds": [{"name": n, "reason": r} for n, r in buckets["RED"]],
        },
        "golden_pipes": {"passed": int(pipe_pass), "total": len(PIPES), "fails": pipe_fails},
        "operators": {"passed": int(op_pass), "total": len(OPERATORS)},
        "contract_drift": contract_drift,
    }
    print("\n@@HEALTH_JSON@@ " + json.dumps(_summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
