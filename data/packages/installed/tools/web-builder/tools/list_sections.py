"""
list_sections.py
사용 가능한 섹션 템플릿 목록을 반환합니다.
"""

import json

TOOL_NAME = "list_sections"
TOOL_DESCRIPTION = "사용 가능한 섹션 템플릿 목록을 반환합니다"
TOOL_PARAMETERS = {
    "category": {
        "type": "string",
        "description": "섹션 카테고리",
        "enum": ["all", "hero", "content", "feature", "social", "commerce", "form", "navigation"],
        "default": "all"
    }
}

# 섹션 템플릿 정의
SECTION_TEMPLATES = {
    "hero": {
        "description": "페이지 상단 히어로 섹션",
        "sections": [
            {
                "id": "hero-simple",
                "name": "심플 히어로",
                "description": "제목, 부제목, CTA 버튼이 있는 기본 히어로",
                "params": {
                    "title": {"type": "string", "required": True},
                    "subtitle": {"type": "string", "required": False},
                    "cta_text": {"type": "string", "default": "시작하기"},
                    "cta_link": {"type": "string", "default": "#"},
                    "secondary_cta_text": {"type": "string", "required": False},
                    "secondary_cta_link": {"type": "string", "required": False}
                }
            },
            {
                "id": "hero-with-image",
                "name": "이미지 히어로",
                "description": "좌측 텍스트, 우측 이미지 레이아웃",
                "params": {
                    "title": {"type": "string", "required": True},
                    "subtitle": {"type": "string", "required": False},
                    "image_url": {"type": "string", "required": True},
                    "image_alt": {"type": "string", "default": "Hero image"},
                    "cta_text": {"type": "string", "default": "시작하기"},
                    "cta_link": {"type": "string", "default": "#"}
                }
            },
            {
                "id": "hero-centered",
                "name": "중앙 정렬 히어로",
                "description": "모든 요소가 중앙 정렬된 히어로",
                "params": {
                    "title": {"type": "string", "required": True},
                    "subtitle": {"type": "string", "required": False},
                    "badge_text": {"type": "string", "required": False},
                    "cta_text": {"type": "string", "default": "시작하기"},
                    "cta_link": {"type": "string", "default": "#"}
                }
            },
            {
                "id": "hero-video-bg",
                "name": "비디오 배경 히어로",
                "description": "배경에 비디오가 있는 히어로",
                "params": {
                    "title": {"type": "string", "required": True},
                    "subtitle": {"type": "string", "required": False},
                    "video_url": {"type": "string", "required": True},
                    "cta_text": {"type": "string", "default": "시작하기"}
                }
            }
        ]
    },
    "content": {
        "description": "콘텐츠 섹션",
        "sections": [
            {
                "id": "content-text",
                "name": "텍스트 콘텐츠",
                "description": "제목과 본문 텍스트",
                "params": {
                    "title": {"type": "string", "required": True},
                    "content": {"type": "string", "required": True},
                    "align": {"type": "string", "enum": ["left", "center", "right"], "default": "left"}
                }
            },
            {
                "id": "content-two-column",
                "name": "2열 콘텐츠",
                "description": "좌우 2열 레이아웃",
                "params": {
                    "title": {"type": "string", "required": False},
                    "left_content": {"type": "string", "required": True},
                    "right_content": {"type": "string", "required": True}
                }
            },
            {
                "id": "content-image-text",
                "name": "이미지 + 텍스트",
                "description": "이미지와 텍스트가 나란히 배치",
                "params": {
                    "title": {"type": "string", "required": True},
                    "content": {"type": "string", "required": True},
                    "image_url": {"type": "string", "required": True},
                    "image_position": {"type": "string", "enum": ["left", "right"], "default": "right"}
                }
            }
        ]
    },
    "feature": {
        "description": "기능/특징 소개 섹션",
        "sections": [
            {
                "id": "features-grid",
                "name": "기능 그리드",
                "description": "3열 또는 4열 그리드로 기능 표시",
                "params": {
                    "title": {"type": "string", "required": False},
                    "subtitle": {"type": "string", "required": False},
                    "columns": {"type": "number", "enum": [2, 3, 4], "default": 3},
                    "features": {
                        "type": "array",
                        "required": True,
                        "items": {
                            "icon": {"type": "string"},
                            "title": {"type": "string"},
                            "description": {"type": "string"}
                        }
                    }
                }
            },
            {
                "id": "features-alternating",
                "name": "교차 기능",
                "description": "이미지와 텍스트가 교차 배치",
                "params": {
                    "features": {
                        "type": "array",
                        "required": True,
                        "items": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "image_url": {"type": "string"}
                        }
                    }
                }
            },
            {
                "id": "features-cards",
                "name": "기능 카드",
                "description": "카드 형태로 기능 표시",
                "params": {
                    "title": {"type": "string", "required": False},
                    "features": {
                        "type": "array",
                        "required": True,
                        "items": {
                            "icon": {"type": "string"},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "link": {"type": "string", "required": False}
                        }
                    }
                }
            }
        ]
    },
    "social": {
        "description": "사회적 증거 (리뷰, 로고 등)",
        "sections": [
            {
                "id": "testimonials",
                "name": "고객 후기",
                "description": "고객 리뷰/추천 글",
                "params": {
                    "title": {"type": "string", "default": "고객 후기"},
                    "testimonials": {
                        "type": "array",
                        "required": True,
                        "items": {
                            "quote": {"type": "string"},
                            "author": {"type": "string"},
                            "role": {"type": "string"},
                            "avatar_url": {"type": "string", "required": False}
                        }
                    }
                }
            },
            {
                "id": "logo-cloud",
                "name": "로고 클라우드",
                "description": "파트너/고객사 로고 나열",
                "params": {
                    "title": {"type": "string", "default": "신뢰하는 기업들"},
                    "logos": {
                        "type": "array",
                        "required": True,
                        "items": {
                            "name": {"type": "string"},
                            "image_url": {"type": "string"},
                            "link": {"type": "string", "required": False}
                        }
                    }
                }
            },
            {
                "id": "stats",
                "name": "통계",
                "description": "숫자로 보여주는 성과",
                "params": {
                    "title": {"type": "string", "required": False},
                    "stats": {
                        "type": "array",
                        "required": True,
                        "items": {
                            "value": {"type": "string"},
                            "label": {"type": "string"}
                        }
                    }
                }
            }
        ]
    },
    "commerce": {
        "description": "가격 및 상업 관련 섹션",
        "sections": [
            {
                "id": "pricing-cards",
                "name": "가격표 카드",
                "description": "플랜별 가격 비교",
                "params": {
                    "title": {"type": "string", "default": "가격 안내"},
                    "subtitle": {"type": "string", "required": False},
                    "plans": {
                        "type": "array",
                        "required": True,
                        "items": {
                            "name": {"type": "string"},
                            "price": {"type": "string"},
                            "period": {"type": "string", "default": "/월"},
                            "description": {"type": "string"},
                            "features": {"type": "array"},
                            "cta_text": {"type": "string", "default": "선택하기"},
                            "highlighted": {"type": "boolean", "default": False}
                        }
                    }
                }
            },
            {
                "id": "cta-banner",
                "name": "CTA 배너",
                "description": "행동 유도 배너",
                "params": {
                    "title": {"type": "string", "required": True},
                    "subtitle": {"type": "string", "required": False},
                    "cta_text": {"type": "string", "required": True},
                    "cta_link": {"type": "string", "default": "#"},
                    "background": {"type": "string", "enum": ["primary", "secondary", "gradient"], "default": "primary"}
                }
            }
        ]
    },
    "form": {
        "description": "폼 및 입력 섹션",
        "sections": [
            {
                "id": "contact-form",
                "name": "문의 폼",
                "description": "연락처 및 문의 폼",
                "params": {
                    "title": {"type": "string", "default": "문의하기"},
                    "subtitle": {"type": "string", "required": False},
                    "fields": {
                        "type": "array",
                        "default": ["name", "email", "message"],
                        "items": {"type": "string", "enum": ["name", "email", "phone", "company", "subject", "message"]}
                    },
                    "submit_text": {"type": "string", "default": "보내기"}
                }
            },
            {
                "id": "newsletter",
                "name": "뉴스레터",
                "description": "이메일 구독 폼",
                "params": {
                    "title": {"type": "string", "default": "뉴스레터 구독"},
                    "subtitle": {"type": "string", "required": False},
                    "placeholder": {"type": "string", "default": "이메일을 입력하세요"},
                    "submit_text": {"type": "string", "default": "구독하기"}
                }
            }
        ]
    },
    "navigation": {
        "description": "네비게이션 관련 섹션",
        "sections": [
            {
                "id": "header",
                "name": "헤더",
                "description": "페이지 상단 네비게이션",
                "params": {
                    "logo": {"type": "string", "required": False},
                    "logo_text": {"type": "string", "required": False},
                    "nav_items": {
                        "type": "array",
                        "required": True,
                        "items": {
                            "label": {"type": "string"},
                            "href": {"type": "string"}
                        }
                    },
                    "cta_text": {"type": "string", "required": False},
                    "cta_link": {"type": "string", "required": False}
                }
            },
            {
                "id": "footer",
                "name": "푸터",
                "description": "페이지 하단",
                "params": {
                    "logo": {"type": "string", "required": False},
                    "logo_text": {"type": "string", "required": False},
                    "description": {"type": "string", "required": False},
                    "columns": {
                        "type": "array",
                        "required": False,
                        "items": {
                            "title": {"type": "string"},
                            "links": {"type": "array"}
                        }
                    },
                    "social_links": {
                        "type": "array",
                        "required": False,
                        "items": {
                            "platform": {"type": "string"},
                            "url": {"type": "string"}
                        }
                    },
                    "copyright": {"type": "string", "required": False}
                }
            }
        ]
    }
}


def run(category: str = "all") -> dict:
    """
    사용 가능한 섹션 템플릿 목록 반환

    Args:
        category: 카테고리 필터

    Returns:
        섹션 템플릿 목록
    """
    if category == "all":
        total_count = sum(len(cat["sections"]) for cat in SECTION_TEMPLATES.values())
        return {
            "success": True,
            "total_sections": total_count,
            "categories": SECTION_TEMPLATES
        }
    else:
        if category not in SECTION_TEMPLATES:
            return {
                "success": False,
                "error": f"잘못된 카테고리: {category}",
                "available_categories": list(SECTION_TEMPLATES.keys())
            }

        return {
            "success": True,
            "category": category,
            "data": SECTION_TEMPLATES[category]
        }


if __name__ == "__main__":
    result = run(category="hero")
    print(json.dumps(result, indent=2, ensure_ascii=False))
