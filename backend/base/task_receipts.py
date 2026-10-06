"""task_receipts.py — 긴 작업의 공통 접수증 통화·상태 어휘·관찰/제어 등록부 (2026-10-05, 설치 목록 ③).

설계 정본: docs/APP_COMMON_FOUNDATION_GAPS_2026_10_05.md §1-③.
수명이 다른 셋을 섞지 않는다 — 목표(self:goal, 라운드를 거듭하는 의지) / **작업**(task·job, 한 실행) / 티켓(HTTP 연결 복구).
이 모듈은 둘째(작업)의 **관찰·제어 계약**만 둔다. 실행기(위임 task·script job·guestpc·신문 발행·강의 렌더·노트북 색인·
시트 엔진)는 각자 저장소를 그대로 두고 **어댑터 뒤**에 남는다 — 새 저장소를 만들지 않는다.

접수증(통화 1종) — 모든 긴 작업의 즉시 반환:
    {success: true, accepted: true, task_ref: {kind, task_id[, owner]}, state: "queued"|"running"[, status_url], …}
투영(status/wait 의 반환) — **항상 같은 칸**(2026-10-07 긴문장 26회차: 칸이 상황마다 달라 작업을 시작한 뒤의 프로그램이 죽었다):
    {task_ref, state, terminal, timed_out, result(성공일 때만 값·아니면 null), failure(작업의 실패 사유·아니면 null), progress, raw?}
    `error` 는 투영의 칸이 아니다 — **이 낱말 호출 자체의 실패**(값을 못 얻음)에만 실린다. 판본 2 는 `error`/`success:false` 를
    도구 실패로 올리므로, 작업의 사정(failure)과 호출의 사정(error)을 한 칸에 섞으면 "실패한 작업의 상태 조회"가 중단이 된다.
상태 어휘(한 벌) — queued · running · waiting_children · cancel_requested · succeeded · failed · cancelled · interrupted · unknown
    cancel_requested ≠ cancelled(요청과 확인은 다른 사실) · timeout(대기자의 사정, 작업은 계속) ≠ failed(작업의 사정) ·
    interrupted(실행자가 종료 기록 없이 사라짐) ≠ failed · unknown(이 몸이 모르는 작업 — 유실·재기동·남의 작업).

어댑터 등록은 두 길:
  ① 코드(몸의 명사): 인지층이 부팅 때 register() — delegation(routing_system.register_all, 라우터 능력 주입과 같은 의존 역전).
  ② 데이터(사전): 패키지 ibl_actions.yaml 최상위 `task_kinds: {kind: "module:function"}` — 등록되지 않은 kind 를 처음 만나면
     설치 패키지 yaml 을 훑어 그 모듈을 패키지 폴더에서 적재한다(api_engine 의 패키지 모듈 적재와 같은 sys.path 규칙).
base 층이라 위층을 import 하지 않는다 — 어댑터 함수는 값(ref)만 받고 투영을 돌려준다.
"""
import importlib.util
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

QUEUED, RUNNING, WAITING_CHILDREN, CANCEL_REQUESTED = "queued", "running", "waiting_children", "cancel_requested"
SUCCEEDED, FAILED, CANCELLED, INTERRUPTED, UNKNOWN = "succeeded", "failed", "cancelled", "interrupted", "unknown"
STATES = frozenset({QUEUED, RUNNING, WAITING_CHILDREN, CANCEL_REQUESTED, SUCCEEDED, FAILED, CANCELLED, INTERRUPTED, UNKNOWN})
TERMINAL = frozenset({SUCCEEDED, FAILED, CANCELLED, INTERRUPTED})
LIVE = frozenset({QUEUED, RUNNING, WAITING_CHILDREN, CANCEL_REQUESTED})
WAIT_MAX_SECONDS = 240      # self:script status 의 상한과 같다 — 더 긴 작업은 다시 wait 하거나 트리거에 맡긴다
POLL_SECONDS = 1.0

_LOCK = threading.Lock()
_STATUS: dict = {}     # kind -> fn(ref) -> view
_CANCEL: dict = {}     # kind -> fn(ref) -> view
_RESOLVED: set = set()


def receipt(kind: str, task_id, *, state: str = QUEUED, owner: Optional[str] = None, status_url: Optional[str] = None,
            **extra) -> dict:
    """접수증 — 긴 작업을 시작한 낱말이 즉시 돌려주는 통화. 접수는 완료가 아니다."""
    if state not in LIVE:
        raise ValueError(f"접수증 상태는 {sorted(LIVE)} 중 하나입니다 (받음: {state})")
    out = {"success": True, "accepted": True, "task_ref": ref(kind, task_id, owner), "state": state}
    if status_url:
        out["status_url"] = status_url
    out.update(extra)
    return out


