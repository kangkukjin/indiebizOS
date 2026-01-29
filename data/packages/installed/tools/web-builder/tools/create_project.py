"""
create_project.py
Next.js + shadcn/ui 프로젝트를 생성합니다.
"""

import subprocess
import json
import os
from pathlib import Path

# 도구 메타데이터
TOOL_NAME = "create_project"
TOOL_DESCRIPTION = "Next.js + shadcn/ui 프로젝트를 생성합니다"
TOOL_PARAMETERS = {
    "name": {
        "type": "string",
        "description": "프로젝트 이름 (영문, 소문자, 하이픈 허용)",
        "required": True
    },
    "template": {
        "type": "string",
        "description": "프로젝트 템플릿",
        "enum": ["blank", "landing", "portfolio", "blog", "business"],
        "default": "blank"
    },
    "features": {
        "type": "array",
        "description": "추가 기능",
        "items": {"type": "string", "enum": ["dark_mode", "i18n", "analytics", "seo", "pwa"]},
        "default": ["dark_mode", "seo"]
    },
    "output_dir": {
        "type": "string",
        "description": "프로젝트 생성 경로",
        "default": "/Users/kangkukjin/Desktop/AI/outputs/web-projects"
    }
}

DEFAULT_OUTPUT_DIR = "/Users/kangkukjin/Desktop/AI/outputs/web-projects"

# 기본 shadcn 컴포넌트 (템플릿별)
TEMPLATE_COMPONENTS = {
    "blank": ["button"],
    "landing": ["button", "card", "badge", "separator", "navigation-menu"],
    "portfolio": ["button", "card", "avatar", "badge", "tabs", "separator"],
    "blog": ["button", "card", "badge", "separator", "input", "textarea"],
    "business": ["button", "card", "badge", "form", "input", "select", "navigation-menu", "sheet"]
}


