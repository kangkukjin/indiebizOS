"""agg_spec.py — groupby 의 agg 파라미터 정규화(모양 사전).

handler.py 에서 분리(2026-08-27, 1500줄 규칙 — filter 마찰 수리로 한도 초과).
agg 가 취할 수 있는 모양들과 각 모양의 뜻·거절 사유가 전부 여기 산다:

  · 생략 / "count"        → 그룹별 행수 (ep1258: 스칼라 "count" 는 중의성 0)
  · {새열: [op, 원본열]}   → 명시 명명 집계
  · {새열: ["count"]}     → 행수를 새열 이름으로 — count 는 원본열이 필요 없는
                            유일한 op 이라 1원소 리스트가 자연스럽다(ep2114 실측:
                            이 모양이 두 번 거절돼 groupby 를 파이프에서 포기시켰다)
  · {원본열: op}          → 자동 명명 'op_원본열'. op="count" 에 비실존 필드가 오면
                            오타 방어(39회차 계약)로 거절하되, 행수 의도였을 문장에게
                            옳은 모양({k: ["count"]})을 오류문이 그 자리에서 가르친다.
  · dict 아닌 agg         → 정직 거절(조용히 버리면 count 로 위장된다, ⑧′)

내부 명세 op "row_count" = 그룹 행수(원본열 없음). 잎 모듈(형제 import 없음).
"""

_AGG = {"count", "sum", "avg", "min", "max"}


def normalize_agg(agg, dicts, field_missing_error):
    """agg → ([(출력열, op, 원본열)], auto_named, 오류봉투|None).

    field_missing_error: diagnostics._field_missing_error (handler 가 주입 — 잎 유지).
    """
    if isinstance(agg, str) and agg.strip().lower() == "count":
        # 'count' 는 원본열이 필요 없는 유일한 op — agg 생략(그룹별 count)과 같은 뜻
        # (ep1258: 거절→같은 철자 재시도가 두 왕복을 태웠다). 다른 스칼라는 거절 유지.
        agg = None
    specs, auto_named = [], []
    if isinstance(agg, dict):
        for k, v in agg.items():
            if isinstance(v, (list, tuple)) and len(v) == 2:  # {새열: [op, 원본열]}
                specs.append((str(k), str(v[0]).lower(), str(v[1])))
            elif isinstance(v, (list, tuple)) and len(v) == 1 and str(v[0]).lower() == "count":
                specs.append((str(k), "row_count", ""))  # {새열: ["count"]} — 행수 출력명
            else:  # {원본열: op} — 집계열 이름은 'op_원본열' 자동 명명
                specs.append((f"{v}_{k}", str(v).lower(), str(k)))
                auto_named.append(f"{v}_{k}")
    elif agg:
        # dict 아닌 agg("sum:size" 등)를 조용히 버리면 count 로 위장된다(⑧′ 실측)
        return None, None, {
            "success": False,
            "error": f"groupby: agg 는 dict 여야 합니다 — {{원본열: op}} 또는 {{새열명: [op, 원본열]}}, "
                     f"op={'/'.join(sorted(_AGG))}. 예: {{매출: [\"sum\", \"금액\"]}}. 받은 값: {agg!r} "
                     f"(스칼라는 'count' 만 허용 — 원본열이 필요 없는 유일한 op)"}
    for out_col, op, src in specs:
        if op == "row_count":  # 내부 명세(행수) — 원본열이 없으니 아래 검사 대상이 아니다
            continue
        if op not in _AGG:
            return None, None, {"success": False,
                                "error": f"groupby: 알 수 없는 집계 op '{op}' (가능: {'/'.join(sorted(_AGG))})"}
        # 명시 count(field)의 field도 장식이 아니다 — 전 행에 없는 필드는 거절(39회차).
        if not any(src in d for d in dicts):
            err = field_missing_error("groupby", src, dicts)
            if op == "count":
                err["error"] += (f' 원본열 없이 그룹 행수를 새 열 이름으로 내려면 '
                                 f'{{{src}: ["count"]}} (1원소 리스트 형)로 쓰세요.')
            return None, None, err
    if not specs:
        # agg 생략은 행 수다. 명시 count(열)의 non-null 의미와 섞으면 null/부재
        # 그룹이 2행이어도 0으로 나온다(B40-3).
        specs = [("count", "row_count", "")]
    return specs, auto_named, None
