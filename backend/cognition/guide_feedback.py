"""가이드 되먹임 — 쓴 놈이 고친다 (증류 4단계).

## 왜 있나

가이드는 7종 기억 중 **증류가 없는 유일한 기억**이었다:

| 기억 | 어디서 증류되나 |
|---|---|
| 해마 | 실행에서 (성공한 실행 → 용례) |
| 심층메모리 | 대화에서 |
| 포식기억 | 포식에서 |
| **가이드** | **아무 데서도 — 사람이 손으로 쓰고 그 뒤 방치** |

앞의 셋은 전부 `_after_response` 의 1·2·3 단계다. 가이드만 그 자리에 없었고,
그 공백이 2026-08-17 에 79→67개·81KB 를 손으로 걷어내는 청구서로 돌아왔다.

**가장 좋은 감사자는 방금 그 가이드를 쓴 에이전트다.** 주간 순찰은 차가운 산문을 읽고
*추측*해야 하지만, `table:chart_line` 이 없어서 실패한 에이전트는 *안다*. 이 모듈은
턴이 끝난 뒤 그 앎을 가이드에 되돌려 쓴다.

## 세 갈래로 갈라 쓴다 — 위험이 다르기 때문

1. **관찰 덧붙이기(자동)** — "2026-08-17 실측: region 필터는 서울·세종만 집계된다".
   저위험이고, 실측으로 확인된 *안 썩는 내용*이다(썩는 건 시스템을 다시 적은 부분이고,
   안 썩는 건 세계를 측정한 부분이다 — 2026-08-17 전수 정리의 결론).
2. **사실 오류 수정(자동, 단 기계 검증 후)** — 죽은 어휘 이름·끊긴 경로처럼 *검증 가능한*
   것만. ★모델의 제안을 그대로 믿지 않는다: `old` 가 실제로 파일에 있고 `new` 가 실재하는
   어휘·경로일 때만 적용한다(notebook 의 '인용 결정론 후검증'과 같은 규율 — 판단은 모델이,
   확인은 코드가).
3. **방침·전제 변경(제안만)** — 사람에게 올린다. 한 번의 이상한 실패로 멀쩡한 지침을
   바꾸면 안 된다. 2026-08-17 에 `remotion.md` 의 운명이 실제로 사용자 판정으로 뒤집혔다 —
   기계가 혼자 정하면 틀린다.

## churn 감시

매 턴 "고칠 것 있나?"를 물으면 모델은 **뭐라도 고치려는 편향**을 보인다. 그래서 모든
수정을 `guide_edit` 에 기록한다 — 가이드가 매주 흔들리면 그건 학습이 아니라 churn 이고,
그때는 기준을 조여야 한다(`edit_churn()` 이 그 숫자를 준다).
"""

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parents[2] / "data"
GUIDES_DIR = DATA_PATH / "guides"
PROPOSALS_PATH = DATA_PATH / "guide_proposals.jsonl"

MAX_GUIDES_PER_TURN = 2      # 비용 상한 — 한 턴에 여러 가이드가 붙어도 앞의 둘만
MAX_GUIDE_CHARS = 6000       # 모델에 보일 본문 상한
OBS_HEADING = "## 실측 기록 (자동 누적)"

REVIEW_COOLDOWN_DAYS = 30    # 최근 검토했으면 다시 안 본다 (비용 절약, 2026-08-17 사용자 판정)

_SYS = ("당신은 방금 작업을 끝낸 실행 에이전트다. 방금 쓴 가이드가 실제와 맞았는지만 본다. "
        "고칠 것이 없으면 없다고 답하는 것이 정상이다. JSON만 출력한다.")


# ---------------------------------------------------------------- 검증 도구

def _live_actions() -> set:
    try:
        import yaml
        d = yaml.safe_load((DATA_PATH / "ibl_nodes.yaml").read_text(encoding="utf-8"))
        nodes = d.get("nodes", d)
        return {f"{n}:{a}" for n, v in nodes.items() if isinstance(v, dict)
                for a in (v.get("actions") or {})}
    except Exception:
        return set()


