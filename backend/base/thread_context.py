"""
thread_context.py - 스레드 로컬 컨텍스트 관리
IndieBiz OS Core

에이전트 ID, Task ID 등 스레드별 상태 관리
각 에이전트가 별도 스레드에서 실행되므로 스레드 로컬 변수로 컨텍스트 관리
"""

import threading
import time
from contextlib import contextmanager

# 스레드 로컬 저장소
_thread_local = threading.local()

# ============ 활성 작업 레지스트리 (조종실 '액티브 프로젝트' 계기) ============
# 모든 실행 경로가 시작 시 thread_context 세터를 부르고 finally 에서 clear_all_context()
# 를 부르는 관습을 초크포인트로 쓴다: set_user_input(프로젝트 에이전트 런) 과
# 'task_sysai_' 접두사의 set_current_task_id(시스템 AI 런)에서 등록, clear 에서 해제.
# 조종실이 GET /nodes/active-work 로 읽는다. 건강점검 런은 제외.

_active_lock = threading.Lock()
_active_work = {}  # thread ident → {project_id, agent_id, agent_name, sysai, started_at}


def _touch_active_work(sysai: bool = False):
    """현재 스레드를 활성 작업으로 등록 (런 시작 세터들이 호출)."""
    if is_health_check_mode():
        return
    with _active_lock:
        _active_work[threading.get_ident()] = {
            "project_id": getattr(_thread_local, 'project_id', None) or "",
            "agent_id": getattr(_thread_local, 'agent_id', None) or "",
            "agent_name": getattr(_thread_local, 'agent_name', None) or "",
            "sysai": sysai,
            "started_at": time.time(),
        }


def _drop_active_work():
    with _active_lock:
        _active_work.pop(threading.get_ident(), None)


def _drop_active_work_if_sysai():
    """이 스레드의 활성작업 등록이 sysai 런일 때만 해제 (clear_current_task_id 대칭 해제).

    set_current_task_id('task_sysai_…') 가 sysai=True 로 등록하므로 그 등록만 되돌린다.
    프로젝트 에이전트 런(set_user_input, sysai=False)은 clear_all_context 가 해제하니
    여기선 건드리지 않는다. 등록 레코드를 직접 봐 task_id 문자열 변화와 무관하게 정확히 해제."""
    ident = threading.get_ident()
    with _active_lock:
        w = _active_work.get(ident)
        if w and w.get("sysai"):
            _active_work.pop(ident, None)


def clear_sysai_active_work():
    """모든 sysai 활성작업 등록을 스레드 아이덴티티와 무관하게 확정 해제.

    시스템 AI 는 러너 없는 싱글턴이라 동시 sysai 런이 없다. 등록(set_current_task_id)과
    해제(clear_current_task_id)가 서로 다른 스레드에서 돌면 스레드-키 대칭이 깨져 _active_work
    에 유령이 남는다 — 조종실 '액티브 프로젝트'가 끝난 런을 최대 1시간(list_active_work 안전청소)
    까지 busy 로 오표시한다. 에피소드 END 훅(episode_logger._finalize)이 이 함수로 확정 청소해,
    어느 스레드가 런을 끝내든 대칭을 보장한다. 반환값=청소한 항목 수(진단용)."""
    with _active_lock:
        stale = [ident for ident, w in _active_work.items() if w.get("sysai")]
        for ident in stale:
            _active_work.pop(ident, None)
        return len(stale)


