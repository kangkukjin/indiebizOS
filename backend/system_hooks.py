"""
system_hooks.py - 시스템 변경 훅
IndieBiz OS Core

시스템에 변경이 있을 때 자동으로 문서를 업데이트합니다.

참고: 패키지 관련 훅은 package_manager.py에서 직접 처리합니다.
      (폴더 기반 단일 진실 원천 원칙)
"""

from datetime import datetime
from typing import List, Dict, Any

from system_docs import (
    update_overview_stats,
    update_inventory_projects,
    log_change
)


def on_project_created(project: Dict[str, Any], all_projects: List[Dict[str, Any]]):
    """프로젝트 생성 시"""
    log_change("PROJECT_CREATED", f"{project.get('name', 'Unknown')} (ID: {project.get('id', '?')})")
    update_inventory_projects(all_projects)
    update_overview_stats(project_count=len(all_projects))


def on_project_deleted(project_id: str, all_projects: List[Dict[str, Any]]):
    """프로젝트 삭제 시"""
    log_change("PROJECT_DELETED", f"ID: {project_id}")
    update_inventory_projects(all_projects)
    update_overview_stats(project_count=len(all_projects))


def on_agent_created(project_id: str, agent: Dict[str, Any], total_agent_count: int):
    """에이전트 생성 시"""
    log_change("AGENT_CREATED", f"{agent.get('name', 'Unknown')} in project {project_id}")
    update_overview_stats(agent_count=total_agent_count)


def on_agent_deleted(project_id: str, agent_id: str, total_agent_count: int):
    """에이전트 삭제 시"""
    log_change("AGENT_DELETED", f"Agent {agent_id} from project {project_id}")
    update_overview_stats(agent_count=total_agent_count)


def refresh_system_stats(project_manager):
    """시스템 통계 전체 새로고침"""
    try:
        # 프로젝트 수
        projects = project_manager.list_projects()
        project_count = len([p for p in projects if not p.get('is_folder', False)])

        # 에이전트 수 (모든 프로젝트의 에이전트 합계)
        agent_count = 0
        for project in projects:
            if not project.get('is_folder', False):
                try:
                    agents = project_manager.get_agents(project['id'])
                    agent_count += len(agents)
                except:
                    pass

        # 도구 패키지 수
        tool_count = 0
        try:
            from package_manager import package_manager
            tool_count = len(package_manager.list_installed())
        except:
            pass

        update_overview_stats(
            project_count=project_count,
            agent_count=agent_count,
            tool_count=tool_count
        )
        update_inventory_projects(projects)

        # 패키지 인벤토리는 package_manager가 직접 관리
        try:
            from package_manager import package_manager
            package_manager._update_inventory()
        except:
            pass

        log_change("STATS_REFRESHED", f"Projects: {project_count}, Agents: {agent_count}, Tools: {tool_count}")

    except Exception as e:
        log_change("STATS_REFRESH_ERROR", str(e))
