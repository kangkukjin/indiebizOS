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
import hashlib
import json
import os
import stat
import time
from pathlib import Path

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

# 오래 남은 예약은 재확인 대상으로 보고한다. 시간만으로 수행자 사망을 판정하지 않는다.
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


def _read_followup(result_path: str) -> dict:
    """판정 옆자리의 수행자 후속 기록(followup.json) — 없으면 빈 dict. 부작용 없음.

    ★왜 옆자리인가(2026-08-25): 성공 판정의 result.json 은 워치독이 헬스 확인 뒤 통째로
    덮는다. 수행자(red_apply)가 남기는 것 — 턴 종료를 봤는지 상한으로 강행했는지, 위탁받은
    검증 명령의 결과 — 은 그래서 같은 폴더의 다른 파일에 산다. 회수는 여기서 합친다."""
    try:
        with open(os.path.join(os.path.dirname(result_path), "followup.json"),
                  encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def followup_rows(followup: dict) -> list:
    """후속 기록 → 연상 블록에 얹을 XML 줄들. 말할 것이 없으면 빈 목록(0토큰)."""
    rows = []
    fu = followup or {}
    if fu.get("wait_outcome") == "cap":
        # ★상한은 안전망이지 시간표가 아니다 — 하중을 받기 시작하면 AI 의 얼굴 앞에 띄운다.
        cap = int(fu.get("turn_cap_s") or 0)
        rows.append(
            f'    <wait outcome="cap">예약한 턴({fu.get("episode_id") or "?"})이 스스로 '
            f'닫히지 않아 대기 상한{f"({cap}초)" if cap else ""}으로 강행했다 — 대개 그 턴이 '
            f'적용을 기다리며 살아 있던 경우다(자기가 자기 병목). 다음부터 예약 뒤에는 곧바로 '
            f'턴을 닫아라 — 그러면 몇 초 안에 적용된다.</wait>')
    elif fu.get("wait_outcome") == "cut":
        rows.append(
            f'    <wait outcome="cut">예약한 턴({fu.get("episode_id") or "?"})은 다른 재기동에 잘려 '
            f'스스로 닫히지 못했다 — 몸(/health)의 신고로 판정해 상한 대기 없이 적용했다. '
            f'그 턴의 마지막 보고는 유실됐을 수 있다(주행기록 CUT 표식 확인).</wait>')
    if fu.get("quiesce_outcome") == "cap":
        # 도는 턴이 0 이 되기를 상한까지 기다리다 강행 — 잘렸을 수 있는 턴을 이름으로 댄다.
        qcap = int(fu.get("quiesce_cap_s") or 0)
        cut = fu.get("live_turns_at_cap") or []
        cut_s = ("(" + ", ".join(str(i) for i in cut) + ")") if cut else ""
        cap_s = f"({qcap}초)" if qcap else ""
        rows.append(
            f'    <wait outcome="quiesce_cap">다른 턴{cut_s}이 '
            f'도는 채로 정적 대기 상한{cap_s}에 닿아 강행했다 — 그 턴은 '
            f'리로드에 잘렸을 수 있다(주행기록 고아 확인). 긴 턴이 이어지는 시간대라면 수리 적용을 '
            f'그 뒤로 미루는 편이 낫다.</wait>')
    pv = fu.get("post_verify") or {}
    if pv.get("ran"):
        code = pv.get("exit_code")
        verdict = "pass" if code == 0 else ("fail" if code is not None else "unknown")
        body = (pv.get("output") or "").replace("<", "‹").replace('"', "'").strip()[:500]
        rows.append(
            f'    <verify verdict="{verdict}" exit="{code}" cmd="'
            f'{(pv.get("cmd") or "").replace(chr(34), chr(39))[:120]}">{body}</verify>')
    elif pv:
        rows.append(f'    <verify verdict="skipped">{(pv.get("output") or "")[:200]}</verify>')
    return rows


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
        data["_followup"] = _read_followup(path)
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


def staged_live_comparison(repo: str, session: dict) -> dict:
    """조회 시 파일 내용만 비교한다. 기능 동등·커밋·활성화·수행자 생존 판정은 아니다.

    원장과 파일은 변경하지 않는다. 다른 경로로 반영되거나 발전한 정본도 그대로 둔다.
    """
    root = Path(repo).resolve()
    unknown = object()

    def fingerprint(value):
        if not isinstance(value, str) or not value:
            return unknown
        try:
            candidate = root / value
            path = candidate.resolve()
            path.relative_to(root)
            if candidate.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
                return unknown
            with path.open('rb') as stream:
                return hashlib.file_digest(stream, 'sha256').hexdigest()
        except FileNotFoundError:
            return None
        except (OSError, ValueError, RuntimeError):
            return unknown

    counts = dict(matching=0, base_unchanged=0, diverged=0, unknown=0)
    for rec in (session.get('files') or {}).values():
        if not isinstance(rec, dict):
            counts['unknown'] += 1
            continue
        live = fingerprint(rec.get('rel'))
        desired = None if rec.get('op') == 'delete' else fingerprint(rec.get('staged'))
        if live is unknown or desired is unknown or (desired is None and rec.get('op') != 'delete'):
            state = 'unknown'
        elif live == desired:
            state = 'matching'
        elif 'base_sha' not in rec:
            state = 'unknown'
        elif live == rec['base_sha']:
            state = 'base_unchanged'
        else:
            state = 'diverged'
        counts[state] += 1
    return counts


def staged_summary(row: dict) -> str:
    counts = row['live_comparison']
    return (f"내용 같음 {counts['matching']} · 원본 그대로 {counts['base_unchanged']} · "
            f"정본 별도 변경 {counts['diverged']} · 확인 불가 {counts['unknown']}")


def collect_unapplied(repo: str, min_age_s: float = 60.0, owner: str = None) -> list:
    """원장에 남은 격리 세션과 현재 파일 비교. 미반영 기능 목록이 아니다.

    부작용 없음. min_age_s는 진행 중 세션의 보고 유예이며 오래된 예약도
    수행자 사망으로 단정하지 않는다. 호환 이름 stranded_scheduled는 재확인 후보다.
    """
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
        # 신선한 예약은 기다린다. 오래된 예약은 생존 여부를 추측하지 않고 보고한다.
        if status == "apply_scheduled" and age < SCHEDULED_STALE_S:
            continue
        out.append({"key": s.get("key"),
                    "files": [r.get("rel") for r in (s.get("files") or {}).values()],
                    "age_s": int(age),
                    "live_comparison": staged_live_comparison(repo, s),
                    "stranded_scheduled": status == "apply_scheduled"})
        if len(out) >= MAX_ITEMS:
            break  # 프롬프트에 싣지 않을 세션의 파일까지 읽지 않는다.
    return out[:MAX_ITEMS]


def pending_scent(repo: str, owner: str = None) -> str:
    """미보고 판정 + 미적용 스테이징을 연상 블록용 XML 로. 없으면 빈 문자열(0토큰).

    ★부작용 있음: 반환과 동시에 판정에 보고 표식을 남긴다(한 번만 말하기 위해).
    스테이징 원장은 수정하지 않고 조회 때마다 파일을 대조한다.

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
    has_verify = False
    for d in items:
        outcome = d.get("outcome") or "unknown"
        label = _OUTCOME_LABEL.get(outcome, outcome)
        files = d.get("files") or d.get("restored") or []
        detail = (d.get("detail") or d.get("note") or "").replace('"', "'")[:160]
        head = (f'  <repair outcome="{outcome}" files="{len(files)}">{label}'
                + (f' — {detail}' if detail else ""))
        sub = followup_rows(d.get("_followup"))
        has_verify = has_verify or any(r.startswith("    <verify") for r in sub)
        rows.append(head + "</repair>" if not sub
                    else "\n".join([head] + sub + ["  </repair>"]))
    note = ("직전 자기수리의 결말이다(리로드로 그때의 턴이 끊겨 아직 사용자에게 보고되지 "
            "않았다). 사용자에게 결과를 한 문장으로 먼저 알리고, 실패·롤백이면 무엇이 "
            "원상 복구됐는지 말하라. 원래 수리의 자동 재개 인계가 있으면 그 목표·실패 증거를 "
            "따라 미완료 부분을 이어서 처리하라. 인계 없는 과거 보고만으로 새 수리를 시작하지 마라.")
    if has_verify:
        note += (" <verify> 는 네가 적용과 함께 위탁한 검증 명령을 수행자가 대신 돌린 "
                 "결과다(네 턴이 죽은 뒤에 돌았다) — 그 판정도 한 문장으로 함께 전하라.")
    mark_announced(items)
    return (f"<repair_outcome note=\"{note}\">\n" + "\n".join(rows) + "\n</repair_outcome>"
            + _staged_block(staged))


def _staged_block(staged: list) -> str:
    """미적용 스테이징 블록. 없으면 빈 문자열."""
    if not staged:
        return ""
    rows = [f'  <staged key="{s["key"]}" files="{len(s["files"])}"'
            + (' scheduled_review="true"' if s.get("stranded_scheduled") else "")
            + ">" + staged_summary(s) + " — " + ", ".join(s["files"][:6]) + "</staged>" for s in staged]
    note = ("미정리 격리 세션과 조회 시 파일 비교다. 원본 그대로는 스테이징 시작 내용과 같다는 뜻이다. "
            "기능 부재·활성화·커밋 여부는 별도 확인한다. 현재 과제에 필요한 차이만 검토하며 "
            "이 목록만으로 apply/discard하지 않는다. scheduled_review는 오래된 예약이므로 "
            "수행자·영수증을 확인한다.")
    return f"\n<repair_staged note=\"{note}\">\n" + "\n".join(rows) + "\n</repair_staged>"
