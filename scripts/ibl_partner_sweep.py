#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""동반 낱말(조합 파트너) 관측 스윕 — 카탈로그가 "이 낱말이 무엇과 이어지는지"까지 말하게 한다 (2026-08-30).

왜: 상시로 켜져 있는 유일한 사전(카탈로그 71,302자·148줄)에 **조합 정보가 한 글자도 없었다**.
⟨열⟩(반환)·⟨인자⟩(입력)까지 관측으로 채워 놓고 정작 *이웃*만 비어 있어서, 낱말은 저마다
섬으로 제시된다. 문장이 모델에 닿는 통로는 둘뿐이고 둘 다 얇다 — 문법 프롬프트의 조합 예문
29개(등장 액션 32/148 = 22%)와 턴마다 오는 회상 top-3(조합 20.1%). 즉 **148 중 116 낱말은
상시 프롬프트 어디에서도 문장 안에 있는 모습을 본 적이 없다.**

실측 근거(08-30): 낱말 단위로 '교재 조합 노출률 → 실행 조합률' 상관 r=0.72(실행 20회+ 27낱말).
보여준 대로 쓴다. 단 실행(30.5%)이 교재(19.2%)·회상(20.1%)보다 높아 노출은 천장이 아니라
사전확률이다 — 그래서 이 스윕은 '가르치는 처방'이 아니라 **관측된 이웃의 광고**다.

무엇을: 선언하지 않는다(선행 명사 스키마 금지 — 헌법 '명사의 자리'). 교재(ibl_usage.db)와
실행(episode_log 완전 관측분)을 진짜 파서로 뜯어 **인접쌍**을 세고 `data/ibl_partners.json` 에
적는다. ibl_access 가 카탈로그 액션 줄에 `⟨동반: >>a · &b⟩` 로 붙인다(상위 2·최소 3회).

토큰 세 종:
  `>>node:action`  파이프에서 그 낱말 **뒤에** 실제로 온 낱말
  `&node:action`   `&` 병렬의 **곁가지**(같은 액션이면 `&같은액션` — 팬아웃 접기 자리)
  `??node:action`  `??` 폴백에서 **다음 가지**로 선 낱말

규율(⟨열⟩·⟨인자⟩ 스윕과 같다):
  - 파생물(ibl_partners.json)은 직접 수정 금지 — 다음 스윕이 되돌린다.
  - 절단된 로그는 분모에서 뺀다(잘린 코드의 뒷문장은 없는 게 아니라 안 보이는 것이다).
  - 카탈로그 밖 액션(은퇴·환각)은 싣지 않고 건수만 신고한다.
  - ★자기 자신으로 가는 `>>`(`limbs:browser >> limbs:browser`)는 **동반이 아니라 접힐 수
    있었던 자리**다(조합 계기 ⑦ '연속 동일 액션 반복'). 광고하면 반복을 권장하게 되므로 뺀다.
    같은 액션의 `&` 병렬은 반대로 그 반복을 *접은* 모양이라 남긴다.
