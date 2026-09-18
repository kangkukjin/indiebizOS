#!/usr/bin/env python3
"""시험 — 이 몸의 pytest 를 파일·표현식 단위로 돌려 items 통화로 보고(실패 시험 이름·요지 동반).
why: 개발 주행이 `.venv/bin/python -m pytest …` 를 Bash 로 매번 쳤다(2주 187회+). 같은 명령의 되풀이 = 등록 스크립트 자리.
     [self:edit] 로 고친 뒤 [self:script]{op:"run", id:"시험", args:{files:[…]}} 로 닫는다 — 고치기→검증이 한 프로그램에 든다.
args (stdin JSON):
  files    ["backend/test_x.py", …] — 생략하거나 폴더를 주면 **전수**(5천여 시험·약 8분)
  k        pytest -k 표현식(선택)
  timeout  전체 시한(초, 기본 600)
★전수는 전경으로 받지 않는다(2026-09-18, ep3855): 수리 턴이 전수를 전경으로 돌리고 끝나기를 30여 호출로 폴링했고,
  자기 변경과 무관한 기존 실패까지 조사하러 갔다. 수리·개발의 검증은 **바뀐 곳의 시험 파일**이다 — 전수는 커밋 관문과 CI 의 몫.
  꼭 전수가 필요하면 run 에 background:true 를 주고 status{job_id, wait:240} 로 받는다(진행은 stderr 로 흐른다).
산출: {"items": [{"file", "passed", "failed", "errors", "skipped", "ok", "failures":[이름…]}], "ok", "message"}
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
SUMMARY_RE = re.compile(r"(\d+) (passed|failed|error|errors|skipped)")
PROGRESS_RE = re.compile(r"^([.FEsx]+)\s+\[\s*\d+%\]")


def _args():
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        return json.loads(raw) if raw.strip() else {}
    except (ValueError, OSError):
        return {}


def _run(files, k, timeout):
    cmd = [PY, "-m", "pytest", "-q", "-p", "no:warnings", "-rf", *files]
    if k:
        cmd += ["-k", k]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    text = p.stdout + "\n" + p.stderr
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    summary_line = next((l for l in reversed(text.splitlines()) if SUMMARY_RE.search(l)), "")   # 요약 줄이 있으면 그것
    for n, kind in SUMMARY_RE.findall(summary_line):
        counts["errors" if kind.startswith("error") else kind] = int(n)
    if not summary_line:                                   # 이 몸의 pytest 설정은 -q 요약 줄을 안 낸다 — 진행 줄의 글자를 센다
        for line in text.splitlines():
            m = PROGRESS_RE.match(line)
            if m:
                seq = m.group(1)
                counts["passed"] += seq.count("."); counts["failed"] += seq.count("F")
                counts["errors"] += seq.count("E"); counts["skipped"] += seq.count("s") + seq.count("x")
    failures = [m.group(1) for m in re.finditer(r"^FAILED (\S+)", text, re.M)]
    return counts, failures, p.returncode, text


def _whole_suite(requested):
    """전수인가 — files 생략, 또는 폴더를 가리킨 선택."""
    return not requested or any((ROOT / f).is_dir() for f in requested)


def main():
    a = _args()
    requested = a.get("files") or []
    if _whole_suite(requested) and os.environ.get("INDIEBIZ_SCRIPT_MODE") == "foreground":
        print(json.dumps({"success": False, "items": [], "error": (
            "전수 시험(5천여 건·약 8분)은 전경으로 받지 않습니다. 수리·개발의 검증이면 files 에 바뀐 곳의 시험 파일만 주세요"
            "(전수는 커밋 관문·CI 의 몫). 꼭 전수가 필요하면 [self:script]{op:\"run\", id:\"시험\", background:true} 로 돌리고 "
            "[self:script]{op:\"status\", job_id:\"<받은 job_id>\", wait:240} 로 받습니다.")}, ensure_ascii=False))
        return 0
    files = requested or [str(p.relative_to(ROOT)) for p in sorted((ROOT / "backend").glob("test_*.py"))]
    k = a.get("k") or ""
    timeout = float(a.get("timeout") or 600)
    items = []
    t0 = time.time()
    for n, f in enumerate(files, 1):
        print(f"[진행] {n}/{len(files)} {f}", file=sys.stderr, flush=True)     # 백그라운드 status 의 progress 로 보인다
        if not (ROOT / f).exists():
            items.append({"file": f, "ok": False, "passed": 0, "failed": 0, "errors": 1, "skipped": 0, "failures": ["파일 없음"]})
            continue
        try:
            counts, failures, rc, text = _run([f], k, max(5.0, timeout - (time.time() - t0)))
            ok = rc == 0 or (rc == 5 and not failures)          # 5 = 수집 0(k 로 전부 걸러짐)
            items.append({"file": f, "ok": ok, **counts, "failures": failures[:12]})
        except subprocess.TimeoutExpired:
            items.append({"file": f, "ok": False, "passed": 0, "failed": 0, "errors": 1, "skipped": 0, "failures": ["시한 초과"]})
    ok = all(i["ok"] for i in items)
    p_sum = sum(i["passed"] for i in items); f_sum = sum(i["failed"] + i["errors"] for i in items)
    print(json.dumps({"items": items, "ok": ok, "seconds": round(time.time() - t0, 1),
                      "message": f"{len(items)}파일 · 통과 {p_sum} · 실패 {f_sum}" + ("" if ok else " — 실패 목록은 items[].failures")},
                     ensure_ascii=False))
    return 0          # 시험·관문 실패는 *결과*(ok:false·items)이지 스크립트 고장이 아니다 — exit 1 이면 [self:script] 가 "스크립트 실패" 로 봉해 items 가 안 흐른다(ep2862 실측)


if __name__ == "__main__":
    sys.exit(main())