def ref(kind: str, task_id, owner: Optional[str] = None) -> dict:
    r = {"kind": str(kind), "task_id": str(task_id)}
    if owner:
        r["owner"] = str(owner)
    return r


def view(r: dict, state: str, *, progress=None, result=None, error: Optional[str] = None, raw=None, **extra) -> dict:
    """어댑터가 돌려주는 투영 — 상태 어휘 밖의 값은 거절(어댑터의 상태 번역 누락을 드러낸다)."""
    if state not in STATES:
        raise ValueError(f"상태 어휘 밖: {state} (허용 {sorted(STATES)})")
    out = {"task_ref": dict(r), "state": state, "terminal": state in TERMINAL, "timed_out": False,
           "result": result if state == SUCCEEDED else None, "failure": error or None, "progress": progress}
    if raw is not None:
        out["raw"] = raw
    out.update(extra)
    return out


def register(kind: str, status_fn: Callable[[dict], dict], cancel_fn: Optional[Callable[[dict], dict]] = None) -> None:
    with _LOCK:
        _STATUS[str(kind)] = status_fn
        if cancel_fn is not None:
            _CANCEL[str(kind)] = cancel_fn
        else:
            _CANCEL.pop(str(kind), None)


def registered() -> list:
    with _LOCK:
        return sorted(_STATUS)


def normalize_ref(value, kind: Optional[str] = None, task_id=None, owner: Optional[str] = None) -> Optional[dict]:
    """`ref:` 인자(접수증 통째·task_ref·문자열) 또는 평탄 kind/task_id 를 하나의 ref 로. 못 만들면 None."""
    if isinstance(value, dict):
        inner = value.get("task_ref") if isinstance(value.get("task_ref"), dict) else value
        k = inner.get("kind") or kind
        t = inner.get("task_id") if inner.get("task_id") not in (None, "") else task_id
        o = inner.get("owner") or owner
        if k and t not in (None, ""):
            return ref(k, t, o)
        return None
    if isinstance(value, str) and value.strip():
        if ":" in value and not kind:
            k, _, t = value.partition(":")
            return ref(k.strip(), t.strip(), owner) if k.strip() and t.strip() else None
        if kind:
            return ref(kind, value.strip(), owner)
        return None
    if kind and task_id not in (None, ""):
        return ref(kind, task_id, owner)
    return None


# ── 어댑터 해소(데이터 길) ─────────────────────────────────────────────────────

def _packages_root() -> Optional[Path]:
    try:
        from runtime_utils import get_base_path
        return Path(get_base_path()) / "data" / "packages" / "installed" / "tools"
    except Exception:
        return None


