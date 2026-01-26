import os
import glob
import re
import subprocess
import shlex
import json
from datetime import datetime
from pathlib import Path

# 시스템 AI 전용 상태 폴더 (data/system_ai_state/)
DATA_PATH = Path(__file__).parent.parent.parent.parent
SYSTEM_AI_STATE_PATH = DATA_PATH / "system_ai_state"


def get_state_paths(project_path: str, agent_id: str = None) -> dict:
    """에이전트별 상태 파일 경로 반환

    - 시스템 AI: data/system_ai_state/
    - 프로젝트 에이전트: projects/{project_id}/agent_{agent_id}_*.json
    """
    project_path = Path(project_path).resolve()

    # 시스템 AI인지 확인 (project_path가 data 폴더 또는 "."인 경우)
    if str(project_path).endswith("data") or project_path == Path(".").resolve():
        state_dir = SYSTEM_AI_STATE_PATH
        prefix = ""
    else:
        # 프로젝트 에이전트는 프로젝트 폴더에 상태 저장
        state_dir = project_path
        # 에이전트별 파일명 접두사 (agent_id가 있으면 사용)
        prefix = f"agent_{agent_id}_" if agent_id else ""

    # 폴더 생성
    state_dir.mkdir(parents=True, exist_ok=True)

    return {
        "todo": state_dir / f"{prefix}todo_state.json",
        "question": state_dir / f"{prefix}question_state.json",
        "plan_mode": state_dir / f"{prefix}plan_mode_state.json",
        "plan_file": state_dir / f"{prefix}current_plan.md"
    }


# 위험한 명령어 패턴 (사용자 승인 필요)
DANGEROUS_PATTERNS = [
    # 파일 삭제/수정
    'rm ', 'rm\t', 'rmdir', 'unlink',
    # 권한 관련
    'sudo', 'chmod', 'chown', 'chgrp',
    # 디스크 관련 위험 명령어
    'dd ', 'mkfs', 'format', 'diskutil erase', 'diskutil partitionDisk',
    # 시스템 종료/재시작
    'shutdown', 'reboot', 'halt',
    # 프로세스 종료
    'kill ', 'killall', 'pkill',
]


def is_dangerous_command(command: str) -> bool:
    """명령어가 위험한지 검사"""
    command_lower = command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in command_lower:
            return True
    return False