def clear_project_active_work(project_id: str = "", agent_name: str = "",
                              started_at_max: float = None):
    """끝난 프로젝트 런의 활성작업 등록을 스레드 아이덴티티와 무관하게 확정 해제.

    sysai 와 같은 누수: set_user_input(_touch_active_work) 등록과 clear_all_context
    (_drop_active_work) 해제가 서로 다른 스레드에서 돌면(자기반성 턴 등 thread-hop) 스레드-키
    대칭이 깨져 유령이 남아, 조종실 '액티브 프로젝트'가 창 닫은 뒤에도 busy 로 오표시된다.
    에피소드 END 훅(episode_logger._finalize)이 종료되는 에피소드의 project_id/agent_name 으로
    이 함수를 호출해 확정 청소한다.

    안전: sysai 등록은 건드리지 않는다. project_id 또는 agent_name 이 일치하는 항목만 지운다.
    started_at_max 를 주면 그 시각 이전(=이 에피소드 런 이하)에 시작된 것만 지워, 같은 프로젝트의
    *더 나중에 시작된* 동시 런은 보존한다. 반환값=청소한 항목 수(진단용)."""
    if not project_id and not agent_name:
        return 0
    with _active_lock:
        stale = []
        for ident, w in _active_work.items():
            if w.get("sysai"):
                continue
            pid_match = project_id and w.get("project_id") == project_id
            name_match = agent_name and w.get("agent_name") == agent_name
            if not (pid_match or name_match):
                continue
            if started_at_max is not None and w.get("started_at", 0) > started_at_max:
                continue
            stale.append(ident)
        for ident in stale:
            _active_work.pop(ident, None)
        return len(stale)


# System AI 대화창 존재(하트비트) — 조종실 '액티브 프로젝트'가 "창 열림=활성"을 판단.
# 프로젝트는 started AgentRunner 로 창 존재를 알지만 System AI 는 싱글턴이라 러너가 없다.
# SystemAIView 가 열려 있는 동안 주기적으로 갱신 → TTL 안이면 '창 열림'. 닫힘/크래시/백엔드
# 재시작 모두 하트비트 중단·재개로 self-healing(별도 close 신호에 의존하지 않음).
_sysai_presence = {"last_seen": 0.0}
_SYSAI_PRESENCE_TTL = 8.0


def mark_sysai_window(present: bool = True):
    """System AI 창 하트비트. present=False 는 즉시 부재 처리(닫힘 beacon)."""
    with _active_lock:
        _sysai_presence["last_seen"] = time.time() if present else 0.0


def is_sysai_window_open() -> bool:
    """마지막 하트비트가 TTL 안이면 창이 열려 있다고 본다."""
    with _active_lock:
        return (time.time() - _sysai_presence["last_seen"]) < _SYSAI_PRESENCE_TTL


# ============ 프로젝트 창 존재 (창 열림=활성) ============
# System AI 와 완전히 같은 self-healing 하트비트. 예전엔 프로젝트 칩을 '창 닫힘→Electron
# stop_all→러너 레지스트리에서 제거'로 지웠는데, 그 close 신호(fire-and-forget fetch)가
# 한 번이라도 실패하면(500/네트워크 스왈로우) 칩이 영구히 남아 재발했다. 이제 프로젝트 창도
# 열려 있는 동안 하트비트를 찍고, 닫힘/크래시/백엔드 재시작 모두 하트비트 중단으로 TTL 만료 →
# 칩 소멸. 별도 close 신호에 의존하지 않는다.
_project_presence = {}  # project_id → last_seen
_PROJECT_PRESENCE_TTL = 8.0


def mark_project_window(project_id: str, present: bool = True):
    """프로젝트 창 하트비트. present=False 는 즉시 부재 처리(닫힘 beacon)."""
    if not project_id:
        return
    with _active_lock:
        if present:
            _project_presence[project_id] = time.time()
        else:
            _project_presence.pop(project_id, None)


def open_project_windows() -> set:
    """마지막 하트비트가 TTL 안인 프로젝트 id 집합. 만료분은 청소."""
    now = time.time()
    with _active_lock:
        for pid in list(_project_presence.keys()):
            if now - _project_presence[pid] >= _PROJECT_PRESENCE_TTL:
                _project_presence.pop(pid, None)
        return set(_project_presence.keys())


def list_active_work() -> list:
    """지금 실행 중인 작업 목록. 죽은 스레드/1시간 초과 잔재(clear 누락 방어)는 청소."""
    now = time.time()
    alive = {t.ident for t in threading.enumerate()}
    out = []
    with _active_lock:
        for ident in list(_active_work.keys()):
            w = _active_work[ident]
            if ident not in alive or now - w["started_at"] > 3600:
                _active_work.pop(ident, None)
                continue
            out.append(dict(w, elapsed_sec=int(now - w["started_at"])))
    return out


# ============ 에이전트 ID 관리 ============

def set_current_agent_id(agent_id: str):
    """현재 스레드의 에이전트 ID 설정"""
    _thread_local.agent_id = agent_id


