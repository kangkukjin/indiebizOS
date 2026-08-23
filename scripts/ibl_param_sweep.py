#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""입력 모양(인자 이름) 관측 스윕 — 카탈로그가 "무엇을 받는지"까지 말하게 한다 (2026-08-23).

왜: 반환 모양은 ⟨열: …⟩ 로 실측·방출되는데(ibl_shape_sweep), **입력 모양은 아무 데도
구조로 없다** — 151 액션 중 정식 params 스키마 0, 인자 의미는 전부 `target_description`
산문(41K자, 어휘 텍스트의 73%)에 있고 그 산문은 프롬프트에 실리지도 않는다(해마 RAG 만 읽음).
모델은 인자를 해마 예문에서 *추측*한다. 한글 비유로 말하면 글자 모양(조음 구조)이 반은
비어 있는 셈이다 — 이 스윕이 그 반을 채운다.

무엇을: 선언 스키마를 손으로 쓰지 않는다(선행 명사 스키마 금지 — 헌법 '명사의 자리').
대신 **쓰인 흔적을 측정**한다 — 교재(코퍼스 ibl_usage.db)와 실행(episode_log 의 완전
관측 execute_ibl 코드)을 진짜 파서(ibl_parser.parse)로 뜯어 액션별·op별 인자 키의 빈도를
`data/ibl_param_shapes.json` 에 적고, ibl_access 가 카탈로그 줄에 ⟨인자: a·b·(c)⟩ 로 붙인다
(괄호 = 가끔 쓰이는 선택 인자, 괄호 없음 = 거의 항상 함께 오는 인자).

규율(반환 모양 스윕과 같다):
  - 파생물(ibl_param_shapes.json)은 직접 수정 금지 — 다음 스윕이 되돌린다.
  - 절단된 로그(`…(+N자)`/옛 `...`)는 분모에서 뺀다 — 잘린 코드를 파싱하면 거짓 모양이 된다.
  - 파싱 실패한 코드는 조용히 건너뛰지 않고 건수를 신고한다(깨짐≠없음).
  - `op`/`_`-접두 키는 인자 목록에서 뺀다(op 는 `.op` 줄이 이미 구조로 말한다).
