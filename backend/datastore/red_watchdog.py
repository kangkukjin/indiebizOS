"""
red_watchdog.py - RED 자가수정 감시견 (분리 프로세스)
IndieBiz OS Core

헌법 개정(2026-08-05)의 기계 안전판 Floor #5. 그랜트된 RED 쓰기(backend/*.py)가
일어나면 핸들러가 이 스크립트를 *분리 프로세스*(start_new_session)로 띄운다 —
uvicorn 이 깨진 코드 import 로 죽어도 감시견은 살아남아 롤백한다.

동작:
  1. 조용해질 때까지 대기 — 매니페스트 mtime 이 QUIET_S 초 동안 안 변하면
     (연쇄 편집이 끝나면) 리로드 디바운스(2s)+import 여유를 두고 헬스체크 시작.
  2. /health 폴링 — 살아 있으면 결과 기록 후 퇴근.
  3. 죽어 있으면 자동 롤백 — 백업 복원(신규 파일은 삭제) → .py touch 로 리로드 유발
     → 재폴링 → OS 알림(desktop_notify) + 결과 기록.

★uvicorn --reload 는 워커가 import 에러로 죽어도 리로더 마스터가 살아 파일 변경을
기다린다 — 복원+touch 가 곧 재기동이다. (마스터까지 죽는 부류는 결과 파일에 남겨
사람이 본다.)

사용: python3 red_watchdog.py <manifest.json>
매니페스트: {"repo", "health_url", "files": {절대경로: 백업경로|null}, "task_key"}
표준 라이브러리만 사용(의존성 0).
"""
import json
import os
import shutil
import sys
import time
import urllib.request

QUIET_S = 6.0          # 마지막 쓰기 후 이 시간 동안 추가 쓰기가 없으면 검사 시작
GRACE_S = 5.0          # 리로드 디바운스(2s) + import 여유
HEALTH_TRIES = 20      # 2초 간격 → 최대 40초 대기
HEALTH_INTERVAL = 2.0
MAX_LIFETIME_S = 30 * 60  # 감시견 최장 수명 (매니페스트가 계속 갱신돼도 언젠가 끝냄)

# 안전장치 파일 — 이 파일들이 수정된 태스크는 /health 만으로 부족하다(게이트를 고치다
# 게이트를 죽여도 서버는 멀쩡히 뜬다 = 침묵 결함). 기능 스모크까지 통과해야 한다.
# (③검증자 없는 영역 보강, 2026-08-05)
SAFETY_SUFFIXES = (
    # 물리 이동(2026-08-05 ⑦): 안전장치 둘은 backend/datastore/ 로 이사.
    # suffix 매칭이라 디렉토리 포함 전체 접미사로 적는다.
    "backend/datastore/red_grant.py",
    "backend/datastore/red_watchdog.py",
    "tools/system_essentials/handler.py",
    # 격리 스테이징(2026-08-17) — 여기가 망가지면 수리가 조용히 라이브 직행으로
    # 폴백하거나(격리 상실) 적용이 안 되고도 됐다고 보고될 수 있다. /health 로는
    # 둘 다 안 잡히는 침묵 결함이라 기능 스모크 대상이다.
    "tools/system_essentials/repair_staging.py",
    # 검증 관문 형제(2026-09-01 분리, 1500줄 규칙) — 관문이 죽으면 거짓 초록 부류.
    "tools/system_essentials/repair_gates.py",
    "scripts/red_safety_selftest.py",
)


def _touches_safety(manifest: dict) -> bool:
    files = manifest.get("files") or {}
    return any(p.endswith(s) for p in files for s in SAFETY_SUFFIXES)


def _run_safety_selftest(repo: str):
    """기능 스모크 실행. (통과 여부, 상세) — 스크립트 부재는 통과 취급(구판 호환)."""
    import subprocess
    script = os.path.join(repo, "scripts", "red_safety_selftest.py")
    if not os.path.exists(script):
        return True, "selftest 스크립트 없음(스킵)"
    try:
        p = subprocess.run([sys.executable, script], cwd=repo,
                           capture_output=True, text=True, timeout=120)
        tail = ((p.stdout or "") + (p.stderr or "")).strip()[-400:]
        return p.returncode == 0, tail
    except Exception as e:
        return False, f"selftest 실행 실패: {e}"


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _poll_health(url: str) -> bool:
    for _ in range(HEALTH_TRIES):
        if _healthy(url):
            return True
        time.sleep(HEALTH_INTERVAL)
    return False


