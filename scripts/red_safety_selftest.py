"""
red_safety_selftest.py - 자기수정 안전장치 기능 스모크 (기계 채점, AI 0)

자체수리 불가 지대 ③ 보강(2026-08-05): 안전장치(게이트·그랜트·백업·워치독) 자체를
수리하다 미묘하게 망가뜨리면, 워치독은 /health 만 보므로 침묵 결함이 된다 — 다음
수리 때에야 드러나는 부류. 이 배터리가 안전장치의 *기능*을 임시 저장소에서 실측한다.

배선 3곳:
  1. red_watchdog — 안전장치 파일이 수정된 태스크는 헬스체크 후 이 배터리도 통과해야
     한다(실패 = 자동 롤백). 게이트를 고치다 게이트를 죽이면 즉시 되돌아간다.
  2. World Pulse 자가점검(12h 면역 순찰) — __static__:red_safety 항목으로 합류.
  3. pre-commit — 안전장치 파일이 스테이징되면 커밋 전 통과 강제.

계약: 마지막 줄에 `@@RED_SAFETY@@ {"ok":bool,"passed":n,"failed":[...]}` 기계 판독
마커. exit 0=전부 통과. 라이브 서버 불요·무접촉(임시 저장소 + 자기 프로세스 전역만).
표준 라이브러리만 사용. 소요 ~5초.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

try:
    import boot_paths  # noqa: F401 — 층 디렉토리 등재 (물리 이동 2026-08-05)
except ImportError:
    pass

_passed = []
_failed = []


def check(name, cond):
    (_passed if cond else _failed).append(name)


def triggers_regex() -> str:
    """안전장치 파일 방아쇠 정규식 — **목록의 거처는 여기가 아니라 워치독**이다.

    ★왜 (2026-08-22): pre-commit 이 이 목록을 하드코딩하고 있었고, 2026-08-05 에
    안전장치 둘이 `backend/datastore/` 로 이사한 뒤 훅의 목록만 옛 경로에 남았다 —
    게다가 `repair_staging.py` 는 애초에 목록에 없었다. 즉 **안전장치 파일을 고쳐도
    커밋 게이트가 안 걸렸다**(이 스크립트를 손으로 돌려야 알았다). IBL 트리거를
    빌더에게 물어보게 만든 2026-07-25 수리와 같은 부류 — 훅은 묻기만 한다.

    suffix 매칭이라 `(^|/)접미사$` 로 낸다(`tools/system_essentials/handler.py` 가
    `data/packages/installed/...` 아래에 있어도 걸리게)."""
    import re as _re
    sys.path.insert(0, str(REPO / "backend" / "datastore"))
    import red_watchdog as _rw
    return "(^|/)(" + "|".join(_re.escape(s) for s in _rw.SAFETY_SUFFIXES) + ")$"


def main():
    spec = importlib.util.spec_from_file_location(
        "h", str(REPO / "data/packages/installed/tools/system_essentials/handler.py"))
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)

    import red_grant
    import thread_context

    tmp = Path(tempfile.mkdtemp(prefix="redself_")).resolve()
    try:
        (tmp / "backend" / "static").mkdir(parents=True)
        (tmp / "frontend").mkdir()
        (tmp / "scripts").mkdir()
        (tmp / "data" / "system_ai_state").mkdir(parents=True)
        foo = tmp / "backend" / "foo.py"
        foo.write_text("x = 1\n")
        h._REPO_ROOT = tmp

        # ── 게이트 ──
        thread_context.clear_all_context()
        red_grant.revoke_grant()
        msg = h._red_zone_violation(str(foo))
        check("gate_refuse_without_grant", bool(msg) and "허가되지 않았습니다" in msg)
        check("gate_static_exempt", h._red_zone_violation(str(tmp / "backend" / "static" / "x.html")) is None)
        check("gate_static_py_still_red", h._red_zone_violation(str(tmp / "backend" / "static" / "e.py")) is not None)
        check("gate_data_pass", h._red_zone_violation(str(tmp / "data" / "x.json")) is None)
        # 게이트 파일 자체 변조 보호(데이터 구역인데도 그랜트 필요)
        check("gate_self_file_protected", h._red_zone_violation(h._SELF_FILE) is not None)

        # ── 그랜트 매칭 ──
        thread_context.set_current_task_id("task_sysai_selftest")
        thread_context.set_current_agent_id("system_ai")
        red_grant.issue_grant("system_ai", "task_sysai_selftest", "selftest")
        check("grant_task_match", h._red_zone_violation(str(foo)) is None)
        thread_context.set_current_task_id("task_sysai_OTHER")
        check("grant_other_task_refused", h._red_zone_violation(str(foo)) is not None)
        thread_context.set_current_task_id("task_sysai_selftest")

        pf = tmp / "data" / "system_ai_state" / "install_approvals.json"
        pf.write_text("{}")
        check("protected_ledger_even_with_grant", h._red_zone_violation(str(pf)) is not None)

        # ── 사전 구문검증 + 백업 ──
        err = h._red_write_prepare(str(foo), "def broken(:\n")
        check("precommit_syntax_reject", bool(err) and "구문 오류" in err)
        check("precommit_valid_pass", h._red_write_prepare(str(foo), "x = 2\n") is None)
        mdir = tmp / "data" / "system_ai_state" / "red_backups" / "task_sysai_selftest"
        manifest = json.loads((mdir / "manifest.json").read_text())
        bpath = manifest["files"].get(str(foo.resolve()))
        check("backup_original", bool(bpath) and Path(bpath).read_text() == "x = 1\n")
        foo.write_text("x = 2\n")
        h._red_write_prepare(str(foo), "x = 3\n")
        manifest = json.loads((mdir / "manifest.json").read_text())
        check("backup_first_write_wins",
              Path(manifest["files"][str(foo.resolve())]).read_text() == "x = 1\n")

        # ── 워치독 롤백 (상수 패치, 죽은 헬스포트) ──
        wd_spec = importlib.util.spec_from_file_location("wd", str(REPO / "backend" / "datastore" / "red_watchdog.py"))
        wd = importlib.util.module_from_spec(wd_spec)
        wd_spec.loader.exec_module(wd)
        wd.QUIET_S, wd.GRACE_S, wd.HEALTH_TRIES, wd.HEALTH_INTERVAL = 0.3, 0.1, 2, 0.1
        notes = []
        wd._notify = lambda t, b: notes.append(t)
        foo.write_text("def broken(:\n")
        m2 = {"repo": str(tmp), "health_url": "http://127.0.0.1:59998/health",
              "task_key": "task_sysai_selftest",
              "files": {str(foo.resolve()): bpath}}
        m2p = mdir / "wdtest" / "manifest.json"
        m2p.parent.mkdir()
        m2p.write_text(json.dumps(m2))
        time.sleep(0.4)
        sys.argv = ["red_watchdog.py", str(m2p)]
        wd.main()
        check("watchdog_rollback_restores", foo.read_text() == "x = 1\n")
        res = json.loads((m2p.parent / "result.json").read_text())
        check("watchdog_result_recorded", res.get("outcome") == "rolled_back")
        check("watchdog_notify_fired", bool(notes))

        # ── 회수 ──
        red_grant.revoke_grant("task_sysai_OTHER")
        check("revoke_wrong_task_noop", h._red_zone_violation(str(foo)) is None)
        red_grant.revoke_grant("task_sysai_selftest")
        check("revoke_closes_gate", h._red_zone_violation(str(foo)) is not None)

        # ── REPAIR 감지 ──
        import cognitive_consciousness as cc

        class D(cc.CognitiveConsciousnessMixin):
            def _log(self, m):
                pass

        d = D()
        check("repair_tag", d._tag_override("#repair x") == "REPAIR")
        check("repair_cue_positive", d._is_repair_cue("백엔드 자막 코드 고쳐줘"))
        check("repair_cue_zone_only_neg", not d._is_repair_cue("백엔드가 뭐야?"))
        check("repair_cue_verb_only_neg", not d._is_repair_cue("사진 고쳐줘"))

        # ── 모델 핀 ──
        import model_resolver as mr
        dsc = mr.resolve("system_repair")
        check("model_pin_top_tier", dsc.get("tier") == "고급")

        # ── 격리 스테이징 이음매 (2026-08-17) ──
        # 무거운 생애주기 배터리는 backend/test_repair_staging.py. 여기서는 워치독이
        # 되돌릴 수 있게 **이음매가 살아 있는지**만 싸게 본다(git 조작 없음).
        stg = h._staging_mod()
        check("staging_contract_present",
              all(callable(getattr(stg, n, None))
                  for n in ("stage_file", "stage_delete", "can_stage", "staged_path",
                            "verify", "op_apply", "op_status", "op_discard", "op_propose")))
        # 그랜트가 없으면 스테이징도 없다 — 게이트가 막는 자리와 같은 조건
        red_grant.revoke_grant()
        thread_context.clear_all_context()
        check("staging_off_without_grant", h._red_stage(str(foo), for_write=True) == str(foo))
        # RED 밖 경로는 스테이징 대상이 아니다(일상 data/ 쓰기가 격리로 새면 안 됨)
        check("staging_ignores_green",
              h._red_stage(str(tmp / "data" / "x.json"), for_write=True) == str(tmp / "data" / "x.json"))
        # 워치독이 이 파일의 수정을 안전장치로 취급하는가 (침묵 결함 방어의 연결고리)
        import red_watchdog as _rw
        check("staging_in_watchdog_safety_list",
              any(s.endswith("repair_staging.py") for s in _rw.SAFETY_SUFFIXES))
        # ★목록의 사본이 셋이다(워치독·스테이징·pre-commit). 셋이 어긋나면 어느 한 층만
        #   조용히 안 걸린다 — 실측(2026-08-22): 훅만 옛 경로에 남아 커밋 게이트가 안 걸렸다.
        check("safety_list_single_truth",
              tuple(h._staging_mod().SAFETY_SUFFIXES) == tuple(_rw.SAFETY_SUFFIXES))
        _hook = (REPO / "scripts/git-hooks/pre-commit").read_text(encoding="utf-8")
        check("precommit_asks_for_safety_triggers",
              "--triggers-regex" in _hook and "backend/red_grant" not in _hook)

        # ── 프롬프트 기계 계약 (분류기·파서가 스위치하는 토큰) ──
        up = (REPO / "data/common_prompts/unconscious_prompt.md").read_text(encoding="utf-8")
        check("prompt_contract_categories",
              all(t in up for t in ("EXECUTE", "THINK", "REPAIR", "SESSION_RESET")))
        # 수리 교리는 2026-09-06 정리(89f81be6)로 조각으로 옮겼다 — 본문에 있으면 모든 턴에
        # 실리므로, REPAIR 턴에만 <repair_doctrine> 로 적재한다. 검사도 그 자리를 따라간다
        # (2026-09-07: 옛 검사가 옮겨간 문구를 본문에서 찾고 있어 정리 이후 줄곧 빨강이었다).
        rp = (REPO / "data/common_prompts/fragments/14_consciousness_repair.md").read_text(encoding="utf-8")
        cp = (REPO / "data/common_prompts/consciousness_prompt.md").read_text(encoding="utf-8")
        check("prompt_contract_repair_rules",
              "수리 안전수칙" in rp and "수리 안전수칙" not in cp)

    finally:
        thread_context.clear_all_context()
        try:
            red_grant.revoke_grant()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)

    ok = not _failed
    for n in _failed:
        print(f"  ✗ {n}")
    print(f"[red_safety_selftest] {len(_passed)} 통과 / {len(_failed)} 실패")
    print("@@RED_SAFETY@@ " + json.dumps({"ok": ok, "passed": len(_passed), "failed": _failed},
                                         ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--triggers-regex" in sys.argv:
        print(triggers_regex())
        sys.exit(0)
    sys.exit(main())
