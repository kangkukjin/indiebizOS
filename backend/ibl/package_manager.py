"""
package_manager.py - 도구 패키지 관리 시스템
IndieBiz OS Core

설계 원칙:
- 도구 패키지만 관리 (extensions 개념 폐기)
- 폴더 구조가 유일한 진실의 원천 (Single Source of Truth)
- AI가 폴더를 분석하여 유효성 판별 및 README 자동 생성

packages/
├── not_installed/tools/  # 설치되지 않은 도구 패키지
│   └── youtube/
├── installed/tools/      # 설치된 도구 패키지
│   └── time/
└── dev/tools/            # 개발 중인 도구 패키지

available = not_installed + installed (논리적 합집합)
설치: not_installed → installed로 이동
삭제: installed → not_installed로 이동
"""

import json
import shutil
import asyncio
import inspect
import importlib.util
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from runtime_utils import get_python_cmd


def _log_pkg_file_write(path):
    """쓰기 관문 원장 — AI 패키지 파일 생성·수정 사건(관측, 실패 무해)."""
    try:
        from write_ledger import log_write
        log_write(path, event="write", gate="package_files")
    except Exception:
        pass

# 경로 설정
BACKEND_PATH = Path(__file__).parent.parent
from runtime_utils import get_base_path as _get_base_path
DATA_PATH = _get_base_path() / "data"
PACKAGES_PATH = DATA_PATH / "packages"
NOT_INSTALLED_PATH = PACKAGES_PATH / "not_installed"
INSTALLED_PATH = PACKAGES_PATH / "installed"
CORE_MANIFEST_PATH = DATA_PATH / "core_manifest.json"


# ============ 표준 코어 경계 (origin 해소) ============
# core_manifest.json = 배포에 딸려온 "표준 코어" 집합의 단일 진실
# (scripts/build_core_manifest.py 가 git 추적 집합에서 파생·커밋).
# 매니페스트에 없는 패키지 = 사용자가 나중에 더한 것 = origin:user.
_CORE_PACKAGE_NAMES: Optional[set] = None


