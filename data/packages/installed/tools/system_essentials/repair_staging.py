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
리로드는 적용 순간 한 번이다.

★기존 안전판은 무엇도 대체하지 않는다. 적용 단계가 _red_write_prepare/
_red_write_finalize 를 그대로 통과하므로 백업·keeper 일시정지·분리 워치독·자동
롤백이 전부 이어받는다. 스테이징은 그 **앞에** 검증 층을 하나 더 놓을 뿐이다.
(라이브 프로세스의 *행동* 검증은 여전히 적용 이후다 — 격리 사본에서 잡는 것은
구조적 브릭[구문·import·삼각·안전장치 스모크]이고, 브릭 위험은 거기 산다.)

★스테이징 베이스 = 라이브 작업 트리 (HEAD 아님). worktree 는 HEAD 로 만들지만
①세션 생성 시 추적 변경분(git diff HEAD)을 best-effort 로 얹고 ②파일을 처음 건드릴 때
**라이브 원본에서 씨를 뿌린다**(권위). HEAD 를 베이스로 쓰면 미커밋 라이브 작업을
적용이 조용히 되돌린다 — 데이터 손실.

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
from datetime import datetime, timedelta

SESSION_DIRNAME = os.path.join("data", "system_ai_state", "repair_sessions")
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


def _session_path(repo: str, key: str) -> str:
    d = os.path.join(repo, SESSION_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{key}.json")


def load_session(repo: str, key: str):
    """세션 원장 읽기 — 없으면 None. (핸들러 재임포트를 건너 살아남도록 디스크에 산다.)"""
    try:
        with open(_session_path(repo, key), encoding="utf-8") as f:
            s = json.load(f)
        return s if s.get("status") == "staging" else None
    except Exception:
        return None


def _save_session(repo: str, sess: dict):
    with open(_session_path(repo, sess["key"]), "w", encoding="utf-8") as f:
        json.dump(sess, f, ensure_ascii=False, indent=2)


def _is_git_repo(repo: str) -> bool:
    try:
        return _git(["rev-parse", "--git-dir"], repo).returncode == 0
    except Exception:
        return False


# ── 세션 (격리 사본) ──────────────────────────────────────────────────────

def ensure_session(repo: str, key: str):
    """스테이징 세션 확보 — 없으면 worktree 를 만든다. 실패 시 None(=라이브 직행 폴백)."""
    sess = load_session(repo, key)
    if sess and os.path.isdir(os.path.join(repo, sess["worktree"])):
        return sess
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
    # 라이브 미커밋 변경분을 격리 사본에 얹는다(추적 파일 한정, best-effort).
    # 실패해도 치명적이지 않다 — 건드리는 파일은 stage_file 이 라이브에서 다시 씨를 뿌린다.
    try:
        diff = _git(["diff", "HEAD"], repo).stdout
        if diff.strip():
            p = subprocess.run(["git", "apply", "--allow-empty", "-"], cwd=wt_abs,
                               input=diff, capture_output=True, text=True, timeout=GIT_TIMEOUT)
            if p.returncode != 0:
                print(f"[수리 스테이징] 미커밋 변경분 이식 실패(무시): {p.stderr.strip()[:200]}")
    except Exception as e:
        print(f"[수리 스테이징] 미커밋 변경분 이식 예외(무시): {e}")
    sess = {"key": key, "worktree": wt_rel, "status": "staging",
            "created_at": datetime.now().isoformat(), "files": {}}
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

def _module_name(rel: str):
    """backend/<층>/<모듈>.py → 모듈명. 평면 이름 + boot_paths 층 등재 규약."""
    if not (rel.startswith("backend" + os.sep) and rel.endswith(".py")):
        return None
    base = os.path.basename(rel)
    if base == "__init__.py":
        return None
    return base[:-3]


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
    pat = re.compile(r"^\s*(?:from\s+%s\s+import|import\s+%s\b)" % (re.escape(mod), re.escape(mod)),
                     re.MULTILINE)
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


def verify(repo: str, sess: dict):
    """격리 사본에서 기계 검증. (통과여부, checks[]) — 자기채점 아닌 pass/fail 기계값."""
    wt_abs = os.path.join(repo, sess["worktree"])
    recs = list((sess.get("files") or {}).values())
    rels = [r["rel"] for r in recs if r.get("op") != "delete"]
    del_rels = [r["rel"] for r in recs if r.get("op") == "delete"]
    checks = []
    py = sys.executable or "python3"       # ★venv 파이썬 — 시스템 python3 는 의존성이 없다

    # 0. 삭제 — 남는 쪽의 import 가 깨지지 않는지 (삭제 고유의 위험)
    if del_rels:
        dropped = set(del_rels)
        orphans = {}
        for rel in del_rels:
            mod = _module_name(rel)
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
    mods = sorted({m for m in (_module_name(r) for r in rels) if m})
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

    # 4. 안전장치를 고쳤으면(지웠으면 더더욱) 기능 스모크까지 — 게이트를 고치다 게이트를
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


# ── op: apply / status / discard ──────────────────────────────────────────

def _ctx(ti):
    return (ti.get("_repo_root"), ti.get("_grant_key"))


def op_apply(ti):
    """검증 통과분만 라이브로 일괄 이동 — 리로드는 여기서 한 번.

    검증 → 준비(백업·구문·keeper) → 쓰기 → 워치독. 어느 단계에서 막히든 그 앞까지는
    라이브 무변경이다(준비 단계 실패도 쓰기 전에 걸린다)."""
    repo, key = _ctx(ti)
    if not repo:
        return {"success": False, "error": "repo 루트를 찾지 못했습니다."}
    if not key:
        return {"success": False, "error":
                "수리 그랜트가 없습니다 — apply 는 사용자 명령 수리(REPAIR) 경로 전용입니다."}
    sess = load_session(repo, key)
    if not sess or not (sess.get("files") or {}):
        return {"success": False, "error":
                "적용할 스테이징 변경이 없습니다. RED 파일을 [self:write]/[self:edit] 로 "
                "고치면 자동으로 격리 사본에 쌓입니다."}

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
    _save_session(repo, sess)
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
            "key": s.get("key"), "status": s.get("status"),
            "files": [r.get("rel") for r in (s.get("files") or {}).values()],
            "worktree": s.get("worktree"), "created_at": s.get("created_at"),
            "applied_at": s.get("applied_at"), "current": s.get("key") == key,
        })
    pending = [i for i in items if i["status"] == "staging"]
    return {"success": True, "items": items,
            "message": (f"스테이징 세션 {len(items)}건 (미적용 {len(pending)}건). "
                        f"미적용은 라이브에 아무 영향이 없습니다 — 적용은 op:apply.")}


