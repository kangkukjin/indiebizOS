"""guide_downscale.py — 가이드 야간 하향 정규화 (수면의 후반부, 2026-09-02)

## 왜 있나

시냅스 항상성 가설: 수면은 낮에 커진 시냅스를 전체적으로 줄여 신호 대 잡음을 회복한다.
우리 야간 통합(증류·재학습·해마 정리)은 **더하기만** 했다 — 가이드는 자라기만 해서 79KB 까지
갔고 사람이 손으로 걷어냈다(2026-08-17 81KB · 09-02 67→21·62→30·79→34KB). 여기가 줄이는 패스다.
정본: docs/COMPONENT_APOPTOSIS_HANDOFF.md §B. component_lifecycle(항목 단위 죽음)의 짝 —
그쪽은 파일을 지우고, 이쪽은 파일 안을 줄인다.

## 무엇을 줄이나 — 세 부류, 우선순위 순

1. **어휘와 어긋난 문장** — 죽은 `[node:action]` 참조(은퇴·제안 문맥은 면제, 빌드 가드와 같은
   기준)·retired_contracts 금지 문구·끊긴 `backend/…py` 경로.
2. **완성 처방** — 자리표 골격이 아닌 완성 문장(no-concrete-sentences 규율). 기계가 못 재므로
   LLM 지시로만 두고, 손실은 3 의 기계 대조가 막는다.
3. **쓰인 흔적 없는 절** — guide_registry.section_uses 가 관찰창 동안 0 인 `##` 절. 단 귀속이
   그 가이드에서 실제로 돌았을 때(`*` 표지 ≥ section_unused_min_turns)만 — 아니면 '미사용'은
   '못 봤음'이다. 삭제가 아니라 **한 줄 요약으로 압축**(절 제목은 남긴다).

## 규율

- **대상 선정**: 예산(guide_budget_bytes) 초과 가이드 상위 N + guide_audit 깃발 가이드.
  예산 안이고 깃발 없는 가이드는 건드리지 않는다(강한 시냅스는 남는다).
- **기계 대조가 관문**: 압축본은 원본의 ①살아 있는 `[node:action]` 참조 집합 ②`##`/`###` 절 제목
  집합 ③백틱 `backend/…py` 경로 집합을 **보존**하고 ④더 짧아야 한다(예산 초과분은 예산 안으로).
  하나라도 어기면 그 회차는 건너뛰고 `unchecked` 로 남긴다 — 판정 불가 ≠ 무결(guide_audit 규율).
- **모델은 압축만 한다**: 무엇을 줄일지의 표식은 기계가 앞에서 세우고, 통과 판정도 기계가 한다.
- 통과 시 `[self:body]{op:commit}` 라벨 `downscale(guide): X 34→22KB` — 사후 검토=커밋 diff.
- 되먹임: guide_feedback 이 압축 뒤 그 가이드에서 사실오류를 고쳤다면(edit_churn 에 잡힌다)
  다음 회차 대상에서 그 가이드는 뒤로 민다 — 과압축의 학습.

주간 카덴스. run_maintenance_bundle 이 guide_audit(6.5) 직후에 부른다(깃발을 입력으로 받기 위해).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "data"
GUIDES_DIR = DATA / "guides"
NODES_PATH = DATA / "ibl_nodes.yaml"
RETIRED_CONTRACTS_PATH = DATA / "retired_contracts.yaml"
AUDIT_FLAGS_PATH = DATA / "guide_audit_flags.json"
STATE_PATH = DATA / "guide_downscale_state.json"
FLAGS_PATH = DATA / "guide_downscale_flags.json"

CADENCE_HOURS = 168
SECTION_WINDOW_DAYS = 60
MAX_GUIDE_CHARS = 60000     # 모델에 보일 본문 상한(예산 36KB 가이드도 통째로 들어간다)

ACTION_RE = re.compile(r"\[([a-z_][a-z0-9_-]*):([a-z_][a-z0-9_-]*)\]")
HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.M)
PATH_RE = re.compile(r"`(backend/[A-Za-z0-9_/]+\.py)`")
EXCUSED_RE = re.compile(r"구 |은퇴|폐지|개명|흡수|승격|부활|아직 없는|가상의|제안|통합|합병|없습니다|아니다|자리표시자")
LIFECYCLE_MARK_RE = re.compile(r"^<!-- lifecycle: candidate since [^\n]*-->\n?", re.M)

_SYS = ("당신은 절차 기억(가이드)의 야간 정리자다. 뜻을 바꾸지 않고 줄인다. "
        "표식된 부류만 줄이고, 어휘 참조·절 제목·경로는 그대로 둔다. 마크다운만 출력한다.")

COMMIT_FN = None   # 시험 주입 자리 — 라이브는 component_lifecycle._commit


# ---------------------------------------------------------------- 표식 (기계가 앞에서 센다)

def _live_actions() -> Set[Tuple[str, str]]:
    try:
        import yaml
        d = yaml.safe_load(NODES_PATH.read_text(encoding="utf-8")) or {}
        nodes = d.get("nodes", d)
        return {(n, a) for n, v in nodes.items() if isinstance(v, dict)
                for a in (v.get("actions") or {})}
    except Exception:
        return set()


def _retired_phrases() -> List[str]:
    try:
        import yaml
        d = yaml.safe_load(RETIRED_CONTRACTS_PATH.read_text(encoding="utf-8")) or {}
        out: List[str] = []
        for ent in (d.get("retired") or []):
            out += [str(p) for p in (ent.get("phrases") or []) if p]
        return out
    except Exception:
        return []


def _section_of(lines: List[str], idx: int) -> str:
    for j in range(idx, -1, -1):
        m = HEADING_RE.match(lines[j])
        if m:
            return m.group(2).strip()
    return "__head__"


def build_markers(text: str, guide: str, live: Set[Tuple[str, str]], policy: Dict) -> Dict[str, List[str]]:
    """세 부류의 위치 표식 — 전부 기계가 재는 것만(LLM 0)."""
    lines = text.split("\n")
    dead: List[str] = []
    phrases: List[str] = []
    for i, ln in enumerate(lines):
        if EXCUSED_RE.search(ln) or "retired-ok" in ln:
            continue
        for n, a in ACTION_RE.findall(ln):
            if live and (n, a) not in live:
                dead.append(f"L{i + 1}: [{n}:{a}] — 존재하지 않는 어휘")
    for ph in _retired_phrases():
        for i, ln in enumerate(lines):
            if ph in ln and "retired-ok" not in ln:
                phrases.append(f"L{i + 1}: 은퇴 문구 「{ph}」")
    broken: List[str] = []
    for rel in sorted(set(PATH_RE.findall(text))):
        if not (BASE / rel).exists():
            broken.append(f"끊긴 경로 `{rel}`")

    unused: List[str] = []
    try:
        from guide_registry import section_uses
        uses = section_uses(guide, SECTION_WINDOW_DAYS)
    except Exception:
        uses = {}
    turns = int(uses.get("*", 0))
    if turns >= int(policy.get("section_unused_min_turns", 3)):
        for m in HEADING_RE.finditer(text):
            title = m.group(2).strip()
            if uses.get(title, 0) == 0 and ACTION_RE.search(text[m.end():m.end() + 4000] or ""):
                unused.append(title)
    return {"dead_refs": dead, "retired_phrases": phrases, "broken_paths": broken,
            "unused_sections": unused, "observed_turns": [str(turns)]}


# ---------------------------------------------------------------- 기계 대조 (관문)

def _headings(text: str) -> Set[str]:
    return {re.sub(r"\s+", " ", m.group(2).strip()) for m in HEADING_RE.finditer(text)}


def verify_compressed(original: str, compressed: str, live: Set[Tuple[str, str]],
                      budget: Optional[int]) -> Optional[str]:
    """통과면 None, 아니면 탈락 사유. 판단이 아니라 대조다."""
    if not compressed or not compressed.strip():
        return "빈 출력"
    if len(compressed.encode("utf-8")) >= len(original.encode("utf-8")):
        return "더 짧아지지 않음"
    if budget and len(original.encode("utf-8")) > budget and len(compressed.encode("utf-8")) > budget:
        return f"예산 {budget}B 안으로 들어오지 않음 ({len(compressed.encode('utf-8'))}B)"
    o_pairs = {p for p in ACTION_RE.findall(original) if not live or p in live}
    c_pairs = set(ACTION_RE.findall(compressed))
    lost = sorted(o_pairs - c_pairs)
    if lost:
        return "살아 있는 어휘 참조 유실: " + ", ".join(f"[{n}:{a}]" for n, a in lost[:6])
    lost_h = sorted(_headings(original) - _headings(compressed))
    if lost_h:
        return "절 제목 유실: " + " / ".join(lost_h[:6])
    lost_p = sorted(set(PATH_RE.findall(original)) - set(PATH_RE.findall(compressed)))
    lost_p = [p for p in lost_p if (BASE / p).exists()]
    if lost_p:
        return "살아 있는 코드 경로 유실: " + ", ".join(lost_p[:6])
    return None


# ---------------------------------------------------------------- 대상 선정

def _audit_flagged() -> Set[str]:
    try:
        d = json.loads(AUDIT_FLAGS_PATH.read_text(encoding="utf-8"))
        return {f.get("guide") for f in (d.get("flags") or []) if f.get("guide")}
    except Exception:
        return set()


def _recent_churn() -> Set[str]:
    """최근 30일 사실수정이 있었던 가이드 — 과압축 뒤 수리된 흔적일 수 있어 뒤로 민다."""
    try:
        from guide_feedback import edit_churn
        return {r.get("guide") for r in edit_churn(30) if (r.get("edit_days") or 0) >= 2}
    except Exception:
        return set()


def pick_targets(policy: Dict) -> List[Dict]:
    budget = int(policy.get("guide_budget_bytes", 36000))
    per_run = int(policy.get("downscale_per_run", 2))
    flagged = _audit_flagged()
    churn = _recent_churn()
    rows: List[Dict] = []
    for p in sorted(GUIDES_DIR.glob("*.md")):
        try:
            size = p.stat().st_size
        except OSError:
            continue
        over = size > budget
        if not over and p.name not in flagged:
            continue
        rows.append({"guide": p.name, "bytes": size, "over": over, "flagged": p.name in flagged,
                     "churn": p.name in churn})
    # 예산 초과 큰 것 먼저, 최근 수리 흔적은 뒤로
    rows.sort(key=lambda r: (r["churn"], not r["over"], -r["bytes"]))
    return rows[:per_run]


# ---------------------------------------------------------------- 압축 (모델은 여기서만)

def _prompt(guide: str, text: str, markers: Dict[str, List[str]], budget: int, over: bool) -> str:
    def _blk(title: str, items: List[str]) -> str:
        return f"[{title}]\n" + ("\n".join(f"  - {x}" for x in items) if items else "  (없음)")
    goal = (f"예산 {budget} 바이트 안으로 줄여라(현재 {len(text.encode('utf-8'))}B)." if over
            else "표식된 부류만 줄여라(예산 안이므로 크기 목표 없음).")
    return (
        f"아래 가이드 `{guide}` 를 **뜻을 바꾸지 않고** 줄인다. {goal}\n\n"
        "줄이는 부류(우선순위 순) — 표식된 것만:\n"
        "  1. 어휘와 어긋난 문장: 아래 [죽은 참조]·[은퇴 문구]·[끊긴 경로] 줄을 지우거나 한 줄로 접는다.\n"
        "  2. 완성 처방: 그대로 복붙할 완성 문장(구체 검색어·완성 본문)은 자리표 골격(`<대상>`·`{날짜}`)으로 바꾼다.\n"
        "  3. [미사용 절]: 절 제목은 그대로 두고 본문을 한 줄 요약으로 접는다(마지막에 '상세는 git 이력' 표기).\n\n"
        "지키는 것(기계가 대조한다 — 하나라도 어기면 이번 출력은 버려진다):\n"
        "  · 살아 있는 `[node:action]` 참조는 전부 남긴다(표식 안 된 어휘 참조 삭제 금지).\n"
        "  · 모든 `##`/`###` 절 제목을 그대로 남긴다(순서 유지).\n"
        "  · 백틱 `backend/…py` 경로는 끊긴 것만 지운다.\n"
        "  · 실측 기록·함정·사용자 판정 문장은 줄이되 지우지 않는다.\n"
        "  · 새 내용을 쓰지 않는다.\n\n"
        + _blk("죽은 참조", markers.get("dead_refs", [])) + "\n"
        + _blk("은퇴 문구", markers.get("retired_phrases", [])) + "\n"
        + _blk("끊긴 경로", markers.get("broken_paths", [])) + "\n"
        + _blk("미사용 절 (관측 턴 " + ",".join(markers.get("observed_turns", ["0"])) + ")",
               markers.get("unused_sections", [])) + "\n\n"
        f"[가이드 원문]\n<<<GUIDE>>>\n{text[:MAX_GUIDE_CHARS]}\n<<<END>>>\n\n"
        "출력: 압축한 가이드 전문을 <<<GUIDE>>> 와 <<<END>>> 사이에. 설명·머리말 없이."
    )


def _extract(resp: str) -> Optional[str]:
    if not resp:
        return None
    m = re.search(r"<<<GUIDE>>>\s*\n(.*?)\n?<<<END>>>", resp, re.S)
    body = m.group(1) if m else None
    if body is None:
        # 태그를 빼먹었지만 마크다운으로 시작하면 관대하게
        s = resp.strip()
        body = s if s.startswith("#") or s.startswith("<!--") else None
    return body.rstrip() + "\n" if body else None


def downscale_one(guide: str, policy: Dict, live: Optional[Set[Tuple[str, str]]] = None,
                  ai_call=None) -> Dict:
    """가이드 하나를 압축한다. 반환 {guide, ok, before, after, reason, markers}. 파일 쓰기·커밋은 ok 일 때만."""
    path = GUIDES_DIR / guide
    text = path.read_text(encoding="utf-8")
    live = live if live is not None else _live_actions()
    budget = int(policy.get("guide_budget_bytes", 36000))
    before = len(text.encode("utf-8"))
    over = before > budget

    # 생명주기 후보 표식은 모델에 안 보이고 결과에 다시 붙인다(표식은 기계 소유).
    mark = ""
    m = LIFECYCLE_MARK_RE.match(text)
    if m:
        mark, text = m.group(0), text[m.end():]

    markers = build_markers(text, guide, live, policy)
    has_target = any(markers[k] for k in ("dead_refs", "retired_phrases", "broken_paths", "unused_sections"))
    if not over and not has_target:
        return {"guide": guide, "ok": False, "before": before, "after": before,
                "reason": "줄일 표식 없음(예산 안)", "markers": markers, "skipped": True}

    call = ai_call
    if call is None:
        from consciousness_agent import oneshot_ai_call
        call = lambda p: oneshot_ai_call(p, system_prompt=_SYS, role="guide_audit")  # noqa: E731
    resp = call(_prompt(guide, text, markers, budget, over))
    compressed = _extract(resp or "")
    if compressed is None:
        return {"guide": guide, "ok": False, "before": before, "after": before,
                "reason": "응답을 읽지 못함", "markers": markers}
    why = verify_compressed(text, compressed, live, budget if over else None)
    if why:
        return {"guide": guide, "ok": False, "before": before, "after": len(compressed.encode("utf-8")),
                "reason": why, "markers": markers}
    path.write_text(mark + compressed, encoding="utf-8")
    after = len((mark + compressed).encode("utf-8"))
    try:
        from guide_registry import record_review
        record_review(guide)
    except Exception:
        pass
    return {"guide": guide, "ok": True, "before": before, "after": after, "reason": None,
            "markers": markers}


# ---------------------------------------------------------------- 번들 진입점

def _should_run(force: bool) -> bool:
    if force:
        return True
    try:
        st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        last = datetime.fromisoformat(st["last_run"])
        return datetime.now() - last >= timedelta(hours=CADENCE_HOURS)
    except Exception:
        return True


def run_guide_downscale(force: bool = False, ai_call=None) -> Dict:
    """주간 카덴스로 예산 초과·깃발 가이드를 압축하고 self_checks 형식 1건을 돌려준다."""
    if not _should_run(force):
        return {"skipped": "cadence"}
    try:
        from component_lifecycle import load_policy, _commit as _lc_commit
    except Exception:
        load_policy = lambda: {"guide_budget_bytes": 36000, "downscale_per_run": 2,  # noqa: E731
                               "section_unused_min_turns": 3}
        _lc_commit = None
    policy = load_policy()
    started = datetime.now()
    targets = pick_targets(policy)
    live = _live_actions()
    done: List[Dict] = []
    unchecked: List[Dict] = []
    for t in targets:
        try:
            r = downscale_one(t["guide"], policy, live, ai_call=ai_call)
        except Exception as e:
            r = {"guide": t["guide"], "ok": False, "reason": f"예외 {e}", "before": t["bytes"],
                 "after": t["bytes"]}
        (done if r.get("ok") else unchecked).append(r)

    committed = None
    if done:
        paths = [f"data/guides/{r['guide']}" for r in done]
        label = ", ".join(f"{r['guide']} {r['before'] // 1024}→{r['after'] // 1024}KB" for r in done)
        msg = f"downscale(guide): {label} (guide_downscale — 야간 하향 정규화, 기계 대조 통과)"
        fn = COMMIT_FN or _lc_commit
        committed = bool(fn(paths, msg)) if fn else False

    try:
        STATE_PATH.write_text(json.dumps({"last_run": started.isoformat(), "done": len(done),
                                          "unchecked": len(unchecked)}, ensure_ascii=False),
                              encoding="utf-8")
        FLAGS_PATH.write_text(json.dumps({"measured_at": started.isoformat(), "targets": targets,
                                          "done": done, "unchecked": unchecked, "committed": committed},
                                         ensure_ascii=False, indent=1, default=str),
                              encoding="utf-8")
    except Exception as e:
        logger.warning(f"[GuideDownscale] 상태 저장 실패 (무시): {e}")

    notes = []
    if done:
        notes.append("압축 " + ", ".join(f"{r['guide']}({r['before'] // 1024}→{r['after'] // 1024}KB)" for r in done))
    real_unchecked = [u for u in unchecked if not u.get("skipped")]
    if real_unchecked:
        notes.append(f"판정 불가 {len(real_unchecked)} — " + "; ".join(
            f"{u['guide']}: {u.get('reason')}" for u in real_unchecked[:3]))
    if notes:
        logger.info(f"[GuideDownscale] {' · '.join(notes)}")
    return {
        "node": "__telemetry__",
        "action": "guide_downscale",
        "success": not real_unchecked,
        "response_ms": int((datetime.now() - started).total_seconds() * 1000),
        "data_quality": "ok" if not real_unchecked else "audit_incomplete",
        "error_message": " / ".join(notes) if real_unchecked else None,
        "targets": targets, "done": done, "unchecked": unchecked, "committed": committed,
    }
