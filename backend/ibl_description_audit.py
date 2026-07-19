"""IBL 액션 설명(description) 의미 드리프트 점검 — `--check`의 *의미* 판.

`build_ibl_nodes.py --check`는 src↔tool.json↔handler의 *구조*(액션·op·param 키)를
AST로 정확 비교한다. 그러나 `description:`은 자유 자연어라 어떤 게이트도 그 *내용*이
현재 동작·어휘와 맞는지 보지 않는다 → 동작이 바뀌어도(예: 통화 records/table→items)
설명 산문은 조용히 stale해진다(좀비 어휘, architecture_harness_sturdiness 4균열).

이 모듈은 그 빈틈을 메운다:
  1. (AI 0) 결정적 교차참조 검사 — 설명이 가리키는 `[node:action]`이 실재하는가.
  2. (경량 LLM) 의미 드리프트 — 정본 어휘 앵커에 비춰 각 설명이 ①은퇴 어휘·통화 모순
     ②끊긴 액션 참조 ③returns/op와 어긋난 주장 을 쓰는지 플래그.

비용: 주간 카덴스(run_maintenance_bundle에 합류, 자기 페이싱). 경량 티어(role=background).
구조 `--check`가 커밋을 *막는다*면, 이건 self-check가 *깃발만 꽂는다* — 판단·수정은 사람.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

try:
    from logging_utils import get_logger
    logger = get_logger(__name__)
except Exception:  # pragma: no cover - 독립 실행 폴백
    import logging
    logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent
_NODES_YAML = _ROOT / "data" / "ibl_nodes.yaml"
_STATE_PATH = _ROOT / "data" / ".ibl_desc_audit_state.json"
_FLAGS_PATH = _ROOT / "data" / "ibl_description_flags.json"

CADENCE_HOURS = 168        # 주 1회 (구조 --check는 커밋마다, 의미는 비싸니 주간)
_BATCH = 30                # LLM 호출당 액션 수

# 정본 어휘 앵커 — 설명이 이 모델과 어긋나면 드리프트.
# (단일 소스: 통화/노드 모델이 바뀌면 여기 한 줄만 고친다.)
_VOCAB_ANCHOR = """\
[현재 IBL 어휘 — 이 모델이 진실이다]
- 통화는 하나뿐: `items` = [{…열린 dict…}] (목록형). 옛 records/table/document 표현은 전부 items로 흡수·은퇴됨. 설명이 "records 통화"·"table 통화"·"두 통화" 같은 옛 모델을 쓰면 드리프트다.
- 액션의 역할은 `returns:`로 선언: items(통화 냄) / transform(통화→통화 변환자) / scalar(단일값) / effect(행동·종착).
- 6개 노드만 존재: sense(감각·조회) / self(자기·관리) / limbs(손발·기기) / others(타인·소통) / engines(미디어 생성) / table(표·통화 변환 문법). 다른 노드명은 없다.
- 변환자(returns:transform)는 통화를 받아 같은 통화를 낸다(closure) → `>>` 조합.
- 변환자에는 단항(입력 1개)과 **이항**(입력 2개, `&` 병렬로 공급: join/union/merge)이 있다. "두 입력"·"두 items"는 이항 변환자의 *정상* 표현이다 — 통화가 둘이라는 뜻이 아니므로 드리프트가 아니다.
- "통화는 하나"는 *통화의 종류*가 하나라는 뜻이지, 한 번에 입력을 하나만 받는다는 뜻이 아니다.
- 도메인 명사(통계표·스프레드시트·시트·행·차트·문서 등)나 파라미터 이름(rows/sheets/blocks/table=…)은 통화 모델 주장이 아니다 — "records 통화"·"table 통화"·"두 통화"처럼 옛 *통화 모델*을 명시할 때만 currency 드리프트다.
- returns:effect/scalar 액션이 결과를 `>>`로 다음 액션에 넘기라고 안내하는 것은 transform 주장이 아니다(파이프 사용법 안내일 뿐). op 분기 액션에서 단건 op의 응답 형태를 부연하는 것도 returns와의 모순이 아니다.
"""


# ───────────────────────── 액션 로드 ─────────────────────────

def _load_actions() -> List[Dict]:
    """ibl_nodes.yaml에서 액션을 (node, action, fullname, description, returns, ops)로 평탄화."""
    import yaml
    if not _NODES_YAML.exists():
        return []
    data = yaml.safe_load(_NODES_YAML.read_text(encoding="utf-8")) or {}
    nodes = data.get("nodes", data)  # 구조: {meta, nodes:{node:{actions}}}
    out: List[Dict] = []
    for node, node_def in nodes.items():
        if not isinstance(node_def, dict):
            continue
        actions = node_def.get("actions") or {}
        if not isinstance(actions, dict):
            continue
        for name, adef in actions.items():
            if not isinstance(adef, dict):
                continue
            ops_block = adef.get("ops") or {}
            op_names = list((ops_block.get("values") or {}).keys()) if isinstance(ops_block, dict) else []
            out.append({
                "node": node,
                "action": name,
                "fullname": f"{node}:{name}",
                "description": str(adef.get("description") or "").strip(),
                "returns": adef.get("returns"),
                "ops": op_names,
            })
    return out


# ──────────────── 1) 결정적 교차참조 검사 (AI 0) ────────────────

def check_broken_crossrefs(actions: List[Dict]) -> List[Dict]:
    """설명이 `[node:action]` 또는 `node:action` 형태로 가리키는 액션이 실재하는지 검사.

    끊긴 교차참조(예: 가리키던 액션이 개명·삭제됨)를 LLM 없이 잡는다. bare 액션명은
    오탐이 커서 제외 — 명시적 노드:액션 형태만 본다.
    """
    valid = {a["fullname"] for a in actions}
    valid_nodes = {a["node"] for a in actions}
    flags: List[Dict] = []
    ref_re = re.compile(r"\[?([a-z]+):([a-z_]+)\]?")
    for a in actions:
        desc = a["description"]
        for m in ref_re.finditer(desc):
            node, act = m.group(1), m.group(2)
            if node not in valid_nodes:
                continue  # node:action 패턴이 아닌 우연한 콜론(예: "op: ...") 제외
            full = f"{node}:{act}"
            if full not in valid and full != a["fullname"]:
                flags.append({
                    "action": a["fullname"],
                    "kind": "broken_crossref",
                    "issue": f"설명이 가리키는 [{full}] 가 존재하지 않음 (개명·삭제?)",
                })
    return flags


# ──────────────── 2) 의미 드리프트 (경량 LLM) ────────────────

_SYS_PROMPT = (
    "너는 IBL 액션 카탈로그의 *설명 산문*이 현재 어휘·동작과 맞는지 감사하는 점검기다. "
    "설명이 stale(은퇴 어휘)·모순·끊긴 참조를 쓸 때만 플래그한다. 멀쩡하면 침묵한다. "
    "추측 금지 — 명백한 불일치만. 출력은 JSON 배열, 그 외 텍스트 금지."
)


def _audit_batch_llm(batch: List[Dict], valid_names: List[str]) -> List[Dict]:
    """한 배치의 설명을 경량 LLM으로 감사. 플래그된 항목만 반환."""
    from consciousness_agent import lightweight_ai_call

    lines = []
    for a in batch:
        ops = f" ops={a['ops']}" if a["ops"] else ""
        lines.append(f"- {a['fullname']} (returns:{a['returns']}{ops})\n    desc: {a['description']}")
    listing = "\n".join(lines)

    prompt = (
        f"{_VOCAB_ANCHOR}\n"
        f"[감사 대상 설명들]\n{listing}\n\n"
        "각 설명을 위 어휘 앵커에 비춰 *의미*만 검사하라. 플래그 기준(둘뿐):\n"
        "  1. currency: 옛 통화 어휘(records/table 통화·두 모양 등) 사용 — 현재는 items 하나. (단, 이항 변환자의 '두 입력'은 정상. "
        "'items 통화'·'통합 통화 items'는 *현행* 어휘이므로 절대 플래그하지 마라.)\n"
        "  2. contradiction: returns/ops와 *명백히* 어긋난 주장(예: returns:scalar인데 '목록 반환'). 애매하면 플래그하지 마라. "
        "(op 분기 액션에서 '단건 op는 해당 객체 응답'처럼 설명이 op별 반환 차이를 *명시*하는 것은 모순이 아니라 정확한 문서다 — returns는 대표 op 기준의 액션 단위 선언일 뿐이다.)\n"
        "★다른 액션을 가리키는 교차참조의 존재 여부는 검사하지 마라(별도 결정적 검사가 한다). 모르면 침묵하라 — 오탐은 검사의 신뢰를 깎는다.\n"
        "문제 있는 항목만 JSON 배열로: "
        '[{"action":"node:name","kind":"currency|contradiction","issue":"한 줄 근거"}]. '
        "문제 없으면 빈 배열 []. JSON만 출력."
    )

    resp = lightweight_ai_call(prompt, system_prompt=_SYS_PROMPT, role="background")
    if not resp:
        return []
    return _parse_flags(resp)


def _parse_flags(resp: str) -> List[Dict]:
    """LLM 응답에서 JSON 배열을 관대하게 추출."""
    txt = resp.strip()
    # 코드펜스 제거
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt, flags=re.MULTILINE).strip()
    m = re.search(r"\[.*\]", txt, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return []
    out = []
    for item in arr if isinstance(arr, list) else []:
        if isinstance(item, dict) and item.get("action") and item.get("issue"):
            out.append({
                "action": str(item["action"]),
                "kind": str(item.get("kind", "drift")),
                "issue": str(item["issue"])[:200],
            })
    return out


def audit_descriptions(use_llm: bool = True, limit: Optional[int] = None) -> Dict:
    """전체 설명 감사 — 결정적 교차참조 + (옵션) 경량 LLM 의미 드리프트.

    Returns: {"total": N, "flags": [...], "llm": bool}
    """
    actions = _load_actions()
    if limit:
        actions = actions[:limit]
    valid_names = [a["fullname"] for a in actions]

    flags = check_broken_crossrefs(actions)

    if use_llm:
        for i in range(0, len(actions), _BATCH):
            batch = actions[i:i + _BATCH]
            try:
                flags.extend(_audit_batch_llm(batch, valid_names))
            except Exception as e:
                logger.warning(f"[DescAudit] 배치 {i//_BATCH} LLM 실패 (무시): {e}")

    # 액션별 dedup (같은 액션 여러 kind는 보존하되 동일 issue만 합침)
    seen = set()
    deduped = []
    for f in flags:
        key = (f["action"], f["kind"], f["issue"][:40])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)

    return {"total": len(actions), "flags": deduped, "llm": use_llm}


# ──────────────── 카덴스 게이트 + self-check 합류 ────────────────

def _should_run(force: bool = False) -> bool:
    if force:
        return True
    try:
        st = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        last = st.get("last_run")
        if not last:
            return True
        return datetime.now() - datetime.fromisoformat(last) >= timedelta(hours=CADENCE_HOURS)
    except Exception:
        return True


def _save_state(result: Dict):
    try:
        _STATE_PATH.write_text(json.dumps({
            "last_run": datetime.now().isoformat(),
            "flag_count": len(result.get("flags", [])),
        }, ensure_ascii=False), encoding="utf-8")
        _FLAGS_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[DescAudit] 상태 저장 실패 (무시): {e}")


def run_description_drift_check(force: bool = False) -> Dict:
    """주간 카덴스 게이트로 설명 의미 드리프트를 감사하고 self_checks 형식 1건을 반환.

    run_maintenance_bundle(self-check 사이클)에 합류한다. 6h마다 호출돼도 주 1회만 실제 실행.
    플래그는 data/ibl_description_flags.json + self_checks(__ibl_health__:description_drift)에 남는다.
    """
    if not _should_run(force):
        return {"skipped": "cadence"}

    result = audit_descriptions(use_llm=True)
    _save_state(result)

    flags = result["flags"]
    note = None
    if flags:
        head = "; ".join(f"{f['action']}({f['kind']})" for f in flags[:6])
        note = f"{len(flags)}건 드리프트: {head}"
        logger.warning(f"[DescAudit] 설명 드리프트 {len(flags)}건 — {_FLAGS_PATH.name} 참조")
    else:
        logger.info(f"[DescAudit] 설명 {result['total']}개 감사 — 드리프트 0")

    return {
        "node": "__ibl_health__",
        "action": "description_drift",
        "success": len(flags) == 0,
        "response_ms": 0,
        "data_quality": "ok" if not flags else "description_drift",
        "error_message": note,
        "flags": flags,
    }


if __name__ == "__main__":
    sys.path.insert(0, str(_ROOT / "backend"))
    use_llm = "--no-llm" not in sys.argv
    lim = None
    for a in sys.argv:
        if a.startswith("--limit="):
            lim = int(a.split("=", 1)[1])
    res = audit_descriptions(use_llm=use_llm, limit=lim)
    print(f"감사 {res['total']}개 액션 (LLM={res['llm']}) → 플래그 {len(res['flags'])}건")
    for f in res["flags"]:
        print(f"  [{f['kind']:14}] {f['action']:24} {f['issue']}")
