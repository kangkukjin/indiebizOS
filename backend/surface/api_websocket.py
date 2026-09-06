"""
api_websocket.py - WebSocket 채팅 API (스트리밍 지원)
IndieBiz OS Core
"""

import re
import uuid
import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import yaml

from websocket_manager import manager
from conversation_db import ConversationDB

router = APIRouter()

# 매니저 인스턴스
project_manager = None

# 스트리밍을 위한 스레드 풀
executor = ThreadPoolExecutor(max_workers=4)

# 스트림 태스크 레지스트리 (2026-08-15 조향) — client_id 별 실행 중 스트림(시스템AI·에이전트 공용).
# 실행 중 같은 클라이언트의 새 메시지 = 조향 접수 판정에 쓴다. 연결 해제 시 정리.
_stream_tasks: dict = {}
# client_id → (조향 키, 에이전트 이름). 조향 키 = provider.agent_id 와 같은 값이어야
# execute_tool 의 drain 과 만난다 — 에이전트 경로는 agents.yaml 의 id(핸들러가 해소 직후
# 등록), 시스템 AI 는 "system_ai" 고정.
_stream_agent_keys: dict = {}

# 클라이언트별 중단 플래그 (client_id -> bool)
cancel_flags: dict[str, bool] = {}


def filter_internal_markers(text: str) -> str:
    """내부 시스템 마커를 출력에서 제거

    AI가 프롬프트에서 본 내부 마커 형식을 모방하여 출력에 포함시키는 경우가 있음.
    이런 마커들은 사용자에게 보여서는 안 됨.
    """
    if not text:
        return text
    # <system-reminder>...</system-reminder> 태그 제거
    text = re.sub(r'<system-reminder>.*?</system-reminder>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # 불완전한 태그도 제거
    text = re.sub(r'</?system-reminder[^>]*>', '', text, flags=re.IGNORECASE)
    # [[마커]] 형식 제거 (APPROVAL_REQUESTED는 이미 처리됨)
    text = re.sub(r'\[\[QUESTION_PENDING\]\]', '', text)
    text = re.sub(r'\[\[PLAN_MODE_ENTERED\]\]', '', text)
    text = re.sub(r'\[\[PLAN_APPROVAL_REQUESTED\]\]', '', text)
    return text.strip()


def _process_documents(documents: list, message: str) -> str:
    """첨부된 문서 파일을 텍스트로 변환하여 메시지에 추가"""
    if not documents:
        return message
    try:
        from document_converter import convert_document
    except ImportError:
        return message

    doc_texts = []
    for doc in documents:
        file_path = doc.get("filePath", "")
        file_name = doc.get("fileName", "")
        if not file_path:
            continue
        result = convert_document(file_path)
        if result.get("text"):
            doc_texts.append(
                f"\n\n--- 첨부 문서: {file_name} (원본 경로: {file_path}) ---\n"
                f"{result['text']}"
            )
        elif result.get("error"):
            doc_texts.append(
                f"\n\n--- 첨부 문서: {file_name} (변환 실패: {result['error']}) ---"
            )
    if doc_texts:
        message = message + "".join(doc_texts)
    return message


# 도구 이벤트 → 표면 페이로드. 에이전트·시스템AI 양단이 **같은 이름·같은 필드**로 나른다.
# ★손으로 다시 짓지 않는다(2026-09-02 수리): 옛 코드는 두 곳에서 각각
# {type, name, result, agent} 만 골라 담아 프로바이더가 실어 보낸 두 필드를 떨어뜨렸다 —
#   · is_error : 그 호출이 성공했나 실패했나 (표면의 유일한 판정 근거)
#   · id       : 병렬 호출의 start↔result 페어링 키(anthropic.py 가 '유일한 정답'이라 적어 둔 것)
# 그래서 표면은 실패한 도구도 초록 체크로 그렸고, 병렬 호출은 이름으로 짝을 찾다 엇갈렸다.
# 방출부(providers/*)도 이벤트 타입(tool_start/tool_result)도 멀쩡했고, 내부 소비자
# (agent_pipeline._collect)는 같은 두 필드를 이미 쓰고 있었다 — 끊긴 고리는 이 transport 하나였다.
# images 는 일부러 뺀다: base64 라 WS 로 두 번 흐르면 무겁고, 최종 메시지에 이미 실린다.
_TOOL_EVENT_FIELDS = ("id", "name", "input", "result")


def tool_event_payload(event: dict, agent: str) -> dict:
    """프로바이더 도구 이벤트를 표면 계약 그대로 옮긴다 (tool_start/tool_result 공용)."""
    payload = {"type": event.get("type"), "agent": agent}
    for key in _TOOL_EVENT_FIELDS:
        value = event.get(key)
        if value is not None:
            payload[key] = value
    payload.setdefault("name", "unknown")
    if payload["type"] == "tool_result":
        # 판정은 언제나 실린다 — 없으면 '성공'이 아니라 '미표명'이 되어 옛 병이 되살아난다.
        payload["is_error"] = bool(event.get("is_error", False))
    return payload


def is_cancelled(client_id: str) -> bool:
    """클라이언트의 중단 요청 여부 확인"""
    return cancel_flags.get(client_id, False)


def set_cancel(client_id: str, value: bool):
    """클라이언트의 중단 플래그 설정"""
    cancel_flags[client_id] = value


def get_agent_runners():
    from agent_registry import get_agent_runners as _get
    return _get()


def _ensure_agent_runner(project_id: str, agent_id: str, agent_config: dict, agents_data: dict):
    """등기부에 살아있는 러너가 없으면 그 자리에서 시작해 등록한다 (멱등).

    등기부(agent_runners)는 메모리뿐이라 uvicorn reload·keeper 재기동마다 통째로
    비워진다 — 옛 동작은 그때 '실행 중이 아닙니다' 오류를 돌려줘, 화면이 낡은
    '실행 중' 표시를 믿는 동안 대화가 막혔다(2026-08-10 진단: 유휴 후 복귀 증상의
    진범). 스케줄러(calendar_actions._ensure_agent_running)·시스템 AI가 이미 같은
    자동 시작을 하므로, 채팅 수신도 같은 계약으로 맞춘다. 반환: runner_info | None.
    """
    from datetime import datetime
    from agent_runner import AgentRunner

    agent_runners = get_agent_runners()
    info = (agent_runners.get(project_id) or {}).get(agent_id)
    runner = info.get("runner") if info else None
    if runner and runner.running and runner.ai:
        return info

    try:
        project_path = project_manager.get_project_path(project_id)
        # 원본 config 를 오염시키지 않도록 사본에 경로를 심는다 (start 엔드포인트와 동일 계약)
        cfg = dict(agent_config)
        cfg["_project_path"] = str(project_path)
        cfg["_project_id"] = project_id
        new_runner = AgentRunner(cfg, agents_data.get("common", {}) or {})
        new_runner.start()
        agent_runners.setdefault(project_id, {})[agent_id] = {
            "runner": new_runner,
            "config": cfg,
            "running": True,
            "started_at": datetime.now().isoformat(),
        }
        print(f"[에이전트 자동 시작] {cfg.get('name', agent_id)} (채팅 수신 시 등기부 부재 — 재기동 후 복구)")
        return agent_runners[project_id][agent_id]
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[에이전트 자동 시작 실패] {project_id}/{agent_id}: {e}")
        return None


async def _bail_stream(client_id: str, msg: str):
    """스트림 핸들러 이른-return 공통 마무리 (2026-08-10, 고아 에피소드 수리).

    옛 이른-return 들은 end_episode 없이 빠져나가 에피소드가 원장에 START 만 있는
    고아로 남았다(같은 컨텍스트의 다음 메시지가 salvage — 최근 200건 중 12건).
    사유를 print(에피소드 버퍼에 기록)하고 에피소드를 닫은 뒤 오류를 보낸다.
    """
    print(f"[WS stream 중단] {msg}")
    try:
        from episode_logger import EpisodeLogger
        EpisodeLogger.end_episode()
    except Exception:
        pass
    await manager.send_message(client_id, {"type": "error", "message": msg})


def init_manager(pm):
    global project_manager
    project_manager = pm


# ============ Launcher WebSocket ============
# 상태·송신(send_launcher_command 등)은 websocket_manager(데이터층 허브)로 이동 —
# 아래층(ibl_routing·notify_dispatch 등)이 라우터를 import 하지 않게 (2026-08-05 ⑦).
from websocket_manager import (  # noqa: E402
    set_launcher_ws, clear_launcher_ws,
)


@router.websocket("/ws/launcher")
async def websocket_launcher(websocket: WebSocket):
    """런처 전용 WebSocket — 백엔드→런처 명령 전달 채널"""
    await websocket.accept()
    set_launcher_ws(websocket, asyncio.get_running_loop())
    print("[WS] Launcher 연결됨")

    try:
        while True:
            # Launcher→백엔드 메시지 (ping/ack 등)
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except (WebSocketDisconnect, Exception):
        clear_launcher_ws()
        print("[WS] Launcher 연결 해제")


# ============ WebSocket 채팅 ============

@router.websocket("/ws/chat/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str):
    """채팅 WebSocket 엔드포인트"""
    print(f"[WS] 연결: {client_id}")
    await manager.connect(websocket, client_id)

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type", "chat")

            if message_type == "chat":
                await handle_chat_message(client_id, data)
            elif message_type == "chat_stream":
                # (2026-08-15 조향 확장) 에이전트 스트림도 태스크로 — 시스템 AI 와 동일
                # 원리. 실행 중 같은 에이전트로 온 메시지 = 조향, 다른 에이전트 = 정직
                # 거절(같은 client 의 이벤트 스트림을 두 턴이 나눠 쓰는 혼선 방지).
                # 신원 안전 근거: run_stream 이 워커 스레드 안에서 클로저 변수로 신원을
                # 재설정하므로("별도 스레드이므로 컨텍스트 재설정") 태스크 교차와 무관.
                _prev_task = _stream_tasks.get(client_id)
                if _prev_task is not None and not _prev_task.done():
                    _key, _running_name = _stream_agent_keys.get(client_id, (None, None))
                    _target = data.get("agent_name", "")
                    if _key and _target in (_running_name, _key):
                        from steer_inbox import post as _steer_post
                        _pending = _steer_post(_key, data.get("message", ""))
                        await manager.send_message(client_id, {
                            "type": "steer_accepted",
                            "message": f"⤳ 조향 접수 — 다음 도구 완료 시 반영됩니다 (대기 {_pending}건)",
                        })
                    else:
                        await manager.send_message(client_id, {
                            "type": "steer_accepted",
                            "message": f"⚠ '{_running_name or '다른 작업'}' 실행 중 — 끝난 뒤 보내주세요",
                        })
                else:
                    _t = asyncio.create_task(handle_chat_message_stream(client_id, data))
                    _stream_tasks[client_id] = _t
                    _t.add_done_callback(lambda t: t.cancelled() or (
                        t.exception() and print(f"[WS] 에이전트 스트림 태스크 예외: {t.exception()}")))
            elif message_type == "system_ai_stream":
                # (2026-08-15 조향) 스트림을 태스크로 띄워 수신 루프를 비워 둔다 — 이전엔
                # await 가 루프를 막아 스트림 중 cancel·추가 메시지가 턴 종료까지 WS 버퍼에
                # 잠들었다(중단 버튼도 실은 스트림 중 무효였던 구조). 실행 중 도착한
                # system_ai_stream 은 새 턴이 아니라 **조향(steer)** 으로 접수된다 —
                # 같은 채팅창이 곧 조향 입력창(steer_inbox → 다음 도구 결과에 부록 배달).
                _prev_task = _stream_tasks.get(client_id)
                if _prev_task is not None and not _prev_task.done():
                    from steer_inbox import post as _steer_post
                    _pending = _steer_post("system_ai", data.get("message", ""))
                    await manager.send_message(client_id, {
                        "type": "steer_accepted",
                        "message": f"⤳ 조향 접수 — 다음 도구 완료 시 반영됩니다 (대기 {_pending}건)",
                    })
                else:
                    _t = asyncio.create_task(handle_system_ai_chat_stream(client_id, data))
                    _stream_tasks[client_id] = _t
                    _stream_agent_keys[client_id] = ("system_ai", None)
                    _t.add_done_callback(lambda t: t.cancelled() or (
                        t.exception() and print(f"[WS] 시스템AI 스트림 태스크 예외: {t.exception()}")))
            elif message_type == "cancel":
                # 중단 요청 처리
                set_cancel(client_id, True)
                print(f"[WS] 중단 요청: {client_id}")
                await manager.send_message(client_id, {"type": "cancelled"})
            elif message_type == "ping":
                await manager.send_message(client_id, {"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(client_id)
        print(f"[WS] 정상 연결 해제: {client_id}")
    except Exception as e:
        error_msg = str(e)
        # 연결 관련 에러인 경우에만 disconnect
        if "closed" in error_msg.lower() or "disconnect" in error_msg.lower() or "connection" in error_msg.lower():
            print(f"[WS] 연결 에러로 해제: {client_id} - {e}")
            manager.disconnect(client_id)
        else:
            # 일시적 에러는 로그만 남기고 루프 계속 (연결 유지)
            print(f"[WS 에러] {client_id}: {e} (연결 유지 시도)")
            # 하지만 여기서는 while 루프가 끝나므로 결국 연결 해제됨
            manager.disconnect(client_id)
    finally:
        # 조향 태스크 레지스트리 정리 — 스트림 태스크 자체는 계속 돌게 둔다(백그라운드
        # 완주가 기존 계약: 타임아웃 후에도 작업은 완료되어 대화 저장·재접속 회수).
        _stream_tasks.pop(client_id, None)
        _stream_agent_keys.pop(client_id, None)


async def handle_chat_message(client_id: str, data: dict):
    """채팅 메시지 처리 (기존 동기 방식)"""
    message = data.get("message", "")
    agent_name = data.get("agent_name", "")
    project_id = data.get("project_id", "")
    images = data.get("images", [])
    action_hint = data.get("action_hint")  # 마법책 선택 액션 (예: "sense:price")
    message = await asyncio.to_thread(_process_documents, data.get("documents", []), message)  # 문서 변환(textutil 등)은 스레드로

    try:
        # 시작 알림
        await manager.send_message(client_id, {
            "type": "start",
            "agent": agent_name
        })

        project_path = project_manager.get_project_path(project_id)

        # 에이전트 설정 로드
        agents_file = project_path / "agents.yaml"
        if not agents_file.exists():
            await _bail_stream(client_id, f"에이전트 설정을 찾을 수 없습니다. (project={project_id})")
            return

        with open(agents_file, 'r', encoding='utf-8') as f:
            agents_data = yaml.safe_load(f)

        # 에이전트 찾기
        agent_config = None
        agent_id = None
        for agent in agents_data.get("agents", []):
            if agent.get("name") == agent_name:
                agent_config = agent
                agent_id = agent.get("id")
                break

        if not agent_config:
            await _bail_stream(client_id, f"에이전트 '{agent_name}'을(를) 찾을 수 없습니다. (project={project_id})")
            return

        # 실행 중인 AgentRunner 확인 — 등기부에 없으면 자동 시작 (재기동으로 비워진 등기부 복구)
        runner_info = _ensure_agent_runner(project_id, agent_id, agent_config, agents_data)
        if not runner_info:
            await _bail_stream(client_id, f"에이전트 '{agent_name}' 시작에 실패했습니다. 백엔드 로그를 확인해주세요.")
            return

        runner = runner_info.get("runner")

        if not runner or not runner.ai:
            await _bail_stream(client_id, f"에이전트 '{agent_name}'의 AI가 준비되지 않았습니다.")
            return

        # 스레드 컨텍스트 설정 (call_agent 등에서 발신자 정보로 사용)
        from thread_context import set_current_agent_id, set_current_agent_name, set_current_project_id, set_user_input
        set_current_agent_id(agent_id)
        set_current_agent_name(agent_name)
        set_current_project_id(project_id)
        set_user_input(message)

        # 대화 DB
        db = ConversationDB(str(project_path / "conversations.db"))

        # 사용자 및 에이전트 ID
        user_id = db.get_or_create_agent("user", "human")
        target_agent_id = db.get_or_create_agent(agent_name, "ai_agent")

        # 히스토리 로드
        history = db.get_history_for_ai(target_agent_id, user_id)

        # 사용자 메시지 저장 (이미지 포함)
        db.save_message(user_id, target_agent_id, message, images=images if images else None)

        # 태스크 생성
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        try:
            db.create_task(
                task_id=task_id,
                requester="user@gui",
                requester_channel="gui",
                original_request=message,
                delegated_to=agent_name,
                ws_client_id=client_id
            )
        except Exception as e:
            print(f"[WS] 태스크 생성 실패: {e}")

        # 스레드 컨텍스트에 task_id 설정 (call_agent에서 사용)
        from thread_context import set_current_task_id
        set_current_task_id(task_id)

        # ★ LLM 파이프라인(의식+실행)을 워커 스레드로 오프로드한다 — 이벤트 루프를
        # 막지 않기 위해. 동기 블로킹(process_message_with_history)을 async 핸들러에서
        # 직접 부르면 루프가 막혀, claude_code(아웃오브프로세스)가 MCP→HTTP 로 같은
        # 백엔드 /ibl/execute 로 재진입할 때 처리되지 못하는 자기 데드락이 난다(시스템 AI
        # 채팅 bug1과 동일 부류). 스트리밍 핸들러(handle_chat_message_stream/system_ai)는
        # 이미 executor.submit(run_stream) 으로 이 패턴을 쓴다 — 비스트리밍 경로도 합류.
        # thread_context 는 threading.local 이라 워커 스레드 안에서 재설정한다(run_stream 미러).
        loop = asyncio.get_running_loop()

        def _work():
            """워커 스레드 — 인지 파이프라인 제너레이터를 drain하는 블로킹 어댑터.

            반성·평가·SESSION_RESET 등 파이프라인 기능을 스트림 경로와 자동 공유(Task B).
            """
            from thread_context import (set_current_agent_id as _sa, set_current_agent_name as _sn,
                                        set_current_project_id as _sp, set_current_task_id as _st,
                                        set_user_input as _su, set_task_origin as _so,
                                        clear_all_context as _clear)
            from agent_pipeline import drain_stream
            _sa(agent_id); _sn(agent_name); _sp(project_id); _st(task_id); _su(message)
            _so("user")  # 채팅창 = 사람의 직접 명령 (RED 수리 그랜트 전제조건)
            try:
                result = drain_stream(runner.cognitive_stream(
                    message, history,
                    images=images, action_hint=action_hint, agent_name=agent_name,
                ))
                if result.get("clarify"):
                    print(f"[의식] clarification fast-path (non-stream): 실행 에이전트 스킵")
                    return {"clarify": result["final"]}
                response = result["final"]
                if not response and result.get("error"):
                    response = f"AI 응답 생성 실패: {result['error']}"
                tool_images = runner.ai.get_last_tool_images()
                return {"response": response, "tool_images": tool_images}
            finally:
                _clear()

        # 에피소드 contextvar 를 워커로 전파(스트림 경로의 copy_context 선례 합류) —
        # run_in_executor 는 컨텍스트를 복사하지 않아, 이 줄이 없으면 워커의 IBL 실행이
        # episode 없는 고아 run 으로 남는다(2026-08-29 척추 수리).
        result = await loop.run_in_executor(
            executor, contextvars.copy_context().run, _work)

        if result.get("clarify"):
            _clarify_text = result["clarify"]
            message_id = db.save_message(target_agent_id, user_id, _clarify_text)
            await manager.send_message(client_id, {
                "type": "response",
                "content": _clarify_text,
                "agent": agent_name,
                "message_id": message_id,
            })
            await manager.send_message(client_id, {
                "type": "end",
                "agent": agent_name,
            })
            return

        # AI 응답 저장 (도구 결과 이미지 포함)
        response = result["response"]
        tool_images = result.get("tool_images")
        message_id = db.save_message(target_agent_id, user_id, response, images=tool_images)

        # 응답 전송
        await manager.send_message(client_id, {
            "type": "response",
            "content": response,
            "agent": agent_name,
            "message_id": message_id
        })

        # 완료 알림
        await manager.send_message(client_id, {
            "type": "end",
            "agent": agent_name
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        # 컨텍스트 정리
        from thread_context import clear_all_context
        clear_all_context()
        await manager.send_message(client_id, {
            "type": "error",
            "message": str(e)
        })


async def handle_chat_message_stream(client_id: str, data: dict):
    """채팅 메시지 처리 (스트리밍 방식)"""
    message = data.get("message", "")
    agent_name = data.get("agent_name", "")
    project_id = data.get("project_id", "")
    images = data.get("images", [])
    action_hint = data.get("action_hint")  # 마법책 선택 액션 (예: "sense:price")
    message = await asyncio.to_thread(_process_documents, data.get("documents", []), message)  # 문서 변환(textutil 등)은 스레드로

    # 태스크 id 는 에피소드보다 먼저 정한다 — 이벤트 루프 한 스레드에서 여러 턴이 동시에
    # 열리므로 thread-local 상속은 이웃 턴의 태스크를 물려받는다(2026-09-06 ep2905 → 명시 바인딩).
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    # 에피소드 로그 시작 (project_id 전달 — 종료 시 조종실 액티브 유령 청소용)
    try:
        from episode_logger import EpisodeLogger
        EpisodeLogger.start_episode(agent_name, message, project_id=project_id, task_id=task_id)
    except Exception:
        pass

    try:
        # 시작 알림
        await manager.send_message(client_id, {
            "type": "start",
            "agent": agent_name
        })

        project_path = project_manager.get_project_path(project_id)

        # 에이전트 설정 로드
        agents_file = project_path / "agents.yaml"
        if not agents_file.exists():
            await _bail_stream(client_id, f"에이전트 설정을 찾을 수 없습니다. (project={project_id})")
            return

        with open(agents_file, 'r', encoding='utf-8') as f:
            agents_data = yaml.safe_load(f)

        # 에이전트 찾기 (이름 또는 ID로)
        agent_config = None
        agent_id = None
        for agent in agents_data.get("agents", []):
            if agent.get("name") == agent_name or agent.get("id") == agent_name:
                agent_config = agent
                agent_id = agent.get("id")
                # agent_name이 ID였다면 실제 이름으로 교체
                agent_name = agent.get("name", agent_name)
                break

        if not agent_config:
            await _bail_stream(client_id, f"에이전트 '{agent_name}'을(를) 찾을 수 없습니다. (project={project_id})")
            return

        # 조향 키 등록 (2026-08-15) — provider.agent_id 와 같은 값(yaml id)이어야
        # execute_tool 의 drain 과 만난다. 수신 루프의 조향 분기가 이 등록을 읽는다.
        _stream_agent_keys[client_id] = (agent_id or agent_name, agent_name)
        # 턴 취소 플래그 리셋 (sysai 핸들러와 동일 계약 — 직전 턴의 중단이 새 턴을 즉사시키지 않게)
        set_cancel(client_id, False)

        # 실행 중인 AgentRunner 확인 — 등기부에 없으면 자동 시작 (재기동으로 비워진 등기부 복구)
        runner_info = _ensure_agent_runner(project_id, agent_id, agent_config, agents_data)
        if not runner_info:
            await _bail_stream(client_id, f"에이전트 '{agent_name}' 시작에 실패했습니다. 백엔드 로그를 확인해주세요.")
            return

        runner = runner_info.get("runner")

        if not runner or not runner.ai:
            await _bail_stream(client_id, f"에이전트 '{agent_name}'의 AI가 준비되지 않았습니다.")
            return

        # 스레드 컨텍스트 설정
        from thread_context import set_current_agent_id, set_current_agent_name, set_current_project_id, set_current_task_id
        set_current_agent_id(agent_id)
        set_current_agent_name(agent_name)
        set_current_project_id(project_id)

        # 대화 DB
        db = ConversationDB(str(project_path / "conversations.db"))

        # 사용자 및 에이전트 ID
        user_id = db.get_or_create_agent("user", "human")
        target_agent_id = db.get_or_create_agent(agent_name, "ai_agent")

        # 히스토리 로드
        history = db.get_history_for_ai(target_agent_id, user_id)

        # 사용자 메시지 저장 (이미지 포함)
        db.save_message(user_id, target_agent_id, message, images=images if images else None)

        # 태스크 생성 (id 는 에피소드 시작 전에 정했다 — 명시 바인딩)
        try:
            db.create_task(
                task_id=task_id,
                requester="user@gui",
                requester_channel="gui",
                original_request=message,
                delegated_to=agent_name,
                ws_client_id=client_id
            )
        except Exception as e:
            print(f"[WS] 태스크 생성 실패: {e}")

        set_current_task_id(task_id)

        # 스트리밍 처리를 위한 큐
        event_queue = asyncio.Queue()
        final_content = ""
        timed_out = False  # 타임아웃 발생 여부 (워커 스레드에서 확인)
        loop = asyncio.get_running_loop()

        tool_calls_log = []  # X-Ray/태스크 이력용 — 제너레이터 _turn_meta에서 수신

        def _complete_task_row(final_text: str):
            """태스크 행을 completed 로 닫고 X-Ray 이벤트를 민다.

            정상 종료와 '타임아웃 후 워커 완주' 두 자리가 같은 마무리를 쓰도록 한 곳에
            둔다 — 옛 판은 소비자 쪽에만 있어서, 타임아웃이 나면 살아 있는 워커 위에
            *부분* 결과로 completed 를 찍었다.
            """
            if not task_id:
                return
            try:
                import json as _json
                tool_history_json = _json.dumps(tool_calls_log, ensure_ascii=False) if tool_calls_log else None
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    try:
                        cursor.execute("ALTER TABLE tasks ADD COLUMN tool_history TEXT")
                    except Exception:
                        pass
                    cursor.execute("""
                        UPDATE tasks SET status = 'completed', result = ?,
                                         completed_at = CURRENT_TIMESTAMP, tool_history = ?
                        WHERE task_id = ?
                    """, ((final_text or "")[:500], tool_history_json, task_id))
                    conn.commit()
                # X-Ray 실시간 이벤트
                try:
                    from xray_stream import push_xray_event
                    push_xray_event("task_complete", {
                        "task_id": task_id,
                        "request": (message or "")[:100],
                        "agent": agent_name,
                        "tool_count": len(tool_calls_log),
                    })
                except Exception:
                    pass
            except Exception as ct_err:
                print(f"[WS] complete_task 실패 (무시): {ct_err}")

        def run_stream():
            """워커 스레드 — 인지 파이프라인 제너레이터를 소비해 이벤트를 pump (transport 어댑터).

            인지 오케스트레이션(연상→분류→의식→실행→평가→반성→증류)은 전부
            runner.cognitive_stream(agent_pipeline.py) 안에서 일어난다.
            """
            nonlocal final_content
            # 별도 스레드이므로 컨텍스트 재설정 필요
            from thread_context import set_user_input as _set_user_input, set_task_origin as _set_origin
            set_current_agent_id(agent_id)
            set_current_agent_name(agent_name)
            set_current_project_id(project_id)
            set_current_task_id(task_id)
            _set_user_input(message)
            _set_origin("user")  # 채팅창 = 사람의 직접 명령 (RED 수리 그랜트 전제조건)
            # 텍스트 청크 합산 — 청크마다 로그를 찍지 않고 종료 한 줄에 총량만 싣는다.
            _text_chunks = _text_chars = 0

            try:
                # (2026-08-15 4라운드 감사) cancel_check 배선 — 이전엔 이 경로만 None 이라
                # 중단이 도는 턴의 도구 루프에 원리적으로 닿지 않았다(UI 만 멈춘 척).
                # ★runner.cancel_event 재사용 금지: 그건 상주 폴링 루프 전체를 끝내는
                # 신호(에이전트 정지)라 턴 취소로 쓰면 다음 턴 즉사+폴링 사망.
                for event in runner.cognitive_stream(
                    message, history,
                    images=images, action_hint=action_hint, agent_name=agent_name,
                    cancel_check=lambda: is_cancelled(client_id),
                ):
                    # 중단 즉시 탈출 (5라운드 감사 (A) — sysai 워커와 대칭): cancel_check 는
                    # 도구 경계에서만 잡히므로, 긴 텍스트 스트리밍 중에도 여기서 끊는다.
                    if is_cancelled(client_id):
                        asyncio.run_coroutine_threadsafe(
                            event_queue.put({"type": "cancelled", "content": "사용자가 중단했습니다."}),
                            loop)
                        break
                    event_type = event.get("type", "unknown")
                    if event_type == "_turn_meta":
                        # 내부 메타 — 클라이언트 미전달, 도구 이력만 회수
                        tool_calls_log.extend(event.get("tool_calls") or [])
                        continue
                    # tool_start/tool_result/thinking은 provider에서 이미 print되므로 중복 제거.
                    if event_type == "error":
                        print(f"[WS run_stream] error: {event.get('content', '')[:300]}")
                    elif event_type == "text":
                        # ★청크마다 찍지 않는다(2026-08-25): 청크 크기는 프로바이더가 정한다
                        # — in-process DeepSeek 은 1~5자씩 흘려보내 한 턴이 수백 줄이 됐다
                        # (실측: backend_runtime.log 62,670줄 중 6,016줄=9.6%가 이 한 줄에서
                        # 나왔고 그동안 실제 턴은 20여 회였다). 진단에 쓰이는 건 청크마다의
                        # 길이가 아니라 총량이므로 합산해 스트림 종료 한 줄에 싣는다.
                        _text_chunks += 1
                        _text_chars += len(str(event.get("content", "")))
                    elif event_type not in ("tool_start", "tool_result", "thinking", "final", "cognition"):
                        print(f"[WS run_stream] 이벤트 수신: {event_type}")
                    asyncio.run_coroutine_threadsafe(
                        event_queue.put(event),
                        loop
                    )
                    if event_type == "final":
                        final_content = event.get("content", "")
                        print(f"[WS run_stream] final_content 설정됨 (len={len(final_content)})")
            except Exception as e:
                print(f"[WS run_stream] 예외 발생: {e}")
                asyncio.run_coroutine_threadsafe(
                    event_queue.put({"type": "error", "content": str(e)}),
                    loop
                )
            finally:
                print(f"[WS run_stream] 스트림 종료, final_content len={len(final_content)}, "
                      f"text {_text_chars}자/{_text_chunks}청크, timed_out={timed_out}")
                if timed_out:
                    # 타임아웃 이후 완주분 인계 — 소비자는 이미 떠났으므로 저장·태스크
                    # 닫기·원장 닫기를 실제로 끝낸 여기서 한다(시스템 AI 경로와 대칭).
                    if final_content:
                        try:
                            filtered = filter_internal_markers(final_content)
                            msg_id = db.save_message_undelivered(target_agent_id, user_id, filtered)
                            print(f"[WS run_stream] 타임아웃 후 미전달 메시지 저장 완료: message_id={msg_id}")
                        except Exception as save_err:
                            print(f"[WS run_stream] 타임아웃 후 메시지 저장 실패: {save_err}")
                    _complete_task_row(final_content)
                    try:
                        from episode_logger import EpisodeLogger
                        EpisodeLogger.end_episode()
                    except Exception:
                        pass
                    try:
                        from thread_context import clear_all_context as _cac
                        _cac()
                    except Exception:
                        pass
                asyncio.run_coroutine_threadsafe(
                    event_queue.put(None),  # 종료 신호
                    loop
                )

        # 별도 스레드에서 스트리밍 시작
        # 현재 컨텍스트(에피소드 contextvar 포함)를 복사해 executor 스레드로 전파 —
        # run_stream 의 로그가 이 요청의 에피소드 버퍼로 모인다(동시 실행 격리). 에피소드가
        # 없으면 None 컨텍스트라 무해.
        executor.submit(contextvars.copy_context().run, run_stream)

        # 이벤트 수신 및 클라이언트 전송
        # 영상 제작 등 오래 걸리는 작업을 위해 타임아웃을 10분으로 설정
        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=600)
            except asyncio.TimeoutError:
                timed_out = True
                print(f"[WS] 에이전트 타임아웃 발생 (600초), final_content 길이: {len(final_content)}")
                await manager.send_message(client_id, {
                    "type": "error",
                    "message": "응답 시간 초과 (10분). 작업은 계속 진행 중이며, "
                               "끝나면 미전달 메시지로 저장됩니다."
                })
                # 뒷정리는 하지 않는다 — 워커가 살아 있다(시스템 AI 경로와 같은 부류의
                # 고아 실행 수리, 2026-08-22). 저장·태스크 닫기·Episode END 는 워커의
                # finally 가 완주 시점에 한다. thread_context 만 이 스레드 몫으로 비운다
                # (threading.local — 워커가 비워도 루프 스레드 것은 안 지워진다).
                from thread_context import clear_all_context as _cac_loop
                _cac_loop()
                return

            if event is None:
                break

            event_type = event.get("type")

            if event_type == "cancelled":
                # 중단 확인 전송 후 즉시 종료 (sysai 소비자와 대칭)
                await manager.send_message(client_id, {
                    "type": "cancelled",
                    "message": event.get("content", "중단됨"),
                })
                break

            if event_type == "text":
                # 텍스트 청크 전송
                await manager.send_message(client_id, {
                    "type": "stream_chunk",
                    "content": event.get("content", ""),
                    "agent": agent_name
                })

            elif event_type == "tool_start":
                # 도구 시작 알림 (input 포함 — 시스템AI 경로와 같은 계약)
                await manager.send_message(client_id, tool_event_payload(event, agent_name))

            elif event_type == "tool_result":
                # 도구 결과 알림 (id·is_error 포함 — 표면이 성공/실패를 구별하고 병렬 호출을 짝짓는다)
                message_data = tool_event_payload(event, agent_name)
                tool_name = message_data["name"]
                tool_input = event.get("input") or {}

                # todo_write 도구인 경우 TODO 데이터 추가
                # Phase 17: execute_ibl 경유 시 params에서 추출
                if tool_name == "todo_write":
                    todos = tool_input.get("todos", [])
                    if todos:
                        message_data["todos"] = todos
                elif tool_name == "execute_ibl":
                    # Phase 17: execute_ibl 경유 시 params 또는 result에서 추출
                    _ibl_params = tool_input.get("params", {})
                    _ibl_todos = _ibl_params.get("todos", [])

                    # 입력에 없으면 결과에서 추출 시도 (JSON 문자열인 경우)
                    if not _ibl_todos:
                        _res = message_data.get("result", "")
                        if isinstance(_res, str) and _res.startswith("{"):
                            try:
                                import json
                                _res_data = json.loads(_res)
                                if isinstance(_res_data, dict):
                                    # 1) 단일 step 결과인 경우
                                    if _res_data.get("_ibl_user_action") == "todo_write":
                                        _ibl_todos = _res_data.get("todos", [])
                                    # 2) 파이프라인 결과인 경우 (final_result 확인)
                                    elif "final_result" in _res_data:
                                        _final = _res_data["final_result"]
                                        if isinstance(_final, str) and _final.startswith("{"):
                                            _final_data = json.loads(_final)
                                            if isinstance(_final_data, dict) and _final_data.get("_ibl_user_action") == "todo_write":
                                                _ibl_todos = _final_data.get("todos", [])
                            except:
                                pass

                    if _ibl_todos:
                        message_data["todos"] = _ibl_todos
                        message_data["name"] = "todo_write"

                await manager.send_message(client_id, message_data)

            elif event_type == "thinking":
                # AI 사고 과정 알림
                await manager.send_message(client_id, {
                    "type": "thinking",
                    "content": event.get("content", ""),
                    "agent": agent_name
                })

            elif event_type == "cognition":
                # 자율주행 작업전 공개(계기판) — 실행 직전 판단/확신/연상 노출
                await manager.send_message(client_id, {**event, "agent": agent_name})

            elif event_type == "final":
                final_content = event.get("content", "")
                print(f"[WS while루프] final 이벤트 수신 (len={len(final_content)})")

            elif event_type == "error":
                await manager.send_message(client_id, {
                    "type": "error",
                    "message": event.get("content", "알 수 없는 오류")
                })
                break

        # 취소 플래그 턴-종료 리셋 (5라운드 감사 (D) — 남은 True 가 같은 client_id 의
        # 다른 경로/다음 소비에 새지 않게. 시작 리셋과 양단 대칭.)
        set_cancel(client_id, False)

        # AI 응답 저장 (final_content 사용)
        print(f"[WS] while 루프 종료, final_content 길이: {len(final_content)}")
        if final_content:
            # 내부 시스템 마커 필터링
            final_content = filter_internal_markers(final_content)
            # 도구 결과 이미지 수집하여 저장
            tool_images = runner.ai.get_last_tool_images()
            message_id = db.save_message(target_agent_id, user_id, final_content, images=tool_images)

            # 최종 응답 전송
            await manager.send_message(client_id, {
                "type": "response",
                "content": final_content,
                "agent": agent_name,
                "message_id": message_id
            })

        # 태스크 완료 처리 (X-Ray 타임라인용)
        # tool_calls_log는 run_stream 스레드에서 수집됨 — thread_context가 아닌 이 변수를 직접 사용
        _complete_task_row(final_content)

        # 완료 알림
        await manager.send_message(client_id, {
            "type": "end",
            "agent": agent_name
        })

        # 에피소드 로그 종료
        try:
            from episode_logger import EpisodeLogger
            EpisodeLogger.end_episode()
        except Exception:
            pass

        # 컨텍스트 정리
        from thread_context import clear_all_context
        clear_all_context()

    except Exception as e:
        import traceback
        traceback.print_exc()
        # 에피소드 로그 종료 (에러 시에도)
        try:
            from episode_logger import EpisodeLogger
            EpisodeLogger.end_episode()
        except Exception:
            pass
        from thread_context import clear_all_context
        clear_all_context()
        await manager.send_message(client_id, {
            "type": "error",
            "message": str(e)
        })


# ============ 시스템 AI WebSocket 스트리밍 (통합 아키텍처) ============

async def handle_system_ai_chat_stream(client_id: str, data: dict):
    """시스템 AI 채팅 메시지 처리 (스트리밍 방식)

    **통합 아키텍처**: runner.cognitive_stream(agent_pipeline.py) 하나가 인지
    파이프라인 전체를 수행하고, 이 핸들러는 이벤트를 pump하는 transport 어댑터.
    """
    message = data.get("message", "")
    images = data.get("images", [])
    action_hint = data.get("action_hint")  # 마법책 선택 액션 (예: "sense:price")
    message = await asyncio.to_thread(_process_documents, data.get("documents", []), message)  # 문서 변환(textutil 등)은 스레드로

    # 앱메이커 표면 — 시스템 AI에 앱메이커 role(extra_role)을 씌우고 대화를 분리(source='appmaker').
    # forage_role 선례와 같은 방식. 전체 파이프라인 유지(force_role 없음 = 의식 프레이밍 1회 활용).
    is_appmaker = data.get("role") == "appmaker"
    conv_source = "appmaker" if is_appmaker else None
    conv_thread = "appmaker" if is_appmaker else "system_ai"
    extra_role = ""
    if is_appmaker:
        try:
            from pathlib import Path as _Path
            from runtime_utils import get_base_path
            _rp = _Path(get_base_path()) / "data" / "appmaker_role.txt"
            extra_role = _rp.read_text(encoding="utf-8") if _rp.exists() else ""
        except Exception:
            extra_role = ""

    # 태스크 id 는 에피소드보다 먼저 — 명시 바인딩(프로젝트 스트림 핸들러와 같은 이유, ep2905 실측
    # 주인공: 이 핸들러가 설계 에이전트의 진행 중 태스크를 물려받아 run 을 공유·조기 종료시켰다).
    task_id = f"task_sysai_{uuid.uuid4().hex[:8]}"
    # 에피소드 로그 시작
    try:
        from episode_logger import EpisodeLogger
        EpisodeLogger.start_episode("system_ai", message, task_id=task_id)
    except Exception:
        pass

    try:
        # 시작 알림
        await manager.send_message(client_id, {
            "type": "start",
            "agent": "system_ai"
        })

        # 시스템 AI 설정 및 헬퍼 함수 로드
        from api_system_ai import load_system_ai_config
        from system_ai_memory import (
            save_conversation,
            get_history_for_ai,
            create_task,
            delete_task,
            get_task
        )
        from thread_context import set_current_task_id, clear_all_context

        # 태스크 생성 (위임 기능에 필요 — id 는 에피소드 시작 전에 정했다)
        try:
            create_task(
                task_id=task_id,
                requester="user@gui",
                requester_channel="gui",
                original_request=message,
                delegated_to="system_ai",
                ws_client_id=client_id
            )
        except Exception as e:
            print(f"[WS] 시스템 AI 태스크 생성 실패: {e}")

        # 스레드 컨텍스트에 task_id 설정 (call_project_agent에서 사용)
        set_current_task_id(task_id)

        config = load_system_ai_config()
        api_key = config.get("apiKey", "")
        provider = config.get("provider", "anthropic")
        model = config.get("model", "claude-sonnet-4-20250514")

        # ★provider 를 보고 판정한다 — claude_code(중앙 OAuth)·ollama 는 키가 원래 없다.
        from model_resolver import provider_needs_api_key
        if not api_key and provider_needs_api_key(provider):
            await _bail_stream(client_id, f"API 키가 설정되지 않았습니다. ({provider})")
            return

        # 최근 대화 히스토리 로드 (조회 + 역할 매핑 + Observation Masking 통합)
        history = get_history_for_ai(limit=7, thread=conv_thread)

        # 사용자 메시지 저장 (이미지 포함)
        save_conversation("user", message, source=conv_source, images=images if images else None)

        # 스트리밍 처리 (AIAgent 사용)
        event_queue = asyncio.Queue()
        final_content = ""
        turn_budget = {}  # 턴 토큰·캐시 적중 — _turn_meta 에서 수신, end 이벤트에 동봉(고정물이 읽음)
        tool_results_list = []  # 도구 실행 결과 기록용
        collected_tool_images = []  # 도구 결과 이미지 수집
        timed_out = False  # 타임아웃 발생 여부 (워커 스레드에서 확인)
        loop = asyncio.get_running_loop()

        # 중단 플래그 초기화
        set_cancel(client_id, False)

        def run_stream():
            """워커 스레드 — 시스템 AI 인지 파이프라인 제너레이터를 pump (transport 어댑터).

            인지 오케스트레이션(연상→분류→의식→실행→평가→반성→증류)은 전부
            runner.cognitive_stream(agent_pipeline.py) 안에서 일어난다 — 프로젝트
            경로(#handle_chat_message_stream)와 같은 드라이버, _is_system_ai 플래그 분기.
            """
            nonlocal final_content
            # 스레드별로 컨텍스트를 다시 설정해야 함 (thread-local storage)
            set_current_task_id(task_id)
            from thread_context import set_task_origin as _set_origin
            _set_origin("user")  # 시스템 AI 채팅창 = 사람의 직접 명령 (RED 수리 그랜트 전제조건)
            from system_ai_core import get_system_ai_runner
            runner = get_system_ai_runner()
            gen = runner.cognitive_stream(
                message, history,
                images=images if images else None,
                action_hint=action_hint,
                extra_role=extra_role,
                cancel_check=lambda: is_cancelled(client_id),
            )
            try:
                for event in gen:
                    # 중단 요청 시 루프 탈출 (gen.close()가 제너레이터 뒷정리 실행)
                    if is_cancelled(client_id):
                        asyncio.run_coroutine_threadsafe(
                            event_queue.put({"type": "cancelled", "content": "사용자가 중단했습니다."}),
                            loop
                        )
                        break

                    event_type = event.get("type")
                    if event_type == "_turn_meta":
                        for _k in ("turn_tokens", "turn_cache_read"):
                            if event.get(_k) is not None:
                                turn_budget[_k] = event[_k]
                        continue  # 내부 메타 — 클라이언트 미전달(턴 예산만 회수)
                    if event_type == "tool_result" and event.get("images"):
                        collected_tool_images.extend(event["images"])

                    asyncio.run_coroutine_threadsafe(event_queue.put(event), loop)
                    if event_type == "final":
                        final_content = event.get("content", "")
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    event_queue.put({"type": "error", "content": str(e)}),
                    loop
                )
            finally:
                # 조기 종료(취소·예외)여도 제너레이터 finally(모델 복원·메모리 쓰기) 실행 보장
                gen.close()
                if timed_out:
                    # 타임아웃 이후 완주분 인계 — 소비자(WS)는 이미 떠났으므로 저장·
                    # 전송·원장 닫기를 실제로 끝낸 쪽인 여기서 한다.
                    if final_content:
                        try:
                            filtered = filter_internal_markers(final_content)
                            save_conversation("assistant", filtered, source=conv_source)
                            print(f"[WS run_stream] 시스템AI 타임아웃 후 대화 저장 완료")
                            # ★저장만 하면 사용자는 결과를 영영 못 본다 — 창이 다시
                            #  열려 있으면(재접속·다른 창) 밀어 준다. auto_report 는
                            #  프론트가 response 와 같은 자리에 그린다.
                            asyncio.run_coroutine_threadsafe(
                                manager.send_to_system_ai_chat({
                                    "type": "auto_report",
                                    "content": filtered,
                                    "agent": "system_ai",
                                }), loop)
                        except Exception as save_err:
                            print(f"[WS run_stream] 시스템AI 타임아웃 후 저장 실패: {save_err}")
                    # 태스크 정리 — 위임이 걸려 있으면 남긴다(결과를 기다리는 주인이 있다).
                    # 판정은 DB 의 pending_delegations 하나로 한다: 소비자가 모으던
                    # tool_results_list 는 타임아웃 시점에서 끊겨 반쪽이다.
                    try:
                        _td = get_task(task_id)
                        if _td and _td.get("pending_delegations", 0) > 0:
                            print(f"[WS run_stream] 위임 대기 중 — 태스크 유지: {task_id}")
                        else:
                            delete_task(task_id)
                            print(f"[WS run_stream] 시스템 AI 태스크 삭제(타임아웃 후 완주): {task_id}")
                    except Exception as _te:
                        print(f"[WS run_stream] 타임아웃 후 태스크 정리 실패: {_te}")
                    # 에피소드는 여기서 닫는다 — 소비자가 닫으면 원장의 total_ms 가
                    # 실제 종료가 아니라 타임아웃 시각이 된다(실측 24분41초 vs 실제 27분).
                    try:
                        from episode_logger import EpisodeLogger
                        EpisodeLogger.end_episode()
                    except Exception:
                        pass
                    try:
                        clear_all_context()
                    except Exception:
                        pass
                asyncio.run_coroutine_threadsafe(event_queue.put(None), loop)

        # 스레드에서 스트리밍 시작
        # 현재 컨텍스트(에피소드 contextvar 포함)를 복사해 executor 스레드로 전파 —
        # run_stream 의 로그가 이 요청의 에피소드 버퍼로 모인다(동시 실행 격리). 에피소드가
        # 없으면 None 컨텍스트라 무해.
        executor.submit(contextvars.copy_context().run, run_stream)

        # 이벤트 수신 및 클라이언트 전송
        # 영상 제작 등 오래 걸리는 작업을 위해 타임아웃을 10분으로 설정
        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=600)
            except asyncio.TimeoutError:
                timed_out = True
                print(f"[WS] 시스템AI 타임아웃 발생 (600초), final_content 길이: {len(final_content)}")
                await manager.send_message(client_id, {
                    "type": "error",
                    "message": "응답 시간 초과 (10분). 작업은 계속 진행 중이며, "
                               "끝나면 채팅창에 자동으로 표시됩니다."
                })
                # ★뒷정리를 여기서 하지 않는다 (2026-08-22 수리). 워커 스레드는 아직
                #  살아 있다 — 옛 판은 여기서 곧장 아래로 떨어져 부분 응답 저장 ·
                #  response/end 전송 · 태스크 삭제 · Episode END 를 전부 찍었고,
                #  그 뒤로도 워커가 3분간 보고서 파일을 계속 편집했다(고아 실행).
                #  게다가 워커의 finally 가 완성본을 또 저장해 대화가 이중 적재됐다.
                #  살아 있는 실행 위에 "끝남"을 찍지 않는다 — 뒷정리 전부를
                #  워커의 finally 한 곳으로 넘기고 여기서는 전송만 끝낸다.
                #  ★단 이벤트 루프 *스레드*의 thread_context 는 여기서 비운다 —
                #   thread_context 는 threading.local 이라 워커가 비워도 이 스레드
                #   것은 안 지워지고, 공유 루프 스레드에 task_id 가 남는다.
                clear_all_context()
                return

            if event is None:
                break

            # 중단된 경우
            if event.get("type") == "cancelled":
                await manager.send_message(client_id, {
                    "type": "cancelled",
                    "message": event.get("content", "중단됨")
                })
                break

            event_type = event.get("type")

            if event_type == "text":
                await manager.send_message(client_id, {
                    "type": "stream_chunk",
                    "content": event.get("content", ""),
                    "agent": "system_ai"
                })

            elif event_type == "tool_start":
                await manager.send_message(client_id, tool_event_payload(event, "system_ai"))

            elif event_type == "tool_result":
                message_data = tool_event_payload(event, "system_ai")
                tool_result = message_data.get("result", "")
                tool_name = message_data["name"]

                # 도구 결과 기록 (final이 비어있을 때 사용)
                # ★판정은 두 층이다: 프로바이더의 is_error(호출 자체가 죽음) ∪ 본문 휴리스틱
                # (호출은 성공했으나 IBL 봉투가 실패인 부류). 앞을 새로 얻었다고 뒤를 버리지 않는다.
                tool_results_list.append({
                    "name": tool_name,
                    "result": tool_result,
                    "has_error": bool(message_data.get("is_error"))
                                 or "error" in tool_result.lower()
                                 or '"success": false' in tool_result.lower()
                })

                tool_input = event.get("input") or {}

                # todo_write 도구인 경우 TODO 데이터 추가
                # Phase 17: execute_ibl 경유 시 params에서 추출
                if tool_name == "todo_write":
                    todos = tool_input.get("todos", [])
                    if todos:
                        message_data["todos"] = todos
                elif tool_name == "execute_ibl":
                    # Phase 17: execute_ibl 경유 시 params 또는 result에서 추출
                    _ibl_params = tool_input.get("params", {})
                    _ibl_todos = _ibl_params.get("todos", [])

                    # 입력에 없으면 결과에서 추출 시도 (JSON 문자열인 경우)
                    if not _ibl_todos:
                        _res = message_data.get("result", "")
                        if isinstance(_res, str) and _res.startswith("{"):
                            try:
                                import json
                                _res_data = json.loads(_res)
                                if isinstance(_res_data, dict):
                                    # 1) 단일 step 결과인 경우
                                    if _res_data.get("_ibl_user_action") == "todo_write":
                                        _ibl_todos = _res_data.get("todos", [])
                                    # 2) 파이프라인 결과인 경우 (final_result 확인)
                                    elif "final_result" in _res_data:
                                        _final = _res_data["final_result"]
                                        if isinstance(_final, str) and _final.startswith("{"):
                                            _final_data = json.loads(_final)
                                            if isinstance(_final_data, dict) and _final_data.get("_ibl_user_action") == "todo_write":
                                                _ibl_todos = _final_data.get("todos", [])
                            except:
                                pass

                    if _ibl_todos:
                        message_data["todos"] = _ibl_todos
                        message_data["name"] = "todo_write"

                await manager.send_message(client_id, message_data)

            elif event_type == "thinking":
                await manager.send_message(client_id, {
                    "type": "thinking",
                    "content": event.get("content", ""),
                    "agent": "system_ai"
                })

            elif event_type == "cognition":
                # 작업전 공개(계기판) — 실행 직전 판단/확신/연상 노출
                await manager.send_message(client_id, {**event, "agent": "system_ai"})

            elif event_type == "final":
                final_content = event.get("content", "")

            elif event_type == "error":
                await manager.send_message(client_id, {
                    "type": "error",
                    "message": event.get("content", "알 수 없는 오류")
                })
                break

        # 취소 플래그 턴-종료 리셋 (5라운드 감사 (D) — 에이전트 경로와 양단 대칭)
        set_cancel(client_id, False)

        # AI 응답 저장
        # final_content가 비어있으면 도구만 실행되고 텍스트 응답이 없는 경우
        # 도구 결과를 기반으로 유용한 메시지 제공
        if not final_content or final_content.strip() == "":
            if tool_results_list:
                # 에러가 있는지 확인
                errors = [r for r in tool_results_list if r.get("has_error")]
                if errors:
                    error_details = "\n".join([f"- {e['name']}: {e['result'][:200]}" for e in errors])
                    final_content = f"도구 실행 중 오류가 발생했습니다:\n\n{error_details}"
                else:
                    # 마지막 도구 결과 표시
                    last_result = tool_results_list[-1]
                    final_content = f"도구 '{last_result['name']}'이 실행되었지만 AI가 응답을 생성하지 않았습니다.\n\n도구 결과:\n{last_result['result'][:500]}"
            else:
                final_content = "(AI가 응답을 생성하지 않았습니다. 다시 시도해주세요.)"

        # 내부 시스템 마커 필터링
        final_content = filter_internal_markers(final_content)

        save_conversation("assistant", final_content, source=conv_source, images=collected_tool_images if collected_tool_images else None)

        await manager.send_message(client_id, {
            "type": "response",
            "content": final_content,
            "agent": "system_ai"
        })

        # 위임이 발생했는지 확인
        # 1) 도구 이름으로 직접 호출 감지
        # 2) execute_ibl 도구로 간접 호출 감지 (team:delegate_project 등)
        # 3) DB에서 pending_delegations > 0 확인 (가장 확실)
        delegated = any(r.get("name") == "call_project_agent" for r in tool_results_list)

        if not delegated:
            # IBL 엔진을 통한 간접 위임 감지: execute_ibl 결과에서 위임 키워드 확인
            for r in tool_results_list:
                if r.get("name") == "execute_ibl":
                    result_str = r.get("result", "")
                    if "에게 작업을 위임했습니다" in result_str or '"delegated": true' in result_str:
                        delegated = True
                        break

        if not delegated:
            # 최종 확인: DB에서 pending_delegations 체크
            try:
                task_data = get_task(task_id)
                if task_data and task_data.get('pending_delegations', 0) > 0:
                    delegated = True
                    print(f"[WS] DB pending_delegations로 위임 감지: {task_id}")
            except Exception:
                pass

        if delegated:
            # 위임된 경우: "delegated" 타입으로 전송 (프론트엔드가 연결 유지)
            await manager.send_message(client_id, {
                "type": "delegated",
                "agent": "system_ai",
                "task_id": task_id,
                "message": "작업을 위임했습니다. 결과를 기다리는 중..."
            })
            print(f"[WS] 시스템 AI 위임 발생 - 태스크 유지: {task_id}")
        else:
            # 위임 없이 완료: "end" 전송 후 태스크 삭제
            await manager.send_message(client_id, {
                "type": "end",
                **turn_budget,  # turn_tokens·turn_cache_read (미측정이면 키 없음)
                "agent": "system_ai"
            })
            try:
                delete_task(task_id)
                print(f"[WS] 시스템 AI 태스크 삭제: {task_id}")
            except Exception as e:
                print(f"[WS] 시스템 AI 태스크 삭제 실패: {e}")

        # 에피소드 로그 종료
        try:
            from episode_logger import EpisodeLogger
            EpisodeLogger.end_episode()
        except Exception:
            pass

        clear_all_context()

    except Exception as e:
        import traceback
        traceback.print_exc()
        # 에피소드 로그 종료 (에러 시에도)
        try:
            from episode_logger import EpisodeLogger
            EpisodeLogger.end_episode()
        except Exception:
            pass
        try:
            from thread_context import clear_all_context
            clear_all_context()
        except:
            pass
        await manager.send_message(client_id, {
            "type": "error",
            "message": str(e)
        })


# 채팅 스트림 진입점 등록 — calendar_actions 등 아래층이 라우터를 import 하지 않고
# websocket_manager 슬롯을 통해 같은 경로로 주입하게 한다 (2026-08-05 감사 ⑦).
from websocket_manager import register_chat_streams as _register_chat_streams  # noqa: E402

_register_chat_streams(handle_chat_message_stream, handle_system_ai_chat_stream)
