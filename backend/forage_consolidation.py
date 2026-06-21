"""forage_consolidation.py — 포식 기억 정리 패스 (심층메모리 정리의 *공간* 짝).

증류(입력, agent_cognitive._distill_forage_memory)의 배치/오프라인 짝이다. 증류는
"방금 끝난 한 포식"만 보지만, 정리는 축적된 지도 전체를 보고 *의미적 근접중복*을
청소한다 — 같은 디스크를 여러 번 포식하면 약간 다른 표현의 항목이 쌓이는 드리프트.

설계(memory_consolidation 과 동형):
- 기계 단계(병합 적용·LRU 가지치기·카덴스)는 forage_memory 가 담당 (무LLM, 싸다)
- 의미 병합 판단만 경량 AI에 위임 — 근접중복 후보 중 '진짜 같은 지도 지식'만 병합
- self-check(run_maintenance_bundle)에 합류하되 내부 24h 카덴스 게이트로 자기 페이싱
- ★surface 표식 항목은 후보에서 제외(필터버블 반대힘 보호 — merge_entries 도 이중 거부)
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List

CADENCE_HOURS = 24        # 정리 최소 간격
MIN_ROWS_FOR_MERGE = 6    # 이 미만이면 병합 스킵 (가지치기만)
MAX_GROUPS = 10           # 한 사이클 LLM 병합 그룹 상한 (비용 가드)


def _is_due(force: bool = False) -> bool:
    if force:
        return True
    import forage_memory as FM
    last = FM.get_meta("last_consolidated")
    if not last:
        return True
    try:
        return datetime.now() - datetime.fromisoformat(last) >= timedelta(hours=CADENCE_HOURS)
    except ValueError:
        return True


def _parse_merges(resp: str, valid_ids: set) -> List[Dict]:
    if not resp:
        return []
    rc = resp.strip()
    if rc.startswith("```"):
        rc = rc.split("\n", 1)[-1]
        if rc.endswith("```"):
            rc = rc[:-3]
        rc = rc.strip()
    try:
        data = json.loads(rc)
    except json.JSONDecodeError:
        return []
    merges = data.get("merges", []) if isinstance(data, dict) else []
    out = []
    for m in merges:
        keep = m.get("keep_id")
        drops = [d for d in (m.get("drop_ids") or []) if d in valid_ids and d != keep]
        if keep not in valid_ids or not drops:
            continue
        out.append({**m, "keep_id": keep, "drop_ids": drops})
    return out


def _merge_map_llm(body: str, items: List[Dict], today: str) -> List[Dict]:
    """이 포식 공간(디스크/코드레포) 지도 항목 중 근접중복 묶음을 경량 AI로 판정."""
    from consciousness_agent import lightweight_ai_call
    # 공간 종류에 맞춘 명칭(code:<repo> 면 코드, 아니면 디스크).
    space_word = "코드레포" if str(body).startswith("code") else "디스크"
    locus_word = "디렉토리·모듈" if str(body).startswith("code") else "폴더"
    listing = "\n".join(
        f'- id={it["id"]} [{it["kind"]}] {it["locus"]}: {(it.get("claim") or "")[:200]}'
        for it in items
    )
    prompt = f"""아래는 한 {space_word}('{body}')에 대해 누적된 포식 지도 항목들이다. 오늘은 {today}.
같은 {space_word}를 여러 번 뒤지며 *같은 지도 지식*이 약간 다른 표현으로 중복 누적됐을 수 있다.

{listing}

'정확히 같은 공간 지식'을 가리키는 것끼리만 병합하라:
- kind 가 다르거나(identity vs dead_branch 등) 서로 다른 {locus_word}·다른 사실이면 병합 금지.
- 병합 시 가장 구체적·정확한 하나로 정규화(claim). dead_branch면 prune_reason 유지.
- prior_class 는 structural({locus_word} 동질·싸게 재검증) 또는 semantic(의미/정체 주장).
- 애매하면 병합하지 마라(과병합은 지식 손실).

JSON으로만 응답:
{{"merges":[{{"keep_id":<남길 id>,"drop_ids":[<삭제 id들>],"claim":"<정규본>","prior_class":"structural|semantic","prune_reason":"(dead_branch면)"}}]}}
병합할 게 없으면 {{"merges":[]}}."""
    resp = lightweight_ai_call(
        prompt=prompt,
        system_prompt="포식 지도 병합 판정기. 같은 공간 지식만 병합. JSON으로만.")
    return _parse_merges(resp, {it["id"] for it in items})


def _merge_owner_llm(items: List[Dict], today: str) -> List[Dict]:
    """주인모델 항목 중 근접중복(같은 facet의 같은 사실)을 병합 판정."""
    from consciousness_agent import lightweight_ai_call
    listing = "\n".join(
        f'- id={it["id"]} [{it["facet"]}]: {(it.get("value") or "")[:200]}'
        for it in items
    )
    prompt = f"""아래는 주인(사용자) 모델로 누적된 항목들이다. 오늘은 {today}.
