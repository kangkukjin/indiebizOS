"""
api_system_ai.py - 시스템 AI 대화 API
IndieBiz OS Core

시스템 AI는 IndieBiz의 관리자이자 안내자입니다:
- 첫 실행 시 사용법 안내
- 도구 패키지 분석, 설치, 제거
- 에이전트 생성, 수정, 삭제 도움
- 오류 진단 및 해결

모듈화:
- system_ai_core.py: AI 에이전트 생성, 메시지 처리, 의식 통합, 설정
- system_ai_tools.py: 도구 정의, 프로젝트 에이전트/이벤트/스위치 실행
- system_ai_plans.py: 플랜 레지스트리, 플랜/스케줄 실행
"""

import json
import os
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 메모리 관련
from system_ai_memory import (
    load_user_profile,
    save_conversation,
    get_recent_conversations,
    get_history_for_ai,
    get_memory_context,
    save_memory,
    get_memories
)
# 시스템 문서 관련
from system_docs import (
    read_doc,
    init_all_docs
)

# === 하위 모듈 re-export (기존 import 호환성 유지) ===
from system_ai_core import (
    load_system_ai_config,
    save_system_ai_config,
    create_system_ai_agent,
    get_system_ai_runner,
    process_system_ai_message,
    process_system_ai_message_stream,
    execute_system_tool,
    get_system_prompt,
    get_anthropic_tools,
    get_all_system_ai_tools,
    SYSTEM_AI_CONFIG_PATH,
    DATA_PATH,
    BACKEND_PATH,
)

from system_ai_tools import (
    _execute_list_project_agents,
    _execute_call_project_agent,
    _execute_manage_events,
    _execute_list_switches,
)

from system_ai_plans import (
    register_plan_step,
    on_agent_plan_step_complete,
    _execute_schedule,
    _execute_create_plan,
    _update_plan_status,
    _parse_plan_steps,
    _execute_plan,
)

router = APIRouter()

# 시스템 AI 역할 파일 경로
SYSTEM_AI_ROLE_PATH = DATA_PATH / "system_ai_role.txt"
# 포식 브라우저 역할 프롬프트 — 실행 에이전트에 "가볼 만한 링크를 나열하라"를 덧대는 표면별 역할.
# 매 요청마다 읽어 편집이 바로 반영된다(계기판 설정에서 이 파일을 고치는 미래를 위한 이음매).
FORAGE_ROLE_PATH = DATA_PATH / "forage_role.txt"
# 웹 검색 가이드(검색법 + 웹 랜드마크 지도). 포식=정의상 항상 웹검색이라 forage_chat 이 *항상 주입*.
# 일반 에이전트는 read_guide/의식 get_guide_list 로 선택적으로 읽는다(같은 파일). 매 요청 read=라이브.
WEB_SEARCH_GUIDE_PATH = DATA_PATH / "guides" / "web_search.md"


# ============ Pydantic 모델 ============

class ImageData(BaseModel):
    base64: str
    media_type: str


