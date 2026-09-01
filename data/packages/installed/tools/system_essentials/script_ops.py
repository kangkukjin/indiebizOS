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
- 인터프리터도 같은 이유로 **역할 이름**(python·bash·node)만 적는다 (2026-08-22). 실경로는
  실행 시점에 그 몸이 해소한다 — 원장은 3 OS 로 클론되므로 경로를 얼리면 원리적으로 부서진다.
  옛 형식(경로가 박힌) 원장은 런타임이 자가치유하고, CI(check_win_portability)가 재발을 막는다.

로그: data/script_runs/<id>.log.

긴 작업 핸들(2026-08-21): `run{background:true}` 는 즉시 job_id 를 돌려주고 별도 프로세스
(`_bg_runner.py`, 백엔드 리로드와 무관하게 생존)가 실행·기록한다. `status{job_id|id, wait}` 가
상태·결과를 읽는다(wait≤240초 유한 대기). 왜: ep1253~1256 에서 나레이션 생성이 타임아웃된 뒤
네 에피소드가 Bash `until …; sleep` 폴링이었다 — 폴링 1회=모델 왕복 1회. 원칙(worker-thread-dies-on-reload):
긴 작업=별도 프로세스+상태 파일, "running" 은 살아 있다는 뜻이어야 한다(pid 생존 검사).
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

from common import platform_utils  # OS 이식성 단일 소스(분리 실행·생존 판정)

_ROOT = Path(__file__).resolve().parents[5]  # indiebizOS/
_SCRIPT_DIR = _ROOT / "data" / "scripts"           # 본문 (추적)
_REGISTRY = _SCRIPT_DIR / "registry.yaml"          # 정의 (추적)
_STATE = _ROOT / "data" / "scripts.json"           # 실행 상태 (무시)
_RUN_DIR = _ROOT / "data" / "script_runs"
_JOB_DIR = _RUN_DIR / "jobs"
_BG_RUNNER = Path(__file__).with_name("_bg_runner.py")
_MAX_WAIT = 240

# 확장자 → **역할 이름**(경로 아님). 실경로는 _resolve_interpreter 가 매 실행 해소한다.
_INTERPRETERS = {".py": "python", ".sh": "bash", ".js": "node"}
_STDOUT_TAIL = 8000
_STDERR_TAIL = 2000
_DEFAULT_TIMEOUT = 300


def _coerce_args(args):
    """run 의 args 경계 관용 (2026-08-30, ep2357): dict 또는 JSON 객체 *문자열*.

    받은 dict 는 어차피 json.dumps 로 stdin 에 나가므로, 문자열이 JSON 객체면 같은
    바이트다 — dict 만 고집하던 제약이 41건짜리 원장 배치를 IBL 문장 8KB 인라인
    또는 Bash stdin 우회(등록 통로 밖 실행)로 내몰았다. 이 관용으로
    args: "$file:0" + files_from(큰 본문의 정본 통로)와 조합된다.
    반환: (dict|None, 에러 문자열|None) — 객체 아닌 JSON(배열·스칼라)은 정직 거절.
    """
    if args is None or isinstance(args, dict):
        return args, None
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
        except (ValueError, TypeError):
            return None, ("args 문자열이 JSON 으로 파싱되지 않습니다 — JSON 객체({키: 값}) "
                          "리터럴이나 그 문자열($file:0/files_from 경유 포함)을 주세요.")
        if isinstance(parsed, dict):
            return parsed, None
        return None, f"args 는 JSON 객체({{키: 값}})여야 합니다 — 문자열을 파싱하니 {type(parsed).__name__} 이(가) 나왔습니다."
    return None, "args 는 JSON 객체({키: 값}) 또는 그 JSON 문자열이어야 합니다 — 스크립트 stdin 으로 전달됩니다."


