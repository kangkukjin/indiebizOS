"""
package_manager.py - 도구 패키지 관리 시스템
IndieBiz OS Core

설계 원칙:
- 도구 패키지만 관리 (extensions 개념 폐기)
- 폴더 구조가 유일한 진실의 원천 (Single Source of Truth)
- AI가 폴더를 분석하여 유효성 판별 및 README 자동 생성

packages/
├── available/tools/     # 설치 가능한 도구 패키지
│   └── youtube/
└── installed/tools/     # 설치된 도구 패키지
    └── time/
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# 경로 설정
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH.parent / "data"
PACKAGES_PATH = DATA_PATH / "packages"
AVAILABLE_PATH = PACKAGES_PATH / "available"
INSTALLED_PATH = PACKAGES_PATH / "installed"


def ensure_package_dirs():
    """패키지 디렉토리 생성"""
    (AVAILABLE_PATH / "tools").mkdir(parents=True, exist_ok=True)
    (INSTALLED_PATH / "tools").mkdir(parents=True, exist_ok=True)


class PackageManager:
    """도구 패키지 관리자"""

    def __init__(self):
        ensure_package_dirs()
        self._cache = {}

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

        return metadata

    def _scan_all_packages(self) -> List[Dict[str, Any]]:
        """모든 도구 패키지 폴더 스캔"""
        packages = []
        tools_path = AVAILABLE_PATH / "tools"

        if not tools_path.exists():
            return packages

        for pkg_dir in tools_path.iterdir():
            if pkg_dir.is_dir() and not pkg_dir.name.startswith('.'):
                pkg_info = self._scan_package(pkg_dir)

                # 설치 여부 확인
                installed_path = INSTALLED_PATH / "tools" / pkg_dir.name
                pkg_info["installed"] = installed_path.exists()
                pkg_info["package_type"] = "tools"

                packages.append(pkg_info)

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
        pkg_path = AVAILABLE_PATH / "tools" / package_id
        if pkg_path.exists():
            pkg_info = self._scan_package(pkg_path)
            installed_path = INSTALLED_PATH / "tools" / package_id
            pkg_info["installed"] = installed_path.exists()
            pkg_info["package_type"] = "tools"
            pkg_info["path"] = str(pkg_path)
            return pkg_info
        return None

    # ============ 패키지 설치/제거 ============

    def install_package(self, package_id: str, package_type: str = None) -> Dict[str, Any]:
        """도구 패키지 설치"""
        src_path = AVAILABLE_PATH / "tools" / package_id
        dst_path = INSTALLED_PATH / "tools" / package_id

        if not src_path.exists():
            raise ValueError(f"패키지를 찾을 수 없습니다: {package_id}")

        if dst_path.exists():
            raise ValueError(f"이미 설치된 패키지입니다: {package_id}")

        # 복사
        shutil.copytree(src_path, dst_path)

        # 설치 기록
        install_info = {
            "installed_at": datetime.now().isoformat(),
            "from": str(src_path)
        }
        with open(dst_path / ".install_info.json", 'w', encoding='utf-8') as f:
            json.dump(install_info, f, ensure_ascii=False, indent=2)

        # inventory.md 자동 업데이트
        self._update_inventory()

        pkg_info = self._scan_package(src_path)
        return {
            "status": "installed",
            "package": pkg_info,
            "message": f"'{pkg_info.get('name', package_id)}' 패키지가 설치되었습니다."
        }

    def uninstall_package(self, package_id: str, package_type: str = None) -> Dict[str, Any]:
        """도구 패키지 제거"""
        installed_path = INSTALLED_PATH / "tools" / package_id

        if not installed_path.exists():
            raise ValueError(f"설치되지 않은 패키지입니다: {package_id}")

        # 이름 먼저 가져오기
        pkg_info = self._scan_package(installed_path)
        pkg_name = pkg_info.get("name", package_id)

        # 삭제
        shutil.rmtree(installed_path)

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
        """Google Gemini로 분석"""
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        gemini_model = genai.GenerativeModel(model_name=model or "gemini-2.0-flash-exp")
        response = gemini_model.generate_content(prompt)
        return response.text

    # ============ 패키지 등록 ============

    def register_folder(self, folder_path: str, name: str = None, description: str = None,
                        readme_content: str = None, package_type: str = None) -> Dict[str, Any]:
        """폴더를 도구 패키지로 등록 (AI가 생성한 README 포함)"""
        folder = Path(folder_path)

        if not folder.exists() or not folder.is_dir():
            raise ValueError("유효한 폴더가 아닙니다")

        pkg_id = folder.name
        dst_path = AVAILABLE_PATH / "tools" / pkg_id

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
        available_path = AVAILABLE_PATH / "tools" / package_id
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
        pkg_path = AVAILABLE_PATH / "tools" / package_id
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
        pkg_path = AVAILABLE_PATH / "tools" / package_id
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
        pkg_path = AVAILABLE_PATH / "tools" / package_id
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


# 전역 인스턴스
package_manager = PackageManager()
