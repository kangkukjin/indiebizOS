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
import inspect
import importlib.util
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# 경로 설정
BACKEND_PATH = Path(__file__).parent
from runtime_utils import get_base_path as _get_base_path
DATA_PATH = _get_base_path() / "data"
PACKAGES_PATH = DATA_PATH / "packages"
NOT_INSTALLED_PATH = PACKAGES_PATH / "not_installed"
INSTALLED_PATH = PACKAGES_PATH / "installed"


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

        # tool.json에서 도구 목록 추출
        tool_json_path = pkg_path / "tool.json"
        if tool_json_path.exists():
            try:
                tool_data = json.loads(tool_json_path.read_text(encoding='utf-8'))
                tools = []
                if isinstance(tool_data, list):
                    tools = tool_data
                elif isinstance(tool_data, dict):
                    if "tools" in tool_data:
                        tools = tool_data["tools"]
                    elif "name" in tool_data:
                        tools = [tool_data]

                metadata["tools"] = [
                    {"name": t.get("name", ""), "description": t.get("description", "")}
                    for t in tools if t.get("name")
                ]
            except:
                pass

        return metadata

    def _scan_all_packages(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """모든 도구 패키지 폴더 스캔 (not_installed + installed)

        Args:
            use_cache: 캐시 사용 여부 (기본 True)
        """
        import time

        # 캐시가 유효하면 캐시 반환
        if use_cache and self._is_cache_valid():
            return PackageManager._packages_cache

        packages = []

        # installed 폴더 스캔
        installed_path = INSTALLED_PATH / "tools"
        if installed_path.exists():
            for pkg_dir in installed_path.iterdir():
                if pkg_dir.is_dir() and not pkg_dir.name.startswith('.'):
                    pkg_info = self._scan_package(pkg_dir)
                    pkg_info["installed"] = True
                    pkg_info["package_type"] = "tools"
                    packages.append(pkg_info)

        # not_installed 폴더 스캔
        not_installed_path = NOT_INSTALLED_PATH / "tools"
        if not_installed_path.exists():
            for pkg_dir in not_installed_path.iterdir():
                if pkg_dir.is_dir() and not pkg_dir.name.startswith('.'):
                    pkg_info = self._scan_package(pkg_dir)
                    pkg_info["installed"] = False
                    pkg_info["package_type"] = "tools"
                    packages.append(pkg_info)

        # 캐시 업데이트
        PackageManager._packages_cache = packages
        PackageManager._cache_time = time.time()

        return packages

    # ============ 패키지 목록 API ============

    def list_available(self, package_type: str = None) -> List[Dict[str, Any]]:
        """설치 가능한 도구 패키지 목록"""
        # package_type 파라미터는 하위 호환성을 위해 무시
        return self._scan_all_packages()

    def list_installed(self, package_type: str = None) -> List[Dict[str, Any]]:
        """설치된 도구 패키지 목록"""
        packages = []
        tools_path = INSTALLED_PATH / "tools"

        if not tools_path.exists():
            return packages

        for pkg_dir in tools_path.iterdir():
            if pkg_dir.is_dir() and not pkg_dir.name.startswith('.'):
                pkg_info = self._scan_package(pkg_dir)
                pkg_info["installed"] = True
                pkg_info["package_type"] = "tools"

                # 설치 정보 로드
                install_info_path = pkg_dir / ".install_info.json"
                if install_info_path.exists():
                    try:
                        with open(install_info_path, 'r', encoding='utf-8') as f:
                            install_info = json.load(f)
                            pkg_info["installed_at"] = install_info.get("installed_at")
                    except:
                        pass

                packages.append(pkg_info)

        return packages

    def get_package_info(self, package_id: str, package_type: str = None) -> Optional[Dict[str, Any]]:
        """패키지 정보 조회"""
        installed_path = INSTALLED_PATH / "tools" / package_id
        not_installed_path = NOT_INSTALLED_PATH / "tools" / package_id

        # 설치된 패키지
        if installed_path.exists():
            pkg_info = self._scan_package(installed_path)
            pkg_info["installed"] = True
            pkg_info["package_type"] = "tools"
            pkg_info["path"] = str(installed_path)
            return pkg_info
        # 미설치 패키지
        elif not_installed_path.exists():
            pkg_info = self._scan_package(not_installed_path)
            pkg_info["installed"] = False
            pkg_info["package_type"] = "tools"
            pkg_info["path"] = str(not_installed_path)
            return pkg_info
        return None

    # ============ 패키지 설치/제거 ============

    def install_package(self, package_id: str, package_type: str = None, skip_validation: bool = False) -> Dict[str, Any]:
        """도구 패키지 설치 (not_installed → installed로 이동)"""
        src_path = NOT_INSTALLED_PATH / "tools" / package_id
        dst_path = INSTALLED_PATH / "tools" / package_id

        if not src_path.exists():
            raise ValueError(f"패키지를 찾을 수 없습니다: {package_id}")

        if dst_path.exists():
            raise ValueError(f"이미 설치된 패키지입니다: {package_id}")

        # 설치 전 검증
        validation = None
        if not skip_validation:
            validation = validate_tool_package(src_path)
            if not validation["valid"]:
                raise ValueError(f"패키지 검증 실패: {'; '.join(validation['errors'])}")

        # 이동 (복사가 아닌 이동)
        shutil.move(str(src_path), str(dst_path))

        # 설치 기록 (검증 결과 포함)
        install_info = {
            "installed_at": datetime.now().isoformat(),
            "ai_installed": False,
            "validation": validation
        }
        with open(dst_path / ".install_info.json", 'w', encoding='utf-8') as f:
            json.dump(install_info, f, ensure_ascii=False, indent=2)

        # 캐시 무효화
        self.invalidate_cache()

        # inventory.md 자동 업데이트
        self._update_inventory()

        pkg_info = self._scan_package(dst_path)
        result = {
            "status": "installed",
            "package": pkg_info,
            "message": f"'{pkg_info.get('name', package_id)}' 패키지가 설치되었습니다."
        }

        # 경고가 있으면 추가
        if validation and validation.get("warnings"):
            result["warnings"] = validation["warnings"]

        return result

    async def install_package_with_ai(self, package_id: str, api_key: str, provider: str = "google", model: str = None) -> Dict[str, Any]:
        """
        AI 기반 도구 패키지 설치

        1. README.md 분석하여 설치 요구사항 파악
        2. 필요한 라이브러리 설치 (pip install, npm install 등)
        3. handler.py가 없으면 AI가 생성
        4. tool.json이 없으면 AI가 생성
        5. 설치 완료 후 검증
        """
        import subprocess

        src_path = NOT_INSTALLED_PATH / "tools" / package_id
        dst_path = INSTALLED_PATH / "tools" / package_id

        if not src_path.exists():
            raise ValueError(f"패키지를 찾을 수 없습니다: {package_id}")

        if dst_path.exists():
            raise ValueError(f"이미 설치된 패키지입니다: {package_id}")

        # 1. 패키지 정보 수집
        readme_content = ""
        readme_path = src_path / "README.md"
        if readme_path.exists():
            readme_content = readme_path.read_text(encoding='utf-8')

        tool_json_exists = (src_path / "tool.json").exists()
        handler_exists = (src_path / "handler.py").exists()

        files_info = {}
        for f in src_path.iterdir():
            if f.is_file() and not f.name.startswith('.'):
                try:
                    content = f.read_text(encoding='utf-8')
                    if len(content) > 3000:
                        content = content[:3000] + "\n... (truncated)"
                    files_info[f.name] = content
                except:
                    files_info[f.name] = "(binary file)"

        # 2. AI에게 설치 계획 요청
        install_prompt = f"""IndieBiz OS 도구 패키지 '{package_id}'를 설치하려고 합니다.

패키지 정보:
- README.md: {readme_content or '(없음)'}
- tool.json 존재: {tool_json_exists}
- handler.py 존재: {handler_exists}

파일 내용:
{chr(10).join([f'=== {fname} ==={chr(10)}{content}' for fname, content in files_info.items()])}

---

이 패키지를 완전히 작동하도록 설치하려면 무엇이 필요한지 분석해주세요.

다음 JSON 형식으로 응답해주세요:
{{
    "analysis": "패키지 분석 결과",
    "pip_packages": ["설치할 pip 패키지 목록"],
    "npm_packages": ["설치할 npm 패키지 목록"],
    "system_requirements": ["필요한 시스템 요구사항 (예: node.js 설치 필요)"],
    "generate_handler": true/false,
    "handler_code": "handler.py가 없으면 생성할 코드 (execute 함수 포함)",
    "generate_tool_json": true/false,
    "tool_json": {{"name": "...", "description": "...", "input_schema": {{...}}}},
    "installation_steps": ["설치 단계 설명"],
    "warnings": ["주의사항"]
}}"""

        try:
            if provider in ["google", "gemini"]:
                ai_response = await self._analyze_with_gemini(install_prompt, api_key, model)
            elif provider == "anthropic":
                ai_response = await self._analyze_with_anthropic(install_prompt, api_key, model)
            elif provider in ["openai", "gpt"]:
                ai_response = await self._analyze_with_openai(install_prompt, api_key, model)
            else:
                raise ValueError(f"지원하지 않는 AI 프로바이더: {provider}")

            # JSON 파싱
            import re
            json_match = re.search(r'\{[\s\S]*\}', ai_response)
            if not json_match:
                raise ValueError("AI 응답을 파싱할 수 없습니다")

            install_plan = json.loads(json_match.group())

        except Exception as e:
            raise ValueError(f"AI 분석 실패: {str(e)}")

        # 3. 파일 복사
        shutil.copytree(src_path, dst_path)

        installation_log = []

        # 4. pip 패키지 설치
        pip_packages = install_plan.get("pip_packages", [])
        if pip_packages:
            installation_log.append(f"pip 패키지 설치: {', '.join(pip_packages)}")
            try:
                subprocess.run(
                    ["pip3", "install"] + pip_packages,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
            except Exception as e:
                installation_log.append(f"pip 설치 경고: {str(e)}")

        # 5. handler.py 생성 (필요시)
        if install_plan.get("generate_handler") and install_plan.get("handler_code"):
            handler_path = dst_path / "handler.py"
            if not handler_path.exists():
                handler_path.write_text(install_plan["handler_code"], encoding='utf-8')
                installation_log.append("handler.py 생성됨")

        # 6. tool.json 생성 (필요시)
        if install_plan.get("generate_tool_json") and install_plan.get("tool_json"):
            tool_json_path = dst_path / "tool.json"
            if not tool_json_path.exists():
                with open(tool_json_path, 'w', encoding='utf-8') as f:
                    json.dump(install_plan["tool_json"], f, ensure_ascii=False, indent=2)
                installation_log.append("tool.json 생성됨")

        # 7. 설치 후 검증
        validation = validate_tool_package(dst_path)
        if not validation["valid"]:
            # 검증 실패 시 설치 롤백
            shutil.rmtree(dst_path)
            raise ValueError(f"패키지 검증 실패 (롤백됨): {'; '.join(validation['errors'])}")

        if validation.get("warnings"):
            installation_log.extend([f"경고: {w}" for w in validation["warnings"]])

        # 8. 설치 기록 저장
        install_info = {
            "installed_at": datetime.now().isoformat(),
            "from": str(src_path),
            "ai_installed": True,
            "provider": provider,
            "pip_packages": pip_packages,
            "installation_log": installation_log,
            "ai_analysis": install_plan.get("analysis", ""),
            "validation": validation
        }
        with open(dst_path / ".install_info.json", 'w', encoding='utf-8') as f:
            json.dump(install_info, f, ensure_ascii=False, indent=2)

        # inventory.md 업데이트
        self._update_inventory()

        pkg_info = self._scan_package(dst_path)
        return {
            "status": "installed",
            "package": pkg_info,
            "ai_installed": True,
            "installation_log": installation_log,
            "warnings": install_plan.get("warnings", []) + validation.get("warnings", []),
            "message": f"'{pkg_info.get('name', package_id)}' 패키지가 AI에 의해 설치되었습니다."
        }

    def uninstall_package(self, package_id: str, package_type: str = None) -> Dict[str, Any]:
        """도구 패키지 제거 (installed → not_installed로 이동)"""
        src_path = INSTALLED_PATH / "tools" / package_id
        dst_path = NOT_INSTALLED_PATH / "tools" / package_id

        if not src_path.exists():
            raise ValueError(f"설치되지 않은 패키지입니다: {package_id}")

        # 이름 먼저 가져오기
        pkg_info = self._scan_package(src_path)
        pkg_name = pkg_info.get("name", package_id)

        # 설치 정보 파일 제거
        install_info_path = src_path / ".install_info.json"
        if install_info_path.exists():
            install_info_path.unlink()

        # 이동 (삭제가 아닌 이동)
        shutil.move(str(src_path), str(dst_path))

        # 캐시 무효화
        self.invalidate_cache()

        # inventory.md 자동 업데이트
        self._update_inventory()

        return {
            "status": "uninstalled",
            "package_id": package_id,
            "message": f"'{pkg_name}' 패키지가 제거되었습니다."
        }

    # ============ inventory.md 자동 생성 ============

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
            desc = pkg.get("description", "")[:40]
            lines.append(f"| {pkg['id']} | {pkg['name']} | {desc} | {status} |")
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
            "templates": [],
            "switches": [],
            "agents": []
        }

        if not content:
            return sections

        current_section = None
        current_lines = []

        for line in content.split('\n'):
            if line.startswith('## 프로젝트'):
                if current_section:
                    sections[current_section] = current_lines
                current_section = "projects"
                current_lines = [line]
            elif line.startswith('## 폴더'):
                if current_section:
                    sections[current_section] = current_lines
                current_section = "folders"
                current_lines = [line]
            elif line.startswith('## 도구'):
                if current_section:
                    sections[current_section] = current_lines
                current_section = None
                current_lines = []
            elif line.startswith('## 템플릿'):
                if current_section:
                    sections[current_section] = current_lines
                current_section = "templates"
                current_lines = [line]
            elif line.startswith('## 스위치'):
                if current_section:
                    sections[current_section] = current_lines
                current_section = "switches"
                current_lines = [line]
            elif line.startswith('## 에이전트'):
                if current_section:
                    sections[current_section] = current_lines
                current_section = "agents"
                current_lines = [line]
            elif line.startswith('---'):
                if current_section:
                    sections[current_section] = current_lines
                current_section = None
                current_lines = []
            elif current_section:
                current_lines.append(line)

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

    def remove_package(self, package_id: str, package_type: str = None) -> Dict[str, Any]:
        """패키지 제거 (available에서 삭제)"""
        available_path = NOT_INSTALLED_PATH / "tools" / package_id
        installed_path = INSTALLED_PATH / "tools" / package_id

        if not available_path.exists():
            raise ValueError(f"등록되지 않은 패키지입니다: {package_id}")

        pkg_info = self._scan_package(available_path)
        pkg_name = pkg_info.get("name", package_id)

        # 설치된 상태면 먼저 제거
        if installed_path.exists():
            shutil.rmtree(installed_path)

        # available에서 삭제
        shutil.rmtree(available_path)

        # inventory.md 업데이트
        self._update_inventory()

        return {
            "status": "removed",
            "package_id": package_id,
            "message": f"'{pkg_name}' 패키지가 목록에서 제거되었습니다."
        }

    # ============ 기타 유틸리티 ============

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
