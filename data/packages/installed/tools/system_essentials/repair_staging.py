"""
repair_staging.py - 수리(REPAIR)의 격리 스테이징 (system_essentials 형제 모듈)

★왜 (2026-08-17): 헌법 2026-08-05 의 REPAIR 경로는 사용자 명령 수리에서 RED
(backend/*.py)를 **라이브에 직접** 쓴다. 그래서 편집이 부른 리로드가 편집자 자신의
턴을 끊는다 — keeper 일시정지(_keeper_pause)·분리 워치독(red_watchdog)·다음 턴 판정
회수(red_report)는 전부 그 죽음을 *사후에* 수습하는 장치다. 검증도 사후다: 사전
검증은 compile() 한 줄(구문)뿐이고, 사후 판정은 /health 200 — 즉 "프로세스가 살아는
있다" 뿐이다.

이 모듈은 순서를 뒤집는다:

    (종전)  쓴다 → 리로드 → 죽는다 → 워치독이 맥을 짚는다 → 다음 턴이 판정을 읽는다
    (신)    격리 사본에 쓴다 → 거기서 검증한다 → 통과분만 한 번에 라이브로 옮긴다

스테이징 중에는 라이브가 무변경이라 **리로드가 없고, 편집자가 살아 있다** — 자기
검증 결과를 읽고 고쳐 쓸 수 있다. 라이브가 받는 것은 언제나 검증을 통과한 내용이고,
리로드는 적용 순간 한 번이다. ★그 한 번마저 턴 밖으로 미룬다(2026-08-19 지연 적용):
backend/*.py 적용은 분리 수행자(backend/datastore/red_apply.py)가 턴 종료(응답 전송→
주행기록 END→증류 재합류)를 기다렸다가 쓰기 직전 재검증 후 수행한다 — 최종 보고·
주행기록·증류가 리로드보다 **먼저** 완료된다("자기 죽음 이후 단계는 죽음을 넘는
프로세스가 맡는다"의 적용 단계 판, 워치독 선례). frontend/scripts 만이면 리로드가
없으므로 즉시 적용한다.

★기존 안전판은 무엇도 대체하지 않는다. 적용 단계가 _red_write_prepare/
_red_write_finalize 를 그대로 통과하므로 백업·keeper 일시정지·분리 워치독·자동
롤백이 전부 이어받는다. 스테이징은 그 **앞에** 검증 층을 하나 더 놓을 뿐이다.
(라이브 프로세스의 *행동* 검증은 여전히 적용 이후다 — 격리 사본에서 잡는 것은
구조적 브릭[구문·import·삼각·안전장치 스모크]이고, 브릭 위험은 거기 산다.)

★스테이징 베이스 = 라이브 작업 트리 (HEAD 아님). worktree 는 HEAD 로 만들지만
①세션 생성 시 라이브 드리프트(미커밋·미추적 포함)를 파일 복사로 맞추고 ②파일을 처음
건드릴 때 **라이브 원본에서 씨를 뿌리며**(권위) ③검증 시마다 같은 동기화를 다시 돌려
'지금 라이브 + 세션 델타'를 본다(_sync_worktree_to_live — 2026-08-19 거짓 초록 봉합).
HEAD 를 베이스로 쓰면 미커밋 라이브 작업을 적용이 조용히 되돌린다 — 데이터 손실.

★★사정거리 (2026-08-18 정정) — 이 격리는 **파일이 아니라 문 하나**에 걸려 있다.
게이트는 handler 의 `_red_zone_write_block`(= `[self:write]`/`[self:edit]` 가 지나는 자리)
이고 그랜트는 REPAIR 경로만 발급한다. 그 문을 안 쓰는 편집자 — 아웃오브프로세스
Claude Code 세션(자체 Edit/Bash), `[self:script]{op:run}`, `run_command`, 패키지
핸들러 자신의 `open()` — 는 backend 로 **라이브 직행**하고, 게이트는 repo 루트
미탐지 시 fail-open 이다. 즉 참인 불변식은 "backend 는 격리를 거쳐야 바뀐다"가 아니라
**"REPAIR 경로는 격리를 쓴다"** 이다. 아웃오브프로세스 손은 이 프로세스 밖이라
원리적으로 차단할 수 없으므로, 우회는 차단이 아니라 **가시성**으로 다룬다 —
`scripts/check_red_drift.py`(자가점검 §1H). 정본=docs/SELF_MODIFICATION_SAFETY_DESIGN.md
'이 격리의 사정거리' 표.

원장: data/system_ai_state/repair_sessions/<task_key>.json
격리: .worktrees/repair-<task_key>/
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta

SESSION_DIRNAME = os.path.join("data", "system_ai_state", "repair_sessions")
# ★옛 제안 원장(통합 전 세대). propose 가 여기+selfpatch-* 워크트리를 따로 써서 apply 가
# 원리적으로 못 봤다(실측 08-18: 제안 7건 누적 / 적용 0건). 지금은 제안도 세션이라
# 이 경로는 **좌초 감지 읽기 전용**으로만 남는다 — list_legacy_proposals 참조.
PROPOSAL_DIRNAME = os.path.join("data", "system_ai_state", "patch_proposals")
WORKTREE_PREFIX = os.path.join(".worktrees", "repair-")
SESSION_TTL_DAYS = 7          # 이보다 오래된 종료 세션은 기회주의적으로 청소
GIT_TIMEOUT = 120
SMOKE_TIMEOUT = 180
BUILD_TIMEOUT = 300

# 안전장치 파일 — 수정되면 기능 스모크(red_safety_selftest)까지 통과해야 한다.
# red_watchdog.SAFETY_SUFFIXES 와 같은 목록(둘 다 접미사 매칭).
SAFETY_SUFFIXES = (
    "backend/datastore/red_grant.py",
    "backend/datastore/red_watchdog.py",
    "tools/system_essentials/handler.py",
    "tools/system_essentials/repair_staging.py",
    "scripts/red_safety_selftest.py",
)


# ── 기본 유틸 ─────────────────────────────────────────────────────────────

def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                          text=True, timeout=GIT_TIMEOUT)


def task_key(raw) -> str:
    """세션 키 — _red_backup_dir 과 같은 규칙(백업 폴더와 세션이 같은 이름을 갖는다)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", (raw or "notask"))[:48] or "notask"


def pending_proposals(repo: str):
    """적용 대기 제안 id 목록 — 세션 원장 하나만 읽는다(격리본 살아있는 것만)."""
    d = os.path.join(repo, SESSION_DIRNAME)
    out = []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as f:
                sess = json.load(f)
        except Exception:
            continue
        if sess.get("kind") != "proposal" or sess.get("status") != "staging":
            continue
        if os.path.isdir(os.path.join(repo, sess.get("worktree") or "")):
            out.append(sess.get("proposal_id") or sess.get("key"))
    return out


