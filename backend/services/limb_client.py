"""limb_client.py — 이 몸이 중앙 PC(허브)의 손발(limb)이 되는 클라이언트 (2026-10-13).

설계 정본: docs/INDIEBIZ_BODY_AS_LIMB_DESIGN_2026_10_13.md

역할
- 기존 resident 작업 계약으로 IBL, 준비된 앱 UID shell/Python, 파일 전송을 수행한다.
  IBL은 로컬 엔진, 범용 프로그램은 별도 Android worker에 전달한다.
- 허브 쪽 어휘 = `[limbs:guestpc]{op:"ibl", limb:"<이름>", code:"[...]"}`. 접수증·history·취소·전송은
  상주 PC 와 같은 원장(resident_store)을 쓴다.

보안 (사용자 확정 2026-10-13 — "하드웨어적으로 중앙 PC 와 연결해 설치했을 때만 종속")
- **폰 전용.** PC 는 헬퍼 설치로만 손발이 된다 — 이 모듈은 몸 감지(detect_body)가 폰일 때만 기동한다.
- 자격은 설치 때 USB 로 심긴 **실행 키 하나**(secrets/limb_client.json). 폰에는 초대 키·등록 키가 없고
  다른 허브를 입력할 화면도 없다 — 심긴 허브 하나에만 아웃바운드로 붙는다. 등록 자격은 허브에서
  `provision_phone_limb.py` 가 허브의 1회용 자격을 USB 물리 접근으로 전달한다.
- 인바운드 명령 통로 없음(폰 /ibl/execute 는 localhost). 허브가 remove/revoke 하면 자격을 지우고 멈춘다.
- 실제 준비된 실행 경로만 신고한다. 구형 설치의 미지원 op는 `unsupported_on_this_body`다.
- `media` 봉투(docs/MEDIA_SESSION_CONTRACT.md §6, 2026-10-13): Kotlin MediaBridge 가 import 될 때만
  지원 op 에 든다(지연 판정 — PC 시험에서도 이 모듈을 쓴다). start 는 서비스 **접수**까지만 기다리고
  (워커 스레드를 붙들지 않음) 협상·상태·품질은 폰이 시그널링 WS 로 허브에 직접 보고한다.
  영상·음성 프레임은 Python/JSON 다리를 지나지 않는다.

내구성 (헬퍼 resident_runtime 과 같은 규칙)
- 사건(started/result)은 로컬 spool 에 먼저 적고 다음 sync 에 실어 ack 를 받으면 지운다.
- 작업 기록(jobs/<id>.json)이 running 인 채 프로세스가 죽었으면 재시작 때 `unknown` 결과로 닫는다 —
  부작용을 두 번 내지 않는다.
"""
import json
import os
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

ADAPTER = "indiebiz-v1"
SUPPORTED_OPS = ("ibl", "info")
MEDIA_OPS = ("media", "media_session")       # 전송 계약 op — IBL 어휘가 아니다
MEDIA_BRIDGE_CLASS = "com.indiebiz.phoneagent.media.MediaBridge"
_MEDIA_PURPOSES = {"voice_call", "video_call", "camera", "microphone", "speaker", "playback"}
_bridge_factory: Optional[Callable] = None    # 시험 주입점(가짜 다리) — 없으면 Chaquopy jclass
CONFIG_NAME = "limb_client.json"
EVENT_BATCH = 64
# 허브가 사건 묶음을 통째로 거절하는 코드 — 이런 사건은 재전송해도 영원히 거절되므로 옆으로 치운다.
_DEAD_EVENT_CODES = {"job_not_owned", "invalid_event_id", "invalid_event_kind",
                     "event_too_large", "event_id_conflict", "too_many_events"}

_client: Optional["LimbClient"] = None
_client_lock = threading.Lock()


def _body_profile() -> str:
    """이 몸이 무엇인가 — capability 감지 본체(runtime_utils.detect_body)에 묻는다. 손발 모드는 폰만."""
    try:
        from runtime_utils import detect_body
        return str((detect_body() or {}).get("profile") or "")
    except Exception:  # noqa: BLE001
        return ""