사용: python3 scripts/ibl_param_sweep.py [--min-ratio 0.05] [--dry]   (백엔드 불필요)
"""
import collections
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: F401,E402 — 층 디렉토리 등재

OUT = ROOT / "data" / "ibl_param_shapes.json"
CORPUS = ROOT / "data" / "ibl_usage.db"
EPISODES = ROOT / "data" / "world_pulse.db"

MAX_KEYS = 8          # 한 줄에 싣는 인자 수 상한(카탈로그 폭 예산)
MIN_COUNT = 2         # 한 번 나온 키는 오타일 수 있다
ALWAYS_RATIO = 0.8    # 이 비율 이상 = '거의 항상' (괄호 없이)

# 로그에서 execute_ibl 코드를 뜯는 정규식 — ibl_composition_metrics 와 같은 표식 해석
TOOL = re.compile(r"\] tool_use (\S+) (\{.*)")
TRUNC = re.compile(r"…\(\+(\d+)자\)$")
TRUNC_LEGACY = re.compile(r"\.\.\.$")
CODE = re.compile(r'"code"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _walk(steps, out):
    """파서 산출(중첩 블록 포함)에서 (node, action, params) 를 전부 꺼낸다."""
    if isinstance(steps, dict):
        if "_node" in steps and "action" in steps and isinstance(steps.get("params"), dict):
            out.append((steps["_node"], steps["action"], steps["params"]))
        for v in steps.values():
            if isinstance(v, (dict, list)):
                _walk(v, out)
    elif isinstance(steps, list):
        for s in steps:
            _walk(s, out)


def _codes_from_corpus():
    if not CORPUS.exists():
        return []
    try:
        return [r[0] for r in sqlite3.connect(CORPUS).execute("SELECT ibl_code FROM ibl_examples") if r[0]]
    except sqlite3.Error as e:
        print(f"[경고] 코퍼스 읽기 실패: {e}")
        return []


def _codes_from_episodes():
    """완전 관측된 execute_ibl 코드만. 절단·깨짐은 따로 센다."""
    codes, trunc, malformed = [], 0, 0
    if not EPISODES.exists():
        return codes, trunc, malformed
    try:
        rows = sqlite3.connect(EPISODES).execute("SELECT log FROM episode_log WHERE log LIKE '%execute_ibl%'")
    except sqlite3.Error as e:
        print(f"[경고] episode_log 읽기 실패: {e}")
        return codes, trunc, malformed
    for (log,) in rows:
        for line in (log or "").splitlines():
            m = TOOL.search(line)
            if not m or "execute_ibl" not in m.group(1):
                continue
            arg = m.group(2)
            c = CODE.search(arg)
            if c:
                try:
                    codes.append(json.loads('"' + c.group(1) + '"'))
                except Exception:
                    codes.append(c.group(1))
            elif TRUNC.search(arg) or TRUNC_LEGACY.search(arg):
                trunc += 1
            else:
                malformed += 1
    return codes, trunc, malformed


def observe(min_ratio: float = 0.05):
    from ibl.ibl_parser import parse

    corpus = _codes_from_corpus()
    execs, trunc, malformed = _codes_from_episodes()
    print(f"교재 {len(corpus)}건 · 실행 {len(execs)}건 (절단 {trunc}·깨짐 {malformed} 은 분모 제외)")

    # 색인 키: node:action 과 node:action#op — 둘 다 센다(op 줄이 자기 인자만 말할 수 있게)
    n_samples = collections.Counter()
    key_counts = collections.defaultdict(collections.Counter)
    src_counts = collections.defaultdict(collections.Counter)
    key_src = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    pair_counts = collections.defaultdict(collections.Counter)   # 같은 호출에 함께 온 키 쌍
    folded = collections.Counter()                               # 선언 별칭 → 정규 키로 접은 횟수
    aliases = _alias_map()
    parse_fail = 0
    for origin, codes in (("corpus", corpus), ("exec", execs)):
        for code in codes:
            try:
                steps = parse(code)
            except Exception:
                parse_fail += 1
                continue
            found = []
            _walk(steps, found)
            for node, action, params in found:
                qa = f"{node}:{action}"
                amap = aliases.get(qa) or {}
                keys = []
                for k in params.keys():
                    if k == "op" or str(k).startswith("_"):
                        continue
                    canon = amap.get(k)
                    if canon:
                        folded[f"{qa}: {k}→{canon}"] += 1
                        k = canon
                    if k not in keys:
                        keys.append(k)
                op = params.get("op")
                idx = [qa]
                if isinstance(op, str) and op:
                    idx.append(f"{qa}#{op}")
                for q in idx:
                    n_samples[q] += 1
                    src_counts[q][origin] += 1
                    for i, k in enumerate(keys):
                        key_counts[q][k] += 1
                        key_src[q][k][origin] += 1
                        for k2 in keys[i + 1:]:
                            pair_counts[q][tuple(sorted((k, k2)))] += 1
    print(f"파싱 실패 {parse_fail}건 (교재·실행 합산)")
    if folded:
        print(f"선언 별칭 접기 {sum(folded.values())}건: " +
              ", ".join(f"{k}×{v}" for k, v in folded.most_common(6)))

    # 카탈로그에 없는 액션(환각·은퇴 어휘)은 싣지 않고 신고만 한다 — 붙일 줄이 없다.
    known = _known_actions()
    unknown = sorted({q.split("#")[0] for q in n_samples if known and q.split("#")[0] not in known})
    if unknown:
        print(f"카탈로그 밖 액션 {len(unknown)}개 (환각/은퇴 — 제외): {', '.join(unknown[:12])}{' …' if len(unknown) > 12 else ''}")

    shapes = {}
    for q, n in n_samples.items():
        if known and q.split("#")[0] not in known:
            continue
        ranked = []
        for k, c in key_counts[q].most_common():
            ratio = c / n
            if c < MIN_COUNT or ratio < min_ratio:
                continue
            ranked.append([k, round(ratio, 3)])
        if not ranked:
            continue
        shapes[q] = {
            "n": n,
            "n_corpus": src_counts[q].get("corpus", 0),
            "n_exec": src_counts[q].get("exec", 0),
            "keys": ranked[:MAX_KEYS],
        }
    # ── 분열 후보: 한 슬롯을 두 이름이 나눠 가진 자리 ──────────────────────────
    # 신호 = **함께 온 적이 한 번도 없는** 빈출 키 쌍(상호배타). 같은 자리를 다투는
    # 두 이름이면 한 호출에 같이 오지 않는다(ticker/symbol). 어느 쪽이 정규인지는
    # 여기서 정하지 않는다 — 자동 접기는 몸이 세계에 이름을 붙이는 짓이다. 신고만.
    split = []
    for q, cnt in key_counts.items():
        if "#" in q or n_samples[q] < 20:
            continue
        n = n_samples[q]
        freq = [(k, c) for k, c in cnt.items() if 0.15 <= c / n <= 0.9]
        for i, (a, ca) in enumerate(freq):
            for b, cb in freq[i + 1:]:
                # ① 한 번도 같이 오지 않았고(상호배타) ② 둘이 호출을 거의 다 덮는다(분할).
                # ②가 없으면 그냥 '서로 다른 선택 인자'다 — region_code/limit 같은 잡음.
                if pair_counts[q].get(tuple(sorted((a, b))), 0) == 0 and (ca + cb) / n >= 0.8:
                    split.append({"action": q, "keys": [a, b], "counts": [ca, cb], "n": n})
    split.sort(key=lambda d: -min(d["counts"]))

    # ── 교재 없는 실행 키 — 두 부류를 섞지 않는다 ──────────────────────────────
    # ★2026-08-23 교정: 처음엔 이걸 통째로 "인자 오류율 대리 지표"라 불렀는데 거짓이었다.
    # [sense:search_ddg]{query:} 163건은 **오류가 아니라** 교재가 그 액션을 한 번도 안
    # 가르친 것이다(그 액션의 코퍼스 예문 0건). 갈라서 센다:
    #   ⓐ 교재 공백  = 그 액션 자체가 코퍼스에 없다 → 시드 대기열의 재료(모델은 옳게 쓰고 있다)
    #   ⓑ 발명 후보  = 그 액션은 코퍼스에 있는데 *이 키만* 교재에 없다 → 인자 오류율 대리 지표
    #   ⓒ 은퇴·환각 이름 = 카탈로그 밖 액션 — ⓐ에 섞으면 '교재 공백'이 부풀어 거짓이 된다
    #     (08-23 실측: search_ddg/naver/gnews 옛 이름 호출 ~330건이 ⓐ의 72% 였다. 마지막 호출 08-08).
    gap, invented, exec_key_total = [], [], 0
    retired_n = 0
    for q, per_key in key_src.items():
        if "#" in q:
            continue
        if known and q not in known:
            retired_n += sum(srcs.get("exec", 0) for srcs in per_key.values())
            continue
        taught_action = src_counts[q].get("corpus", 0) > 0
        for k, srcs in per_key.items():
            exec_n = srcs.get("exec", 0)
            if not exec_n:
                continue
            exec_key_total += exec_n
            if srcs.get("corpus"):
                continue
            (invented if taught_action else gap).append({"action": q, "key": k, "exec": exec_n})
    for lst in (gap, invented):
        lst.sort(key=lambda d: -d["exec"])
    gap_n = sum(d["exec"] for d in gap)
    invented_n = sum(d["exec"] for d in invented)
    rate = round(invented_n / exec_key_total, 4) if exec_key_total else 0.0
    print(f"분열 후보 {len(split)}건" + (f" (상위: " + ", ".join(
        f"{d['action']} {d['keys'][0]}/{d['keys'][1]}" for d in split[:4]) + ")" if split else ""))
    print(f"ⓐ 교재 공백 {gap_n}건({len(gap)}종) — 코퍼스에 없는 액션을 실사용이 쓴다(시드 재료)")
    print(f"ⓒ 은퇴·환각 이름 호출 {retired_n}건 — 카탈로그 밖(분모·ⓐ에서 제외)")
    print(f"ⓑ 발명 후보 {invented_n}/{exec_key_total} = {rate * 100:.1f}% ({len(invented)}종) "
          f"— 교재가 있는 액션에 교재 없는 키. ★인자 오류율 대리 지표(낮을수록 좋다)")

    return shapes, dict(parse_fail=parse_fail, truncated=trunc, malformed=malformed,
                        corpus=len(corpus), exec=len(execs), unknown_actions=unknown,
                        folded=sum(folded.values()),
                        split_candidates=split[:40],
                        invented_keys={"n": invented_n, "of": exec_key_total, "rate": rate,
                                       "top": invented[:25]},
                        corpus_gap_keys={"n": gap_n, "top": gap[:25]},
                        retired_or_unknown_calls=retired_n)


def _alias_map() -> dict:
    """액션별 {별칭 → 정규 키} — 어휘 데이터(`aliases:` 블록)가 단일 소스.

    별칭은 *관용*이지 *교재*가 아니다 — 카탈로그가 둘 다 광고하면 언어가 두 이름을 가르친다.
    선언된 별칭은 정규 키로 접어서 센다(호출은 계속 둘 다 통과 — ibl_routing._normalize_param_aliases)."""
    out = {}
    try:
        import yaml
        data = yaml.safe_load((ROOT / "data" / "ibl_nodes.yaml").read_text(encoding="utf-8"))
        for n, nd in (data.get("nodes", data) or {}).items():
            for a, ad in ((nd or {}).get("actions") or {}).items():
                al = (ad or {}).get("aliases")
                if isinstance(al, dict):
                    out[f"{n}:{a}"] = {alt: canon for canon, alts in al.items() for alt in (alts or [])}
    except Exception as e:
        print(f"[경고] 별칭 선언 읽기 실패 — 접지 않고 진행: {e}")
    return out


def _known_actions() -> set:
    try:
        import yaml
        data = yaml.safe_load((ROOT / "data" / "ibl_nodes.yaml").read_text(encoding="utf-8"))
        nodes = data.get("nodes", data) or {}
        return {f"{n}:{a}" for n, nd in nodes.items() for a in ((nd or {}).get("actions") or {})}
    except Exception as e:
        print(f"[경고] 카탈로그 읽기 실패 — 제외 없이 진행: {e}")
        return set()


def main():
    min_ratio = 0.05
    if "--min-ratio" in sys.argv:
        min_ratio = float(sys.argv[sys.argv.index("--min-ratio") + 1])
    shapes, meta = observe(min_ratio)
    doc = {
        "_comment": ("GENERATED by scripts/ibl_param_sweep.py — 교재(코퍼스)+실행(episode_log) 실측 인자 키. "
                     "직접 수정 금지. ibl_access 가 카탈로그 줄에 ⟨인자: …⟩ 로 붙인다. "
                     "선언이 아니라 관측(쓰인 흔적)이다 — 비율은 그 액션 호출 중 그 키가 함께 온 비율."),
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "always_ratio": ALWAYS_RATIO,
        "sources": meta,
        "shapes": dict(sorted(shapes.items())),
    }
    if "--dry" in sys.argv:
        print(json.dumps({k: v for k, v in list(doc["shapes"].items())[:12]}, ensure_ascii=False, indent=1))
        return
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    acts = sum(1 for k in shapes if "#" not in k)
    print(f"관측 액션 {acts}개 · op 변이 {len(shapes) - acts}개 → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
