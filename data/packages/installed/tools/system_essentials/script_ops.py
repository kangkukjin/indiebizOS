"""[self:script] — 등록 스크립트 실행기 (결정화 사다리의 가운데 가로대).

설계선(2026-08-07 결정): **어휘는 코드가 아니라 코드에 대한 참조만 나른다.**
- 저작·디버깅은 도구층(write + run_command — traceback 원문) 그대로. 여기엔 code: 파라미터가 없다.
- 완성·검증된 스크립트를 register 로 원장에 올리면, 워크플로우 step·트리거·앱 버튼·조종실이
  `[self:script]{op:"run", id}` 한 단어로 결정론 실행한다. 옛 shell-IBL 이 죽은 지점
  (코드 문자열이 IBL 파라미터 층을 통과하며 이스케이프·traceback 손실)이 원리적으로 없다.
- 실행=argv 리스트(셸 미경유 — 인젝션·따옴표 지옥 없음), args=JSON stdin.
- 실패는 정직한 통화(exit_code·stderr 꼬리·로그 경로) + 원장 last_error — 신고는 어휘층,
  수리는 도구층(에이전트가 로그 보고 고쳐 재등록).

**등록 스크립트는 어휘처럼 다룬다** (2026-08-16 개정 — 사용자 판정):
- 본문은 `data/scripts/<파일>` 에만 산다. 여기 아니면 register 가 거절한다.
  옛날엔 outputs/ 아래라 .gitignore 에 걸려 **버전 관리 밖**이었다 — 어휘 바로 아래
  가로대인데 백업도 없고 다른 기기에 따라가지도 않았다(경로도 절대경로였다).
- 정의(파일·인터프리터·설명·타임아웃)=`data/scripts/registry.yaml` **추적 대상**.
  어휘가 `ibl_nodes_src/*.yaml` 로 사는 것과 같은 자리.
- 실행 상태(last_run·last_error)=`data/scripts.json` **무시 대상**. 정의와 상태를 안 가르면
  실행할 때마다 원장이 바뀌어 git 이 시끄럽다.
- 파일 경로는 registry 에 **이름만** 적힌다(저장소 상대) — 클론한 어느 기기에서나 돈다.

로그: data/script_runs/<id>.log.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[5]  # indiebizOS/
_SCRIPT_DIR = _ROOT / "data" / "scripts"           # 본문 (추적)
_REGISTRY = _SCRIPT_DIR / "registry.yaml"          # 정의 (추적)
_STATE = _ROOT / "data" / "scripts.json"           # 실행 상태 (무시)
_RUN_DIR = _ROOT / "data" / "script_runs"

_INTERPRETERS = {".py": sys.executable or "python3", ".sh": "/bin/bash", ".js": "node"}
_STDOUT_TAIL = 8000
_STDERR_TAIL = 2000
_DEFAULT_TIMEOUT = 300


def _atomic_write(path, text):
    """무-flock 원자쓰기 (limb_keys 선례)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp~")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _read_registry():
    try:
        d = yaml.safe_load(_REGISTRY.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError, yaml.YAMLError):
        return {}


def _write_registry(d):
    _atomic_write(_REGISTRY, yaml.safe_dump(d, allow_unicode=True, sort_keys=True))


