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

_passed = []
_failed = []


def check(name, cond):
    (_passed if cond else _failed).append(name)


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
        wd_spec = importlib.util.spec_from_file_location("wd", str(REPO / "backend" / "red_watchdog.py"))
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

        # ── 프롬프트 기계 계약 (분류기·파서가 스위치하는 토큰) ──
        up = (REPO / "data/common_prompts/unconscious_prompt.md").read_text(encoding="utf-8")
        check("prompt_contract_categories",
              all(t in up for t in ("EXECUTE", "THINK", "REPAIR", "SESSION_RESET")))
        cp = (REPO / "data/common_prompts/consciousness_prompt.md").read_text(encoding="utf-8")
        check("prompt_contract_repair_rules", "시스템 수리 안전수칙" in cp)

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
    sys.exit(main())
