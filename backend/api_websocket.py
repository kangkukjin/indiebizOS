"""
api_websocket.py - WebSocket 채팅 API (스트리밍 지원)
IndieBiz OS Core
"""

import re
import uuid
import asyncio
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


def is_cancelled(client_id: str) -> bool:
    """클라이언트의 중단 요청 여부 확인"""
    return cancel_flags.get(client_id, False)


def set_cancel(client_id: str, value: bool):
    """클라이언트의 중단 플래그 설정"""
    cancel_flags[client_id] = value


def get_agent_runners():
    from api_agents import get_agent_runners as _get
    return _get()


def init_manager(pm):
    global project_manager
    project_manager = pm


# ============ Launcher WebSocket ============

_launcher_ws = None  # Launcher 전용 WS 연결 (1개)

@router.websocket("/ws/launcher")
async def websocket_launcher(websocket: WebSocket):
    """런처 전용 WebSocket — 백엔드→런처 명령 전달 채널"""
    global _launcher_ws
    await websocket.accept()
    _launcher_ws = websocket
    print("[WS] Launcher 연결됨")

    try:
        while True:
            # Launcher→백엔드 메시지 (ping/ack 등)
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except (WebSocketDisconnect, Exception):
        _launcher_ws = None
        print("[WS] Launcher 연결 해제")


async def send_launcher_command(command: str, params: dict = None) -> bool:
    """백엔드에서 Launcher로 명령 전송 (예: 프로젝트 창 열기)"""
    global _launcher_ws
    if not _launcher_ws:
        print(f"[WS] Launcher 미연결, 명령 전달 불가: {command}")
        return False
    try:
        await _launcher_ws.send_json({
            "type": "launcher_command",
            "command": command,
            "params": params or {}
        })
        return True
    except Exception as e:
        print(f"[WS] Launcher 명령 전달 실패: {e}")
        _launcher_ws = None
        return False


def get_launcher_ws():
    """Launcher WS 연결 상태 확인 (동기 호출용)"""
    return _launcher_ws


# ============ WebSocket 채팅 ============

@router.websocket("/ws/android/{agent_id}")
async def websocket_android(websocket: WebSocket, agent_id: str):
    """안드로이드 전용 에이전트 WebSocket 엔드포인트"""
    # agent_id는 이미 "android_xxx" 형식으로 전달됨 - 접두사 추가하지 않음
    print(f"[WS Android] 연결: {agent_id}")
    await manager.connect(websocket, agent_id)

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type", "chat")

            if message_type == "chat":
                await handle_android_chat(agent_id, data)
            elif message_type == "ping":
                await manager.send_message(agent_id, {"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(agent_id)
        print(f"[WS Android] 연결 해제: {agent_id}")
    except Exception as e:
        print(f"[WS Android 에러] {agent_id}: {e}")
        manager.disconnect(agent_id)


async def handle_android_chat(client_id: str, data: dict):
    """안드로이드 에이전트 채팅 처리"""
    message = data.get("message", "")

    try:
        from api_android import get_android_agent
        agent = get_android_agent()

        if not agent:
            await manager.send_message(client_id, {
                "type": "error",
                "message": "안드로이드 에이전트가 실행 중이 아닙니다."
            })
            return

        # 시작 알림
        await manager.send_message(client_id, {"type": "start"})

        # 동기 제너레이터를 별도 스레드에서 실행하고 Queue로 결과 전달
        queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def run_stream():
            """별도 스레드에서 동기 스트림 실행"""
            try:
                for chunk in agent.chat_stream_sync(message):
                    loop.call_soon_threadsafe(queue.put_nowait, ("chunk", chunk))
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
            except Exception as e:
                import traceback
                traceback.print_exc()
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(e)))

        # 스레드 풀에서 스트림 실행
        executor.submit(run_stream)

        # Queue에서 메시지 수신하여 WebSocket으로 전송
        while True:
            msg_type, content = await queue.get()

            if msg_type == "chunk":
                await manager.send_message(client_id, {
                    "type": "chunk",
                    "content": content
                })
            elif msg_type == "done":
                await manager.send_message(client_id, {"type": "done"})
                break
            elif msg_type == "error":
                await manager.send_message(client_id, {
                    "type": "error",
                    "message": content
                })
                break

    except Exception as e:
        import traceback
        traceback.print_exc()
        await manager.send_message(client_id, {
            "type": "error",
            "message": str(e)
        })


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
                await handle_chat_message_stream(client_id, data)
            elif message_type == "system_ai_stream":
                await handle_system_ai_chat_stream(client_id, data)
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