def _resolve_from_packages(kind: str) -> bool:
    """설치 패키지의 `task_kinds` 선언에서 kind 의 어댑터를 찾아 적재·등록. 찾았으면 True."""
    root = _packages_root()
    if root is None or not root.is_dir():
        return False
    try:
        import yaml
    except ImportError:
        return False
    for pkg_dir in sorted(root.iterdir()):
        frag = pkg_dir / "ibl_actions.yaml"
        if not frag.is_file():
            continue
        try:
            doc = yaml.safe_load(frag.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        kinds = doc.get("task_kinds") if isinstance(doc, dict) else None
        if not isinstance(kinds, dict) or kind not in kinds:
            continue
        spec = str(kinds[kind] or "")
        module_name, _, func_name = spec.partition(":")
        candidate = pkg_dir / f"{module_name}.py"
        if not module_name or not func_name or not candidate.is_file():
            return False
        pkg_str = str(pkg_dir)
        if pkg_str not in sys.path:
            sys.path.insert(0, pkg_str)   # 패키지 형제 모듈 import 규칙 — api_engine 의 적재와 같다
        try:
            mod = sys.modules.get(module_name)
            if mod is None or not hasattr(mod, func_name):
                mspec = importlib.util.spec_from_file_location(module_name, candidate)
                mod = importlib.util.module_from_spec(mspec)
                sys.modules[module_name] = mod
                mspec.loader.exec_module(mod)
            fn = getattr(mod, func_name)
        except Exception:
            return False
        cancel = getattr(mod, f"{func_name}_cancel", None)
        register(kind, fn, cancel if callable(cancel) else None)
        return True
    return False


def _adapter(kind: str, table: dict):
    with _LOCK:
        fn = table.get(kind)
        tried = kind in _RESOLVED
    if fn is None and not tried:
        with _LOCK:
            _RESOLVED.add(kind)
        _resolve_from_packages(kind)
        with _LOCK:
            fn = table.get(kind)
    return fn


# ── 관찰·제어 ──────────────────────────────────────────────────────────────────

def status(r: dict) -> dict:
    """현재 투영. 모르는 kind 면 unknown(실패로 꾸미지 않는다)."""
    fn = _adapter(r["kind"], _STATUS)
    if fn is None:
        return view(r, UNKNOWN, error=f"이 몸이 모르는 작업 종류 '{r['kind']}' — 어댑터 미등록(잠든 패키지이거나 다른 몸의 작업)")
    try:
        out = fn(r)
    except Exception as exc:  # noqa: BLE001 — 어댑터 예외는 unknown 으로 정직하게(작업이 실패한 것이 아니다)
        return view(r, UNKNOWN, error=f"상태 조회 실패({type(exc).__name__}): {exc}")
    if not isinstance(out, dict) or out.get("state") not in STATES:
        return view(r, UNKNOWN, error=f"어댑터 '{r['kind']}' 가 상태 어휘 밖의 투영을 돌려줌")
    return _stable(r, out)


def _stable(r: dict, out: dict) -> dict:
    """어댑터가 view() 를 거치지 않고 만든 투영도 같은 칸을 갖게 한다(옛 `error` 칸은 failure 로 옮긴다)."""
    out = dict(out)
    legacy = out.pop("error", None)
    out.setdefault("task_ref", dict(r))
    out.setdefault("terminal", out["state"] in TERMINAL)
    out.setdefault("timed_out", False)
    out.setdefault("progress", None)
    out["result"] = out.get("result") if out["state"] == SUCCEEDED else None
    out["failure"] = out.get("failure") or legacy or None
    return out


def _unfinished(v: dict) -> str:
    return v.get("failure") or f"작업이 {v['state']} 상태입니다 — 결과가 없습니다."


def wait(r: dict, timeout: float = 60.0, poll: float = POLL_SECONDS) -> dict:
    """종료 상태가 되거나 timeout 이 끝날 때까지 기다린 뒤 투영.

    **시간 초과는 실패가 아니다(대기자의 사정)** — `success: true, timed_out: true` 와 현재 상태를 값으로 돌려준다.
    프로그램은 `[if:$r.timed_out]` 로 갈라 같은 ref 로 다시 기다린다. 옛 구현은 success:false 라 판본 2 에서 프로그램
    전체가 중단됐고(이미 시작한 작업만 남긴 채), catch 에서도 시간 초과와 작업 실패를 가를 값이 없었다(26회차 L26-2).
    작업이 성공 아닌 종료(failed·cancelled·interrupted)·unknown 이면 **기다린 값을 못 얻은 것**이라 success:false —
    투영 칸(state·failure·task_ref)은 그대로 실려 `$error.details` 로 읽힌다."""
    try:
        requested = float(timeout if timeout is not None else 60.0)
    except (TypeError, ValueError):
        requested = 60.0
    limit = max(0.0, min(requested, WAIT_MAX_SECONDS))
    deadline = time.monotonic() + limit
    while True:
        v = status(r)
        if v["state"] == SUCCEEDED:
            return {"success": True, **v}
        if v["state"] in TERMINAL or v["state"] == UNKNOWN:
            return {"success": False, **v, "error": _unfinished(v)}
        left = deadline - time.monotonic()
        if left <= 0:
            note = f"대기 {int(limit)}초가 끝났습니다 — 작업은 {v['state']} 상태로 계속됩니다(실패 아님). 같은 ref 로 다시 wait 하세요."
            if requested > WAIT_MAX_SECONDS:
                note += f" (timeout 상한 {WAIT_MAX_SECONDS}초로 줄임)"
            return {"success": True, **v, "timed_out": True, "note": note}
        time.sleep(min(max(poll, 0.1), left))


def cancel(r: dict) -> dict:
    """취소 요청. 어댑터가 확인한 사실만 말한다 — 요청을 남겼으면 cancel_requested, 되돌렸으면 cancelled."""
    fn = _adapter(r["kind"], _CANCEL)
    if fn is None:
        cur = status(r)
        return {"success": False, **cur, "error": f"작업 종류 '{r['kind']}' 는 취소를 지원하지 않습니다 (현재 {cur['state']})."}
    try:
        out = fn(r)
    except Exception as exc:  # noqa: BLE001
        cur = status(r)
        return {"success": False, **cur, "error": f"취소 실패({type(exc).__name__}): {exc}"}
    if not isinstance(out, dict) or out.get("state") not in STATES:
        cur = status(r)
        return {"success": False, **cur, "error": f"어댑터 '{r['kind']}' 의 취소 투영이 상태 어휘 밖"}
    out = _stable(r, out)
    if out["state"] in (CANCELLED, CANCEL_REQUESTED):
        return {"success": True, **out}
    return {"success": False, **out, "error": out.get("failure") or f"취소되지 않았습니다 (현재 {out['state']})."}


def _reset_for_tests() -> None:
    with _LOCK:
        _STATUS.clear(); _CANCEL.clear(); _RESOLVED.clear()