def _load_core_package_names() -> set:
    """core_manifest.json 에서 코어 패키지 이름 집합 로드 (프로세스 캐시)."""
    global _CORE_PACKAGE_NAMES
    if _CORE_PACKAGE_NAMES is not None:
        return _CORE_PACKAGE_NAMES
    names: set = set()
    try:
        if CORE_MANIFEST_PATH.exists():
            with open(CORE_MANIFEST_PATH, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            pkgs = manifest.get("core", {}).get("packages", {})
            names.update(pkgs.get("tools", []))
            names.update(pkgs.get("extensions", []))
    except Exception as e:
        print(f"[PackageManager] core_manifest 로드 실패 (모두 user로 간주): {e}")
    _CORE_PACKAGE_NAMES = names
    return names


def resolve_package_origin(package_id: str) -> str:
    """패키지 origin 판정: 매니페스트에 있으면 'core', 없으면 'user'."""
    return "core" if package_id in _load_core_package_names() else "user"


def invalidate_core_manifest_cache() -> None:
    """매니페스트 재생성 후 origin 캐시 무효화."""
    global _CORE_PACKAGE_NAMES
    _CORE_PACKAGE_NAMES = None


def validate_tool_package(pkg_path: Path) -> Dict[str, Any]:
    """
    도구 패키지 검증

    검증 항목:
    1. tool.json 존재 및 유효한 JSON
    2. handler.py 존재
    3. handler.py에 execute() 함수 존재
    4. execute() 함수 시그니처가 (tool_name, args, project_path) 형식
    5. tool.json의 모든 도구가 handler.py에서 처리 가능

    Returns:
        {
            "valid": True/False,
            "errors": ["에러 메시지들"],
            "warnings": ["경고 메시지들"],
            "tools": ["도구 이름들"]
        }
    """
    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "tools": []
    }

    # 1. tool.json 확인
    tool_json_path = pkg_path / "tool.json"
    if not tool_json_path.exists():
        result["valid"] = False
        result["errors"].append("tool.json 파일이 없습니다")
        return result

    try:
        tool_data = json.loads(tool_json_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        result["valid"] = False
        result["errors"].append(f"tool.json이 유효한 JSON이 아닙니다: {e}")
        return result

    # 도구 목록 추출
    tools = []
    if isinstance(tool_data, list):
        tools = tool_data
    elif isinstance(tool_data, dict):
        if "tools" in tool_data:
            tools = tool_data["tools"]
        elif "name" in tool_data:
            tools = [tool_data]

    tool_names = [t.get("name") for t in tools if t.get("name")]
    result["tools"] = tool_names

    if not tool_names:
        result["valid"] = False
        result["errors"].append("tool.json에 도구가 정의되어 있지 않습니다")
        return result

    # 2. handler.py 확인
    handler_path = pkg_path / "handler.py"
    if not handler_path.exists():
        result["valid"] = False
        result["errors"].append("handler.py 파일이 없습니다")
        return result

    # 3. handler.py 로드 및 execute 함수 확인
    try:
        spec = importlib.util.spec_from_file_location("temp_handler", handler_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        result["valid"] = False
        result["errors"].append(f"handler.py 로드 실패: {e}")
        return result

    if not hasattr(module, 'execute'):
        result["valid"] = False
        result["errors"].append("handler.py에 execute() 함수가 없습니다")
        return result

    # 4. execute() 시그니처 확인
    execute_func = getattr(module, 'execute')
    sig = inspect.signature(execute_func)
    params = list(sig.parameters.keys())

    # 최소 2개 파라미터 필요 (tool_name, args)
    # 3개면 완벽 (tool_name, args, project_path)
    if len(params) < 2:
        result["valid"] = False
        result["errors"].append(f"execute() 함수는 최소 2개 파라미터가 필요합니다. 현재: {params}")
        return result

    if len(params) == 2:
        result["warnings"].append(
            f"execute() 함수가 2개 파라미터만 받습니다: {params}. "
            "project_path를 세 번째 파라미터로 추가하는 것을 권장합니다."
        )

    # 5. handler.py 코드에서 도구 처리 확인
    handler_code = handler_path.read_text(encoding='utf-8')
    missing_tools = []
    for tool_name in tool_names:
        # tool_name이 handler 코드에 언급되는지 확인
        if f'"{tool_name}"' not in handler_code and f"'{tool_name}'" not in handler_code:
            missing_tools.append(tool_name)

    if missing_tools:
        result["warnings"].append(
            f"다음 도구들이 handler.py에서 처리되지 않을 수 있습니다: {missing_tools}"
        )

    return result


def ensure_package_dirs():
    """패키지 디렉토리 생성"""
    (NOT_INSTALLED_PATH / "tools").mkdir(parents=True, exist_ok=True)
    (INSTALLED_PATH / "tools").mkdir(parents=True, exist_ok=True)


class PackageManager:
    """도구 패키지 관리자"""

    # 클래스 레벨 캐시 (싱글톤처럼 동작)
    _packages_cache: List[Dict[str, Any]] = []
    _cache_time: float = 0
    _cache_ttl: float = 60.0  # 60초 캐시 유효시간

    def __init__(self):
        ensure_package_dirs()
        self._cache = {}

    def _is_cache_valid(self) -> bool:
        """캐시 유효성 확인"""
        import time
        return (PackageManager._packages_cache and
                time.time() - PackageManager._cache_time < PackageManager._cache_ttl)

    def invalidate_cache(self):
        """캐시 무효화 (패키지 설치/제거 시 호출)"""
        PackageManager._packages_cache = []
        PackageManager._cache_time = 0
        # 표준 코어 매니페스트도 다시 읽어야 재생성된 origin 경계가 반영된다
        invalidate_core_manifest_cache()
        # tool_loader의 도구↔패키지 매핑도 함께 비워야 신규/변경된 tool.json이 반영된다
        try:
            from tool_loader import clear_cache as _clear_tool_loader_cache
            _clear_tool_loader_cache()
        except Exception as e:
            raise RuntimeError(f"tool_loader 캐시 무효화 실패: {e}") from e

    # ============ 핵심: 폴더 스캔 ============

    def _scan_package(self, pkg_path: Path) -> Dict[str, Any]:
        """단일 패키지 폴더 스캔하여 메타데이터 추출"""
        pkg_id = pkg_path.name

        metadata = {
            "id": pkg_id,
            "name": pkg_id.replace('-', ' ').replace('_', ' ').title(),
            "description": "",
            "type": "tools",
        }

        # README에서 설명 추출
        for doc_file in ['README.md', 'readme.md', 'README.txt']:
            doc_path = pkg_path / doc_file
            if doc_path.exists():
                try:
                    content = doc_path.read_text(encoding='utf-8')
                    lines = content.strip().split('\n')
                    desc_lines = []
                    for line in lines:
                        line = line.strip()
                        if line.startswith('#') or not line:
                            if desc_lines:
                                break
                            continue
                        desc_lines.append(line)
                        if len(desc_lines) >= 2:
                            break
                    if desc_lines:
                        metadata["description"] = ' '.join(desc_lines)[:200]
                except:
                    pass
                break

        # 파일 목록
        files = [f.name for f in pkg_path.iterdir()
                 if f.is_file() and not f.name.startswith('.')]
        metadata["files"] = files

        # tool.json에서 패키지 설명 및 도구 목록 추출
        tool_json_path = pkg_path / "tool.json"
        if tool_json_path.exists():
            try:
                tool_data = json.loads(tool_json_path.read_text(encoding='utf-8'))
                tools = []
                if isinstance(tool_data, list):
                    tools = tool_data
                elif isinstance(tool_data, dict):
                    # 패키지 레벨 description 추출 (README보다 우선)
                    if tool_data.get("description"):
                        metadata["description"] = tool_data["description"][:500]
                    # 패키지 레벨 name 추출
                    if tool_data.get("name"):
                        metadata["name"] = tool_data["name"]
                    # 패키지 레벨 version 추출
                    if tool_data.get("version"):
                        metadata["version"] = tool_data["version"]

                    if "tools" in tool_data:
                        tools = tool_data["tools"]
                    elif "name" in tool_data and "input_schema" in tool_data:
                        # 단일 도구 형식
                        tools = [tool_data]

                metadata["tools"] = [
                    {"name": t.get("name", ""), "description": t.get("description", "")}
                    for t in tools if t.get("name")
                ]
            except:
                pass

        # origin: 표준 코어(배포 동봉) vs 사용자 추가
        metadata["origin"] = resolve_package_origin(pkg_id)
        from vocabulary_policy import required_packages
        metadata["required"] = pkg_id in required_packages()

        return metadata

    def _scan_all_packages(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """보유 전체. installed는 호환 필드이며 폴더 대신 활성 선택을 뜻한다."""
        from vocabulary_state import inventory, is_active
        packages = []
        for pid, entry in inventory().get("packages", {}).items():
            info = self._scan_package(entry["path"])
            info.update(installed=is_active(pid), active=is_active(pid), package_type="tools")
            packages.append(info)
        return packages

    def list_available(self, package_type: str = None) -> List[Dict[str, Any]]:
        return self._scan_all_packages()

    def list_installed(self, package_type: str = None) -> List[Dict[str, Any]]:
        return [p for p in self._scan_all_packages() if p["active"]]

    def get_package_info(self, package_id: str, package_type: str = None) -> Optional[Dict[str, Any]]:
        """패키지 정보 조회"""
        installed_path = INSTALLED_PATH / "tools" / package_id
        not_installed_path = NOT_INSTALLED_PATH / "tools" / package_id

        # 설치된 패키지
        if installed_path.exists():
            pkg_info = self._scan_package(installed_path)
            from vocabulary_state import is_active
            pkg_info["installed"] = is_active(package_id)
            pkg_info["package_type"] = "tools"
            pkg_info["path"] = str(installed_path)
            return pkg_info
        # 미설치 패키지
        elif not_installed_path.exists():
            pkg_info = self._scan_package(not_installed_path)
            from vocabulary_state import is_active
            pkg_info["installed"] = is_active(package_id)
            pkg_info["package_type"] = "tools"
            pkg_info["path"] = str(not_installed_path)
            return pkg_info
        return None

    # ============ 패키지 설치/제거 ============

    def install_package(self, package_id: str, package_type: str = None,
                        skip_validation: bool = False, *, authority=None) -> Dict[str, Any]:
        """보유 묶음을 깨우는 호환 진입점. 파일 이동·AI 설치·코퍼스 재생성 없음."""
        from vocabulary_lifecycle import set_package_active
        return set_package_active(package_id, True, authority=authority)

    async def install_package_with_ai(self, package_id: str, api_key: str,
                                      provider: str = "google", model: str = None):
        """옛 자동 설치는 사람의 어휘 선택을 대신하지 않는다."""
        return self.install_package(package_id)

    def uninstall_package(self, package_id: str, package_type: str = None,
                          *, authority=None) -> Dict[str, Any]:
        """잠재우기. 파일·설정·용례·벡터와 건강 기록을 보존한다."""
        from vocabulary_policy import require_optional
        require_optional(package_id)
        from vocabulary_lifecycle import set_package_active
        return set_package_active(package_id, False, authority=authority)

    def _update_inventory(self):
        """inventory.md 전체 재생성"""
        try:
            from system_docs import read_doc, write_doc

            # 현재 상태 스캔
            tools = self._scan_all_packages()

            # inventory.md 내용 생성
            self._regenerate_inventory_md(tools)

        except Exception as e:
            print(f"[PackageManager] inventory.md 업데이트 실패: {e}")

    def _regenerate_inventory_md(self, tools: List[Dict]):
        """inventory.md 전체 재생성"""
        from system_docs import read_doc, write_doc

        # 기존 내용에서 보존할 섹션 추출
        existing = read_doc("inventory")
        preserved_sections = self._extract_preserved_sections(existing)

        # 새 문서 생성
        lines = ["# IndieBiz OS 인벤토리", ""]

        # 보존된 섹션 추가 (프로젝트, 폴더)
        if preserved_sections.get("projects"):
            lines.extend(preserved_sections["projects"])
            lines.append("")

        if preserved_sections.get("folders"):
            lines.extend(preserved_sections["folders"])
            lines.append("")

        # 도구 패키지 섹션
        lines.append(f"## 도구 패키지 (Tools) - {len(tools)}개")
        lines.append("에이전트가 사용할 수 있는 유틸리티")
        lines.append("")
        lines.append("| ID | 이름 | 설명 | 상태 |")
        lines.append("|----|------|------|------|")
        for pkg in sorted(tools, key=lambda x: x['id']):
            status = "설치됨" if pkg.get("installed") else "미설치"
            desc = pkg.get("description", "").replace("\n", " ").replace("|", "/").strip()[:40]
            lines.append(f"| {pkg['id']} | {pkg['name']} | {desc} | {status} |")
        lines.append("")

        # 보존된 섹션 추가 (extensions·IBL 어휘 — 2026-08-21 시한폭탄 수리: 보존 목록에
        # 없어서 다음 재생성 한 번에 두 절이 통째로 사라질 상태였다. IBL 어휘 절의
        # 마커 구간은 build_ibl_nodes 가 재생성하므로 여기서는 통째로 보존만 한다.)
        if preserved_sections.get("extensions"):
            lines.extend(preserved_sections["extensions"])
            lines.append("")

        if preserved_sections.get("ibl"):
            lines.extend(preserved_sections["ibl"])
            lines.append("")

        # 보존된 섹션 추가 (템플릿, 스위치, 에이전트)
        if preserved_sections.get("templates"):
            lines.extend(preserved_sections["templates"])
            lines.append("")

        if preserved_sections.get("switches"):
            lines.extend(preserved_sections["switches"])
            lines.append("")

        if preserved_sections.get("agents"):
            lines.extend(preserved_sections["agents"])
            lines.append("")

        # 타임스탬프
        lines.append("---")
        lines.append(f"*마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

        write_doc("inventory", "\n".join(lines))

    def _extract_preserved_sections(self, content: str) -> Dict[str, List[str]]:
        """기존 inventory.md에서 보존할 섹션 추출"""
        sections = {
            "projects": [],
            "folders": [],
            "extensions": [],
            "ibl": [],
            "templates": [],
            "switches": [],
            "agents": []
        }

        if not content:
            return sections

        current_section = None
        current_lines = []

        def _flush():
            # 섹션 끝의 빈 줄은 보존하지 않음 (재생성 시 매번 새로 붙기 때문에 누적 방지)
            while current_lines and current_lines[-1] == "":
                current_lines.pop()
            if current_section:
                sections[current_section] = current_lines

        for line in content.split('\n'):
            if line.startswith('## 프로젝트'):
                _flush()
                current_section = "projects"
                current_lines = [line]
            elif line.startswith('## 폴더'):
                _flush()
                current_section = "folders"
                current_lines = [line]
            elif line.startswith('## 도구'):
                _flush()
                current_section = None
                current_lines = []
            elif line.startswith('## 백엔드'):
                _flush()
                current_section = "extensions"
                current_lines = [line]
            elif line.startswith('## IBL'):
                _flush()
                current_section = "ibl"
                current_lines = [line]
            elif line.startswith('## 템플릿'):
                _flush()
                current_section = "templates"
                current_lines = [line]
            elif line.startswith('## 스위치'):
                _flush()
                current_section = "switches"
                current_lines = [line]
            elif line.startswith('## 에이전트'):
                _flush()
                current_section = "agents"
                current_lines = [line]
            elif line.startswith('---'):
                _flush()
                current_section = None
                current_lines = []
            elif current_section:
                current_lines.append(line)
        _flush()

        if current_section:
            sections[current_section] = current_lines

        return sections

    # ============ AI 기반 폴더 분석 ============

    def analyze_folder_basic(self, folder_path: str) -> Dict[str, Any]:
        """폴더 기본 분석 (AI 없이)"""
        folder = Path(folder_path)

        if not folder.exists():
            return {"valid": False, "error": "폴더가 존재하지 않습니다"}

        if not folder.is_dir():
            return {"valid": False, "error": "폴더가 아닙니다"}

        all_files = []
        for f in folder.iterdir():
            if f.is_file() and not f.name.startswith('.'):
                all_files.append(f.name)

        if not all_files:
            return {"valid": False, "error": "폴더가 비어있습니다"}

        py_files = [f for f in all_files if f.endswith('.py')]
        json_files = [f for f in all_files if f.endswith('.json')]
        has_tool_json = 'tool.json' in json_files
        has_handler = 'handler.py' in py_files
        has_readme = any(f.lower() in ['readme.md', 'readme.txt'] for f in all_files)

        # 파일 내용 수집 (AI 분석용)
        file_contents = {}
        for fname in all_files[:10]:  # 최대 10개 파일만
            fpath = folder / fname
            try:
                if fpath.suffix in ['.py', '.json', '.md', '.txt']:
                    content = fpath.read_text(encoding='utf-8')
                    if len(content) > 5000:
                        content = content[:5000] + "\n... (truncated)"
                    file_contents[fname] = content
            except:
                pass

        return {
            "valid": None,  # AI가 판단 필요
            "folder_name": folder.name,
            "folder_path": str(folder),
            "files": all_files,
            "py_files": py_files,
            "json_files": json_files,
            "has_tool_json": has_tool_json,
            "has_handler": has_handler,
            "has_readme": has_readme,
            "file_contents": file_contents,
            "suggested_name": folder.name.replace('-', ' ').replace('_', ' ').title()
        }

    async def analyze_folder_with_ai(self, folder_path: str, api_key: str, provider: str = "anthropic", model: str = None) -> Dict[str, Any]:
        """AI를 사용하여 폴더 분석 및 패키지 유효성 판별"""
        # 기본 분석 수행
        basic_analysis = self.analyze_folder_basic(folder_path)

        if basic_analysis.get("error"):
            return basic_analysis

        # AI에게 분석 요청
        file_contents = basic_analysis.get("file_contents", {})
        files_summary = "\n\n".join([
            f"=== {fname} ===\n{content}"
            for fname, content in file_contents.items()
        ])

        prompt = f"""다음 폴더를 분석하여 IndieBiz OS의 도구 패키지로 등록 가능한지 판별해주세요.

폴더명: {basic_analysis['folder_name']}
파일 목록: {', '.join(basic_analysis['files'])}
Python 파일: {', '.join(basic_analysis['py_files'])}
tool.json 존재: {basic_analysis['has_tool_json']}
handler.py 존재: {basic_analysis['has_handler']}
README 존재: {basic_analysis['has_readme']}

파일 내용:
{files_summary}

---

도구 패키지의 요구사항:
1. tool.json 파일이 있어야 함 (도구 정의: name, description, input_schema)
2. handler.py 파일이 있어야 함 (execute 함수 구현)
3. 또는 이 두 파일을 자동 생성할 수 있을 만큼 충분한 정보가 있어야 함

다음 JSON 형식으로 응답해주세요:
{{
    "valid": true/false,
    "reason": "판별 이유",
    "package_name": "패키지 이름",
    "package_description": "패키지 설명 (한 문장)",
    "tools": [
        {{"name": "도구명", "description": "도구 설명"}}
    ],
    "missing_files": ["필요하지만 없는 파일"],
    "can_auto_generate": true/false,
    "readme_content": "생성할 README.md 내용 (마크다운)"
}}"""

        try:
            if provider == "anthropic":
                result = await self._analyze_with_anthropic(prompt, api_key, model)
            elif provider in ["openai", "gpt"]:
                result = await self._analyze_with_openai(prompt, api_key, model)
            elif provider in ["google", "gemini"]:
                result = await self._analyze_with_gemini(prompt, api_key, model)
            else:
                return {**basic_analysis, "valid": False, "error": f"지원하지 않는 AI 프로바이더: {provider}"}

            # JSON 파싱
            import re
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                analysis_result = json.loads(json_match.group())
                return {
                    **basic_analysis,
                    **analysis_result
                }
            else:
                return {**basic_analysis, "valid": False, "error": "AI 응답을 파싱할 수 없습니다"}

        except Exception as e:
            return {**basic_analysis, "valid": False, "error": f"AI 분석 실패: {str(e)}"}

    async def _analyze_with_anthropic(self, prompt: str, api_key: str, model: str = None) -> str:
        """Anthropic Claude로 분석"""
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model or "claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    async def _analyze_with_openai(self, prompt: str, api_key: str, model: str = None) -> str:
        """OpenAI GPT로 분석"""
        import openai
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model or "gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content

    async def _analyze_with_gemini(self, prompt: str, api_key: str, model: str = None) -> str:
        """Google Gemini로 분석 - google-genai 버전"""
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model or "gemini-2.0-flash-exp",
            contents=prompt
        )
        return response.text

    # ============ 패키지 등록 ============

    def register_folder(self, folder_path: str, name: str = None, description: str = None,
                        readme_content: str = None, package_type: str = None) -> Dict[str, Any]:
        """폴더를 도구 패키지로 등록 (AI가 생성한 README 포함)"""
        folder = Path(folder_path)

        if not folder.exists() or not folder.is_dir():
            raise ValueError("유효한 폴더가 아닙니다")

        pkg_id = folder.name
        dst_path = NOT_INSTALLED_PATH / "tools" / pkg_id

        if dst_path.exists():
            raise ValueError(f"이미 등록된 패키지입니다: {pkg_id}")

        # 복사
        shutil.copytree(folder, dst_path)

        # README 생성/업데이트
        readme_path = dst_path / "README.md"
        if readme_content:
            # AI가 생성한 README 사용
            readme_path.write_text(readme_content, encoding='utf-8')
        elif name or description:
            # 수동 입력
            pkg_name = name or pkg_id.replace('-', ' ').replace('_', ' ').title()
            content = f"# {pkg_name}\n\n{description or ''}\n"
            readme_path.write_text(content, encoding='utf-8')

        # inventory.md 업데이트
        self._update_inventory()

        metadata = self._scan_package(dst_path)
        return {
            "status": "registered",
            "package_id": pkg_id,
            "package_type": "tools",
            "metadata": metadata,
            "message": f"'{metadata['name']}' 패키지가 등록되었습니다."
        }

    def remove_package(self, package_id: str, package_type: str = None,
                       *, authority=None) -> Dict[str, Any]:
        """옛 삭제 진입점도 잠재우기로 수렴한다. 개인 자료의 삭제는 별도 작업이다."""
        return self.uninstall_package(package_id, authority=authority)

    def get_package_files(self, package_id: str, package_type: str = None) -> List[str]:
        """패키지 내 파일 목록"""
        pkg_path = NOT_INSTALLED_PATH / "tools" / package_id
        if not pkg_path.exists():
            return []

        files = []
        for f in pkg_path.rglob('*'):
            if f.is_file() and not f.name.startswith('.'):
                rel_path = f.relative_to(pkg_path)
                files.append(str(rel_path))
        return files

    def read_package_file(self, package_id: str, package_type: str, file_path: str) -> Optional[str]:
        """패키지 내 파일 읽기"""
        pkg_path = NOT_INSTALLED_PATH / "tools" / package_id
        full_path = pkg_path / file_path

        # 보안: 패키지 경로 밖으로 나가는 것 방지
        try:
            full_path.resolve().relative_to(pkg_path.resolve())
        except ValueError:
            return None

        if not full_path.exists():
            return None

        try:
            return full_path.read_text(encoding='utf-8')
        except:
            return None

    def update_package_metadata(self, package_id: str, package_type: str = None,
                                 name: str = None, description: str = None) -> Dict[str, Any]:
        """패키지 README.md 업데이트로 메타데이터 변경"""
        pkg_path = NOT_INSTALLED_PATH / "tools" / package_id
        if not pkg_path.exists():
            raise ValueError(f"패키지를 찾을 수 없습니다: {package_id}")

        readme_path = pkg_path / "README.md"

        # 새 README 내용 생성
        new_name = name or package_id.replace('-', ' ').replace('_', ' ').title()
        new_desc = description or ""

        content = f"# {new_name}\n\n{new_desc}\n"
        readme_path.write_text(content, encoding='utf-8')

        # inventory.md 업데이트
        self._update_inventory()

        return self._scan_package(pkg_path)

    # 하위 호환성을 위한 메서드 (deprecated)
    def analyze_folder(self, folder_path: str) -> Dict[str, Any]:
        """폴더 분석 (하위 호환성)"""
        return self.analyze_folder_basic(folder_path)


# ============ 패키지 인코더/디코더 (Nostr 공유용) ============

def encode_package(package_id: str, include_description: bool = True) -> str:
    """
    패키지를 Nostr 메시지용 텍스트로 인코딩

    Args:
        package_id: 패키지 ID
        include_description: AI 설명 포함 여부

    Returns:
        인코딩된 텍스트 (구분자로 파일 경계 표시)

    포맷:
        ===PACKAGE_START===
        id: package_id
        name: Package Name
        description: 패키지 설명

        ===FILE:filename.ext===
        파일 내용

        ===FILE:another.py===
        파일 내용

        ===PACKAGE_END===
    """
    # 패키지 경로 찾기
    pkg_path = INSTALLED_PATH / "tools" / package_id
    if not pkg_path.exists():
        pkg_path = NOT_INSTALLED_PATH / "tools" / package_id
    if not pkg_path.exists():
        raise ValueError(f"패키지를 찾을 수 없습니다: {package_id}")

    lines = [
        "===PACKAGE_START===",
        "[IndieBiz OS Package Format v1]",
        "[이 코드를 참조하여 사용자 환경에 맞게 설치하세요]",
        ""
    ]

    # 메타데이터
    lines.append(f"id: {package_id}")

    # tool.json에서 이름과 설명 추출
    tool_json_path = pkg_path / "tool.json"
    pkg_name = package_id
    pkg_desc = ""

    if tool_json_path.exists():
        try:
            tool_data = json.loads(tool_json_path.read_text(encoding='utf-8'))
            if isinstance(tool_data, dict):
                pkg_name = tool_data.get("name", package_id)
                pkg_desc = tool_data.get("description", "")
            elif isinstance(tool_data, list) and tool_data:
                pkg_name = tool_data[0].get("name", package_id)
                pkg_desc = tool_data[0].get("description", "")
        except:
            pass

    lines.append(f"name: {pkg_name}")
    if pkg_desc:
        lines.append(f"description: {pkg_desc}")
    lines.append("")

    # 파일들 추가
    # 우선순위: tool.json, handler.py, 기타 .py, requirements.txt, 기타
    priority_files = ["tool.json", "handler.py"]
    other_py = []
    other_files = []

    for f in pkg_path.iterdir():
        if f.is_file() and not f.name.startswith('.'):
            if f.name in priority_files:
                continue
            elif f.suffix == '.py':
                other_py.append(f.name)
            elif f.name in ['requirements.txt', 'package.json']:
                other_files.insert(0, f.name)  # 앞에 추가
            elif f.suffix in ['.md', '.txt', '.json', '.yaml', '.yml']:
                other_files.append(f.name)

    # 파일 순서 결정
    file_order = []
    for pf in priority_files:
        if (pkg_path / pf).exists():
            file_order.append(pf)
    file_order.extend(sorted(other_py))
    file_order.extend(other_files)

    # 파일 내용 추가
    for filename in file_order:
        file_path = pkg_path / filename
        if file_path.exists():
            try:
                content = file_path.read_text(encoding='utf-8')
                lines.append(f"===FILE:{filename}===")
                lines.append(content)
                lines.append("")  # 파일 간 구분
            except:
                pass  # 바이너리 파일 등은 스킵

    lines.append("===PACKAGE_END===")

    return "\n".join(lines)


def decode_package(encoded_text: str, target_dir: Path = None) -> Dict[str, Any]:
    """
    인코딩된 텍스트를 패키지 폴더로 디코딩

    Args:
        encoded_text: encode_package()로 생성된 텍스트
        target_dir: 저장할 디렉토리 (기본: not_installed/tools/)

    Returns:
        {
            "success": True/False,
            "package_id": "id",
            "package_path": "/path/to/package",
            "files_created": ["file1.py", "file2.json"],
            "error": "에러 메시지 (실패 시)"
        }
    """
    if target_dir is None:
        target_dir = NOT_INSTALLED_PATH / "tools"

    result = {
        "success": False,
        "package_id": None,
        "package_path": None,
        "files_created": [],
        "error": None
    }

    # 유효성 검사
    if "===PACKAGE_START===" not in encoded_text or "===PACKAGE_END===" not in encoded_text:
        result["error"] = "유효하지 않은 패키지 형식입니다"
        return result

    # 패키지 부분만 추출
    start_idx = encoded_text.find("===PACKAGE_START===")
    end_idx = encoded_text.find("===PACKAGE_END===")
    if start_idx == -1 or end_idx == -1:
        result["error"] = "패키지 경계를 찾을 수 없습니다"
        return result

    package_content = encoded_text[start_idx:end_idx + len("===PACKAGE_END===")]

    # 메타데이터 파싱
    lines = package_content.split("\n")
    package_id = None
    package_name = None
    package_desc = None

    i = 1  # ===PACKAGE_START=== 다음 줄부터
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("===FILE:"):
            break
        if line.startswith("id:"):
            package_id = line[3:].strip()
        elif line.startswith("name:"):
            package_name = line[5:].strip()
        elif line.startswith("description:"):
            package_desc = line[12:].strip()
        i += 1

    if not package_id:
        result["error"] = "패키지 ID를 찾을 수 없습니다"
        return result

    result["package_id"] = package_id

    # 패키지 폴더 생성
    pkg_path = target_dir / package_id
    if pkg_path.exists():
        result["error"] = f"이미 존재하는 패키지입니다: {package_id}"
        return result

    try:
        pkg_path.mkdir(parents=True, exist_ok=True)

        # 파일 파싱 및 저장
        current_file = None
        current_content = []

        for line in lines[i:]:
            if line.startswith("===FILE:") and line.endswith("==="):
                # 이전 파일 저장
                if current_file:
                    file_content = "\n".join(current_content).strip()
                    file_path = pkg_path / current_file
                    file_path.write_text(file_content, encoding='utf-8')
                    result["files_created"].append(current_file)
                    _log_pkg_file_write(file_path)

                # 새 파일 시작
                current_file = line[8:-3]  # ===FILE: 과 === 제거
                current_content = []
            elif line == "===PACKAGE_END===":
                # 마지막 파일 저장
                if current_file:
                    file_content = "\n".join(current_content).strip()
                    file_path = pkg_path / current_file
                    file_path.write_text(file_content, encoding='utf-8')
                    result["files_created"].append(current_file)
                    _log_pkg_file_write(file_path)
                break
            else:
                if current_file:
                    current_content.append(line)

        result["success"] = True
        result["package_path"] = str(pkg_path)

    except Exception as e:
        # 실패 시 정리
        if pkg_path.exists():
            shutil.rmtree(pkg_path)
        result["error"] = f"패키지 생성 실패: {str(e)}"

    return result


def get_package_for_sharing(package_id: str) -> str:
    """
    Nostr에 공유할 패키지 텍스트 생성 (encode_package의 래퍼)
    """
    return encode_package(package_id)


def install_package_from_text(encoded_text: str) -> Dict[str, Any]:
    """
    인코딩된 텍스트에서 패키지 설치 (decode_package + 검증)
    """
    # 디코딩
    decode_result = decode_package(encoded_text)

    if not decode_result["success"]:
        return decode_result

    package_id = decode_result["package_id"]
    pkg_path = Path(decode_result["package_path"])

    # 검증
    validation = validate_tool_package(pkg_path)

    decode_result["validation"] = validation

    if not validation["valid"]:
        decode_result["warnings"] = validation.get("errors", [])
    elif validation.get("warnings"):
        decode_result["warnings"] = validation["warnings"]

    return decode_result


# 전역 인스턴스
package_manager = PackageManager()
