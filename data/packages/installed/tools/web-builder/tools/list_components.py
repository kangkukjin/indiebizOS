"""
list_components.py
사용 가능한 shadcn/ui 컴포넌트 목록을 반환합니다.
"""

import json
import os

TOOL_NAME = "list_components"
TOOL_DESCRIPTION = "사용 가능한 shadcn/ui 컴포넌트 목록을 반환합니다"
TOOL_PARAMETERS = {
    "project_path": {
        "type": "string",
        "description": "프로젝트 경로 (설치된 컴포넌트 확인용, 선택사항)",
        "required": False
    },
    "category": {
        "type": "string",
        "description": "카테고리 필터",
        "enum": ["all", "layout", "form", "data", "feedback", "navigation", "overlay"],
        "default": "all"
    }
}

# 카테고리별 컴포넌트 분류
COMPONENTS_BY_CATEGORY = {
    "layout": {
        "description": "레이아웃 및 컨테이너",
        "components": [
            {"name": "card", "description": "콘텐츠를 담는 카드 컨테이너"},
            {"name": "aspect-ratio", "description": "고정 비율 컨테이너"},
            {"name": "scroll-area", "description": "커스텀 스크롤바 영역"},
            {"name": "separator", "description": "구분선"},
            {"name": "resizable", "description": "크기 조절 가능한 패널"},
            {"name": "collapsible", "description": "접기/펼치기 컨테이너"},
            {"name": "accordion", "description": "아코디언 (접이식 패널)"},
            {"name": "tabs", "description": "탭 컨테이너"},
        ]
    },
    "form": {
        "description": "폼 입력 요소",
        "components": [
            {"name": "button", "description": "버튼"},
            {"name": "input", "description": "텍스트 입력"},
            {"name": "textarea", "description": "여러 줄 텍스트 입력"},
            {"name": "select", "description": "드롭다운 선택"},
            {"name": "checkbox", "description": "체크박스"},
            {"name": "radio-group", "description": "라디오 버튼 그룹"},
            {"name": "switch", "description": "토글 스위치"},
            {"name": "slider", "description": "슬라이더"},
            {"name": "form", "description": "폼 (react-hook-form 통합)"},
            {"name": "label", "description": "라벨"},
            {"name": "input-otp", "description": "OTP 입력"},
            {"name": "toggle", "description": "토글 버튼"},
            {"name": "toggle-group", "description": "토글 버튼 그룹"},
            {"name": "calendar", "description": "달력"},
            {"name": "date-picker", "description": "날짜 선택"},
            {"name": "combobox", "description": "검색 가능한 선택"},
        ]
    },
    "data": {
        "description": "데이터 표시",
        "components": [
            {"name": "table", "description": "테이블"},
            {"name": "data-table", "description": "데이터 테이블 (정렬, 필터)"},
            {"name": "badge", "description": "배지 (라벨)"},
            {"name": "avatar", "description": "아바타 이미지"},
            {"name": "progress", "description": "진행률 바"},
            {"name": "skeleton", "description": "로딩 스켈레톤"},
            {"name": "chart", "description": "차트"},
            {"name": "carousel", "description": "캐러셀 (슬라이더)"},
        ]
    },
    "feedback": {
        "description": "사용자 피드백",
        "components": [
            {"name": "alert", "description": "알림 메시지"},
            {"name": "alert-dialog", "description": "확인 다이얼로그"},
            {"name": "toast", "description": "토스트 알림"},
            {"name": "sonner", "description": "토스트 알림 (Sonner)"},
        ]
    },
    "navigation": {
        "description": "네비게이션",
        "components": [
            {"name": "navigation-menu", "description": "네비게이션 메뉴"},
            {"name": "menubar", "description": "메뉴바"},
            {"name": "breadcrumb", "description": "브레드크럼"},
            {"name": "pagination", "description": "페이지네이션"},
            {"name": "command", "description": "명령 팔레트"},
        ]
    },
    "overlay": {
        "description": "오버레이 및 팝업",
        "components": [
            {"name": "dialog", "description": "다이얼로그 (모달)"},
            {"name": "sheet", "description": "사이드 시트"},
            {"name": "drawer", "description": "드로어"},
            {"name": "popover", "description": "팝오버"},
            {"name": "tooltip", "description": "툴팁"},
            {"name": "hover-card", "description": "호버 카드"},
            {"name": "dropdown-menu", "description": "드롭다운 메뉴"},
            {"name": "context-menu", "description": "컨텍스트 메뉴 (우클릭)"},
        ]
    }
}


def get_installed_components(project_path: str) -> list:
    """프로젝트에 설치된 컴포넌트 목록"""
    if not project_path:
        return []

    info_path = os.path.join(project_path, ".web-builder.json")
    if os.path.exists(info_path):
        with open(info_path, "r") as f:
            info = json.load(f)
            return info.get("shadcn_components", [])

    # components/ui 폴더에서 직접 확인
    ui_path = os.path.join(project_path, "src", "components", "ui")
    if not os.path.exists(ui_path):
        ui_path = os.path.join(project_path, "components", "ui")

    if os.path.exists(ui_path):
        files = os.listdir(ui_path)
        return [f.replace(".tsx", "") for f in files if f.endswith(".tsx")]

    return []


def run(project_path: str = None, category: str = "all") -> dict:
    """
    사용 가능한 컴포넌트 목록 반환

    Args:
        project_path: 프로젝트 경로 (설치 여부 확인)
        category: 카테고리 필터

    Returns:
        컴포넌트 목록
    """
    installed = get_installed_components(project_path) if project_path else []

    if category == "all":
        result = {}
        for cat_name, cat_data in COMPONENTS_BY_CATEGORY.items():
            components = []
            for comp in cat_data["components"]:
                comp_info = comp.copy()
                comp_info["installed"] = comp["name"] in installed
                components.append(comp_info)
            result[cat_name] = {
                "description": cat_data["description"],
                "components": components
            }

        # 전체 목록도 추가
        all_components = []
        for cat_data in COMPONENTS_BY_CATEGORY.values():
            for comp in cat_data["components"]:
                all_components.append(comp["name"])

        return {
            "success": True,
            "total_count": len(all_components),
            "installed_count": len(installed),
            "installed": installed,
            "categories": result
        }
    else:
        if category not in COMPONENTS_BY_CATEGORY:
            return {
                "success": False,
                "error": f"잘못된 카테고리: {category}",
                "available_categories": list(COMPONENTS_BY_CATEGORY.keys())
            }

        cat_data = COMPONENTS_BY_CATEGORY[category]
        components = []
        for comp in cat_data["components"]:
            comp_info = comp.copy()
            comp_info["installed"] = comp["name"] in installed
            components.append(comp_info)

        return {
            "success": True,
            "category": category,
            "description": cat_data["description"],
            "components": components,
            "installed": [c for c in installed if c in [comp["name"] for comp in cat_data["components"]]]
        }


if __name__ == "__main__":
    result = run(category="form")
    print(json.dumps(result, indent=2, ensure_ascii=False))
