import os
import glob
import re
import subprocess
import shlex
from datetime import datetime

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

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
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
            return f"Successfully wrote to {tool_input['file_path']}"

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

            # 상대 경로로 변환하고 정렬
            relative_paths = sorted([
                os.path.relpath(m, project_path) for m in matches
            ])

            if relative_paths:
                return "\n".join(relative_paths)
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

            return f"Successfully edited {tool_input['file_path']}"

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

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Error: {str(e)}"
