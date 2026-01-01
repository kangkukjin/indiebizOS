"""
system_docs.py - 시스템 문서 관리
IndieBiz OS Core

시스템 문서 계층 구조:
1. overview.md - 시스템 개요 및 사용자 안내 (항상 간략히 참조)
2. architecture.md - 시스템 구조 및 설계 의도
3. inventory.md - 설치된 것들 (프로젝트, 에이전트, 도구)
4. technical.md - 기술 상세 (API, 설정, 경로 등)
5. packages.md - 패키지 설치/제거 및 개발 가이드

시스템 AI는 필요할 때 해당 문서를 읽어서 참조합니다.
패키지 설치/제거 시에는 반드시 packages.md를 먼저 읽어야 합니다.
"""

import json
import os
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from runtime_utils import get_python_cmd, get_node_cmd

# 경로 설정
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH.parent / "data"
DOCS_PATH = DATA_PATH / "system_docs"


def ensure_docs_dir():
    """문서 디렉토리 생성"""
    DOCS_PATH.mkdir(parents=True, exist_ok=True)


def get_doc_path(doc_name: str) -> Path:
    """문서 경로 반환"""
    ensure_docs_dir()
    return DOCS_PATH / f"{doc_name}.md"


def read_doc(doc_name: str) -> str:
    """문서 읽기"""
    path = get_doc_path(doc_name)
    if path.exists():
        return path.read_text(encoding='utf-8')
    return ""


def write_doc(doc_name: str, content: str):
    """문서 쓰기"""
    path = get_doc_path(doc_name)
    path.write_text(content, encoding='utf-8')


def append_to_doc(doc_name: str, content: str):
    """문서에 내용 추가"""
    existing = read_doc(doc_name)
    write_doc(doc_name, existing + "\n" + content)


def list_docs() -> List[str]:
    """문서 목록"""
    ensure_docs_dir()
    return [f.stem for f in DOCS_PATH.glob("*.md")]


# ============ 초기 문서 템플릿 ============

def init_overview():
    """개요 문서 초기화"""
    if read_doc("overview"):
        return read_doc("overview")

    content = f"""# IndieBiz OS 시스템 개요

## IndieBiz의 의미

IndieBiz OS는 사람들에게 자유와 더 많은 가능성을 주기 위한 시스템입니다.

### 1. AI 프로바이더 선택의 자유
특정 AI 프로바이더에 종속되지 않습니다. 궁극적으로는 로컬 AI가 운영의 중심을 맡는 시대를 대비합니다.
사용자가 Anthropic, OpenAI, Google 중 선택할 수 있고, 올라마 확장으로 로컬 AI도 사용 가능합니다.

### 2. 열린 개발과 확장
중앙에서 통제하고 배포하는 시스템이 아닙니다. 사용자가 마음대로 개조할 수 있습니다.
AI와 함께라면 시스템을 부시고 늘려서 원하는대로 확장하는 것이 어렵지 않습니다.

### 3. 사용자 중심
수익을 위해 사용자를 플랫폼에 종속시키지 않습니다.
여러분의 하드웨어, 여러분의 정보는 여러분이 책임지고 사용합니다.
그것들이 항상 여러분의 통제 아래에 있어야 한다는 것이 IndieBiz의 기본철학입니다.

### 4. 소통과 IndieNet
탈중앙화 네트워크인 Nostr 채널을 기본으로 가지고 있습니다.
Gmail, Telegram, Matrix 등으로 채널을 확장할 수 있습니다.
AI와 소통하고, 이웃과 소통하고, AI 에이전트끼리 소통할 수 있습니다.
모두에게 열린 탈중앙화 망 IndieNet에서 더 많은 가능성이 생겨날 것입니다.

## 3가지 오브젝트 타입

IndieBiz는 바탕화면 같은 공간에 3종류의 오브젝트를 배치할 수 있는 OS입니다.

### 1. 프로젝트 (Project)
프로젝트는 AI 에이전트들의 팀입니다. 여러 에이전트를 프로젝트에 추가할 수 있고,
각 에이전트는 개별적으로 AI 프로바이더, 프롬프트, 도구를 설정할 수 있습니다.

- **복사 가능**: 프로젝트를 통째로 복사해서 새 프로젝트를 만들 수 있습니다
- **템플릿화**: 유용한 프로젝트를 템플릿으로 저장하여 재사용할 수 있습니다
- **예시**: 블로그 작성팀(기획자+작가+편집자), 연구팀(검색원+분석가+요약가) 등

### 2. 스위치 (Switch)
스위치는 자동화를 위한 오브젝트입니다. 자연어 명령을 저장해두고
한 번의 클릭으로 실행할 수 있습니다.

- **자연어 자동화**: "오늘 뉴스 요약해줘", "이메일 확인해서 중요한 것만 알려줘" 등
- **빠른 실행**: 자주 쓰는 명령을 스위치로 만들어 클릭 한 번으로 실행
- **커스터마이징**: 스위치에 연결할 에이전트와 도구를 지정 가능

### 3. 폴더 (Folder)
폴더는 프로젝트와 스위치를 정리하기 위한 오브젝트입니다.

- 프로젝트와 스위치를 폴더 안에 넣어 정리
- 폴더 안에 폴더를 넣을 수도 있음
- 바탕화면을 깔끔하게 유지

## 에이전트 유형

### 외부 에이전트 (External Agent)
Nostr, Gmail, Telegram 등의 소통 채널을 가진 에이전트입니다.
- 원격에서 명령을 받을 수 있음
- 외출 중에도 메시지로 에이전트에게 작업 지시 가능
- IndieNet을 통해 다른 사용자의 에이전트와 소통 가능

### 내부 에이전트 (Internal Agent)
소통 채널이 없는 에이전트입니다.
- IndieBiz OS 내에서만 동작
- 프로젝트 내 다른 에이전트와만 협업
- 보안이 중요한 작업에 적합

## 현재 상태
- 마지막 업데이트: {datetime.now().strftime("%Y-%m-%d %H:%M")}
- 프로젝트 수: 0
- 에이전트 수: 0
- 설치된 도구 패키지: 0

---
*이 문서는 시스템 AI가 사용자 안내 시 참조합니다.*
"""
    write_doc("overview", content)
    return content