def get_current_agent_id() -> str:
    """현재 스레드의 에이전트 ID 가져오기"""
    return getattr(_thread_local, 'agent_id', None)


def set_current_project_id(project_id: str):
    """현재 스레드의 프로젝트 ID 설정"""
    _thread_local.project_id = project_id


def get_current_project_id() -> str:
    """현재 스레드의 프로젝트 ID 가져오기"""
    return getattr(_thread_local, 'project_id', None)


def set_surface_ticket(ticket):
    """표면 티켓(F51-1) — 이 스레드의 실행이 진행 상태를 남길 티켓 (2026-08-29 ⑨).

    표면(api_ibl)이 실행 전에 싣고 실행 후 복원한다. 엔진(execute_pipeline)의
    **최외곽** 파이프라인이 이 값을 읽어 step 경계마다 ticket_progress 를 쓰고,
    안쪽 실행이 겹쳐 쓰지 못하게 자기 범위에서 비운다(claim-by-clear — 값 소유권이
    곧 진행 신고권). snapshot()이 전 칸을 통째로 옮기므로 워커 스레드에도 규약이
    그대로 전파된다(빈 값 전파 = 자식은 신고하지 않음)."""
    _thread_local.surface_ticket = ticket


def get_surface_ticket():
    """현재 스레드의 표면 티켓 (없으면 None)."""
    return getattr(_thread_local, 'surface_ticket', None)


def set_progress_ticket(ticket):
    """진행 **신고** 티켓 (2026-09-01) — 좌표 소유권과 분리된 두 번째 슬롯.

    surface_ticket 은 "프로그램 좌표(step/of)를 누가 쓰는가"의 소유권이라 집는 즉시
    비운다. 그런데 옛 규약은 비우기만 해서, 소유자 **아래**의 실행(each 의 각 행·
    하위 파이프)은 살아 움직이면서도 아무 말도 못 했다 — 회수가 본 마지막 갱신 시각이
    1행 시작에서 얼어 멈춤과 느림이 구별 불가였다(09-01 실측).
    이 슬롯은 소유자가 채우고 아래 전부가 읽는다: 좌표는 못 건드리고 detail 칸만
    갱신한다(규약 정본=ibl/ibl_progress.py)."""
    _thread_local.progress_ticket = ticket


def get_progress_ticket():
    """현재 스레드의 진행 신고 티켓 (없으면 None)."""
    return getattr(_thread_local, 'progress_ticket', None)


def set_current_surface(surface: str):
    """현재 실행을 요청한 *표면* 설정 ('web' = 브라우저 표면, None = 이 기계에서 직접).

    2026-07-21 신설. 배경: 소리·저장처럼 "어디서 나야 하는가"가 갈리는 액션이
    몸 프로파일(어느 몸이 실행하는가)로 판정되고 있었다. 원격런처는 맥 백엔드가
    실행하고 폰이 보고 있으므로, 몸 기준이면 폰에서 눌러도 소리가 맥에서 난다.
    판정 축은 실행하는 몸이 아니라 *보고 있는 표면*이다 — 그 힌트를 여기 싣는다.

    'web' = 원격런처·포털·폰 네이티브 WebView (셋 다 같은 런처 셸 = 브라우저가 재생·저장 가능).
    None = 데스크탑 일렉트론 등 그 기계 자신 (맥 스피커가 곧 '여기서 재생').
    """
    _thread_local.surface = surface


def get_current_surface() -> str:
    """현재 실행을 요청한 표면 ('web' 또는 None)."""
    return getattr(_thread_local, 'surface', None)


# ============ Call Channel (action_health 출처 — 2026-08-21 ③ 조사) ============
# 이 IBL 실행을 *어느 통로가* 시작했는가. action_health.channel 로 기록돼 §1D 실사용
# 실패율을 읽을 수 있게 한다 (그동안 사용자가 겪은 실패와 배터리·앱·순찰이 한 칸에
# 섞여 품질 지표로 못 읽었다 — 08-15 selfcheck origin 분리와 같은 부류의 일반화).
# 값: 'agent'(에이전트 도구 루프 — 위임·재진입 포함) / 'app'(앱·조종실·원격·포털의
# 직접 /ibl/execute) / 'scheduler'(캘린더 파이프라인 직접 실행). 순찰·스윕은 channel 이
# 아니라 source='self_check' 가 가른다. ★스케줄러가 *위임으로* 연 에이전트 런은 도구
# 스레드가 새로 떠 'agent' 로 읽힌다(교차 스레드 전파는 task_id 유실 부류 — 미해결 명시).

