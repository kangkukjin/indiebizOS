"""
edit_styles.py
프로젝트 스타일(색상, 폰트 등)을 수정합니다.
"""

import json
import os
import re

TOOL_NAME = "edit_styles"
TOOL_DESCRIPTION = "프로젝트 스타일(색상, 폰트 등)을 수정합니다"
TOOL_PARAMETERS = {
    "project_path": {
        "type": "string",
        "description": "프로젝트 경로",
        "required": True
    },
    "theme": {
        "type": "string",
        "description": "테마 프리셋",
        "enum": ["default", "blue", "green", "purple", "orange", "red", "custom"],
        "default": "default"
    },
    "custom_colors": {
        "type": "object",
        "description": "커스텀 색상 (theme='custom'일 때)",
        "required": False,
        "properties": {
            "primary": {"type": "string", "description": "HSL 값 (예: '221.2 83.2% 53.3%')"},
            "background": {"type": "string"},
            "foreground": {"type": "string"}
        }
    },
    "border_radius": {
        "type": "string",
        "description": "테두리 반경",
        "enum": ["none", "sm", "md", "lg", "full"],
        "default": "md"
    }
}

# 테마 프리셋
THEME_PRESETS = {
    "default": {
        "light": {
            "background": "0 0% 100%",
            "foreground": "0 0% 3.9%",
            "primary": "0 0% 9%",
            "primary-foreground": "0 0% 98%",
            "secondary": "0 0% 96.1%",
            "secondary-foreground": "0 0% 9%",
            "muted": "0 0% 96.1%",
            "muted-foreground": "0 0% 45.1%",
            "accent": "0 0% 96.1%",
            "accent-foreground": "0 0% 9%",
            "destructive": "0 84.2% 60.2%",
            "border": "0 0% 89.8%",
            "ring": "0 0% 3.9%"
        },
        "dark": {
            "background": "0 0% 3.9%",
            "foreground": "0 0% 98%",
            "primary": "0 0% 98%",
            "primary-foreground": "0 0% 9%",
            "secondary": "0 0% 14.9%",
            "secondary-foreground": "0 0% 98%",
            "muted": "0 0% 14.9%",
            "muted-foreground": "0 0% 63.9%",
            "accent": "0 0% 14.9%",
            "accent-foreground": "0 0% 98%",
            "destructive": "0 62.8% 30.6%",
            "border": "0 0% 14.9%",
            "ring": "0 0% 83.1%"
        }
    },
    "blue": {
        "light": {
            "background": "0 0% 100%",
            "foreground": "222.2 84% 4.9%",
            "primary": "221.2 83.2% 53.3%",
            "primary-foreground": "210 40% 98%",
            "secondary": "210 40% 96.1%",
            "secondary-foreground": "222.2 47.4% 11.2%",
            "muted": "210 40% 96.1%",
            "muted-foreground": "215.4 16.3% 46.9%",
            "accent": "210 40% 96.1%",
            "accent-foreground": "222.2 47.4% 11.2%",
            "destructive": "0 84.2% 60.2%",
            "border": "214.3 31.8% 91.4%",
            "ring": "221.2 83.2% 53.3%"
        },
        "dark": {
            "background": "222.2 84% 4.9%",
            "foreground": "210 40% 98%",
            "primary": "217.2 91.2% 59.8%",
            "primary-foreground": "222.2 47.4% 11.2%",
            "secondary": "217.2 32.6% 17.5%",
            "secondary-foreground": "210 40% 98%",
            "muted": "217.2 32.6% 17.5%",
            "muted-foreground": "215 20.2% 65.1%",
            "accent": "217.2 32.6% 17.5%",
            "accent-foreground": "210 40% 98%",
            "destructive": "0 62.8% 30.6%",
            "border": "217.2 32.6% 17.5%",
            "ring": "224.3 76.3% 48%"
        }
    },
    "green": {
        "light": {
            "background": "0 0% 100%",
            "foreground": "240 10% 3.9%",
            "primary": "142.1 76.2% 36.3%",
            "primary-foreground": "355.7 100% 97.3%",
            "secondary": "240 4.8% 95.9%",
            "secondary-foreground": "240 5.9% 10%",
            "muted": "240 4.8% 95.9%",
            "muted-foreground": "240 3.8% 46.1%",
            "accent": "240 4.8% 95.9%",
            "accent-foreground": "240 5.9% 10%",
            "destructive": "0 84.2% 60.2%",
            "border": "240 5.9% 90%",
            "ring": "142.1 76.2% 36.3%"
        },
        "dark": {
            "background": "20 14.3% 4.1%",
            "foreground": "0 0% 95%",
            "primary": "142.1 70.6% 45.3%",
            "primary-foreground": "144.9 80.4% 10%",
            "secondary": "240 3.7% 15.9%",
            "secondary-foreground": "0 0% 98%",
            "muted": "0 0% 15%",
            "muted-foreground": "240 5% 64.9%",
            "accent": "12 6.5% 15.1%",
            "accent-foreground": "0 0% 98%",
            "destructive": "0 62.8% 30.6%",
            "border": "240 3.7% 15.9%",
            "ring": "142.4 71.8% 29.2%"
        }
    },
    "purple": {
        "light": {
            "background": "0 0% 100%",
            "foreground": "224 71.4% 4.1%",
            "primary": "262.1 83.3% 57.8%",
            "primary-foreground": "210 20% 98%",
            "secondary": "220 14.3% 95.9%",
            "secondary-foreground": "220.9 39.3% 11%",
            "muted": "220 14.3% 95.9%",
            "muted-foreground": "220 8.9% 46.1%",
            "accent": "220 14.3% 95.9%",
            "accent-foreground": "220.9 39.3% 11%",
            "destructive": "0 84.2% 60.2%",
            "border": "220 13% 91%",
            "ring": "262.1 83.3% 57.8%"
        },
        "dark": {
            "background": "224 71.4% 4.1%",
            "foreground": "210 20% 98%",
            "primary": "263.4 70% 50.4%",
            "primary-foreground": "210 20% 98%",
            "secondary": "215 27.9% 16.9%",
            "secondary-foreground": "210 20% 98%",
            "muted": "215 27.9% 16.9%",
            "muted-foreground": "217.9 10.6% 64.9%",
            "accent": "215 27.9% 16.9%",
            "accent-foreground": "210 20% 98%",
            "destructive": "0 62.8% 30.6%",
            "border": "215 27.9% 16.9%",
            "ring": "263.4 70% 50.4%"
        }
    },
    "orange": {
        "light": {
            "background": "0 0% 100%",
            "foreground": "20 14.3% 4.1%",
            "primary": "24.6 95% 53.1%",
            "primary-foreground": "60 9.1% 97.8%",
            "secondary": "60 4.8% 95.9%",
            "secondary-foreground": "24 9.8% 10%",
            "muted": "60 4.8% 95.9%",
            "muted-foreground": "25 5.3% 44.7%",
            "accent": "60 4.8% 95.9%",
            "accent-foreground": "24 9.8% 10%",
            "destructive": "0 84.2% 60.2%",
            "border": "20 5.9% 90%",
            "ring": "24.6 95% 53.1%"
        },
        "dark": {
            "background": "20 14.3% 4.1%",
            "foreground": "60 9.1% 97.8%",
            "primary": "20.5 90.2% 48.2%",
            "primary-foreground": "60 9.1% 97.8%",
            "secondary": "12 6.5% 15.1%",
            "secondary-foreground": "60 9.1% 97.8%",
            "muted": "12 6.5% 15.1%",
            "muted-foreground": "24 5.4% 63.9%",
            "accent": "12 6.5% 15.1%",
            "accent-foreground": "60 9.1% 97.8%",
            "destructive": "0 72.2% 50.6%",
            "border": "12 6.5% 15.1%",
            "ring": "20.5 90.2% 48.2%"
        }
    },
    "red": {
        "light": {
            "background": "0 0% 100%",
            "foreground": "0 0% 3.9%",
            "primary": "0 72.2% 50.6%",
            "primary-foreground": "0 85.7% 97.3%",
            "secondary": "0 0% 96.1%",
            "secondary-foreground": "0 0% 9%",
            "muted": "0 0% 96.1%",
            "muted-foreground": "0 0% 45.1%",
            "accent": "0 0% 96.1%",
            "accent-foreground": "0 0% 9%",
            "destructive": "0 84.2% 60.2%",
            "border": "0 0% 89.8%",
            "ring": "0 72.2% 50.6%"
        },
        "dark": {
            "background": "0 0% 3.9%",
            "foreground": "0 0% 98%",
            "primary": "0 72.2% 50.6%",
            "primary-foreground": "0 85.7% 97.3%",
            "secondary": "0 0% 14.9%",
            "secondary-foreground": "0 0% 98%",
            "muted": "0 0% 14.9%",
            "muted-foreground": "0 0% 63.9%",
            "accent": "0 0% 14.9%",
            "accent-foreground": "0 0% 98%",
            "destructive": "0 62.8% 30.6%",
            "border": "0 0% 14.9%",
            "ring": "0 72.2% 50.6%"
        }
    }
}

