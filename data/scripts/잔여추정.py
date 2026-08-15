#!/usr/bin/env python3
"""잔여추정 — 탐색 잔여(elusion) 측정. 구 [self:residual] 액션의 스크립트판 (2026-08-15 어휘 은퇴).

"거기 없음" vs "덜 봤음"을 측정으로 가른다. 판단(없음/덜봄/전부)은 AI 몫 — 이 스크립트는 숫자만.

사용 ([self:script]{op:"run", id:"잔여추정", args:{...}}):
  estimate (기본): {"relevant": 관련 수, "sampled": 표본 크기, "unseen": 미관측 모집단}
      → Wilson 95% CI 로 미관측 중 누락 추정.
  sample: {"mode":"sample", "n":20, "q":"검색어", "kind":"any", "path":"...", "seen":[...]}
      → 미관측 균일 무작위 표본 (indiebizOS backend/file_index 필요 — 이 몸에서만).
출력: items 통화 JSON (stdout).
"""
import json
import math
import sys


def wilson(r: int, n: int, z: float = 1.96):
    """Wilson score 95% 신뢰구간 (r 성공 / n 시행)."""
    if n <= 0:
        return (0.0, 0.0, 1.0)
    p = r / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (p, max(0.0, center - half), min(1.0, center + half))


def run_estimate(args):
    r = int(args.get("relevant", 0))
    n = int(args.get("sampled") or args.get("n") or 0)
    M = int(args.get("unseen") or args.get("pool") or 0)
    if n <= 0:
        return {"success": False, "error": "sampled(n)는 1 이상"}
    p, lo, hi = wilson(r, n)
    return {
        "success": True, "mode": "estimate",
        "relevant_in_sample": r, "sampled": n, "unseen": M,
        "rate": round(p, 4), "rate_ci95": [round(lo, 4), round(hi, 4)],
        "missed_estimate": round(p * M, 1),
        "missed_ci95": [round(lo * M, 1), round(hi * M, 1)],
        "items": [{"title": f"미관측 {M}개 중 누락 점추정 {round(p*M,1)}개 (95% 상한 {round(hi*M,1)}개)",
                   "meta": f"표본 {n}개 중 관련 {r}개 · 비율 {round(p,4)} [{round(lo,4)}, {round(hi,4)}]",
                   "summary": "상한이 목표(전부 찾기/없음 단언) 대비 작으면 커버, 크면 더 볼 것 — 판단은 목표에 달렸다."}],
    }


def run_sample(args):
    """미관측 표본 — indiebizOS backend/file_index 의존 (이 몸에서만)."""
    import os
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    be = os.path.join(repo, "backend")
    if be not in sys.path:
        sys.path.insert(0, be)
    try:
        import boot_paths  # noqa: F401
        import file_index
    except Exception as e:
        return {"success": False, "error": f"file_index 불가(이 몸에 backend 없음?): {e}"}
    import random
    seen = args.get("seen") or []
    if isinstance(seen, str):
        seen = [seen]
    seen_set = {os.path.abspath(os.path.expanduser(str(p))) for p in seen}
    n = max(1, int(args.get("n") or 20))
    pool = file_index.candidate_paths(
        kind=args.get("kind") or "any", q=args.get("q") or args.get("query"),
        start=args.get("start"), end=args.get("end"),
        ext=args.get("extension") or args.get("ext"), path=args.get("path"))
    unseen = [p for p in pool if os.path.abspath(p) not in seen_set]
    k = min(n, len(unseen))
    picked = random.sample(unseen, k) if k else []
    return {"success": True, "mode": "sample", "pool_total": len(pool),
            "seen": len(seen_set), "unseen": len(unseen), "sample_size": k,
            "items": [{"title": p} for p in picked],
            "note": f"표본을 열어 관련 수를 센 뒤 args {{relevant, sampled:{k}, unseen:{len(unseen)}}} 로 다시 실행(estimate)."}


def main():
    try:
        args = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        args = {}
    mode = (args.get("mode") or "estimate").strip().lower()
    out = run_sample(args) if mode == "sample" else run_estimate(args)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