def run_command(cmd: list, cwd: str = None, timeout: int = 300) -> dict:
    """명령어 실행"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "명령어 실행 시간 초과"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_shadcn_config(project_path: str, features: list) -> None:
    """components.json 생성 (shadcn 설정)"""
    config = {
        "$schema": "https://ui.shadcn.com/schema.json",
        "style": "new-york",
        "rsc": True,
        "tsx": True,
        "tailwind": {
            "config": "tailwind.config.ts",
            "css": "app/globals.css",
            "baseColor": "neutral",
            "cssVariables": True,
            "prefix": ""
        },
        "aliases": {
            "components": "@/components",
            "utils": "@/lib/utils",
            "ui": "@/components/ui",
            "lib": "@/lib",
            "hooks": "@/hooks"
        }
    }

    config_path = os.path.join(project_path, "components.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def create_utils_file(project_path: str) -> None:
    """lib/utils.ts 생성"""
    utils_dir = os.path.join(project_path, "lib")
    os.makedirs(utils_dir, exist_ok=True)

    utils_content = '''import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
'''

    with open(os.path.join(utils_dir, "utils.ts"), "w") as f:
        f.write(utils_content)


def update_globals_css(project_path: str, dark_mode: bool = True) -> None:
    """globals.css 업데이트 (shadcn 스타일)"""
    css_content = '''@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 0 0% 3.9%;
    --card: 0 0% 100%;
    --card-foreground: 0 0% 3.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 0 0% 3.9%;
    --primary: 0 0% 9%;
    --primary-foreground: 0 0% 98%;
    --secondary: 0 0% 96.1%;
    --secondary-foreground: 0 0% 9%;
    --muted: 0 0% 96.1%;
    --muted-foreground: 0 0% 45.1%;
    --accent: 0 0% 96.1%;
    --accent-foreground: 0 0% 9%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 0 0% 98%;
    --border: 0 0% 89.8%;
    --input: 0 0% 89.8%;
    --ring: 0 0% 3.9%;
    --radius: 0.5rem;
  }
'''

    if dark_mode:
        css_content += '''
  .dark {
    --background: 0 0% 3.9%;
    --foreground: 0 0% 98%;
    --card: 0 0% 3.9%;
    --card-foreground: 0 0% 98%;
    --popover: 0 0% 3.9%;
    --popover-foreground: 0 0% 98%;
    --primary: 0 0% 98%;
    --primary-foreground: 0 0% 9%;
    --secondary: 0 0% 14.9%;
    --secondary-foreground: 0 0% 98%;
    --muted: 0 0% 14.9%;
    --muted-foreground: 0 0% 63.9%;
    --accent: 0 0% 14.9%;
    --accent-foreground: 0 0% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 0 0% 98%;
    --border: 0 0% 14.9%;
    --input: 0 0% 14.9%;
    --ring: 0 0% 83.1%;
  }
'''

    css_content += '''}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
  }
}
'''

    app_dir = os.path.join(project_path, "app")
    os.makedirs(app_dir, exist_ok=True)
    css_path = os.path.join(app_dir, "globals.css")
    with open(css_path, "w") as f:
        f.write(css_content)


def create_project_info(project_path: str, name: str, template: str, features: list) -> None:
    """프로젝트 정보 파일 생성"""
    info = {
        "name": name,
        "template": template,
        "features": features,
        "created_by": "web-builder",
        "shadcn_components": TEMPLATE_COMPONENTS.get(template, [])
    }

    info_path = os.path.join(project_path, ".web-builder.json")
    with open(info_path, "w") as f:
        json.dump(info, f, indent=2)


def run(name: str, template: str = "blank", features: list = None, output_dir: str = None) -> dict:
    """
    Next.js + shadcn/ui 프로젝트 생성

    Args:
        name: 프로젝트 이름
        template: 템플릿 (blank, landing, portfolio, blog, business)
        features: 추가 기능 리스트
        output_dir: 출력 디렉토리

    Returns:
        생성 결과
    """
    if not name:
        return {"success": False, "error": "프로젝트 이름(name)은 필수입니다"}

    if features is None:
        features = ["dark_mode", "seo"]

    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR

    # output_dir이 이미 name으로 끝나면 중복 방지
    # 예: output_dir="/path/indiebiz-next", name="indiebiz-next" → /path/indiebiz-next (중복 X)
    if os.path.basename(output_dir.rstrip("/")) == name:
        project_path = output_dir
        output_dir = os.path.dirname(output_dir)
    else:
        project_path = os.path.join(output_dir, name)

    # 출력 디렉토리 생성
    os.makedirs(output_dir, exist_ok=True)

    # 이미 존재하는지 확인
    if os.path.exists(project_path):
        return {
            "success": False,
            "error": f"프로젝트 '{name}'이 이미 존재합니다: {project_path}"
        }

    results = []

    # 1. Next.js 프로젝트 생성
    results.append("1. Next.js 프로젝트 생성 중...")
    create_cmd = [
        "npx", "create-next-app@latest", name,
        "--typescript",
        "--tailwind",
        "--eslint",
        "--app",
        "--src-dir",
        "--import-alias", "@/*",
        "--no-turbopack",
        "--yes"
    ]

    result = run_command(create_cmd, cwd=output_dir, timeout=180)
    if not result["success"]:
        return {
            "success": False,
            "error": f"Next.js 프로젝트 생성 실패: {result.get('error', result.get('stderr', ''))}",
            "attempted_path": project_path
        }

    # 프로젝트 디렉토리가 실제로 생성되었는지 확인
    if not os.path.exists(project_path):
        return {
            "success": False,
            "error": f"create-next-app 실행 후 프로젝트 디렉토리가 생성되지 않았습니다: {project_path}",
            "stdout": result.get("stdout", "")[:500],
            "stderr": result.get("stderr", "")[:500]
        }

    results.append("   OK Next.js 프로젝트 생성 완료")

    # src 디렉토리 구조로 경로 조정 (--src-dir 지원 여부에 따라 다름)
    src_path = os.path.join(project_path, "src")
    if not os.path.exists(src_path):
        # src 디렉토리가 없으면 프로젝트 루트를 사용
        src_path = project_path

    # 2. 추가 패키지 설치
    results.append("2. 추가 패키지 설치 중...")
    packages = ["clsx", "tailwind-merge", "class-variance-authority", "lucide-react"]

    if "dark_mode" in features:
        packages.append("next-themes")

    install_cmd = ["npm", "install"] + packages
    result = run_command(install_cmd, cwd=project_path, timeout=120)
    if not result["success"]:
        results.append(f"   ⚠ 패키지 설치 경고: {result.get('stderr', '')[:100]}")
    else:
        results.append("   ✓ 추가 패키지 설치 완료")

    # 3. shadcn 설정 파일 생성
    results.append("3. shadcn/ui 설정 중...")
    create_shadcn_config(project_path, features)
    results.append("   ✓ components.json 생성")

    # 4. utils 파일 생성
    create_utils_file(src_path)
    results.append("   ✓ lib/utils.ts 생성")

    # 5. globals.css 업데이트
    update_globals_css(src_path, dark_mode="dark_mode" in features)
    results.append("   ✓ globals.css 업데이트")

    # 6. UI 컴포넌트 디렉토리 생성
    ui_dir = os.path.join(src_path, "components", "ui")
    os.makedirs(ui_dir, exist_ok=True)
    results.append("   ✓ components/ui 디렉토리 생성")

    # 7. 프로젝트 정보 파일 생성
    create_project_info(project_path, name, template, features)
    results.append("   ✓ 프로젝트 정보 파일 생성")

    # 8. 기본 컴포넌트 추가
    components_to_add = TEMPLATE_COMPONENTS.get(template, ["button"])
    results.append(f"4. 기본 컴포넌트 추가 중... ({', '.join(components_to_add)})")

    for component in components_to_add:
        add_cmd = ["npx", "shadcn@latest", "add", component, "--yes"]
        result = run_command(add_cmd, cwd=project_path, timeout=60)
        if result["success"]:
            results.append(f"   ✓ {component} 추가됨")
        else:
            results.append(f"   ⚠ {component} 추가 실패")

    return {
        "success": True,
        "project_path": project_path,
        "template": template,
        "features": features,
        "components": components_to_add,
        "logs": results,
        "next_steps": [
            f"cd {project_path}",
            "npm run dev  # 개발 서버 실행",
            "# 또는 web-builder의 preview_site 도구 사용"
        ]
    }


if __name__ == "__main__":
    # 테스트
    result = run(
        name="test-project",
        template="landing",
        features=["dark_mode", "seo"]
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