def init_architecture():
    """아키텍처 문서 초기화"""
    if read_doc("architecture"):
        return read_doc("architecture")

    content = f"""# IndieBiz OS 아키텍처

## 시스템 구조

```
indiebizOS/
├── backend/           # FastAPI 백엔드
│   ├── api.py        # 메인 서버
│   ├── api_*.py      # 각 모듈 라우터
│   └── data/         # 데이터 저장소
├── frontend/         # Electron + React 프론트엔드
│   └── src/
└── data/             # 공유 데이터
    ├── projects/     # 프로젝트 데이터
    └── system_docs/  # 시스템 문서
```

## 핵심 컴포넌트

### 시스템 AI
- IndieBiz의 관리자이자 안내자
- 시스템 설정의 AI 프로바이더 사용
- 사용자 정보(단기기억)와 시스템 문서(장기기억) 참조

### 프로젝트 매니저
- 프로젝트 생성, 수정, 삭제
- 에이전트 관리
- 대화 이력 관리

### 도구 시스템
- manifest.yaml 기반 도구 패키지
- 에이전트별 도구 배분
- 함수 호출(tool use) 지원

## 설계 원칙
1. 최소주의: 핵심 기능만 코어에 포함
2. 확장성: 도구 패키지로 기능 확장
3. 독립성: 각 컴포넌트는 독립적으로 동작

---
*마지막 업데이트: {datetime.now().strftime("%Y-%m-%d %H:%M")}*
"""
    write_doc("architecture", content)
    return content


def init_inventory():
    """인벤토리 문서 초기화"""
    if read_doc("inventory"):
        return read_doc("inventory")

    content = f"""# IndieBiz OS 인벤토리

## 프로젝트
(아직 프로젝트가 없습니다)

## 에이전트
(아직 에이전트가 없습니다)

## 도구 패키지
(아직 설치된 도구 패키지가 없습니다)

## 스위치
(아직 스위치가 없습니다)

---
*마지막 업데이트: {datetime.now().strftime("%Y-%m-%d %H:%M")}*
"""
    write_doc("inventory", content)
    return content


