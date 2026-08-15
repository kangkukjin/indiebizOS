#!/usr/bin/env python3
"""vocab_composition_metrics.py — 언어의 조합성 4지표 (고차 문장 전후 비교용)

왜 조합률로 재지 않는가: 시딩으로 올릴 수 있는 숫자는 지표가 아니다. "소스 >> table:*" 를
아무리 더 넣어도 *문형*은 늘지 않는다. 그래서 이 스크립트는 네 가지를 함께 잰다 —

  1. 파이프 길이 중앙값        — 문장이 실제로 길어졌는가
  2. 미조합 액션 수            — 어휘가 언어에 편입되고 있는가 (그리고 어느 노드가 갇혀 있는가)
  3. 문형 분포                 — 조회/발신/축적/시간/조건/적용 (핵심 지표)
  4. 낱말당 조합 파트너 다양성 — "차원을 더했는가"의 대리 측정 (파트너 1개면 낱말이 아니라 고정구)

읽는 것: data/ibl_usage.db(해마 코퍼스) + data/ibl_nodes.yaml(레지스트리).
쓰는 것: 없음(순수 읽기). --json 으로 기계 판독 출력.

사용:
  python3 scripts/vocab_composition_metrics.py
  python3 scripts/vocab_composition_metrics.py --json > /tmp/before.json
  python3 scripts/vocab_composition_metrics.py --compare /tmp/before.json

정본 설계: docs/HIGHER_ORDER_SENTENCE_DESIGN.md §6
stdlib 전용(yaml 제외 — 레지스트리 파싱에만 사용).
"""
import argparse
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "ibl_usage.db")
REG = os.path.join(ROOT, "data", "ibl_nodes.yaml")

ACT_RE = re.compile(r"\[([a-z_]+):([a-z_0-9]+)\]")

# ★행동 vs 교재 (2026-08-15 수리) — 이 둘을 한 숫자에 섞으면 둘 다 못 본다.
#
# 실측 사례: 전체 코퍼스는 파이프 7%·길이 중앙값 2 인데, 실사용 증류만 보면 22%·중앙값 3
# 이었다. 차이의 정체는 balanced_20260516(옛 합성 대량 1,781행, 파이프 2%)이다 —
# 그건 *가르친 것*이지 *한 것*이 아닌데 전체 평균을 끌어내려 "이 언어는 2단에서 멈춘다"는
# 잘못된 진단을 만들었다.
#
# 판정의 근거는 **행동**이다. 교재는 맥락으로만 본다(시딩으로 올릴 수 있는 숫자는 지표가
# 아니라는 원칙의 연장 — 시드는 교재에만 들어가고 행동은 못 건드린다).
BEHAVIOR_SOURCES = {"distilled"}   # 실행 경험 증류 = AI 가 실제로 쓴 문장

# ★조합은 파이프만이 아니다 (2026-08-15 2차 수리) — `do:` 안에 문장을 싣는 것이
# 고차 조합이다. 이걸 못 보면 [table:each]{items:…, do:"[sense:weather]…"} 가 "단발"로
# 세어져, 고차 문장을 만들어 놓고 그게 쓰인 걸 지표가 부정하게 된다(실측 사례 1건).
NESTED_RE = re.compile(r"\bdo\s*:\s*[\"'\[]")


def is_composed(code: str) -> bool:
    """조합된 문장인가 — 파이프(>>) 또는 고차(do: 에 문장 적재)."""
    return ">>" in code or bool(NESTED_RE.search(code))

# 문형 분류 — 문장이 *무엇을 하는 모양인가*. 한 문장이 여러 문형에 속할 수 있다(발신+적용 등).
# 판정은 등장 액션의 노드/이름으로 한다(의미가 아니라 구조 — 재현 가능해야 하므로).
SINK_NODES = {"others", "limbs"}
LEDGER_ACTIONS = {
    "self:memory", "self:storage", "self:notebook", "self:forage", "self:folder_note",
    "self:write", "self:sheet", "self:finance", "self:health", "self:spend",
    "self:business", "self:business_item", "self:workflow", "self:script",
}
TIME_ACTIONS = {"self:schedule", "self:trigger", "self:manage_events", "self:goal", "self:switch"}
APPLY_ACTIONS = {"table:each"}


