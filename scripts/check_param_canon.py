#!/usr/bin/env python3
"""파라미터·op 정본(canon) 가드 — 같은 개념에 새 이름이 또 생기는 것을 차단.

배경(2026-08-05 어휘 감사): 패키지 횡단 파라미터 표준이 없어 같은 개념이 이름을
불렸다 — 검색어 7가지(query/q/keyword/…), 결과 상한 7가지(limit/count/max_results/…),
읽기 op 5철자(get/detail/info/read/status). AI 는 매 요청마다 "이 동사는 limit 인가
count 인가"를 추측한다. 대량 개명은 코퍼스 이주가 따르는 언어 개정이라 여기서 안 한다 —
이 가드는 **신규 어휘의 게이트**: 기존 위반은 BASELINE 동결, 새 위반만 차단.

정본 규칙(고신뢰 동의어만 — 과잉 금지는 오탐·allowlist 부패를 낳는다, validators 교훈):
  파라미터(tool.json input_schema 기준):
    q, keyword, search_term      → query   (검색어)
    count, max_results, display, top → limit  (결과 상한)
    latitude → lat / longitude, lon → lng    (좌표)
    ※ pattern(정규식)·topic(주제)·keywords(태그 복수)·n(table 문법)·size(치수)·x,y(화면좌표)는
      별개 개념이라 정본 대상 아님.
  op(ops.values 기준):
    'get' 금지 → detail  (순수 동의어. info/read/status 는 뉘앙스가 달라 불문)
    짝 규칙 — add ↔ remove(소속 추가/제거) · save/create ↔ delete(엔티티 생성/파기).
    add+delete 혼합, save/create+remove 혼합 = 짝 불일치.

사용: python3 scripts/check_param_canon.py
      python3 scripts/check_param_canon.py --self-test
의존성: PyYAML. 실패 시 exit 1.
"""
import glob
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PARAM_CANON = {
    "q": "query", "keyword": "query", "search_term": "query",
    "count": "limit", "max_results": "limit", "display": "limit", "top": "limit",
    "latitude": "lat", "longitude": "lng", "lon": "lng",
}

# 2026-08-24 (#repair B5): 동결 부채 목록을 **지우고** 예외 0 으로 돌린다.
#
# 왜 지우나 — 동결은 미루기의 다른 이름이다. 2026-08-05 에 21 param + 5 op 을
# 얼려 두었고, 그 목록은 그 뒤 한 번도 줄지 않았다. 더 나쁜 것은 그 면제가
# **관문의 사각지대와 같은 자리**였다는 점이다: 선언이 없으니 타입 관문도
# 정본 가드도 그 param 을 모두 못 보았다(B35-3 ① 에서 선언을 채우자 이 가드가
# 즉시 5건을 잡았다 — 가리지 않으면 보이지 않는다).
#
# 어떻게 갑0나 — 이름을 지우지 않고 자리를 옮겼다:
#   · param 20건: tool_json properties 에서 정본으로 개명(또는 중복 삭제)하고
#     관습어는 aliases 로 수용. 핸들러는 정본 키를 먼저 읽는다(둘 다 온다).
#     → 기존 호출(count/q/keyword/max_results/display/lon)은 그대로 통과한다.
#   · op 4건: get→detail(workflow·trigger·folder_note), remove→delete(portal).
#     엔진은 구 철자를 계속 받고(어휘만 정본), 교재(코퍼스 48문장)·가이드는
#     정본으로 이주했다 — 이름을 바꾸면 표면을 다 옴기는 것이 규약(checklist 0단계).
#   · 죽은 면제 2건(sense:search_local·others:contact): 그 액션은 이미 없다.
#
# ★이제 예외가 없다. 새 비정본이 들어오면 그냠 바로 커밋이 막힌다 —
#   목록을 다시 세우지 말 것(면허가 아니라는 말은 목록이 있는 한 지켜지지 않았다).
BASELINE_PARAMS: dict = {}
BASELINE_OPS: dict = {}


def _tool_props(root: str) -> dict:
    """tool 이름 → (패키지, input_schema property 집합)."""
    out = {}
    for tj in glob.glob(os.path.join(root, "data/packages/installed/tools/*/tool.json")):
        pkg = os.path.basename(os.path.dirname(tj))
        try:
            t = json.load(open(tj, encoding="utf-8"))
        except Exception:
            continue
        for tool in (t.get("tools") or []):
            props = ((tool.get("input_schema") or {}).get("properties") or {})
            out[tool.get("name")] = (pkg, set(props.keys()))
    return out


