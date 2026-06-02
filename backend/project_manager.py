"""
project_manager.py - 프로젝트 생성/삭제/관리 클래스
IndieBiz OS Core
"""

import json
import shutil
from pathlib import Path
from datetime import datetime


class ProjectManager:
    """프로젝트 CRUD 관리"""

    def __init__(self, base_path: Path = None):
        if base_path is None:
            import os
            base_path = Path(os.environ.get("INDIEBIZ_BASE_PATH", str(Path(__file__).parent.parent)))

        self.base_path = Path(base_path)
        self.templates_path = self.base_path / "templates"
        self.projects_path = self.base_path / "projects"
        self.projects_json = self.projects_path / "projects.json"

        # 폴더 생성
        self.projects_path.mkdir(exist_ok=True)
        self.templates_path.mkdir(exist_ok=True)

        # projects.json 초기화
        if not self.projects_json.exists():
            self._save_projects_list([])

    def _load_projects_list(self) -> list:
        """프로젝트 목록 로드"""
        if self.projects_json.exists():
            with open(self.projects_json, encoding='utf-8') as f:
                return json.load(f)
        return []

    def _save_projects_list(self, projects: list):
        """프로젝트 목록 저장"""
        with open(self.projects_json, 'w', encoding='utf-8') as f:
            json.dump(projects, f, ensure_ascii=False, indent=2)

    def list_projects(self) -> list:
        """모든 프로젝트 목록 반환"""
        return self._load_projects_list()

    def create_project(self, name: str, icon_position: tuple = None, parent_folder: str = None, template_name: str = "기본") -> dict:
        """새 프로젝트 생성"""
        projects = self._load_projects_list()
        for p in projects:
            if p["name"] == name and p.get("parent_folder") == parent_folder:
                raise ValueError(f"같은 위치에 '{name}'이(가) 이미 존재합니다.")

        project_path = self.projects_path / name
        if project_path.exists():
            raise ValueError(f"프로젝트 '{name}'이(가) 이미 존재합니다.")

        project_path.mkdir(parents=True)

        # 템플릿에서 파일 복사
        self._copy_template_to_project(project_path, template_name)

        project_info = {
            "id": name,
            "name": name,
            "type": "project",
            "path": str(project_path),
            "created_at": datetime.now().isoformat(),
            "icon_position": icon_position or (100, 100),
            "parent_folder": parent_folder,
            "last_opened": None
        }

        projects.append(project_info)
        self._save_projects_list(projects)

        # 시스템 문서 업데이트 (inventory.md)
        try:
            from system_docs import update_inventory_projects, log_change
            project_items = [p for p in projects if p.get("type") == "project"]
            update_inventory_projects(project_items)
            log_change("PROJECT_CREATED", f"{name} (ID: {name})")
        except Exception as e:
            print(f"[ProjectManager] 시스템 문서 업데이트 실패: {e}")

        return project_info

    def list_templates(self) -> list:
        """사용 가능한 템플릿 목록 반환"""
        templates = []
        if self.templates_path.exists():
            for item in self.templates_path.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    templates.append(item.name)
        return sorted(templates)

    def _copy_template_to_project(self, project_path: Path, template_name: str = "기본"):
        """템플릿을 프로젝트로 복사"""
        template_path = self.templates_path / template_name

        if not template_path.exists():
            # 템플릿이 없으면 기본 파일 생성
            self._create_default_project_files(project_path)
            return

        # agent_roles 폴더 (폴더 전체 복사 + 프로젝트 루트에도 복사)
        roles_src = template_path / "agent_roles"
        if roles_src.exists():
            # agent_roles 폴더 생성 및 복사
            roles_dst = project_path / "agent_roles"
            roles_dst.mkdir(exist_ok=True)
            for agent_file in roles_src.glob("*.txt"):
                shutil.copy2(agent_file, roles_dst / agent_file.name)
                # 프로젝트 루트에도 복사 (indiebizE 호환)
                shutil.copy2(agent_file, project_path / agent_file.name)

        # agents.yaml.template -> agents.yaml
        template_src = template_path / "agents.yaml.template"
        if template_src.exists():
            shutil.copy2(template_src, project_path / "agents.yaml")

        # config.yaml
        config_src = template_path / "config.yaml"
        if config_src.exists():
            shutil.copy2(config_src, project_path / "config.yaml")

        # outputs 폴더 생성
        (project_path / "outputs").mkdir(exist_ok=True)

        # tokens 폴더 생성
        (project_path / "tokens").mkdir(exist_ok=True)

    def _create_default_project_files(self, project_path: Path):
        """기본 프로젝트 파일 생성"""
        # agents.yaml 기본 내용
        agents_content = """# IndieBiz OS 에이전트 설정
agents:
  - id: agent_001
    name: 집사
    type: external
    active: true
    ai:
      provider: anthropic
      model: claude-sonnet-4-20250514
      api_key: ""
    allowed_tools: []
    role: ""
"""
        (project_path / "agents.yaml").write_text(agents_content, encoding='utf-8')

    def delete_project(self, name: str, move_to_trash: bool = True):
        """프로젝트/폴더 삭제"""
        projects = self._load_projects_list()

        item_to_delete = None
        for p in projects:
            if p["id"] == name or p["name"] == name:
                item_to_delete = p
                break

        if not item_to_delete:
            raise ValueError(f"'{name}'을(를) 찾을 수 없습니다.")

        # 폴더인 경우 내부 아이템도 재귀적으로 삭제
        if item_to_delete.get("type") == "folder":
            folder_items = self.get_folder_items(item_to_delete["id"])
            for item in folder_items:
                self.delete_project(item["id"], move_to_trash)

        project_path = self.projects_path / name
        if project_path.exists():
            if move_to_trash:
                trash_path = self.projects_path / "trash"
                trash_path.mkdir(exist_ok=True)

                trash_dest = trash_path / name
                if trash_dest.exists():
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    trash_dest = trash_path / f"{name}_{timestamp}"

                shutil.move(str(project_path), str(trash_dest))
            else:
                shutil.rmtree(project_path)

        projects = [p for p in projects if p["id"] != item_to_delete["id"]]
        self._save_projects_list(projects)

        # 시스템 문서 업데이트 (inventory.md)
        if item_to_delete.get("type") == "project":
            try:
                from system_docs import update_inventory_projects, log_change
                project_items = [p for p in projects if p.get("type") == "project"]
                update_inventory_projects(project_items)
                log_change("PROJECT_DELETED", f"{name}")
            except Exception as e:
                print(f"[ProjectManager] 시스템 문서 업데이트 실패: {e}")

    def update_project_position(self, name: str, x: int, y: int):
        """프로젝트 아이콘 위치 업데이트"""
        projects = self._load_projects_list()
        for project in projects:
            if project["name"] == name:
                project["icon_position"] = (x, y)
                break
        self._save_projects_list(projects)

    def get_project_path(self, name: str) -> Path:
        """프로젝트 경로 반환"""
        return self.projects_path / name

    def create_folder(self, name: str, icon_position: tuple = None, parent_folder: str = None) -> dict:
        """빈 폴더 생성"""
        projects = self._load_projects_list()
        for p in projects:
            if p["name"] == name and p.get("parent_folder") == parent_folder:
                raise ValueError(f"같은 위치에 '{name}'이(가) 이미 존재합니다.")

        folder_info = {
            "id": name,
            "name": name,
            "type": "folder",
            "created_at": datetime.now().isoformat(),
            "icon_position": icon_position or (100, 100),
            "parent_folder": parent_folder,
            "items": []
        }

        projects.append(folder_info)
        self._save_projects_list(projects)

        return folder_info

    def _is_descendant_of(self, projects: list, ancestor_id: str, descendant_id: str) -> bool:
        """
        descendant_id가 ancestor_id의 자손인지 확인 (순환 참조 방지용)

        Args:
            projects: 프로젝트 목록
            ancestor_id: 조상 후보 ID
            descendant_id: 자손 후보 ID

        Returns:
            True면 descendant_id가 ancestor_id의 자손임
        """
        current_id = descendant_id
        visited = set()  # 무한 루프 방지

        while current_id:
            if current_id in visited:
                break  # 이미 순환 참조가 있는 경우
            visited.add(current_id)

            if current_id == ancestor_id:
                return True

            # 현재 아이템의 부모 찾기
            current_item = next((p for p in projects if p["id"] == current_id), None)
            if not current_item:
                break
            current_id = current_item.get("parent_folder")

        return False

    def move_to_folder(self, item_id: str, folder_id: str):
        """프로젝트 또는 폴더를 다른 폴더로 이동"""
        projects = self._load_projects_list()

        item = None
        folder = None
        for p in projects:
            if p["id"] == item_id:
                item = p
            if p["id"] == folder_id:
                folder = p

        if not item or not folder:
            raise ValueError("아이템 또는 폴더를 찾을 수 없습니다.")

        if folder["type"] != "folder":
            raise ValueError("대상이 폴더가 아닙니다.")

        if item_id == folder_id:
            raise ValueError("폴더를 자기 자신 안으로 이동할 수 없습니다.")

        # 순환 참조 방지: 대상 폴더가 이동할 아이템의 자손인지 확인
        if item.get("type") == "folder":
            if self._is_descendant_of(projects, item_id, folder_id):
                raise ValueError("폴더를 자신의 하위 폴더 안으로 이동할 수 없습니다.")

        item["parent_folder"] = folder_id
        self._save_projects_list(projects)

    def move_out_of_folder(self, item_id: str):
        """프로젝트를 폴더에서 꺼내기 (루트로 이동)"""
        projects = self._load_projects_list()

        for p in projects:
            if p["id"] == item_id:
                p["parent_folder"] = None
                break

        self._save_projects_list(projects)

    def get_folder_items(self, folder_id: str) -> list:
        """폴더 안의 프로젝트 목록 반환"""
        projects = self._load_projects_list()
        return [item for item in projects if item.get("parent_folder") == folder_id]

    def move_to_trash(self, item_id: str) -> dict:
        """프로젝트 또는 폴더를 휴지통으로 이동"""
        projects = self._load_projects_list()

        for i, p in enumerate(projects):
            if p["id"] == item_id:
                p["in_trash"] = True
                p["trashed_at"] = datetime.now().isoformat()
                p["original_parent_folder"] = p.get("parent_folder")
                p["parent_folder"] = None
                projects[i] = p
                self._save_projects_list(projects)
                return p

        raise ValueError(f"'{item_id}'을(를) 찾을 수 없습니다.")

    def restore_from_trash(self, item_id: str) -> dict:
        """휴지통에서 프로젝트 또는 폴더 복원"""
        projects = self._load_projects_list()

        for i, p in enumerate(projects):
            if p["id"] == item_id:
                p["in_trash"] = False

                # 원래 폴더가 존재하고 휴지통에 없는지 확인
                original_folder = p.get("original_parent_folder")
                if original_folder:
                    folder_exists = any(
                        proj["id"] == original_folder and not proj.get("in_trash", False)
                        for proj in projects
                    )
                    p["parent_folder"] = original_folder if folder_exists else None
                else:
                    p["parent_folder"] = None

                if "trashed_at" in p:
                    del p["trashed_at"]
                if "original_parent_folder" in p:
                    del p["original_parent_folder"]
                projects[i] = p
                self._save_projects_list(projects)
                return p

        raise ValueError(f"'{item_id}'을(를) 찾을 수 없습니다.")

    def list_trash(self) -> list:
        """휴지통 아이템 목록 반환"""
        projects = self._load_projects_list()
        return [p for p in projects if p.get("in_trash", False)]

    def empty_trash(self):
        """휴지통 비우기 (영구 삭제)"""
        projects = self._load_projects_list()
        trash_items = [p for p in projects if p.get("in_trash", False)]

        for item in trash_items:
            if item.get("type") == "project":
                project_path = self.projects_path / item["name"]
                if project_path.exists():
                    shutil.rmtree(project_path)

        projects = [p for p in projects if not p.get("in_trash", False)]
        self._save_projects_list(projects)

    def rename_item(self, item_id: str, new_name: str) -> dict:
        """프로젝트 또는 폴더 이름 변경"""
        if not new_name or not new_name.strip():
            raise ValueError("새 이름을 입력해주세요.")

        new_name = new_name.strip()
        projects = self._load_projects_list()

        original = None
        original_idx = -1
        for i, p in enumerate(projects):
            if p["id"] == item_id:
                original = p
                original_idx = i
                break

        if not original:
            raise ValueError(f"'{item_id}'을(를) 찾을 수 없습니다.")

        parent_folder = original.get("parent_folder")
        for p in projects:
            if p["id"] != item_id and p["name"] == new_name and p.get("parent_folder") == parent_folder:
                raise ValueError(f"같은 위치에 '{new_name}'이(가) 이미 존재합니다.")

        old_name = original["name"]

        if original["type"] == "project":
            old_path = self.projects_path / old_name
            new_path = self.projects_path / new_name

            if new_path.exists():
                raise ValueError(f"프로젝트 '{new_name}'이(가) 이미 존재합니다.")

            if old_path.exists():
                old_path.rename(new_path)

            original["id"] = new_name
            original["name"] = new_name
            original["path"] = str(new_path)
        else:
            original["id"] = new_name
            original["name"] = new_name

        for p in projects:
            if p.get("parent_folder") == old_name:
                p["parent_folder"] = new_name

        projects[original_idx] = original
        self._save_projects_list(projects)

        # 시스템 문서 업데이트 (inventory.md)
        try:
            from system_docs import update_inventory_projects, log_change
            # 프로젝트만 필터링해서 업데이트
            project_items = [p for p in projects if p.get("type") == "project"]
            update_inventory_projects(project_items)
            log_change("PROJECT_RENAMED", f"{old_name} -> {new_name}")
        except Exception as e:
            print(f"[ProjectManager] 시스템 문서 업데이트 실패: {e}")

        return original

    def copy_item(self, item_id: str, new_name: str = None, parent_folder: str = None) -> dict:
        """프로젝트 또는 폴더 복사"""
        projects = self._load_projects_list()

        original = None
        for p in projects:
            if p["id"] == item_id:
                original = p
                break

        if not original:
            raise ValueError(f"'{item_id}'을(를) 찾을 수 없습니다.")

        if not new_name:
            base_name = original["name"]
            counter = 1
            new_name = f"{base_name} 사본"
            while any(p["name"] == new_name and p.get("parent_folder") == parent_folder for p in projects):
                counter += 1
                new_name = f"{base_name} 사본 {counter}"

        for p in projects:
            if p["name"] == new_name and p.get("parent_folder") == parent_folder:
                raise ValueError(f"같은 위치에 '{new_name}'이(가) 이미 존재합니다.")

        # 아이콘 위치 오프셋 (복사본이 원본과 겹치지 않도록)
        original_pos = original.get("icon_position", (100, 100))
        offset_pos = (original_pos[0] + 30, original_pos[1] + 30)

        if original["type"] == "folder":
            copied = self.create_folder(new_name, offset_pos, parent_folder)

            folder_items = self.get_folder_items(item_id)
            for item in folder_items:
                self.copy_item(item["id"], None, copied["id"])
        else:
            src_path = self.projects_path / original["name"]
            dst_path = self.projects_path / new_name

            if dst_path.exists():
                raise ValueError(f"프로젝트 '{new_name}'이(가) 이미 존재합니다.")

            shutil.copytree(src_path, dst_path)

            copied = {
                "id": new_name,
                "name": new_name,
                "type": "project",
                "path": str(dst_path),
                "created_at": datetime.now().isoformat(),
                "icon_position": offset_pos,
                "parent_folder": parent_folder,
                "last_opened": None
            }

            projects = self._load_projects_list()
            projects.append(copied)
            self._save_projects_list(projects)

        return copied
