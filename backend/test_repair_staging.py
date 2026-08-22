"""
test_repair_staging.py - 수리 격리 스테이징 배터리 (2026-08-17)

REPAIR 경로가 라이브 substrate 를 직접 수술하지 않고 격리 사본에 쌓았다가 검증
통과분만 옮기는지를 임시 git 저장소에서 기계 실측한다. **라이브 무접촉** — 모든
검사는 tempdir 안의 가짜 저장소에서 돈다.

핵심 계약 5:
  S1 그랜트 있는 RED 쓰기는 격리로 간다 — 라이브 무변경(리로드 없음)
  S2 자기가 쓴 것을 되읽으면 격리본이 온다 (안 건드린 파일은 라이브)
  S3 검증이 실패하면 라이브는 끝까지 무변경 (부분 적용 없음)
  S4 검증이 통과하면 라이브로 일괄 이동 + 기존 안전판(백업)이 이어받는다
  S5 그랜트가 없거나 git 이 없으면 스테이징 없이 종전 경로로 폴백한다
  S8 검증 베이스 = 지금 라이브 + 세션 델타 (2026-08-19 거짓 초록 봉합 — 미추적 신규
     의존·세션 개설 후 라이브 드리프트·커밋 드리프트까지 검증 시마다 동기화)
  S9 지연 적용 (2026-08-19): backend/*.py apply=예약(라이브 무변경)→수행자가 턴 종료
     후 쓰기 직전 재검증 — 예약~수행 사이 라이브 드리프트가 적용을 막는다
  S10 분리 수행자(red_apply) 실프로세스 종단 — 부트스트랩·핸들러 로드·그랜트 이월

실행: python3 backend/test_repair_staging.py   (exit 0 = 전부 통과)
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
try:
    import boot_paths  # noqa: F401
except ImportError:
    pass

_passed, _failed = [], []


def check(name, cond, detail=""):
    (_passed if cond else _failed).append(name if cond else f"{name}: {detail}"[:300])


def _load_handler():
    spec = importlib.util.spec_from_file_location(
        "h_staging", str(REPO / "data/packages/installed/tools/system_essentials/handler.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BOOT_PATHS_STUB = '''import os, sys
_H = os.path.dirname(os.path.abspath(__file__))
for d in ("base", "cognition"):
    p = os.path.join(_H, d)
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)
'''


def _make_repo(tmp: Path, git=True) -> Path:
    """최소 가짜 저장소 — backend 층 구조 + boot_paths 스텁(import 스모크가 실제로 돌게)."""
    (tmp / "backend" / "cognition").mkdir(parents=True)
    (tmp / "backend" / "base").mkdir(parents=True)
    (tmp / "scripts").mkdir()
    (tmp / "data" / "system_ai_state").mkdir(parents=True)
    (tmp / "backend" / "boot_paths.py").write_text(BOOT_PATHS_STUB)
    (tmp / "backend" / "cognition" / "victim.py").write_text("VALUE = 'original'\n")
    (tmp / "backend" / "cognition" / "bystander.py").write_text("OTHER = 'live'\n")
    if git:
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
            subprocess.run(["git"] + args, cwd=tmp, env=env, capture_output=True)
    return tmp


def _grant(h, task_id="task_staging_test"):
    import red_grant
    import thread_context
    thread_context.clear_all_context()
    thread_context.set_current_task_id(task_id)
    thread_context.set_current_agent_id("system_ai")
    red_grant.issue_grant(agent_id="system_ai", task_id=task_id, reason="staging battery")
    return task_id


def _ungrant():
    import red_grant
    import thread_context
    red_grant.revoke_grant()
    thread_context.clear_all_context()


def _apply_full(st, h, tmp, key_str):
    """op_apply → (backend 세트면 예약이므로) 수행자 경유로 완결 — 지연 적용의 두 단계를
    배터리에서 잇는다. 예약이 아니면(즉시 경로) 그 결과 그대로."""
    r = st.op_apply({"_repo_root": str(tmp), "_grant_key": key_str,
                     "_red_prepare": h._red_write_prepare, "_red_finalize": h._red_write_finalize})
    if r.get("scheduled"):
        return st.perform_scheduled_apply(str(tmp), key_str,
                                          prepare=h._red_write_prepare,
                                          finalize=h._red_write_finalize)
    return r


def run():
    h = _load_handler()
    st = h._staging_mod()
    # 예약이 실제 수행자를 spawn 하면 배터리의 직접 perform 호출과 경주한다 — 심으로 차단
    # (S10 만 실프로세스를 직접 기동해 종단을 본다)
    os.environ["INDIEBIZ_REPAIR_NO_SPAWN"] = "1"

    # ══ S1/S2/S3/S4 — git 저장소에서 전 생애주기 ══
    tmp = Path(tempfile.mkdtemp(prefix="stg_")).resolve()
    victim = tmp / "backend" / "cognition" / "victim.py"
    bystander = tmp / "backend" / "cognition" / "bystander.py"
    try:
        _make_repo(tmp)
        h._REPO_ROOT = tmp
        task = _grant(h)

        # S1 — 쓰기가 격리로 간다
        staged = h._red_stage(str(victim), for_write=True)
        check("S1_redirected_off_live", staged != str(victim), staged)
        check("S1_staged_inside_worktree", ".worktrees/repair-" in staged.replace(os.sep, "/"), staged)
        # 씨는 라이브에서 뿌려진다 (HEAD 아님) — 라이브 미커밋 작업 보존의 근거
        check("S1_seeded_from_live", Path(staged).read_text() == "VALUE = 'original'\n")
        Path(staged).write_text("VALUE = 'patched'\n")
        check("S1_live_untouched", victim.read_text() == "VALUE = 'original'\n", victim.read_text())

        # S2 — 되읽기는 격리본, 안 건드린 파일은 라이브
        check("S2_read_sees_own_write",
              h._red_stage(str(victim), for_write=False) == staged)
        check("S2_untouched_reads_live",
              h._red_stage(str(bystander), for_write=False) == str(bystander))

        # S3a — 구문 오류는 py_compile 이 잡고, 라이브는 무변경
        Path(staged).write_text("VALUE = 'broken'\ndef (:\n")
        r = st.op_apply({"_repo_root": str(tmp), "_grant_key": st.task_key(task),
                         "_red_prepare": h._red_write_prepare, "_red_finalize": h._red_write_finalize})
        check("S3a_syntax_blocks_apply", r.get("applied") is not True and "py_compile" in (r.get("failed_gates") or []),
              json.dumps(r, ensure_ascii=False)[:200])
        check("S3a_live_untouched", victim.read_text() == "VALUE = 'original'\n")

        # S3b — ★import 스모크: 구문은 멀쩡한데 import 가 죽는 부류(사전 compile() 로는
        #       원리적으로 못 잡는다). 브릭의 실제 원인 대부분이 여기 산다.
        Path(staged).write_text("VALUE = UNDEFINED_NAME\n")
        r = st.op_apply({"_repo_root": str(tmp), "_grant_key": st.task_key(task),
                         "_red_prepare": h._red_write_prepare, "_red_finalize": h._red_write_finalize})
        check("S3b_import_smoke_catches_nameerror",
              r.get("applied") is not True and "import_smoke" in (r.get("failed_gates") or []),
              json.dumps(r, ensure_ascii=False)[:300])
        check("S3b_live_still_untouched", victim.read_text() == "VALUE = 'original'\n")

        # S3c — 부분 적용 금지: 두 파일 중 하나만 깨져도 둘 다 안 나간다
        staged_by = h._red_stage(str(bystander), for_write=True)
        Path(staged_by).write_text("OTHER = 'would_be_applied'\n")
        r = st.op_apply({"_repo_root": str(tmp), "_grant_key": st.task_key(task),
                         "_red_prepare": h._red_write_prepare, "_red_finalize": h._red_write_finalize})
        check("S3c_no_partial_apply",
              r.get("applied") is not True and bystander.read_text() == "OTHER = 'live'\n",
              bystander.read_text())

        # S4 — 통과하면: backend/*.py 는 ★지연 적용 — apply=예약(라이브 무변경),
        #      실제 쓰기는 수행자(perform_scheduled_apply)가 턴 종료 후 재검증하고 수행
        Path(staged).write_text("VALUE = 'patched'\n")
        r = st.op_apply({"_repo_root": str(tmp), "_grant_key": st.task_key(task),
                         "_red_prepare": h._red_write_prepare, "_red_finalize": h._red_write_finalize})
        check("S4_backend_apply_is_scheduled",
              r.get("scheduled") is True and r.get("applied") is False,
              json.dumps(r, ensure_ascii=False)[:300])
        check("S4_live_untouched_until_performed", victim.read_text() == "VALUE = 'original'\n")
        check("S4_job_file_written",
              (tmp / "data" / "system_ai_state" / "repair_sessions"
               / f"{st.task_key(task)}.apply.json").exists())
        r = st.perform_scheduled_apply(str(tmp), st.task_key(task),
                                       prepare=h._red_write_prepare, finalize=h._red_write_finalize)
        check("S4_apply_succeeds", r.get("applied") is True, json.dumps(r, ensure_ascii=False)[:300])
        check("S4_live_updated", victim.read_text() == "VALUE = 'patched'\n", victim.read_text())
        check("S4_second_file_too", bystander.read_text() == "OTHER = 'would_be_applied'\n")
        bdir = tmp / "data" / "system_ai_state" / "red_backups" / st.task_key(task)
        check("S4_backup_taken", (bdir / "manifest.json").exists())
        if (bdir / "manifest.json").exists():
            man = json.loads((bdir / "manifest.json").read_text())
            backups = [b for b in man.get("files", {}).values() if b]
            check("S4_backup_holds_original",
                  any(Path(b).read_text() == "VALUE = 'original'\n" for b in backups),
                  str(backups))
        # 적용된 세션은 더 이상 스테이징이 아니다(다음 쓰기는 새 세션)
        check("S4_session_closed", st.load_session(str(tmp), st.task_key(task)) is None)

        # S6 — 신규 파일(라이브에 없던 것) 경로: 씨 뿌릴 원본이 없다 → 롤백은 '삭제'
        newmod = tmp / "backend" / "cognition" / "fresh.py"
        task_new = _grant(h, "task_newfile")
        s_new = h._red_stage(str(newmod), for_write=True)
        check("S6_new_file_staged", s_new != str(newmod) and not newmod.exists())
        Path(s_new).parent.mkdir(parents=True, exist_ok=True)
        Path(s_new).write_text("FRESH = 1\n")
        r = _apply_full(st, h, tmp, st.task_key(task_new))
        check("S6_new_file_applied", r.get("applied") is True and newmod.exists(),
              json.dumps(r, ensure_ascii=False)[:200])
        nman = tmp / "data" / "system_ai_state" / "red_backups" / st.task_key(task_new) / "manifest.json"
        if nman.exists():
            # 신규 파일은 백업이 null — 워치독 롤백이 '복원'이 아니라 '삭제'여야 한다
            check("S6_new_file_backup_null",
                  json.loads(nman.read_text())["files"].get(str(newmod.resolve())) is None)

        # ══ S7 — 삭제/이동/복사도 같은 층 (2026-08-17 후속) ══
        # S7a 삭제: 라이브는 apply 전까지 그대로, 격리 사본에서만 사라진다
        doomed = tmp / "backend" / "cognition" / "doomed.py"
        doomed.write_text("DOOMED = 1\n")
        task_del = _grant(h, "task_delete")
        check("S7a_delete_staged", st.stage_delete(str(tmp), st.task_key(task_del), str(doomed)))
        check("S7a_live_file_survives", doomed.exists())
        sess_del = st.load_session(str(tmp), st.task_key(task_del))
        check("S7a_recorded_as_delete",
              list(sess_del["files"].values())[0]["op"] == "delete")
        ok, checks_d = st.verify(str(tmp), sess_del)
        check("S7a_delete_verifies", ok, str([c["gate"] for c in checks_d if not c["passed"]]))
        # S12f — 파이썬만 든 세션엔 tsc 관문이 아예 안 뜬다(안 건드린 것은 검사도 비용 0)
        check("S12f_no_tsc_gate_without_frontend",
              "frontend_tsc" not in [c["gate"] for c in checks_d],
              str([c["gate"] for c in checks_d]))
        r = _apply_full(st, h, tmp, st.task_key(task_del))
        check("S7a_delete_applied", r.get("applied") is True and not doomed.exists(),
              json.dumps(r, ensure_ascii=False)[:200])
        dman = tmp / "data" / "system_ai_state" / "red_backups" / st.task_key(task_del) / "manifest.json"
        check("S7a_delete_backed_up", dman.exists() and any(
            b and Path(b).read_text() == "DOOMED = 1\n"
            for b in json.loads(dman.read_text())["files"].values()))

        # S7b — ★삭제 고유의 위험: 남의 import 가 깨진다. 쓰기 스모크로는 원리적으로
        #       못 잡는 부류(지워진 모듈은 import 해볼 수조차 없다).
        needed = tmp / "backend" / "cognition" / "needed.py"
        needed.write_text("NEEDED = 1\n")
        (tmp / "backend" / "cognition" / "user_of.py").write_text("import needed\nUSES = needed.NEEDED\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-qm", "add needed"], cwd=tmp, capture_output=True)
        task_orphan = _grant(h, "task_orphan")
        st.stage_delete(str(tmp), st.task_key(task_orphan), str(needed))
        ok_o, checks_o = st.verify(str(tmp), st.load_session(str(tmp), st.task_key(task_orphan)))
        gate_o = next((c for c in checks_o if c["gate"] == "delete_no_orphan_imports"), None)
        check("S7b_orphan_import_blocks", not ok_o and gate_o and not gate_o["passed"],
              json.dumps(gate_o, ensure_ascii=False)[:300] if gate_o else "gate missing")
        check("S7b_orphan_names_the_importer",
              bool(gate_o) and "user_of.py" in (gate_o.get("detail") or ""))
        r = st.op_apply({"_repo_root": str(tmp), "_grant_key": st.task_key(task_orphan),
                         "_red_prepare": h._red_write_prepare, "_red_finalize": h._red_write_finalize})
        check("S7b_live_file_survives_block", r.get("applied") is not True and needed.exists())
        st.op_discard({"_repo_root": str(tmp), "_grant_key": st.task_key(task_orphan)})

        # S7c — 이동: 양쪽(대상 쓰기 + 원본 삭제)이 한 세션에 함께 적재된다
        mover = tmp / "backend" / "cognition" / "mover.py"
        mover.write_text("MOVED = 1\n")
        moved_to = tmp / "backend" / "base" / "mover.py"
        task_mv = _grant(h, "task_move")
        k_mv = st.task_key(task_mv)
        check("S7c_both_sides_stageable",
              st.can_stage(str(tmp), k_mv, str(mover)) and st.can_stage(str(tmp), k_mv, str(moved_to)))
        s_dst = st.stage_file(str(tmp), k_mv, str(moved_to))
        Path(s_dst).parent.mkdir(parents=True, exist_ok=True)
        Path(s_dst).write_text(mover.read_text())
        st.stage_delete(str(tmp), k_mv, str(mover))
        check("S7c_live_untouched_both", mover.exists() and not moved_to.exists())
        r = _apply_full(st, h, tmp, k_mv)
        check("S7c_move_applied", r.get("applied") is True and moved_to.exists() and not mover.exists(),
              json.dumps(r, ensure_ascii=False)[:250])

        # ══ S8 — 베이스 신선도 (2026-08-19 거짓 초록 봉합) ══
        # S8a: 미추적 신규 의존 모듈 — 옛 이식(git diff HEAD | apply)은 추적 한정이라
        #      격리 사본에 없었고, import 스모크가 제안 내용과 무관하게 거짓 빨강을 냈다.
        dep = tmp / "backend" / "cognition" / "dep_live.py"
        dep.write_text("TOKEN = 'v1'\n")                    # ★커밋하지 않는다(미추적)
        importer = tmp / "backend" / "cognition" / "importer.py"
        task_s8 = _grant(h, "task_sync")
        s_imp = h._red_stage(str(importer), for_write=True)
        Path(s_imp).parent.mkdir(parents=True, exist_ok=True)
        Path(s_imp).write_text("import dep_live\nX = dep_live.TOKEN\n")
        sess8 = st.load_session(str(tmp), st.task_key(task_s8))
        ok8, checks8 = st.verify(str(tmp), sess8)
        check("S8a_untracked_dep_visible", ok8,
              json.dumps([c for c in checks8 if not c["passed"]], ensure_ascii=False)[:300])
        check("S8a_live_sync_gate_present",
              any(c["gate"] == "live_sync" and c["passed"] for c in checks8))

        # S8b: ★거짓 초록 재현 — 세션 개설 *뒤* 의존 모듈이 라이브에서 바뀌면 검증은
        #      '지금 라이브' 기준으로 다시 봐야 한다. 옛 코드는 개설 시점 스냅샷을 보고
        #      초록을 냈고, apply 는 진짜 라이브(TOKEN 없는)로 갔다 — 브릭 경로.
        dep.write_text("RENAMED = 'v2'\n")                  # TOKEN 소멸
        ok8b, checks8b = st.verify(str(tmp), sess8)
        failed8b = [c["gate"] for c in checks8b if not c["passed"]]
        check("S8b_live_drift_breaks_green", (not ok8b) and "import_smoke" in failed8b,
              json.dumps(failed8b, ensure_ascii=False))

        # S8c: 커밋 드리프트 — 제안이 며칠 묵는 동안 라이브에 커밋이 쌓여도 따라온다
        #      (워크트리 베이스 커밋 ↔ 라이브 HEAD 의 diff 까지 동기화 — 낡은 베이스 봉합).
        dep.write_text("TOKEN = 'v3'\n")
        subprocess.run(["git", "add", "backend/cognition/dep_live.py"],
                       cwd=tmp, capture_output=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-qm", "dep v3"], cwd=tmp, capture_output=True)
        ok8c, checks8c = st.verify(str(tmp), sess8)
        check("S8c_committed_drift_synced", ok8c,
              json.dumps([c for c in checks8c if not c["passed"]], ensure_ascii=False)[:300])

        # S8d: 스테이징이 이긴다 — 세션에 적재된 파일은 동기화가 라이브로 덮지 않는다
        importer.write_text("LIVE_EDIT = 1\n")              # 라이브에 같은 경로가 생겨도
        st.verify(str(tmp), sess8)
        check("S8d_staged_wins",
              Path(s_imp).read_text() == "import dep_live\nX = dep_live.TOKEN\n",
              Path(s_imp).read_text()[:120])
        importer.unlink()
        st.op_discard({"_repo_root": str(tmp), "_grant_key": st.task_key(task_s8)})

        # ══ S9 — 지연 창 드리프트 (2026-08-19 지연 적용) ══
        # 예약(검증 통과)~수행 사이에도 라이브는 변한다 — 수행자는 쓰기 직전 재검증해야
        # 하고, 실패하면 라이브 무변경 + 세션은 staging 복귀 + 결말은 result.json.
        dep9 = tmp / "backend" / "cognition" / "dep9.py"
        dep9.write_text("NINE = 1\n")
        imp9 = tmp / "backend" / "cognition" / "imp9.py"
        task9 = _grant(h, "task_defer_drift")
        s9 = h._red_stage(str(imp9), for_write=True)
        Path(s9).parent.mkdir(parents=True, exist_ok=True)
        Path(s9).write_text("import dep9\nY = dep9.NINE\n")
        r = st.op_apply({"_repo_root": str(tmp), "_grant_key": st.task_key(task9),
                         "_red_prepare": h._red_write_prepare, "_red_finalize": h._red_write_finalize})
        check("S9_scheduled", r.get("scheduled") is True, json.dumps(r, ensure_ascii=False)[:200])
        dep9.write_text("GONE = 1\n")           # 예약~수행 사이 라이브 드리프트(NINE 소멸)
        r = st.perform_scheduled_apply(str(tmp), st.task_key(task9),
                                       prepare=h._red_write_prepare, finalize=h._red_write_finalize)
        check("S9_reverify_blocks_stale_apply",
              r.get("applied") is not True and not imp9.exists(),
              json.dumps(r, ensure_ascii=False)[:300])
        sess9 = st.read_session(str(tmp), st.task_key(task9))
        check("S9_session_back_to_staging", bool(sess9) and sess9.get("status") == "staging",
              str(sess9 and sess9.get("status")))
        res9 = (tmp / "data" / "system_ai_state" / "red_backups"
                / st.task_key(task9) / "result.json")
        check("S9_deferred_result_reported",
              res9.exists() and json.loads(res9.read_text()).get("outcome") == "deferred_verify_failed",
              res9.read_text()[:200] if res9.exists() else "no result.json")
        st.op_discard({"_repo_root": str(tmp), "_grant_key": st.task_key(task9)})
        dep9.unlink()

        # ══ S10 — 분리 수행자(red_apply) 실프로세스 종단 ══
        # 부트스트랩(sys.path·boot_paths)·핸들러 로드·그랜트 이월(인메모리 재발급)까지
        # 실제 프로세스로 검증 — 코드 루트(실저장소)와 데이터 루트(가짜 repo)가 갈라진다.
        v10 = tmp / "backend" / "cognition" / "victim10.py"
        v10.write_text("TEN = 'orig'\n")
        task10 = _grant(h, "task_red_apply_proc")
        s10 = h._red_stage(str(v10), for_write=True)
        Path(s10).write_text("TEN = 'deferred'\n")
        r = st.op_apply({"_repo_root": str(tmp), "_grant_key": st.task_key(task10),
                         "_red_prepare": h._red_write_prepare, "_red_finalize": h._red_write_finalize})
        check("S10_scheduled", r.get("scheduled") is True, json.dumps(r, ensure_ascii=False)[:200])
        job10 = (tmp / "data" / "system_ai_state" / "repair_sessions"
                 / f"{st.task_key(task10)}.apply.json")
        env10 = {**os.environ, "RED_APPLY_NO_EPISODE_GRACE_S": "0", "RED_APPLY_SETTLE_S": "0"}
        env10.pop("INDIEBIZ_REPAIR_NO_SPAWN", None)
        p10 = subprocess.run([sys.executable, str(REPO / "backend" / "datastore" / "red_apply.py"),
                              str(job10)], capture_output=True, text=True, timeout=180, env=env10)
        check("S10_process_applies", p10.returncode == 0 and v10.read_text() == "TEN = 'deferred'\n",
              ((p10.stdout or "") + (p10.stderr or ""))[-400:])
        sess10 = st.read_session(str(tmp), st.task_key(task10))
        check("S10_session_applied", bool(sess10) and sess10.get("status") == "applied",
              str(sess10 and sess10.get("status")))

        # ── status / discard ──
        r = st.op_status({"_repo_root": str(tmp), "_grant_key": st.task_key(task)})
        check("status_lists_session", r.get("success") and any(
            i.get("status") == "applied" for i in r.get("items", [])), json.dumps(r)[:200])

        task2 = _grant(h, "task_discard_test")
        s2 = h._red_stage(str(victim), for_write=True)
        Path(s2).write_text("VALUE = 'discard_me'\n")
        r = st.op_discard({"_repo_root": str(tmp), "_grant_key": st.task_key(task2)})
        check("discard_ok", r.get("success") is True, json.dumps(r, ensure_ascii=False)[:200])
        check("discard_leaves_live", victim.read_text() == "VALUE = 'patched'\n")
        check("discard_removes_worktree", not Path(s2).exists())

        # ── S5a — 그랜트 없으면 스테이징 없음(게이트가 이미 막는 자리) ──
        _ungrant()
        check("S5a_no_grant_no_staging",
              h._red_stage(str(victim), for_write=True) == str(victim))
    finally:
        _ungrant()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    # ══ S5b — git 아닌 저장소: 스테이징 불가 → 라이브 직행 폴백(설치본·폰 몸) ══
    tmp2 = Path(tempfile.mkdtemp(prefix="stg_nogit_")).resolve()
    try:
        _make_repo(tmp2, git=False)
        h._REPO_ROOT = tmp2
        v2 = tmp2 / "backend" / "cognition" / "victim.py"
        _grant(h, "task_nogit")
        check("S5b_nogit_falls_back_to_live",
              h._red_stage(str(v2), for_write=True) == str(v2))
    finally:
        _ungrant()
        import shutil
        shutil.rmtree(tmp2, ignore_errors=True)

    # ══ S11 — 열린 턴 재해소: 오염된 agent 필터를 무필터 폴백이 이긴다 (ep1282) ══
    # 재진입 스레드 문맥은 episode_id 를 잃고 agent_id 를 'agent_001' 로 오염시킨다 —
    # 필터 0건이 곧 '문맥 없음'(10초 유예→턴 절단)으로 떨어지면 안 된다.
    tmp3 = Path(tempfile.mkdtemp(prefix="stg_epi_")).resolve()
    try:
        import sqlite3
        db3 = tmp3 / "data" / "world_pulse.db"
        db3.parent.mkdir(parents=True, exist_ok=True)
        conn3 = sqlite3.connect(db3)
        # ★source 열 — 2026-08-22 `5a42ea5`(B18-2)가 재해소 쿼리에 `COALESCE(source,…)`
        #   를 넣으면서 이 픽스처가 낡았다. 열이 없으면 쿼리가 던지고 재해소는 except 로
        #   None 이 되어 S11 셋이 통째로 빨강이 된다(픽스처 부패 — 수리 대상은 코드가 아님).
        conn3.execute("CREATE TABLE episode_log (id INTEGER PRIMARY KEY, started_at TEXT, "
                      "ended_at TEXT, agent TEXT, user_message TEXT, log TEXT, "
                      "total_ms INTEGER, source TEXT)")
        conn3.execute("INSERT INTO episode_log (id, started_at, ended_at, agent) "
                      "VALUES (1, '2026-08-20T15:00:00', '2026-08-20T15:01:00', 'system_ai')")
        conn3.execute("INSERT INTO episode_log (id, started_at, ended_at, agent) "
                      "VALUES (2, '2026-08-20T15:01:29', NULL, 'system_ai')")
        conn3.commit()
        conn3.close()
        import importlib.util as _ilu
        spec_ra = _ilu.spec_from_file_location(
            "red_apply_s11", str(REPO / "backend" / "datastore" / "red_apply.py"))
        ra = _ilu.module_from_spec(spec_ra)
        spec_ra.loader.exec_module(ra)
        check("S11_executor_wrong_agent_falls_back",
              ra._resolve_open_episode(str(db3), "agent_001") == 2)
        check("S11_executor_right_agent_direct",
              ra._resolve_open_episode(str(db3), "system_ai") == 2)
        check("S11_scheduler_wrong_agent_falls_back",
              st._current_episode_id(str(tmp3), "agent_001") == 2)
        conn3 = sqlite3.connect(db3)
        conn3.execute("UPDATE episode_log SET ended_at='2026-08-20T15:02:35' WHERE id=2")
        conn3.commit()
        conn3.close()
        check("S11_no_open_row_stays_none",
              ra._resolve_open_episode(str(db3), "agent_001") is None
              and st._current_episode_id(str(tmp3), "agent_001") is None)
    finally:
        import shutil
        shutil.rmtree(tmp3, ignore_errors=True)

    # ══ S12 — frontend 타입검사 관문 (2026-08-22 신설) ══
    # RED 구역에 frontend 가 있는데 관문은 전부 파이썬용이었다 — 이 경로로 .tsx 10건이
    # 무검사 통과한 것이 실측 근거. 여기서는 가짜 워크트리에 진짜 tsc 를 돌린다
    # (node_modules 는 라이브에서 빌리고 즉시 회수 — 라이브는 읽기만).
    check("S12_errors_ignore_position",
          st._tsc_errors("src/a.ts(3,7): error TS2322: Type 'string' is not assignable.")
          == st._tsc_errors("src/a.ts(41,7): error TS2322: Type 'string' is not assignable."),
          "줄·칸이 밀린 같은 오류가 '새 오류'로 보이면 델타 판정이 선행 파손을 볼모로 잡는다")

    tmp4 = Path(tempfile.mkdtemp(prefix="stg_tsc_")).resolve()
    try:
        fe = tmp4 / "frontend"
        (fe / "src").mkdir(parents=True)
        (fe / "tsconfig.app.json").write_text(json.dumps({
            "compilerOptions": {"target": "ES2022", "module": "ESNext",
                                "moduleResolution": "bundler", "strict": True,
                                "noEmit": True, "skipLibCheck": True},
            "include": ["src"]}), encoding="utf-8")
        live_nm = REPO / "frontend" / "node_modules"

        # (a) node_modules 가 없는 몸 — 정직한 건너뜀이지 빨강이 아니다
        #     (검사 못 하는 것이 apply 를 영원히 막으면 2026-08-18 부류의 재생산)
        g_skip = st._tsc_check(str(tmp4), str(tmp4), ["frontend/src/x.ts"])
        check("S12a_skips_honestly_without_node_modules",
              g_skip["passed"] is True and g_skip.get("skipped") is True and g_skip["detail"],
              json.dumps(g_skip, ensure_ascii=False)[:200])

        if live_nm.is_dir():
            # (b) 타입 오류가 있는 격리 사본은 빨강 — 실 tsc
            (fe / "src" / "x.ts").write_text('export const n: number = "문자열";\n',
                                             encoding="utf-8")
            g_bad = st._tsc_check(str(REPO), str(tmp4), ["frontend/src/x.ts"])
            check("S12b_catches_type_error",
                  g_bad["passed"] is False and "TS2322" in (g_bad.get("detail") or ""),
                  json.dumps(g_bad, ensure_ascii=False)[:300])
            # (c) ★심링크 회수 — 격리 사본에 라이브를 가리키는 잔재를 남기지 않는다
            #     (워크트리 청소가 라이브 node_modules 를 향하게 되는 자리)
            check("S12c_borrowed_node_modules_returned",
                  not (fe / "node_modules").exists() and not (fe / "node_modules").is_symlink())
            # (d) 깨끗한 사본은 초록
            (fe / "src" / "x.ts").write_text('export const n: number = 3;\n', encoding="utf-8")
            g_ok = st._tsc_check(str(REPO), str(tmp4), ["frontend/src/x.ts"])
            check("S12d_clean_passes", g_ok["passed"] is True and not g_ok.get("skipped"),
                  json.dumps(g_ok, ensure_ascii=False)[:300])
        else:
            check("S12b_live_node_modules_absent_skipped", True,
                  "라이브 frontend/node_modules 미설치 — 실 tsc 검사 생략")
    finally:
        import shutil
        shutil.rmtree(tmp4, ignore_errors=True)

    print(f"[repair_staging_selftest] {len(_passed)} 통과 / {len(_failed)} 실패")
    for f in _failed:
        print(f"  ✗ {f}")
    print("@@REPAIR_STAGING@@ " + json.dumps(
        {"ok": not _failed, "passed": len(_passed), "failed": _failed}, ensure_ascii=False))
    return 1 if _failed else 0


# ─────────────────────────────────────────────────────────────────────────────
def test_battery_under_pytest():
    """pytest 가 이 배터리를 **보게 하는 다리** (2026-08-23).

    이 파일은 `check(name, cond)` 누적형 스크립트라 `def test_*` 가 없다 — 그래서
    정본 러너(pytest.ini·CI `python -m pytest -m "not local"`)가 여기서 **0건을 수집하고
    조용히 지나갔다**. 실측: 자기수정 격리 생애주기 배터리(63검사)가 CI 에서 한 번도 안 돌고 있었다.
    ★0건 수집은 '통과'가 아니라 '아무것도 안 봤다'이다 — 러너가 그 둘을 같은 초록으로
    보여주는 것이 거짓 초록의 뿌리다(27·28회차 상상훈련이 이 초록을 "전부 통과"로 적었다).
    본문은 모듈 레벨에서 스텁·전역을 만지므로 **별도 프로세스**로 돌린다(공유 프로세스
    오염 회피 — test_framing_amend_gate 가 모듈 스킵을 택한 것과 같은 이유의 반대편 해법).
    """
    import subprocess
    import sys as _sys
    proc = subprocess.run([_sys.executable, os.path.abspath(__file__)],
                          cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, \
        "배터리 실패 (rc=%s)\n%s" % (proc.returncode, ((proc.stdout or "") + (proc.stderr or ""))[-3000:])


# RUNNER: script-battery — 직접 실행이 배터리 전체를 돌리고 실패 시 종료코드≠0 을 낸다.
# pytest 는 이 파일을 다리 시험(별도 프로세스)으로 본다. `__main__` 을 pytest 로
# 위임하면 다리가 자기를 다시 불러 무한 재귀하므로 여기만 위임하지 않는다.
# (가드: backend/test_single_runner.py R2 — 면제는 추론이 아니라 이 선언으로만.)
if __name__ == "__main__":
    raise SystemExit(run())