def set_call_channel(channel: str, override: bool = False):
    """호출 통로 설정 — 기본 set-if-unset (바깥 이음매가 먼저 세운 값을 보존)."""
    if override or getattr(_thread_local, 'call_channel', None) is None:
        _thread_local.call_channel = channel


def get_call_channel() -> str:
    """현재 실행의 호출 통로 ('agent'/'app'/'scheduler' 또는 None=미상)."""
    return getattr(_thread_local, 'call_channel', None)


def clear_call_channel():
    _thread_local.call_channel = None


def is_web_surface() -> bool:
    """요청 표면이 브라우저인가 — 출력지(소리·저장) 판정용."""
    return get_current_surface() == 'web'


# ============ Task Origin (자기수정 헌법 2026-08-05) ============
# 이 태스크가 *사람의 직접 명령*에서 왔는가. RED(살아있는 기질) 수정 그랜트는
# origin == 'user' 일 때만 발급된다 — 스케줄러·자가점검·위임 사슬·외부 채널 등
# 자율 경로는 origin 을 안 세팅하므로(None) fail-closed.
# 세팅 지점 = 사용자 대면 transport 4곳(WS 채팅×2·/system-ai/chat·에이전트 명령 HTTP).
# 해제 = 인지 파이프라인 finally(소비 1회) + clear_all_context(백스톱) — 풀 스레드 재사용
# 으로 다음 런에 새는 것을 막는다.

def set_task_origin(origin: str):
    """현재 스레드 태스크의 출처 설정 ('user' = 사람의 직접 명령)."""
    _thread_local.task_origin = origin


def get_task_origin() -> str:
    """현재 스레드 태스크의 출처 ('user' 또는 None)."""
    return getattr(_thread_local, 'task_origin', None)


def clear_task_origin():
    """태스크 출처 해제 — 파이프라인이 소비 후 호출(풀 스레드 누수 방지)."""
    _thread_local.task_origin = None


# ── 리허설 출처 — **리허설은 삶이 아니다** (2026-08-23) ──────────────────────
# 상상 훈련은 언어의 갭을 찾으려고 *일부러* 안 되는 문장·없는 종목·빈 손을 밟는다.
# 그 의도된 실패가 실사용과 같은 칸에 쌓이면 몸이 자기 삶을 잘못 읽는다 —
# 실측(2026-08-23): 8배 회차 20분이 남긴 `table:flatten` 실패 32건이 만성 실패
# 순위 1위(37건 중 86%)를 만들었다. 사용자 알림함까지 올라갔던 B18-1 사고의 재연이다.
# 훈련 가이드 §6 은 이미 같은 판정을 내려 두었다("훈련 실측은 일부러 증류에 안 담긴다.
# 리허설은 삶이 아니다") — 그 판정이 건강 원장에는 아직 적용되지 않았을 뿐이다.
#
# ★판정을 '이름 규약'이 아니라 **행위자 봉투**로 한다: 훈련 프로브가 /ibl/execute 에
#   origin: "training" 을 실으면 actor_context 가 each·폴백·병렬 가지까지 전파한다.
#   (B18-1 이 프로세스 정체로 시험을 격리한 것과 같은 자리 — 판정은 한 벌, 표식은 기계가.)
# ★덤: origin 이 'user' 가 아니게 되므로 리허설은 RED 수정 그랜트도 못 받는다(fail-closed).
#   훈련 턴이 라이브 코어를 고쳤던 22회차 사고와 같은 방향의 보호다.
ISOLATED_ORIGINS = frozenset({"test", "training"})
REHEARSAL_ORIGINS = frozenset({"training"})


