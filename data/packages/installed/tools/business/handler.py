"""
business/handler.py
비즈니스 관계 및 연락처(이웃) 관리 도구
"""

import sys
from pathlib import Path


def execute(tool_name: str, tool_input: dict, project_path: str = ".", agent_id: str = None) -> str:
    """비즈니스 도구 실행"""
    try:
        # backend 경로 추가 (business_manager 임포트용)
        backend_path = str(Path(__file__).parent.parent.parent.parent.parent / "backend")
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)

        from business_manager import BusinessManager
        bm = BusinessManager()

        if tool_name == "get_neighbors":
            # 이웃 목록 조회
            search = tool_input.get("search")
            info_level = tool_input.get("info_level")

            neighbors = bm.get_neighbors(search=search, info_level=info_level)

            if not neighbors:
                return "등록된 이웃이 없습니다."

            # 결과 포맷팅
            result_lines = [f"이웃 목록 ({len(neighbors)}명):"]
            for n in neighbors:
                fav_mark = "[즐겨찾기]" if n.get('favorite') else ""
                level_str = f"Lv.{n.get('info_level', 0)}"
                rating_str = f"★{n.get('rating', 0)}" if n.get('rating') else ""
                result_lines.append(f"  - {n['name']} (ID:{n['id']}) {level_str} {rating_str} {fav_mark}".strip())

            return "\n".join(result_lines)

        elif tool_name == "send_email":
            # Gmail로 이메일 전송
            to = tool_input.get("to")
            subject = tool_input.get("subject")
            body = tool_input.get("body")
            attachment_path = tool_input.get("attachment_path")

            if not to or not subject or not body:
                return "Error: to, subject, body는 필수입니다."

            # 에이전트의 이메일 주소 가져오기
            agent_email = None
            if agent_id and project_path:
                import yaml
                agents_file = Path(project_path) / "agents.yaml"
                if agents_file.exists():
                    with open(agents_file, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                    for agent in data.get("agents", []):
                        if agent.get("id") == agent_id:
                            agent_email = agent.get("email")
                            break

            if not agent_email:
                return "Error: 에이전트에 이메일이 설정되어 있지 않습니다. 에이전트 설정에서 이메일을 먼저 설정하세요."

            # Gmail 클라이언트로 발송
            from api_gmail import get_gmail_client_for_email
            client = get_gmail_client_for_email(agent_email)
            client.send_message(to=to, subject=subject, body=body, attachment_path=attachment_path)

            return f"이메일 발송 완료: {to}에게 '{subject}' 제목으로 발송했습니다."

        elif tool_name == "get_neighbor_detail":
            # 이웃 상세 조회
            neighbor_id = tool_input.get("neighbor_id")
            name = tool_input.get("name")

            if not neighbor_id and not name:
                return "Error: neighbor_id 또는 name 중 하나는 필수입니다."

            # 이름으로 검색 시 ID 찾기
            if name and not neighbor_id:
                neighbors = bm.get_neighbors(search=name)
                exact_match = [n for n in neighbors if n['name'] == name]
                if not exact_match:
                    return f"'{name}' 이름의 이웃을 찾을 수 없습니다."
                neighbor_id = exact_match[0]['id']

            # 이웃 상세 정보 조회
            neighbor = bm.get_neighbor(neighbor_id)
            if not neighbor:
                return f"ID {neighbor_id}의 이웃을 찾을 수 없습니다."

            # 연락처 조회
            contacts = bm.get_contacts(neighbor_id)

            # 최근 메시지 조회 (최근 5개)
            messages = bm.get_messages(neighbor_id=neighbor_id, limit=5)

            # 결과 포맷팅
            result_lines = [
                f"=== {neighbor['name']} (ID: {neighbor['id']}) ===",
                f"정보 레벨: {neighbor.get('info_level', 0)}",
                f"평가: {'★' * neighbor.get('rating', 0) if neighbor.get('rating') else '없음'}",
                f"즐겨찾기: {'예' if neighbor.get('favorite') else '아니오'}",
            ]

            # 추가 정보
            if neighbor.get('additional_info'):
                result_lines.append(f"\n[메모]\n{neighbor['additional_info']}")

            # 비즈니스 문서
            if neighbor.get('business_doc'):
                result_lines.append(f"\n[비즈니스 정보]\n{neighbor['business_doc']}")

            # 연락처
            if contacts:
                result_lines.append("\n[연락처]")
                for c in contacts:
                    result_lines.append(f"  - {c['contact_type']}: {c['contact_value']}")
            else:
                result_lines.append("\n[연락처] 없음")

            # 최근 메시지
            if messages:
                result_lines.append("\n[최근 메시지]")
                for m in messages[:5]:
                    direction = "← 수신" if not m.get('is_from_user') else "→ 발신"
                    content_preview = m['content'][:50] + "..." if len(m['content']) > 50 else m['content']
                    result_lines.append(f"  {direction} ({m.get('created_at', '')[:10]}): {content_preview}")

            return "\n".join(result_lines)

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Error: {str(e)}"
