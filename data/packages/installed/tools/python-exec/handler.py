"""
python-exec 도구 핸들러
"""
import json
import os
import subprocess
import platform
from pathlib import Path
from datetime import datetime

# 대용량 출력 저장 경로
OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "outputs" / "python_exec"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 출력 길이 임계값 (이 이상이면 파일로 저장)
OUTPUT_THRESHOLD = 3000


def get_python_cmd():
    """번들된 Python 또는 시스템 Python 경로 반환

    우선순위:
    1. INDIEBIZ_PYTHON_PATH 환경변수 (Electron에서 설정)
    2. INDIEBIZ_RUNTIME_PATH/python 경로
    3. 폴더 탐색으로 runtime 찾기
    4. 시스템 Python (폴백)
    """
    # 1. 환경변수에서 직접 Python 경로 확인 (가장 확실한 방법)
    env_python = os.environ.get("INDIEBIZ_PYTHON_PATH")
    if env_python and Path(env_python).exists():
        return env_python

    # 기본값 (시스템 Python)
    is_windows = platform.system() == "Windows"
    python_cmd = "python" if is_windows else "python3"

    # 2. INDIEBIZ_RUNTIME_PATH 환경변수에서 runtime 경로 확인
    env_runtime = os.environ.get("INDIEBIZ_RUNTIME_PATH")
    if env_runtime:
        runtime_path = Path(env_runtime)
        if runtime_path.exists():
            if is_windows:
                bundled_python = runtime_path / "python" / "python.exe"
            else:
                bundled_python = runtime_path / "python" / "bin" / "python3"

            if bundled_python.exists():
                return str(bundled_python)

    # 3. 폴더 탐색 (개발 환경 또는 환경변수 미설정 시)
    current = Path(__file__).parent
    while current.parent != current:
        if (current / "backend").exists():
            runtime_path = current / "runtime"
            break
        current = current.parent
    else:
        return python_cmd

    # Electron extraResources 경로도 확인
    if not runtime_path.exists():
        resources_path = current.parent / "Resources" / "runtime"
        if resources_path.exists():
            runtime_path = resources_path

    if runtime_path.exists():
        if is_windows:
            bundled_python = runtime_path / "python" / "python.exe"
        else:
            bundled_python = runtime_path / "python" / "bin" / "python3"

        if bundled_python.exists():
            python_cmd = str(bundled_python)

    return python_cmd


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """
    Python 코드 실행 도구

    Args:
        tool_name: 도구 이름 (이 패키지에서는 "execute_python")
        tool_input: 도구 입력 파라미터
        project_path: 프로젝트 경로

    Returns:
        실행 결과 문자열
    """
    if tool_name == "execute_python":
        code = tool_input.get("code", "")
        try:
            python_cmd = get_python_cmd()
            result = subprocess.run(
                [python_cmd, "-c", code],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=project_path
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"

            if not output:
                return "(실행 완료, 출력 없음)"

            # 출력이 임계값을 초과하면 파일로 저장
            if len(output) > OUTPUT_THRESHOLD:
                return _save_large_output(output)

            return output

        except subprocess.TimeoutExpired:
            return "실행 시간 초과 (30초)"
        except Exception as e:
            return f"실행 오류: {str(e)}"

    return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)