def load_registry_actions():
    try:
        import yaml
    except ImportError:
        print("PyYAML 이 필요합니다 (.venv 파이썬으로 실행하세요).", file=sys.stderr)
        raise SystemExit(2)
    with open(REG, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    nodes = data.get("nodes", data)
    out = set()
    for node, body in nodes.items():
        if not isinstance(body, dict):
            continue
        for a in (body.get("actions") or {}):
            out.add(f"{node}:{a}")
    return out


def sentence_forms(names, code):
    """한 문장의 문형 집합."""
    forms = set()
    if any(n.startswith("sense:") for n in names) or any(n.startswith("table:") for n in names):
        forms.add("조회")
    if any(n.split(":")[0] in SINK_NODES for n in names) or "self:notify_user" in names:
        forms.add("발신")
    if any(n in LEDGER_ACTIONS for n in names):
        forms.add("축적")
    if any(n in TIME_ACTIONS for n in names):
        forms.add("시간")
    if any(n in APPLY_ACTIONS for n in names):
        forms.add("적용")
    if re.search(r"\bif\b|\bcase\b", code):
        forms.add("조건")
    return forms


def measure():
    con = sqlite3.connect(DB)
    rows = [(r[0] or "", r[1] or "") for r in
            con.execute("select source, ibl_code from ibl_examples") if r[1]]
    con.close()
    allacts = load_registry_actions()
    return {
        "행동": _measure_codes([c for s, c in rows if s in BEHAVIOR_SOURCES], allacts),
        "교재": _measure_codes([c for _, c in rows], allacts),
        "출처별": {s: n for s, n in Counter(s for s, _ in rows).most_common(8)},
    }


def _measure_codes(codes, allacts):
    pipe_lengths = []
    in_pipe = set()
    partners = defaultdict(set)
    form_counter = Counter()
    grammar = Counter()

    solo_form_counter = Counter()
    nested = 0
    for code in codes:
        names_all = [f"{m.group(1)}:{m.group(2)}" for m in ACT_RE.finditer(code)]
        for label, pat in (("&", r"&"), ("$변수", r"\$[a-z_]"), (";", r";"),
                           ("??", r"\?\?"), ("if/case", r"\bif\b|\bcase\b"), ("@몸", r"@[a-z]")):
            if re.search(pat, code):
                grammar[label] += 1
        # ★문형은 *조합된 문장* 기준으로만 센다. 단발 명령("메시지 보내줘" 한 줄)까지 세면
        #   "발신 973" 같은 숫자가 나와 조합이 되고 있다는 착시를 준다 — 이 지표가 묻는 것은
        #   "싱크가 파이프 안으로 들어왔는가"이지 "싱크 어휘를 쓰는가"가 아니다.
        if not is_composed(code):
            for form in sentence_forms(names_all, code):
                solo_form_counter[form] += 1
            continue
        for form in sentence_forms(names_all, code):
            form_counter[form] += 1
        if NESTED_RE.search(code):
            nested += 1
            # 고차 문장은 do: 안의 낱말도 조합 파트너다 — 파이프가 아니어도 함께 쓰였다.
            for a1 in names_all:
                for a2 in names_all:
                    if a1 != a2:
                        partners[a1].add(a2)
                in_pipe.add(a1)
        if ">>" not in code:
            continue
        seq = []
        for seg in code.split(">>"):
            m = ACT_RE.search(seg)
            seq.append(f"{m.group(1)}:{m.group(2)}" if m else None)
        named = [n for n in seq if n]
        if named:
            pipe_lengths.append(len(named))
        for i, n in enumerate(seq):
            if not n:
                continue
            in_pipe.add(n)
            if i > 0 and seq[i - 1]:
                partners[n].add(seq[i - 1])
            if i < len(seq) - 1 and seq[i + 1]:
                partners[n].add(seq[i + 1])

    never = sorted(a for a in allacts if a not in in_pipe)
    never_by_node = Counter(a.split(":")[0] for a in never)
    div = sorted((len(v) for v in partners.values()), reverse=True)
    total = len(codes)

    return {
        "총_문장": total,
        "조합_문장": len(pipe_lengths) + nested,
        "파이프_문장": len(pipe_lengths),
        "고차_문장": nested,          # do: 에 문장을 실은 것 (파이프 없이도 조합)
        "파이프_비율%": round((len(pipe_lengths) + nested) * 100 / total, 1) if total else 0,
        "파이프_길이_중앙값": statistics.median(pipe_lengths) if pipe_lengths else 0,
        "파이프_길이_평균": round(statistics.mean(pipe_lengths), 2) if pipe_lengths else 0,
        "레지스트리_액션": len(allacts),
        "미조합_액션": len(never),
        "미조합_노드별": dict(never_by_node.most_common()),
        "미조합_목록": never,
        "문형_분포": dict(form_counter.most_common()),        # 파이프 문장 기준
        "문형_수": len(form_counter),
        "문형_분포_단발": dict(solo_form_counter.most_common()),  # 참고: 조합 안 된 단발 문장
        "파트너_다양성_중앙값": statistics.median(div) if div else 0,
        "파트너_다양성_최대": div[0] if div else 0,
        "파트너_1개뿐": sum(1 for d in div if d == 1),
        "문법_사용": {k: f"{v} ({round(v*100/total,1)}%)" for k, v in grammar.most_common()},
    }


def render(full, before=None):
    print("=" * 62)
    print(" 언어 조합성 4지표")
    print("=" * 62)
    print(" ★판정 근거는 [행동] 이다 — [교재] 는 맥락. 시드는 교재만 올리고")
    print("   행동은 못 건드린다(그래서 시딩으로 못 속이는 지표다).")
    src = full.get("출처별") or {}
    if src:
        print("   출처: " + " · ".join(f"{k} {v:,}" for k, v in list(src.items())[:5]))
    for label, key in (("행동 (실사용 증류)", "행동"), ("교재 (전 코퍼스)", "교재")):
        print()
        print("─" * 62)
        print(f" [{label}]")
        print("─" * 62)
        _render_one(full[key], (before or {}).get(key))
    print("=" * 62)


def _render_one(m, before=None):
    def delta(key):
        if not before or key not in before:
            return ""
        try:
            d = m[key] - before[key]
        except TypeError:
            return ""
        if d == 0:
            return "  (변화 없음)"
        return f"  ({'+' if d > 0 else ''}{round(d, 2)})"

    print(f"문장                   {m['총_문장']:,}")
    print(f"조합 문장              {m.get('조합_문장', m['파이프_문장']):,} ({m['파이프_비율%']}%)"
          f"   [파이프 {m['파이프_문장']:,} · 고차 {m.get('고차_문장', 0):,}]")
    print()
    print(f"① 파이프 길이 중앙값   {m['파이프_길이_중앙값']}{delta('파이프_길이_중앙값')}"
          f"   [평균 {m['파이프_길이_평균']}]")
    print(f"② 미조합 액션          {m['미조합_액션']} / {m['레지스트리_액션']}{delta('미조합_액션')}")
    for node, n in m["미조합_노드별"].items():
        print(f"     {node:8s} {n}")
    print(f"③ 문형 수 (파이프 안)  {m['문형_수']}{delta('문형_수')}")
    solo = m.get("문형_분포_단발", {})
    for form, n in m["문형_분포"].items():
        b = f"  (전 {before['문형_분포'].get(form, 0)})" if before and "문형_분포" in before else ""
        print(f"     {form:4s} {n:5,}{b}    [단발 {solo.get(form, 0):,}]")
    for form, n in solo.items():
        if form not in m["문형_분포"]:
            print(f"     {form:4s} {0:5,}          [단발 {n:,}]  ← 조합된 적 없음")
    print(f"④ 파트너 다양성 중앙값 {m['파트너_다양성_중앙값']}{delta('파트너_다양성_중앙값')}"
          f"   [최대 {m['파트너_다양성_최대']} · 파트너 1개뿐 {m['파트너_1개뿐']}개]")
    print()
    print("문법 사용률")
    for k, v in m["문법_사용"].items():
        print(f"     {k:8s} {v}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="기계 판독 JSON 출력")
    ap.add_argument("--compare", metavar="BEFORE.json", help="이전 측정과 델타 비교")
    ap.add_argument("--list-never", action="store_true", help="미조합 액션 전체 목록")
    args = ap.parse_args()

    m = measure()
    if args.json:
        print(json.dumps(m, ensure_ascii=False, indent=2))
        return
    before = None
    if args.compare:
        with open(args.compare, encoding="utf-8") as f:
            before = json.load(f)
    render(m, before)
    if args.list_never:
        print("\n미조합 액션 전체 (행동 기준 — 실사용 파이프에 한 번도 안 나온 것):")
        for a in m["행동"]["미조합_목록"]:
            mark = "" if a in m["교재"]["미조합_목록"] else "   (교재에는 조합 있음 = 가르쳤으나 안 씀)"
            print("  ", a + mark)


if __name__ == "__main__":
    main()