def _media_bridge():
    """Kotlin MediaBridge — 폰 프로파일에서 Chaquopy 로만 존재. 없으면 None(= media 미지원 몸)."""
    if _bridge_factory is not None:
        try:
            return _bridge_factory()
        except Exception:  # noqa: BLE001
            return None
    if _body_profile() != "phone":
        return None
    try:
        from java import jclass  # Chaquopy
        return jclass(MEDIA_BRIDGE_CLASS)
    except Exception:  # noqa: BLE001
        return None


def _screen_bridge():
    if _body_profile() != "phone":
        return None
    try:
        from java import jclass
        return jclass("com.indiebiz.phoneagent.screen.ScreenBridge")
    except Exception:
        return None


def supported_ops() -> List[str]:
    """지원 op — `media` 는 다리가 import 될 때만(지연 판정)."""
    ops = list(SUPPORTED_OPS)
    if _screen_bridge() is not None:
        ops.append("desktop")
    if _media_bridge() is not None:
        ops.append("media")
    from phone_remote_execution import capabilities
    if capabilities():
        ops.extend(("shell", "python", "transfer"))
    from phone_native_control import capabilities as control_capabilities
    if control_capabilities():
        ops.append('control')
    from phone_updates import capabilities as update_capabilities
    if update_capabilities():
        ops.append("phone_update")
    return ops


def validate_media_session(session) -> Optional[str]:
    """계약 §6 봉투의 필수 칸 검사 — 결함이면 사유. (상세 검증은 Kotlin MediaEnvelope.parse 가 한 번 더.)"""
    if not isinstance(session, dict):
        return "session_required"
    sid = session.get("session_id")
    if not isinstance(sid, str) or len(sid) < 8:
        return "session_id_required"
    grant = session.get("grant")
    if not isinstance(grant, dict) or not grant.get("token"):
        return "grant_required"
    if session.get("purpose") not in _MEDIA_PURPOSES:
        return "purpose_unknown"
    stream = session.get("stream")
    url = stream.get("url") if isinstance(stream, dict) else None
    if not isinstance(url, str) or not url.startswith(("ws://", "wss://")):
        return "stream_url_required"
    tracks = session.get("tracks")
    if not isinstance(tracks, list) or not (tracks or isinstance(session.get("content"), dict)):
        return "tracks_required"
    return None


def _media_result(raw) -> Dict:
    """MediaBridge 의 JSON 문자열 → 작업 결과 봉투. {"error": <계약 코드>} 는 success:false 로."""
    try:
        obj = json.loads(str(raw))
    except (TypeError, ValueError):
        return {"success": False, "error": "media_bridge_bad_reply", "raw": str(raw)[:500]}
    if not isinstance(obj, dict):
        return {"success": False, "error": "media_bridge_bad_reply", "raw": obj}
    if obj.get("error"):
        return {"success": False, **obj}
    return {"success": True, **obj}


class LimbError(Exception):
    def __init__(self, code: str, status: int = 0):
        super().__init__(code)
        self.code = code
        self.status = status


def config_path() -> Path:
    """설치 때 심긴 실행 자격. 폰 = filesDir/secrets/limb_client.json (keys.json 과 같은 자리,
    BaseBundle 재추출에 안 지워지는 app-private sibling)."""
    ud = os.environ.get("INDIEBIZ_USERDATA")
    if ud:
        return Path(ud).parent / "secrets" / CONFIG_NAME
    base = os.environ.get("INDIEBIZ_BASE_PATH") or "."
    return Path(base) / "data" / CONFIG_NAME


def spool_dir() -> Path:
    ud = os.environ.get("INDIEBIZ_USERDATA")
    base = Path(ud) if ud else Path(os.environ.get("INDIEBIZ_BASE_PATH") or ".") / "data"
    return base / "limb_spool"