def init_technical():
    """기술 문서 초기화"""
    if read_doc("technical"):
        return read_doc("technical")

    content = f"""# IndieBiz OS 기술 문서

## API 엔드포인트

### 프로젝트
- GET /projects - 프로젝트 목록
- POST /projects - 프로젝트 생성
- GET /projects/{{id}} - 프로젝트 조회
- PUT /projects/{{id}} - 프로젝트 수정
- DELETE /projects/{{id}} - 프로젝트 삭제

### 에이전트
- GET /projects/{{id}}/agents - 에이전트 목록
- POST /projects/{{id}}/agents - 에이전트 생성
- PUT /projects/{{id}}/agents/{{agent_id}} - 에이전트 수정
- DELETE /projects/{{id}}/agents/{{agent_id}} - 에이전트 삭제

### 시스템 AI
- POST /system-ai/chat - 시스템 AI와 대화
- GET /system-ai/status - 상태 확인
- GET /system-ai/conversations - 대화 이력

### IndieNet
- POST /indienet/generate - ID 생성
- GET /indienet/profile - 프로필 조회
- POST /indienet/post - 포스트 작성

## 설정 파일 위치
- 시스템 AI 설정: data/system_ai_config.json
- 사용자 프로필: data/my_profile.txt
- IndieNet 설정: data/indienet_config.json

## 지원 AI 프로바이더
- Anthropic Claude (claude-sonnet-4, claude-3.5-sonnet, claude-3.5-haiku)
- OpenAI GPT (gpt-4o, gpt-4o-mini, gpt-4-turbo)
- Google Gemini (gemini-2.0-flash, gemini-1.5-pro, gemini-1.5-flash)

---
*마지막 업데이트: {datetime.now().strftime("%Y-%m-%d %H:%M")}*
"""
    write_doc("technical", content)
    return content


def init_all_docs():
    """모든 문서 초기화"""
    init_overview()
    init_architecture()
    init_inventory()
    init_technical()


# ============ 문서 업데이트 함수들 ============

def update_inventory_projects(projects: List[Dict[str, Any]]):
    """프로젝트 목록 업데이트"""
    content = read_doc("inventory")

    # 프로젝트 섹션 업데이트
    project_section = "## 프로젝트\n"
    if projects:
        for p in projects:
            project_section += f"- **{p.get('name', 'Unknown')}** (ID: {p.get('id', '?')})\n"
            if p.get('description'):
                project_section += f"  - {p['description']}\n"
    else:
        project_section += "(아직 프로젝트가 없습니다)\n"

    # 기존 프로젝트 섹션 교체
    import re
    content = re.sub(
        r'## 프로젝트\n.*?(?=\n## |\n---)',
        project_section,
        content,
        flags=re.DOTALL
    )

    # 타임스탬프 업데이트
    content = re.sub(
        r'\*마지막 업데이트:.*\*',
        f'*마지막 업데이트: {datetime.now().strftime("%Y-%m-%d %H:%M")}*',
        content
    )

    write_doc("inventory", content)


def update_inventory_agents(project_id: str, agents: List[Dict[str, Any]]):
    """에이전트 목록 업데이트 (특정 프로젝트)"""
    # 기술적으로는 프로젝트별로 에이전트를 기록해야 함
    # 간단히 전체 에이전트 수만 개요에 업데이트
    pass


def update_inventory_packages(installed_tools: List[Dict], installed_extensions: List[Dict]):
    """인벤토리 문서의 패키지 설치 상태만 빠르게 업데이트"""
    content = read_doc("inventory")
    if not content:
        return

    import re

    # 도구 패키지 섹션에서 상태만 업데이트
    installed_tool_ids = {pkg['id'] for pkg in installed_tools}
    installed_ext_ids = {pkg['id'] for pkg in installed_extensions}

    # 테이블 행의 상태 업데이트 (미설치 -> 설치됨 또는 그 반대)
    def update_status(match):
        row = match.group(0)
        # ID 추출 (첫 번째 | 뒤의 값)
        parts = row.split('|')
        if len(parts) >= 2:
            pkg_id = parts[1].strip()
            # 도구 섹션인지 확장 섹션인지 확인하고 상태 변경
            if pkg_id in installed_tool_ids or pkg_id in installed_ext_ids:
                return row.replace('미설치', '설치됨')
            else:
                return row.replace('설치됨', '미설치')
        return row

    # 각 테이블 행 업데이트
    content = re.sub(r'\|[^|]+\|[^|]+\|[^|]+\| (미설치|설치됨) \|', update_status, content)

    # 타임스탬프 업데이트
    content = re.sub(
        r'\*마지막 업데이트:.*\*',
        f'*마지막 업데이트: {datetime.now().strftime("%Y-%m-%d %H:%M")}*',
        content
    )

    write_doc("inventory", content)


