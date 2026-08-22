#!/usr/bin/env python3
"""[self:script] 백그라운드 러너 — 별도 프로세스(백엔드 리로드·워커 죽음과 무관하게 생존).
인자: job json 경로. 스크립트를 돌리고 로그·종료코드·stdout 통화를 job json 에 기록한다."""
import json, os, subprocess, sys, time
from pathlib import Path

STDOUT_TAIL = 8000
STDERR_TAIL = 2000


def _write(path, d):
    tmp = path.with_name(path.name + ".tmp~")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def main():
    job_path = Path(sys.argv[1])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job["status"] = "running"; job["pid"] = os.getpid()
    _write(job_path, job)
    started = time.time()
    timed_out = False
    try:
        proc = subprocess.run([job["interpreter"], job["script"]], input=job.get("stdin"),
                              capture_output=True, text=True, timeout=job.get("timeout") or 300,
                              cwd=str(Path(job["script"]).parent))
        code, out, err = proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as te:
        code, timed_out = -1, True
        out = te.stdout.decode("utf-8", "replace") if isinstance(te.stdout, bytes) else (te.stdout or "")
        err = te.stderr.decode("utf-8", "replace") if isinstance(te.stderr, bytes) else (te.stderr or "")
    except OSError as e:
        code, out, err = -2, "", str(e)
    dur = int((time.time() - started) * 1000)
    try:
        Path(job["log"]).write_text(f"# {job['job_id']} exit={code} {dur}ms\n--- stdout ---\n{out}\n--- stderr ---\n{err}", encoding="utf-8")
    except OSError:
        pass
    ok = code == 0 and not timed_out
    job.update({"status": "done" if ok else "failed", "exit_code": code, "duration_ms": dur,
                "ended_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    if not ok:
        job["error"] = ("타임아웃" if timed_out else f"exit {code}") + " — " + err[-STDERR_TAIL:]
    else:
        parsed = None
        try:
            parsed = json.loads(out)
        except (ValueError, TypeError):
            pass
        if isinstance(parsed, dict) and (isinstance(parsed.get("items"), list) or isinstance(parsed.get("table"), dict)):
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
        ok = job.get("status") == "done"
        secs = round((job.get("duration_ms") or 0) / 1000)
        body = (f"{job.get('id')} {'완료' if ok else '실패'} ({secs}초)"
                + ("" if ok else " — " + str(job.get("error", ""))[:200])
                + f"\n결과: [self:script]{{op: \"status\", job_id: \"{job.get('job_id')}\"}}")
        payload = json.dumps({"title": "백그라운드 작업 " + ("완료" if ok else "실패"),
                              "message": body, "type": "info" if ok else "error",
                              "source": "script"}).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{port}/notifications", data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:
        pass


if __name__ == "__main__":
    main()