RADIUS_VALUES = {
    "none": "0",
    "sm": "0.25rem",
    "md": "0.5rem",
    "lg": "0.75rem",
    "full": "9999px"
}


def generate_css(theme_colors: dict, radius: str) -> str:
    """CSS 변수 생성"""
    light = theme_colors.get("light", {})
    dark = theme_colors.get("dark", {})
    radius_value = RADIUS_VALUES.get(radius, "0.5rem")

    css = '''@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
'''

    for key, value in light.items():
        css += f"    --{key}: {value};\n"

    css += f"    --radius: {radius_value};\n"
    css += "  }\n\n"

    css += "  .dark {\n"
    for key, value in dark.items():
        css += f"    --{key}: {value};\n"
    css += "  }\n"

    css += '''}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
  }
}
'''

    return css


def run(project_path: str, theme: str = "default", custom_colors: dict = None, border_radius: str = "md") -> dict:
    """
    프로젝트 스타일 수정

    Args:
        project_path: 프로젝트 경로
        theme: 테마 프리셋
        custom_colors: 커스텀 색상
        border_radius: 테두리 반경

    Returns:
        수정 결과
    """
    if not os.path.exists(project_path):
        return {"success": False, "error": f"프로젝트를 찾을 수 없습니다: {project_path}"}

    # globals.css 경로 찾기
    possible_paths = [
        os.path.join(project_path, "src", "app", "globals.css"),
        os.path.join(project_path, "app", "globals.css"),
        os.path.join(project_path, "styles", "globals.css")
    ]

    css_path = None
    for path in possible_paths:
        if os.path.exists(path):
            css_path = path
            break

    if not css_path:
        return {"success": False, "error": "globals.css를 찾을 수 없습니다"}

    # 테마 색상 가져오기
    if theme == "custom" and custom_colors:
        # 기본 테마를 기반으로 커스텀 색상 적용
        theme_colors = THEME_PRESETS["default"].copy()
        for mode in ["light", "dark"]:
            if mode in theme_colors:
                for key, value in custom_colors.items():
                    if key in theme_colors[mode]:
                        theme_colors[mode][key] = value
    elif theme in THEME_PRESETS:
        theme_colors = THEME_PRESETS[theme]
    else:
        return {
            "success": False,
            "error": f"알 수 없는 테마: {theme}",
            "available_themes": list(THEME_PRESETS.keys())
        }

    # CSS 생성 및 저장
    css_content = generate_css(theme_colors, border_radius)

    with open(css_path, "w", encoding="utf-8") as f:
        f.write(css_content)

    return {
        "success": True,
        "theme": theme,
        "border_radius": border_radius,
        "css_path": css_path,
        "message": f"스타일이 '{theme}' 테마로 업데이트되었습니다",
        "note": "변경사항을 보려면 개발 서버를 재시작하세요"
    }


def list_themes() -> dict:
    """사용 가능한 테마 목록"""
    themes = []
    for name, colors in THEME_PRESETS.items():
        themes.append({
            "name": name,
            "primary_light": colors["light"].get("primary", ""),
            "primary_dark": colors["dark"].get("primary", "")
        })

    return {
        "success": True,
        "themes": themes,
        "border_radius_options": list(RADIUS_VALUES.keys())
    }


if __name__ == "__main__":
    result = list_themes()
    print(json.dumps(result, indent=2, ensure_ascii=False))