def update_overview_stats(project_count: int = None, agent_count: int = None, tool_count: int = None):
    """개요 문서의 통계 업데이트 (변경된 값만 업데이트)"""
    content = read_doc("overview")
    if not content:
        return

    import re

    if project_count is not None:
        content = re.sub(
            r'- 프로젝트 수: \d+',
            f'- 프로젝트 수: {project_count}',
            content
        )

    if agent_count is not None:
        content = re.sub(
            r'- 에이전트 수: \d+',
            f'- 에이전트 수: {agent_count}',
            content
        )

    if tool_count is not None:
        content = re.sub(
            r'- 설치된 패키지: \d+',
            f'- 설치된 패키지: {tool_count}',
            content
        )

    content = re.sub(
        r'- 마지막 업데이트:.*',
        f'- 마지막 업데이트: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        content
    )

    write_doc("overview", content)


def log_change(action: str, details: str):
    """변경 이력 로그"""
    log_path = DOCS_PATH / "changelog.log"
    ensure_docs_dir()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {action}: {details}\n"

    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(log_entry)


# ============ 시스템 AI용 도구 정의 ============

SYSTEM_AI_TOOLS = [
    {
        "name": "read_system_doc",
        "description": "시스템 문서를 읽습니다. 사용 가능한 문서: overview(개요), architecture(구조), inventory(인벤토리), technical(기술), packages(패키지 가이드). 패키지 설치/제거 시에는 반드시 packages 문서를 먼저 읽으세요.",
        "parameters": {
            "type": "object",
            "properties": {
                "doc_name": {
                    "type": "string",
                    "enum": ["overview", "architecture", "inventory", "technical", "packages"],
                    "description": "읽을 문서 이름"
                }
            },
            "required": ["doc_name"]
        }
    },
    {
        "name": "list_system_docs",
        "description": "사용 가능한 시스템 문서 목록을 확인합니다",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "list_packages",
        "description": "설치 가능한 도구 패키지 목록을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_package_info",
        "description": "특정 패키지의 상세 정보를 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "package_id": {
                    "type": "string",
                    "description": "패키지 ID"
                }
            },
            "required": ["package_id"]
        }
    },
    {
        "name": "install_package",
        "description": "도구 패키지를 설치합니다. 사용자의 동의를 받은 후에만 이 도구를 사용하세요.",
        "parameters": {
            "type": "object",
            "properties": {
                "package_id": {
                    "type": "string",
                    "description": "설치할 패키지 ID"
                }
            },
            "required": ["package_id"]
        }
    }
]