def get_isolated_origin() -> str:
    """현재 실행의 명시적 격리 출처(test/training), 아니면 None.

    pytest 프로세스 판정은 runtime_utils의 몫이다. 이 함수는 외부 HTTP 검증기처럼
    별도 프로세스가 body의 origin으로 선언한 격리만 판정한다. 원장이 origin 집합을
    각자 복제하지 않도록 행위자 봉투의 단일 판정점에 둔다.
    """
    try:
        origin = get_task_origin()
        return origin if origin in ISOLATED_ORIGINS else None
    except Exception:
        return None


def in_rehearsal() -> bool:
    """이 실행이 리허설(상상 훈련)인가 — 건강·통계 원장이 실사용과 가르는 판정."""
    return get_isolated_origin() in REHEARSAL_ORIGINS


@contextmanager
def actor_context(agent_id=None, task_id=None, origin=None):
    """진입점 계약 — 행위자 3칸(agent·task·origin)을 세우고 끝나면 이전 값으로 복원.

    쓰기 관문 원장(write_ledger)·episode 조인이 이 3칸을 읽는다. 진입점마다 세우는
    칸이 제각각이라(2026-08-21 실측: api_agents=agent+origin / api_system_ai=task+origin /
    api_ibl=task만) 같은 구멍이 재발하던 것을 계약 하나로 모은다 — 새 진입점은 개별
    세터 대신 이것을 부를 것.

    None 인 칸은 건드리지 않는다(모르는 값을 빈 값으로 덮지 않음 — 부분 복원이 부모
    컨텍스트를 지우는 사고 방지). 복원은 set 과 대칭: task 는 clear_current_task_id 로
    task_sysai_ 활성작업 등록까지 해제(api_ibl 의 기존 수동 복원과 동일 규약)."""
    prev_agent = get_current_agent_id()
    prev_task = get_current_task_id()
    prev_origin = get_task_origin()
    if agent_id is not None:
        set_current_agent_id(agent_id)
    if task_id is not None:
        set_current_task_id(task_id)
    if origin is not None:
        set_task_origin(origin)
    try:
        yield
    finally:
        if agent_id is not None:
            set_current_agent_id(prev_agent)
        if task_id is not None:
            if prev_task:
                set_current_task_id(prev_task)
            else:
                clear_current_task_id()
        if origin is not None:
            if prev_origin:
                set_task_origin(prev_origin)
            else:
                clear_task_origin()


def get_current_registry_key() -> str:
    """현재 스레드의 레지스트리 키 가져오기 (project_id:agent_id 형식)"""
    project_id = get_current_project_id()
    agent_id = get_current_agent_id()
    if not agent_id:
        return None
    return f"{project_id}:{agent_id}" if project_id else agent_id


def get_current_agent_name() -> str:
    """현재 스레드의 에이전트 이름 가져오기"""
    return getattr(_thread_local, 'agent_name', None)


def set_current_agent_name(name: str):
    """현재 스레드의 에이전트 이름 설정"""
    _thread_local.agent_name = name


# ============ Task ID 관리 ============

def set_current_task_id(task_id: str):
    """현재 스레드의 task_id 설정 (시스템 자동 관리)"""
    _thread_local.task_id = task_id
    # 시스템 AI 런은 set_user_input 을 안 거치므로 task 접두사로 활성 작업 등록
    if task_id and str(task_id).startswith('task_sysai_'):
        _touch_active_work(sysai=True)


def get_current_task_id() -> str:
    """현재 스레드의 task_id 가져오기"""
    return getattr(_thread_local, 'task_id', None)


def clear_current_task_id():
    """현재 스레드의 task_id 초기화 + sysai 활성작업 등록 해제(대칭).

    set_current_task_id 가 task_sysai_ 런을 _active_work 에 등록하므로, 이 스레드의 sysai
    등록을 여기서 해제한다. 안 그러면 시스템 AI 응답이 끝나도 조종실 '액티브 프로젝트'에
    최대 1시간(list_active_work 안전청소)까지 유령으로 남는다 — HTTP/러너/폴러 sysai 경로가
    clear_all_context 대신 이 함수를 finally 에서 쓰기 때문(WebSocket 경로만 clear_all_context)."""
    _thread_local.task_id = None
    _drop_active_work_if_sysai()


# ============ call_agent 호출 추적 ============

