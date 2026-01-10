"""
api_helpers.py - API 공통 헬퍼 함수
IndieBiz OS Core

에이전트 규칙 파일(rules.json) 관리
- 공통설정, 역할, 영구메모 변경 시 rules.json 자동 업데이트
"""

from pathlib import Path
from conversation_db import ConversationDB


def update_agent_rules_json(agent_name: str, project_path: Path):
    """
    txt 파일들을 읽어서 agent_{name}_rules.json 업데이트
    공통설정, 역할, 영구메모 중 하나라도 변경되면 호출

    Args:
        agent_name: 에이전트 이름
        project_path: 프로젝트 경로
    """
    # txt 파일들 읽기
    common_content = ""
    role_content = ""
    note_content = ""

    common_file = project_path / "common_settings.txt"
    if common_file.exists():
        common_content = common_file.read_text(encoding='utf-8').strip()

    role_file = project_path / f"agent_{agent_name}_role.txt"
    if role_file.exists():
        role_content = role_file.read_text(encoding='utf-8').strip()

    note_file = project_path / f"agent_{agent_name}_note.txt"
    if note_file.exists():
        note_content = note_file.read_text(encoding='utf-8').strip()

    # rules.json 생성
    ConversationDB.save_rules_history(
        agent_name=agent_name,
        system_prompt=common_content,
        role=role_content,
        persistent_note=note_content,
        project_path=str(project_path)
    )

    print(f"[Rules] {agent_name} rules.json 업데이트 완료")


def update_all_agents_rules_json(project_path: Path):
    """
    프로젝트 내 모든 에이전트의 rules.json 업데이트
    공통설정 변경 시 호출

    Args:
        project_path: 프로젝트 경로
    """
    import yaml

    agents_file = project_path / "agents.yaml"
    if not agents_file.exists():
        print(f"[Rules] agents.yaml 없음: {project_path}")
        return

    with open(agents_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    updated_count = 0
    for agent in data.get("agents", []):
        agent_name = agent.get("name")
        if agent_name:
            update_agent_rules_json(agent_name, project_path)
            updated_count += 1

    print(f"[Rules] 프로젝트 내 {updated_count}개 에이전트 rules.json 업데이트 완료")