def _mechanical_smell(path: Path, live: set) -> Optional[str]:
    """LLM 없이 공짜로 재는 부패 신호 — 죽은 어휘 참조 / 끊긴 코드 경로.

    빌드 가드가 쓰는 것과 같은 검출이고, 여기선 **쿨다운을 뚫는 열쇠**로 쓴다.
    """
    try:
        src = path.read_text(encoding="utf-8")
    except OSError:
        return None
    known = {a.split(":")[0] for a in live}
    dead = {f"{n}:{a}" for n, a in re.findall(r"\[([a-z_]+):([a-z_]+)\]", src)
            if n in known and f"{n}:{a}" not in live}
    if dead:
        return f"죽은 어휘 참조 {sorted(dead)[:3]}"
    broken = [r for r in re.findall(r"`(backend/[A-Za-z0-9_/]+\.py)`", src)
              if not (DATA_PATH.parent / r).exists()]
    if broken:
        return f"끊긴 코드 경로 {broken[:2]}"
    return None


def should_review(guide: str, live: set) -> tuple:
    """이번 턴에 이 가이드를 검토할까? → (검토여부, 사유)

    ★쿨다운만 두면 구멍이 생긴다: 쿨다운 *중에* 어휘가 바뀌면 그 사이 낡은 가이드를
    한 달간 못 잡는다. 그래서 **무료 기계 신호**(죽은 어휘·끊긴 경로)는 쿨다운을 뚫는다 —
    LLM 을 안 쓰므로 이 예외에는 비용이 없고, 정작 급한 부패만 즉시 걸린다.
    """
    path = GUIDES_DIR / guide
    if not path.exists():
        return False, "파일 없음"
    smell = _mechanical_smell(path, live)
    if smell:
        return True, f"기계 신호({smell})"
    try:
        from guide_registry import last_review
        last = last_review(guide)
    except Exception:
        last = None
    if not last:
        return True, "검토 이력 없음"
    try:
        y, m, d = (int(x) for x in last.split("-"))
        age = (date.today() - date(y, m, d)).days
    except Exception:
        return True, "검토일 해석 불가"
    if age < REVIEW_COOLDOWN_DAYS:
        return False, f"최근 검토({age}일 전) — 쿨다운"
    return True, f"마지막 검토 {age}일 전"


def _verify_fix(old: str, new: str, live: set) -> Optional[str]:
    """사실 수정 제안이 *기계적으로* 옳은지 확인. 통과하면 None, 아니면 거절 사유.

    ★여기가 이 모듈의 안전 바닥이다 — 모델은 무엇을 고칠지 제안하고,
    옳은지는 코드가 확인한다. 확인할 수 없는 제안은 적용하지 않는다.
    """
    if not old or not new or old == new:
        return "빈 값이거나 동일"
    if len(old) > 300 or len(new) > 300:
        return "너무 긴 치환(문단 재작성은 사실 수정이 아니다)"

    # ① 어휘 이름 수정: new 안의 [node:action] 은 전부 실재해야 한다
    new_acts = {f"{m[0]}:{m[1]}" for m in re.findall(r"\[([a-z_]+):([a-z_]+)\]", new)}
    known_nodes = {a.split(":")[0] for a in live}
    for a in new_acts:
        if a.split(":")[0] in known_nodes and a not in live:
            return f"새 텍스트가 실재하지 않는 어휘를 부른다: {a}"

    # ② 경로 수정: new 안의 backend/... 경로는 실존해야 한다
    for rel in re.findall(r"(backend/[A-Za-z0-9_/]+\.py)", new):
        if not (DATA_PATH.parent / rel).exists():
            return f"새 텍스트가 실존하지 않는 경로를 가리킨다: {rel}"

    # ③ old 가 죽은 어휘·끊긴 경로를 담고 있었는가 = 고칠 만한 것이었는가
    old_acts = {f"{m[0]}:{m[1]}" for m in re.findall(r"\[([a-z_]+):([a-z_]+)\]", old)}
    old_dead = {a for a in old_acts if a.split(":")[0] in known_nodes and a not in live}
    old_broken = [r for r in re.findall(r"(backend/[A-Za-z0-9_/]+\.py)", old)
                  if not (DATA_PATH.parent / r).exists()]
    if not old_dead and not old_broken:
        return "옛 텍스트에 죽은 어휘·끊긴 경로가 없다(사실 오류가 아니라 표현 변경 — 제안으로 돌린다)"
    return None