def set_called_agent(called: bool = True):
    """
    현재 스레드에서 call_agent가 호출되었음을 표시

    이 플래그는 자동 보고 로직에서 사용됨:
    - True: AI가 다른 에이전트에게 작업을 위임함 → 자동 보고 스킵 (위임받은 에이전트가 보고할 것)
    - False: AI가 직접 작업 완료 → 자동 보고 실행
    """
    _thread_local.called_agent = called


def did_call_agent() -> bool:
    """현재 스레드에서 call_agent가 호출되었는지 확인"""
    return getattr(_thread_local, 'called_agent', False)


def clear_called_agent():
    """call_agent 호출 플래그 초기화"""
    _thread_local.called_agent = False


# ============ Health Check 컨텍스트 ============

def set_health_check_mode(enabled: bool = True):
    """현재 스레드가 건강 체크 모드임을 표시

    SystemAI 가 건강 점검 맥락(from_agent=__health_check__)에서 실행될 때,
    IBL 액션 결과를 source=self_check 으로 기록하기 위한 플래그.
    (현 일일 건강 점검 run_daily_health_check 은 SystemAI 를 거치지 않아 이 플래그를
    켜지 않는다 — 향후 AI triage 가 다시 필요해질 때를 위한 무해한 배관으로 남겨둠.)
    """
    _thread_local.health_check_mode = enabled


def is_health_check_mode() -> bool:
    """현재 스레드가 건강 체크 모드인지 확인"""
    return getattr(_thread_local, 'health_check_mode', False)


# ============ User Input 추적 (IBL 용례 학습용) ============

def set_user_input(text: str):
    """현재 스레드의 사용자 원본 입력 저장 (IBL 실행 로그에 사용)"""
    _thread_local.user_input = text
    # 런 시작 신호 — 이 시점엔 project_id/agent_name 이 이미 세팅돼 있다(호출 관습)
    if text:
        _touch_active_work()


def get_user_input() -> str:
    """현재 스레드의 사용자 원본 입력 가져오기"""
    return getattr(_thread_local, 'user_input', '')


# ============ 도구 호출 이력 (경험 증류용) ============

def append_tool_call(tool_name: str, tool_input: dict, success: bool = True,
                     node: str = "", action: str = "", duration_ms: int = 0):
    """현재 스레드의 도구 호출 이력에 추가"""
    if not hasattr(_thread_local, 'tool_calls'):
        _thread_local.tool_calls = []
    _thread_local.tool_calls.append({
        "tool_name": tool_name,
        "input": tool_input,
        "success": success,
        "node": node,
        "action": action,
        "ms": duration_ms,
    })


def get_tool_calls() -> list:
    """현재 스레드의 도구 호출 이력 반환"""
    return getattr(_thread_local, 'tool_calls', [])


def clear_tool_calls():
    """현재 스레드의 도구 호출 이력 초기화"""
    _thread_local.tool_calls = []


# ============ Goal 평가 결과 (증류 게이트용) ============
# 목표 평가 루프의 최종 판정을 증류 단계로 전달한다. 평가가 NOT_ACHIEVED로
# 끝난(=목표 미달성) 실행의 IBL 패턴을 해마에 학습하면 실패가 코퍼스에 누적되어
# 시간이 갈수록 추천 품질을 깎는다(복리 출혈). 증류 전에 이 판정을 보고 거른다.
# None = 평가 안 함(EXECUTE/Reflex 등) → 증류 허용(기존 동작).

def set_goal_eval_outcome(achieved: bool, severity: int = 0):
    """현재 스레드의 목표 평가 최종 판정 저장."""
    _thread_local.goal_eval_outcome = {"achieved": bool(achieved), "severity": int(severity)}


def get_goal_eval_outcome():
    """현재 스레드의 목표 평가 판정 반환. 평가가 없었으면 None."""
    return getattr(_thread_local, 'goal_eval_outcome', None)


def clear_goal_eval_outcome():
    """현재 스레드의 목표 평가 판정 초기화."""
    _thread_local.goal_eval_outcome = None


# ============ 관용구 회상 (해마 phrase 채널, 2026-09-04) ============
# build_execution_memory 가 이 턴에 올린 관용구 코드들을 두고, 턴 끝의 증류(이미 아는 관용구면
# 다시 뽑지 않음)·귀속(실행 궤적에 순서대로 절반 이상 등장했으면 성공/실패 기록)이 읽는다.
# 반환 튜플(xml, top_score, top_code)을 바꾸지 않으려고 스레드-로컬로 나른다 — goal_eval_outcome 과 같은 결.

