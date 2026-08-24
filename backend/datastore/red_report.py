"""
red_report.py - 자기수리 결말 회수 (분리 프로세스가 남긴 판정을 대화로 되돌린다)
IndieBiz OS Core

★왜 필요한가(2026-08-17): backend 를 고치는 수리는 **자기 턴이 죽은 뒤에 결말이 난다** —
편집이 부른 리로드가 에이전트를 끊고, 그 뒤에 워치독(분리 프로세스)이 헬스체크·롤백을
수행해 `result.json` 에 판정을 적는다. 그런데 그 파일을 읽는 쪽이 **아무 데도 없었다**:
성공이면 조용히 퇴근, 실패면 OS 알림 한 번. 사용자 자리에서는 성공한 수리와 그냥
멎어버린 수리가 **구별되지 않았다**("멈춰버린 것 같다"의 나머지 절반).

이 모듈은 미보고 판정을 주워 다음 턴의 맥락에 얹고(=AI 가 말로 닫는다) 보고 표식을
남긴다. 회수는 한 번뿐(announced_at 기록)이고, 오래된 판정은 조용히 흘려보낸다.
표준 라이브러리만 사용 — 워치독(의존성 0 계약)도 같은 파일 형식을 읽고 쓴다.
"""
import json
import os
import time

MAX_AGE_S = 24 * 3600   # 이보다 오래된 판정은 보고하지 않는다(지난 이야기)
MAX_ITEMS = 3           # 한 턴에 얹는 판정 수 상한

_OUTCOME_LABEL = {
    "healthy": "수리 성공 — 수정 후 서버 정상 확인됨",
    "rolled_back": "수리 실패 — 서버가 죽어 자동 롤백됨(원상 복구)",
    "intentional_shutdown": "판정 보류 — 시스템이 의도적으로 종료됨(수리는 보존)",
    "timeout": "판정 미완 — 감시견 수명 초과(수동 확인 필요)",
    # 지연 적용(2026-08-19) 수행자 단계의 결말 — repair_staging._write_deferred_result
    "deferred_verify_failed": "예약 적용 중단 — 쓰기 직전 재검증 실패(라이브 무변경, 격리 보존)",
    "deferred_apply_failed": "예약 적용 실패 — 적용 단계 오류(라이브 상태는 detail 확인)",
    "deferred_canceled": "예약 적용 취소 — 예약 후 세션이 변해 스냅샷이 낡음(라이브 무변경)",
}

# 예약 적용은 턴 종료 후 몇 분 안에 스스로 끝난다 — 이보다 오래 apply_scheduled 로
# 남아 있으면 수행자(red_apply)가 죽은 것(좌초)이라 다시 보고 대상이 된다.
SCHEDULED_STALE_S = 30 * 60


# ★판정의 주인 (2026-08-25, 사용자 확정: "수리한 에이전트가 말하도록 해야지")
# 수리는 자기 턴이 죽은 뒤에 결말이 나므로, 그 결말을 **누구의 입이 닫느냐**가 정해져야 한다.
# 옛 규칙은 "시스템 AI 만"(수리의 주체이자 보고 책임자)이었는데, 2026-08-25 에 그랜트 한도가
# 정본대로 복원되면서 프로젝트 에이전트도 수리 주체가 됐다 — 그러면 그 판정이 명령한 창이
# 아닌 곳으로 간다. 주인은 **수리를 한 그 에이전트**다.
#
# 열쇠는 쓰기 시점에 원장(manifest·session)에 박히고, 다음 턴의 회상이 자기 열쇠로 조회한다.
# 규칙 한 벌만 두는 이유: 생산자(handler·repair_staging)와 소비자(cognitive_recall)가 각자
# 조립하면 반드시 어긋난다 — 어긋나면 판정이 **아무 입에도 안 걸려 영영 침묵**한다.
OWNER_SYSTEM_AI = "system_ai"