def _read_state():
    try:
        d = json.loads(_STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_state(d):
    _atomic_write(_STATE, json.dumps(d, ensure_ascii=False, indent=1))


def _script_path(entry):
    """registry 의 file(이름)을 실경로로. 저장소 상대라 어느 기기에서나 푼다."""
    return _SCRIPT_DIR / str(entry.get("file") or "")


def _rel_to_root(raw):
    """저장소 안 경로면 상대경로로 접는다 — 다른 기기에서도 풀리도록.
    밖(시스템 인터프리터 등)이면 그대로 둔다.
    ★resolve() 를 쓰지 않는다 — .venv/bin/python3 은 homebrew 로 가는 심볼릭 링크라
      따라가면 저장소 밖이 되어 접히지 않는다(접어야 하는 바로 그 대상이다)."""
    try:
        return Path(raw).relative_to(_ROOT).as_posix()
    except ValueError:
        return str(raw)


def _resolve_interpreter(raw):
    """registry 의 interpreter 를 실행 가능한 형태로. 상대경로면 저장소 기준."""
    s = str(raw or "")
    p = Path(s)
    if s and not p.is_absolute() and "/" in s:
        return str(_ROOT / s)
    return s


def _sanitize_id(raw):
    s = re.sub(r"[^0-9A-Za-z가-힣_\-]", "_", str(raw).strip())
    return s[:64]


def _resolve_path(tool_input, raw):
    p = Path(str(raw))
    if not p.is_absolute():
        p = Path(tool_input.get("_project_path") or ".") / p
    return p.resolve()


def _entry_item(sid, e, state):
    lr = (state.get(sid) or {}).get("last_run") or {}
    if lr:
        verdict = "✅ 성공" if lr.get("ok") else f"🔴 실패(exit {lr.get('exit_code')})"
        status = f"마지막 실행 {str(lr.get('at', ''))[:16]} — {verdict}"
    else:
        status = "실행 이력 없음"
    # ⑱(2026-08-08, 실험 9): 원장은 '마지막 실행'만 알고 '지금 돌 수 있는가'를 몰랐다 —
    # 파일이 사라져도 목록엔 ✅ 로 남는다. 실행자는 대개 새벽의 스케줄러이고 list 가
    # 유일한 점검 창구이므로, pre-flight(파일 실존·인터프리터 해석)를 여기서 한다.
    problems = []
    if not _script_path(e).is_file():
        problems.append("⚠️ 파일 없음")
    interp = _resolve_interpreter(e.get("interpreter")).split()[0]
    if interp and not (shutil.which(interp) or Path(interp).is_file()):
        problems.append("⚠️ 인터프리터 없음")
    if problems:
        status = " · ".join(problems) + f" — {status}"
    return {"title": sid, "meta": f"{e.get('interpreter', '')} · data/scripts/{e.get('file', '')}",
            "summary": f"{e.get('description', '')} — {status}".strip(" —"),
            "registered_at": e.get("registered_at", ""),
            "runnable": not problems}


def op_list(tool_input):
    """등록 목록 + 마지막 실행 상태 (items 통화)."""
    registry, state = _read_registry(), _read_state()
    items = [_entry_item(sid, e, state) for sid, e in sorted(registry.items())]
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

    # 본문은 data/scripts/ 에만 산다 — 여기 있어야 버전 관리되고 다른 기기에서도 돈다.
    # (옛날엔 outputs/ 아래라 .gitignore 에 걸려 백업조차 없었다.)
    try:
        rel = p.relative_to(_SCRIPT_DIR).as_posix()
    except ValueError:
        return {"success": False,
                "error": f"등록 스크립트는 data/scripts/ 안에 있어야 합니다 (지금: {p}).",
                "hint": f"mv '{p}' data/scripts/ 로 옮긴 뒤 그 경로로 다시 register 하세요 — "
                        f"어휘와 같이 버전 관리되고 다른 기기에서도 실행되게 하기 위함입니다."}

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

    registry = _read_registry()
    updated = sid in registry
    prev = registry.get(sid) or {}
    registry[sid] = {
        "file": rel,
        "interpreter": _rel_to_root(interpreter) if "/" in interpreter else interpreter,
        "description": str(tool_input.get("description") or prev.get("description") or ""),
        "timeout": timeout,
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _write_registry(registry)
    return {"success": True, "id": sid, "updated": updated, "path": str(p), "interpreter": interpreter,
            "message": f"등록 {'갱신' if updated else '완료'} — 실행: [self:script]{{op: \"run\", id: \"{sid}\"}}"}


def op_remove(tool_input):
    """등록 해제 — 파일은 지우지 않는다."""
    sid = _sanitize_id(tool_input.get("id") or "")
    registry = _read_registry()
    if not sid or sid not in registry:
        return {"success": False,
                "error": f"등록되지 않은 id: {sid or '(비어 있음)'} — op:list 로 확인. 등록: {', '.join(sorted(registry)) or '없음'}"}
    registry.pop(sid)
    _write_registry(registry)
    state = _read_state()
    if state.pop(sid, None) is not None:
        _write_state(state)
    return {"success": True, "id": sid, "message": "등록 해제 (파일은 보존)."}


def op_run(tool_input):
    """등록 id 실행 — argv 리스트(셸 미경유), args=JSON stdin. 실패=exit_code·stderr 정직 반환."""
    sid = _sanitize_id(tool_input.get("id") or "")
    registry = _read_registry()
    entry = registry.get(sid) if sid else None
    if entry is None:
        return {"success": False,
                "error": f"등록되지 않은 id: {sid or '(비어 있음)'} — 임의 경로·코드 실행은 불가, op:register 로 먼저 등록. "
                         f"등록: {', '.join(sorted(registry)) or '없음'}"}
    p = _script_path(entry)
    if not p.is_file():
        # pre-flight 실패도 상태에 남긴다(⑱) — 안 남기면 list/이력이 이 실패를 영영 모른다
        state = _read_state()
        state.setdefault(sid, {})["last_error"] = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "exit_code": None,
            "preflight": "file_missing", "stderr_tail": f"등록된 파일이 사라짐: {p}"}
        _write_state(state)
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
            [_resolve_interpreter(entry["interpreter"]), str(p)],
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
        interp_shown = _resolve_interpreter(entry.get("interpreter"))
        return {"success": False,
                "error": f"실행 불가: {e} — interpreter({interp_shown}) 존재 여부 확인 후 재등록."}
    duration_ms = int((time.time() - started) * 1000)

    try:
        log_path.write_text(f"# {sid} @ {time.strftime('%Y-%m-%dT%H:%M:%S')} exit={exit_code} {duration_ms}ms\n"
                            f"--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}", encoding="utf-8")
    except OSError:
        pass

    ok = (exit_code == 0) and not timed_out
    state = _read_state()
    st = state.setdefault(sid, {})
    st["last_run"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "ok": ok,
                      "exit_code": exit_code, "duration_ms": duration_ms}
    if not ok:
        st["last_error"] = {"at": st["last_run"]["at"], "exit_code": exit_code,
                            "stderr_tail": stderr[-_STDERR_TAIL:]}
    _write_state(state)

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