def _notify(title: str, body: str):
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import boot_paths  # noqa: F401 — 층 디렉토리 등재 (물리 이동 2026-08-05)
        from desktop_notify import native_notify
        native_notify(title, body)
    except Exception:
        pass


def _keeper_release(repo: str):
    """keeper 일시정지 표식 회수 — 기계가 세운 것(내용 'auto ...')만 지운다.

    ★이 회수가 여기 있는 이유(2026-08-17): 표식을 세운 쪽(RED 쓰기 경로)은 자기가 부른
    리로드에 죽는다 — 회수 단계를 실행할 손이 원리적으로 없다. 감시견은 분리 프로세스라
    그 죽음을 넘어 살아남는 유일한 손이고, 어느 결말(정상·롤백·타임아웃)로 끝나든 여기를
    지난다. 사람이 손으로 세운 표식(빈 파일)은 의도적 정비이므로 건드리지 않는다
    (그쪽은 keeper 의 PAUSE_TTL 만료가 바닥을 받친다)."""
    try:
        flag = os.path.join(repo or "", "data", "backend_keeper_off")
        if not os.path.exists(flag):
            return
        with open(flag, encoding="utf-8") as f:
            if not f.read(4).startswith("auto"):
                return  # 사람이 세운 표식 — 남의 정비 창을 닫지 않는다
        os.remove(flag)
    except Exception:
        pass


def _intentional_shutdown(manifest: dict) -> bool:
    """시스템이 *의도적으로* 꺼졌는가 — Electron 종료 정리·start.sh trap 이 남기는
    표식(data/.intentional_shutdown). 이때 죽은 /health 는 수리 탓이 아니므로
    롤백하면 안 된다(정상 수리를 오판 되돌림 — 수명주기 개편과의 충돌 봉합 08-05).
    다음 시작이 표식을 지우므로, 표식이 있는 동안만 대기/퇴근 판단에 쓴다."""
    try:
        return os.path.exists(os.path.join(manifest.get("repo", ""), "data", ".intentional_shutdown"))
    except Exception:
        return False


def _rollback(manifest: dict) -> list:
    """백업 복원. 신규 파일(backup=null)은 삭제. 복원 목록 반환."""
    restored = []
    for path, backup in (manifest.get("files") or {}).items():
        try:
            if backup and os.path.exists(backup):
                shutil.copy2(backup, path)
                restored.append(path)
            elif backup is None and os.path.exists(path):
                os.remove(path)
                restored.append(path + " (신규분 삭제)")
        except Exception as e:
            restored.append(f"{path} (복원 실패: {e})")
    # 리로드 유발 — 복원된 .py 를 touch (mtime 변경 = uvicorn 리로더 방아쇠)
    for path in (manifest.get("files") or {}):
        if path.endswith(".py") and os.path.exists(path):
            try:
                os.utime(path, None)
            except Exception:
                pass
            break
    return restored


def _manifest_owner(manifest_path: str) -> str:
    """매니페스트가 적어 둔 수리 주체. 못 읽으면 종전 규약(시스템 AI)으로 착지한다 —
    주인을 모른다고 판정을 버리면 그 수리는 어느 입에도 안 걸린다."""
    try:
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f).get("owner") or "system_ai"
    except Exception:
        return "system_ai"


