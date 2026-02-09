import os
import glob
import re
import subprocess
import shlex
import shutil
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


def _validate_path_in_scope(path: str, project_path: str) -> str | None:
    """경로가 프로젝트 범위 내인지 검증. 벗어나면 에러 메시지 반환, 정상이면 None"""
    abs_path = os.path.abspath(path)
    abs_project = os.path.abspath(project_path)
    # 절대 경로로 시작하는 경우 (프로젝트 외부 접근) 허용
    # 상대 경로가 ../로 프로젝트 밖으로 나가는 경우만 차단
    if not abs_path.startswith(abs_project + os.sep) and abs_path != abs_project:
        return f"Error: 프로젝트 범위를 벗어나는 경로입니다: {abs_path}"
    return None


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
            # 대용량 파일 방어 (1MB 제한)
            MAX_READ_SIZE = 1_000_000
            file_size = os.path.getsize(path)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read(MAX_READ_SIZE)
            if file_size > MAX_READ_SIZE:
                content += f"\n\n... (파일이 {file_size // 1000}KB로 큽니다. 처음 1MB만 표시)"
            return content

        elif tool_name == "write_file":
            path = os.path.join(project_path, tool_input["file_path"])
            scope_err = _validate_path_in_scope(path, project_path)
            if scope_err:
                return scope_err
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
            max_results = 100

            # 검색 제외 디렉토리/확장자 (바이너리, 캐시, VCS)
            SKIP_DIRS = {'.git', '.svn', '__pycache__', 'node_modules', '.venv', 'venv', '.tox', '.mypy_cache'}
            SKIP_EXTS = {'.pyc', '.pyo', '.so', '.dylib', '.dll', '.exe', '.bin',
                         '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
                         '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv',
                         '.zip', '.gz', '.tar', '.rar', '.7z', '.bz2',
                         '.woff', '.woff2', '.ttf', '.eot', '.otf',
                         '.pdf', '.doc', '.docx', '.xls', '.xlsx',
                         '.db', '.sqlite', '.sqlite3'}

            # 검색할 파일 목록 가져오기 (불필요 파일 필터링)
            files = glob.glob(os.path.join(root, file_pattern), recursive=True)
            files = [
                f for f in files
                if os.path.isfile(f)
                and os.path.splitext(f)[1].lower() not in SKIP_EXTS
                and not any(skip in f.split(os.sep) for skip in SKIP_DIRS)
            ]

            results = []
            regex_pattern = re.compile(pattern) if use_regex else None
            search_done = False

            for file_path in files:
                if search_done:
                    break
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            if use_regex:
                                matched = regex_pattern.search(line)
                            else:
                                matched = pattern in line

                            if matched:
                                rel_path = os.path.relpath(file_path, project_path)
                                results.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                                if len(results) >= max_results:
                                    search_done = True
                                    break
                except (UnicodeDecodeError, PermissionError, OSError):
                    continue

            if results:
                if search_done:
                    return "\n".join(results) + f"\n... (결과가 {max_results}개에 도달하여 검색 중단)"
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
            scope_err = _validate_path_in_scope(file_path, project_path)
            if scope_err:
                return scope_err
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

        elif tool_name == "copy_path":
            src = os.path.join(project_path, tool_input["source"])
            dst = os.path.join(project_path, tool_input["destination"])
            scope_err = _validate_path_in_scope(dst, project_path)
            if scope_err:
                return scope_err

            if not os.path.exists(src):
                return f"Error: 원본이 존재하지 않습니다: {src}"

            # 대상 상위 디렉토리 생성
            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)

            if os.path.isdir(src):
                # 폴더 복사 (대상이 이미 있으면 삭제 후 복사)
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                count = sum(len(files) for _, _, files in os.walk(dst))
                return f"폴더를 복사했습니다: {os.path.abspath(dst)} ({count}개 파일)"
            else:
                # 파일 복사
                shutil.copy2(src, dst)
                return f"파일을 복사했습니다: {os.path.abspath(dst)}"

        elif tool_name == "move_path":
            src = os.path.join(project_path, tool_input["source"])
            dst = os.path.join(project_path, tool_input["destination"])
            scope_err = _validate_path_in_scope(dst, project_path)
            if scope_err:
                return scope_err

            if not os.path.exists(src):
                return f"Error: 원본이 존재하지 않습니다: {src}"

            # 대상 상위 디렉토리 생성
            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)

            # 대상이 이미 있으면 삭제
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)

            shutil.move(src, dst)
            return f"이동 완료: {os.path.abspath(dst)}"

        elif tool_name == "delete_path":
            target = os.path.join(project_path, tool_input["path"])
            scope_err = _validate_path_in_scope(target, project_path)
            if scope_err:
                return scope_err

            if not os.path.exists(target):
                return f"Error: 경로가 존재하지 않습니다: {target}"

            abs_target = os.path.abspath(target)

            if os.path.isdir(target):
                count = sum(len(files) for _, _, files in os.walk(target))
                shutil.rmtree(target)
                return f"폴더를 삭제했습니다: {abs_target} ({count}개 파일 포함)"
            else:
                os.remove(target)
                return f"파일을 삭제했습니다: {abs_target}"

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

        elif tool_name == "save_agent_note":
            # 에이전트 영구 메모 저장
            content = tool_input.get("content", "")
            append = tool_input.get("append", False)

            # 프로젝트 경로에서 note 파일 경로 결정
            project_dir = Path(project_path).resolve()

            # 시스템 AI인지 확인
            if str(project_dir).endswith("data") or project_dir == Path(".").resolve():
                note_file = SYSTEM_AI_STATE_PATH / "system_ai_note.txt"
            else:
                # 프로젝트 에이전트
                agent_name = agent_id.replace("agent_", "") if agent_id and agent_id.startswith("agent_") else agent_id
                note_file = project_dir / f"agent_{agent_name}_note.txt"

            note_file.parent.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

            if append and note_file.exists():
                # 기존 내용에 추가
                existing = note_file.read_text(encoding='utf-8')
                new_content = f"{existing}\n\n---\n[{timestamp}]\n{content}"
                note_file.write_text(new_content.strip(), encoding='utf-8')
            else:
                # 덮어쓰기 (맨 위에 갱신 시간 기록)
                new_content = f"[최종 갱신: {timestamp}]\n\n{content}"
                note_file.write_text(new_content, encoding='utf-8')

            # 파일 크기 경고 (5KB 초과 시)
            file_size = note_file.stat().st_size
            size_warning = ""
            if file_size > 5000:
                size_warning = f"\n\n⚠️ 메모가 {file_size // 1000}KB로 커졌습니다. read_agent_note로 현재 내용을 확인하고, 필요한 정보만 정리해서 append=false로 덮어쓰기하세요."

            return f"메모가 저장되었습니다: {note_file}{size_warning}"

        elif tool_name == "read_agent_note":
            # 에이전트 영구 메모 읽기
            project_dir = Path(project_path).resolve()

            # 시스템 AI인지 확인
            if str(project_dir).endswith("data") or project_dir == Path(".").resolve():
                note_file = SYSTEM_AI_STATE_PATH / "system_ai_note.txt"
            else:
                # 프로젝트 에이전트
                agent_name = agent_id.replace("agent_", "") if agent_id and agent_id.startswith("agent_") else agent_id
                note_file = project_dir / f"agent_{agent_name}_note.txt"

            if not note_file.exists():
                return "저장된 메모가 없습니다. save_agent_note로 메모를 저장하세요."

            content = note_file.read_text(encoding='utf-8')
            return f"=== 내 영구 메모 ===\n{content}"

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Error: {str(e)}"
