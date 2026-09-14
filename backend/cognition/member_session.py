"""member_session.py — 회원 세션 러너(테넌트 경계): 시스템 AI 싱글턴에 깃발을 꽂지 않는다.

정본: docs/EXTERNAL_SERVICE_APP_HANDOFF.md §3-0 (2026-09-14, 1단계).

회원 세션 = 프로젝트 에이전트 모양의 `AgentRunner` **인스턴스**(레지스트리 미등록·폴링 루프 없음).
같은 인지 파이프라인(cognitive_stream)을 타되 실행 상태·프롬프트·기억 공급원·취소·임시 파일·비용이
세션마다 갈린다. 회원 세션 계약(§3-0 표):
- 실행 상태: 세션별 러너·히스토리(RAM, 상한)·잠금. 주인 `SystemAIRunner` 를 만지지 않는다.
- 프롬프트: 러너 초기화를 회원 주체 안에서 하므로 카탈로그가 회원 부재 필터를 지난다(member_profile).
- 기억: 회상은 주체 관문(0단계)이 닫고, 쓰기는 cognitive_distill._after_response 관문이 닫는다.
- 행위자 봉투: principal member:<id> · agent=member:<id> · task_member_* · origin=member.
- 임시 파일: data/_member_tmp/<nid>-<device>/ (세션 종료·부팅 시 삭제).
- 비용·한도: data/member_policy.json — 회원당 세션 수·동시 턴·일일 턴. 메타 원장 data/member_usage.json
  (주체·날짜·턴 수·토큰만 — 내용 없음).
"""
import json
import os
import shutil
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Dict, Optional

_DEFAULT_POLICY = {
    "max_sessions_per_member": 2,
    "max_concurrent_turns_per_member": 1,
    "daily_turns": 40, "daily_turns_by_level": {}, "global_daily_turns": 400,
    "max_jobs_per_turn": 64,
    "history_turns": 20,
    "allowed_nodes": ["sense", "table", "self", "limbs", "engines"],
    "notice": "",
    "hard_token_limit": 64000, "deadline_s": 1800, "max_model_calls": 80,
    "command_timeout_s": 120, "max_message_chars": 64000,
}
TMP_DIRNAME = "_member_tmp"


def _base() -> Path:
    from runtime_utils import get_base_path
    return Path(get_base_path())