def op_discard(ti):
    """세션 폐기 — 격리 사본을 지운다. 라이브는 원래부터 무변경이라 되돌릴 것이 없다."""
    repo, key = _ctx(ti)
    if not repo:
        return {"success": False, "error": "repo 루트를 찾지 못했습니다."}
    target = task_key(ti.get("key") or key)
    try:
        with open(_session_path(repo, target), encoding="utf-8") as f:
            sess = json.load(f)
    except Exception:
        return {"success": False, "error": f"그런 스테이징 세션이 없습니다: {target}"}
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
    """RED 변경을 격리 사본에만 제안 + 검증. 라이브 무변경. 적용은 사용자 명령 수리가.

    ★apply 와 다른 점 = 그랜트가 없다. 자율 태스크(스케줄러·자가점검)가 발견한 문제를
    사람이 볼 수 있게 남기는 채널이라, 여기엔 라이브로 가는 길이 없다."""
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

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    wt_rel = os.path.join(".worktrees", f"selfpatch-{ts}")
    wt_abs = os.path.join(repo, wt_rel)
    add = _git(["worktree", "add", "--detach", wt_abs, "HEAD"], repo)
    if add.returncode != 0:
        return {"success": False, "error": f"worktree 생성 실패: {add.stderr.strip()}"}

    try:
        wt_file = os.path.join(wt_abs, rel_target)
        if content is not None:
            os.makedirs(os.path.dirname(wt_file), exist_ok=True)
            with open(wt_file, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            if not os.path.exists(wt_file):
                raise FileNotFoundError(
                    f"대상 파일이 HEAD에 없어 old_string 교체 불가: {rel_target} (신규 파일은 content 로)")
            with open(wt_file, encoding="utf-8") as f:
                orig = f.read()
            n = orig.count(old_string)
            if n == 0:
                raise ValueError("old_string 이 대상 파일에 없습니다.")
            if n > 1:
                raise ValueError(f"old_string 이 {n}번 나와 모호합니다 — 주변 맥락을 더 포함하세요.")
            with open(wt_file, "w", encoding="utf-8") as f:
                f.write(orig.replace(old_string, new_string, 1))

        diff = _git(["diff", "--", rel_target], wt_abs).stdout
        pseudo = {"worktree": wt_rel, "files": {abs_target: {"staged": wt_file, "rel": rel_target}}}
        verified, checks = verify(repo, pseudo)

        prop_dir = os.path.join(repo, "data", "system_ai_state", "patch_proposals")
        os.makedirs(prop_dir, exist_ok=True)
        proposal = {"id": ts, "target": rel_target, "reason": reason, "diff": diff,
                    "checks": checks, "verified": verified, "worktree": wt_rel,
                    "status": "proposed", "created_at": datetime.now().isoformat()}
        with open(os.path.join(prop_dir, f"{ts}.json"), "w", encoding="utf-8") as f:
            json.dump(proposal, f, ensure_ascii=False, indent=2)

        return {
            "success": True, "proposal_id": ts, "target": rel_target,
            "verified": verified, "checks": checks, "worktree": wt_rel,
            "verdict": ("기계 검증 통과 ✓" if verified else "기계 검증 실패 ✗ — checks 확인"),
            "diff": diff[:4000] + ("\n…(diff 잘림)" if len(diff) > 4000 else ""),
            "note": ("이 변경은 격리 사본에만 있고 라이브는 무변경입니다. 적용은 사용자가 "
                     "수리 경로(REPAIR)로 명령할 때 하거나 사람이 직접 머지합니다. "
                     f"폐기: git worktree remove {wt_rel}."),
        }
    except Exception as e:
        _git(["worktree", "remove", "--force", wt_abs], repo)
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
        if any(mk in args for mk in _BACKEND_MARKERS) or any(mk in command.lower() for mk in ("lsof", ":8765")):
            return ("Error: 이 몸의 백엔드를 kill 로 재기동시킬 수 없습니다 — 자기 목을 치는 "
                    "동작입니다(그 순간 이 턴도 함께 죽습니다).\n"
                    "프로세스가 정말 멎었다면 keeper(scripts/backend_keeper.sh)가 되살립니다.\n"
                    + _RELOAD_HINT)
    return None