def _args_from_file(path_str):
    """args_file — stdin 으로 보낼 JSON 객체를 **파일에서** 읽는다 (2026-09-01).

    왜 필요했나 (2026-08-30 실측 ④ → 09-01 실측 ⑥ 재발): args 는 JSON 객체(또는 그
    문자열)여야 하는데, 원장 48행 upsert 처럼 payload 가 킬로바이트급인 호출은
    **IBL 문장 안에 8KB 를 리터럴로 박는 것** 말고는 길이 없었다. `$file:0`+files_from
    은 표면이 그 본문을 인라인으로 실어 보내야 해서 같은 값을 두 번 나르고, MCP
    호출 크기 한도에도 걸린다. 그래서 이틀 연속 셸 stdin 우회를 썼다 — 등록 통로 밖
    실행이라 실행 이력·상태·해마가 전부 굶었다(어휘가 있는데 못 쓰는 상태).

    ★파일은 이미 이 몸 안에 있다. 나르지 말고 **가리키면** 된다:
        [self:write]{path: "…/payload.json", content: …} >> …
        [self:script]{op: "run", id: "json원장", args_file: "…/payload.json"}

    계약은 args 와 **같다** — JSON 객체 하나. 배열·스칼라는 정직 거절(스크립트들이
    `{op, path, items}` 모양의 dict 를 stdin 으로 받기로 한 규약).
    반환: (dict|None, 에러 문자열|None)
    """
    p = Path(str(path_str)).expanduser()
    if not p.is_absolute():
        p = (_ROOT / p)
    if not p.is_file():
        return None, (f"args_file 을 찾지 못했습니다: {p} — 실존 파일 경로를 주세요"
                      "(상대경로는 저장소 루트 기준).")
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return None, f"args_file 을 읽지 못했습니다: {e}"
    try:
        parsed = json.loads(text)
    except ValueError as e:
        return None, (f"args_file 이 JSON 이 아닙니다 ({e}) — {p} 의 내용은 JSON 객체"
                      "({키: 값}) 하나여야 합니다.")
    if not isinstance(parsed, dict):
        return None, (f"args_file 은 JSON 객체({{키: 값}})여야 합니다 — {p} 를 파싱하니 "
                      f"{type(parsed).__name__} 이(가) 나왔습니다.")
    return parsed, None


def _resolve_run_args(tool_input):
    """run 의 stdin payload 해소 — args(인라인) 또는 args_file(가리키기) 하나.

    둘 다 오면 정직 거절한다: 어느 쪽이 stdin 이 되는지 조용히 고르면, 고르지 않은
    쪽을 준 사람은 자기 값이 갔다고 믿는다(침묵 오선택 금지).
    반환: (dict|None, 에러|None, 출처 표시 문자열|None)
    """
    has_file = bool(str(tool_input.get("args_file") or "").strip())
    has_args = tool_input.get("args") is not None
    if has_file and has_args:
        return None, ("args 와 args_file 을 함께 줬습니다 — stdin 은 하나입니다. "
                      "큰 payload 면 args_file 만, 작은 리터럴이면 args 만 주세요."), None
    if has_file:
        args, err = _args_from_file(str(tool_input["args_file"]).strip())
        return args, err, str(tool_input["args_file"]).strip()
    args, err = _coerce_args(tool_input.get("args"))
    return args, err, None


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


def _is_python_name(name):
    """python / python3 / python3.13 / python.exe / pythonw … 파이썬 가족인가."""
    n = str(name).lower()
    if n.endswith(".exe"):
        n = n[:-4]
    return n.rstrip("0123456789.") in ("python", "pythonw")