def load_policy(base: Path = None) -> dict:
    p = Path(base or _base()) / "data" / "member_policy.json"
    pol = dict(_DEFAULT_POLICY)
    try:
        pol.update(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        pass
    return pol


class MemberSession:
    def __init__(self, neighbor_id: str, device_id: str, level: Optional[int], name: str, base: Path, policy: dict):
        self.neighbor_id = str(neighbor_id)
        self.device_id = str(device_id or "")
        self.level = level
        self.name = name or f"회원-{self.neighbor_id}"
        self.policy = policy
        self.id = uuid.uuid4().hex[:12]
        self.dir = Path(base) / "data" / TMP_DIRNAME / f"{self.neighbor_id}-{self.device_id or 'nodev'}-{self.id}"
        self.history = deque(maxlen=int(policy.get("history_turns", 20)) * 2)
        self.lock = threading.Lock()
        self.runner = None
        self.created_at = time.time()
        self.last_turn_at = None
        self.turns = 0
        self.cancel = threading.Event()
        self.closed = False

    # ── 러너(회원 주체 안에서 초기화 — 카탈로그·프롬프트가 회원 필터를 지난다) ──
    def _ensure_runner(self):
        if self.runner is not None:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        role_src = Path(_base()) / "data" / "member_role.md"
        agent_name = "회원도우미"
        role_text = role_src.read_text(encoding="utf-8") if role_src.exists() else "회원의 기기와 기억으로 일하는 회원도우미입니다."
        notice = self.policy.get("notice") or ""
        if notice:
            role_text += f"\n\n[고지] {notice}\n"
        (self.dir / f"agent_{agent_name}_role.txt").write_text(role_text, encoding="utf-8")
        from member_runner import MemberRunner
        cfg = {"name": agent_name, "allowed_nodes": list(self.policy.get("allowed_nodes") or []),
               "_project_path": str(self.dir), "_project_id": "", "ai": {},
               "_member": {"neighbor_id": self.neighbor_id, "device_id": self.device_id, "level": self.level, "limits": {k: self.policy[k] for k in ("hard_token_limit", "deadline_s")}}}
        runner = MemberRunner(cfg)   # id 없음 → 레지스트리 미등록, start() 안 함(폴링 루프 없음)
        runner._init_ai()
        self.runner = runner

    def close(self):
        self.cancel.set()
        self.closed = True
        if not self.lock.acquire(blocking=False):
            return
        try:
            self.cleanup()
        finally:
            self.lock.release()

    def cleanup(self):
        self.runner = None
        self.history.clear()
        try:
            if self.dir.exists():
                shutil.rmtree(self.dir, ignore_errors=True)
        except Exception:
            pass


class MemberSessionManager:
    _instance = None
    _ilock = threading.Lock()

    def __init__(self, base: Path = None):
        self.base = Path(base or _base())
        self.policy = load_policy(self.base)
        self.sessions: Dict[tuple, MemberSession] = {}
        self.lock = threading.RLock()
        self.active = {}
        self.sweep_orphans()

    @classmethod
    def instance(cls) -> "MemberSessionManager":
        with cls._ilock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ── 임시 저장소 — 세션 종료·부팅 시 삭제(§3-6) ──
    def sweep_orphans(self) -> int:
        root = self.base / "data" / TMP_DIRNAME
        live = {str(s.dir) for s in self.sessions.values()}
        n = 0
        if root.exists():
            for d in root.iterdir():
                if str(d) not in live:
                    shutil.rmtree(d, ignore_errors=True); n += 1
        return n

    # ── 메타 원장(허용 필드만: 주체·날짜·턴·토큰) ──
    def _usage_path(self) -> Path:
        return self.base / "data" / "member_usage.json"

    def _usage(self) -> dict:
        try:
            return json.loads(self._usage_path().read_text(encoding="utf-8"))
        except Exception:
            return {}

    def turns_today(self, neighbor_id: str) -> int:
        day = time.strftime("%Y-%m-%d")
        return int(((self._usage().get(str(neighbor_id)) or {}).get(day) or {}).get("turns", 0))

    def _bump_usage(self, neighbor_id: str, tokens: Optional[int]):
        day = time.strftime("%Y-%m-%d")
        u = self._usage()
        rec = u.setdefault(str(neighbor_id), {}).setdefault(day, {"turns": 0, "tokens": 0})
        rec["turns"] = int(rec.get("turns", 0)) + 1
        if tokens:
            rec["tokens"] = int(rec.get("tokens", 0)) + int(tokens)
        p = self._usage_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(u, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)

    # ── 세션 ──
    def get_or_create(self, neighbor_id, device_id, level, name) -> MemberSession:
        key = (str(neighbor_id), str(device_id or ""))
        with self.lock:
            s = self.sessions.get(key)
            if s is None:
                mine = [k for k in self.sessions if k[0] == str(neighbor_id)]
                if len(mine) >= int(self.policy.get("max_sessions_per_member", 2)):
                    raise MemberLimit("이 회원의 세션 수가 상한에 닿았습니다 — 다른 기기의 세션을 닫아 주세요.")
                s = MemberSession(neighbor_id, device_id, level, name, self.base, self.policy)
                self.sessions[key] = s
            return s

    def close(self, neighbor_id, device_id) -> bool:
        key = (str(neighbor_id), str(device_id or ""))
        with self.lock:
            s = self.sessions.pop(key, None)
        if s:
            s.close()
        return bool(s)

    def turn(self, neighbor_id, device_id, level, name, message: str, *, local_task_id="", code=None, on_event=None, body_session="") -> dict:
        """회원 한 턴. 접수는 회원별 원자 예약, 내용은 턴 임시 경로와 손발에만 둔다."""
        import principal
        import thread_context as tc
        import member_runtime as mr
        from member_bridge import connected, request
        nid = str(neighbor_id)
        if not message.strip() or len(message) > int(self.policy["max_message_chars"]):
            return {"success": False, "error_type": "input", "error": "메시지가 비었거나 너무 깁니다"}
        with self.lock:
            day = time.strftime("%Y-%m-%d")
            cap = self.policy.get("daily_turns_by_level", {}).get(str(level), self.policy["daily_turns"])
            global_count = sum(int(days.get(day, {}).get("turns", 0)) for days in self._usage().values())
            if global_count >= int(self.policy["global_daily_turns"]):
                return {"success": False, "error_type": "limit", "error": "오늘의 전체 회원 한도에 닿았습니다"}
            if self.turns_today(nid) >= int(cap):
                return {"success": False, "error_type": "limit", "error": "오늘의 대화 한도에 닿았습니다"}
            if self.active.get(nid, 0) >= int(self.policy["max_concurrent_turns_per_member"]):
                return {"success": False, "error_type": "busy", "error": "이 회원의 이전 작업이 진행 중입니다"}
            try:
                s = self.get_or_create(nid, device_id, level, name)
            except MemberLimit as exc:
                return {"success": False, "error_type": "limit", "error": str(exc)}
            if not s.lock.acquire(blocking=False):
                return {"success": False, "error_type": "busy", "error": "이전 대화가 진행 중입니다"}
            self.active[nid] = self.active.get(nid, 0) + 1
            try:
                self._bump_usage(nid, None)  # 실패·취소도 예약한 턴을 소비한다
            except Exception:
                self.active[nid] -= 1
                s.lock.release()
                return {"success": False, "error_type": "storage", "error": "사용량 원장에 기록할 수 없습니다"}
        task_id = f"task_member_{uuid.uuid4().hex}"
        p = principal.member(nid, level, device_id)
        tokens = None
        mr.install_output_guard()
        try:
            with principal.narrow(p, "member_session"), tc.actor_context(
                    agent_id=p.key(), task_id=task_id, origin="member"), mr.turn_scope(
                    s.dir, device_id, task_id, s.cancel, self.policy):
                if principal.current() != p:
                    raise PermissionError("전송 관문의 회원 신원 불일치")
                if s.closed or s.cancel.is_set():
                    return {"success": False, "error_type": "cancelled", "error": "회원 작업이 중단됐습니다"}
                mr.current()["local_task_id"] = local_task_id
                mr.current()["body_session"] = body_session
                online = connected(device_id)
                if local_task_id and not online:
                    return {"success": False, "error": "회원 기기가 연결되어 있지 않습니다"}
                recalled = {}
                if online:
                    recalled = request({"op": "memory_recall", "query": message, "limit": 40})
                    if recalled.get("success") is False:
                        return recalled
                mr.current()["shell_available"] = bool(local_task_id and recalled.get("shell_available"))
                mr.current()["javascript_available"] = bool(local_task_id and recalled.get("javascript_available"))
                if code is None:
                    s._ensure_runner()
                else:
                    # 선언형 앱은 모델을 초기화하거나 호출하지 않는다. 같은 IBL 도구 관문만 사용한다.
                    from member_runner import MemberRunner
                    s.dir.mkdir(parents=True, exist_ok=True)
                    s.runner = MemberRunner.__new__(MemberRunner)
                    s.runner.project_path = s.dir
                    s.runner.config = {}
                if online:
                    s.history.clear()
                    s.history.extend(recalled.get("history", []))
                    s.runner.config["_member_memory"] = json.dumps({"memories": recalled.get("memories", []), "recent_results": recalled.get("recent_results", [])}, ensure_ascii=False)
                    s.runner.config["_member_memory"] += "\n회원 작업 폴더: " + str(recalled.get("workspace", ""))
                    s.runner.config["_member_sentences"] = "\n".join(str(x.get("code", "")) for x in recalled.get("sentences", []))
                from agent_pipeline import drain_stream
                if code is not None:
                    raw = s.runner._member_tool("execute_ibl", {"code": code})
                    value = json.loads(raw) if isinstance(raw, str) else raw
                    result = {"final": json.dumps(value, ensure_ascii=False), "app_result": value,
                              "error": (value.get("error") or ("앱 실행 실패" if value.get("success") is False else None)) if isinstance(value, dict) else None}
                else:
                    def events():
                        for event in s.runner.cognitive_stream(message, list(s.history), agent_name="회원도우미", cancel_check=s.cancel.is_set):
                            if on_event and event.get("type") in ("text", "tool_call", "tool_result", "tool_start", "status", "error"):
                                on_event(event)
                            yield event
                    result = drain_stream(events())
                response = result.get("final") or result.get("error") or ""
                tokens = result.get("turn_tokens")
                success = not bool(result.get("error")) and not s.cancel.is_set()
                saved = False
                if online and not s.cancel.is_set():
                    receipt = request({"op": "memory_save", "record": {
                        "id": task_id, "user": message, "assistant": response,
                        "episode": {"task": task_id, "success": success,
                                    "tool_calls": result.get("tool_calls", [])}}})
                    saved = receipt.get("success") is True and receipt.get("saved") is True
                    if saved and success and code is None:
                        # 선별도 같은 회원 예산 안에서 끝낸다. 저장은 회원 기기의 승인 판을 지난다.
                        from providers.base import turn_token_scope, read_turn_tokens
                        remaining = max(1, int(self.policy["hard_token_limit"]) - int(tokens or 0))
                        try:
                            with turn_token_scope(p.key(), task_id, (), hard_token_limit=remaining, deadline_s=20):
                                for index, content in enumerate(s.runner.select_local_memory(message)):
                                    request({"op": "memory_save", "record": {"id": f"{task_id}:memory:{index}", "content": content}})
                                tokens = int(tokens or 0) + int(read_turn_tokens() or 0)
                        except Exception:
                            pass  # 대화 저장 성공과 장기 기억 선별 실패는 다른 결과다.
                s.history.append({"role": "user", "content": message})
                s.history.append({"role": "assistant", "content": response})
                s.turns += 1
                s.last_turn_at = time.time()
                return {"success": success, "response": response, "error": result.get("error"), "memory_saved": saved,
                        "session": s.id, "task_id": task_id, "tokens": tokens, "app_result": result.get("app_result"),
                        "turns_today": self.turns_today(nid)}
        except Exception as exc:
            # 예외 문자열은 경로·요청·모델 원문을 포함할 수 있으므로 허브 로그에 기록하지 않는다.
            return {"success": False, "error_type": type(exc).__name__,
                    "error": "회원 작업을 완료하지 못했습니다. 모델 설정과 기기 연결을 확인하세요."}
        finally:
            # 인지 생성기가 반환한 뒤에만 삭제. close()는 진행 중인 작업의 경로를 먼저 지우지 않는다.
            remembered = list(s.history) if not s.closed else []
            s.cleanup()
            s.history.extend(remembered)
            s.lock.release()
            with self.lock:
                self.active[nid] = max(0, self.active.get(nid, 1) - 1)
                if tokens:
                    u = self._usage()
                    day = time.strftime("%Y-%m-%d")
                    rec = u[nid][day]
                    rec["tokens"] = int(rec.get("tokens", 0)) + int(tokens)
                    path = self._usage_path()
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(u), encoding="utf-8")
                    os.replace(tmp, path)


class MemberLimit(Exception):
    pass
