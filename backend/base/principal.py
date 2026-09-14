"""principal.py — 요청 주체(principal): 권한·회상·기록자 판정의 정본 축.

정본 설계: docs/EXTERNAL_SERVICE_APP_HANDOFF.md §3-3 · §4 (2026-09-14).

주체는 **전송 관문**이 세운다(localhost·런처 세션=owner, 외부 공개 경로=anonymous).
이후의 모든 주장(요청 본문의 device_id·principal·origin, 이웃 신뢰 원장 조회)은
**좁힐 수만 있고 넓힐 수 없다** — 넓히는 주장은 거절되고 현재 주체가 유지된다.
주체가 없거나 불일치해도 주인 권한으로 복원하지 않는다.

실행 에이전트 이름(agent_id)은 판정 축이 아니다 — body_ask 가 이웃의 부탁을
agent_id="system_ai" 로 실행하는 것이 반례.

저장은 contextvars — asyncio 태스크·anyio 스레드풀(starlette run_in_threadpool)·
execution_workers.bind_context(copy_context) 를 그대로 건넌다. thread_context.snapshot/
restore 도 이 값을 실어 손 스레드 이동(runtime_work 오프로드)까지 잇는다.

기본값(미설정) = owner: 프로세스 내부(스케줄러·자가점검·부팅 순찰)는 전송 관문이
없는 주인의 몸이다. 외부 요청은 반드시 미들웨어가 한 번 세운다.
"""
import contextvars
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

KIND_OWNER = "owner"
KIND_MEMBER = "member"      # 외부 서비스 앱 회원(limb key 인증) — 1단계에서 사용
KIND_BODY = "body"          # 이웃 몸([others:ask] 수신, body_trust 원장)
KIND_PORTAL = "portal"      # 공개 포털 회원(쿠키)
KIND_ANONYMOUS = "anonymous"

# 좁힘 순서 — 작을수록 넓다. 같은 등급 사이의 전환은 신원이 같을 때만 허용.
_RANK = {KIND_OWNER: 0, KIND_MEMBER: 1, KIND_BODY: 1, KIND_PORTAL: 1, KIND_ANONYMOUS: 2}


@dataclass(frozen=True)
class Principal:
    kind: str = KIND_OWNER
    id: str = ""              # 이웃 id 등(owner/anonymous 는 빈 문자열)
    level: Optional[int] = None
    device_id: str = ""
    extra: tuple = field(default=())   # 계측용(표시명 등) — 판정에 쓰지 않는다

    @property
    def is_owner(self) -> bool:
        return self.kind == KIND_OWNER

    def key(self) -> str:
        """캐시 키·원장 표기용 안정 문자열. 같은 사람의 다른 기기는 같은 키(기억은 사람에 붙는다)."""
        return self.kind if self.kind in (KIND_OWNER, KIND_ANONYMOUS) else f"{self.kind}:{self.id}"

    def __str__(self) -> str:
        return self.key()


OWNER = Principal()
ANONYMOUS = Principal(kind=KIND_ANONYMOUS)

_current: contextvars.ContextVar = contextvars.ContextVar("indiebiz_principal", default=None)


def current() -> Principal:
    """현재 실행 문맥의 주체. 미설정=owner(프로세스 내부)."""
    p = _current.get()
    return p if p is not None else OWNER


def is_owner() -> bool:
    return current().is_owner


def cache_key() -> str:
    return current().key()


def _can_narrow(frm: Principal, to: Principal) -> bool:
    rf, rt = _RANK.get(frm.kind, 9), _RANK.get(to.kind, 9)
    if rt < rf:
        return False               # 넓힘
    if rt == rf and frm.kind != KIND_OWNER and frm != to:
        return False               # 같은 등급의 다른 신원(body:A → body:B) — 불일치
    return True


class _Scope:
    """좁힘 범위 — with 블록을 나가면 이전 주체로 복원. 넓히는 주장은 거절하고 현재를 유지한다."""

    def __init__(self, target: Principal, source: str = ""):
        self.target = target
        self.source = source
        self.token = None
        self.applied = None

    def __enter__(self) -> Principal:
        cur = current()
        if _can_narrow(cur, self.target):
            self.applied = self.target
        else:
            logger.warning("[principal] 넓히는 주장 거절 (%s): %s → %s 유지", self.source, cur, self.target)
            self.applied = cur
        self.token = _current.set(self.applied)
        return self.applied

    def __exit__(self, *exc):
        if self.token is not None:
            _current.reset(self.token)
        return False


def narrow(target: Principal, source: str = "") -> _Scope:
    """주체 좁힘(with 문). 예: with principal.narrow(principal.body(neighbor_id, level, device_id), "nodes/ask"):"""
    return _Scope(target, source)


def authenticate(target: Principal, source: str = "") -> bool:
    """자체 인증 경로(limb key·포털 쿠키)의 관문 — 자격을 검증한 라우트가 주체를 세운다.
    기저가 owner(로컬·세션) 또는 anonymous(외부 공개 경로)일 때만 세울 수 있다. 이미 다른
    신원으로 좁혀진 문맥에서는 거절(불일치)한다. 반환 = 세워졌는가."""
    cur = current()
    if cur.is_owner or cur.kind == KIND_ANONYMOUS or cur == target:
        _current.set(target)
        return True
    logger.warning("[principal] 인증 주체 불일치 거절 (%s): %s ≠ %s", source, cur, target)
    return False


def set_transport(target: Principal):
    """전송 관문 전용 — 요청 문맥의 기저 주체를 세운다(요청마다 새 contextvars 문맥이라 누출 없음).
    관문 밖에서 부르지 말 것: 좁힘 규칙을 우회한다."""
    return _current.set(target)


def reset_transport(token) -> None:
    try:
        _current.reset(token)
    except Exception:
        pass


def transport_principal(external: bool, session_ok: bool) -> Principal:
    """전송 관문의 판정 — 로컬(localhost·Electron·프로세스 내부)=owner, 외부+세션 검증=owner,
    외부 공개 경로(세션 없음)=anonymous. 자체 인증 경로(limb key·포털 쿠키·nas)는 자기 관문에서 더 좁힌다."""
    if not external or session_ok:
        return OWNER
    return ANONYMOUS


def body(neighbor_id, level=None, device_id: str = "") -> Principal:
    return Principal(kind=KIND_BODY, id=str(neighbor_id), level=level, device_id=str(device_id or ""))


def member(neighbor_id, level=None, device_id: str = "") -> Principal:
    return Principal(kind=KIND_MEMBER, id=str(neighbor_id), level=level, device_id=str(device_id or ""))


def portal(neighbor_id=None, level=None) -> Principal:
    if neighbor_id is None or neighbor_id == "":
        return ANONYMOUS
    return Principal(kind=KIND_PORTAL, id=str(neighbor_id), level=level)


# ── 스냅샷 이음매(thread_context.snapshot/restore 가 부른다) ──────────────────

SNAPSHOT_KEY = "_principal"


def export_for_snapshot() -> Optional[Principal]:
    return _current.get()


def import_from_snapshot(value) -> None:
    _current.set(value if isinstance(value, Principal) else None)


def recall_allowed(channel: str = "") -> bool:
    """회상 공급원 공통 판정 — 주인 것(해마 용례·심층메모리·포식·결정 원장·문서)은 owner 만 읽는다.
    회원 자기 것·주인 발행분의 회상은 1단계(프로파일 축)에서 이 함수의 채널 인자로 연다."""
    return is_owner()