def _resolve_interpreter(raw, suffix=None):
    """원장 값 → **이 몸에서** 실행 가능한 경로. 반환 (경로, note|None).

    ★인터프리터는 '몸의 명사'다 — "지금 무슨 파이썬으로 도는가"는 그 몸의 런타임만 아는
      사실이지, 원장에 적어 다른 몸에 부칠 데이터가 아니다("명사의 자리" 헌법).
      registry.yaml 은 추적되어 3 OS 로 클론되므로 여기에 경로를 얼리면 원리적으로 부서진다
      (맥 .venv/bin/python3 ↔ 윈도우 .venv\\Scripts\\python.exe, 마이너 버전 고착, 홈브루 절대경로).

    해소 순서:
      1. 경로가 박혀 있고(옛 원장·명시 override) 이 몸에 실존하면 → 존중
      2. 박힌 경로가 없으면 → **역할로 되살린다**(다른 기기에서 온 원장 자가치유) + note
      3. 역할 이름: 파이썬 가족 → sys.executable(그 몸 자신) / 그 외 → PATH 조회
    이래서 옛 형식 원장도 마이그레이션 없이 어디서든 돈다.
    """
    s = str(raw or "").strip()
    if not s:
        s = _INTERPRETERS.get(str(suffix or "").lower(), "")
    if not s:
        return "", "인터프리터를 알 수 없습니다 — interpreter 파라미터로 지정하세요."
    note = None
    if "/" in s or "\\" in s:                      # 경로가 박힌 값
        p = Path(s)
        if not p.is_absolute():
            p = _ROOT / s                          # 저장소 상대
        if p.is_file():
            return str(p), None
        note = (f"원장에 박힌 인터프리터 경로({s})가 이 몸에 없어 역할로 해소했습니다 — "
                f"interpreter 를 생략해 재등록하면 어느 기기에서나 풉니다.")
        # ★파일명은 두 구분자 모두로 자른다 — POSIX 의 Path 는 백슬래시를 구분자로 안 봐서
        #   윈도우에서 등록된 원장(C:\\Python\\python.exe)이 맥에 오면 자가치유가 안 된다.
        s = re.split(r"[\\/]", s)[-1]
    if _is_python_name(s):
        return (sys.executable or shutil.which("python3") or shutil.which("python") or "python3"), note
    found = shutil.which(s)
    if not found and s.lower().endswith(".exe"):
        found = shutil.which(s[:-4])          # 윈도우 원장(bash.exe)이 유닉스에 온 경우
    if found:
        return found, note
    return s, (note or f"'{s}' 을 PATH 에서 찾지 못했습니다.")


def _sanitize_id(raw):
    s = re.sub(r"[^0-9A-Za-z가-힣_\-]", "_", str(raw).strip())
    return s[:64]