def owner_key(agent_id: str = "", project_id: str = "") -> str:
    """수리 주체의 열쇠. 에이전트 신원이 없으면 시스템 AI(그 몸은 agent_id 를 안 세운다).

    프로젝트를 앞에 붙이는 이유: agent_001 같은 id 는 **프로젝트 안에서만** 유일하다.

    ★시스템 AI 는 자리에 따라 신원이 반쯤 서 있다 — 채팅 턴은 agent_id 를 안 세우지만
    자기 상주 루프는 config 의 id/project(`system_ai`/`system`)를 세운다. 같은 몸이
    자리에 따라 다른 열쇠를 받으면 판정이 어긋나 영영 침묵하므로, 예약된 id 하나로
    접는다(id 가 system_ai 면 프로젝트와 무관하게 시스템 AI)."""
    aid = (agent_id or "").strip()
    pid = (project_id or "").strip()
    if not aid or aid == OWNER_SYSTEM_AI:
        return OWNER_SYSTEM_AI
    return f"{pid}:{aid}" if pid else aid


def current_owner() -> str:
    """지금 이 스레드가 누구인가 — 스레드 컨텍스트에서 읽는다(없으면 시스템 AI)."""
    try:
        from thread_context import get_current_agent_id, get_current_project_id
        return owner_key(get_current_agent_id() or "", get_current_project_id() or "")
    except Exception:
        return OWNER_SYSTEM_AI


def _owner_of(record: dict) -> str:
    """원장 한 건의 주인. 표식이 없는 옛 기록은 종전 규약대로 시스템 AI 것이다."""
    return (record or {}).get("owner") or OWNER_SYSTEM_AI


def _backups_root(repo: str) -> str:
    return os.path.join(repo, "data", "system_ai_state", "red_backups")


def _iter_result_paths(repo: str):
    root = _backups_root(repo)
    try:
        for name in os.listdir(root):
            p = os.path.join(root, name, "result.json")
            if os.path.exists(p):
                yield p
    except OSError:
        return


def collect_pending(repo: str, max_items: int = MAX_ITEMS, owner: str = None) -> list:
    """아직 사용자에게 보고되지 않은 수리 판정 목록(최신 우선). 부작용 없음.

    owner 를 주면 **그 주체가 낸 판정만** 돌려준다(None=전부 — 감사·시험용)."""
    out = []
    now = time.time()
    for path in _iter_result_paths(repo):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if data.get("announced_at"):
            continue
        if owner is not None and _owner_of(data) != owner:
            continue
        finished = data.get("finished_at") or 0
        if finished and now - finished > MAX_AGE_S:
            continue
        data["_path"] = path
        out.append(data)
    out.sort(key=lambda d: d.get("finished_at") or 0, reverse=True)
    return out[:max_items]


def mark_announced(items: list):
    """보고 표식 — 같은 판정을 두 번 말하지 않는다."""
    for data in items:
        path = data.get("_path")
        if not path:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                cur = json.load(f)
            cur["announced_at"] = time.time()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cur, f, ensure_ascii=False, indent=2)
        except Exception:
            continue