def execute(tool_name: str, tool_input: dict, project_path: str = ".", agent_id: str = None) -> str:
    try:
        if tool_name == "read_file":
            path = os.path.join(project_path, tool_input["file_path"])
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()

        elif tool_name == "write_file":
            path = os.path.join(project_path, tool_input["file_path"])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(tool_input["content"])
            # 절대 경로로 반환 (에이전트 간 경로 혼동 방지)
            abs_path = os.path.abspath(path)
            return f"Successfully wrote to {abs_path}"

        elif tool_name == "list_directory":
            dir_path = os.path.join(project_path, tool_input.get("dir_path", "."))
            items = os.listdir(dir_path)
            return "\n".join(items)

        elif tool_name == "grep_files":
            pattern = tool_input["pattern"]
            file_pattern = tool_input.get("file_pattern", "**/*")
            root = os.path.join(project_path, tool_input.get("root_path", "."))
            use_regex = tool_input.get("regex", False)

            # 검색할 파일 목록 가져오기
            files = glob.glob(os.path.join(root, file_pattern), recursive=True)
            files = [f for f in files if os.path.isfile(f)]

            results = []
            regex_pattern = re.compile(pattern) if use_regex else None

            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            matched = False
                            if use_regex:
                                if regex_pattern.search(line):
                                    matched = True
                            else:
                                if pattern in line:
                                    matched = True

                            if matched:
                                rel_path = os.path.relpath(file_path, project_path)
                                results.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                except:
                    continue

            if results:
                # 결과가 너무 많으면 제한
                if len(results) > 100:
                    return "\n".join(results[:100]) + f"\n... and {len(results) - 100} more matches"
                return "\n".join(results)
            else:
                return f"No matches found for: {pattern}"

        elif tool_name == "get_current_time":
            fmt = tool_input.get("format", "%Y-%m-%d %H:%M:%S")
            return datetime.now().strftime(fmt)

        elif tool_name == "glob_files":
            pattern = tool_input["pattern"]
            root = os.path.join(project_path, tool_input.get("root_path", "."))

            # recursive glob 지원
            matches = glob.glob(os.path.join(root, pattern), recursive=True)

            # 절대 경로로 변환하고 정렬 (에이전트 간 경로 혼동 방지)
            absolute_paths = sorted([
                os.path.abspath(m) for m in matches
            ])

            if absolute_paths:
                return "\n".join(absolute_paths)
            else:
                return f"No files matching pattern: {pattern}"

        elif tool_name == "edit_file":
            file_path = os.path.join(project_path, tool_input["file_path"])
            old_string = tool_input["old_string"]
            new_string = tool_input["new_string"]

            # 파일 읽기
            if not os.path.exists(file_path):
                return f"Error: 파일이 존재하지 않습니다: {tool_input['file_path']}"

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # old_string이 파일에 있는지 확인
            count = content.count(old_string)
            if count == 0:
                return f"Error: 교체할 문자열을 찾을 수 없습니다. 파일 내용을 다시 확인하세요."
            elif count > 1:
                return f"Error: 교체할 문자열이 {count}번 발견되었습니다. 더 구체적인 문자열을 지정하세요."

            # 교체 수행
            new_content = content.replace(old_string, new_string, 1)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            # 절대 경로로 반환 (에이전트 간 경로 혼동 방지)
            return f"Successfully edited {os.path.abspath(file_path)}"

        elif tool_name == "open_in_browser":
            import sys
            path = tool_input.get("path", "")
            if not path:
                return "Error: 경로가 지정되지 않았습니다."

            try:
                if sys.platform == "darwin":
                    subprocess.run(["open", path], check=True)
                elif sys.platform == "win32":
                    subprocess.run(["start", path], shell=True, check=True)
                else:
                    subprocess.run(["xdg-open", path], check=True)
                return f"브라우저에서 열었습니다: {path}"
            except Exception as e:
                return f"Error: 브라우저 열기 실패: {e}"

        elif tool_name == "run_command":
            command = tool_input.get("command", "").strip()
            timeout = min(tool_input.get("timeout", 60), 300)  # 최대 300초
            approved = tool_input.get("approved", False)

            if not command:
                return "Error: 명령어가 비어있습니다."

            # 위험한 명령어 감지 - 승인되지 않았으면 승인 요청
            if not approved and is_dangerous_command(command):
                return f"__REQUIRES_APPROVAL__:{command}"

            # 명령어 실행
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=project_path
                )

                output = ""
                if result.stdout:
                    output += result.stdout
                if result.stderr:
                    output += f"\n[stderr]\n{result.stderr}" if output else result.stderr

                if result.returncode != 0:
                    output += f"\n[exit code: {result.returncode}]"

                return output.strip() if output else "(명령어가 출력 없이 완료됨)"

            except subprocess.TimeoutExpired:
                return f"Error: 명령어 실행 시간 초과 ({timeout}초)"
            except Exception as e:
                return f"Error: 명령어 실행 실패: {e}"

        elif tool_name == "todo_write":
            todos = tool_input.get("todos", [])
            paths = get_state_paths(project_path, agent_id)

            # 상태 저장
            state = {
                "todos": todos,
                "updated_at": datetime.now().isoformat()
            }

            with open(paths["todo"], 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            # 결과 포맷팅 (텍스트 기반, Anthropic 스타일)
            result_lines = ["Todo list updated:"]
            for i, todo in enumerate(todos, 1):
                status = todo["status"]
                if status == "in_progress":
                    result_lines.append(f"  {i}. [in_progress] {todo['activeForm']}")
                elif status == "completed":
                    result_lines.append(f"  {i}. [completed] {todo['content']}")
                else:
                    result_lines.append(f"  {i}. [pending] {todo['content']}")

            return "\n".join(result_lines)

        elif tool_name == "ask_user_question":
            questions = tool_input.get("questions", [])
            paths = get_state_paths(project_path, agent_id)

            # 질문 상태 저장 (프론트엔드에서 폴링)
            state = {
                "questions": questions,
                "status": "pending",  # pending, answered
                "answers": None,
                "created_at": datetime.now().isoformat()
            }

            with open(paths["question"], 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            # 특수 마커와 함께 반환 - 프론트엔드가 질문 UI를 표시
            return "[[QUESTION_PENDING]]사용자에게 질문을 전달했습니다. 응답을 기다리는 중..."

        elif tool_name == "enter_plan_mode":
            paths = get_state_paths(project_path, agent_id)

            # 계획 모드 상태 저장
            state = {
                "active": True,
                "phase": "exploring",  # exploring, designing, reviewing, finalizing
                "entered_at": datetime.now().isoformat(),
                "plan_file": str(paths["plan_file"])
            }

            with open(paths["plan_mode"], 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            # 계획 파일 초기화
            with open(paths["plan_file"], 'w', encoding='utf-8') as f:
                f.write(f"# 구현 계획\n\n생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n## 목표\n\n(작성 중...)\n\n## 구현 단계\n\n1. \n\n## 수정할 파일\n\n- \n\n## 테스트 방법\n\n- \n")

            return "[[PLAN_MODE_ENTERED]]계획 모드로 진입했습니다. 코드를 탐색하고 구현 계획을 수립한 후 exit_plan_mode를 호출하세요."

        elif tool_name == "exit_plan_mode":
            paths = get_state_paths(project_path, agent_id)

            # 계획 모드 상태 확인
            if not paths["plan_mode"].exists():
                return "Error: 계획 모드가 활성화되어 있지 않습니다."

            with open(paths["plan_mode"], 'r', encoding='utf-8') as f:
                state = json.load(f)

            if not state.get("active"):
                return "Error: 계획 모드가 활성화되어 있지 않습니다."

            # 계획 파일 읽기
            plan_content = ""
            if paths["plan_file"].exists():
                with open(paths["plan_file"], 'r', encoding='utf-8') as f:
                    plan_content = f.read()

            # 상태 업데이트 - 승인 대기
            state["phase"] = "awaiting_approval"
            state["plan_content"] = plan_content

            with open(paths["plan_mode"], 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            return f"[[PLAN_APPROVAL_REQUESTED]]계획 수립이 완료되었습니다. 사용자 승인을 기다리는 중...\n\n---\n{plan_content}"

        elif tool_name == "get_neighbors":
            # 이웃 목록 조회
            search = tool_input.get("search")
            info_level = tool_input.get("info_level")

            try:
                # business_manager 임포트 (backend 경로 추가)
                import sys
                backend_path = str(Path(__file__).parent.parent.parent.parent.parent / "backend")
                if backend_path not in sys.path:
                    sys.path.insert(0, backend_path)

                from business_manager import BusinessManager
                bm = BusinessManager()
                neighbors = bm.get_neighbors(search=search, info_level=info_level)

                if not neighbors:
                    return "등록된 이웃이 없습니다."

                # 간략 정보만 반환
                result_lines = [f"이웃 목록 ({len(neighbors)}명):"]
                for n in neighbors:
                    fav_mark = "[즐겨찾기]" if n.get('favorite') else ""
                    level_str = f"Lv.{n.get('info_level', 0)}"
                    rating_str = f"★{n.get('rating', 0)}" if n.get('rating') else ""
                    result_lines.append(f"  - {n['name']} (ID:{n['id']}) {level_str} {rating_str} {fav_mark}".strip())

                return "\n".join(result_lines)

            except Exception as e:
                return f"Error: 이웃 목록 조회 실패 - {e}"

        elif tool_name == "get_neighbor_detail":
            # 이웃 상세 조회
            neighbor_id = tool_input.get("neighbor_id")
            name = tool_input.get("name")

            if not neighbor_id and not name:
                return "Error: neighbor_id 또는 name 중 하나는 필수입니다."

            try:
                import sys
                backend_path = str(Path(__file__).parent.parent.parent.parent.parent / "backend")
                if backend_path not in sys.path:
                    sys.path.insert(0, backend_path)

                from business_manager import BusinessManager
                bm = BusinessManager()

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

            except Exception as e:
                return f"Error: 이웃 상세 조회 실패 - {e}"

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Error: {str(e)}"