def set_phrase_recall(codes):
    _thread_local.phrase_recall = [c for c in (codes or []) if isinstance(c, str) and c.strip()]


def get_phrase_recall():
    return list(getattr(_thread_local, 'phrase_recall', None) or [])


def clear_phrase_recall():
    _thread_local.phrase_recall = []


# ============ Allowed Nodes (IBL Node Access Control) ============

def set_allowed_nodes(allowed):
    """현재 스레드의 allowed_nodes 설정 (ibl_only 모드용)"""
    _thread_local.allowed_nodes = allowed


def get_allowed_nodes():
    """현재 스레드의 allowed_nodes 가져오기. None이면 제한 없음."""
    return getattr(_thread_local, 'allowed_nodes', None)


def snapshot() -> dict:
    """현재 스레드의 thread-local 컨텍스트 스냅샷.

    IBL 핸들러를 워커 스레드로 오프로드할 때(async 안전), agent_id/allowed_nodes/
    task_id 등 컨텍스트를 워커 스레드로 전파하기 위해 사용한다.
    threading.local은 스레드 간 자동 전파가 안 되므로 명시적으로 떠서 옮긴다.

    ★궤적 손잡이(contextvars)도 함께 뜬다 — threading.local 만 나르면 워커에서
    실행되는 핸들러의 쓰기(write_ledger)·사건(record_trajectory_event)이 부모 run 을
    못 보고 고아가 된다(2026-08-29 실측). 이 이음매를 지나는 모든 스레드 이동
    (핸들러 타임아웃 스레드·오프로드풀·병렬 분기)이 이 한 벌로 척추를 잇는다.
    """
    snap = dict(_thread_local.__dict__)
    try:
        from episode_logger import capture_trace
        snap["_trajectory_trace"] = capture_trace()
    except Exception:
        pass
    return snap


def restore(snap: dict):
    """snapshot()으로 떠둔 컨텍스트를 현재 스레드의 thread-local에 복원."""
    snap = dict(snap or {})
    trace = snap.pop("_trajectory_trace", None)
    try:
        from episode_logger import adopt_trace
        adopt_trace(trace)   # None 포함 set — 풀 스레드 재사용의 잔류 trace 청소
    except Exception:
        pass
    # 복원은 *상태 전체*의 복원이다 — 스냅샷 이후 새로 생긴 키(예: 시험이 세운
    # agent_id·task_id, 풀 스레드에 남은 잔류)를 지우지 않으면 "restore 했는데 새 키가
    # 그대로"가 되어 다음 사용자에게 샌다(test_repair_root_doctrine D5 → 뒤 시험의
    # registry_key 오염 실측). snap 에 없는 키는 걷어낸다.
    for k in list(_thread_local.__dict__.keys()):
        if k not in snap:
            delattr(_thread_local, k)
    for k, v in snap.items():
        setattr(_thread_local, k, v)


# ============ 컨텍스트 일괄 관리 ============

def clear_all_context():
    """모든 스레드 로컬 컨텍스트 초기화"""
    _drop_active_work()
    _thread_local.agent_id = None
    _thread_local.agent_name = None
    _thread_local.project_id = None
    _thread_local.surface = None
    _thread_local.task_origin = None
    _thread_local.task_id = None
    _thread_local.called_agent = False
    _thread_local.allowed_nodes = None
    _thread_local.user_input = ''
    _thread_local.tool_calls = []
    _thread_local.health_check_mode = False
    _thread_local.call_channel = None
    _thread_local.surface_ticket = None
    _thread_local.progress_ticket = None


def get_context_summary() -> dict:
    """현재 컨텍스트 요약 (디버깅용)"""
    return {
        "agent_id": get_current_agent_id(),
        "agent_name": get_current_agent_name(),
        "project_id": get_current_project_id(),
        "registry_key": get_current_registry_key(),
        "task_id": get_current_task_id(),
        "called_agent": did_call_agent(),
        "allowed_nodes": get_allowed_nodes(),
        "user_input": get_user_input()
    }