# ---------------------------------------------------------------- 적용

def _append_observation(path: Path, texts: List[str]) -> int:
    """실측 관찰을 날짜와 함께 덧붙인다. 중복이면 건너뛴다."""
    try:
        src = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    fresh = [t for t in texts if t and t.strip() and t.strip()[:60] not in src]
    if not fresh:
        return 0
    today = date.today().isoformat()
    lines = "\n".join(f"- {today} 실측: {t.strip()}" for t in fresh)
    if OBS_HEADING in src:
        src = src.replace(OBS_HEADING, f"{OBS_HEADING}\n{lines}", 1)
    else:
        src = src.rstrip() + f"\n\n{OBS_HEADING}\n\n> 실행 에이전트가 턴 종료 후 덧붙인다.\n{lines}\n"
    path.write_text(src, encoding="utf-8")
    return len(fresh)


def _apply_fix(path: Path, old: str, new: str) -> bool:
    try:
        src = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if src.count(old) != 1:      # 유일하지 않으면 손대지 않는다(엉뚱한 자리 치환 방지)
        return False
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    return True


def _queue_proposal(guide: str, issue: str, evidence: str = "") -> None:
    try:
        with open(PROPOSALS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "at": date.today().isoformat(), "guide": guide,
                "issue": issue[:400], "evidence": evidence[:300],
            }, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[GuideFeedback] 제안 기록 실패 (무시): {e}")