def _session_path(repo: str, key: str) -> str:
    d = os.path.join(repo, SESSION_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{key}.json")


def read_session(repo: str, key: str):
    """세션 원장 **원본** 읽기 — 상태 무관(applied/discarded 도 그대로 돌려준다).

    ★load_session 과 나누는 이유(2026-08-18 실측): load_session 은 '지금 쌓는 중인
    세션' 접근자라 staging 이 아니면 None 을 준다. 그걸 존재 판정에 쓰면 **닫힌 세션이
    '없는 것'으로 보여** ①이미 적용된 제안에 "그런 제안이 없습니다"라 답하고 ②같은 키를
    비어 있다고 판단해 재사용 → ensure_session 이 이전 격리본을 지우고 원장을 덮어쓴다
    (조용한 파괴). 존재·상태를 물을 때는 이 함수를 쓸 것.
    """
    try:
        with open(_session_path(repo, key), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_session(repo: str, key: str):
    """지금 쌓는 중인 세션 — staging 이 아니면 None. (존재 판정엔 read_session 을 쓸 것.)"""
    s = read_session(repo, key)
    return s if s and s.get("status") == "staging" else None


PROPOSAL_KEY_PREFIX = "proposal-"


def proposal_key(pid: str) -> str:
    """제안 id → 세션 키. 제안도 세션의 한 종류라 키 공간이 하나다(2026-08-18 통합)."""
    pid = (pid or "").strip()
    return pid if pid.startswith(PROPOSAL_KEY_PREFIX) else PROPOSAL_KEY_PREFIX + pid


def list_legacy_proposals(repo: str):
    """옛 patch_proposals/ 원장 — 통합 전(2026-08-18) 세대. 읽기 전용.

    통합 시점에 살아있는 제안은 0건이라 이관은 불필요했다. 그래도 이 함수를 남기는 건
    **좌초 감지**용이다 — 옛 판이 돌던 몸에서 올라온 제안이 있으면 status 가 알린다.
    """
    d = os.path.join(repo, PROPOSAL_DIRNAME)
    out = []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as f:
                prop = json.load(f)
        except Exception:
            continue
        if (prop.get("status") or "proposed") != "proposed":
            continue                       # 이미 닫힌 기록
        wt = prop.get("worktree") or ""
        if wt and os.path.isdir(os.path.join(repo, wt)):
            out.append(prop)               # 좌초: 옛 저장소에 살아있는 제안
    return out


def _save_session(repo: str, sess: dict):
    with open(_session_path(repo, sess["key"]), "w", encoding="utf-8") as f:
        json.dump(sess, f, ensure_ascii=False, indent=2)


def _is_git_repo(repo: str) -> bool:
    try:
        return _git(["rev-parse", "--git-dir"], repo).returncode == 0
    except Exception:
        return False


# ── 세션 (격리 사본) ──────────────────────────────────────────────────────

_SYNC_MAX_FILES = 4000    # 드리프트가 이보다 크면 동기화 대신 정직한 거부(저장소 비정상)


def _sync_worktree_to_live(repo: str, wt_abs: str, skip_rels=()):
    """격리 사본을 '지금 라이브 작업 트리'로 맞춘다(세션 적재분 제외). 반환 (ok, detail).

    ★왜 (2026-08-19 거짓 초록 봉합): 검증의 계약은 "이 델타를 **지금 라이브**에 얹으면
    안전한가"인데, 격리 사본의 베이스는 세 경로로 낡는다 —
      ①개설 때 미커밋 이식(git apply)이 컨텍스트 불일치로 조용히 실패 → 베이스=HEAD 잔류
        (검증은 HEAD 기준 초록, apply 는 진짜 라이브로 — 거짓 초록)
      ②세션 도중 격리 밖 파일이 라이브 직행으로 바뀜 — data/ibl_nodes_src 등은 RED 구역
        밖이라 스테이징이 안 잡는데, 삼각 검증은 그 파일을 읽는다(다른 세계 대조)
      ③제안(proposal)이 며칠 묵는 동안 라이브에 커밋이 쌓임 (낡은 베이스)
    커밋 드리프트(워크트리 베이스↔라이브 HEAD diff)와 작업 트리 드리프트(status,
    미추적 포함)를 합쳐 파일 단위 **복사**로 맞춘다 — 패치 적용이 아니라서 조용히
    실패할 자리가 없다. skip_rels(세션 적재 파일)는 안 건드린다 — 스테이징이 이긴다.
    경로는 -z(NUL 구분)로 받는다 — 한글 경로가 quotepath 로 깨지지 않게."""
    skip = set(skip_rels)

    def _excluded(r):
        return (r == ".git" or r.startswith(".git" + os.sep)
                or r.startswith(".worktrees" + os.sep))

    rels = set()
    try:
        base = _git(["rev-parse", "HEAD"], wt_abs)
        head = _git(["rev-parse", "HEAD"], repo)
        if base.returncode != 0 or head.returncode != 0:
            return False, "git rev-parse 실패: " + (base.stderr or head.stderr).strip()[:200]
        if base.stdout.strip() != head.stdout.strip():
            d = _git(["diff", "--name-only", "-z", "--no-renames",
                      base.stdout.strip(), head.stdout.strip()], repo)
            if d.returncode != 0:
                return False, "git diff 실패: " + d.stderr.strip()[:200]
            rels.update(x for x in d.stdout.split("\0") if x)
        st = _git(["status", "--porcelain", "-z", "--no-renames",
                   "--untracked-files=all"], repo)
        if st.returncode != 0:
            return False, "git status 실패: " + st.stderr.strip()[:200]
        rels.update(e[3:] for e in st.stdout.split("\0") if len(e) > 3)
        rels = {r for r in rels if r not in skip and not _excluded(r)}
        if len(rels) > _SYNC_MAX_FILES:
            return False, (f"라이브 드리프트 {len(rels)}건 — 상한({_SYNC_MAX_FILES}) 초과. "
                           f"저장소 상태가 비정상입니다(.gitignore 붕괴 등) — 낡은 베이스로 "
                           f"검증하는 대신 거부합니다.")
        copied = removed = 0
        for rel in sorted(rels):
            live_p = os.path.join(repo, rel)
            wt_p = os.path.join(wt_abs, rel)
            if os.path.isfile(live_p):
                os.makedirs(os.path.dirname(wt_p), exist_ok=True)
                shutil.copy2(live_p, wt_p)
                copied += 1
            elif os.path.lexists(wt_p):
                os.remove(wt_p)            # 라이브에서 사라진 파일 — 격리에서도 지운다
                removed += 1
        return True, f"라이브 동기화 {copied + removed}건 (복사 {copied}·삭제 {removed})"
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"동기화 실패: {e}"


def ensure_session(repo: str, key: str):
    """스테이징 세션 확보 — 없으면 worktree 를 만든다. 실패 시 None(=라이브 직행 폴백)."""
    sess = load_session(repo, key)
    if sess and os.path.isdir(os.path.join(repo, sess["worktree"])):
        return sess
    # ★적용 예약(apply_scheduled) 세션에 같은 키의 쓰기가 이어지면 staging 으로 재개봉한다
    #   — 예약 스냅샷이 낡아지므로 수행자(red_apply)가 상태를 보고 그 예약을 취소한다.
    #   재개봉 없이 두면 아래 '잔재 정리'가 예약분 워크트리를 지워버린다(예약 파괴).
    full = read_session(repo, key)
    if (full and full.get("status") == "apply_scheduled"
            and os.path.isdir(os.path.join(repo, full.get("worktree") or ""))):
        full["status"] = "staging"
        full.pop("scheduled_at", None)
        _save_session(repo, full)
        print("[수리 스테이징] 적용 예약 세션에 쓰기 재개 — 예약 취소, staging 재개봉")
        return full
    if not _is_git_repo(repo):
        return None                      # git 없는 몸 — 스테이징 불가, 종전 경로로
    wt_rel = WORKTREE_PREFIX + key
    wt_abs = os.path.join(repo, wt_rel)
    if os.path.isdir(wt_abs):            # 원장만 사라진 잔재 — 재사용 대신 정리
        _git(["worktree", "remove", "--force", wt_abs], repo)
    add = _git(["worktree", "add", "--detach", wt_abs, "HEAD"], repo)
    if add.returncode != 0:
        print(f"[수리 스테이징] worktree 생성 실패 — 스테이징 없이 진행: {add.stderr.strip()[:200]}")
        return None
    # 라이브 드리프트(미커밋·미추적)를 격리 사본에 맞춘다 — ★best-effort 가 아니다.
    # 옛 구현(git diff HEAD | git apply)은 ①추적 파일 한정이라 미추적 신규 모듈이 빠져
    # import 스모크가 거짓 빨강을 냈고 ②컨텍스트 불일치로 조용히 실패하면 베이스가 HEAD 로
    # 남아 검증이 HEAD 기준 초록을 냈다(거짓 초록 — 2026-08-19 봉합). 동기화가 안 되면
    # 격리는 거짓말을 하므로 세션 자체를 거부한다 → 호출자는 종전 라이브 직행 경로
    # (구문검증+백업+워치독)로 폴백한다(S5b 와 같은 착지 — 격리 없음 > 거짓 격리).
    ok, detail = _sync_worktree_to_live(repo, wt_abs)
    if not ok:
        print(f"[수리 스테이징] 베이스 동기화 실패 — 스테이징 없이 진행: {detail}")
        _git(["worktree", "remove", "--force", wt_abs], repo)
        return None
    # ★주인 — 미적용 스테이징(<repair_staged>)과 지연 적용 결말이 **명령한 창으로**
    #   돌아가게 하는 열쇠. 규칙은 red_report 한 곳에만 둔다(생산자·소비자 동형, 08-25).
    sess = {"key": key, "worktree": wt_rel, "status": "staging",
            "created_at": datetime.now().isoformat(), "owner": _repair_owner(), "files": {}}
    _save_session(repo, sess)
    print(f"[수리 스테이징] 격리 사본 개설: {wt_rel} — 라이브는 이 세션이 적용될 때까지 무변경")
    return sess


def staged_path(repo: str, key: str, live_abs: str):
    """이미 스테이징된 파일의 격리 사본 경로 — 아니면 None(읽기 리다이렉션 판정용)."""
    sess = load_session(repo, key)
    if not sess:
        return None
    rec = (sess.get("files") or {}).get(live_abs)
    return rec.get("staged") if rec else None


def _rel_in_repo(repo: str, live_abs: str):
    try:
        rel = os.path.relpath(live_abs, repo)
    except ValueError:
        return None
    return None if rel.startswith("..") else rel


def can_stage(repo: str, key: str, live_abs: str) -> bool:
    """이 경로를 세션에 적재할 수 있는가 — 이동처럼 **양쪽이 다 되어야** 하는 연산에서
    한쪽만 적재되고 다른 쪽이 라이브로 새는 반쪽 상태를 막기 위한 선판정."""
    if not repo or not key or _rel_in_repo(repo, live_abs) is None:
        return False
    return ensure_session(repo, key) is not None


def stage_file(repo: str, key: str, live_abs: str):
    """쓰기 대상을 격리 사본 경로로 바꾼다(첫 접촉 시 라이브 원본에서 씨 뿌리기).

    반환: 격리 사본 절대경로. 스테이징 불가(git 없음 등)면 None → 호출자는 라이브 직행."""
    sess = ensure_session(repo, key)
    if not sess:
        return None
    rel = _rel_in_repo(repo, live_abs)
    if rel is None:
        return None                       # repo 밖 — 스테이징 대상 아님
    wt_abs = os.path.join(repo, sess["worktree"])
    st_abs = os.path.join(wt_abs, rel)
    files = sess.setdefault("files", {})
    rec = files.get(live_abs)
    if rec is None or rec.get("op") == "delete":
        # 삭제로 적재됐던 경로에 다시 쓰면 '쓰기'가 이긴다(지웠다가 다시 만든 경우)
        os.makedirs(os.path.dirname(st_abs), exist_ok=True)
        existed = os.path.exists(live_abs)
        if existed and not os.path.exists(st_abs):
            shutil.copy2(live_abs, st_abs)     # ★씨는 라이브에서 — HEAD 가 아니다
        files[live_abs] = {"op": "write", "staged": st_abs, "rel": rel, "existed": existed}
        _save_session(repo, sess)
    return st_abs


def stage_delete(repo: str, key: str, live_abs: str) -> bool:
    """삭제를 세션에 적재 — 라이브 파일은 그대로 두고, 격리 사본에서만 지운다.

    격리 사본에서 실제로 지우는 이유: 그래야 검증(IBL 삼각 빌드·참조 검사)이 **그 파일이
    없는 세계**를 본다. 라이브 삭제는 apply 가 백업을 뜬 뒤에 한다."""
    sess = ensure_session(repo, key)
    if not sess:
        return False
    rel = _rel_in_repo(repo, live_abs)
    if rel is None:
        return False
    wt_abs = os.path.join(repo, sess["worktree"])
    st_abs = os.path.join(wt_abs, rel)
    try:
        if os.path.exists(st_abs):
            os.remove(st_abs)
    except OSError as e:
        print(f"[수리 스테이징] 격리 사본 삭제 실패(계속): {e}")
    sess.setdefault("files", {})[live_abs] = {
        "op": "delete", "rel": rel, "staged": st_abs, "existed": os.path.exists(live_abs)}
    _save_session(repo, sess)
    return True


# ── 검증 배터리 (격리 사본 안에서만) ──────────────────────────────────────

def _module_name(rel: str, base_abs: str = None):
    """backend 하위 .py → import 스모크가 실제로 쓸 수 있는 모듈명.

    ★backend 안에 두 규약이 공존한다(2026-08-18 실측):
      · 층 디렉토리(base·datastore·ibl·cognition·services·surface) = `__init__.py` **없음**
        → boot_paths 가 각 디렉토리를 sys.path 에 올려 **평면 이름**(`import ibl_engine`)
      · 진짜 패키지(drivers·providers·channels·common) = `__init__.py` **있음**
        → backend/ 가 sys.path 라 **점 표기**(`import providers.claude_code`)
    옛 구현은 전부 평면으로 뭉개서 후자를 `ModuleNotFoundError` 로 무조건 탈락시켰다.
    제안 내용과 무관하게 import_smoke 가 ✗ 라 **apply 가 영원히 막혔다**
    (실측: backend/drivers/sqlite_driver.py · backend/providers/claude_code.py 제안 2건).
    디렉토리 목록을 박지 않고 `__init__.py` 존재로 판정한다 — 새 패키지가 생겨도 따라온다.
    """
    if not (rel.startswith("backend" + os.sep) and rel.endswith(".py")):
        return None
    base = os.path.basename(rel)
    if base == "__init__.py":
        return None
    mod = base[:-3]
    if not base_abs:
        return mod
    parts = rel.split(os.sep)                     # backend, <디렉토리...>, 파일.py
    pkg = []
    for i in range(1, len(parts) - 1):
        d = os.path.join(base_abs, *parts[:i + 1])
        if not os.path.exists(os.path.join(d, "__init__.py")):
            pkg = []                              # 층 디렉토리 — 평면 이름
            break
        pkg.append(parts[i])
    return ".".join(pkg + [mod]) if pkg else mod


def _smoke_env(wt_abs: str):
    """격리 사본을 향하는 환경 — ★라이브 INDIEBIZ_BASE_PATH 를 물려받으면 스모크가
    라이브 data/ 를 건드린다(격리가 깨진다)."""
    env = dict(os.environ)
    env["INDIEBIZ_BASE_PATH"] = wt_abs
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _orphan_importers(wt_abs: str, mod: str, dropped_rels: set):
    """격리 사본에서 `mod` 를 아직 import 하는 파일들 — 삭제가 남길 고아 참조.

    ★왜 별도 검사인가: 쓰기의 위험은 *그 파일이 깨지는* 것이라 그 모듈만 import 해보면
    잡힌다. 삭제의 위험은 반대다 — **남의 import 가 깨진다**. 지워진 모듈은 import 해볼
    수도 없으니(없는 게 정상) 스모크로는 원리적으로 안 잡힌다."""
    esc = re.escape(mod)
    pats = [r"^\s*(?:from\s+%s\s+import|import\s+%s\b)" % (esc, esc)]
    if "." in mod:
        # 패키지 내부 상대 import — providers/__init__.py 의 `from .claude_code import ...`
        # 는 점 표기 패턴에 안 걸린다. 삭제 고아 검출에서 가장 가까운 참조를 놓치는 자리.
        pats.append(r"^\s*from\s+\.%s\s+import" % re.escape(mod.rsplit(".", 1)[-1]))
    pat = re.compile("|".join(pats), re.MULTILINE)
    hits = []
    try:
        listed = subprocess.run(["git", "ls-files", "*.py"], cwd=wt_abs,
                                capture_output=True, text=True, timeout=GIT_TIMEOUT).stdout
    except Exception:
        return hits
    for rel in listed.splitlines():
        if not rel or rel in dropped_rels:
            continue
        try:
            with open(os.path.join(wt_abs, rel), encoding="utf-8", errors="replace") as f:
                if pat.search(f.read()):
                    hits.append(rel)
        except OSError:
            continue
        if len(hits) >= 12:
            break
    return hits


_TSC_ERR = re.compile(r"^(?P<file>[^(]+)\((?P<line>\d+),(?P<col>\d+)\):\s+(?P<rest>error TS\d+:.*)$")


def _tsc_errors(text: str):
    """tsc 출력 → **자리(줄·칸)를 뺀** 오류 집합. 델타 판정용 — 델타가 줄 번호를 밀면
    같은 선행 오류가 새 오류로 보인다(파일+메시지로만 동일성 판정)."""
    out = set()
    for ln in (text or "").splitlines():
        m = _TSC_ERR.match(ln.strip())
        if m:
            out.add((m.group("file").strip(), m.group("rest").strip()))
    return out


def _run_tsc(fe_dir: str, tsc_bin: str, wt_abs: str):
    p = subprocess.run([tsc_bin, "-p", "tsconfig.app.json", "--noEmit"], cwd=fe_dir,
                       capture_output=True, text=True, timeout=SMOKE_TIMEOUT,
                       env=_smoke_env(wt_abs))
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def _tsc_check(repo: str, wt_abs: str, ts_rels: list):
    """frontend 타입검사 관문 (2026-08-22 신설).

    ★왜: RED 구역은 `("backend", "frontend", "scripts")` 인데 관문은 전부 파이썬용이라
    **타입은 아무도 안 봤다** — 실측으로 이 경로를 이미 `.tsx`/`.ts` 10건이 무검사로
    통과했다(NarrationStudio.tsx 등). 브릭은 아니지만(프런트가 깨져도 백엔드는 산다)
    빌드 때까지 조용한 부류다.

    두 가지를 **빌린다**:
    - `node_modules` — 의존성은 델타가 아니다. 워크트리는 HEAD 로 뜨고 node_modules 는
      gitignore 라 없으므로 라이브 것을 심링크로 읽고 **검증 후 즉시 회수**한다(격리
      사본에 남기면 워크트리 청소가 라이브를 향하게 된다).
    - **선행 상태** — 실패했을 때만 라이브에서 한 번 더 돌려(읽기 전용·noEmit) 델타가
      *새로* 만든 오류만 빨강으로 친다. 선행 파손이 무관한 수리를 볼모로 잡지 않게
      (`build --check` 를 격리에 못 들인 것과 같은 이유가 여기선 이렇게 풀린다).

    ★검사할 수 없으면 초록도 빨강도 아닌 **건너뜀**을 적는다 — node_modules 없는 몸에서
    apply 가 영원히 막히는 것은 import 스모크가 패키지 모듈을 탈락시켜 apply 를 막던
    2026-08-18 부류의 재생산이다. 대신 침묵하지 않는다(사유를 detail 에 적는다).
    """
    gate = {"gate": "frontend_tsc", "files": ts_rels[:12]}
    fe_wt = os.path.join(wt_abs, "frontend")
    if not os.path.exists(os.path.join(fe_wt, "tsconfig.app.json")):
        return dict(gate, passed=True, skipped=True,
                    detail="frontend/tsconfig.app.json 없음 — 타입검사 건너뜀")

    nm_wt = os.path.join(fe_wt, "node_modules")
    nm_live = os.path.join(repo, "frontend", "node_modules")
    borrowed = False
    if not os.path.exists(nm_wt):
        if not os.path.isdir(nm_live):
            return dict(gate, passed=True, skipped=True,
                        detail="frontend/node_modules 미설치 — 타입검사 불가"
                               "(npm install 후 재검증하면 이 관문이 켜집니다)")
        try:
            os.symlink(nm_live, nm_wt)
            borrowed = True
        except OSError as e:
            return dict(gate, passed=True, skipped=True,
                        detail=f"node_modules 를 빌리지 못함 — 타입검사 건너뜀 ({e})")

    tsc_bin = os.path.join(nm_wt, ".bin", "tsc")
    try:
        if not os.path.exists(tsc_bin):
            return dict(gate, passed=True, skipped=True,
                        detail="node_modules/.bin/tsc 없음 — 타입검사 건너뜀")
        try:
            rc, out = _run_tsc(fe_wt, tsc_bin, wt_abs)
        except (OSError, subprocess.SubprocessError) as e:
            return dict(gate, passed=True, skipped=True,
                        detail=f"tsc 실행 실패 — 타입검사 건너뜀 ({e})")
        if rc == 0:
            return dict(gate, passed=True, detail="타입 오류 없음")

        # 실패 — 선행 상태와 대조해 '이 델타가 만든 오류'만 빨강으로
        after = _tsc_errors(out)
        base_bin = os.path.join(nm_live, ".bin", "tsc")
        before = None
        if after and os.path.exists(base_bin):
            try:
                # ★선행 상태 실측 — 라이브 소스를 읽기만 한다(noEmit·incremental 없음).
                #   _smoke_env 에 라이브 루트를 넘기지 않는다(격리 규약: 라이브
                #   INDIEBIZ_BASE_PATH 를 물려주지 않는다 — tsc 는 안 읽지만 규약을 지킨다).
                _, base_out = _run_tsc(os.path.join(repo, "frontend"), base_bin,
                                       os.path.join(repo, "frontend"))
                before = _tsc_errors(base_out)
            except (OSError, subprocess.SubprocessError):
                before = None
        if before is not None:
            new = after - before
            if not new:
                return dict(gate, passed=True, preexisting=len(after),
                            detail=(f"타입 오류 {len(after)}건은 전부 **선행 파손**"
                                    f"(이 델타가 만든 것 아님) — 통과시킵니다.\n"
                                    + out[-800:]))
            return dict(gate, passed=False, preexisting=len(after) - len(new),
                        detail=(f"이 델타가 만든 타입 오류 {len(new)}건"
                                f"(선행 {len(after) - len(new)}건 제외):\n"
                                + "\n".join(f"{f}: {m}" for f, m in sorted(new))[:1500]))
        return dict(gate, passed=False, detail=out[-1500:])
    finally:
        if borrowed:
            try:
                os.unlink(nm_wt)           # ★심링크만 끊는다(라이브는 못 건드린다)
            except OSError:
                pass


def verify(repo: str, sess: dict):
    """격리 사본에서 기계 검증. (통과여부, checks[]) — 자기채점 아닌 pass/fail 기계값."""
    wt_abs = os.path.join(repo, sess["worktree"])
    recs = list((sess.get("files") or {}).values())
    rels = [r["rel"] for r in recs if r.get("op") != "delete"]
    del_rels = [r["rel"] for r in recs if r.get("op") == "delete"]
    checks = []
    py = sys.executable or "python3"       # ★venv 파이썬 — 시스템 python3 는 의존성이 없다

    # ★베이스 신선도 — 격리 사본을 '지금 라이브 + 세션 델타'로 동기화한 뒤에만 관문을
    # 돌린다. 안 그러면 세션 개설 후의 라이브 변화(격리 밖 파일 직행 편집·새 커밋·개설 때
    # 이식 실패 잔재)를 못 본 채 초록을 낸다(거짓 초록 — 2026-08-19 봉합).
    ok_sync, sync_detail = _sync_worktree_to_live(
        repo, wt_abs, skip_rels={r["rel"] for r in recs})
    checks.append({"gate": "live_sync", "passed": ok_sync, "detail": sync_detail[:800]})
    if not ok_sync:
        return False, checks               # 낡은 베이스 위의 관문은 초록도 빨강도 못 믿는다

    # 0. 삭제 — 남는 쪽의 import 가 깨지지 않는지 (삭제 고유의 위험)
    if del_rels:
        dropped = set(del_rels)
        orphans = {}
        for rel in del_rels:
            mod = _module_name(rel, wt_abs)
            if not mod:
                continue
            hits = _orphan_importers(wt_abs, mod, dropped)
            if hits:
                orphans[mod] = hits
        checks.append({
            "gate": "delete_no_orphan_imports", "passed": not orphans,
            "deleted": del_rels,
            "detail": ("" if not orphans else "삭제하려는 모듈을 아직 import 하는 파일: "
                       + "; ".join(f"{m} ← {', '.join(v)}" for m, v in orphans.items()))[:1200],
        })

    # 1. 구문 (모든 .py)
    py_rels = [r for r in rels if r.endswith(".py")]
    if py_rels:
        p = subprocess.run([py, "-m", "py_compile"] + [os.path.join(wt_abs, r) for r in py_rels],
                           capture_output=True, text=True, timeout=SMOKE_TIMEOUT,
                           env=_smoke_env(wt_abs))
        checks.append({"gate": "py_compile", "passed": p.returncode == 0,
                       "detail": ((p.stdout or "") + (p.stderr or "")).strip()[-800:]})

    # 2. import 스모크 — ★사전 compile() 이 못 잡는 부류(ImportError·모듈 최상위
    #    NameError·순환 import)를 여기서 잡는다. 브릭의 실제 원인 대부분이 여기 산다.
    mods = sorted({m for m in (_module_name(r, wt_abs) for r in rels) if m})
    if mods:
        code = "import boot_paths\n" + "".join(f"import {m}\n" for m in mods)
        p = subprocess.run([py, "-c", code], cwd=os.path.join(wt_abs, "backend"),
                           capture_output=True, text=True, timeout=SMOKE_TIMEOUT,
                           env=_smoke_env(wt_abs))
        checks.append({"gate": "import_smoke", "passed": p.returncode == 0,
                       "modules": mods,
                       "detail": ((p.stdout or "") + (p.stderr or "")).strip()[-1500:]})

    # 3. IBL 삼각 검증 (src ↔ tool.json ↔ handler)
    #    ★--check 의 코퍼스/fixture 검사는 런타임 DB·미추적 파생물에 의존해 격리
    #    사본에서 못 돈다 → plain build(삼각)까지가 격리에서 가능한 최대치.
    build = os.path.join(wt_abs, "scripts", "build_ibl_nodes.py")
    if os.path.exists(build):
        p = subprocess.run([py, "scripts/build_ibl_nodes.py"], cwd=wt_abs,
                           capture_output=True, text=True, timeout=BUILD_TIMEOUT,
                           env=_smoke_env(wt_abs))
        checks.append({"gate": "ibl_triangle", "passed": p.returncode == 0,
                       "detail": ((p.stdout or "") + (p.stderr or "")).strip()[-800:]})

    # 4. frontend 타입검사 — RED 구역에 frontend 가 있으므로 .ts/.tsx 도 이 층을 지난다.
    #    삭제도 방아쇠에 넣는다: 지워진 모듈을 아직 import 하는 쪽은 파이썬만 고아 검사가
    #    있고(delete_no_orphan_imports) 프런트는 없었는데, 격리 사본엔 이미 그 파일이
    #    없으므로 tsc 가 그대로 잡는다.
    ts_rels = [r for r in (rels + del_rels)
               if r.replace(os.sep, "/").startswith("frontend/")
               and r.endswith((".ts", ".tsx"))]
    if ts_rels:
        checks.append(_tsc_check(repo, wt_abs, ts_rels))

    # 5. 안전장치를 고쳤으면(지웠으면 더더욱) 기능 스모크까지 — 게이트를 고치다 게이트를
    #    죽여도 서버는 멀쩡히 뜬다 = 침묵 결함이라 /health 로는 못 잡는다
    if any(r.replace(os.sep, "/").endswith(s) for r in (rels + del_rels) for s in SAFETY_SUFFIXES):
        st = os.path.join(wt_abs, "scripts", "red_safety_selftest.py")
        if os.path.exists(st):
            p = subprocess.run([py, "scripts/red_safety_selftest.py"], cwd=wt_abs,
                               capture_output=True, text=True, timeout=SMOKE_TIMEOUT,
                               env=_smoke_env(wt_abs))
            checks.append({"gate": "safety_selftest", "passed": p.returncode == 0,
                           "detail": ((p.stdout or "") + (p.stderr or "")).strip()[-800:]})

    return all(c["passed"] for c in checks), checks


# ── 지연 적용 (2026-08-19) ────────────────────────────────────────────────

def _reload_triggering(sess: dict) -> bool:
    """이 적용이 uvicorn 리로드를 부르는가 — backend/**.py 가 하나라도 끼면 참.

    uvicorn 은 reload=True(reload_delay 2초)로 backend 를 감시한다. frontend/scripts 는
    라이브 프로세스가 import 하지 않아 즉시 적용해도 이 턴이 죽지 않는다."""
    for r in (sess.get("files") or {}).values():
        rel = (r.get("rel") or "").replace(os.sep, "/")
        if rel.startswith("backend/") and rel.endswith(".py"):
            return True
    return False


def _current_episode_id(repo: str = None, agent_id: str = None):
    """지금 턴의 주행기록 행 id — 수행자가 '턴이 닫혔다'를 이 행의 ended_at 으로 판정한다.

    ★contextvar 폴백(2026-08-20 ep1265·1267): apply 가 claude_code 의 MCP→HTTP
    재진입 스레드로 들어오면 EpisodeLogger.current() 가 None 이다(agent_id·task_id
    전파 유실과 같은 부류 — task_id 는 그랜트 매칭으로 수리됐지만 episode_id 는
    빠져 있었다). 그러면 수행자가 10초 유예 후 라이브를 써서 리로드가 아직 열려
    있는 턴을 끊는다. 폴백: 그 에이전트의 열린(ended_at 없는) 최신 행 = 지금 턴.

    ★agent 필터는 참고일 뿐 최종이 아니다(2026-08-20 ep1282): agent_id 도 같은
    오염원(재진입 스레드 문맥→그랜트)에서 온다 — 'agent_001' 이 실려 필터가 열린
    system_ai 턴을 놓치고 null 을 반환, 수행자가 10초 유예로 떨어져 턴을 끊었다.
    예약은 턴이 열려 있는 동안 일어나므로 무필터 열린 최신 행이 곧 이 턴이다.

    ★단 시험 유래 행은 후보가 아니다(2026-08-22 B18-2): 시험 프로세스가 start 만 하고
    끝내지 않은 행은 다음 부팅의 고아 회수 전까지 영원히 ended_at NULL 이라, 무필터
    폴백이 그걸 집으면 수행자가 죽은 턴을 상한까지 기다린다."""
    try:
        from episode_logger import EpisodeLogger
        eid = getattr(EpisodeLogger.current(), "episode_id", None)
        if eid:
            return eid
    except Exception:
        pass
    if not repo:
        return None
    try:
        import sqlite3
        db = os.path.join(repo, "data", "world_pulse.db")
        if not os.path.exists(db):
            return None
        conn = sqlite3.connect(db, timeout=5)
        row = None
        if agent_id:
            row = conn.execute(
                "SELECT id FROM episode_log WHERE ended_at IS NULL AND agent=? "
                "AND COALESCE(source, 'usage') <> 'test' "
                "ORDER BY id DESC LIMIT 1", (agent_id,)).fetchone()
        if not row:
            row = conn.execute(
                "SELECT id FROM episode_log WHERE ended_at IS NULL "
                "AND COALESCE(source, 'usage') <> 'test' "
                "ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _grant_identity():
    """현재 그랜트의 (task_id, agent_id, reason) — 잡 파일로 수행자에게 이월된다."""
    try:
        from red_grant import active_grant
        from thread_context import get_current_task_id, get_current_agent_id
        g = active_grant(task_id=get_current_task_id(), agent_id=get_current_agent_id())
        if g:
            return g.get("task_id") or "", g.get("agent_id") or "", g.get("reason") or ""
    except Exception:
        pass
    return "", "", ""


def _repair_owner() -> str:
    """이 수리를 하는 주체의 열쇠 — 규칙은 red_report 한 곳에만 둔다(생산자·소비자 동형)."""
    try:
        from red_report import current_owner
        return current_owner()
    except Exception:
        return "system_ai"


def _write_deferred_result(repo: str, key_str: str, payload: dict, owner: str = None):
    """수행자 단계의 결말을 red_report 가 줍는 자리(red_backups/<key>/result.json)에 남긴다
    — 워치독 판정과 같은 형식·같은 회수 경로라 다음 턴에 반드시 보고된다.

    ★owner 는 **세션 원장에서** 온다 — 이 함수는 분리 수행자(red_apply) 프로세스에서
    도는데, 거기엔 수리한 에이전트의 스레드 컨텍스트가 없다. 지금 여기서 물으면
    언제나 '시스템 AI' 라는 오답이 나온다."""
    try:
        bdir = os.path.join(repo, "data", "system_ai_state", "red_backups", key_str)
        os.makedirs(bdir, exist_ok=True)
        payload = dict(payload)
        payload.setdefault("finished_at", time.time())
        payload.setdefault("owner", owner or "system_ai")
        with open(os.path.join(bdir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[수리 스테이징] 지연 결과 기록 실패(계속): {e}")


def write_followup(repo: str, key_str: str, payload: dict):
    """수행자가 남기는 **후속 기록** — result.json 옆자리(followup.json).

    ★왜 옆자리냐: 성공 경로의 result.json 은 나중에 워치독이 헬스 판정으로 **통째로
    덮는다**. 수행자가 먼저 쓰면 사라진다. 같은 폴더의 다른 파일이면 둘이 안 부딪히고,
    회수하는 쪽(red_report)은 판정을 집을 때 옆을 한 번 더 보면 된다."""
    try:
        bdir = os.path.join(repo, "data", "system_ai_state", "red_backups", key_str)
        os.makedirs(bdir, exist_ok=True)
        payload = dict(payload)
        payload.setdefault("finished_at", time.time())
        with open(os.path.join(bdir, "followup.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[수리 스테이징] 후속 기록 실패(계속): {e}")


def _turn_cap_s() -> int:
    """수행자의 턴 종료 대기 상한 — **출처는 red_apply 하나**(문구와 실제가 갈라지지 않게)."""
    try:
        import red_apply
        return int(red_apply.TURN_CLOSE_CAP_S)
    except Exception:
        return 900      # 수행자를 못 읽는 자리(가짜 저장소 시험 등) — 문구용 폴백


def _schedule_deferred_apply(repo: str, sess: dict, checks: list, verify_cmd: str = ""):
    """지연 적용 예약 — 라이브 쓰기를 '이 턴이 닫힌 뒤'로 미뤄 분리 수행자에 맡긴다.

    반환: 응답 dict / None(예약 불능 → 호출자가 즉시 적용으로 폴백).
    수행자(red_apply)는 ①주행기록 ended_at(=응답 전송·버퍼 저장 완료) ②증류 재합류
    (refresh_episode 의 log 재기록)를 기다린 뒤 쓰기 직전 재검증하고 적용한다."""
    key = sess["key"]
    job_path = os.path.join(repo, SESSION_DIRNAME, f"{key}.apply.json")
    # 수행자 스크립트는 코드 루트(이 모듈이 사는 저장소) 기준 — 대상 repo 에 없으면
    # (테스트의 가짜 저장소 등) 코드 루트 것을 쓴다.
    script = os.path.join(repo, "backend", "datastore", "red_apply.py")
    if not os.path.exists(script):
        code_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 *[os.pardir] * 5))
        script = os.path.join(code_root, "backend", "datastore", "red_apply.py")
        if not os.path.exists(script):
            return None
    task_id, agent_id, reason = _grant_identity()
    job = {"key": key, "repo": repo,
           "episode_id": _current_episode_id(repo, agent_id or "system_ai"),
           "task_id": task_id or key, "agent_id": agent_id or "system_ai",
           "reason": reason, "scheduled_at": datetime.now().isoformat(),
           "verify_cmd": (verify_cmd or "").strip(),
           "handler_path": os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "handler.py")}
    try:
        with open(job_path, "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False, indent=2)
        if not os.environ.get("INDIEBIZ_REPAIR_NO_SPAWN"):   # 테스트 심 — 수행자는 직접 기동
            log = open(job_path + ".log", "ab")
            subprocess.Popen([sys.executable, script, job_path],
                             stdout=log, stderr=log, start_new_session=True, cwd=repo)
    except Exception as e:
        print(f"[수리 스테이징] 지연 적용 예약 실패: {e}")
        try:
            os.remove(job_path)
        except OSError:
            pass
        return None
    sess["status"] = "apply_scheduled"
    sess["scheduled_at"] = job["scheduled_at"]
    sess["checks"] = checks
    _save_session(repo, sess)
    rels = [r.get("rel") for r in (sess.get("files") or {}).values()]
    # ★"기다리는 그 턴이 곧 당신이다" 를 기계가 들이민다 (2026-08-25, ep1934 실측)
    #   — 옛 문구는 "이 턴이 닫힌 뒤 적용된다"까지만 말했다. 사실로는 맞지만, 예약을 낸
    #   AI 는 자기 턴이 **그 병목이라는 것**을 읽지 못하고 턴 안에서 적용을 폴링했다.
    #   그러면 적용은 영영 안 오고 대기 상한이 통째로 타며, 안전망이던 상한이 시간표가 된다.
    #   episode_id 는 이미 잡에 있다 — 없던 것은 정보가 아니라 **자기수용감각**이었다.
    eid = job.get("episode_id")
    _cap = _turn_cap_s()
    _who = f"지금 이 턴(주행기록 {eid})" if eid else "지금 이 턴"
    _verify_note = (
        f"위탁한 검증 명령(`{job['verify_cmd'][:120]}`)도 적용 뒤 수행자가 대신 돌려 "
        f"결과를 같은 보고에 실어 보냅니다."
        if job.get("verify_cmd") else
        "적용 뒤 확인할 것이 있으면 apply 에 verify_cmd 로 명령을 함께 맡기세요 — "
        "수행자가 적용 후 돌려 다음 턴에 보고합니다. 이 턴에서 기다려서는 볼 수 없습니다.")
    return {
        "success": True, "applied": False, "scheduled": True, "verified": True,
        "checks": [{"gate": c["gate"], "passed": True} for c in checks],
        "files": rels,
        "waiting_on_episode": eid,
        "do_not_wait": True,
        "message": (f"검증 통과 — 라이브 적용을 예약했습니다({len(rels)}건). "
                    f"★{_who}이 닫혀야 적용이 일어납니다 — 기다리는 대상이 곧 당신입니다. "
                    f"그러니 이 턴에서 적용을 기다리거나 폴링하지 마십시오. 기다리면 적용은 "
                    f"오지 않고 대기 상한 {_cap}초를 통째로 태운 뒤에야 강행됩니다. "
                    f"**지금 턴을 닫는 것이 이 작업의 완결입니다.** "
                    f"턴이 닫히면(응답 전송·주행기록 저장·증류 완료) 분리 수행자가 쓰기 직전 "
                    f"재검증 후 적용하고, 리로드는 그때 한 번 일어납니다. 적용·헬스 판정은 "
                    f"다음 턴에 자동으로 보고됩니다. {_verify_note} "
                    f"사용자에게는 '검증 통과, 적용 예약됨'으로 알리세요 — "
                    f"아직 라이브에 반영되지 않았습니다."),
        "worktree": sess["worktree"],
    }


def perform_scheduled_apply(repo: str, key: str, prepare=None, finalize=None):
    """예약된 적용의 실제 수행 — 분리 수행자(red_apply)가 턴 종료 대기 후 부른다.

    ★쓰기 직전 재검증: 예약~수행 사이에도 라이브는 변할 수 있다(그 창도 세계다).
    verify 의 live_sync 가 그 드리프트까지 맞춘 뒤 관문을 다시 돌린다. 실패하면
    라이브 무변경 + 세션은 staging 으로 되돌아가(<repair_staged> 가 계속 문다)
    결말은 result.json 으로 다음 턴에 보고된다. 멱등: 이미 적용된 세션은 no-op."""
    sess = read_session(repo, key)
    if not sess:
        return {"success": False, "applied": False, "error": f"세션 원장이 없습니다: {key}"}
    key_str = task_key(sess.get("key") or key)
    _owner = sess.get("owner")   # 수리한 에이전트 — 이 프로세스는 그를 알 길이 없다
    rels = [r.get("rel") for r in (sess.get("files") or {}).values()]
    st = sess.get("status")
    if st == "applied":
        return {"success": True, "applied": True, "note": "이미 적용됨(중복 수행 무시)"}
    if st != "apply_scheduled":
        # 예약 뒤 같은 세션에 쓰기가 이어지면 ensure_session 이 staging 으로 재개봉한다
        # — 그 예약 스냅샷은 낡았으므로 취소가 맞다(세션은 <repair_staged> 로 계속 보인다).
        _write_deferred_result(repo, key_str, {
            "outcome": "deferred_canceled", "files": rels,
            "note": f"예약 후 세션 상태가 '{st}' 로 바뀌어 적용을 취소했습니다(스냅샷 낡음)."},
            owner=_owner)
        return {"success": False, "applied": False,
                "error": f"세션 상태 {st} — 예약이 낡아 취소했습니다(라이브 무변경)."}
    if not os.path.isdir(os.path.join(repo, sess.get("worktree") or "")):
        sess["status"] = "discarded"
        sess["discarded_at"] = datetime.now().isoformat()
        sess["note"] = "격리 사본 소실로 예약 적용 불능"
        _save_session(repo, sess)
        _write_deferred_result(repo, key_str, {
            "outcome": "deferred_apply_failed", "files": rels,
            "note": "격리 사본이 사라져 예약 적용을 수행할 수 없었습니다 — 다시 수리하세요."},
            owner=_owner)
        return {"success": False, "applied": False, "error": "격리 사본 소실"}
    ok, checks = verify(repo, sess)
    if not ok:
        failed = [c["gate"] for c in checks if not c["passed"]]
        sess["status"] = "staging"
        sess.pop("scheduled_at", None)
        sess["checks"] = checks
        _save_session(repo, sess)
        _write_deferred_result(repo, key_str, {
            "outcome": "deferred_verify_failed", "files": rels,
            "note": (f"쓰기 직전 재검증 실패({', '.join(failed)}) — 예약~수행 사이 라이브가 "
                     f"변했습니다. 라이브 무변경, 수정분은 격리 사본에 보존.")},
            owner=_owner)
        return {"success": False, "applied": False, "verified": False,
                "checks": checks, "failed_gates": failed,
                "error": f"쓰기 직전 재검증 실패({', '.join(failed)}) — 라이브 무변경"}
    out = _perform_apply(repo, sess, checks, prepare, finalize)
    if not out.get("applied"):
        cur = read_session(repo, key)
        if cur and cur.get("status") == "apply_scheduled":
            cur["status"] = "staging"
            cur.pop("scheduled_at", None)
            _save_session(repo, cur)
        _write_deferred_result(repo, key_str, {
            "outcome": "deferred_apply_failed", "files": rels,
            "note": (out.get("error") or out.get("message") or "적용 단계 오류")[:400]},
            owner=_owner)
    return out


# ── op: apply / status / discard ──────────────────────────────────────────

def _ctx(ti):
    return (ti.get("_repo_root"), ti.get("_grant_key"))


def op_apply(ti):
    """검증 통과분의 라이브 반영 — backend/*.py 는 ★지연 적용(턴 종료 후 분리 수행자).

    검증 → (리로드를 부르는 세트면) 예약 → 수행자가 턴 종료 대기 → 재검증 → 준비(백업·
    구문·keeper) → 쓰기 → 워치독. 어느 단계에서 막히든 그 앞까지는 라이브 무변경이다.
    리로드가 없는 세트(frontend/scripts)는 지금 즉시 같은 코어로 적용한다."""
    repo, key = _ctx(ti)
    if not repo:
        return {"success": False, "error": "repo 루트를 찾지 못했습니다."}
    if not key:
        # ★사유는 게이트가 동봉한다(_grant_denial) — 만료·미발급·주인 불일치는 다른 사건이고,
        #   한 문장으로 뭉개면 막힌 쪽이 자기를 오진한다(2026-08-23 ep1746: 45분 턴의 그랜트가
        #   시계에 만료됐는데 "수리 경로 전용"만 읽고 '나는 수리 세션이 아니다'로 보고했다).
        _why = (ti.get("_grant_denial") or "").strip()
        return {"success": False, "error":
                (f"{_why} apply 는 사용자 명령 수리(REPAIR) 경로 전용입니다." if _why else
                 "수리 그랜트가 없습니다 — apply 는 사용자 명령 수리(REPAIR) 경로 전용입니다."),
                "grant_denial": _why}
    # proposal_id 가 오면 그 제안 세션을, 없으면 이 수리 세션을 적용한다.
    # 제안도 세션이라 분기는 '어느 키를 여는가'뿐이다(2026-08-18 통합).
    pid = (ti.get("proposal_id") or "").strip()
    if pid:
        sess = read_session(repo, proposal_key(pid))
    else:
        # ★staging 뿐 아니라 apply_scheduled 도 받는다 — 예약이 좌초하면(수행자 사망)
        #   다시 apply 가 재검증 후 재예약한다(수행자 중복은 perform 쪽 멱등으로 안전).
        sess = read_session(repo, key)
        if sess and sess.get("status") not in ("staging", "apply_scheduled"):
            sess = None
        if sess and not os.path.isdir(os.path.join(repo, sess.get("worktree") or "")):
            sess = None
    if pid:
        if not sess:
            return {"success": False, "applied": False,
                    "error": f"그런 제안이 없습니다: {pid} (op:status 로 목록 확인)"}
        st = sess.get("status")
        if st in ("applied", "discarded"):
            when = sess.get("applied_at") or sess.get("discarded_at") or ""
            return {"success": False, "applied": False,
                    "error": f"이미 {'적용' if st == 'applied' else '폐기'}된 제안입니다: {pid} {when}"}
        if not os.path.isdir(os.path.join(repo, sess.get("worktree") or "")):
            return {"success": False, "applied": False,
                    "error": (f"제안 {pid} 의 격리 사본이 사라져 적용할 내용이 없습니다 — "
                              f"기록만 남은 죽은 제안입니다. 다시 propose 하세요.")}
    if not sess or not (sess.get("files") or {}):
        pend = pending_proposals(repo)
        hint = ""
        if pend:
            hint = (" 대기 중인 제안이 있습니다 — 적용하려면 "
                    + " 또는 ".join(f'[self:patch]{{op:"apply", proposal_id:"{x}"}}'
                                    for x in pend[:3]))
        return {"success": False, "error":
                "적용할 스테이징 변경이 없습니다. RED 파일을 [self:write]/[self:edit] 로 "
                "고치면 자동으로 격리 사본에 쌓입니다." + hint,
                "pending_proposals": pend}

    ok, checks = verify(repo, sess)
    if not ok:
        failed = [c["gate"] for c in checks if not c["passed"]]
        return {"success": False, "applied": False, "verified": False,
                "checks": checks, "failed_gates": failed,
                "message": (f"기계 검증 실패({', '.join(failed)}) — 라이브는 무변경입니다. "
                            f"격리 사본에서 고쳐 쓴 뒤 다시 apply 하세요."),
                "worktree": sess["worktree"]}

    prepare = ti.get("_red_prepare")
    finalize = ti.get("_red_finalize")

    # ★지연 적용 (2026-08-19): backend/*.py 가 끼면 라이브 쓰기가 uvicorn 리로드를 불러
    # **이 턴을 실행 중인 워커를 죽인다** — 최종 응답·주행기록 버퍼·증류 스레드가 전부
    # 그 워커 안에 산다. 검증은 방금 끝났으니 쓰기만 '턴이 닫힌 뒤'로 미뤄 분리 수행자에
    # 맡긴다. frontend/scripts 만이면 리로드가 없으므로 지금 그대로 적용한다.
    verify_cmd = (ti.get("verify_cmd") or "").strip()
    if len(verify_cmd) > 2000:
        return {"success": False, "applied": False,
                "error": "verify_cmd 가 너무 깁니다(2000자 상한) — 스크립트로 만들어 그 경로를 주세요."}

    if _reload_triggering(sess):
        out = _schedule_deferred_apply(repo, sess, checks, verify_cmd)
        if out is not None:
            return out
        print("[수리 스테이징] 지연 적용 예약 불능 — 즉시 적용 폴백(이 턴은 리로드에 끊길 수 있음)")
    out = _perform_apply(repo, sess, checks, prepare, finalize)
    if verify_cmd and out.get("applied"):
        # 즉시 적용 경로(리로드 없음)에는 위탁할 죽음이 없다 — 이 턴이 그대로 살아 있으므로
        # 검증은 지금 직접 하는 게 맞다. 조용히 삼키면 "돌렸겠지"로 오해된다.
        out["verify_cmd_deferred"] = False
        out["message"] = (out.get("message") or "") + (
            f" ★verify_cmd 는 돌리지 않았습니다 — 리로드 없는 즉시 적용이라 이 턴이 살아 "
            f"있습니다. 지금 직접 확인하세요: {verify_cmd[:160]}")
    return out


def _perform_apply(repo: str, sess: dict, checks: list, prepare, finalize):
    """검증 통과분의 실제 라이브 반영 — 즉시 경로와 지연 수행자가 공유하는 단일 쓰기 코어."""
    files = sess["files"]
    to_write = {p: r for p, r in files.items() if r.get("op") != "delete"}
    to_delete = {p: r for p, r in files.items() if r.get("op") == "delete"}

    # 준비 전량 선통과 — 하나라도 막히면 아무것도 건드리지 않는다(부분 적용 금지).
    # 삭제도 여기서 백업을 뜬다: 워치독 롤백이 되돌릴 수 있는 건 백업이 있는 것뿐이다.
    staged_contents = {}
    for live_abs, rec in to_write.items():
        try:
            with open(rec["staged"], encoding="utf-8") as f:
                staged_contents[live_abs] = f.read()
        except Exception as e:
            return {"success": False, "applied": False,
                    "error": f"격리 사본을 읽지 못했습니다: {rec['rel']} ({e})"}
    if prepare:
        for live_abs, content in staged_contents.items():
            err = prepare(live_abs, content)
            if err:
                return {"success": False, "applied": False,
                        "error": f"적용 전 안전판이 거부했습니다({files[live_abs]['rel']}): {err}"}
        for live_abs in to_delete:
            err = prepare(live_abs)        # 내용 없음 = 구문검증 건너뛰고 원본 백업만
            if err:
                return {"success": False, "applied": False,
                        "error": f"삭제 전 백업이 실패했습니다({files[live_abs]['rel']}): {err}"}

    # ★쓰기 먼저, 삭제 나중 — 이동(move)은 '대상에 생긴 뒤 원본이 사라진다'가 안전한 순서다
    written, removed = [], []
    for live_abs, content in staged_contents.items():
        os.makedirs(os.path.dirname(live_abs), exist_ok=True)
        with open(live_abs, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(files[live_abs]["rel"])
    for live_abs, rec in to_delete.items():
        try:
            if os.path.exists(live_abs):
                os.remove(live_abs)
            removed.append(rec["rel"])
        except OSError as e:
            removed.append(f"{rec['rel']} (삭제 실패: {e})")
    if finalize:
        for live_abs in list(staged_contents) + list(to_delete):
            finalize(live_abs)             # backend .py 면 워치독(헬스체크·자동 롤백)

    sess["status"] = "applied"
    sess["applied_at"] = datetime.now().isoformat()
    sess["checks"] = checks
    _save_session(repo, sess)      # 제안이든 수리 세션이든 원장이 하나다
    _cleanup_old(repo)
    _n = len(written) + len(removed)
    return {
        "success": True, "applied": True, "verified": True,
        "files": written, "removed": removed,
        "checks": [{"gate": c["gate"], "passed": True} for c in checks],
        "message": (f"검증 통과 후 라이브 적용 {_n}건(쓰기 {len(written)}·삭제 {len(removed)}). "
                    f"backend/*.py 가 포함되면 지금 리로드가 일어나고, 분리 워치독이 "
                    f"/health 를 확인해 실패 시 자동 롤백합니다(판정은 다음 턴에 보고됩니다)."),
        "worktree": sess["worktree"],
    }


def op_status(ti):
    """스테이징 현황 — 무엇이 격리에 쌓여 있고 라이브에 뭐가 안 갔는지."""
    repo, key = _ctx(ti)
    if not repo:
        return {"success": False, "error": "repo 루트를 찾지 못했습니다."}
    d = os.path.join(repo, SESSION_DIRNAME)
    items = []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            continue
        items.append({
            "key": s.get("key"), "status": s.get("status"), "kind": s.get("kind") or "repair",
            "proposal_id": s.get("proposal_id"), "reason": s.get("reason"),
            "verified": s.get("verified"),
            "files": [r.get("rel") for r in (s.get("files") or {}).values()],
            "worktree": s.get("worktree"), "created_at": s.get("created_at"),
            "applied_at": s.get("applied_at"), "current": s.get("key") == key,
        })
    pending = [i for i in items if i["status"] == "staging"]
    props = [i for i in pending if i.get("kind") == "proposal"]
    msg = (f"스테이징 세션 {len(items)}건 (미적용 {len(pending)}건 · 그중 적용 대기 제안 "
           f"{len(props)}건). 미적용은 라이브에 아무 영향이 없습니다.")
    if props:
        msg += (" 제안 적용은 [self:patch]{op:\"apply\", proposal_id:\"<id>\"} "
                "— 수리(REPAIR) 경로에서만 통과합니다.")
    out = {"success": True, "items": items,
           "proposals": [{"proposal_id": i.get("proposal_id") or i["key"],
                          "files": i["files"], "reason": i.get("reason"),
                          "verified": i.get("verified"), "created_at": i["created_at"]}
                         for i in props],
           "message": msg}
    stranded = list_legacy_proposals(repo)
    if stranded:   # 통합 전 세대가 남긴 살아있는 제안 — 이관 안내(코드는 안 읽는다)
        out["legacy_stranded"] = [x.get("id") for x in stranded]
        out["message"] += (f" ★옛 원장(patch_proposals)에 좌초된 제안 {len(stranded)}건이 "
                           f"있습니다 — 통합 전 세대라 apply 가 못 봅니다. 다시 propose 하세요.")
    return out


def op_discard(ti):
    """세션 폐기 — 격리 사본을 지운다. 라이브는 원래부터 무변경이라 되돌릴 것이 없다."""
    repo, key = _ctx(ti)
    if not repo:
        return {"success": False, "error": "repo 루트를 찾지 못했습니다."}
    pid = (ti.get("proposal_id") or "").strip()
    target = proposal_key(pid) if pid else task_key(ti.get("key") or key)
    try:
        with open(_session_path(repo, target), encoding="utf-8") as f:
            sess = json.load(f)
    except Exception:
        return {"success": False, "error":
                f"그런 스테이징 세션이 없습니다: {target}. "
                f"propose 로 올린 제안을 지우려면 proposal_id 를 주세요(op:status 에 목록)."}
    _remove_worktree(repo, sess)
    sess["status"] = "discarded"
    sess["discarded_at"] = datetime.now().isoformat()
    _save_session(repo, sess)
    return {"success": True, "key": target,
            "message": f"격리 사본을 폐기했습니다({len(sess.get('files') or {})}건). 라이브는 무변경이었습니다."}


def _remove_worktree(repo: str, sess: dict):
    wt = os.path.join(repo, sess.get("worktree") or "")
    if sess.get("worktree") and os.path.isdir(wt):
        r = _git(["worktree", "remove", "--force", wt], repo)
        if r.returncode != 0:
            shutil.rmtree(wt, ignore_errors=True)
            _git(["worktree", "prune"], repo)


def _cleanup_old(repo: str):
    """종료된 오래된 세션의 격리 사본 청소 — 기회주의적, 실패는 무시."""
    d = os.path.join(repo, SESSION_DIRNAME)
    if not os.path.isdir(d):
        return
    cutoff = datetime.now() - timedelta(days=SESSION_TTL_DAYS)
    for name in os.listdir(d):
        if not name.endswith(".json"):
            continue
        p = os.path.join(d, name)
        try:
            with open(p, encoding="utf-8") as f:
                s = json.load(f)
            if s.get("status") == "staging":
                continue
            stamp = s.get("applied_at") or s.get("discarded_at") or s.get("created_at")
            if stamp and datetime.fromisoformat(stamp) < cutoff:
                _remove_worktree(repo, s)
        except Exception:
            continue


# ── op: propose (자율 태스크용 — 그랜트 없는 경로) ────────────────────────

def op_propose(ti):
    """RED 변경을 격리 사본에만 제안 + 검증. 라이브 무변경.

    ★2026-08-18 통합: 제안도 **같은 스테이징 세션**을 쓴다(key=`proposal-<ts>`).
    옛 구현은 자기 워크트리(`.worktrees/selfpatch-<ts>`)와 자기 원장(`patch_proposals/`)을
    따로 가져, 같은 `[self:patch]` 어휘인데 apply 가 원리적으로 못 봤다(제안 7건·적용 0건).
    이제 저장소가 하나라 apply/status/discard 가 분기 없이 같은 것을 본다.

    ★그랜트 요구는 apply 쪽에 그대로다 — 자율 태스크가 스스로 적용하는 길은 여전히 없다
    (헌법 08-05 조건 1). propose 는 '그랜트 없이 세션을 여는' 유일한 입구일 뿐이다.

    ★덤으로 고쳐진 것: 씨를 HEAD 가 아니라 **라이브 원본**에서 뿌린다(stage_file 규약).
    옛 propose 는 old_string 을 HEAD 내용에 맞춰봐서, 미커밋 라이브와 어긋나면
    "old_string 이 없습니다"로 헛발질했다.
    """
    repo = ti.get("_repo_root")
    red_check = ti.get("_red_check")
    if not repo:
        return {"success": False, "error": "repo 루트를 찾지 못해 propose 를 실행할 수 없습니다."}
    raw_path = ti.get("path")
    content = ti.get("content")
    old_string, new_string = ti.get("old_string"), ti.get("new_string")
    reason = (ti.get("reason") or "").strip()

    if not raw_path:
        return {"success": False, "error": "대상 파일 경로(path)가 필요합니다."}
    if not reason:
        return {"success": False, "error": "reason(변경 근거)이 필요합니다 — 사람 검토용."}
    if content is None and not (old_string is not None and new_string is not None):
        return {"success": False, "error":
                "변경 내용이 필요합니다: content(전체 내용) 또는 old_string+new_string(부분 교체)."}

    abs_target = os.path.realpath(raw_path if os.path.isabs(raw_path)
                                  else os.path.join(repo, raw_path))
    if red_check and red_check(abs_target) is None:
        return {"success": False, "error":
                "propose 는 RED 구역(backend/·frontend/·scripts/) 전용입니다. "
                "그 밖의 파일은 [self:write]/[self:edit] 로 직접 쓰세요."}
    rel_target = os.path.relpath(abs_target, repo)
    if rel_target.startswith(".."):
        return {"success": False, "error": f"repo 밖 경로는 propose 대상이 아닙니다: {abs_target}"}
    if not _is_git_repo(repo):
        return {"success": False, "error": "git 저장소가 아니라 격리(worktree)를 만들 수 없습니다."}

    # 같은 초에 두 번 부르면 키가 겹친다 — 옛 구현은 worktree 생성 실패로 떨어졌고,
    # 세션을 재사용하면 두 제안이 조용히 한 세션에 합쳐진다. 접미사로 가른다.
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_ts, n = ts, 1
    while read_session(repo, proposal_key(ts)) is not None:   # 닫힌 세션도 자리를 차지한다
        n += 1
        ts = f"{base_ts}_{n}"
    key = proposal_key(ts)

    st_abs = stage_file(repo, key, abs_target)
    if not st_abs:
        return {"success": False, "error": "격리 사본을 열지 못했습니다(git worktree 생성 실패)."}
    try:
        if content is not None:
            os.makedirs(os.path.dirname(st_abs), exist_ok=True)
            with open(st_abs, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            if not os.path.exists(st_abs):
                raise FileNotFoundError(
                    f"대상 파일이 없어 old_string 교체 불가: {rel_target} (신규 파일은 content 로)")
            with open(st_abs, encoding="utf-8") as f:
                orig = f.read()
            cnt = orig.count(old_string)
            if cnt == 0:
                raise ValueError("old_string 이 대상 파일에 없습니다.")
            if cnt > 1:
                raise ValueError(f"old_string 이 {cnt}번 나와 모호합니다 — 주변 맥락을 더 포함하세요.")
            with open(st_abs, "w", encoding="utf-8") as f:
                f.write(orig.replace(old_string, new_string, 1))

        sess = load_session(repo, key)
        wt_abs = os.path.join(repo, sess["worktree"])
        diff = _git(["diff", "--", rel_target], wt_abs).stdout
        verified, checks = verify(repo, sess)
        sess.update({"kind": "proposal", "proposal_id": ts, "reason": reason,
                     "verified": verified, "checks": checks, "diff": diff[:8000]})
        _save_session(repo, sess)

        return {
            "success": True, "proposal_id": ts, "target": rel_target,
            "verified": verified, "checks": checks, "worktree": sess["worktree"],
            "verdict": ("기계 검증 통과 ✓" if verified else "기계 검증 실패 ✗ — checks 확인"),
            "diff": diff[:4000] + ("\n…(diff 잘림)" if len(diff) > 4000 else ""),
            "note": ("이 변경은 격리 사본에만 있고 라이브는 무변경입니다. "
                     f'적용: 사용자가 수리(REPAIR) 경로로 명령한 턴에서 '
                     f'[self:patch]{{op:"apply", proposal_id:"{ts}"}} — '
                     "그때 검증을 다시 돌려 통과분만 라이브로 갑니다(재작업 불필요). "
                     f'폐기: [self:patch]{{op:"discard", proposal_id:"{ts}"}}.'),
        }
    except Exception as e:
        sess = load_session(repo, key)
        if sess:
            _remove_worktree(repo, sess)
        try:
            os.remove(_session_path(repo, key))
        except OSError:
            pass
        return {"success": False, "error": f"propose 실패: {e}"}


# ── 리로드 강제 금지 가드 (2026-08-17) ────────────────────────────────────
# ★왜: 실측(08-18) 시스템 AI 가 수리 중 `touch backend/api.py && curl 헬스 폴링` 을
# 셸로 돌렸다. touch 가 uvicorn 리로드를 부르고, 그 리로드가 **그 턴을 실행 중이던
# 워커를 죽인다** — finally 가 못 돌아 에피소드가 안 닫히고, WS 가 끊겨 클라이언트는
# 완료 신호를 영영 못 받는다(화면의 도구 칩이 영원히 도는 것처럼 보임). 서버는 멀쩡한데
# 사용자 자리에서는 "혼자 돌고 있다"로 보인다.
#
# 이건 격리 스테이징이 없애려던 바로 그 동작의 **셸 우회**다. 반영은 apply 가 하고,
# 그 뒤 판정은 분리 워치독이 다음 턴에 보고한다 — 손으로 리로드를 부를 이유가 없다.
# 프롬프트(천장)가 아니라 쓰기 지점의 구조(바닥)로 막는다.
#
# ★한계(정직하게): 셸은 튜링완전이라 완전 차단은 불가하다(`find … | xargs touch` 등).
# 흔한 직접 형태를 막고, 나머지는 프롬프트 수칙과 워치독이 받는다.
_TOUCH_RE = re.compile(r"\btouch\b([^;&|]*)")
_KILL_RE = re.compile(r"\b(?:kill|pkill|killall)\b([^;&|]*)")
# 이 몸의 백엔드를 가리키는 표식 — kill 계열이 이걸 겨누면 자기 목을 치는 것이다.
_BACKEND_MARKERS = ("uvicorn", "api.py", "backend_keeper", "8765")

_RELOAD_HINT = (
    "수리 반영은 [self:patch]{op:\"apply\"} 가 합니다 — 검증(구문·import·삼각)을 통과한 "
    "내용만 라이브로 옮기고, 그때 리로드가 한 번 일어납니다. 그 뒤 헬스 판정은 분리 "
    "워치독이 맡아 다음 턴에 보고하므로, 직접 폴링할 필요도 없습니다."
)


def reload_forcing_violation(command: str, repo: str):
    """리로드를 손으로 강제하는 명령이면 거부 메시지, 아니면 None."""
    if not command or not repo:
        return None
    red_roots = [os.path.join(repo, d) for d in ("backend", "frontend", "scripts")]

    for m in _TOUCH_RE.finditer(command):
        for tok in m.group(1).split():
            if tok.startswith("-"):
                continue
            cand = tok.strip("'\"")
            real = os.path.realpath(cand if os.path.isabs(cand) else os.path.join(repo, cand))
            if any(real == r or real.startswith(r + os.sep) for r in red_roots):
                return (f"Error: RED 구역 파일에 touch 로 리로드를 강제할 수 없습니다: {cand}\n"
                        f"★그 리로드는 지금 이 턴을 실행 중인 워커를 죽입니다 — 에피소드가 "
                        f"닫히지 않고 화면의 작업 표시가 영원히 멈춥니다(실측).\n{_RELOAD_HINT}")

    for m in _KILL_RE.finditer(command):
        args = m.group(1).lower()
        if any(mk in args for mk in _BACKEND_MARKERS) or any(mk in command.lower() for mk in ("lsof", ":8765")):  # vj-ok: 명령행 표식 탐지
            return ("Error: 이 몸의 백엔드를 kill 로 재기동시킬 수 없습니다 — 자기 목을 치는 "
                    "동작입니다(그 순간 이 턴도 함께 죽습니다).\n"
                    "프로세스가 정말 멎었다면 keeper(scripts/backend_keeper.sh)가 되살립니다.\n"
                    + _RELOAD_HINT)
    return None
