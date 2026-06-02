"""CalendarActionsMixin — 캘린더 매니저의 액션 실행 메서드 모음.

CalendarManager에서 분리된 액션 함수들을 Mixin으로 제공합니다.
스위치, 워크플로우, 파이프라인, 알림, 목표 실행 등의 액션과
"보이는 실행"을 위한 창/WS 관리 헬퍼를 포함합니다.
"""

from typing import Dict

from runtime_utils import get_base_path

BASE_PATH = get_base_path()


class CalendarActionsMixin:
    """캘린더 액션 실행 메서드를 모아놓은 Mixin 클래스."""

    # =========================================================================
    # 액션 함수 (기존 scheduler.py에서 이전)
    # =========================================================================

    def _action_test(self, task: dict):
        """테스트 작업"""
        self._log(f"테스트 작업 실행: {task.get('title', 'unknown')}")
        return {"success": True, "message": "테스트 완료"}

    def _action_run_switch(self, task: dict):
        """스위치 실행 작업"""
        params = task.get("action_params", {})
        switch_id = params.get("switch_id")

        if not switch_id:
            self._log(f"스위치 ID가 없습니다: {task.get('title')}")
            return {"success": False, "error": "switch_id 누락"}

        try:
            from switch_manager import SwitchManager
            from switch_runner import SwitchRunner

            sm = SwitchManager()
            switch = sm.get_switch(switch_id)

            if not switch:
                self._log(f"스위치를 찾을 수 없습니다: {switch_id}")
                return {"success": False, "error": f"스위치 없음: {switch_id}"}

            self._log(f"스위치 실행: {switch.get('name', switch_id)}")
            runner = SwitchRunner(switch, on_status=self._log)
            result = runner.run()

            sm.record_run(switch_id)

            try:
                from notification_manager import get_notification_manager
                nm = get_notification_manager()
                if result.get("success"):
                    nm.success(
                        title="스케줄 실행 완료",
                        message=f"'{switch.get('name')}' 스위치가 성공적으로 실행되었습니다.",
                        source="scheduler"
                    )
                else:
                    nm.warning(
                        title="스케줄 실행 실패",
                        message=f"'{switch.get('name')}' 스위치 실행 중 오류: {result.get('message', '알 수 없는 오류')}",
                        source="scheduler"
                    )
            except Exception:
                pass

            return result

        except Exception as e:
            self._log(f"스위치 실행 오류: {str(e)}")
            return {"success": False, "error": str(e)}

    def _action_run_workflow(self, task: dict):
        """워크플로우 실행 작업"""
        params = task.get("action_params", {})
        workflow_id = params.get("workflow_id")

        if not workflow_id:
            self._log(f"워크플로우 ID가 없습니다: {task.get('title')}")
            return {"success": False, "error": "workflow_id 누락"}

        try:
            from workflow_engine import execute_workflow

            self._log(f"워크플로우 실행: {workflow_id}")
            result = execute_workflow(workflow_id, ".")

            try:
                from notification_manager import get_notification_manager
                nm = get_notification_manager()
                if result.get("success"):
                    nm.success(
                        title="워크플로우 실행 완료",
                        message=f"'{workflow_id}' 워크플로우가 성공적으로 실행되었습니다. ({result.get('steps_completed', 0)}/{result.get('steps_total', 0)} steps)",
                        source="scheduler"
                    )
                else:
                    nm.warning(
                        title="워크플로우 실행 실패",
                        message=f"'{workflow_id}' 워크플로우 실행 중 오류: {result.get('error', '알 수 없는 오류')}",
                        source="scheduler"
                    )
            except Exception:
                pass

            return result

        except Exception as e:
            self._log(f"워크플로우 실행 오류: {str(e)}")
            return {"success": False, "error": str(e)}

    def _action_run_pipeline(self, task: dict):
        """IBL 파이프라인 실행 — 창을 열고 에이전트가 보이는 곳에서 실행

        흐름:
        1. 프로젝트 창(또는 시스템 AI 창) 열기
        2. 에이전트 활성화 + WS 연결 대기
        3. WS를 통해 메시지 주입 → 에이전트가 채팅창에서 실시간으로 작업
        4. 요청/응답/도구실행 과정이 모두 사용자에게 보임
        """
        import time as _time
        import asyncio

        params = task.get("action_params", {})
        pipeline = params.get("pipeline", "")
        trigger_id = params.get("trigger_id")

        owner_project_id = task.get("owner_project_id", "")
        owner_agent_id = task.get("owner_agent_id", "")
        is_system_ai = (owner_project_id == "__system_ai__")

        if not pipeline:
            self._log(f"파이프라인이 없습니다: {task.get('title')}")
            return {"success": False, "error": "pipeline 누락"}

        # 사용자 메시지 생성 (에이전트에게 보낼 내용)
        user_message = (
            f"[스케줄 작업] 다음을 실행하고 결과를 보고해주세요:\n\n"
            f"`{pipeline}`"
        )

        try:
            start = _time.time()

            if is_system_ai:
                result = self._execute_visible_system_ai(user_message, task)
            elif owner_project_id and owner_agent_id:
                result = self._execute_visible_agent(
                    owner_project_id, owner_agent_id, user_message, task
                )
            else:
                # ── 소유자 없는 스케줄: 파이프라인 직접 실행 (레거시) ──
                from ibl_parser import parse as ibl_parse, IBLSyntaxError
                from workflow_engine import execute_pipeline

                try:
                    steps = ibl_parse(pipeline)
                except IBLSyntaxError as e:
                    self._log(f"IBL 문법 오류: {e}")
                    return {"success": False, "error": f"IBL 문법 오류: {e}"}

                self._log(f"[레거시] 파이프라인 직접 실행: {pipeline[:60]}...")
                result = execute_pipeline(steps, ".", agent_id=owner_agent_id)

            duration_ms = int((_time.time() - start) * 1000)

            # 트리거 이력 기록
            if trigger_id:
                try:
                    from trigger_engine import _add_history
                    _add_history(
                        trigger_id=trigger_id,
                        trigger_name=task.get("title", ""),
                        success=result.get("success", False),
                        result_summary=str(result.get("final_result", ""))[:500],
                        duration_ms=duration_ms
                    )
                except Exception:
                    pass

            # 알림 (성공/실패)
            try:
                from notification_manager import get_notification_manager
                nm = get_notification_manager()
                owner_label = f"{owner_project_id}/{owner_agent_id}" if owner_project_id else ""
                if result.get("success"):
                    nm.success(
                        title=f"스케줄 실행 완료{' — ' + owner_label if owner_label else ''}",
                        message=f"'{task.get('title')}'",
                        source="scheduler"
                    )
                else:
                    nm.warning(
                        title=f"스케줄 실행 실패{' — ' + owner_label if owner_label else ''}",
                        message=f"'{task.get('title')}': {result.get('error', '알 수 없는 오류')}",
                        source="scheduler"
                    )
            except Exception:
                pass

            return result

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._log(f"파이프라인 실행 오류: {str(e)}")
            return {"success": False, "error": str(e)}

    # =========================================================================
    # 스케줄 실행: "보이는 실행" — 창을 열고 에이전트가 채팅에서 작업
    # =========================================================================

    def _run_async(self, async_fn):
        """sync 스레드에서 async 함수 실행 헬퍼"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(async_fn(), loop)
                return future.result(timeout=30)
            else:
                return asyncio.run(async_fn())
        except RuntimeError:
            return asyncio.run(async_fn())

    def _open_window_and_wait_ws(self, project_id: str, agent_id: str,
                                  agent_name: str, is_system_ai: bool) -> str:
        """창을 열고 WS 연결이 생길 때까지 대기. client_id 반환.

        Returns:
            WS client_id (성공) 또는 None (실패)
        """
        import time as _t
        from websocket_manager import manager as ws_manager
        from api_websocket import send_launcher_command

        # 1) 이미 WS 연결이 있으면 바로 반환
        if is_system_ai:
            existing = ws_manager.find_system_ai_connections()
        else:
            existing = ws_manager.find_agent_connections(project_id, agent_id)

        if existing:
            self._log(f"WS 이미 연결됨: {existing[0]}")
            return existing[0]

        # 2) 창 열기 명령
        if is_system_ai:
            self._log("시스템 AI 창 열기 →")
            self._run_async(lambda: send_launcher_command("open_system_ai_window", {}))
        else:
            self._log(f"프로젝트 창 열기 → {project_id}/{agent_name}")
            self._run_async(lambda: send_launcher_command(
                "open_project_window",
                {"project_id": project_id, "project_name": project_id,
                 "agent_id": agent_id, "agent_name": agent_name}
            ))

        # 3) WS 연결 대기 (최대 30초)
        #    React StrictMode는 마운트→언마운트→재마운트를 하므로
        #    첫 번째 연결이 바로 죽을 수 있음. 안정화 대기 필요.
        first_found_at = None
        stable_client_id = None

        for i in range(60):
            _t.sleep(0.5)
            if is_system_ai:
                connections = ws_manager.find_system_ai_connections()
            else:
                connections = ws_manager.find_agent_connections(project_id, agent_id)

            if connections:
                latest = connections[-1]  # 가장 최신 연결 사용
                if first_found_at is None:
                    first_found_at = i
                    stable_client_id = latest
                    self._log(f"WS 연결 감지, 안정화 대기: {latest} ({(i+1)*0.5:.1f}초)")
                    continue  # 바로 반환하지 않고 안정화 대기

                # 첫 감지 후 2초(4틱) 이상 지났으면 안정적
                stable_client_id = latest  # 항상 최신으로 갱신
                if i - first_found_at >= 4:
                    self._log(f"WS 연결 안정화 확인: {stable_client_id} ({(i+1)*0.5:.1f}초)")
                    return stable_client_id
            else:
                # 연결이 있었다가 사라짐 (StrictMode 언마운트)
                if first_found_at is not None:
                    self._log(f"WS 연결 일시 해제 감지 (StrictMode), 재연결 대기...")
                    first_found_at = None
                    stable_client_id = None

        # 타임아웃이지만 연결이 있으면 반환
        if stable_client_id:
            self._log(f"WS 안정화 대기 타임아웃, 마지막 연결 사용: {stable_client_id}")
            return stable_client_id

        self._log("WS 연결 타임아웃 (30초)")
        return None

    def _ensure_agent_running(self, project_id: str, agent_id: str) -> bool:
        """에이전트가 agent_runners에 등록되어 있는지 확인하고, 없으면 시작.
        프론트엔드가 에이전트를 시작할 때까지 대기하거나 직접 시작.
        """
        import time as _t
        from api_agents import get_agent_runners

        # 프론트엔드가 autoActivateAgent로 시작할 시간 기다림
        for i in range(20):
            runners = get_agent_runners()
            if project_id in runners and agent_id in runners[project_id]:
                runner_info = runners[project_id][agent_id]
                runner = runner_info.get("runner")
                if runner and runner.running and runner.ai:
                    self._log(f"에이전트 준비 완료: {project_id}/{agent_id} ({(i+1)*0.5:.1f}초)")
                    return True
            _t.sleep(0.5)

        self._log(f"에이전트 자동 시작 타임아웃, 직접 시작 시도: {project_id}/{agent_id}")
        # 프론트엔드가 시작하지 않았으면 백엔드에서 직접 시작
        try:
            import yaml
            from project_manager import ProjectManager
            from agent_runner import AgentRunner

            pm = ProjectManager()
            project_path = pm.get_project_path(project_id)
            agents_yaml = project_path / "agents.yaml"
            if not agents_yaml.exists():
                return False

            data = yaml.safe_load(agents_yaml.read_text(encoding='utf-8'))
            agents = data.get("agents", [])
            common_config = data.get("common", {})

            agent_config = None
            for ag in agents:
                if ag.get("id") == agent_id or ag.get("name") == agent_id:
                    agent_config = ag
                    agent_id = ag.get("id", agent_id)
                    break

            if not agent_config:
                active = [a for a in agents if a.get("active", True)]
                if active:
                    agent_config = active[0]
                    agent_id = agent_config.get("id", agent_id)

            if not agent_config:
                return False

            agent_config["_project_path"] = str(project_path)
            agent_config["_project_id"] = project_id

            runner = AgentRunner(agent_config, common_config)
            runner.start()

            runners = get_agent_runners()
            if project_id not in runners:
                runners[project_id] = {}
            runners[project_id][agent_id] = {
                "runner": runner,
                "config": agent_config,
                "running": True,
                "started_at": __import__('datetime').datetime.now().isoformat()
            }

            _t.sleep(1.0)
            self._log(f"에이전트 직접 시작 완료: {agent_config.get('name', agent_id)}")
            return True

        except Exception as e:
            self._log(f"에이전트 직접 시작 실패: {e}")
            return False

    def _inject_message_via_ws(self, client_id: str, project_id: str,
                                agent_id: str, agent_name: str,
                                message: str, is_system_ai: bool) -> dict:
        """WS를 통해 메시지를 주입 — handle_chat_message_stream / handle_system_ai_chat_stream 호출.

        프론트엔드의 ChatView가 보낸 것과 동일한 경로를 타서
        스트리밍, 도구 실행, 응답이 모두 채팅창에 실시간으로 보임.

        fire-and-forget: 코루틴을 이벤트 루프에 스케줄링하고 즉시 반환.
        에이전트 작업은 비동기로 실행되며, 결과는 WS를 통해 프론트엔드에 전달됨.
        """
        import asyncio

        try:
            if is_system_ai:
                from api_websocket import handle_system_ai_chat_stream
                data = {
                    "type": "system_ai_stream",
                    "message": message,
                }
                self._log(f"시스템 AI WS 메시지 주입: {message[:60]}...")
                coro = handle_system_ai_chat_stream(client_id, data)
            else:
                from api_websocket import handle_chat_message_stream
                data = {
                    "type": "chat_stream",
                    "message": message,
                    "agent_name": agent_name,
                    "project_id": project_id,
                }
                self._log(f"에이전트 WS 메시지 주입: {project_id}/{agent_name} — {message[:60]}...")
                coro = handle_chat_message_stream(client_id, data)

            # fire-and-forget: 이벤트 루프에 코루틴 스케줄링 (완료를 기다리지 않음)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(coro, loop)
                else:
                    asyncio.run(coro)
            except RuntimeError:
                asyncio.run(coro)

            self._log("WS 메시지 주입 완료 (에이전트 작업 시작됨)")
            return {"success": True, "final_result": "WS를 통해 실행됨 (채팅창에 표시)", "visible": True}

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._log(f"WS 메시지 주입 실패: {e}")
            return {"success": False, "error": str(e)}

    def _execute_visible_agent(self, project_id: str, agent_id: str,
                                message: str, task: dict) -> dict:
        """프로젝트 에이전트: 창 열기 → 에이전트 활성화 → WS로 메시지 주입"""

        # 에이전트 이름 조회
        agent_name = agent_id
        try:
            import yaml
            agents_yaml = BASE_PATH / "projects" / project_id / "agents.yaml"
            if agents_yaml.exists():
                data = yaml.safe_load(agents_yaml.read_text(encoding='utf-8'))
                for ag in data.get("agents", []):
                    if ag.get("id") == agent_id or ag.get("name") == agent_id:
                        agent_name = ag.get("name", agent_id)
                        agent_id = ag.get("id", agent_id)
                        break
        except Exception:
            pass

        self._log(f"[{project_id}/{agent_name}] 보이는 실행 시작")

        # 1. 창 열기 + WS 연결 대기
        client_id = self._open_window_and_wait_ws(project_id, agent_id, agent_name, False)
        if not client_id:
            self._log("창/WS 연결 실패 → 보이는 실행 불가")
            return {"success": False, "error": "프로젝트 창/WS 연결 실패"}

        # 2. 에이전트가 agent_runners에 등록되기 대기
        if not self._ensure_agent_running(project_id, agent_id):
            self._log("에이전트 시작 실패")
            return {"success": False, "error": "에이전트 시작 실패"}

        # 3. WS로 메시지 주입 → 채팅창에 실시간 표시
        return self._inject_message_via_ws(client_id, project_id, agent_id, agent_name, message, False)

    def _execute_visible_system_ai(self, message: str, task: dict) -> dict:
        """시스템 AI: 창 열기 → WS 연결 대기 → WS로 메시지 주입"""

        self._log("[시스템 AI] 보이는 실행 시작")

        # 1. 창 열기 + WS 연결 대기
        client_id = self._open_window_and_wait_ws("__system_ai__", "system_ai", "시스템 AI", True)
        if not client_id:
            self._log("시스템 AI 창/WS 연결 실패")
            return {"success": False, "error": "시스템 AI 창/WS 연결 실패"}

        # 2. WS로 메시지 주입 → 채팅창에 실시간 표시
        return self._inject_message_via_ws(client_id, "__system_ai__", "system_ai", "시스템 AI", message, True)

    def _action_send_notification(self, task: dict):
        """알림 전송 작업"""
        params = task.get("action_params", {})
        message = params.get("message", task.get("description", ""))
        title = params.get("title", task.get("title", "스케줄 알림"))
        noti_type = params.get("type", "info")

        try:
            from notification_manager import get_notification_manager
            nm = get_notification_manager()
            notification = nm.create(
                title=title,
                message=message,
                type=noti_type,
                source="scheduler"
            )
            self._log(f"알림 전송: {title}")
            return {"success": True, "notification_id": notification["id"]}
        except Exception as e:
            self._log(f"알림 전송 실패: {str(e)}")
            return {"success": False, "error": str(e)}

    def _action_run_goal(self, task: dict):
        """Phase 26: 목표 반복 실행 (every/schedule에 의해 트리거)

        CalendarManager가 every 주기에 맞춰 goal의 다음 라운드를 실행합니다.
        goal_id로 DB에서 목표를 조회하고, agent_runner를 통해 판단 루프 1회를 실행합니다.
        """
        params = task.get("action_params", {})
        goal_id = params.get("goal_id")

        if not goal_id:
            self._log(f"Goal ID가 없습니다: {task.get('title')}")
            return {"success": False, "error": "goal_id 누락"}

        try:
            from conversation_db import ConversationDB
            db = ConversationDB()
            goal = db.get_goal(goal_id)

            if not goal:
                self._log(f"목표를 찾을 수 없습니다: {goal_id}")
                return {"success": False, "error": f"목표 없음: {goal_id}"}

            # 이미 종료된 목표면 스킵
            if goal["status"] in ("achieved", "expired", "limit_reached", "cancelled"):
                self._log(f"종료된 목표 스킵: {goal['name']} ({goal['status']})")
                # 이벤트도 비활성화
                task["enabled"] = False
                self._save_config()
                return {"success": True, "skipped": True, "reason": goal["status"]}

            # agent_runner를 통해 판단 루프 실행
            from agent_runner import AgentRunner

            # 활성 에이전트 찾기 (registry에서 running 상태인 에이전트)
            runner = None
            for aid, agent in AgentRunner.agent_registry.items():
                if agent.running:
                    runner = agent
                    break

            if runner:
                runner._activate_and_run_goal(goal_id)
            else:
                self._log(f"활성 에이전트 없음, Goal 실행 스킵: {goal_id}")
                return {"success": False, "error": "활성 에이전트 없음"}

            # 실행 후 상태 재확인
            updated_goal = db.get_goal(goal_id)
            if updated_goal and updated_goal["status"] in ("achieved", "expired", "limit_reached"):
                task["enabled"] = False
                self._save_config()
                self._log(f"목표 완료, 스케줄 비활성화: {goal['name']} ({updated_goal['status']})")

            try:
                from notification_manager import get_notification_manager
                nm = get_notification_manager()
                nm.info(
                    title="목표 라운드 실행",
                    message=f"'{goal['name']}' 라운드 {goal.get('current_round', 0) + 1} 실행됨",
                    source="scheduler"
                )
            except Exception:
                pass

            self._log(f"목표 라운드 실행 완료: {goal['name']}")
            return {"success": True, "goal_id": goal_id, "name": goal["name"]}

        except Exception as e:
            self._log(f"목표 실행 실패: {goal_id} - {str(e)}")
            return {"success": False, "error": str(e)}