사용: python3 scripts/ibl_partner_sweep.py [--top 2] [--min-count 3] [--dry]   (백엔드 불필요)
"""
import collections
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
import boot_paths  # noqa: F401,E402 — 층 디렉토리 등재
# 로그에서 코드를 뜯는 규약(절단 표식 해석·완전 관측 판정)은 인자 스윕이 정본 — 복제하지 않는다.
from ibl_param_sweep import (  # noqa: E402
    _codes_from_corpus, _codes_from_episodes, _known_actions,
)

OUT = ROOT / "data" / "ibl_partners.json"

TOP_N = 2        # 한 줄에 싣는 동반 수 상한(카탈로그 폭 예산)
MIN_COUNT = 3    # 1~2회는 한 세션의 버릇일 수 있다


def _qa(step) -> str:
    """액션 스텝이면 'node:action', 아니면 None."""
    if isinstance(step, dict) and "_node" in step and "action" in step:
        return f"{step['_node']}:{step['action']}"
    return None


def _heads(step) -> list:
    """그 스텝이 통화를 내보내는 '앞자리' 액션들 — 병렬이면 가지 전부, 단일이면 자기 자신."""
    if not isinstance(step, dict):
        return []
    if step.get("_parallel"):
        out = []
        for b in step.get("branches") or []:
            out.extend(_heads(b))
        return out
    if step.get("_fallback_chain"):
        out = []
        for b in step.get("_fallback_chain") or []:
            out.extend(_heads(b))
        return out
    q = _qa(step)
    return [q] if q else []


def _collect(steps, pairs, parse):
    """파서 산출을 걸으며 인접쌍을 모은다. steps = 한 파이프(문장)의 스텝 목록."""
    if not isinstance(steps, list):
        steps = [steps]
    prev = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        # 줄바꿈·`;` 로 나뉜 독립 문장은 이어진 게 아니다 — 사슬을 끊는다.
        if step.get("_seq_boundary"):
            prev = []
        heads = _heads(step)
        for a in prev:
            for b in heads:
                if a != b:                      # 자기 자신으로 가는 `>>` = 접힐 자리(제외)
                    pairs[a][f">>{b}"] += 1
        if step.get("_parallel"):
            # ★한 문장에서 한 번만 센다 — 가지마다 세면 3갈래 자기병렬이 6표가 되어
            #   `&같은액션` 이 `>>` 파트너를 부당하게 밀어낸다(같은 사건은 한 표).
            branches = [h for b in (step.get("branches") or []) for h in _heads(b)]
            for a in set(branches):
                for tok in {("&같은액션" if a == b else f"&{b}") for b in branches if b != a or branches.count(a) > 1}:
                    pairs[a][tok] += 1
        if step.get("_fallback_chain"):
            chain = [h for b in (step.get("_fallback_chain") or []) for h in _heads(b)]
            for a, b in zip(chain, chain[1:]):
                if a != b:
                    pairs[a][f"??{b}"] += 1
        # 블록(조건·반복·try)의 몸은 그 자체가 문장이다 — 사슬을 잇지 않고 따로 건다.
        for key in ("branches", "body", "then", "else", "action", "steps"):
            val = step.get(key)
            if step.get("_parallel") and key == "branches":
                continue
            if isinstance(val, (list, dict)) and not step.get("_fallback_chain"):
                _collect(val, pairs, parse)
        if isinstance(step.get("condition"), (list, dict)):
            _collect(step["condition"], pairs, parse)
        # `[table:each]{do: "…"}` 의 do 는 문자열에 담긴 진짜 문장이다 — 파싱해서 함께 센다.
        do = (step.get("params") or {}).get("do") if isinstance(step.get("params"), dict) else None
        if isinstance(do, str) and "[" in do:
            try:
                _collect(parse(do), pairs, parse)
            except Exception:
                pass
        prev = heads or prev


def observe(top_n: int = TOP_N, min_count: int = MIN_COUNT):
    from ibl.ibl_parser import parse

    corpus = _codes_from_corpus()
    execs, trunc, malformed = _codes_from_episodes()
    print(f"교재 {len(corpus)}건 · 실행 {len(execs)}건 (절단 {trunc}·깨짐 {malformed} 은 분모 제외)")

    pairs = collections.defaultdict(collections.Counter)
    parse_fail = 0
    for codes in (corpus, execs):
        for code in codes:
            try:
                steps = parse(code)
            except Exception:
                parse_fail += 1
                continue
            _collect(steps, pairs, parse)
    print(f"파싱 실패 {parse_fail}건 (교재·실행 합산)")

    known = _known_actions()
    unknown = sorted({a for a in pairs if known and a not in known})
    if unknown:
        print(f"카탈로그 밖 액션 {len(unknown)}개 (환각/은퇴 — 제외): "
              f"{', '.join(unknown[:12])}{' …' if len(unknown) > 12 else ''}")

    partners, dropped_unknown = {}, 0
    for a, cnt in pairs.items():
        if known and a not in known:
            continue
        ranked = []
        for tok, c in cnt.most_common():
            tgt = tok.lstrip(">&?")
            if known and tgt not in known and tgt != "같은액션":
                dropped_unknown += 1
                continue
            if c < min_count:
                continue
            ranked.append([tok, c])
            if len(ranked) >= top_n:
                break
        if ranked:
            partners[a] = {"n": sum(cnt.values()), "top": ranked}
    return partners, dict(parse_fail=parse_fail, truncated=trunc, malformed=malformed,
                          corpus=len(corpus), exec=len(execs), unknown_actions=unknown,
                          dropped_unknown_targets=dropped_unknown,
                          top_n=top_n, min_count=min_count)


def main():
    top_n, min_count = TOP_N, MIN_COUNT
    if "--top" in sys.argv:
        top_n = int(sys.argv[sys.argv.index("--top") + 1])
    if "--min-count" in sys.argv:
        min_count = int(sys.argv[sys.argv.index("--min-count") + 1])
    partners, meta = observe(top_n, min_count)
    doc = {
        "_comment": ("GENERATED by scripts/ibl_partner_sweep.py — 교재(코퍼스)+실행(episode_log) 실측 "
                     "조합 파트너. 직접 수정 금지. ibl_access 가 카탈로그 줄에 ⟨동반: …⟩ 로 붙인다. "
                     "선언이 아니라 관측(이어진 흔적)이다 — 안 붙은 줄은 '조합 불가'가 아니라 '관측 없음'."),
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "top_n": top_n,
        "min_count": min_count,
        "sources": meta,
        "partners": dict(sorted(partners.items())),
    }
    if "--dry" in sys.argv:
        for a, v in list(doc["partners"].items())[:20]:
            print(f"  {a:22} ⟨동반: {' · '.join(t for t, _ in v['top'])}⟩")
        print(f"\n(dry) 붙는 액션 {len(partners)}개")
        return
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    added = sum(len(" ⟨동반: " + " · ".join(t for t, _ in v["top"]) + "⟩") for v in partners.values())
    print(f"동반 관측 액션 {len(partners)}개 · 카탈로그 추가 {added:,}자 → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