def collect_unapplied(repo: str, min_age_s: float = 60.0, owner: str = None) -> list:
    """적용되지 않은 채 남은 격리 스테이징 세션 (2026-08-17).

    ★왜 여기냐: 격리 스테이징은 라이브를 안 건드리는 게 장점인데, 바로 그래서 **적용을
    빠뜨린 수리가 아무 흔적도 남기지 않는다** — 사용자 자리에서는 '고쳤다더니 그대로'가
    된다. 판정 회수(위)가 죽음을 넘은 결말을 닫는 것과 같은 이유로, 이건 *일어나지 않은*
    적용을 닫는다. 세션은 apply/discard 로 스스로 사라지므로 해소되면 조용해진다.

    부작용 없음. min_age_s 는 지금 돌고 있는 턴의 세션을 오보하지 않기 위한 유예."""
    root = os.path.join(repo, "data", "system_ai_state", "repair_sessions")
    now = time.time()
    out = []
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(root, name)
        try:
            with open(path, encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            continue
        status = s.get("status")
        if status not in ("staging", "apply_scheduled") or not (s.get("files") or {}):
            continue
        if owner is not None and _owner_of(s) != owner:
            continue
        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue
        if age > MAX_AGE_S:
            continue
        if status == "staging" and age < min_age_s:
            continue
        # 신선한 예약은 수행자가 곧 처리한다 — 오보하지 않는다. 오래 남은 것만 좌초.
        if status == "apply_scheduled" and age < SCHEDULED_STALE_S:
            continue
        out.append({"key": s.get("key"),
                    "files": [r.get("rel") for r in (s.get("files") or {}).values()],
                    "age_s": int(age),
                    "stranded_scheduled": status == "apply_scheduled"})
    return out[:MAX_ITEMS]


def pending_scent(repo: str, owner: str = None) -> str:
    """미보고 판정 + 미적용 스테이징을 연상 블록용 XML 로. 없으면 빈 문자열(0토큰).

    ★부작용 있음: 반환과 동시에 판정에 보고 표식을 남긴다(한 번만 말하기 위해).
    스테이징 쪽은 표식을 남기지 않는다 — 그건 지나간 사건이 아니라 *지금도 참인 상태*라,
    해소(apply/discard)될 때까지 계속 보여야 한다.

    owner: 이 턴을 도는 주체의 열쇠 — 자기가 한 수리의 결말만 줍는다. 남의 판정을
    가져가면 그 판정은 announced 표식이 찍힌 채 **정작 명령한 창에서는 영영 안 보인다.**
    """
    items = collect_pending(repo, owner=owner)
    staged = collect_unapplied(repo, owner=owner)
    if not items and not staged:
        return ""
    if not items:
        return _staged_block(staged)
    rows = []
    for d in items:
        outcome = d.get("outcome") or "unknown"
        label = _OUTCOME_LABEL.get(outcome, outcome)
        files = d.get("files") or d.get("restored") or []
        detail = (d.get("detail") or d.get("note") or "").replace('"', "'")[:160]
        rows.append(
            f'  <repair outcome="{outcome}" files="{len(files)}">{label}'
            + (f' — {detail}' if detail else "")
            + "</repair>"
        )
    note = ("직전 자기수리의 결말이다(리로드로 그때의 턴이 끊겨 아직 사용자에게 보고되지 "
            "않았다). 사용자에게 결과를 한 문장으로 먼저 알리고, 실패·롤백이면 무엇이 "
            "원상 복구됐는지 말한 뒤 다음 행동을 제안하라. 이미 지난 일이니 다시 수리하지 "
            "말고, 사용자가 새로 요청한 일이 있으면 그것을 이어서 하라.")
    mark_announced(items)
    return (f"<repair_outcome note=\"{note}\">\n" + "\n".join(rows) + "\n</repair_outcome>"
            + _staged_block(staged))


def _staged_block(staged: list) -> str:
    """미적용 스테이징 블록. 없으면 빈 문자열."""
    if not staged:
        return ""
    rows = [f'  <staged key="{s["key"]}" files="{len(s["files"])}"'
            + (' stranded_scheduled="true"' if s.get("stranded_scheduled") else "")
            + ">" + ", ".join(s["files"][:6]) + "</staged>" for s in staged]
    note = ("지난 수리가 격리 사본에만 쌓인 채 **라이브에 적용되지 않았다** — 그 수정은 "
            "지금 시스템에 없다. 이어서 마무리하려면 [self:patch]{op:\"apply\"} 로 "
            "검증·적용하고, 더 필요 없으면 {op:\"discard\"} 로 정리하라. 어느 쪽이든 "
            "사용자에게 '아직 반영되지 않았다'는 사실을 먼저 알려라. "
            "stranded_scheduled=true 는 예약된 지연 적용의 수행자가 죽어 좌초한 것 — "
            "다시 apply 하면 재검증 후 재예약된다.")
    return f"\n<repair_staged note=\"{note}\">\n" + "\n".join(rows) + "\n</repair_staged>"
