"""[self:script] — 등록 스크립트 실행기 (결정화 사다리의 가운데 가로대).

설계선(2026-08-07 결정): **어휘는 코드가 아니라 코드에 대한 참조만 나른다.**
- 저작·디버깅은 도구층(write + run_command — traceback 원문) 그대로. 여기엔 code: 파라미터가 없다.
- 완성·검증된 스크립트를 register 로 원장에 올리면, 워크플로우 step·트리거·앱 버튼·조종실이
  `[self:script]{op:"run", id}` 한 단어로 결정론 실행한다. 옛 shell-IBL 이 죽은 지점
  (코드 문자열이 IBL 파라미터 층을 통과하며 이스케이프·traceback 손실)이 원리적으로 없다.
- 실행=argv 리스트(셸 미경유 — 인젝션·따옴표 지옥 없음), args=JSON stdin.
- 실패는 정직한 통화(exit_code·stderr 꼬리·로그 경로) + 원장 last_error — 신고는 어휘층,
  수리는 도구층(에이전트가 로그 보고 고쳐 재등록).

원장: data/scripts.json (무-flock 원자쓰기 — limb_keys 선례). 로그: data/script_runs/<id>.log.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[5]  # indiebizOS/
_LEDGER = _ROOT / "data" / "scripts.json"
_RUN_DIR = _ROOT / "data" / "script_runs"

_INTERPRETERS = {".py": sys.executable or "python3", ".sh": "/bin/bash", ".js": "node"}
_STDOUT_TAIL = 8000
_STDERR_TAIL = 2000
_DEFAULT_TIMEOUT = 300


def _read_ledger():
    try:
        d = json.loads(_LEDGER.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_ledger(d):
    _LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = _LEDGER.with_name(_LEDGER.name + ".tmp~")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _LEDGER)


def _sanitize_id(raw):
    s = re.sub(r"[^0-9A-Za-z가-힣_\-]", "_", str(raw).strip())
    return s[:64]


def _resolve_path(tool_input, raw):
    p = Path(str(raw))
    if not p.is_absolute():
        p = Path(tool_input.get("_project_path") or ".") / p
    return p.resolve()


def _entry_item(sid, e):
    lr = e.get("last_run") or {}
    if lr:
        verdict = "✅ 성공" if lr.get("ok") else f"🔴 실패(exit {lr.get('exit_code')})"
        status = f"마지막 실행 {str(lr.get('at', ''))[:16]} — {verdict}"
    else:
        status = "실행 이력 없음"
    return {"title": sid, "meta": f"{e.get('interpreter', '')} · {e.get('path', '')}",
            "summary": f"{e.get('description', '')} — {status}".strip(" —"),
            "registered_at": e.get("registered_at", "")}


def op_list(tool_input):
    """등록 목록 + 마지막 실행 상태 (items 통화)."""
    ledger = _read_ledger()
    items = [_entry_item(sid, e) for sid, e in sorted(ledger.items())]
    return {"success": True, "count": len(items), "items": items,
            **({} if items else {"message": "등록된 스크립트가 없습니다 — op:register 로 등록 (path 필수)."})}


def op_register(tool_input):
    """스크립트 등록/갱신 — 실존 파일만, 같은 id 재등록=갱신."""
    raw_path = tool_input.get("path") or tool_input.get("file_path")
    if not raw_path:
        return {"success": False, "error": "path 가 필요합니다 — 등록할 스크립트 파일 경로."}
    p = _resolve_path(tool_input, raw_path)
    if not p.is_file():
        return {"success": False, "error": f"파일을 찾을 수 없습니다: {p}"}

    interpreter = (tool_input.get("interpreter") or "").strip() or _INTERPRETERS.get(p.suffix.lower())
    if not interpreter:
        return {"success": False,
                "error": f"인터프리터를 추론할 수 없습니다({p.suffix}) — interpreter 파라미터로 지정 (예 python3)."}

    sid = _sanitize_id(tool_input.get("id") or p.stem)
    if not sid:
        return {"success": False, "error": "유효한 id 를 만들 수 없습니다 — id 파라미터로 지정."}
    try:
        timeout = int(tool_input.get("timeout", _DEFAULT_TIMEOUT) or _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT

    ledger = _read_ledger()
    updated = sid in ledger
    prev = ledger.get(sid) or {}
    ledger[sid] = {
        "path": str(p),
        "interpreter": interpreter,
        "description": str(tool_input.get("description") or prev.get("description") or ""),
        "timeout": timeout,
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "last_run": prev.get("last_run"),
        "last_error": prev.get("last_error"),
    }
    _write_ledger(ledger)
    return {"success": True, "id": sid, "updated": updated, "path": str(p), "interpreter": interpreter,
            "message": f"등록 {'갱신' if updated else '완료'} — 실행: [self:script]{{op: \"run\", id: \"{sid}\"}}"}


def op_remove(tool_input):
    """등록 해제 — 파일은 지우지 않는다."""
    sid = _sanitize_id(tool_input.get("id") or "")
    ledger = _read_ledger()
    if not sid or sid not in ledger:
        return {"success": False,
                "error": f"등록되지 않은 id: {sid or '(비어 있음)'} — op:list 로 확인. 등록: {', '.join(sorted(ledger)) or '없음'}"}
    ledger.pop(sid)
    _write_ledger(ledger)
    return {"success": True, "id": sid, "message": "등록 해제 (파일은 보존)."}


def op_run(tool_input):
    """등록 id 실행 — argv 리스트(셸 미경유), args=JSON stdin. 실패=exit_code·stderr 정직 반환."""
    sid = _sanitize_id(tool_input.get("id") or "")
    ledger = _read_ledger()
    entry = ledger.get(sid) if sid else None
    if entry is None:
        return {"success": False,
                "error": f"등록되지 않은 id: {sid or '(비어 있음)'} — 임의 경로·코드 실행은 불가, op:register 로 먼저 등록. "
                         f"등록: {', '.join(sorted(ledger)) or '없음'}"}
    p = Path(entry["path"])
    if not p.is_file():
        return {"success": False,
                "error": f"등록된 파일이 사라졌습니다: {p} — 파일 복구 후 재등록하거나 op:remove."}

    args = tool_input.get("args")
    stdin_data = None
    if args is not None:
        if not isinstance(args, dict):
            return {"success": False, "error": "args 는 JSON 객체({키: 값})여야 합니다 — 스크립트 stdin 으로 전달됩니다."}
        stdin_data = json.dumps(args, ensure_ascii=False)
    try:
        timeout = int(tool_input.get("timeout") or entry.get("timeout") or _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT

    _RUN_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _RUN_DIR / f"{sid}.log"
    started = time.time()
    try:
        proc = subprocess.run(
            [entry["interpreter"], str(p)],
            input=stdin_data, capture_output=True, text=True,
            timeout=timeout, cwd=str(p.parent),
        )
        exit_code, stdout, stderr = proc.returncode, proc.stdout or "", proc.stderr or ""
        timed_out = False
    except subprocess.TimeoutExpired as te:
        exit_code, timed_out = -1, True
        stdout = (te.stdout or b"").decode("utf-8", "replace") if isinstance(te.stdout, bytes) else (te.stdout or "")
        stderr = (te.stderr or b"").decode("utf-8", "replace") if isinstance(te.stderr, bytes) else (te.stderr or "")
    except OSError as e:
        return {"success": False, "error": f"실행 불가: {e} — interpreter({entry['interpreter']}) 존재 여부 확인 후 재등록."}
    duration_ms = int((time.time() - started) * 1000)

    try:
        log_path.write_text(f"# {sid} @ {time.strftime('%Y-%m-%dT%H:%M:%S')} exit={exit_code} {duration_ms}ms\n"
                            f"--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}", encoding="utf-8")
    except OSError:
        pass

    ok = (exit_code == 0) and not timed_out
    entry["last_run"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "ok": ok,
                         "exit_code": exit_code, "duration_ms": duration_ms}
    if not ok:
        entry["last_error"] = {"at": entry["last_run"]["at"], "exit_code": exit_code,
                               "stderr_tail": stderr[-_STDERR_TAIL:]}
    ledger[sid] = entry
    _write_ledger(ledger)

    if not ok:
        return {"success": False, "id": sid, "exit_code": exit_code, "duration_ms": duration_ms,
                **({"timed_out": True, "error": f"타임아웃 {timeout}초 초과 — 스크립트 중단."} if timed_out
                   else {"error": f"스크립트 실패 (exit {exit_code}) — 로그를 보고 도구층(run_command)에서 고친 뒤 재등록."}),
                "stderr_tail": stderr[-_STDERR_TAIL:], "log": str(log_path)}

    res = {"success": True, "id": sid, "exit_code": 0, "duration_ms": duration_ms, "log": str(log_path)}
    # stdout 이 JSON 이고 items/table 을 실으면 통화로 승격 — 파이프로 흐른다.
    parsed = None
    try:
        parsed = json.loads(stdout)
    except (ValueError, TypeError):
        pass
    if isinstance(parsed, dict) and (isinstance(parsed.get("items"), list) or isinstance(parsed.get("table"), dict)):
        for k, v in parsed.items():
            res.setdefault(k, v)
    else:
        res["stdout"] = stdout[-_STDOUT_TAIL:]
    return res