def main():
    manifest_path = sys.argv[1]
    started = time.time()
    result_path = manifest_path.replace("manifest.json", "result.json")

    def _write_result(payload: dict):
        try:
            payload["finished_at"] = time.time()
            # ★판정의 주인을 매니페스트에서 실어 나른다 (2026-08-25) — 회수하는 쪽
            #   (red_report)이 "이 판정이 내 것인가"로 묻기 때문. 매니페스트를 못 읽는
            #   결말(수명 초과 등)도 있으므로 여기서 매번 best-effort 로 읽는다.
            payload.setdefault("owner", _manifest_owner(manifest_path))
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    while True:
        if time.time() - started > MAX_LIFETIME_S:
            _write_result({"outcome": "timeout", "note": "감시견 수명 초과 — 검사 미완"})
            _notify("IndieBiz 자가수정 판정 미완",
                    "감시견 수명이 초과돼 수리 결과를 확정하지 못했습니다. 수동 확인이 필요합니다.")
            return
        # 1. 조용해질 때까지 대기
        try:
            mtime = os.path.getmtime(manifest_path)
        except OSError:
            return  # 매니페스트가 사라짐 — 회수된 것으로 보고 퇴근
        if time.time() - mtime < QUIET_S:
            time.sleep(1.0)
            continue

        time.sleep(GRACE_S)
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            return
        url = manifest.get("health_url", "http://127.0.0.1:8765/health")

        # 2. 헬스체크
        if _poll_health(url):
            # 검사 중 추가 쓰기가 있었으면 다시 조용해질 때까지 루프
            try:
                if os.path.getmtime(manifest_path) > mtime:
                    continue
            except OSError:
                return
            # 2b. 안전장치 파일이 수정된 태스크 — 기능 스모크까지 통과해야 healthy
            if _touches_safety(manifest):
                ok, detail = _run_safety_selftest(manifest.get("repo", ""))
                if not ok:
                    restored = _rollback(manifest)
                    recovered = _poll_health(url)
                    _write_result({
                        "outcome": "rolled_back",
                        "reason": "safety_selftest_failed",
                        "detail": detail,
                        "restored": restored,
                        "recovered": recovered,
                    })
                    _notify("IndieBiz 안전장치 자가검사 실패",
                            f"안전장치 수정이 기능 스모크를 통과하지 못해 자동 롤백했습니다 (복원 {len(restored)}건).")
                    return
            files = list((manifest.get("files") or {}).keys())
            _write_result({"outcome": "healthy", "files": files})
            # ★성공에도 알린다(2026-08-17): 실패만 알리고 성공은 침묵하면, 리로드로 턴이
            #   끊긴 사용자 자리에서 **성공한 수리와 그냥 멎은 수리가 구별되지 않는다**.
            _notify("IndieBiz 자가수정 완료",
                    f"수정 후 서버 정상 확인 (수정 {len(files)}건).")
            return

        # 3. 죽었다 — 단, 의도된 종료(창 닫기·start.sh 종료)면 수리 탓이 아니다: 롤백 금지
        if _intentional_shutdown(manifest):
            _write_result({"outcome": "intentional_shutdown",
                           "note": "시스템이 의도적으로 종료됨 — 수리 보존, 롤백 안 함. "
                                   "다음 부팅이 실패하면 red_backups 백업으로 수동 복원."})
            return

        # 자동 롤백
        restored = _rollback(manifest)
        recovered = _poll_health(url)
        _write_result({
            "outcome": "rolled_back",
            "recovered": recovered,
            "restored": restored,
        })
        if recovered:
            _notify("IndieBiz 자가수정 롤백",
                    f"RED 수정 후 서버가 죽어 자동 롤백했습니다 (복원 {len(restored)}건). 서버는 복구됐습니다.")
        else:
            _notify("IndieBiz 자가수정 롤백 실패",
                    "자동 롤백 후에도 서버가 살아나지 않습니다. 수동 확인이 필요합니다: "
                    + result_path)
        return


if __name__ == "__main__":
    # 어떤 결말이든(정상 퇴근·롤백·타임아웃·예외) 표식은 반드시 회수한다 — 회수를
    # 놓치면 keeper 가 통째로 멎어 감시가 사라진다(그 자리를 PAUSE_TTL 이 받치지만
    # 15분을 그냥 흘려보낼 이유가 없다).
    _repo = ""
    try:
        with open(sys.argv[1], encoding="utf-8") as _f:
            _repo = (json.load(_f) or {}).get("repo", "")
    except Exception:
        pass
    try:
        main()
    finally:
        _keeper_release(_repo)