def _resolve_path(tool_input, raw):
    p = Path(str(raw))
    if not p.is_absolute():
        # 공개 계약과 가이드의 register 예시는 저장소 상대 경로
        # (`data/scripts/정산.py`)다. 시스템 AI의 _project_path 는 보통
        # `<repo>/data`라 여기에 다시 붙이면 `<repo>/data/data/scripts/...`가 되어
        # 문서에 적힌 정답이 실패한다(ep1950). 명시적인 data/scripts 경로는
        # 등록 스크립트의 정본 루트에서 먼저 해소한다.
        parts = p.parts
        if len(parts) >= 2 and parts[:2] == ("data", "scripts"):
            p = _ROOT / p
        else:
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
    interp, _note = _resolve_interpreter(e.get("interpreter"), _script_path(e).suffix)
    if not interp or not (shutil.which(interp) or Path(interp).is_file()):
        problems.append("⚠️ 인터프리터 없음")
    if problems:
        status = " · ".join(problems) + f" — {status}"
    # F16-3 (2026-08-20 상상훈련 16회차): 성패가 summary 산문에만 접혀 "실패한 것만
    # 골라줘"가 파이프 표현 불가였다(F1 규약: 파이프가 물 값은 칸으로 병기).
    # last_status = ok|error|none — 원장이 이미 아는 값의 투영일 뿐.
    return {"title": sid, "meta": f"{e.get('interpreter', '')} · data/scripts/{e.get('file', '')}",
            "summary": f"{e.get('description', '')} — {status}".strip(" —"),
            "registered_at": e.get("registered_at", ""),
            "last_status": ("ok" if lr.get("ok") else "error") if lr else "none",
            "last_run": str(lr.get("at", "")) if lr else "",
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

    # 원장에는 **역할 이름**만 적는다 — 경로를 얼리면 그 몸에서만 도는 원장이 된다.
    # (registry.yaml 은 git 추적 대상이라 3 OS 로 그대로 클론된다.)
    raw_interp = str(tool_input.get("interpreter") or "").strip()
    warn = None
    if not raw_interp:
        interpreter = _INTERPRETERS.get(p.suffix.lower())
        if not interpreter:
            return {"success": False,
                    "error": f"인터프리터를 추론할 수 없습니다({p.suffix}) — interpreter 파라미터로 지정 (예 python3)."}
    elif "/" in raw_interp or "\\" in raw_interp:
        interpreter = _rel_to_root(raw_interp)          # 명시 override — 존중하되 경고
        warn = ("인터프리터에 경로를 박았습니다 — registry.yaml 은 추적되어 다른 기기·OS 로 "
                "클론되므로 그쪽에선 이 경로가 없습니다(런타임이 역할로 되살리지만 의도와 다를 수 있음). "
                "특별한 이유가 없으면 interpreter 를 생략하세요 — 그 몸 자신의 파이썬이 잡힙니다.")
    elif _is_python_name(raw_interp):
        interpreter = "python"                          # python3.13 등 버전 고착을 역할로 정규화
    else:
        interpreter = raw_interp

    sid = _sanitize_id(tool_input.get("id") or p.stem)
    if not sid:
        return {"success": False, "error": "유효한 id 를 만들 수 없습니다 — id 파라미터로 지정."}

    registry = _read_registry()
    updated = sid in registry
    prev = registry.get(sid) or {}
    # timeout 미지정 = "그대로 두라" — 승계하지 않으면 재등록이 기존 값을 조용히 깎는다(silent clamp).
    raw_timeout = tool_input.get("timeout")
    try:
        timeout = int(raw_timeout) if raw_timeout not in (None, "") else int(prev.get("timeout") or _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = int(prev.get("timeout") or _DEFAULT_TIMEOUT)

    registry[sid] = {
        "file": rel,
        "interpreter": interpreter,
        "description": str(tool_input.get("description") or prev.get("description") or ""),
        "timeout": timeout,
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _write_registry(registry)
    return {"success": True, "id": sid, "updated": updated, "path": str(p), "interpreter": interpreter,
            "timeout": timeout,
            **({"warning": warn} if warn else {}),
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

    args, _aerr, _args_src = _resolve_run_args(tool_input)
    if _aerr:
        return {"success": False, "error": _aerr}
    stdin_data = json.dumps(args, ensure_ascii=False) if args is not None else None
    try:
        timeout = int(tool_input.get("timeout") or entry.get("timeout") or _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT

    _RUN_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _RUN_DIR / f"{sid}.log"
    interp, interp_note = _resolve_interpreter(entry.get("interpreter"), p.suffix)
    if tool_input.get("background"):
        return _run_background(sid, entry, p, stdin_data, timeout, interp, interp_note)
    started = time.time()
    try:
        proc = subprocess.run(
            [interp, str(p)],
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
        return {"success": False,
                "error": f"실행 불가: {e} — interpreter({interp or entry.get('interpreter')}) 를 이 몸에서 찾지 못했습니다.",
                **({"interpreter_note": interp_note} if interp_note else {})}
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
                "stderr_tail": stderr[-_STDERR_TAIL:], "log": str(log_path),
                **({"interpreter_note": interp_note} if interp_note else {})}

    res = {"success": True, "id": sid, "exit_code": 0, "duration_ms": duration_ms, "log": str(log_path)}
    if interp_note:
        res["interpreter_note"] = interp_note
    if _args_src:
        # 어디서 온 payload 로 돌았는지 말한다 — 파일을 고쳤는데 옛 값으로 돈 것을
        # 결과만 보고는 알 수 없다(가리키기의 값은 호출 밖에서 바뀐다).
        res["args_file"] = _args_src
        res["args_bytes"] = len(stdin_data or "")
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


# ───────────── 긴 작업 핸들 (background run / status) ─────────────

def _pid_alive(pid):
    """살아 있나? — 판정은 common.platform_utils 한 곳에 있다.
    (윈도우에서 os.kill(pid, 0) 은 질문이 아니라 TerminateProcess 라 그 작업을 죽인다.)"""
    return platform_utils.pid_alive(pid)


def _read_job(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _run_background(sid, entry, script_path, stdin_data, timeout, interp, interp_note=None):
    """별도 프로세스로 실행 — 즉시 job_id 반환. 상태는 data/script_runs/jobs/<job_id>.json."""
    _JOB_DIR.mkdir(parents=True, exist_ok=True)
    job_id = f"{sid}-{time.strftime('%Y%m%d_%H%M%S')}"
    job_path = _JOB_DIR / f"{job_id}.json"
    log_path = _RUN_DIR / f"{job_id}.log"
    job = {"job_id": job_id, "id": sid, "status": "starting", "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "timeout": timeout, "log": str(log_path), "interpreter": interp,
           "script": str(script_path), "stdin": stdin_data}
    _atomic_write(job_path, json.dumps(job, ensure_ascii=False))
    # 러너는 부모(백엔드)의 죽음·리로드를 넘어 살아야 한다 — 분리 방식은 OS 마다 다르므로
    # 공용 spawn_detached 에 맡긴다(유닉스=새 세션 / 윈도우=DETACHED_PROCESS, 세션 개념 없음).
    try:
        runner = platform_utils.spawn_detached(
            [sys.executable or "python3", str(_BG_RUNNER), str(job_path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=str(script_path.parent),
        )
    except OSError as e:
        job["status"] = "failed"; job["error"] = f"러너 기동 실패: {e}"
        _atomic_write(job_path, json.dumps(job, ensure_ascii=False))
        return {"success": False, "job_id": job_id, "error": job["error"]}
    job["runner_pid"] = runner.pid
    _atomic_write(job_path, json.dumps(job, ensure_ascii=False))
    state = _read_state()
    state.setdefault(sid, {})["last_job"] = job_id
    _write_state(state)
    return {"success": True, "job_id": job_id, "id": sid, "status": "running", "log": str(log_path),
            **({"interpreter_note": interp_note} if interp_note else {}),
            "message": f"백그라운드 시작 — [self:script]{{op: \"status\", job_id: \"{job_id}\", wait: 60}} 로 확인(폴링 대신 wait)."}


def op_status(tool_input):
    """작업 상태 — job_id(하나) 또는 id(그 스크립트의 최근 작업들) 또는 전체. wait(초, ≤240)=끝날 때까지 유한 대기."""
    _JOB_DIR.mkdir(parents=True, exist_ok=True)
    job_id = str(tool_input.get("job_id") or "").strip()
    sid = _sanitize_id(tool_input.get("id") or "") if tool_input.get("id") else ""
    try:
        wait = min(int(tool_input.get("wait") or 0), _MAX_WAIT)
    except (TypeError, ValueError):
        wait = 0
    notes = []
    if tool_input.get("wait") and int(tool_input.get("wait")) > _MAX_WAIT:
        notes.append(f"wait 상한 {_MAX_WAIT}초로 줄임")

    def _collect():
        rows = []
        for jp in sorted(_JOB_DIR.glob("*.json"), reverse=True):
            j = _read_job(jp)
            if not j:
                continue
            if job_id and j.get("job_id") != job_id:
                continue
            if sid and j.get("id") != sid:
                continue
            # "running" 은 살아 있다는 뜻이어야 한다 — 러너 pid 가 죽었는데 종료 기록이 없으면 lost
            if j.get("status") in ("starting", "running") and not _pid_alive(j.get("runner_pid")):
                j["status"] = "lost"
                j["error"] = "러너 프로세스가 종료 기록 없이 사라짐(강제 종료·재부팅?) — 로그 확인"
                _atomic_write(jp, json.dumps(j, ensure_ascii=False))
            rows.append(j)
        return rows

    deadline = time.time() + wait
    while True:
        rows = _collect()
        pending = [r for r in rows if r.get("status") in ("starting", "running")]
        if not wait or not pending or time.time() >= deadline:
            break
        time.sleep(2)
    if job_id and not rows:
        return {"success": False, "error": f"job_id 없음: {job_id}"}
    items = []
    for j in rows[:50]:
        row = {k: j.get(k) for k in ("job_id", "id", "status", "started_at", "ended_at", "exit_code", "duration_ms", "log")}
        if j.get("error"):
            row["error"] = j["error"]
        if j.get("status") == "done" and j.get("result") is not None:
            row["result"] = j["result"]
        items.append(row)
    still = [r["job_id"] for r in items if r.get("status") in ("starting", "running")]
    text = f"작업 {len(items)}건" + (f" · 진행 중 {len(still)}" if still else "") + (" · " + ", ".join(notes) if notes else "")
    res = {"success": True, "items": items, "count": len(items), "running": still, "text": text}
    if job_id and len(items) == 1:
        res["status"] = items[0]["status"]
        if items[0].get("result") is not None:
            r = items[0]["result"]
            if isinstance(r, dict):
                for k in ("items", "table", "stdout"):
                    if k in r:
                        res[k] = r[k]
    return res