여러 포식에서 *같은 사실*이 약간 다른 표현으로 중복됐을 수 있다.

{listing}

'같은 facet 의 같은 사실'끼리만 병합하라(다른 분야·다른 사실·다른 facet 은 금지).
병합 시 가장 정확·포괄적인 하나로 정규화(value). 애매하면 병합하지 마라.

JSON으로만 응답:
{{"merges":[{{"keep_id":<id>,"drop_ids":[<id들>],"value":"<정규본>","prior_class":"semantic|structural"}}]}}
없으면 {{"merges":[]}}."""
    resp = lightweight_ai_call(
        prompt=prompt,
        system_prompt="주인모델 병합 판정기. 같은 사실만 병합. JSON으로만.")
    return _parse_merges(resp, {it["id"] for it in items})


def run_forage_consolidation(force: bool = False) -> Dict:
    """포식 기억 정리 — 카덴스 게이트 → 몸별 지도 병합 + 주인모델 병합 → LRU 가지치기.

    self-check(run_maintenance_bundle)에 합류. 24h 카덴스라 6h마다 호출돼도 하루 한 번만
    실제 정리. dirty 판단은 단순 카덴스(증류가 잦지 않아 충분)."""
    import forage_memory as FM
    if not _is_due(force):
        return {"skipped": "cadence"}

    stats = {"bodies": 0, "map_merged": 0, "map_dropped": 0,
             "owner_merged": 0, "owner_dropped": 0, "pruned_map": 0, "pruned_owner": 0}
    today = datetime.now().date().isoformat()
    bodies = FM.list_bodies()

    for body in bodies:
        try:
            cand = FM.merge_candidates(body)
        except Exception as e:
            print(f"[포식정리] 후보 수집 실패 {body} (스킵): {e}")
            continue
        map_items = cand.get("map", [])
        if len(map_items) >= MIN_ROWS_FOR_MERGE:
            try:
                groups = _merge_map_llm(body, map_items, today)[:MAX_GROUPS]
            except Exception as e:
                print(f"[포식정리] map 병합 판정 실패 {body} (스킵): {e}")
                groups = []
            for g in groups:
                fields = {"claim": (g.get("claim") or "").strip()}
                if g.get("prior_class"):
                    fields["prior_class"] = g["prior_class"]
                if g.get("prune_reason"):
                    fields["prune_reason"] = g["prune_reason"]
                if not fields["claim"]:
                    continue
                r = FM.merge_entries(table="forage_map", keep_id=g["keep_id"],
                                     drop_ids=g["drop_ids"], fields=fields)
                if r.get("success"):
                    stats["map_merged"] += 1
                    stats["map_dropped"] += r["dropped"]
        try:
            pr = FM.prune_cap(body=body)
            stats["pruned_map"] += pr.get("map", 0)
            stats["pruned_owner"] += pr.get("owner", 0)
        except Exception as e:
            print(f"[포식정리] 가지치기 실패 {body} (스킵): {e}")
        stats["bodies"] += 1

    # 주인모델은 전역 — 한 번만 (몸 없어도 owner 만 있을 수 있음)
    try:
        owner_items = [o for o in FM.recall(body=None, limit=200).get("owner", [])
                       if not o.get("surface_flag")]
        if len(owner_items) >= MIN_ROWS_FOR_MERGE:
            groups = _merge_owner_llm(owner_items, today)[:MAX_GROUPS]
            for g in groups:
                val = (g.get("value") or "").strip()
                if not val:
                    continue
                fields = {"value": val}
                if g.get("prior_class"):
                    fields["prior_class"] = g["prior_class"]
                r = FM.merge_entries(table="owner_model", keep_id=g["keep_id"],
                                     drop_ids=g["drop_ids"], fields=fields)
                if r.get("success"):
                    stats["owner_merged"] += 1
                    stats["owner_dropped"] += r["dropped"]
    except Exception as e:
        print(f"[포식정리] owner 병합 실패 (스킵): {e}")

    FM.set_meta("last_consolidated", datetime.now().isoformat())
    if stats["map_merged"] or stats["owner_merged"] or stats["pruned_map"]:
        print(f"[포식정리] map 병합 {stats['map_merged']}(삭제 {stats['map_dropped']}) / "
              f"owner 병합 {stats['owner_merged']}(삭제 {stats['owner_dropped']}) / "
              f"가지치기 map {stats['pruned_map']} owner {stats['pruned_owner']}")
    return stats


if __name__ == "__main__":
    import sys
    out = run_forage_consolidation(force="--force" in sys.argv)
    print(json.dumps(out, ensure_ascii=False, indent=2))