class ChatMessage(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None
    images: Optional[List[ImageData]] = None
    # True면 즉시 반환(fire-and-forget) — 수 분짜리 작업이 터널 타임아웃(524)에 걸리지 않도록.
    # 응답/위임결과는 평소처럼 대화 로그에 저장되니 호출 측이 메시지를 폴링해서 받는다.
    background: bool = False


class ChatResponse(BaseModel):
    response: str
    timestamp: str
    provider: str
    model: str


class PromptConfigUpdate(BaseModel):
    selected_template: Optional[str] = None


class RolePromptUpdate(BaseModel):
    content: str


# ============ 시스템 문서 초기화 플래그 ============
_docs_initialized = False


# ============ 채팅 API ============

@router.post("/system-ai/chat", response_model=ChatResponse)
def chat_with_system_ai(chat: ChatMessage):
    # ★ 동기(def) 엔드포인트로 둔다 (async 아님). process_system_ai_message 는 LLM
    # 파이프라인 전체를 동기로 블로킹한다. async 로 두면 이벤트 루프를 통째로 막아,
    # claude_code(아웃오브프로세스) 프로바이더가 MCP→HTTP 로 같은 백엔드 /ibl/execute
    # 로 재진입할 때 루프가 막혀 처리되지 못한다(자기 데드락) → mcp urllib 120초
    # 타임아웃 후에야 풀려 에이전트가 "타임아웃 실패"로 오판한다(예: [limbs:phone]
    # 포워드가 폰에 닿질 못함). def 로 두면 FastAPI 가 스레드풀에서 실행해 루프가
    # 자유로워지고 재진입 /ibl/execute 가 동시 처리된다. set_current_task_id 등은
    # threading.local 이라 엔드포인트 전체가 한 워커 스레드에서 돌아야 일관된다.
    """
    시스템 AI와 대화

    **통합 아키텍처**: AIAgent 클래스를 사용하여 프로젝트 에이전트와
    동일한 프로바이더 코드를 공유합니다. 모든 프로바이더(Anthropic, OpenAI,
    Google, Ollama)가 자동으로 지원됩니다.

    **태스크 기반 처리**: 시스템 AI도 태스크를 생성하고 위임 체인을 지원합니다.
    - 위임이 없으면 → 즉시 응답
    - 위임이 있으면 → "위임 중" 응답, 결과는 WebSocket으로 전송
    """
    import uuid
    from thread_context import set_current_task_id, clear_current_task_id, did_call_agent, clear_called_agent
    from system_ai_memory import create_task as create_system_ai_task

    global _docs_initialized

    config = load_system_ai_config()

    if not config.get("enabled", True):
        raise HTTPException(status_code=400, detail="시스템 AI가 비활성화되어 있습니다.")

    api_key = config.get("apiKey", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="API 키가 설정되지 않았습니다. 설정에서 API 키를 입력해주세요.")

    provider = config.get("provider", "anthropic")
    model = config.get("model", "claude-sonnet-4-20250514")

    # 시스템 문서 초기화 (서버 시작 후 최초 1회만)
    if not _docs_initialized:
        init_all_docs()
        _docs_initialized = True

    def _process() -> str:
        """태스크 생성 + LLM 처리 + 대화 저장. 스레드 컨텍스트(threading.local)가 필요하므로
        동기/백그라운드 모두 이 함수 한 덩어리를 한 스레드에서 실행한다. 응답 텍스트를 반환하고
        (위임 없을 때) assistant 메시지를 대화 로그에 저장한다. 위임이면 최종 결과는
        system_ai_runner._finalize_task() 가 따로 저장한다."""
        task_id = f"task_sysai_{uuid.uuid4().hex[:8]}"
        ws_client_id = chat.context.get("ws_client_id") if chat.context else None
        create_system_ai_task(
            task_id=task_id,
            requester="user@gui",
            requester_channel="gui",
            original_request=chat.message,
            delegated_to="system_ai",
            ws_client_id=ws_client_id
        )
        set_current_task_id(task_id)
        clear_called_agent()
        try:
            # 최근 대화 히스토리 로드 (조회 + 역할 매핑 + Observation Masking 통합)
            history = get_history_for_ai(limit=7)

            # 이미지 데이터 변환
            images_data = None
            if chat.images:
                images_data = [{"base64": img.base64, "media_type": img.media_type} for img in chat.images]

            # 사용자 메시지 저장 (이미지 포함)
            save_conversation("user", chat.message, images=images_data)

            # AIAgent를 사용한 통합 처리 (모든 프로바이더 자동 지원)
            response_text, tool_images = process_system_ai_message(
                message=chat.message,
                history=history,
                images=images_data
            )

            if did_call_agent():
                # 위임이 발생함 → 결과는 나중에 _finalize_task 가 저장(폴링/WebSocket이 회수)
                return f"[위임 중] 프로젝트 에이전트에게 작업을 위임했습니다. 결과는 잠시 후 도착합니다.\n\n{response_text}"

            # 위임 없음 → 즉시 응답, 태스크 완료
            from system_ai_memory import complete_task as complete_system_ai_task
            complete_system_ai_task(task_id, response_text[:500])
            save_conversation("assistant", response_text, images=tool_images)
            return response_text
        finally:
            clear_current_task_id()
            clear_called_agent()

    if chat.background:
        def _worker():
            try:
                _process()
            except Exception:
                import traceback
                traceback.print_exc()
        threading.Thread(target=_worker, daemon=True).start()
        return ChatResponse(
            response="작업을 시작했습니다.",
            timestamp=datetime.now().isoformat(),
            provider=provider,
            model=model
        )

    try:
        response_text = _process()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 응답 생성 실패: {str(e)}")

    return ChatResponse(
        response=response_text,
        timestamp=datetime.now().isoformat(),
        provider=provider,
        model=model
    )


class RecallPreviewRequest(BaseModel):
    message: str


# 연상 묶음의 채널 태그 → 조종실 표시 라벨. _build_execution_memory 가 이 순서로 결합한다.
_RECALL_CHANNELS = [
    ("execution_memory", "실행기억 — 해마 (과거 IBL 용례 연상)"),
    ("related_memory", "심층 메모리 — 사용자·세계 사실"),
    ("forage_memory", "포식 기억 — 냄새지도 + 주인모델"),
    ("disk_skeleton", "디스크 골격 — 집중 폴더 지도 (포식 의도일 때만)"),
]


@router.post("/system-ai/recall-preview")
def recall_preview(req: RecallPreviewRequest):
    """조종실 '기억 회상 검증' — 에이전트 0단계(연상)가 주입하는 기억 묶음을 실행 없이 미리 본다.

    시스템 AI 러너의 _build_execution_memory(해마+심층+포식+디스크골격, LLM 0·부작용 없음)를
    그대로 호출해 *실제 주입물과 동일한* XML 을 채널별로 갈라 돌려준다 — 가공하면 검증창이
    거짓말을 하게 되므로 원문 그대로. sync def 라 FastAPI 스레드풀에서 돈다(임베딩 검색 블로킹).
    """
    import re as _re
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message 가 비어 있습니다")
    from system_ai_core import get_system_ai_runner
    runner = get_system_ai_runner()
    if runner is None:
        raise HTTPException(status_code=503, detail="시스템 AI 러너가 아직 준비되지 않았습니다")
    xml, top_score, top_code = runner._build_execution_memory(message)

    sections = []
    for tag, label in _RECALL_CHANNELS:
        m = _re.search(rf"<{tag}\b.*?</{tag}>", xml or "", _re.DOTALL)
        content = m.group(0) if m else ""
        sections.append({"key": tag, "label": label, "present": bool(content), "content": content})
    return {
        "top_score": round(float(top_score or 0.0), 4),
        "top_code": top_code or "",
        "total_chars": len(xml or ""),
        "sections": sections,
    }


class ForageMessage(BaseModel):
    message: str
    images: Optional[List[ImageData]] = None


class ForageTranslateReq(BaseModel):
    texts: List[str]
    target: str = "ko"


def _gtx_translate_blob(text: str, target: str) -> str:
    """무공식 구글 번역 엔드포인트로 한 덩어리 번역 → 세그먼트 이어붙인 번역문 반환(키 불필요).

    translate_a/single 은 문장 단위로 분절한 배열을 주되 원문의 개행(\\n)을 세그먼트에 보존한다
    (실측). 그래서 텍스트들을 \\n 으로 이어 한 요청에 보내고, 반환 세그먼트를 이어붙이면 개행이
    제자리에 남아 다시 \\n 으로 쪼개 줄별 매핑할 수 있다. POST 라 GET 길이한계도 회피.
    """
    import requests
    r = requests.post(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": "auto", "tl": target, "dt": "t"},
        data={"q": text},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    segs = data[0] or []
    return "".join(s[0] for s in segs if s and s[0] is not None)


@router.post("/forage/translate")
def forage_translate(req: ForageTranslateReq):
    """포식 브라우저 인라인 DOM 번역 — 텍스트 노드 문자열 배열을 받아 *같은 길이*로 번역해 반환.

    구글 페이지 번역 프록시(translate.goog)가 일부 지역에서 막혀(지역 차단) webview 로 *이동*하는
    대신, 현재 페이지의 텍스트만 번역해 제자리 치환하는 방식의 백엔드. 무공식 구글 API(키 없음).
    개행(\\n)을 배치 구분자로 쓰므로 노드 내부 공백은 정규화. 배치 줄 수가 어긋나면 그 배치는 개별
    번역으로 폴백(정확성 보장). 실패 항목은 원문 유지(graceful). 엔진은 여기만 바꾸면 교체됨.
    """
    texts = req.texts or []
    target = (req.target or "ko").strip() or "ko"
    out = list(texts)  # 기본 = 원문(빈칸·실패 시 유지)
    # 번역 대상 = 내용 있는 항목만. 내부 공백/개행은 구분자 충돌 방지로 단일 공백 정규화.
    work = [(i, " ".join((texts[i] or "").split())) for i in range(len(texts))
            if texts[i] and texts[i].strip()]
    CHUNK = 1500  # 문자 예산(응답 안정성)

    def _flush(batch):
        if not batch:
            return
        joined = "\n".join(t for _, t in batch)
        parts = None
        try:
            parts = _gtx_translate_blob(joined, target).split("\n")
        except Exception as e:
            print(f"[포식번역] 배치 실패 (개별 폴백): {e}")
        if parts is not None and len(parts) == len(batch):
            for (i, _o), p in zip(batch, parts):
                out[i] = p
        else:  # 줄 수 불일치·실패 → 개별 번역 폴백
            for i, t in batch:
                try:
                    out[i] = _gtx_translate_blob(t, target)
                except Exception:
                    pass  # 원문 유지

    batch, blen = [], 0
    for i, t in work:
        if blen + len(t) + 1 > CHUNK and batch:
            _flush(batch)
            batch, blen = [], 0
        batch.append((i, t))
        blen += len(t) + 1
    _flush(batch)
    return {"translations": out}


@router.post("/forage/chat", response_model=ChatResponse)
def forage_chat(chat: ForageMessage):
    """포식 브라우저 검색 — 실행 에이전트와 *동일한* 인지 파이프라인에 '포식 역할'만 덧댄다.

    에이전트가 사용자 의도를 듣고 스스로 IBL 검색(sense:search_naver/ddg/realty 등)을 골라
    '가볼 만한 곳'의 링크 목록을 낸다. 무엇을·어떻게 찾을지는 전부 에이전트(프롬프트+IBL) 몫 —
    여기엔 검색 오케스트레이션 코드가 없다(forager는 AI다, 짓지 않는다).
    상태 없는 검색이라 대화 로그에 저장하지 않는다.
    """
    import uuid
    from thread_context import (
        set_current_task_id, clear_current_task_id, clear_called_agent,
        set_allowed_nodes, get_allowed_nodes,
    )
    from system_ai_memory import (
        create_task as create_system_ai_task,
        complete_task as complete_system_ai_task,
    )
    from episode_logger import EpisodeLogger

    config = load_system_ai_config()
    if not config.get("enabled", True):
        raise HTTPException(status_code=400, detail="시스템 AI가 비활성화되어 있습니다.")
    if not config.get("apiKey", ""):
        raise HTTPException(status_code=400, detail="API 키가 설정되지 않았습니다.")

    extra_role = FORAGE_ROLE_PATH.read_text(encoding='utf-8') if FORAGE_ROLE_PATH.exists() else ""
    # ★웹 검색 가이드 항상 주입(포식=늘 웹검색). 이전 bespoke web_landmarks 키워드-게이트 주입을
    #   대체 — 이제 가이드(검색법 + 랜드마크)가 단일 소스. 일반 에이전트는 read_guide 로 선택적.
    if WEB_SEARCH_GUIDE_PATH.exists():
        guide = WEB_SEARCH_GUIDE_PATH.read_text(encoding='utf-8')
        extra_role = f"{extra_role}\n\n---\n\n{guide}" if extra_role else guide

    images_data = None
    if chat.images:
        images_data = [{"base64": img.base64, "media_type": img.media_type} for img in chat.images]

    task_id = f"task_forage_{uuid.uuid4().hex[:8]}"
    create_system_ai_task(
        task_id=task_id, requester="user@forage", requester_channel="gui",
        original_request=chat.message, delegated_to="system_ai",
    )
    set_current_task_id(task_id)
    clear_called_agent()
    # 포식 노드 스코프 — sense(검색·크롤·소스) + self(자기 출력·상태) + table(통화 변환자: filter/sort/dedup…).
    # engines(미디어 생성=슬라이드·영상·이미지)는 제외 — 포식은 링크 나열이라 생성기 불요. 변환 문법은
    #   table 노드로 분리됐으므로 그쪽을 준다(옛 engines는 변환자 때문에 넣었던 것 → table 이 그 자리).
    # limbs(브라우저 운전=인간 몫)·others(위임·연락=말단 단일 에이전트엔 무용)는 제외.
    # allowed_set=프롬프트 어휘 스코핑(IBL XML 축소), thread_context=실행 하드 집행 — 같은 집합.
    forage_nodes = {"sense", "self", "table"}
    _prev_allowed = get_allowed_nodes()
    set_allowed_nodes(forage_nodes)
    # 에피소드 로깅 — agent="forage" 로 주행 기록을 남긴다. 포식은 WebSocket 핸들러를 안 타는
    # 동기 REST 라 그동안 주행기록계에서 빠져 있었음(분석할 데이터 부재). start/end 한 쌍만 걸면,
    # 내부 인지 파이프라인이 찍는 [연상]·[무의식] 마커가 그대로 요약 지표로 자동 추출된다.
    # ★대화 저장·심층/의미 메모리 증류는 WS 핸들러 몫이라 여긴 없음 → 검색 노이즈로 의미기억을
    #   더럽히지 않는다(stateless 검색 성격 보존). 단 *포식 기억 증류*는 붙인다(아래 스레드) —
    #   포식 브라우저가 웹 포식의 주 표면이라 owner_model·웹 관습이 여기서 쌓여야 하기 때문.
    try:
        EpisodeLogger.start_episode("forage", chat.message)
    except Exception:
        pass
    try:
        response_text, _imgs = process_system_ai_message(
            message=chat.message, history=[], images=images_data, extra_role=extra_role,
            force_role="forage",       # 모델 = 계기판 에이전트 핀(overrides["forage"], 기본 경량). 의식·분류 건너뛰고 빠르게.
            allowed_set=forage_nodes,  # 어휘를 sense+self+table 로만 — 경량 모델 프롬프트 다이어트 + 라우팅 집중.
        )
        complete_system_ai_task(task_id, response_text[:500])
        # ★포식 기억 증류 — 포식 브라우저는 웹 포식의 *주 표면*이라 owner_model·웹 관습이 여기서
        #   쌓여야 한다(주입은 이미 코어 _build_execution_memory 가 함). 검색 응답을 막지 않도록
        #   백그라운드 스레드로 돌리고(동기 REST), assume_forage 로 메시지 cue 게이트를 우회한다
        #   (정의상 항상 포식). 자기서술·locus 실존검증 게이트가 안전판. 심층/의미 메모리는
        #   여전히 안 건드림(검색 노이즈 격리) — 포식 기억 전용 증류만 붙인다.
        if response_text:
            import threading
            from system_ai_core import get_system_ai_runner

            def _forage_distill(msg: str, resp: str):
                try:
                    # 초크포인트에 forage 만 옵트인(심층/의미·경험 증류는 검색 노이즈 격리로 제외)
                    get_system_ai_runner()._after_response(
                        msg, resp,
                        write_experience=False, write_deep=False,
                        write_forage=True, assume_forage=True,
                    )
                except Exception as fe:
                    print(f"[포식기억] 브라우저 증류 오류 (무시): {fe}")

            threading.Thread(
                target=_forage_distill, args=(chat.message, response_text), daemon=True
            ).start()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"포식 검색 실패: {str(e)}")
    finally:
        set_allowed_nodes(_prev_allowed)
        clear_current_task_id()
        clear_called_agent()
        try:
            EpisodeLogger.end_episode()
        except Exception:
            pass

    return ChatResponse(
        response=response_text,
        timestamp=datetime.now().isoformat(),
        provider=config.get("provider", "anthropic"),
        model=config.get("model", ""),
    )


# ============ 인지 패널 상태 (질문 / TODO / 계획 모드) ============
# 에이전트의 ask_user_question · todo_write · enter/exit_plan_mode 는 그 결과를
# data/system_ai_state/*.json 에 남길 뿐, 이제껏 그걸 읽어 사용자에게 띄우고 답을
# 되돌리는 HTTP 엔드포인트가 없었다(프론트는 폴링했지만 백엔드가 404). 그래서
# 에이전트는 "응답 대기 중"에 멈추고 사용자는 질문을 보지도 답하지도 못하는 교착이
# 났다. 아래가 그 빠진 절반이다: 계기판(ChatView)이 2초 폴링으로 상태를 읽어 패널을
# 띄우고, 답/승인을 여기로 되돌린다. 실제 에이전트 재개는 프론트가 답을 일반 대화
# 메시지(system_ai_stream)로 흘려보내 다음 턴을 여는 방식(히스토리에 질문이 남아
# 맥락 유지) — 핸들러가 논블로킹이라 원래 턴은 이미 끝나 있기 때문이다.

_SYS_STATE_DIR = DATA_PATH / "system_ai_state"


def _read_sys_state(name: str) -> Optional[Any]:
    """data/system_ai_state/<name> 을 읽어 파싱 (없으면 None)."""
    p = _SYS_STATE_DIR / name
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_sys_state(name: str, data: dict) -> None:
    _SYS_STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_SYS_STATE_DIR / name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _clear_sys_state(name: str) -> None:
    p = _SYS_STATE_DIR / name
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass


class QuestionAnswerBody(BaseModel):
    answers: Dict[str, Any]


class PlanRejectBody(BaseModel):
    reason: Optional[str] = None


# ---- 질문 (ask_user_question ↔ QuestionPanel) ----
@router.get("/system-ai/questions")
def get_system_ai_questions():
    """대기 중인 사용자 질문. 프론트가 2초 폴링해 status=='pending'이면 패널을 띄운다."""
    st = _read_sys_state("question_state.json")
    if not st:
        return {"questions": [], "status": "none", "answers": None}
    return {
        "questions": st.get("questions", []),
        "status": st.get("status", "none"),
        "answers": st.get("answers"),
    }


@router.post("/system-ai/questions/answer")
def answer_system_ai_question(body: QuestionAnswerBody):
    """사용자 답을 기록하고 질문을 마감(status=answered → 다음 폴링이 패널을 내린다).
    에이전트 재개는 프론트가 답을 일반 대화 메시지로 흘려보내 처리한다."""
    st = _read_sys_state("question_state.json") or {}
    st["status"] = "answered"
    st["answers"] = body.answers
    st["answered_at"] = datetime.now().isoformat()
    _write_sys_state("question_state.json", st)
    return {"status": "answered", "answers": body.answers}


@router.delete("/system-ai/questions")
def clear_system_ai_questions():
    _clear_sys_state("question_state.json")
    return {"status": "cleared"}


# ---- TODO (todo_write ↔ TodoPanel) ----
@router.get("/system-ai/todos")
def get_system_ai_todos():
    st = _read_sys_state("todo_state.json")
    if not st:
        return {"todos": [], "updated_at": None}
    if isinstance(st, list):  # 옛 형식 방어
        return {"todos": st, "updated_at": None}
    return {"todos": st.get("todos", []), "updated_at": st.get("updated_at")}


@router.delete("/system-ai/todos")
def clear_system_ai_todos():
    _clear_sys_state("todo_state.json")
    return {"status": "cleared"}


# ---- 계획 모드 (enter/exit_plan_mode ↔ PlanModePanel) ----
@router.get("/system-ai/plan-mode")
def get_system_ai_plan_mode():
    st = _read_sys_state("plan_mode_state.json")
    if not st:
        return {"active": False, "phase": None}
    plan_content = st.get("plan_content")
    if not plan_content:  # exit_plan_mode 가 상태에 안 넣었으면 파일에서 읽기
        pf = _SYS_STATE_DIR / "current_plan.md"
        if pf.exists():
            try:
                plan_content = pf.read_text(encoding="utf-8")
            except Exception:
                plan_content = None
    return {
        "active": st.get("active", False),
        "phase": st.get("phase"),
        "plan_content": plan_content,
        "entered_at": st.get("entered_at"),
    }


@router.post("/system-ai/plan-mode/approve")
def approve_system_ai_plan():
    st = _read_sys_state("plan_mode_state.json") or {}
    st["phase"] = "approved"
    st["approved_at"] = datetime.now().isoformat()
    _write_sys_state("plan_mode_state.json", st)
    return {"status": "approved"}


@router.post("/system-ai/plan-mode/reject")
def reject_system_ai_plan(body: PlanRejectBody = None):
    st = _read_sys_state("plan_mode_state.json") or {}
    st["phase"] = "revision_requested"
    if body and body.reason:
        st["reject_reason"] = body.reason
    _write_sys_state("plan_mode_state.json", st)
    return {"status": "revision_requested"}


@router.delete("/system-ai/plan-mode")
def clear_system_ai_plan_mode():
    _clear_sys_state("plan_mode_state.json")
    return {"status": "cleared"}


@router.get("/system-ai/welcome")
async def get_welcome_message():
    """
    첫 실행 시 환영 메시지
    (API 키 없이도 표시 가능한 정적 메시지)
    """
    return {
        "message": """안녕하세요! IndieBiz OS에 오신 걸 환영합니다.

저는 시스템 AI입니다. IndieBiz 사용을 도와드릴게요.

시작하려면 먼저 AI API 키를 설정해주세요:
1. 오른쪽 상단의 설정(⚙️) 버튼을 클릭
2. AI 프로바이더 선택 (Claude/GPT/Gemini)
3. API 키 입력

설정이 완료되면 저와 대화하면서 IndieBiz를 배워보세요!

무엇이든 물어보세요:
• "뭘 할 수 있어?"
• "새 프로젝트 만들어줘"
• "에이전트가 뭐야?"
• "도구 설치하려면?"
""",
        "needs_api_key": True
    }


@router.get("/system-ai/status")
async def get_system_ai_status():
    """시스템 AI 상태 확인"""
    config = load_system_ai_config()

    has_api_key = bool(config.get("apiKey", ""))

    return {
        "enabled": config.get("enabled", True),
        "provider": config.get("provider", "anthropic"),
        "model": config.get("model", "claude-sonnet-4-20250514"),
        "has_api_key": has_api_key,
        "ready": has_api_key and config.get("enabled", True)
    }


@router.post("/system-ai/reset-session")
async def reset_system_ai_session():
    """Claude Code 세션 매핑 클리어 — 다음 호출이 fresh 세션으로 시작.

    누적된 도구 결과·resume 컨텍스트를 끊고 싶을 때 사용.
    Claude Code provider가 아니면 no-op이지만 200 OK 반환 (안전).
    """
    try:
        from providers.claude_code import clear_session_for_agent
        # 시스템 AI의 registry_key는 "system:system_ai"
        clear_session_for_agent("system:system_ai")
        return {"ok": True, "message": "새 세션을 시작했습니다."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/system-ai/providers")
async def get_available_providers():
    """사용 가능한 AI 프로바이더 목록"""
    return {
        "providers": [
            {
                "id": "anthropic",
                "name": "Anthropic Claude",
                "models": [
                    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4 (추천)"},
                    {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
                    {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku (빠름)"},
                ],
                "api_url": "https://console.anthropic.com"
            },
            {
                "id": "openai",
                "name": "OpenAI GPT",
                "models": [
                    {"id": "gpt-4o", "name": "GPT-4o (추천)"},
                    {"id": "gpt-4o-mini", "name": "GPT-4o Mini (빠름)"},
                    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
                ],
                "api_url": "https://platform.openai.com/api-keys"
            },
            {
                "id": "google",
                "name": "Google Gemini",
                "models": [
                    {"id": "gemini-2.0-flash-exp", "name": "Gemini 2.0 Flash (추천)"},
                    {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro"},
                    {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash (빠름)"},
                ],
                "api_url": "https://aistudio.google.com/apikey"
            }
        ]
    }


# ============ 메모리 관련 API ============

@router.get("/system-ai/conversations")
async def get_conversations(limit: int = 20):
    """시스템 AI 대화 이력 조회"""
    conversations = get_recent_conversations(limit)
    return {"conversations": conversations}


@router.get("/system-ai/conversations/recent")
async def get_conversations_recent(limit: int = 20):
    """시스템 AI 최근 대화 조회"""
    conversations = get_recent_conversations(limit)
    return {"conversations": conversations}


@router.get("/system-ai/conversations/dates")
async def get_conversation_dates():
    """대화가 있는 날짜 목록 조회 (날짜별 메시지 수 포함)"""
    import sqlite3
    from system_ai_memory import MEMORY_DB_PATH

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT date(timestamp) as date, COUNT(*) as count
        FROM conversations
        GROUP BY date(timestamp)
        ORDER BY date DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    dates = [{"date": row[0], "count": row[1]} for row in rows if row[0]]
    return {"dates": dates}


@router.get("/system-ai/conversations/by-date/{date}")
async def get_conversations_by_date(date: str):
    """특정 날짜의 대화 조회"""
    import sqlite3
    from system_ai_memory import MEMORY_DB_PATH

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, timestamp, role, content, summary, importance
        FROM conversations
        WHERE date(timestamp) = ?
        ORDER BY id ASC
    """, (date,))

    rows = cursor.fetchall()
    conn.close()

    conversations = []
    for row in rows:
        conversations.append({
            "id": row[0],
            "timestamp": row[1],
            "role": row[2],
            "content": row[3],
            "summary": row[4],
            "importance": row[5]
        })

    return {"conversations": conversations}


@router.delete("/system-ai/conversations")
async def clear_conversations():
    """시스템 AI 대화 이력 삭제"""
    import sqlite3
    from system_ai_memory import MEMORY_DB_PATH

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()

    return {"status": "cleared"}


# ============ 프롬프트 설정 API ============

@router.get("/system-ai/prompts/config")
async def get_prompt_config():
    """프롬프트 설정 조회"""
    config = load_system_ai_config()
    return {
        "selected_template": config.get("selected_template", "default")
    }


@router.put("/system-ai/prompts/config")
async def update_prompt_config(data: PromptConfigUpdate):
    """프롬프트 설정 업데이트"""
    config = load_system_ai_config()

    if data.selected_template is not None:
        config["selected_template"] = data.selected_template

    save_system_ai_config(config)
    return {"status": "updated", "config": {
        "selected_template": config.get("selected_template")
    }}


@router.get("/system-ai/prompts/role")
async def get_role_prompt():
    """역할 프롬프트 조회 (별도 파일에서 로드)"""
    if SYSTEM_AI_ROLE_PATH.exists():
        content = SYSTEM_AI_ROLE_PATH.read_text(encoding='utf-8')
    else:
        content = ""
    return {"content": content}


@router.put("/system-ai/prompts/role")
async def update_role_prompt(data: RolePromptUpdate):
    """역할 프롬프트 업데이트 (별도 파일에 저장)"""
    SYSTEM_AI_ROLE_PATH.write_text(data.content, encoding='utf-8')
    return {"status": "updated"}
