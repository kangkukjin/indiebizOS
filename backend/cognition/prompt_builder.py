"""
prompt_builder.py - 시스템 프롬프트 빌더
IndieBiz OS Core

기본 프롬프트 + 조건부 프롬프트(git, delegation)를 조합합니다.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional


# 프롬프트 파일 경로
from runtime_utils import get_base_path
PROMPTS_PATH = get_base_path() / "data" / "common_prompts"

logger = logging.getLogger(__name__)

# 싱글톤 인스턴스
_prompt_builder_instance: Optional['PromptBuilder'] = None


def get_prompt_builder() -> 'PromptBuilder':
    """싱글톤 PromptBuilder 인스턴스 반환"""
    global _prompt_builder_instance
    if _prompt_builder_instance is None:
        _prompt_builder_instance = PromptBuilder()
    return _prompt_builder_instance


# system_structure.md '정체성 코어' 캐시 (mtime 기반 무효화)
_SYS_STRUCT_CORE_CACHE: Dict[str, object] = {"mtime": None, "core": None}


def get_system_structure_core() -> str:
    """system_structure.md 의 '정체성 코어'를 반환한다.

    CODEBASE_MAP 마커 구간(백엔드/프론트 디렉토리·파일 트리 — 자기개발·디버깅에서만 쓰는
    *소스 지식*)은 제거하고 한 줄 포인터로 대체한다. 동시에 그 구간을
    guides/codebase_map.md 로 파생한다(system_structure.md 가 더 새로우면 갱신).

    ★단일 소스는 system_structure.md 다 — 사용자는 그 한 파일만 편집하면 되고,
      codebase_map.md 는 여기서 자동 파생된다.
    실행·의식·평가 세 에이전트가 모두 이 함수를 써서 일관되게 코어만 주입한다.
    """
    base = get_base_path()
    doc_path = base / "data" / "system_docs" / "system_structure.md"
    if not doc_path.exists():
        return ""
    mtime = doc_path.stat().st_mtime
    if _SYS_STRUCT_CORE_CACHE["mtime"] == mtime and _SYS_STRUCT_CORE_CACHE["core"] is not None:
        return _SYS_STRUCT_CORE_CACHE["core"]  # type: ignore

    raw = doc_path.read_text(encoding="utf-8")
    START, END = "<!-- CODEBASE_MAP:START -->", "<!-- CODEBASE_MAP:END -->"
    pointer = (
        "> **코드베이스 구조**(백엔드/프론트엔드 디렉토리·파일 위치)는 자기개발·디버깅 작업에서만 "
        "필요하므로 항상 주입하지 않는다. 필요하면 `read_guide(query=\"코드 구조\")` 로 `codebase_map` "
        "가이드를 읽어라 — 의식 에이전트는 자기개발/디버깅 태스크에서 이 가이드를 자동 선택한다."
    )

    if START in raw and END in raw:
        pre, rest = raw.split(START, 1)
        block, post = rest.split(END, 1)
        # 파생 가이드 갱신 (stale 시에만 — 단일 소스 = system_structure.md)
        try:
            guide_path = base / "data" / "guides" / "codebase_map.md"
            if (not guide_path.exists()) or (guide_path.stat().st_mtime < mtime):
                header = (
                    "# 코드베이스 구조 (codebase_map)\n\n"
                    "> 자동 생성 — 직접 편집하지 마라. 원본은 "
                    "`data/system_docs/system_structure.md` 의 CODEBASE_MAP 구간이다. "
                    "거기서 고치면 다음 로드 때 이 파일이 갱신된다.\n\n"
                )
                guide_path.write_text(header + block.strip() + "\n", encoding="utf-8")
        except Exception as e:
            logger.warning(f"[codebase_map] 파생 실패: {e}")
        core = pre.rstrip() + "\n\n" + pointer + "\n" + post
    else:
        core = raw

    _SYS_STRUCT_CORE_CACHE["mtime"] = mtime
    _SYS_STRUCT_CORE_CACHE["core"] = core
    return core


class PromptBuilder:
    """시스템 프롬프트 빌더

    base_prompt_v6.md (항상 포함) + 조건부 프롬프트를 조합합니다.

    사용 예시:
        builder = PromptBuilder()
        prompt = builder.build(agent_count=3, git_enabled=True)
    """

    def __init__(self, prompts_path: Path = None):
        self.prompts_path = prompts_path or PROMPTS_PATH
        self._cache: Dict[str, str] = {}
        self._cache_mtime: Dict[str, float] = {}

    # --- 캐시 무효화 (mtime) ---------------------------------------------
    # ★캐시 주인은 get_prompt_builder() 의 전역 싱글턴이라 캐시 수명 = 프로세스 수명이다.
    #   mtime 검사가 없으면 프롬프트·가이드·시스템문서를 고쳐도 백엔드 재기동 전까지
    #   그 프로세스의 모든 턴에 옛 본문이 주입된다. 특히 가이드는 에이전트가 매 턴
    #   실측 교훈을 적어 넣는 *절차 기억*이라 되먹임 루프(guide_feedback)가 통째로
    #   무효가 된다 — 헤더의 freshness_note 는 매 턴 새로 읽어 '최종수정'만 신선해
    #   보이므로 증상이 조용하다. get_system_structure_core() 의 무효화와 같은 규약.

    @staticmethod
    def _file_mtime(path: Path) -> Optional[float]:
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    def _cache_valid(self, cache_key: str, path: Path) -> bool:
        """캐시가 있고 그 뒤 파일이 안 바뀌었으면 True."""
        if cache_key not in self._cache:
            return False
        mtime = self._file_mtime(path)
        return mtime is not None and self._cache_mtime.get(cache_key) == mtime

    def _stamp(self, cache_key: str, path: Path) -> None:
        mtime = self._file_mtime(path)
        if mtime is None:
            self._cache_mtime.pop(cache_key, None)
        else:
            self._cache_mtime[cache_key] = mtime

    def _read_cached(self, cache_key: str, path: Path) -> str:
        """파일을 캐시해 읽되, mtime 이 바뀌었으면 다시 읽는다."""
        if not path.exists():
            self._cache.pop(cache_key, None)
            self._cache_mtime.pop(cache_key, None)
            return ""
        if self._cache_valid(cache_key, path):
            return self._cache[cache_key]
        content = path.read_text(encoding='utf-8')
        self._cache[cache_key] = content
        self._stamp(cache_key, path)
        return content

    def _load_file(self, filename: str) -> str:
        """프롬프트 파일 로드 (캐시 사용 — mtime 무효화)"""
        return self._read_cached(filename, self.prompts_path / filename)

    def _load_system_doc(self, filename: str) -> str:
        """data/system_docs/ 폴더에서 시스템 문서 로드 (캐시 사용 — mtime 무효화)"""
        return self._read_cached(
            f"__sysdoc__{filename}",
            get_base_path() / "data" / "system_docs" / filename,
        )

    def _load_guide_file(self, guide_filename: str) -> str:
        """data/guides/ 폴더에서 가이드 파일 로드 (캐시 사용 — mtime 무효화)"""
        return self._read_cached(
            f"__guide__{guide_filename}",
            get_base_path() / "data" / "guides" / guide_filename,
        )

    def _guide_block(self, guide_filename: str, origin: str = "agent") -> str:
        """주입할 가이드 블록 = 제목 + **신선도 표식** + 본문. 없으면 빈 문자열.

        가이드는 절차 기억이라 낡는다. 나이만으로는 못 정하므로(오래됐어도 그 뒤
        무수정으로 여러 번 쓰였으면 오히려 검증된 것) 최종수정일과 *그 이후의
        무수정 사용*을 함께 붙여 읽는 쪽이 감안하게 한다. 상세: guide_registry.

        표식은 실패해도 본문 주입을 막지 않는다(신선도는 부가 정보지 전제가 아니다).
        """
        content = self._load_guide_file(guide_filename)
        if not content:
            return ""
        note = ""
        try:
            from guide_registry import freshness_note, record_use, mark_injected
            note = freshness_note(guide_filename)
            record_use(guide_filename, origin)
            mark_injected(guide_filename)   # 턴 종료 후 증류 4단계가 회수해 되돌려 쓴다
        except Exception as e:
            logger.debug(f"[prompt_builder] 가이드 신선도 생략 (무시): {e}")
        head = f"# 가이드: {guide_filename}"
        return f"{head}\n{note}\n{content}" if note else f"{head}\n{content}"

    def _load_world_pulse(self) -> str:
        """World Pulse 로드 — 오늘의 세계 상태 요약

        data/guides/world_pulse.md가 존재하면 내용을 반환합니다.
        대화 시작 시 1회 주입되어 에이전트가 세계 맥락을 알고 시작합니다.
        파일이 없거나 비어있으면 빈 문자열을 반환합니다.

        주의: 캐시하지 않음 — 백그라운드 수집 완료 후 파일이 갱신될 수 있으므로
        매번 디스크에서 읽습니다. (대화 시작 시 1회만 호출되어 성능 영향 없음)
        """
        pulse_path = get_base_path() / "data" / "guides" / "world_pulse.md"
        content = ""
        if pulse_path.exists():
            try:
                content = pulse_path.read_text(encoding='utf-8').strip()
            except Exception as e:
                logger.warning(f"[PromptBuilder] World Pulse 로드 실패: {e}")
                content = ""

        # 이웃 몸 명함 냄새(실험 3) — 캐시된 peer 명함 요약을 세계 인식 옆에 부착.
        # 캐시 없으면 ""(비용 0). 사전이 아니라 냄새 — "저 몸에 부탁할 수 있다"의 인지.
        try:
            from peer_cards import scent_text
            _scent = scent_text()
        except Exception:
            _scent = ""

        if content:
            logger.info(f"[PromptBuilder] World Pulse 주입: ~{len(content)}자")
            return content + (f"\n\n{_scent}" if _scent else "")

        # 폴백(폰-자아 호스팅 §6.7): world_pulse.md 가 아직 없는 몸(예: 펄스 수집이 안 도는 폰)
        # 에서도 *정체성*만은 반드시 주입한다 — "나는 어느 몸인가"를 모르면 자기-모델이 깨진다
        # (집밖 폰이 자기를 맥이라 오인하는 위험). capability portrait 는 body-neutral(detect_body).
        try:
            from runtime_utils import build_capability_portrait
            cap = build_capability_portrait()
            if cap and cap.get("body"):
                lines = ["# 나는 누구인가 (자동 주입)",
                         f"- 나는 지금 **{cap['body']}** 에서 돈다."]
                if cap.get("identity"):
                    lines.append(f"- {cap['identity']}")
                micros = cap.get("micros") or {}
                esc = micros.get("escape")
                if esc == "python":
                    lines.append("- 내 만능 실행 탈출구 = **python**(인-프로세스). 고정 IBL 너머는 execute_python 으로 "
                                 "직접 — 약한 셸도 subprocess 로 포섭, `from java import jclass` 로 안드로이드 SDK 도달.")
                elif esc == "shell":
                    lines.append("- 내 만능 실행 탈출구 = **shell**(run_command). 셸로 python·node 등을 띄워 직접 해결.")
                if micros.get("local"):
                    lines.append(f"- 직접 할 수 있는 원시: {', '.join(micros['local'])}.")
                if micros.get("borrowed"):
                    lines.append(f"- 빌려야 하는 원시(필요 시 맥 위임): {', '.join(micros['borrowed'])}.")
                if cap.get("has_peer"):
                    lines.append(f"- 못 하는 일은 {cap.get('peer_name','상대 노드')}의 액션을 빌릴 수 있다(분산 IBL 자동 위임).")
                logger.info("[PromptBuilder] World Pulse 부재 → 정체성+마이크로 폴백 주입")
                return "\n".join(lines) + (f"\n\n{_scent}" if _scent else "")
        except Exception as e:
            logger.debug(f"[PromptBuilder] 정체성 폴백 실패: {e}")
        return ""

    def _build_resource_list(self) -> str:
        """자원 목록 생성 — guide_db.json에서 가이드 제목을 읽어 한 줄 목록으로 반환

        에이전트가 '어떤 가이드가 존재하는지' 배경 지식으로 기억하게 하여,
        능동적 검색(read_guide) 없이도 관련 가이드를 떠올릴 수 있게 합니다.
        """
        cache_key = "__resource_list__"
        if cache_key in self._cache:
            return self._cache[cache_key]

        guide_db_path = get_base_path() / "data" / "guide_db.json"
        if not guide_db_path.exists():
            return ""

        try:
            data = json.loads(guide_db_path.read_text(encoding='utf-8'))
            guides = data.get("guides", [])
            if not guides:
                return ""

            names = [g["name"] for g in guides if g.get("name")]
            if not names:
                return ""

            resource_text = "# 자원 목록\n참고 가능한 가이드: " + " / ".join(names)
            self._cache[cache_key] = resource_text
            logger.debug(f"[PromptBuilder] 자원 목록 생성: {len(names)}개 가이드, ~{len(resource_text)}자")
            return resource_text
        except Exception as e:
            logger.warning(f"[PromptBuilder] 자원 목록 생성 실패: {e}")
            return ""

    def build(self,
              agent_count: int = 1,
              git_enabled: bool = False,
              delegated_from_system_ai: bool = False,
              ibl_only: bool = False,
              allowed_nodes: list = None,
              project_path: str = None,
              agent_id: str = None,
              role_prompt: str = "",
              additional_context: str = "",
              consciousness_output: dict = None,
              model_name: str = "",
              execution_memory: str = "",
              skip_dynamic: bool = False) -> str:
        """시스템 프롬프트 조합

        Args:
            agent_count: 프로젝트 내 에이전트 수 (2 이상이면 위임 프롬프트 포함)
            git_enabled: Git 관련 프롬프트 포함 여부
            delegated_from_system_ai: 시스템 AI로부터 위임받은 경우 (파일 경로 원칙 포함)
            ibl_only: IBL 전용 모드 (execute_ibl만 사용)
            allowed_nodes: IBL 노드 접근 제어
            project_path: 프로젝트 경로 (동료 에이전트 탐색용)
            agent_id: 현재 에이전트 ID (환경에서 자신 제외용)
            role_prompt: 에이전트 역할 프롬프트
            additional_context: 추가 컨텍스트 (프로젝트 설정 등)
            consciousness_output: 의식 에이전트 출력 (태스크 프레이밍, IBL 포커싱 등)
            execution_memory: 실행기억 (IBL 코드 사례 + 추천 도구 + implementation)

        Returns:
            조합된 시스템 프롬프트 문자열
        """
        parts = []

        # 0. 현재 날짜 (모든 에이전트가 현재 시점을 알도록)
        # ★ 날짜만 — 분 단위 시각을 stable 프롬프트(캐시 prefix 맨 앞)에 넣으면
        #   prefix 매칭이라 매분 ~60K 전체 캐시가 무효화된다. 정밀 시각은
        #   _build_dynamic_context(비캐시 — user message 앞)로 옮기고, 그래도
        #   부족하면 에이전트가 [self:time] 도구로 초 단위까지 얻는다.
        from datetime import datetime
        now = datetime.now()
        # ★ 로케일 비의존 조립: strftime 포맷에 한글 리터럴(년/월/일)이나 %A(로케일
        #   요일명)를 넣으면 윈도우 임베디드 Python(로케일 Korean_Korea + 코드페이지
        #   1252 불일치)에서 인코딩이 UnicodeEncodeError로 터져 부팅이 죽는다.
        #   맥 번들 Python은 UTF-8 로케일이라 재현 안 됨 → 코드가 같아도 윈도우만 깨짐.
        #   숫자 필드 + 한글 요일 테이블로 직접 조립(출력 동일: 2026년 07월 05일 일요일).
        _weekday_ko = ('월', '화', '수', '목', '금', '토', '일')[now.weekday()]
        date_info = f"# 현재 시점\n현재 날짜: {now.year}년 {now.month:02d}월 {now.day:02d}일 {_weekday_ko}요일"
        parts.append(date_info)

        # 1. 기본 프롬프트 (항상 포함)
        base = self._load_file("base_prompt_v6.md")
        if base:
            parts.append(base)

        # 1.5. 시스템 구조 문서 (정체성 코어만 항상 포함 — 디렉토리/파일 트리는
        #      codebase_map 가이드로 분리되어 자기개발/디버깅 시에만 주입된다)
        sys_structure = get_system_structure_core()
        if sys_structure:
            parts.append(f"<system_structure>\n{sys_structure}\n</system_structure>")

        # 2. Git 프롬프트 (조건부)
        if git_enabled:
            git = self._load_file("fragments/06_git.md")
            if git:
                parts.append(git)

        # 3. 위임 프롬프트 (에이전트가 2개 이상이거나 시스템 AI가 위임한 경우)
        if agent_count > 1 or delegated_from_system_ai:
            delegation = self._load_file("fragments/09_delegation.md")
            if delegation:
                parts.append(delegation)

        # 4. IBL 환경 프롬프트 (Phase 16: 단일 경로)
        if ibl_only:
            from ibl_access import build_environment
            ibl = build_environment(allowed_nodes, project_path, agent_id)
            if ibl:
                parts.append(ibl)

        # 4.1 실행기억 (IBL 코드 사례 + 추천 도구 + implementation)
        # skip_dynamic=True면 가변 부분은 외부에서 _build_dynamic_context로 처리
        if execution_memory and not skip_dynamic:
            parts.append(execution_memory)

        # 4.3 의식 에이전트 출력 — IBL 포커싱 힌트 + 태스크 프레이밍
        if consciousness_output and not skip_dynamic:
            consciousness_parts = []

            # 태스크 프레이밍 (지금 풀어야 할 문제 정의)
            task_framing = consciousness_output.get("task_framing", "")
            if task_framing:
                consciousness_parts.append(f"# 현재 태스크\n{task_framing}")

            # 달성 기준 (실행 에이전트가 목표를 알고 행동하도록)
            achievement_criteria = consciousness_output.get("achievement_criteria", "")
            if achievement_criteria:
                consciousness_parts.append(f"# 달성해야 할 목표의 기준\n{achievement_criteria}\n\n이 기준을 모두 충족하도록 응답을 구성하라. 응답 완성 전에 각 항목을 스스로 점검하라.")

            # NOTE: history_summary는 messages 파라미터에서 원본 히스토리를 대체하므로 여기엔 넣지 않음

            # IBL 포커싱 힌트 (제한이 아닌 초점 설정)
            # 키는 capability_focus (consciousness_prompt.md); ibl_focus는 구 이름 폴백.
            ibl_focus = consciousness_output.get("capability_focus") or consciousness_output.get("ibl_focus") or {}
            if ibl_focus:
                focus_parts = []
                primary = ibl_focus.get("primary_nodes", [])
                highlight = ibl_focus.get("highlight_actions", [])
                hint = ibl_focus.get("hint", "")
                if primary:
                    focus_parts.append(f"주요 노드: {', '.join(primary)}")
                if highlight:
                    focus_parts.append(f"주목할 액션: {', '.join(highlight)}")
                if hint:
                    focus_parts.append(f"접근 방향: {hint}")
                if focus_parts:
                    consciousness_parts.append(
                        "<focus note=\"참고용 힌트 — 다른 액션도 자유롭게 사용 가능\">\n"
                        + "\n".join(focus_parts)
                        + "\n</focus>"
                    )

            # context_notes 출력 필드도 폐지 (2026-06-28 self_awareness/world_state와 함께).
            # 프롬프트 응답 형식에 없어 항상 빈 값이었다 → 죽은 읽기 제거(2026-07-06 스키마 감사).
            # 맥락은 task_framing으로 흡수한다.

            # self_awareness·world_state 출력 필드 폐지 (2026-06-28). 의식은 task_framing
            # 으로 문제를 규정하고 self/world 맥락을 그 안에 녹인다. 모델명만 남긴다.
            if model_name:
                consciousness_parts.append(f"# 자기 인식\n- AI 모델: {model_name}")

            if consciousness_parts:
                parts.append("\n".join(consciousness_parts))

            # 의식 에이전트가 지정한 가이드 파일 로드 & 주입
            guide_files = consciousness_output.get("guide_files", [])
            for guide in guide_files:
                block = self._guide_block(guide)
                if block:
                    parts.append(block)

        # 4.5 자원 목록 (가이드 제목 배경 지식)
        resource_list = self._build_resource_list()
        if resource_list:
            parts.append(resource_list)

        # 4.6 World Pulse 직접 주입 폐지 (2026-06-28) — self/world 스냅샷은 이제 의식
        # 에이전트 입력으로만 흐르고 task_framing 으로 녹여 전달된다. 실행 에이전트
        # (EXECUTE/Reflex)는 ambient 주입 없이, 필요 시 sense:here/host/world 로 pull.
        if not consciousness_output:
            if model_name:
                parts.append(f"# 자기 인식\n- AI 모델: {model_name}")

        # 5. 역할 프롬프트
        if role_prompt:
            parts.append(f"\n# Role\n{role_prompt}")

        # 6. 추가 컨텍스트
        if additional_context:
            parts.append(f"\n{additional_context}")

        return "\n\n".join(parts)

    def estimate_tokens(self, prompt: str) -> int:
        """프롬프트 토큰 수 추정 (대략 4자당 1토큰)"""
        return len(prompt) // 4

    def clear_cache(self):
        """파일 캐시 초기화"""
        self._cache.clear()


# 편의 함수들

def build_agent_prompt_split(
    agent_name: str,
    role: str = "",
    agent_count: int = 1,
    agent_notes: str = "",
    git_enabled: bool = False,
    delegated_from_system_ai: bool = False,
    ibl_only: bool = True,
    allowed_nodes: list = None,
    project_path: str = None,
    agent_id: str = None,
    consciousness_output: dict = None,
    model_name: str = "",
    execution_memory: str = "",
    **kwargs
) -> tuple:
    """프로젝트 에이전트 프롬프트를 (안정, 가변)로 분리해 반환.

    안정 부분은 system_prompt로 넘기고, 가변 부분은 user message 앞에 prepend한다.
    Anthropic 프롬프트 캐시 prefix가 매 호출마다 동일해져 캐시 hit이 일어난다.

    Returns:
        (stable_prompt, dynamic_context)
    """
    builder = get_prompt_builder()

    role_parts = [f"당신은 '{agent_name}'입니다."]
    if role:
        role_parts.append(role)
    role_prompt = "\n".join(role_parts)

    additional_context = ""
    if agent_notes:
        additional_context = f"# Notes\n{agent_notes}"

    # 안정 부분 — skip_dynamic=True로 가변 항목 제외
    stable = builder.build(
        agent_count=agent_count,
        git_enabled=git_enabled,
        delegated_from_system_ai=delegated_from_system_ai,
        ibl_only=ibl_only,
        allowed_nodes=allowed_nodes,
        project_path=project_path,
        agent_id=agent_id,
        role_prompt=role_prompt,
        additional_context=additional_context,
        consciousness_output=consciousness_output,  # 4.6 분기 판단용
        model_name=model_name,
        execution_memory=execution_memory,
        skip_dynamic=True,
    )
    dynamic = _build_dynamic_context(consciousness_output, model_name, execution_memory)
    return stable, dynamic


def build_agent_prompt(
    agent_name: str,
    role: str = "",
    agent_count: int = 1,
    agent_notes: str = "",
    git_enabled: bool = False,
    delegated_from_system_ai: bool = False,
    ibl_only: bool = True,
    allowed_nodes: list = None,
    project_path: str = None,
    agent_id: str = None,
    consciousness_output: dict = None,
    model_name: str = "",
    execution_memory: str = "",
    **kwargs  # ibl_enabled 등 하위 호환 파라미터 무시
) -> str:
    """프로젝트 에이전트용 시스템 프롬프트 — 안정+가변을 합친 단일 문자열 (호환용).

    새 호출자는 build_agent_prompt_split을 직접 사용해 캐시 효율을 얻는다.
    """
    stable, dynamic = build_agent_prompt_split(
        agent_name=agent_name,
        role=role,
        agent_count=agent_count,
        agent_notes=agent_notes,
        git_enabled=git_enabled,
        delegated_from_system_ai=delegated_from_system_ai,
        ibl_only=ibl_only,
        allowed_nodes=allowed_nodes,
        project_path=project_path,
        agent_id=agent_id,
        consciousness_output=consciousness_output,
        model_name=model_name,
        execution_memory=execution_memory,
        **kwargs,
    )
    if dynamic:
        return f"{stable}\n\n{dynamic}"
    return stable


def _build_system_ai_stable_prompt(
    user_profile: str = "",
    git_enabled: bool = False,
    extra_role: str = "",
    allowed_set=None,
) -> str:
    """시스템 AI 안정 프롬프트 — 매 호출마다 동일한 부분만.

    Anthropic 프롬프트 캐시는 prefix matching이므로 매번 같아야 hit한다.
    가변 부분(execution_memory, consciousness_output)은 build_system_ai_prompt_split에서
    별도로 반환되어 user message 앞에 prepend된다.
    """
    role_path = get_base_path() / "data" / "system_ai_role.txt"
    role = role_path.read_text(encoding='utf-8') if role_path.exists() else ""

    builder = get_prompt_builder()

    prompt = builder.build(
        agent_count=1,
        git_enabled=git_enabled
    )
    parts = [prompt]

    from ibl_access import build_environment
    # allowed_set 이 오면 그 노드 집합만(포식=sense+self). None이면 전체.
    ibl_env = build_environment(allowed_nodes=None, allowed_set=allowed_set)
    if ibl_env:
        parts.append(ibl_env)

    resource_list = builder._build_resource_list()
    if resource_list:
        parts.append(resource_list)

    delegation_prompt = builder._load_file("fragments/10_system_ai_delegation.md")
    if delegation_prompt:
        parts.append(delegation_prompt)

    if role and role.strip():
        parts.append(f"# Role\n{role.strip()}")

    # 포식 모드 등 표면별 추가 역할 — 실행 에이전트는 그대로 두고 역할만 덧댄다.
    if extra_role and extra_role.strip():
        parts.append(f"# Role (표면별 추가)\n{extra_role.strip()}")

    if user_profile and user_profile.strip():
        parts.append(f"# 시스템 메모\n{user_profile.strip()}")

    return "\n\n".join(parts)


def _repair_turn_block(builder) -> str:
    """이 턴에 RED 그랜트가 살아 있으면 fragments/13_repair.md 본문, 아니면 빈 문자열."""
    try:
        from thread_context import get_current_task_id, get_current_agent_id
        from red_grant import active_grant
        if active_grant(task_id=get_current_task_id() or None,
                        agent_id=get_current_agent_id() or None) is None:
            return ""
        return builder._load_file("fragments/13_repair.md") or ""
    except Exception as e:
        logger.debug(f"[prompt_builder] 수리 교리 주입 생략 (무시): {e}")
        return ""


def _build_dynamic_context(
    consciousness_output: dict = None,
    model_name: str = "",
    execution_memory: str = "",
) -> str:
    """가변 컨텍스트 — 매 호출마다 달라지는 부분만 (시스템 AI/프로젝트 에이전트 공통).

    user message 앞에 prepend되어 프롬프트 캐시 prefix를 깨뜨리지 않게 한다.
    """
    builder = get_prompt_builder()
    parts = []

    # 정밀 현재 시각 — stable 프롬프트엔 날짜만 두어 캐시를 보존하고(발견 1),
    # 분 단위는 캐시되지 않는 dynamic(여기, user message 앞)에 둔다.
    from datetime import datetime
    parts.append(f"# 현재 시각\n{datetime.now().strftime('%Y-%m-%d %H:%M')}")

    if execution_memory:
        parts.append(execution_memory)

    # 배경 참고만 담는다. 명령을 *형성*하는 것(문제 설정·쓸 액션·가이드 지시·충족 기준)은
    # 여기 두지 않는다 — 그건 compile_user_command()가 사용자 명령에 융합한다(의식 경로).
    if consciousness_output:
        # context_notes 폐지 (2026-06-28). 응답 형식에 없어 항상 빈 값 → 죽은 읽기 제거
        # (2026-07-06 스키마 감사). 맥락은 task_framing으로 흡수된다.

        # self_awareness·world_state 출력 필드 폐지 (2026-06-28). 모델명만 남긴다.
        if model_name:
            parts.append(f"# 자기 인식\n- AI 모델: {model_name}")

        guide_files = consciousness_output.get("guide_files", [])
        for guide in guide_files:
            block = builder._guide_block(guide)
            if block:
                parts.append(block)
    else:
        if model_name:
            parts.append(f"# 자기 인식\n- AI 모델: {model_name}")

    # 수리 턴 교리 — 실행자에게 *직접* (2026-09-02).
    # ★왜 여기인가: 의식 프롬프트의 수리 안전수칙은 task_framing(1-2문장 병목)을 거쳐야
    #   실행자에 닿는데, 실행자 자신의 base 프롬프트에는 "요청 밖의 개선 금지"가 직접
    #   걸려 있어 반대 압력만 온전히 도달했다 — 그 결과가 "발견한 뿌리를 범위 밖이라
    #   안 고침 + 고칠까요?"(사용자 관찰 09-01). 소비처에 소비처 말로 둔다.
    #   신호 = RED 그랜트(사람 명령 수리 턴에만 발급, 3단계) — 프롬프트 조립(4단계)보다 앞선다.
    #   dynamic 에 두므로 stable prefix 캐시는 그대로다. 실패는 어느 겹이든 프롬프트를 못 깬다.
    repair_block = _repair_turn_block(builder)
    if repair_block:
        parts.append(repair_block)

    if not parts:
        return ""
    return (
        "<turn_context note=\"이번 턴 한정 부속 참고 정보.\">\n"
        + "\n\n".join(parts)
        + "\n</turn_context>"
    )


# ── 상상실행 초안 (2026-08-31, 사용자 판정 집행) ─────────────────────────────
# 의식이 문제를 규정하며 핵심 작업의 IBL 문장을 초안(imagined_ibl)으로 짓는다 — 사람이
# 행동 전에 동작을 상상실행하듯, 계획을 액추에이터의 언어로 강제해 산문 절차가 숨기는
# 불가능성(안 흐르는 통화·없는 파라미터)을 실행 전에 드러낸다. 초안은 명령이 아니라
# **검증 대상**: 기계 앞모형(파서·액션 실재·파라미터 어휘·T1/T2 통화 타입, LLM 0)을
# 통과해야 강한 출발점이 되고, 실패하면 오류를 붙여 참고로 강등된다. 초안은 턴-로컬 —
# 해마에는 절대 직접 들어가지 않는다(합성 접지 원칙: 기억은 실행된 문장만. 초안이
# 채택·실행·성공하면 기존 증류가 *실행된 형태*를 거둬간다 — 상상→실행→기억 일방향 밸브).

import re as _re

_DRAFT_ACTION_RE = _re.compile(r'\[([a-z_-]+):([a-z_0-9-]+)\]')


def validate_imagined_draft(code: str) -> tuple:
    """상상실행 초안의 기계 앞모형 검증. 반환 (ok: bool, error: str).

    검사 4겹 — ①파서(문법) ②액션 실재(환각 어휘) ③파라미터 어휘(미인식 키)
    ④T1/T2 통화 타입(안 흐르는 파이프). 전부 기존 자산 재사용, LLM 0.
    검사기 자체가 미가용이면 그 겹은 보수적 통과(초안은 힌트일 뿐 — 실행기의
    정직 거절이 최종 심판이라 여기서 턴을 깨지 않는다)."""
    code = (code or "").strip()
    if not code:
        return (False, "빈 초안")
    # ⓪ 액션 존재 — 파서는 산문·미완성 조각을 조용히 삼킬 수 있으니(빈 params 강등 등),
    #   [node:action] 이 하나도 없는 초안은 IBL 이 아니라고 먼저 거절한다.
    if not _DRAFT_ACTION_RE.search(code):
        return (False, "IBL 액션([node:action])이 없는 초안")
    # ① 문법
    try:
        from ibl_parser import parse
        parsed = parse(code)
    except ImportError:
        return (True, "")
    except Exception as e:
        return (False, f"파싱 실패: {e}")
    # ② 액션 실재 (미존재 노드/액션 = 환각 — ibl_usage_rag._validate_ibl_actions 와 같은 판정)
    try:
        from ibl_access import load_nodes_raw
        nodes = (load_nodes_raw() or {}).get("nodes", {})
        if nodes:
            for n, a in _DRAFT_ACTION_RE.findall(code):
                if a not in ((nodes.get(n) or {}).get("actions") or {}):
                    return (False, f"미존재 액션 [{n}:{a}]")
    except Exception:
        pass
    # ③ 파라미터 어휘
    try:
        from ibl_param_vocab import check_code_params
        issues = check_code_params(code)
        if issues:
            detail = ", ".join(f"{i['action']}({','.join(i['unknown'])})" for i in issues)
            return (False, f"미인식 파라미터: {detail}")
    except Exception:
        pass
    # ④ 통화 타입 (T1 머리 변환자 기아 · T2 이음매 기아 — 실행기와 한 벌)
    try:
        from ibl_pipe_types import head_transform_error, seam_starvation_error
        err = head_transform_error(parsed)
        if err:
            return (False, err)
        seam = seam_starvation_error(parsed)
        if seam:
            return (False, seam[1])
    except Exception:
        pass
    return (True, "")


def draft_adoption(draft_code: str, tool_calls: list):
    """초안의 액션이 실제 실행에 등장했는가 — True/False/None(초안 또는 실행 없음).

    관찰 계기(리랭킹·게이트 아님): _recall_was_used 와 같은 액션 교집합 판정.
    턴 끝에 [상상실행] 로그 한 줄 — 초안이 실제로 채택되는지의 실측 데이터."""
    pairs = set(_DRAFT_ACTION_RE.findall(draft_code or ""))
    if not pairs:
        return None
    executed = set()
    for tc in tool_calls or []:
        if isinstance(tc, dict) and tc.get("tool_name") == "execute_ibl":
            executed |= set(_DRAFT_ACTION_RE.findall(
                (tc.get("input") or {}).get("code", "") or ""))
    if not executed:
        return None
    return bool(pairs & executed)


def compile_user_command(user_message: str, consciousness_output: dict) -> str:
    """의식 경로 '사용자 명령 변형기' — [사용자 원문 명령 + 의식의 보강]을 하나의 '사용자 명령'
    프레임으로 융합하되, 그 사이에 **당위 앵커**를 끼운다.

    핵심(사용자 설계): 의식이 더한 것(문제 설정·쓸 수 있는 액션·참고 가이드·충족 기준)을
    원문 명령에 이어 붙이되, 그 사이에 "— 다음 절차에 따라 수행하라:" 앵커를 *사용자 목소리의
    문장 연속*으로 끼워, 뒤따르는 보강 전체를 '참고'가 아닌 '명령'으로 재분류한다.

    (설계 반전 이력) 이전엔 '선언 없이 위치·형식만'으로 원문과 보강을 *구분 안 되게* 붙였다 —
    "모델이 둘을 구분 못 하고 전부 사용자 명령으로 읽는다"는 가정 위였다. 그러나 모델은 짧은
    구어체 원문과 길고 분석적인 보강을 쉽게 구분해 보강을 '메타 해설'로 격하시켰다. 그래서
    seam을 부정하지 않고 *무기화*한다 — 명시적 당위 앵커로 "이 아래는 따른다"를 못박는다.

    두 단서: ① 앵커는 출처(의식 에이전트)를 절대 드러내지 않는다 — 드러내면 '기계 제안'으로
    읽혀 권위가 도로 약해진다(그래서 새 섹션 헤더가 아니라 사용자 발화의 연속). ② 방법 지시
    (hint)는 액션 목록의 '(이 밖의 액션도 가능)' 허가 어조에서 떼어 별도 명령문 줄('수행 절차:')로
    올린다 — 의무가 가용성으로 격하되지 않도록. 무거운 배경(가이드 본문·세계상태 등)은
    _build_dynamic_context가 turn_context 참고로 따로 둔다.
    """
    co = consciousness_output or {}

    # 보강 줄을 먼저 모은다 — 비어있으면 앵커를 끼우지 않는다(허공 매달림 방지).
    aug = []

    task_framing = (co.get("task_framing") or "").strip()
    if task_framing:
        aug.append(task_framing)

    # 의식 프롬프트 출력 키는 capability_focus (consciousness_prompt.md 응답 형식).
    # 예전 ibl_focus 이름을 폴백으로 둔다 — 개명 드리프트로 highlight_actions·hint가
    # 융합에서 조용히 새던 버그의 재발 방지.
    cap_focus = co.get("capability_focus") or co.get("ibl_focus") or {}
    highlight = cap_focus.get("highlight_actions") or []
    if highlight:
        # 팔레트가 열려 있다는 건 사실 — '(이 밖의 액션도 가능)'은 *목록*에만 남긴다.
        aug.append("쓸 수 있는 IBL 액션: " + ", ".join(highlight) + " (이 밖의 액션도 가능).")
    hint = (cap_focus.get("hint") or "").strip()
    if hint:
        # 방법 지시는 허가 어조에서 분리해 명령문 줄로.
        aug.append(f"수행 절차: {hint}")

    # 상상실행 초안 — 검증 통과분만 강한 출발점, 실패분은 오류 동반 참고로 강등.
    # (당위 앵커 아래 실리므로 통과분은 명령 권위를 갖는다 — 그래서 관문이 앞선다.)
    draft = (co.get("imagined_ibl") or "").strip()
    if draft:
        ok, err = validate_imagined_draft(draft)
        if ok:
            aug.append("실행 초안(기계 검증 통과):\n" + draft +
                       "\n이 초안을 출발점으로 삼되, 그대로 복사하지 말고 실행 결과에 따라 "
                       "파라미터·구성을 검증하며 다듬어라.")
        else:
            aug.append(f"실행 초안(검증 실패 — {err}):\n" + draft +
                       "\n이 초안은 그대로 쓰지 말 것. 위 오류를 감안해 직접 재구성하라.")

    guide_files = co.get("guide_files") or []
    if guide_files:
        aug.append(
            "참고할 가이드: " + ", ".join(guide_files)
            + " (위 turn_context에 본문 포함) — 그 지침대로 수행할 것."
        )

    achievement_criteria = (co.get("achievement_criteria") or "").strip()
    if achievement_criteria:
        aug.append(f"충족 기준: {achievement_criteria}")

    user_cmd = (user_message or "").strip()
    if not aug:
        return f"사용자 명령: {user_cmd}"

    # 당위 앵커 — 원문 명령에 사용자 목소리로 이어 붙여, 뒤따르는 보강 전체를 명령으로 재분류.
    return f"사용자 명령: {user_cmd} — 다음 절차에 따라 수행하라:\n" + "\n".join(aug)


def build_system_ai_prompt_split(
    user_profile: str = "",
    git_enabled: bool = False,
    consciousness_output: dict = None,
    model_name: str = "",
    execution_memory: str = "",
    extra_role: str = "",
    allowed_set=None,
) -> tuple:
    """시스템 AI 프롬프트를 (안정, 가변)로 분리해 반환.

    안정 부분은 system_prompt로 넘기고, 가변 부분은 user message 앞에 prepend한다.
    이렇게 해야 매 호출마다 시스템 프롬프트 prefix가 동일해져 Anthropic 프롬프트
    캐시가 hit한다.

    extra_role: 표면별 추가 역할 프롬프트(예: 포식 모드의 "링크를 나열하라"). 안정 부분에
        들어가므로, 같은 표면의 호출끼리는 prefix가 동일해 캐시가 유지된다.

    Returns:
        (stable_prompt, dynamic_context) — dynamic은 빈 문자열일 수 있음
    """
    stable = _build_system_ai_stable_prompt(user_profile, git_enabled, extra_role, allowed_set)
    dynamic = _build_dynamic_context(consciousness_output, model_name, execution_memory)
    return stable, dynamic


def build_system_ai_prompt(
    user_profile: str = "",
    git_enabled: bool = False,
    consciousness_output: dict = None,
    model_name: str = "",
    execution_memory: str = "",
) -> str:
    """시스템 AI 프롬프트 — 안정+가변을 합친 단일 문자열 (호환용).

    새 호출자는 build_system_ai_prompt_split을 직접 사용해 캐시 효율을 얻는다.
    """
    stable, dynamic = build_system_ai_prompt_split(
        user_profile=user_profile,
        git_enabled=git_enabled,
        consciousness_output=consciousness_output,
        model_name=model_name,
        execution_memory=execution_memory,
    )
    if dynamic:
        return f"{stable}\n\n{dynamic}"
    return stable


# 테스트용
if __name__ == "__main__":
    builder = PromptBuilder()

    # 테스트 1: 기본 (위임 없음, git 없음)
    prompt1 = builder.build(agent_count=1)
    print(f"기본: {builder.estimate_tokens(prompt1)} 토큰")
    print()

    # 테스트 2: 위임 + Git
    prompt2 = builder.build(agent_count=3, git_enabled=True)
    print(f"위임 + Git: {builder.estimate_tokens(prompt2)} 토큰")