def _save_large_output(output: str) -> str:
    """대용량 출력을 파일로 저장하고 요약 반환"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 출력 형식 분석
    format_info = _detect_format(output)

    # 파일 확장자 결정
    ext_map = {"JSON": "json", "CSV": "csv", "TSV": "tsv"}
    ext = ext_map.get(format_info["type"], "txt")
    filename = f"python_output_{timestamp}.{ext}"
    filepath = OUTPUT_DIR / filename

    # 파일로 저장
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(output)

    # 미리보기 (처음 500자)
    preview = output[:500]
    if len(output) > 500:
        preview += "\n... (이하 생략)"

    # 구조 설명 생성
    structure_desc = _format_structure_description(format_info)

    result = {
        "success": True,
        "message": f"출력이 {len(output):,}자로 커서 파일로 저장했습니다.",
        "file_path": str(filepath),
        "total_length": len(output),
        "format": format_info["type"],
        "structure": format_info.get("structure"),
        "structure_description": structure_desc,
        "preview": preview
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


def _format_structure_description(format_info: dict) -> str:
    """구조 정보를 읽기 쉬운 설명으로 변환"""
    fmt_type = format_info.get("type", "텍스트")
    structure = format_info.get("structure")

    if not structure:
        return fmt_type

    if fmt_type == "JSON":
        if structure.get("type") == "array":
            count = structure.get("item_count", 0)
            fields = structure.get("item_fields", [])
            field_types = structure.get("field_types", {})

            if fields:
                # 필드 타입 정보 포함
                field_descs = []
                for f in fields[:10]:  # 최대 10개 필드
                    ftype = field_types.get(f, "")
                    if ftype:
                        field_descs.append(f"{f}({ftype})")
                    else:
                        field_descs.append(f)

                fields_str = ", ".join(field_descs)
                if len(fields) > 10:
                    fields_str += f" 외 {len(fields)-10}개"
                return f"JSON 배열 ({count}개 항목), 각 항목 필드: [{fields_str}]"
            return f"JSON 배열 ({count}개 항목)"
        elif structure.get("type") == "object":
            keys = structure.get("keys", [])
            return f"JSON 객체, 키: {', '.join(keys[:10])}"

    elif fmt_type in ("CSV", "TSV"):
        cols = structure.get("columns", [])
        rows = structure.get("row_count", 0)
        return f"{fmt_type} ({rows}행), 컬럼: {', '.join(cols[:10])}"

    elif structure.get("line_count"):
        return f"텍스트 ({structure['line_count']}줄)"

    return fmt_type


def _detect_format(output: str) -> dict:
    """출력 형식 및 구조 감지"""
    output_stripped = output.strip()
    result = {"type": "텍스트", "structure": None}

    # JSON 형식 확인
    if output_stripped.startswith('{') or output_stripped.startswith('['):
        try:
            parsed = json.loads(output_stripped)
            result["type"] = "JSON"
            result["structure"] = _analyze_json_structure(parsed)
            return result
        except:
            pass

    # CSV 형식 확인 (콤마 구분, 여러 줄)
    lines = output_stripped.split('\n')
    if len(lines) > 1:
        first_commas = lines[0].count(',')
        if first_commas > 0 and all(line.count(',') == first_commas for line in lines[:5] if line.strip()):
            result["type"] = "CSV"
            result["structure"] = {
                "columns": lines[0].split(',') if lines else [],
                "row_count": len(lines) - 1
            }
            return result

    # 탭 구분 확인
    if '\t' in output_stripped:
        first_tabs = lines[0].count('\t')
        if first_tabs > 0 and all(line.count('\t') == first_tabs for line in lines[:5] if line.strip()):
            result["type"] = "TSV"
            result["structure"] = {
                "columns": lines[0].split('\t') if lines else [],
                "row_count": len(lines) - 1
            }
            return result

    # 테이블 형식 (줄로 구분된 데이터)
    if len(lines) > 5:
        result["type"] = "텍스트"
        result["structure"] = {"line_count": len(lines)}

    return result


def _analyze_json_structure(data) -> dict:
    """JSON 데이터의 구조 분석"""
    if isinstance(data, list):
        if len(data) == 0:
            return {"type": "array", "item_count": 0, "item_fields": []}

        # 첫 번째 항목의 구조 분석
        first_item = data[0]
        if isinstance(first_item, dict):
            fields = list(first_item.keys())
            # 필드별 타입 추론
            field_types = {}
            for key, value in first_item.items():
                if isinstance(value, (int, float)):
                    field_types[key] = "number"
                elif isinstance(value, str):
                    # 날짜 형식 감지
                    if len(value) == 10 and '-' in value:
                        field_types[key] = "date"
                    else:
                        field_types[key] = "string"
                elif isinstance(value, bool):
                    field_types[key] = "boolean"
                elif isinstance(value, list):
                    field_types[key] = "array"
                elif isinstance(value, dict):
                    field_types[key] = "object"
                else:
                    field_types[key] = "unknown"

            return {
                "type": "array",
                "item_count": len(data),
                "item_fields": fields,
                "field_types": field_types
            }
        else:
            return {"type": "array", "item_count": len(data), "item_type": type(first_item).__name__}

    elif isinstance(data, dict):
        return {
            "type": "object",
            "keys": list(data.keys())[:20]  # 최대 20개 키만
        }

    return {"type": type(data).__name__}
