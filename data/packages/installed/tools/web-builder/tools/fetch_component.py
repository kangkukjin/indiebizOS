"""
fetch_component.py
shadcn/ui 레지스트리에서 최신 컴포넌트 코드를 가져옵니다.
"""

import json
import os
import urllib.request
import urllib.error
from typing import Optional

TOOL_NAME = "fetch_component"
TOOL_DESCRIPTION = "shadcn/ui 레지스트리에서 최신 컴포넌트 코드를 가져옵니다"
TOOL_PARAMETERS = {
    "component": {
        "type": "string",
        "description": "컴포넌트 이름 (예: button, card, dialog)",
        "required": True
    },
    "style": {
        "type": "string",
        "description": "스타일 (new-york 또는 default)",
        "enum": ["new-york", "default"],
        "default": "new-york"
    },
    "project_path": {
        "type": "string",
        "description": "프로젝트 경로 (지정하면 자동 저장)",
        "required": False
    },
    "output_format": {
        "type": "string",
        "description": "출력 형식",
        "enum": ["code", "json", "save"],
        "default": "code"
    }
}

# shadcn/ui 레지스트리 URL (2024년 이후 새 형식)
REGISTRY_BASE_URL = "https://ui.shadcn.com/r"

# 사용 가능한 컴포넌트 목록
AVAILABLE_COMPONENTS = [
    "accordion", "alert", "alert-dialog", "aspect-ratio", "avatar",
    "badge", "breadcrumb", "button", "calendar", "card", "carousel",
    "chart", "checkbox", "collapsible", "combobox", "command",
    "context-menu", "data-table", "date-picker", "dialog", "drawer",
    "dropdown-menu", "form", "hover-card", "input", "input-otp",
    "label", "menubar", "navigation-menu", "pagination", "popover",
    "progress", "radio-group", "resizable", "scroll-area", "select",
    "separator", "sheet", "skeleton", "slider", "sonner", "switch",
    "table", "tabs", "textarea", "toast", "toggle", "toggle-group",
    "tooltip"
]