def execute_system_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """시스템 AI 도구 실행"""
    if tool_name == "read_system_doc":
        doc_name = arguments.get("doc_name", "")
        content = read_doc(doc_name)
        if content:
            return content
        else:
            # 없으면 초기화
            if doc_name == "overview":
                return init_overview()
            elif doc_name == "architecture":
                return init_architecture()
            elif doc_name == "inventory":
                return init_inventory()
            elif doc_name == "technical":
                return init_technical()
            return f"문서 '{doc_name}'을 찾을 수 없습니다."

    elif tool_name == "list_system_docs":
        docs = list_docs()
        if docs:
            return "사용 가능한 문서: " + ", ".join(docs)
        return "아직 생성된 문서가 없습니다."

    elif tool_name == "list_packages":
        from package_manager import package_manager
        packages = package_manager.list_available("tools")

        if not packages:
            return "설치 가능한 패키지가 없습니다."

        result = []
        for pkg in packages:
            status = "✅ 설치됨" if pkg.get("installed") else "⬜ 미설치"
            result.append(f"- **{pkg['name']}** ({pkg['id']}) {status}")
            result.append(f"  {pkg['description']}")

        return f"## 도구 패키지 목록\n\n" + "\n".join(result)

    elif tool_name == "get_package_info":
        from package_manager import package_manager
        package_id = arguments.get("package_id", "")
        info = package_manager.get_package_info(package_id)

        if not info:
            return f"패키지를 찾을 수 없습니다: {package_id}"

        result = [
            f"## {info['name']}",
            f"- **ID**: {info['id']}",
            f"- **버전**: {info.get('version', '1.0.0')}",
            f"- **상태**: {'설치됨' if info.get('installed') else '미설치'}",
            f"\n{info['description']}"
        ]

        if info.get("tools"):
            result.append("\n### 제공 도구")
            for tool in info["tools"]:
                result.append(f"- **{tool['name']}**: {tool['description']}")

        if info.get("features"):
            result.append("\n### 기능")
            for feature in info["features"]:
                result.append(f"- {feature}")

        if info.get("dependencies"):
            result.append(f"\n### 의존성: {', '.join(info['dependencies'])}")

        if info.get("requires_api_key"):
            result.append(f"\n⚠️ {info['requires_api_key'].upper()} API 키가 필요합니다.")

        if info.get("requires_external"):
            result.append(f"\n⚠️ {info['requires_external']}")

        return "\n".join(result)

    elif tool_name == "install_package":
        from package_manager import package_manager
        package_id = arguments.get("package_id", "")

        try:
            result = package_manager.install_package(package_id, "tools")
            return f"✅ {result['message']}"
        except ValueError as e:
            return f"❌ 설치 실패: {str(e)}"
        except Exception as e:
            return f"❌ 오류 발생: {str(e)}"

    # 파일 시스템 도구
    elif tool_name == "read_file":
        file_path = arguments.get("file_path", "")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    elif tool_name == "write_file":
        file_path = arguments.get("file_path", "")
        content = arguments.get("content", "")
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True) if os.path.dirname(file_path) else None
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return json.dumps({"success": True, "message": f"파일 저장 완료: {file_path}"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    elif tool_name == "list_directory":
        dir_path = arguments.get("dir_path", str(DATA_PATH))
        try:
            items = os.listdir(dir_path)
            result = []
            for item in items:
                full_path = os.path.join(dir_path, item)
                item_type = "dir" if os.path.isdir(full_path) else "file"
                result.append({"name": item, "type": item_type})
            return json.dumps({"success": True, "items": result}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    # 코드 실행 도구
    elif tool_name == "execute_python":
        code = arguments.get("code", "")
        try:
            python_cmd = get_python_cmd()
            result = subprocess.run(
                [python_cmd, "-c", code],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(DATA_PATH)
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            return output if output else "(실행 완료, 출력 없음)"
        except subprocess.TimeoutExpired:
            return "실행 시간 초과 (60초)"
        except Exception as e:
            return f"실행 오류: {str(e)}"

    elif tool_name == "execute_node":
        code = arguments.get("code", "")
        try:
            node_cmd = get_node_cmd()
            result = subprocess.run(
                [node_cmd, "-e", code],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(DATA_PATH)
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            return output if output else "(실행 완료, 출력 없음)"
        except subprocess.TimeoutExpired:
            return "실행 시간 초과 (60초)"
        except Exception as e:
            return f"실행 오류: {str(e)}"

    elif tool_name == "run_command":
        command = arguments.get("command", "")
        # 위험한 명령어 필터링
        dangerous = ["rm -rf", "rmdir /s", "format", "mkfs", "dd if="]
        for d in dangerous:
            if d in command:
                return json.dumps({"success": False, "error": f"위험한 명령어 차단: {d}"}, ensure_ascii=False)
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(DATA_PATH)
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            return output if output else "(실행 완료, 출력 없음)"
        except subprocess.TimeoutExpired:
            return "실행 시간 초과 (120초)"
        except Exception as e:
            return f"실행 오류: {str(e)}"

    return f"알 수 없는 도구: {tool_name}"


# 모듈 로드 시 문서 디렉토리 생성
ensure_docs_dir()