def load_config() -> Optional[Dict]:
    p = config_path()
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(cfg, dict) or not all(cfg.get(k) for k in ("hub", "key", "installation_id")):
        return None
    return cfg


def _json_size(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


class LimbClient:
    def __init__(self, cfg: Dict, port: int, *, post: Callable = None, execute: Callable = None,
                 card: Callable = None, log: Callable = print):
        self.cfg = dict(cfg)
        self.port = int(port)
        self._post = post or self._http_post
        self._execute = execute or self._execute_local
        self._card = card or self._card_local
        self.log = log
        self.generation = cfg.get("generation")
        self.stopped = threading.Event()
        self._wake = threading.Event()
        self._event_wake = threading.Event()
        self._event_push_supported = False
        self._event_publisher = None
        from limb_http_transport import LimbHttpTransport
        self._http = LimbHttpTransport(cfg['hub'])
        self.stop_reason: Optional[str] = None
        self._lock = threading.Lock()
        self._queue: List[Dict] = []          # 접수 순서(큐 순서 = 허브 응답 순서)
        self._running: Optional[str] = None
        self._apk_transferring = False
        self._cancelled = set()
        self._active_cancel = {}
        self._controls = set()
        self._worker: Optional[threading.Thread] = None
        self._card_cache = (0.0, None)
        self.spool = spool_dir()
        (self.spool / "events").mkdir(parents=True, exist_ok=True)
        (self.spool / "events_dead").mkdir(parents=True, exist_ok=True)
        (self.spool / "jobs").mkdir(parents=True, exist_ok=True)

    # ── 전송 ────────────────────────────────────────────────────────────────────
    def _http_post(self, path: str, payload: Dict, timeout: float) -> Dict:
        return self._http(path, payload, timeout)

    def _auth(self) -> Dict:
        return {"key": self.cfg["key"], "installation_id": self.cfg["installation_id"]}

    # ── 실행 ────────────────────────────────────────────────────────────────────
    def _execute_local(self, code: str, agent_id: str, timeout: float) -> Dict:
        """이 몸의 /ibl/execute 로 — localhost 는 인증 통과, 실행 경로 단일(폰 push job 과 동일)."""
        import requests
        from thread_context import get_isolated_origin
        payload = {"code": code, "agent_id": agent_id or "limb"}
        origin = get_isolated_origin()
        if origin:
            payload["origin"] = origin
        try:
            r = requests.post(f"http://127.0.0.1:{self.port}/ibl/execute",
                              json=payload,
                              timeout=(5, float(timeout) + 30))
        except Exception as e:  # noqa: BLE001 — 실행 실패는 결과로 돌려준다(루프는 산다)
            return {"success": False, "error": f"로컬 IBL 실행 실패: {e.__class__.__name__}: {e}"}
        try:
            obj = r.json()
        except ValueError:
            obj = {"result": (r.text or "")[:2000]}
        if not isinstance(obj, dict):
            obj = {"result": obj}
        if r.status_code != 200:
            obj.setdefault("success", False)
            obj.setdefault("error", f"HTTP {r.status_code}")
        return obj

    def _card_local(self) -> Dict:
        import requests
        try:
            r = requests.get(f"http://127.0.0.1:{self.port}/nodes/card", timeout=5)
            card = r.json() if r.status_code == 200 else {}
        except Exception:  # noqa: BLE001
            card = {}
        return card if isinstance(card, dict) else {}

    def capabilities(self) -> Dict:
        """connect/sync 마다 신고 — 허브는 adapter 로 봉투 종류(ibl·info)를 고른다. 16KB 상한."""
        now = time.time()
        ts, card = self._card_cache
        if card is None or now - ts > 600:
            card = self._card() or {}
            self._card_cache = (now, card)
        import platform
        caps = {"adapter": ADAPTER, "body": _body_profile() or "unknown",
                "ops": supported_ops(), "ibl": True, "shell": False,
                "python": platform.python_version(), "alias": self.cfg.get("alias")}
        from phone_remote_execution import capabilities
        caps.update(capabilities())
        from phone_native_control import capabilities as control_capabilities
        caps.update(control_capabilities())
        from phone_updates import capabilities as update_capabilities
        caps.update(update_capabilities())
        screen_bridge = _screen_bridge()
        if screen_bridge is not None:
            caps.update({"os": "android", "desktop_stream": 1})
            try:
                screen_caps = json.loads(str(screen_bridge.capabilities()))
                if isinstance(screen_caps, dict):
                    caps["screen"] = screen_caps
                    caps["screen_reconnect"] = screen_caps.get("reconnect", 0)
            except (AttributeError, TypeError, ValueError):
                pass  # Older APKs only expose projection capture.
        bridge = _media_bridge()
        if bridge is not None:
            try:
                mc = json.loads(str(bridge.capabilities()))
            except (TypeError, ValueError):
                mc = None
            if isinstance(mc, dict) and isinstance(mc.get("media_session"), dict):
                caps["media_session"] = {**mc["media_session"],
                                         **{k: mc.get(k) for k in ("abi", "sdk", "permissions", "engine") if k in mc}}
        if card:
            caps["card"] = card
            while _json_size(caps) > 12 * 1024 and caps.get("card"):
                # 명함이 크면 긴 목록부터 덜어낸다(요약 필드는 남김)
                big = max(caps["card"], key=lambda k: _json_size(caps["card"][k]))
                caps["card"].pop(big)
        return caps

    def info(self) -> Dict:
        return {"body": _body_profile() or "unknown", "adapter": ADAPTER,
                "alias": self.cfg.get("alias"), "device_id": self.cfg.get("device_id"),
                "ops": supported_ops(), "capabilities": self.capabilities()}

    # ── spool: 사건·작업 기록 ───────────────────────────────────────────────────
    def _event(self, job_id: str, kind: str, payload: Dict) -> None:
        eid = f"{kind}:{job_id}"
        rec = {"event_id": eid, "job_id": job_id, "kind": kind, "payload": payload,
               "occurred_at": time.time()}
        if kind == "result" and _json_size(payload) > 1536 * 1024:
            # 허브 상한 2MB — 긴 본문은 미리보기로 줄이고 사실은 남긴다
            text = json.dumps(payload, ensure_ascii=False)
            rec["payload"] = {"success": bool(payload.get("success", True)), "truncated": True,
                              "bytes": len(text.encode("utf-8")), "preview": text[:200000]}
        path = self.spool / "events" / f"{time.time_ns():020d}-{eid.replace(':', '_')}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        self._event_wake.set()
        self._wake.set()

    def _pending_events(self):
        out = []
        for p in sorted((self.spool / "events").glob("*.json")):
            try:
                out.append((p, json.loads(p.read_text(encoding="utf-8"))))
            except (OSError, ValueError):
                continue
            if len(out) >= EVENT_BATCH:
                break
        return out

    def _ack(self, events, ids) -> None:
        ids = set(ids or [])
        for p, rec in events:
            if rec.get("event_id") in ids:
                try:
                    p.unlink()
                except OSError:
                    pass

    def _bury(self, events, why: str) -> None:
        for p, _ in events:
            try:
                os.replace(p, self.spool / "events_dead" / p.name)
            except OSError:
                pass
        self.log(f"[limb] 허브가 사건 묶음을 거절({why}) — {len(events)}건 보류함")

    def _record_path(self, jid: str) -> Path:
        return self.spool / "jobs" / f"{jid}.json"

    def _record(self, jid: str, **fields) -> Dict:
        p = self._record_path(jid)
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rec = {}
        rec.update(fields)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
        return rec

    def _recover(self) -> None:
        """재시작: 실행 중이던 작업은 unknown 으로 닫고(재실행 금지), 접수만 된 작업은 다시 줄 세운다."""
        for p in sorted((self.spool / "jobs").glob("*.json")):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if rec.get("state") == "running":
                result = {"unknown": True, "error": "limb_restarted_during_execution"}
                try:
                    if json.loads(rec["job"].get("code") or "{}").get("op") == "phone_update":
                        from phone_updates import recovered
                        result = recovered(rec["job"])
                except (ValueError, TypeError):
                    pass
                self._event(rec["job"]["id"], "result", result)
                self._record(rec["job"]["id"], state="done", result=result)
            elif rec.get("state") == "queued":
                with self._lock:
                    self._queue.append(rec["job"])
            elif rec.get("state") == "done" and time.time() - float(rec.get("queued_at_s") or 0) > 7 * 86400:
                try:
                    p.unlink()
                except OSError:
                    pass

    # ── 수명 ────────────────────────────────────────────────────────────────────
    def _wipe(self, reason: str) -> None:
        """허브가 이 자격을 더 인정하지 않는다 — 자격을 지우고 멈춘다(자가 제거)."""
        self.stop_reason = reason
        from phone_remote_execution import cancel
        with self._lock:
            for jid, event in self._active_cancel.items():
                event.set()
                cancel(jid)
        try:
            config_path().unlink()
        except OSError:
            pass
        with self._lock:
            self._queue.clear()
        self.stopped.set()
        self.log(f"[limb] 손발 모드 종료: {reason}")

    def _removed(self, state: str) -> None:
        if state == "removal_pending":
            try:
                self._post("removed", self._auth(), 20)
            except Exception as e:  # noqa: BLE001
                self.log(f"[limb] 제거 확인 전송 실패(자격은 지움): {e}")
        self._wipe("허브에서 등록 해제됨")

    # ── 작업 ────────────────────────────────────────────────────────────────────
    def _accept(self, job: Dict) -> None:
        jid = str(job.get("id") or "")
        if not jid or self._record_path(jid).exists():
            return  # 미확인 재제안(undelivered) — 이미 기록됐으면 무시
        self._record(jid, job=job, state="queued", queued_at=time.time_ns(), queued_at_s=time.time())
        with self._lock:
            self._queue.append(job)

    def _cancel(self, jid: str) -> None:
        with self._lock:
            if jid in self._active_cancel:
                self._active_cancel[jid].set()
                from phone_remote_execution import cancel
                cancel(jid)
                return
            idx = next((i for i, j in enumerate(self._queue) if j.get("id") == jid), None)
            if idx is not None:
                self._queue.pop(idx)
            elif self._running == jid or self._record_path(jid).exists() is False:
                return  # 실행 중은 중단 못 함(IBL 동기) / 모르는 작업
            else:
                return
        result = {"cancelled": True}
        self._event(jid, "result", result)
        self._record(jid, state="done", result=result)

    def _dispatch(self, job: Dict) -> Dict:
        try:
            env = json.loads(job.get("code") or "{}")
        except ValueError:
            env = {}
        if not isinstance(env, dict):
            env = {}
        op = env.get("op") or "shell"
        if op == "desktop":
            bridge = _screen_bridge()
            if bridge is None:
                return {"success": False, "error": "unsupported_on_this_body"}
            sid = env.get("screen_id", "")
            import re
            if not isinstance(sid, str) or not re.fullmatch(r"[a-f0-9]{32}", sid):
                return {"success": False, "error": "invalid_screen_id"}
            event = self._active_cancel.setdefault(str(job["id"]), threading.Event())
            done = threading.Event()
            def cancel_screen():
                while not done.wait(0.1):
                    if event.is_set() or self.stopped.is_set():
                        bridge.stop(sid)
            if event.is_set() or self.stopped.is_set():
                return {"success": False, "cancelled": True}
            threading.Thread(target=cancel_screen, daemon=True).start()
            try:
                # Native code reads the installed credential; no key enters job history.
                return json.loads(str(bridge.run(sid)))
            finally:
                done.set()
                bridge.stop(sid)
        if op == "phone_update":
            from phone_updates import execute
            with self._lock:
                if self._controls:
                    return {"success": False, "error": "phone_update_busy"}
                cancelled = self._active_cancel.setdefault(str(job["id"]), threading.Event())
                self._apk_transferring = True
            try:
                return execute(self, job, env, cancelled)
            finally:
                with self._lock:
                    self._apk_transferring = False
        if op == 'control':
            from phone_native_control import execute
            with self._lock:
                event = self._active_cancel.setdefault(str(job['id']), threading.Event())
            return execute(str(job['id']), env, event)
        if op in {"shell", "python", "transfer"}:
            if op not in supported_ops():
                return {"success": False, "error": "unsupported_on_this_body", "op": op}
            jid = str(job["id"])
            with self._lock:
                event = self._active_cancel.setdefault(jid, threading.Event())
            if event.is_set() or self.stopped.is_set():
                return {"success": False, "cancelled": True, "error": "cancelled"}
            if op == "transfer":
                from phone_limb_transfer import execute
                try:
                    return execute(self, env, event)
                except InterruptedError:
                    return {"success": False, "cancelled": True, "error": "transfer_cancelled"}
            from phone_remote_execution import execute
            from thread_context import ISOLATED_ORIGINS, actor_context
            origin = env.get("origin")
            with actor_context(agent_id=job.get("agent_id") or "limb",
                               origin=origin if isinstance(origin, str) and origin in ISOLATED_ORIGINS else None):
                return execute(jid, env, event)
        if op == "ibl":
            code = env.get("ibl") or env.get("code") or ""
            if not isinstance(code, str) or not code.strip():
                return {"success": False, "error": "ibl_code_required"}
            try:
                timeout = float(env.get("timeout") or 1800)
            except (TypeError, ValueError):
                timeout = 1800.0
            agent_id = env.get("agent_id") or job.get("agent_id") or "limb"
            from thread_context import ISOLATED_ORIGINS, actor_context
            origin = env.get("origin")
            if not isinstance(origin, str) or origin not in ISOLATED_ORIGINS:
                origin = None
            with actor_context(origin=origin):
                return self._execute(code, agent_id, timeout)
        if op == "info":
            return {"success": True, **self.info()}
        if op in MEDIA_OPS:
            return self._media_op(env)
        return {"success": False, "error": "unsupported_on_this_body", "op": op,
                "supported": supported_ops()}

    def _media_op(self, env: Dict) -> Dict:
        """허브 미디어 봉투 → Kotlin MediaBridge. 두 모양을 받는다:
        {op:"media", action:start|stop|status, session:{§6 칸}} / {op:"media_session", ...§6 칸 자체}.
        start 는 화면 준비(≤5초)·서비스 접수(≤3초)까지만 기다린다.
        그 뒤는 폰이 시그널링 WS 로 보고하므로 작업 결과를 붙들지 않는다."""
        bridge = _media_bridge()
        if bridge is None:
            return {"success": False, "error": "unsupported_on_this_body", "op": env.get("op"),
                    "supported": supported_ops()}
        action = str(env.get("action") or "start")
        if env.get("op") == "media_session":
            session = {k: v for k, v in env.items() if k not in ("op", "action", "reason")}
        else:
            session = env.get("session")
        try:
            if action == "status":
                return _media_result(bridge.status())
            if action == "stop":
                sid = (session.get("session_id") if isinstance(session, dict) else None) or env.get("session_id") or ""
                return _media_result(bridge.stop(str(sid), str(env.get("reason") or "hub_stop")))
            if action != "start":
                return {"success": False, "error": "unsupported_media_action", "action": action}
            why = validate_media_session(session)
            if why:
                return {"success": False, "error": "invalid_media_envelope", "detail": why}
            payload = dict(session)
            payload["auth"] = self._auth()          # WS 첫 프레임 {key, installation_id, grant} 재료
            return _media_result(bridge.start(json.dumps(payload, ensure_ascii=False)))
        except Exception as e:  # noqa: BLE001 — 다리 예외는 결과로(루프는 산다)
            return {"success": False, "error": f"media_bridge_exception: {e.__class__.__name__}: {e}"}

    def _run_job(self, job: Dict, control: bool = False) -> None:
        jid = str(job.get("id"))
        with self._lock:
            if not control:
                self._running = jid
            self._active_cancel.setdefault(jid, threading.Event())
        self._record(jid, state="running")
        self._event(jid, "started", {})
        try:
            result = self._dispatch(job)
        except Exception as e:  # noqa: BLE001 — 작업 하나의 예외가 루프를 죽이면 안 된다
            result = {"success": False, "error": f"limb_execute_exception: {e.__class__.__name__}: {e}"}
        if not isinstance(result, dict):
            result = {"result": result}
        self._event(jid, "result", result)
        self._record(jid, state="done", result=result)
        # Transfers/install jobs may open their own per-thread pool.
        self._http.close()
        with self._lock:
            self._active_cancel.pop(jid, None)
            self._controls.discard(jid)
            if not control:
                self._running = None

    def _drain(self) -> None:
        while not self.stopped.is_set():
            from phone_updates import busy
            if busy():
                return
            with self._lock:
                if not self._queue:
                    return
                job = self._queue.pop(0)
                self._active_cancel.setdefault(str(job["id"]), threading.Event())
            self._run_job(job)

    def _schedule(self, inline: bool = False) -> None:
        from phone_updates import busy
        if busy():
            return  # sync/capabilities continue; no new work during package replacement.
        with self._lock:
            if self._apk_transferring:
                return  # Do not start parallel controls between download and installer commit.
            if not self._queue:
                return
            if not inline:
                # Readiness and transfers must not wait behind a long program.
                for job in list(self._queue):
                    try:
                        op = json.loads(job.get("code") or "{}").get("op")
                    except (ValueError, AttributeError):
                        op = None
                    if op in {"info", "transfer", "media", "media_session", "desktop"} and len(self._controls) < 4:
                        self._queue.remove(job)
                        self._controls.add(str(job["id"]))
                        self._active_cancel.setdefault(str(job["id"]), threading.Event())
                        threading.Thread(target=self._run_job, args=(job, True), daemon=True).start()
            if inline:
                pass
            elif self._worker and self._worker.is_alive():
                return
            else:
                self._worker = threading.Thread(target=self._drain, name="limb-worker", daemon=True)
                self._worker.start()
                return
        self._drain()

    def _busy(self) -> bool:
        with self._lock:
            return bool(self._queue) or self._running is not None or bool(self._controls)

    # ── sync 한 바퀴 ────────────────────────────────────────────────────────────
    def step(self, *, inline: bool = False, wait: Optional[float] = None) -> Optional[Dict]:
        """허브와 한 번 동기화: 쌓인 사건 올리고, 작업·취소 받아 줄 세우고(또는 inline 실행)."""
        events = [] if self._event_publisher and self._event_push_supported else self._pending_events()
        if wait is None:
            wait = 0 if (self._busy() or events) else 20
        payload = {**self._auth(), "events": [e for _, e in events],
                   "capabilities": self.capabilities(), "wait": wait}
        try:
            resp = self._post("sync", payload, float(wait) + 15)
        except LimbError as e:
            if e.code == "invalid_registration":
                self._wipe("허브가 이 자격을 더 모릅니다(폐기·해제·재설치)")
                return None
            if e.code in _DEAD_EVENT_CODES and events:
                self._bury(events, e.code)
                return None
            raise
        self._ack(events, resp.get("ack"))
        self._event_push_supported = resp.get('event_push') == 1
        if self._event_push_supported:
            self._event_wake.set()
        state = resp.get("state")
        if state in ("removed", "removal_pending"):
            self._removed(state)
            return resp
        gen = resp.get("generation")
        if gen and gen != self.generation:
            self.generation = gen
        for jid in resp.get("cancel") or []:
            self._cancel(str(jid))
        if not resp.get("paused"):
            for job in resp.get("jobs") or []:
                self._accept(job)
        self._schedule(inline=inline)
        return resp

    def _publish_events(self) -> None:
        """A result never waits for the command receiver's in-flight long-poll."""
        backoff = 1.0
        try:
            while not self.stopped.is_set():
                self._event_wake.clear()
                events = self._pending_events() if self._event_push_supported else []
                if not events:
                    self._event_wake.wait(1)
                    continue
                try:
                    resp = self._post('events', {**self._auth(), 'events': [e for _, e in events]}, 15)
                    self._ack(events, resp.get('ack'))
                    if resp.get('state') in ('removed', 'removal_pending'):
                        self._removed(resp['state'])
                    for jid in resp.get('cancel') or []:
                        self._cancel(jid)
                    if not resp.get('ack'):
                        self.stopped.wait(backoff)
                    backoff = 1.0
                except LimbError as error:
                    if error.code == 'invalid_registration':
                        self._wipe('허브가 이 자격을 더 모릅니다(폐기·해제·재설치)')
                    elif error.code in _DEAD_EVENT_CODES:
                        self._bury(events, error.code)
                    else:
                        if error.status == 404:
                            self._event_push_supported = False
                        self.stopped.wait(backoff)
                        backoff = min(30, backoff * 2)
                except Exception as error:
                    self.log(f'[limb] 사건 전송 실패: {type(error).__name__}')
                    self.stopped.wait(backoff)
                    backoff = min(30, backoff * 2)
        finally:
            self._http.close()

    def run(self) -> None:
        self._event_publisher = threading.Thread(target=self._publish_events, name='limb-events', daemon=True)
        self._event_publisher.start()
        try:
            self._run_sync()
        finally:
            self.stopped.set()
            self._event_wake.set()
            self._http.close()
            self._event_publisher.join(26)

    def _run_sync(self) -> None:
        self._recover()
        backoff = 1.0
        self.log(f"[limb] 손발 모드 — 허브 {self.cfg['hub']} 에 '{self.cfg.get('alias')}' 로 대기")
        while not self.stopped.is_set():
            try:
                self._wake.clear()
                self.step()
                backoff = 1.0
            except Exception as e:  # noqa: BLE001 — 네트워크 단절은 일상, 지수 백오프
                self.log(f"[limb] sync 실패(재시도 {backoff:.0f}s): {e.__class__.__name__}: {str(e)[:160]}")
                self.stopped.wait(backoff)
                backoff = min(backoff * 2, 60.0)
                continue
            # 롱폴이 바로 돌아온 경우(작업 있음·사건 있음) 틈 없이 다음 바퀴 — 바쁠 땐 짧게 쉰다
            if self._busy():
                self._wake.wait(0.3)

    def stop(self) -> None:
        self.stopped.set()
        self._wake.set()
        self._event_wake.set()
        from phone_remote_execution import cancel
        with self._lock:
            for jid, event in self._active_cancel.items():
                event.set()
                cancel(jid)


def start(port: int, *, log: Callable = print) -> bool:
    """몸 부팅 때 1회 — 폰이고 설치 자격이 있을 때만 손발 루프를 띄운다. PC 는 절대 아니다."""
    global _client
    if _body_profile() != "phone":
        return False
    cfg = load_config()
    if not cfg:
        return False
    with _client_lock:
        if _client is not None and not _client.stopped.is_set():
            return True
        _client = LimbClient(cfg, port, log=log)
        threading.Thread(target=_client.run, name="limb-client", daemon=True).start()
    return True


def status() -> Dict:
    c = _client
    if c is None:
        return {"active": False, "configured": load_config() is not None}
    return {"active": not c.stopped.is_set(), "alias": c.cfg.get("alias"), "hub": c.cfg.get("hub"),
            "device_id": c.cfg.get("device_id"), "stop_reason": c.stop_reason}