def _record_edit(guide: str, kind: str, n: int = 1) -> None:
    """churn 계측 — 가이드가 얼마나 자주 흔들리는지."""
    try:
        from guide_registry import _conn
        with _conn() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS guide_edit (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       guide TEXT NOT NULL, edited_on TEXT NOT NULL,
                       kind TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 1)"""
            )
            conn.execute("INSERT INTO guide_edit(guide, edited_on, kind, n) VALUES(?,?,?,?)",
                         (guide, date.today().isoformat(), kind, n))
    except Exception as e:
        logger.debug(f"[GuideFeedback] 수정 기록 실패 (무시): {e}")


def edit_churn(days: int = 30) -> List[Dict]:
    """최근 수정 빈도 — 자주 흔들리는 가이드가 앞으로."""
    try:
        from guide_registry import _conn
        with _conn() as conn:
            rows = conn.execute(
                "SELECT guide, COUNT(*), SUM(n) FROM guide_edit "
                "WHERE edited_on >= date('now', ?) GROUP BY guide ORDER BY 2 DESC",
                (f"-{days} day",),
            ).fetchall()
        return [{"guide": r[0], "edit_days": r[1], "items": r[2]} for r in rows]
    except Exception:
        return []


# ---------------------------------------------------------------- 본체

def _review_one(guide: str, user_message: str, response: str,
                tool_summary: str, live: set) -> Dict:
    from consciousness_agent import lightweight_ai_call

    path = GUIDES_DIR / guide
    try:
        body = path.read_text(encoding="utf-8")[:MAX_GUIDE_CHARS]
    except OSError:
        return {}

    prompt = (
        f"방금 끝낸 작업에서 아래 가이드를 참고했다. **가이드가 실제와 맞았는지만** 검토하라.\n\n"
        f"[사용자 요청]\n{(user_message or '')[:600]}\n\n"
        f"[내가 실제로 한 일]\n{tool_summary[:1200] or '(도구 실행 없음)'}\n\n"
        f"[응답 요약]\n{(response or '')[:600]}\n\n"
        f"[가이드: {guide}]\n{body}\n\n"
        "다음 넷만 본다:\n"
        "  1. 가이드가 말한 어휘·경로·파라미터가 실제와 달랐나\n"
        "  2. 가이드 절차를 따랐는데 실패했나\n"
        "  3. 가이드에 없는 함정을 새로 만났나\n"
        "  4. 가이드보다 나은 경로를 찾았나\n\n"
        "세 갈래로 나눠 답하라:\n"
        '  · observations: 이번에 실측으로 확인한 함정·사실 (가이드에 없던 것만, 한 줄씩). '
        "일반론·이미 적힌 내용은 넣지 마라.\n"
        '  · factual_fixes: 죽은 어휘 이름·끊긴 경로처럼 *명백한 사실 오류*. '
        '{"old":"파일에 있는 정확한 문자열","new":"고친 문자열","why":"근거"} — old 는 '
        "가이드에서 **그대로 복사**해야 하고 파일에서 유일해야 한다.\n"
        '  · proposals: 방침·전제를 바꿔야 한다는 판단 (문장으로만, 직접 고치지 않는다).\n\n'
        "★이번 턴에서 *실제로 겪은 것*만 써라. 추측·일반론 금지.\n"
        "★고칠 것이 없으면 세 배열 모두 비우는 것이 정상이고 바람직하다.\n"
        '출력: {"observations":[],"factual_fixes":[],"proposals":[]} JSON만.'
    )

    resp = lightweight_ai_call(prompt, system_prompt=_SYS, role="guide_audit")
    if not resp:
        return {}
    m = re.search(r"\{.*\}", resp, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def review_used_guides(guides: List[str], user_message: str, response: str,
                       tool_calls=None) -> Dict:
    """이번 턴에 쓰인 가이드를 검토하고 되돌려 쓴다. 증류 4단계.

    실패는 전부 삼킨다 — 되먹임이 턴을 망치면 안 된다.
    """
    result = {"reviewed": [], "skipped": [], "appended": 0, "fixed": 0,
              "proposed": 0, "rejected": []}
    if not guides:
        return result

    tool_summary = ""
    try:
        if tool_calls:
            names = [(c.get("name") or c.get("tool") or "?") if isinstance(c, dict) else str(c)
                     for c in tool_calls]
            tool_summary = ", ".join(names[:20])
    except Exception:
        pass

    live = _live_actions()
    for guide in list(dict.fromkeys(guides))[:MAX_GUIDES_PER_TURN]:
        path = GUIDES_DIR / guide
        if not path.exists():
            continue
        ok, why = should_review(guide, live)
        if not ok:
            result["skipped"].append(f"{guide}: {why}")
            continue
        try:
            out = _review_one(guide, user_message, response, tool_summary, live)
        except Exception as e:
            logger.debug(f"[GuideFeedback] {guide} 검토 실패 (무시): {e}")
            continue
        # ★고칠 게 없었어도 '검토했다'를 남긴다 — 그게 쿨다운의 근거이자
        #   '무수정 사용'을 "아무도 안 봤다"와 구별해 주는 정보다.
        try:
            from guide_registry import record_review
            record_review(guide)
        except Exception:
            pass
        if not out:
            continue
        result["reviewed"].append(guide)

        obs = [str(o) for o in (out.get("observations") or []) if o][:4]
        if obs:
            n = _append_observation(path, obs)
            if n:
                result["appended"] += n
                _record_edit(guide, "observation", n)

        for fx in (out.get("factual_fixes") or [])[:4]:
            if not isinstance(fx, dict):
                continue
            old, new = str(fx.get("old") or ""), str(fx.get("new") or "")
            why = _verify_fix(old, new, live)
            if why:
                # 검증 탈락은 버리지 않고 제안으로 — 모델이 본 것이 틀렸다는 뜻은 아니다
                result["rejected"].append({"guide": guide, "old": old[:80], "reason": why})
                _queue_proposal(guide, f"[검증 탈락 수정안] {fx.get('why') or ''}",
                                f"old={old[:120]} / new={new[:120]} / 사유={why}")
                result["proposed"] += 1
                continue
            if _apply_fix(path, old, new):
                result["fixed"] += 1
                _record_edit(guide, "factual_fix", 1)

        for pr in (out.get("proposals") or [])[:3]:
            if pr:
                _queue_proposal(guide, str(pr), tool_summary[:200])
                result["proposed"] += 1

    if result["appended"] or result["fixed"] or result["proposed"]:
        logger.info(
            f"[GuideFeedback] {','.join(result['reviewed'])} — "
            f"관찰 +{result['appended']} · 사실수정 {result['fixed']} · 제안 {result['proposed']}"
        )
    return result