async def handle_chat_message(client_id: str, data: dict):
    """채팅 메시지 처리 (기존 동기 방식)"""
    message = data.get("message", "")
    agent_name = data.get("agent_name", "")
    project_id = data.get("project_id", "")
    images = data.get("images", [])

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
            await manager.send_message(client_id, {
                "type": "error",
                "message": "에이전트 설정을 찾을 수 없습니다."
            })
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
            await manager.send_message(client_id, {
                "type": "error",
                "message": f"에이전트 '{agent_name}'을(를) 찾을 수 없습니다."
            })
            return

        # 실행 중인 AgentRunner 확인
        agent_runners = get_agent_runners()
        if project_id not in agent_runners or agent_id not in agent_runners[project_id]:
            await manager.send_message(client_id, {
                "type": "error",
                "message": f"에이전트 '{agent_name}'이(가) 실행 중이 아닙니다. 먼저 시작해주세요."
            })
            return

        runner_info = agent_runners[project_id][agent_id]
        runner = runner_info.get("runner")

        if not runner or not runner.ai:
            await manager.send_message(client_id, {
                "type": "error",
                "message": f"에이전트 '{agent_name}'의 AI가 준비되지 않았습니다."
            })
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

        # 실행기억 생성 (RAG + discover + implementation, 1회)
        execution_memory = runner._build_execution_memory(message)

        # 의식 에이전트 실행 — 메타 판단
        consciousness_output = runner._run_consciousness(
            message, history, execution_memory
        )
        if consciousness_output:
            # 시스템 프롬프트 재구성 (의식 에이전트 출력 + 실행기억 반영)
            role_file = runner.project_path / f"agent_{agent_name}_role.txt"
            role = role_file.read_text(encoding='utf-8') if role_file.exists() else ""
            new_prompt = runner._build_system_prompt(
                role, consciousness_output, execution_memory
            )
            runner.ai.system_prompt = new_prompt
            if runner.ai._provider:
                runner.ai._provider.system_prompt = new_prompt

            # 히스토리 편집 (의식 에이전트 판단에 따라)
            history = runner._apply_consciousness_to_history(history, consciousness_output)

        # 실행기억은 이미 시스템 프롬프트에 반영됨
        # AI 응답 생성
        response = runner.ai.process_message_with_history(
            message_content=message,
            from_email="user@gui",
            history=history,
            reply_to="user@gui",
            task_id=task_id,
            images=images
        )

        # AI 응답 저장 (도구 결과 이미지 포함)
        tool_images = runner.ai.get_last_tool_images()
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

        # 컨텍스트 정리
        from thread_context import clear_all_context
        clear_all_context()

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

    # 에피소드 로그 시작
    try:
        from episode_logger import EpisodeLogger
        EpisodeLogger.start_episode(agent_name, message)
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
            await manager.send_message(client_id, {
                "type": "error",
                "message": "에이전트 설정을 찾을 수 없습니다."
            })
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
            await manager.send_message(client_id, {
                "type": "error",
                "message": f"에이전트 '{agent_name}'을(를) 찾을 수 없습니다."
            })
            return

        # 실행 중인 AgentRunner 확인
        agent_runners = get_agent_runners()
        if project_id not in agent_runners or agent_id not in agent_runners[project_id]:
            await manager.send_message(client_id, {
                "type": "error",
                "message": f"에이전트 '{agent_name}'이(가) 실행 중이 아닙니다. 먼저 시작해주세요."
            })
            return

        runner_info = agent_runners[project_id][agent_id]
        runner = runner_info.get("runner")

        if not runner or not runner.ai:
            await manager.send_message(client_id, {
                "type": "error",
                "message": f"에이전트 '{agent_name}'의 AI가 준비되지 않았습니다."
            })
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

        # 실행기억 생성 (RAG + discover + implementation, 1회)
        execution_memory = runner._build_execution_memory(message)

        # 해마 최고 점수 저장 (경험 증류 판단용)
        from ibl_usage_rag import get_top_score as _get_top_score
        _hippocampus_score = _get_top_score(message)

        # 무의식 에이전트 — 실행형/판단형 분류 (반사 신경 + Reflex IBL)
        request_type, reflex_hint = runner._classify_request(message, execution_memory)
        if reflex_hint:
            print(f"[무의식] Reflex EXECUTE: {reflex_hint[:60]}")
        else:
            print(f"[무의식] 분류: {request_type}")

        # 판단형만 의식 에이전트 실행
        consciousness_output = None
        if request_type == "THINK":
            consciousness_output = runner._run_consciousness(
                message, history, execution_memory
            )
        if consciousness_output:
            role_file = runner.project_path / f"agent_{agent_name}_role.txt"
            role = role_file.read_text(encoding='utf-8') if role_file.exists() else ""
            new_prompt = runner._build_system_prompt(
                role, consciousness_output, execution_memory
            )
            runner.ai.system_prompt = new_prompt
            if runner.ai._provider:
                runner.ai._provider.system_prompt = new_prompt
            history = runner._apply_consciousness_to_history(history, consciousness_output)
        elif execution_memory or reflex_hint:
            # EXECUTE 경로: 실행기억(+reflex 힌트)만 시스템 프롬프트에 반영
            _exec_mem = execution_memory or ""
            if reflex_hint:
                _exec_mem += (
                    f"\n\n<reflex_hint note=\"고확신 매칭된 IBL 패턴입니다. "
                    f"이 코드를 우선적으로 사용하세요.\">"
                    f"\n{reflex_hint}\n</reflex_hint>"
                )
            role_file = runner.project_path / f"agent_{agent_name}_role.txt"
            role = role_file.read_text(encoding='utf-8') if role_file.exists() else ""
            new_prompt = runner._build_system_prompt(role, None, _exec_mem)
            runner.ai.system_prompt = new_prompt
            if runner.ai._provider:
                runner.ai._provider.system_prompt = new_prompt

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

        set_current_task_id(task_id)

        # 스트리밍 처리를 위한 큐
        event_queue = asyncio.Queue()
        final_content = ""
        timed_out = False  # 타임아웃 발생 여부 (워커 스레드에서 확인)
        loop = asyncio.get_running_loop()

        tool_results_log = []  # 도구 실행 이력 수집
        tool_calls_log = []   # 경험 증류용 도구 호출 구조화 이력

        def run_stream():
            """스레드에서 스트리밍 실행"""
            nonlocal final_content
            # 별도 스레드이므로 컨텍스트 재설정 필요
            from thread_context import set_user_input as _set_user_input
            set_current_agent_id(agent_id)
            set_current_agent_name(agent_name)
            set_current_project_id(project_id)
            set_current_task_id(task_id)
            _set_user_input(message)
            # 실행기억은 이미 시스템 프롬프트에 반영됨
            try:
                for event in runner.ai.process_message_stream(
                    message_content=message,
                    history=history,
                    images=images
                ):
                    event_type = event.get("type", "unknown")
                    print(f"[WS run_stream] 이벤트 수신: {event_type}")
                    asyncio.run_coroutine_threadsafe(
                        event_queue.put(event),
                        loop
                    )
                    if event_type == "final":
                        final_content = event.get("content", "")
                        print(f"[WS run_stream] final_content 설정됨 (len={len(final_content)})")
                    elif event_type == "tool_start":
                        # 경험 증류용: 도구 호출 시작 기록
                        tool_calls_log.append({
                            "tool_name": event.get("name", ""),
                            "input": event.get("input", {}),
                            "success": True,  # tool_result에서 업데이트
                        })
                    elif event_type == "tool_result":
                        # 도구 실행 결과 수집 (평가 루프에서 사용)
                        tool_results_log.append(event.get("content", ""))

                # Goal 평가 루프 — 달성 기준이 있으면 평가 후 재시도
                if consciousness_output and final_content:
                    criteria = runner._extract_achievement_criteria(consciousness_output)
                    if criteria:
                        from world_pulse import _load_config as _load_wp_config
                        _goal_cfg = _load_wp_config().get("goal_eval", {})
                        if _goal_cfg.get("enabled", True):
                            print(f"[GoalEval] 달성 기준 감지: {criteria[:80]}")
                            evaluated = runner._run_goal_evaluation_loop(
                                user_message=message,
                                criteria=criteria,
                                initial_response=final_content,
                                history=history,
                                consciousness_output=consciousness_output,
                                max_rounds=_goal_cfg.get("max_rounds", 3),
                                tool_results=tool_results_log,
                                execution_memory=execution_memory,
                            )
                            if evaluated and evaluated.strip() and evaluated != final_content:
                                # 평가 후 재실행된 응답을 스트리밍으로 전송
                                final_content = evaluated
                                asyncio.run_coroutine_threadsafe(
                                    event_queue.put({"type": "text", "content": "\n\n---\n[평가 피드백 반영 재실행]\n\n"}),
                                    loop
                                )
                                asyncio.run_coroutine_threadsafe(
                                    event_queue.put({"type": "text", "content": evaluated}),
                                    loop
                                )
                                asyncio.run_coroutine_threadsafe(
                                    event_queue.put({"type": "final", "content": evaluated}),
                                    loop
                                )
                                print(f"[GoalEval] 재실행 결과 전송 완료 ({len(evaluated)}자)")

            except Exception as e:
                print(f"[WS run_stream] 예외 발생: {e}")
                asyncio.run_coroutine_threadsafe(
                    event_queue.put({"type": "error", "content": str(e)}),
                    loop
                )
            finally:
                print(f"[WS run_stream] 스트림 종료, final_content len={len(final_content)}, timed_out={timed_out}")
                if timed_out and final_content:
                    # 타임아웃 이후 워커가 결과를 완성한 경우: DB에 미전달로 저장
                    try:
                        filtered = filter_internal_markers(final_content)
                        msg_id = db.save_message_undelivered(target_agent_id, user_id, filtered)
                        print(f"[WS run_stream] 타임아웃 후 미전달 메시지 저장 완료: message_id={msg_id}")
                    except Exception as save_err:
                        print(f"[WS run_stream] 타임아웃 후 메시지 저장 실패: {save_err}")
                # thread_context에서 node/action/ms 포함 도구 이력 수집 (X-Ray용)
                try:
                    from thread_context import get_tool_calls as _get_tc, clear_tool_calls as _clear_tc
                    _tc = _get_tc()
                    if _tc:
                        # GoalEval 재실행 포함 모든 라운드의 액션을 누적
                        tool_calls_log.extend(_tc)
                    _clear_tc()
                except Exception:
                    pass

                # 경험 증류: 해마 점수가 낮은 성공 세션에서 새로운 패턴 학습
                if final_content and tool_calls_log:
                    try:
                        from ibl_usage_rag import distill_experience
                        distill_experience(message, tool_calls_log, _hippocampus_score)
                    except Exception as distill_err:
                        print(f"[경험증류] 오류 (무시): {distill_err}")

                asyncio.run_coroutine_threadsafe(
                    event_queue.put(None),  # 종료 신호
                    loop
                )

        # 별도 스레드에서 스트리밍 시작
        executor.submit(run_stream)

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
                    "message": "응답 시간 초과 (10분). 작업이 완료되면 자동으로 표시됩니다."
                })
                break

            if event is None:
                break

            event_type = event.get("type")

            if event_type == "text":
                # 텍스트 청크 전송
                await manager.send_message(client_id, {
                    "type": "stream_chunk",
                    "content": event.get("content", ""),
                    "agent": agent_name
                })

            elif event_type == "tool_start":
                # 도구 시작 알림
                await manager.send_message(client_id, {
                    "type": "tool_start",
                    "name": event.get("name", "unknown"),
                    "agent": agent_name
                })

            elif event_type == "tool_result":
                # 도구 결과 알림
                tool_name = event.get("name", "unknown")
                tool_input = event.get("input", {})

                message_data = {
                    "type": "tool_result",
                    "name": tool_name,
                    "result": event.get("result", ""),
                    "agent": agent_name
                }

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

            elif event_type == "final":
                final_content = event.get("content", "")
                print(f"[WS while루프] final 이벤트 수신 (len={len(final_content)})")

            elif event_type == "error":
                await manager.send_message(client_id, {
                    "type": "error",
                    "message": event.get("content", "알 수 없는 오류")
                })
                break

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
        if task_id:
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
                    """, ((final_content or "")[:500], tool_history_json, task_id))
                    conn.commit()
                # X-Ray 실시간 이벤트
                try:
                    from api_xray import push_xray_event
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

    **통합 아키텍처**: process_system_ai_message_stream()을 사용하여
    AIAgent 클래스의 스트리밍 기능을 활용합니다.
    모든 프로바이더(Anthropic, OpenAI, Gemini, Ollama)가 자동으로 지원됩니다.
    """
    message = data.get("message", "")
    images = data.get("images", [])

    # 에피소드 로그 시작
    try:
        from episode_logger import EpisodeLogger
        EpisodeLogger.start_episode("system_ai", message)
    except Exception:
        pass

    try:
        # 시작 알림
        await manager.send_message(client_id, {
            "type": "start",
            "agent": "system_ai"
        })

        # 시스템 AI 설정 및 헬퍼 함수 로드
        from api_system_ai import (
            load_system_ai_config,
            process_system_ai_message_stream
        )
        from system_ai_memory import (
            save_conversation,
            get_history_for_ai,
            create_task,
            delete_task,
            get_task
        )
        from thread_context import set_current_task_id, clear_all_context

        # 태스크 생성 (위임 기능에 필요)
        task_id = f"task_sysai_{uuid.uuid4().hex[:8]}"
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

        if not api_key:
            await manager.send_message(client_id, {
                "type": "error",
                "message": "API 키가 설정되지 않았습니다."
            })
            return

        # 최근 대화 히스토리 로드 (조회 + 역할 매핑 + Observation Masking 통합)
        history = get_history_for_ai(limit=7)

        # 사용자 메시지 저장 (이미지 포함)
        save_conversation("user", message, images=images if images else None)

        # 스트리밍 처리 (AIAgent 사용)
        event_queue = asyncio.Queue()
        final_content = ""
        tool_results_list = []  # 도구 실행 결과 기록용
        collected_tool_images = []  # 도구 결과 이미지 수집
        timed_out = False  # 타임아웃 발생 여부 (워커 스레드에서 확인)
        loop = asyncio.get_running_loop()

        # 중단 플래그 초기화
        set_cancel(client_id, False)

        def run_stream():
            """스레드에서 시스템 AI 스트리밍 실행 (AgentRunner 인지 파이프라인)"""
            nonlocal final_content
            # 스레드별로 컨텍스트를 다시 설정해야 함 (thread-local storage)
            set_current_task_id(task_id)
            try:
                # 인지 메타데이터 수집 (평가 루프용)
                consciousness_output = None
                execution_memory = ""
                tool_results_log = []

                # 통합된 스트리밍 함수 사용 - 모든 프로바이더 지원
                for event in process_system_ai_message_stream(
                    message=message,
                    history=history,
                    images=images if images else None,
                    cancel_check=lambda: is_cancelled(client_id)  # 중단 체크 함수 전달
                ):
                    # 중단 요청 시 루프 탈출
                    if is_cancelled(client_id):
                        asyncio.run_coroutine_threadsafe(
                            event_queue.put({"type": "cancelled", "content": "사용자가 중단했습니다."}),
                            loop
                        )
                        break

                    event_type = event.get("type")

                    # 인지 메타데이터 수집 (클라이언트에 전달하지 않음)
                    if event_type == "_consciousness_output":
                        consciousness_output = event.get("data")
                        execution_memory = event.get("execution_memory", "")
                        continue

                    # 도구 실행 결과 수집 (평가 루프에서 사용)
                    if event_type == "tool_result":
                        tool_results_log.append(event.get("content", ""))
                        if event.get("images"):
                            collected_tool_images.extend(event["images"])

                    asyncio.run_coroutine_threadsafe(event_queue.put(event), loop)
                    if event_type == "final":
                        final_content = event.get("content", "")

                # 평가 루프 — 달성 기준이 있으면 프로젝트 에이전트와 동일하게 실행
                if consciousness_output and final_content:
                    from system_ai_core import get_system_ai_runner
                    runner = get_system_ai_runner()
                    criteria = runner._extract_achievement_criteria(consciousness_output)
                    if criteria:
                        from world_pulse import _load_config as _load_wp_config
                        _goal_cfg = _load_wp_config().get("goal_eval", {})
                        if _goal_cfg.get("enabled", True):
                            print(f"[GoalEval] 달성 기준 감지: {criteria[:80]}")
                            evaluated = runner._run_goal_evaluation_loop(
                                user_message=message,
                                criteria=criteria,
                                initial_response=final_content,
                                history=history,
                                consciousness_output=consciousness_output,
                                max_rounds=_goal_cfg.get("max_rounds", 3),
                                tool_results=tool_results_log,
                                execution_memory=execution_memory,
                            )
                            if evaluated and evaluated.strip() and evaluated != final_content:
                                final_content = evaluated
                                asyncio.run_coroutine_threadsafe(
                                    event_queue.put({"type": "text", "content": "\n\n---\n[평가 피드백 반영 재실행]\n\n"}),
                                    loop
                                )
                                asyncio.run_coroutine_threadsafe(
                                    event_queue.put({"type": "text", "content": evaluated}),
                                    loop
                                )
                                asyncio.run_coroutine_threadsafe(
                                    event_queue.put({"type": "final", "content": evaluated}),
                                    loop
                                )
                                print(f"[GoalEval] 재실행 결과 전송 완료 ({len(evaluated)}자)")
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    event_queue.put({"type": "error", "content": str(e)}),
                    loop
                )
            finally:
                if timed_out and final_content:
                    # 타임아웃 이후 워커가 결과를 완성한 경우: 시스템 AI 대화 저장
                    try:
                        filtered = filter_internal_markers(final_content)
                        save_conversation("assistant", filtered)
                        print(f"[WS run_stream] 시스템AI 타임아웃 후 대화 저장 완료")
                    except Exception as save_err:
                        print(f"[WS run_stream] 시스템AI 타임아웃 후 저장 실패: {save_err}")
                asyncio.run_coroutine_threadsafe(event_queue.put(None), loop)

        # 스레드에서 스트리밍 시작
        executor.submit(run_stream)

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
                    "message": "응답 시간 초과 (10분). 작업이 완료되면 자동으로 표시됩니다."
                })
                break

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
                await manager.send_message(client_id, {
                    "type": "tool_start",
                    "name": event.get("name", "unknown"),
                    "input": event.get("input", {}),
                    "agent": "system_ai"
                })

            elif event_type == "tool_result":
                tool_result = event.get("result", "")
                tool_name = event.get("name", "unknown")

                # 도구 결과 기록 (final이 비어있을 때 사용)
                tool_results_list.append({
                    "name": tool_name,
                    "result": tool_result,
                    "has_error": "error" in tool_result.lower() or '"success": false' in tool_result.lower()
                })

                tool_input = event.get("input", {})

                message_data = {
                    "type": "tool_result",
                    "name": tool_name,
                    "result": tool_result,
                    "agent": "system_ai"
                }

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

            elif event_type == "final":
                final_content = event.get("content", "")

            elif event_type == "error":
                await manager.send_message(client_id, {
                    "type": "error",
                    "message": event.get("content", "알 수 없는 오류")
                })
                break

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

        save_conversation("assistant", final_content, images=collected_tool_images if collected_tool_images else None)

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
