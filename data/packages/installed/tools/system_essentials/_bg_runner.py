#!/usr/bin/env python3
"""[self:script] 백그라운드 러너 — 별도 프로세스(백엔드 리로드·워커 죽음과 무관하게 생존).
인자: job json 경로. 스크립트를 돌리고 로그·종료코드·stdout 통화를 job json 에 기록한다."""
import json, os, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'backend'))
import boot_paths  # noqa: F401 — detached workers use the same value contract as foreground
from script_runtime import atomic_write, parse_output, v2_output, legacy_value_output

STDOUT_TAIL = 8000
STDERR_TAIL = 2000


def _write(path, d):
    atomic_write(path, json.dumps(d, ensure_ascii=False))


LIVE_MARK = "--- stderr (진행, 실시간) ---\n"
POLL_SECONDS = 1.0


def cancel_marker(job_path):
    """취소 요청 표식 — job json 의 유일한 작성자는 러너이므로 요청자는 옆 파일로만 말한다([self:task]{op: cancel})."""
    return Path(job_path).with_suffix(".cancel")


def _kill_tree(proc):
    """스크립트와 그 자손까지 끝낸다 — 직계만 죽이면 시험 러너의 작업자 같은 손자가 남는다."""
    try:
        import psutil
        kids = psutil.Process(proc.pid).children(recursive=True)
    except Exception:
        kids = []
    try:
        proc.kill()
    except OSError:
        pass
    for kid in kids:
        try:
            kid.kill()
        except Exception:
            pass


def main():
    job_path = Path(sys.argv[1])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job["status"] = "running"; job["pid"] = job["runner_pid"] = os.getpid()
    _write(job_path, job)
    started = time.time()
    timed_out = cancelled = False
    marker = cancel_marker(job_path)
    log_path = Path(job["log"])
    # stderr 는 로그 파일에 **실시간**으로 흘린다(2026-09-10). 종전엔 capture_output 이 둘 다 파이프에
    # 가둬 끝날 때 한 번에 썼고, 그래서 status 는 40분 동안 'running' 밖에 말할 게 없었다.
    # stdout 은 통화(JSON) 자리라 그대로 잡아 둔다. 스크립트가 진행을 말하려면 stderr 에 쓰면 된다.
    try:
        log_fh = open(log_path, "w", encoding="utf-8", buffering=1)
        log_fh.write(f"# {job['job_id']} running since {job.get('started_at')}\n{LIVE_MARK}")
    except OSError:
        log_fh = None
    try:
        if marker.exists():          # 시작하기도 전에 취소됨 — 스크립트를 띄우지 않는다
            cancelled, code, out, err = True, -3, "", ""
        else:
            proc = subprocess.Popen([job["interpreter"], job["script"]],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=(log_fh if log_fh else subprocess.PIPE), text=True,
                                    cwd=str(Path(job["script"]).parent))
            deadline = started + (job.get("timeout") or 300)
            feed = job.get("stdin")
            # 짧게 끊어 기다리며 취소 표식과 시간 상한을 본다(재시도해도 출력은 잃지 않는다. 입력은 첫 호출에만 준다).
            while True:
                try:
                    out, err = proc.communicate(input=feed, timeout=POLL_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    feed = None
                    if marker.exists():
                        cancelled = True
                    elif time.time() >= deadline:
                        timed_out = True
                    else:
                        continue
                    _kill_tree(proc)
                    out, err = proc.communicate()
                    break
            code = -3 if cancelled else -1 if timed_out else proc.returncode
            out, err = out or "", err or ""
    except OSError as e:
        code, out, err = -2, "", str(e)
    if log_fh:
        log_fh.close()
        try:
            live = log_path.read_text(encoding="utf-8")
            err = live.split(LIVE_MARK, 1)[1] if LIVE_MARK in live else ""
        except OSError:
            pass
    dur = int((time.time() - started) * 1000)
    try:
        log_path.write_text(f"# {job['job_id']} exit={code} {dur}ms\n--- stdout ---\n{out}\n--- stderr ---\n{err}", encoding="utf-8")
    except OSError:
        pass
    if job.get('callable_contract'):
        parsed, result_error = v2_output(out, job['callable_contract'])
    elif job.get('value_edition') == 2:
        parsed, result_error = legacy_value_output(out)
    else:
        parsed, result_error = parse_output(out)
    ok = code == 0 and not timed_out and not cancelled and not result_error
    job.update({"status": "cancelled" if cancelled else "done" if ok else "failed", "exit_code": code, "duration_ms": dur,
                "ended_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    if cancelled:
        job["error"] = "요청으로 취소됨 — 결과 없음"
    elif not ok:
        job["error"] = ("타임아웃" if timed_out else result_error or f"exit {code}") + " — " + err[-STDERR_TAIL:]
        if parsed is not None:
            job["result"] = parsed
    else:
        if job.get('value_edition') == 2 or job.get('callable_contract'):
            job['result'] = parsed
        elif isinstance(parsed, dict) and (isinstance(parsed.get("items"), list) or isinstance(parsed.get("table"), dict)
                                         or 'operation_outcome' in parsed):
            job["result"] = parsed
        else:
            job["result"] = {"stdout": out[-STDOUT_TAIL:]}
    job.pop("stdin", None)
    _write(job_path, job)
    _announce(job)


def _announce(job):
    """완료를 사용자에게 알린다 — 백그라운드 작업의 **완료 훅**.

    ★2026-08-22: 여기엔 알림이 아예 없었다. 러너는 상태 파일만 쓰고 조용히 죽었고,
    아는 방법은 status{wait≤240} 폴링뿐이라 240초를 넘는 작업(재학습·렌더·수집)은
    **끝나도 아무도 모르는** 구조였다(사용자 실측 호소: "알림이 자꾸 끊긴다").
    러너는 백엔드와 다른 프로세스라 알림함(메모리 deque)에 직접 못 넣는다 —
    그래서 REST 입구로 넣고, 그 입구가 notify_dispatch 단일 관문을 지난다.
    알림 실패가 작업 기록을 망치면 안 되므로 전부 삼킨다(기록은 이미 저장됨).
    """
    try:
        import os
        import urllib.request
        port = os.environ.get("INDIEBIZ_API_PORT", "8765")
        result = job.get('result')
        plain = (job.get('callable_contract') or {}).get('adapter', {}).get('protocol', 'registered-json/1') == 'registered-json/1'
        outcome = result.get('operation_outcome', {}) if plain and isinstance(result, dict) else {}
        work_failed = isinstance(outcome, dict) and outcome.get('status') == 'failed'
        ok = job.get("status") == "done" and not work_failed
        stopped = job.get("status") == "cancelled"      # 사람이 멈춘 것은 실패 알림이 아니다
        word = "완료" if ok else "취소" if stopped else "실패"
        reason = outcome.get('message', '내부 작업 실패') if work_failed else job.get('error', '')
        secs = round((job.get("duration_ms") or 0) / 1000)
        body = (f"{job.get('id')} {word} ({secs}초)"
                + ("" if ok or stopped else " — " + str(reason)[:200])
                + f"\n결과: [self:script]{{op: \"status\", job_id: \"{job.get('job_id')}\"}}")
        payload = json.dumps({"title": "백그라운드 작업 " + word,
                              "message": body, "type": "info" if ok or stopped else "error",
                              "source": "script"}).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{port}/notifications", data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:
        pass


if __name__ == "__main__":
    main()
