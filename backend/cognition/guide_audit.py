"""가이드 의미 순찰 — `--check` 가 못 보는 *산문*의 부패를 주간으로 훑는다.

## 왜 있나

가이드 위생은 두 층이다:

- **구조**(빌드, `iblbuild_validators.validate_guide_wiring`): 유령 등재·끊긴 코드 경로·
  죽은 어휘 참조·고아. 기계가 정확히 안다.
- **의미**(여기): 전제가 뒤집혔는가, 다른 가이드에 흡수됐는가. 기계가 못 본다.

2026-08-17 정리에서 가장 해로웠던 것이 정확히 두 번째였다 — `business.md` 가
*"이 도메인은 액션을 미리 정의하지 않고 DB 직접 접근으로 처리한다"* 고 첫 문단에서
선언하고 있었다. 어휘가 생기기 전(~06-12) 이야기인데, 검색에 걸리는 가이드가
**AI 에게 어휘를 쓰지 말라고 가르치고** 있었다. 죽은 참조 스캔으로는 절대 못 잡는다
(문법적으로 멀쩡한 산문이다).

`ibl_description_audit`(액션 desc 의 의미 감사)의 형제다. desc 는 200자인데 그 desc 를
설명하는 가이드는 10~30배 길이이고, 그동안 순찰이 0이었다.

## 무엇부터 보나 — 신선도 순

전수는 비싸다. `guide_registry.all_freshness()` 가 **오래됐고 무수정 사용이 없는 것**을
앞에 놓으므로, 매 회차 그 앞에서부터 몇 개만 본다. 나이만으로 고르지 않는 이유:
67일 된 가이드가 그동안 12번 무수정으로 쓰였으면 오히려 검증된 쪽이다.

## 규율 — 판정 불가는 무결이 아니다

응답을 못 읽으면 빈 결과가 아니라 `unchecked` 로 남긴다. 깃발 0 이 '깨끗함'인지
'못 봤음'인지 구별할 수 없으면 이 점검은 조용할수록 안심되는 게 아니라 눈이 먼 것이다.
(`ibl_description_audit` 에서 확립된 규율을 그대로 상속.)

**깃발이지 판결이 아니다.** 무엇을 고치고 무엇을 묘비로 남길지는 사람이 정한다 —
2026-08-17 에 `remotion.md` 의 운명이 실제로 사용자 판정으로 뒤집혔다.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parents[2] / "data"
GUIDES_DIR = DATA_PATH / "guides"
_STATE_PATH = DATA_PATH / "guide_audit_state.json"
_FLAGS_PATH = DATA_PATH / "guide_audit_flags.json"

CADENCE_HOURS = 168          # 주 1회
PER_RUN = 6                  # 회차당 감사할 가이드 수 (신선도 낮은 순)
HEAD_CHARS = 1800            # 가이드 머리 — 전제는 거의 항상 앞에 있다(business.md 실측)

_SYS = "당신은 문서 감사자다. 확실한 것만 말하고, 애매하면 침묵한다. JSON만 출력한다."


class _AuditUnreadable(Exception):
    """응답을 읽지 못했다 — '깨끗함'이 아니라 '판정 불가'."""


def _live_actions() -> Dict[str, str]:
    """현재 살아있는 액션 → desc."""
    try:
        import yaml
        d = yaml.safe_load((DATA_PATH / "ibl_nodes.yaml").read_text(encoding="utf-8"))
        nodes = d.get("nodes", d)
        return {
            f"{n}:{a}": (av.get("description") or "")
            for n, v in nodes.items() if isinstance(v, dict)
            for a, av in (v.get("actions") or {}).items() if isinstance(av, dict)
        }
    except Exception as e:
        logger.warning(f"[GuideAudit] 어휘 로드 실패: {e}")
        return {}


def _guide_catalog() -> List[Dict]:
    """guide_db 의 이름·설명 — 흡수(중복) 판정의 재료."""
    try:
        entries = json.loads((DATA_PATH / "guide_db.json").read_text(encoding="utf-8"))["guides"]
        return [{"file": Path(str(e.get("file") or "")).name,
                 "name": e.get("name"), "description": (e.get("description") or "")[:120]}
                for e in entries]
    except Exception:
        return []


def _pick(limit: int) -> List[Dict]:
    """신선도 낮은 순으로 감사 대상 선정."""
    try:
        from guide_registry import all_freshness
        return all_freshness()[:limit]
    except Exception as e:
        logger.warning(f"[GuideAudit] 신선도 조회 실패 — 이름순 폴백: {e}")
        return [{"guide": p.name, "age_days": None, "clean_uses": 0}
                for p in sorted(GUIDES_DIR.glob("*.md"))[:limit]]


def _audit_one(entry: Dict, live: Dict[str, str], catalog: List[Dict]) -> List[Dict]:
    """가이드 하나를 감사. 플래그된 것만 반환. 응답 못 읽으면 _AuditUnreadable."""
    import re
    from consciousness_agent import lightweight_ai_call

    name = entry["guide"]
    try:
        src = (GUIDES_DIR / name).read_text(encoding="utf-8")
    except OSError:
        return []
    head = src[:HEAD_CHARS]

    refs = sorted({f"{m[0]}:{m[1]}" for m in re.findall(r"\[([a-z_]+):([a-z_]+)\]", src)}
                  & set(live))
    desc_lines = "\n".join(f"  {r} :: {live[r][:180]}" for r in refs[:12]) or "  (참조 없음)"
    others = "\n".join(f"  {c['file']}: {c['description']}"
                       for c in catalog if c["file"] != name)[:2000]

    prompt = (
        f"[감사 대상 가이드] {name}\n"
        f"--- 가이드 머리(앞 {HEAD_CHARS}자) ---\n{head}\n"
        f"--- 이 가이드가 부르는 어휘의 *현재* 설명 ---\n{desc_lines}\n"
        f"--- 다른 가이드 목록 ---\n{others}\n\n"
        "두 가지만 검사하라.\n\n"
        "1. **premise** — 가이드의 *전제*가 위 '현재 어휘' 목록과 어긋나는가.\n"
        "   판정 규칙(기계적으로 적용하라):\n"
        "     · '현재 어휘' 목록이 비어 있지 않은데, 가이드가 «전용 액션이 없다» / «액션을 미리 "
        "정의하지 않는다» / «DB 직접 접근·REST 로 처리한다» 는 취지로 *방침*을 선언하면 → premise.\n"
        "     · 가이드가 권하는 주 경로가, 목록에 실재하는 어휘를 두고 그보다 낮은 층(직접 SQL·"
        "raw HTTP·셸)을 기본으로 지시하면 → premise.\n"
        "   세부가 조금 낡은 것은 해당 없음. *방침·전제*가 뒤집힌 경우만.\n\n"
        "2. **superseded** — 다른 가이드가 같은 주제를 더 온전히 다뤄 이 문서가 불필요한가. "
        "주제가 겹치는 정도로는 부족하고, 이 문서 고유의 내용이 사실상 없을 때만.\n"
        "   ★실측 함정·API 특이사항·파라미터 표는 desc 가 못 담는 것이라 *가치*다 — 중복으로 보지 마라.\n\n"
        "1번은 규칙에 걸리면 주저 말고 플래그하라(놓치면 AI 가 몇 달간 틀린 방침을 배운다). "
        "2번은 확실할 때만 — 애매하면 침묵하라.\n"
        '출력: [{"kind":"premise|superseded","issue":"한 줄 근거"}] · 문제 없으면 []. JSON만.'
    )

    resp = lightweight_ai_call(prompt, system_prompt=_SYS, role="guide_audit")
    if not resp:
        raise _AuditUnreadable("빈 응답")
    m = re.search(r"\[.*\]", resp, re.S)
    if not m:
        raise _AuditUnreadable("JSON 배열 못 찾음")
    try:
        arr = json.loads(m.group(0))
    except Exception as e:
        raise _AuditUnreadable(f"JSON 파싱 실패: {e}")
    out = []
    for it in arr if isinstance(arr, list) else []:
        if isinstance(it, dict) and it.get("kind") in ("premise", "superseded"):
            out.append({"guide": name, "kind": it["kind"],
                        "issue": str(it.get("issue") or "")[:200],
                        "age_days": entry.get("age_days"),
                        "clean_uses": entry.get("clean_uses")})
    return out


def audit_guides(limit: int = PER_RUN) -> Dict:
    live = _live_actions()
    catalog = _guide_catalog()
    targets = _pick(limit)
    flags: List[Dict] = []
    unchecked: List[str] = []
    for e in targets:
        try:
            flags.extend(_audit_one(e, live, catalog))
        except _AuditUnreadable as u:
            unchecked.append(f"{e['guide']}({u})")
        except Exception as ex:
            unchecked.append(f"{e['guide']}(오류: {ex})")
    return {
        "total": len(targets),
        "audited": [e["guide"] for e in targets],
        "flags": flags,
        "unchecked": unchecked,
    }


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
            "audited": result.get("audited", []),
        }, ensure_ascii=False), encoding="utf-8")
        _FLAGS_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[GuideAudit] 상태 저장 실패 (무시): {e}")


def run_guide_drift_check(force: bool = False) -> Dict:
    """주간 카덴스로 가이드 산문을 감사하고 self_checks 형식 1건을 반환.

    run_maintenance_bundle 에 합류한다(6h마다 호출돼도 주 1회만 실제 실행).
    """
    if not _should_run(force):
        return {"skipped": "cadence"}

    result = audit_guides()
    _save_state(result)

    flags = result["flags"]
    unchecked = result.get("unchecked") or []
    notes = []
    if flags:
        head = "; ".join(f"{f['guide']}({f['kind']})" for f in flags[:6])
        notes.append(f"{len(flags)}건 가이드 드리프트: {head}")
        logger.warning(f"[GuideAudit] 가이드 드리프트 {len(flags)}건 — {_FLAGS_PATH.name} 참조")
    if unchecked:
        notes.append(f"{len(unchecked)}개 판정 불가 — 이번 회차는 전수 아님")
        logger.warning(f"[GuideAudit] 판정 불가 {len(unchecked)}개 — {_FLAGS_PATH.name} unchecked 참조")
    if not notes:
        logger.info(f"[GuideAudit] 가이드 {result['total']}개 감사 — 드리프트 0")

    # ★판정 불가도 실패다 — 못 본 것을 '이상 없음'으로 보고하면 눈이 먼 것이다.
    return {
        "node": "__ibl_health__",
        "action": "guide_drift",
        "success": not flags and not unchecked,
        "response_ms": 0,
        "data_quality": ("ok" if not flags and not unchecked
                         else "guide_drift" if flags else "audit_incomplete"),
        "error_message": " / ".join(notes) if notes else None,
        "flags": flags,
        "unchecked": unchecked,
    }