def scan(root: str) -> list:
    reg_path = os.path.join(root, "data/ibl_nodes.yaml")
    d = yaml.safe_load(open(reg_path, encoding="utf-8"))
    props_by_tool = _tool_props(root)
    issues = []
    for nname, node in (d.get("nodes") or {}).items():
        for aname, a in (node.get("actions") or {}).items():
            act = f"{nname}:{aname}"
            # ── 파라미터 정본 ──
            if a.get("router") == "handler" and a.get("tool") in props_by_tool:
                pkg, props = props_by_tool[a["tool"]]
                allowed = BASELINE_PARAMS.get(act, set())
                for p in sorted(props):
                    if p in PARAM_CANON and p not in allowed:
                        issues.append(f"{act} ({pkg}): 파라미터 '{p}' — 정본 '{PARAM_CANON[p]}' 사용")
            # ── op 정본·짝 규칙 ──
            ops = set(((a.get("ops") or {}).get("values") or {}).keys())
            allowed_ops = BASELINE_OPS.get(act, set())
            if "get" in ops and "op-get" not in allowed_ops:
                issues.append(f"{act}: op 'get' — 정본 'detail' 사용")
            if "add" in ops and "delete" in ops and "remove" not in ops \
                    and "pair-add-delete" not in allowed_ops:
                issues.append(f"{act}: 짝 불일치 add↔delete — add 의 짝은 remove")
            if ("save" in ops or "create" in ops) and "remove" in ops \
                    and "delete" not in ops and "add" not in ops \
                    and "pair-save-remove" not in allowed_ops:
                issues.append(f"{act}: 짝 불일치 save/create↔remove — 엔티티 파기는 delete")
    return issues


def self_test() -> bool:
    """가짜 레지스트리·tool.json 으로 검출/면제 양방향 확인."""
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        pkgdir = os.path.join(tmp, "data/packages/installed/tools/fake")
        os.makedirs(pkgdir)
        json.dump({"tools": [
            {"name": "bad_tool", "input_schema": {"properties": {"q": {}, "count": {}}}},
            {"name": "good_tool", "input_schema": {"properties": {"query": {}, "limit": {}, "pattern": {}}}},
        ]}, open(os.path.join(pkgdir, "tool.json"), "w"))
        reg = {"nodes": {"sense": {"actions": {
            "bad": {"router": "handler", "tool": "bad_tool"},
            "good": {"router": "handler", "tool": "good_tool"},
            "badop": {"ops": {"values": {"get": "", "add": "", "delete": ""}}},
            "goodop": {"ops": {"values": {"list": "", "detail": "", "add": "", "remove": ""}}},
        }}}}
        os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
        yaml.safe_dump(reg, open(os.path.join(tmp, "data/ibl_nodes.yaml"), "w"))
        issues = scan(tmp)
        got = "\n".join(issues)
        checks = [
            ("'q'" in got and "'count'" in got, "bad_tool 파라미터 검출"),
            ("good (" not in got, "정본 파라미터 통과"),
            ("op 'get'" in got, "op get 검출"),
            ("add↔delete" in got, "짝 불일치 검출"),
            ("goodop" not in got, "정상 짝 통과"),
        ]
        for cond, label in checks:
            if not cond:
                print(f"✗ self-test: {label} 실패\n{got}")
                ok = False
    print("✓ self-test 통과" if ok else "✗ self-test 실패")
    return ok


def main() -> int:
    if "--self-test" in sys.argv:
        return 0 if self_test() else 1
    issues = scan(ROOT)
    if issues:
        print(f"✗ 파라미터/op 정본 위반 {len(issues)}건 (신규 어휘 게이트):")
        for i in issues:
            print(f"  - {i}")
        print("\n수리: 정본 이름으로 개명하고, 관습어 수용이 필요하면 aliases: 블록으로"
              " (예: aliases: {query: [q]})")
        return 1
    print(f"✓ 파라미터/op 정본 OK (부채 동결: 파라미터 {len(BASELINE_PARAMS)}건 · op {len(BASELINE_OPS)}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