def fetch_from_registry(component: str, style: str = "new-york") -> dict:
    """
    shadcn/ui 레지스트리에서 컴포넌트 정보 가져오기
    """
    url = f"{REGISTRY_BASE_URL}/styles/{style}/{component}.json"

    # 디버그 출력
    print(f"Fetching from: {url}")

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "IndieBiz-WebBuilder/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return {"success": True, "data": data}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"success": False, "error": f"컴포넌트 '{component}'를 찾을 수 없습니다"}
        return {"success": False, "error": f"HTTP 오류: {e.code}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"네트워크 오류: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def fetch_component_index() -> dict:
    """
    전체 컴포넌트 인덱스 가져오기
    """
    url = f"{REGISTRY_BASE_URL}/index.json"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "IndieBiz-WebBuilder/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


def extract_code_from_registry(registry_data: dict) -> dict:
    """
    레지스트리 데이터에서 코드 추출
    """
    files = registry_data.get("files", [])
    dependencies = registry_data.get("dependencies", [])
    registry_dependencies = registry_data.get("registryDependencies", [])

    result = {
        "name": registry_data.get("name", ""),
        "type": registry_data.get("type", ""),
        "dependencies": dependencies,
        "registry_dependencies": registry_dependencies,
        "files": []
    }

    for file_info in files:
        if isinstance(file_info, dict):
            file_data = {
                "path": file_info.get("path", file_info.get("name", "")),
                "content": file_info.get("content", ""),
                "type": file_info.get("type", "registry:ui")
            }
        else:
            # 문자열인 경우 (이전 형식)
            file_data = {"path": file_info, "content": "", "type": "registry:ui"}

        result["files"].append(file_data)

    return result


def save_component_to_project(project_path: str, component_data: dict) -> dict:
    """
    컴포넌트를 프로젝트에 저장
    """
    # src 디렉토리 확인
    src_path = os.path.join(project_path, "src")
    if not os.path.exists(src_path):
        src_path = project_path

    ui_path = os.path.join(src_path, "components", "ui")
    os.makedirs(ui_path, exist_ok=True)

    saved_files = []

    for file_info in component_data.get("files", []):
        content = file_info.get("content", "")
        if not content:
            continue

        # 파일 경로 결정
        file_path = file_info.get("path", "")
        if file_path:
            # 경로에서 파일명 추출
            filename = os.path.basename(file_path)
        else:
            filename = f"{component_data['name']}.tsx"

        full_path = os.path.join(ui_path, filename)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        saved_files.append(full_path)

    return {
        "success": True,
        "saved_files": saved_files,
        "dependencies": component_data.get("dependencies", []),
        "registry_dependencies": component_data.get("registry_dependencies", [])
    }


def run(
    component: str,
    style: str = "new-york",
    project_path: str = None,
    output_format: str = "code"
) -> dict:
    """
    shadcn/ui 컴포넌트 가져오기

    Args:
        component: 컴포넌트 이름
        style: 스타일 (new-york, default)
        project_path: 프로젝트 경로 (저장 시)
        output_format: 출력 형식 (code, json, save)

    Returns:
        컴포넌트 코드 또는 저장 결과
    """
    component = component.lower().strip()

    # 유효성 검사
    if component not in AVAILABLE_COMPONENTS:
        # 유사한 컴포넌트 찾기
        suggestions = [c for c in AVAILABLE_COMPONENTS if component in c or c in component]
        return {
            "success": False,
            "error": f"'{component}'는 유효한 컴포넌트가 아닙니다",
            "suggestions": suggestions[:5] if suggestions else AVAILABLE_COMPONENTS[:10],
            "available_count": len(AVAILABLE_COMPONENTS)
        }

    # 레지스트리에서 가져오기
    result = fetch_from_registry(component, style)

    if not result["success"]:
        return result

    # 코드 추출
    component_data = extract_code_from_registry(result["data"])

    # 출력 형식에 따라 처리
    if output_format == "json":
        return {
            "success": True,
            "component": component,
            "style": style,
            "data": component_data
        }

    elif output_format == "save":
        if not project_path:
            return {
                "success": False,
                "error": "project_path가 필요합니다"
            }

        if not os.path.exists(project_path):
            return {
                "success": False,
                "error": f"프로젝트를 찾을 수 없습니다: {project_path}"
            }

        save_result = save_component_to_project(project_path, component_data)

        # 의존성 설치 안내
        deps = component_data.get("dependencies", [])
        registry_deps = component_data.get("registry_dependencies", [])

        return {
            "success": True,
            "component": component,
            "saved_files": save_result["saved_files"],
            "dependencies_to_install": deps,
            "other_components_needed": registry_deps,
            "install_command": f"npm install {' '.join(deps)}" if deps else None,
            "note": f"다음 컴포넌트도 필요합니다: {', '.join(registry_deps)}" if registry_deps else None
        }

    else:  # code
        # 코드만 반환
        files_content = []
        for file_info in component_data.get("files", []):
            content = file_info.get("content", "")
            if content:
                files_content.append({
                    "filename": os.path.basename(file_info.get("path", f"{component}.tsx")),
                    "code": content
                })

        return {
            "success": True,
            "component": component,
            "style": style,
            "files": files_content,
            "dependencies": component_data.get("dependencies", []),
            "registry_dependencies": component_data.get("registry_dependencies", []),
            "usage_example": get_usage_example(component)
        }


def get_usage_example(component: str) -> str:
    """
    컴포넌트 사용 예시 반환
    """
    examples = {
        "button": '''import { Button } from "@/components/ui/button"

<Button>Click me</Button>
<Button variant="outline">Outline</Button>
<Button variant="ghost">Ghost</Button>
<Button size="lg">Large</Button>''',

        "card": '''import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"

<Card>
  <CardHeader>
    <CardTitle>제목</CardTitle>
    <CardDescription>설명</CardDescription>
  </CardHeader>
  <CardContent>내용</CardContent>
  <CardFooter>푸터</CardFooter>
</Card>''',

        "dialog": '''import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"

<Dialog>
  <DialogTrigger>열기</DialogTrigger>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>제목</DialogTitle>
      <DialogDescription>설명</DialogDescription>
    </DialogHeader>
  </DialogContent>
</Dialog>''',

        "input": '''import { Input } from "@/components/ui/input"

<Input placeholder="이메일" type="email" />''',

        "select": '''import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

<Select>
  <SelectTrigger>
    <SelectValue placeholder="선택하세요" />
  </SelectTrigger>
  <SelectContent>
    <SelectItem value="option1">옵션 1</SelectItem>
    <SelectItem value="option2">옵션 2</SelectItem>
  </SelectContent>
</Select>''',

        "tabs": '''import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

<Tabs defaultValue="tab1">
  <TabsList>
    <TabsTrigger value="tab1">탭 1</TabsTrigger>
    <TabsTrigger value="tab2">탭 2</TabsTrigger>
  </TabsList>
  <TabsContent value="tab1">내용 1</TabsContent>
  <TabsContent value="tab2">내용 2</TabsContent>
</Tabs>''',

        "toast": '''import { useToast } from "@/components/ui/use-toast"

const { toast } = useToast()

toast({
  title: "알림",
  description: "작업이 완료되었습니다.",
})''',

        "badge": '''import { Badge } from "@/components/ui/badge"

<Badge>기본</Badge>
<Badge variant="secondary">보조</Badge>
<Badge variant="outline">외곽선</Badge>
<Badge variant="destructive">위험</Badge>'''
    }

    return examples.get(component, f'''import {{ {component.title().replace("-", "")} }} from "@/components/ui/{component}"

// 사용 예시는 shadcn/ui 공식 문서를 참조하세요
// https://ui.shadcn.com/docs/components/{component}''')


def list_all_components() -> dict:
    """
    사용 가능한 모든 컴포넌트 목록
    """
    return {
        "success": True,
        "total": len(AVAILABLE_COMPONENTS),
        "components": AVAILABLE_COMPONENTS,
        "registry_url": REGISTRY_BASE_URL
    }


if __name__ == "__main__":
    # 테스트
    result = run(component="button", output_format="code")
    print(json.dumps(result, indent=2, ensure_ascii=False))
