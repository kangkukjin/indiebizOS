"""
shadcn_slides.py
shadcn/ui 컴포넌트와 web-builder 테마를 활용한 슬라이드 생성
"""

import os
import json
import uuid
import base64
import urllib.request
from jinja2 import Template

# ============================================
# shadcn/ui 테마 색상 (CSS 변수)
# ============================================

THEMES = {
    "default": {
        "background": "0 0% 100%",
        "foreground": "0 0% 3.9%",
        "primary": "0 0% 9%",
        "primary-foreground": "0 0% 98%",
        "secondary": "0 0% 96.1%",
        "secondary-foreground": "0 0% 9%",
        "muted": "0 0% 96.1%",
        "muted-foreground": "0 0% 45.1%",
        "accent": "0 0% 96.1%",
        "border": "0 0% 89.8%",
        "ring": "0 0% 3.9%",
        "radius": "0.5rem"
    },
    "blue": {
        "background": "0 0% 100%",
        "foreground": "222.2 84% 4.9%",
        "primary": "221.2 83.2% 53.3%",
        "primary-foreground": "210 40% 98%",
        "secondary": "210 40% 96.1%",
        "secondary-foreground": "222.2 47.4% 11.2%",
        "muted": "210 40% 96.1%",
        "muted-foreground": "215.4 16.3% 46.9%",
        "accent": "210 40% 96.1%",
        "border": "214.3 31.8% 91.4%",
        "ring": "221.2 83.2% 53.3%",
        "radius": "0.5rem"
    },
    "green": {
        "background": "0 0% 100%",
        "foreground": "240 10% 3.9%",
        "primary": "142.1 76.2% 36.3%",
        "primary-foreground": "355.7 100% 97.3%",
        "secondary": "240 4.8% 95.9%",
        "secondary-foreground": "240 5.9% 10%",
        "muted": "240 4.8% 95.9%",
        "muted-foreground": "240 3.8% 46.1%",
        "accent": "240 4.8% 95.9%",
        "border": "240 5.9% 90%",
        "ring": "142.1 76.2% 36.3%",
        "radius": "0.5rem"
    },
    "purple": {
        "background": "0 0% 100%",
        "foreground": "224 71.4% 4.1%",
        "primary": "262.1 83.3% 57.8%",
        "primary-foreground": "210 20% 98%",
        "secondary": "220 14.3% 95.9%",
        "secondary-foreground": "220.9 39.3% 11%",
        "muted": "220 14.3% 95.9%",
        "muted-foreground": "220 8.9% 46.1%",
        "accent": "220 14.3% 95.9%",
        "border": "220 13% 91%",
        "ring": "262.1 83.3% 57.8%",
        "radius": "0.5rem"
    },
    "orange": {
        "background": "0 0% 100%",
        "foreground": "20 14.3% 4.1%",
        "primary": "24.6 95% 53.1%",
        "primary-foreground": "60 9.1% 97.8%",
        "secondary": "60 4.8% 95.9%",
        "secondary-foreground": "24 9.8% 10%",
        "muted": "60 4.8% 95.9%",
        "muted-foreground": "25 5.3% 44.7%",
        "accent": "60 4.8% 95.9%",
        "border": "20 5.9% 90%",
        "ring": "24.6 95% 53.1%",
        "radius": "0.5rem"
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
        "border": "0 0% 14.9%",
        "ring": "0 0% 83.1%",
        "radius": "0.5rem"
    }
}

# ============================================
# 슬라이드 템플릿 (shadcn 스타일)
# ============================================

SLIDE_BASE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Black+Han+Sans&family=Do+Hyeon&family=Gothic+A1:wght@400;700;900&family=Noto+Sans+KR:wght@300;400;500;700;900&family=Sunflower:wght@300;500;700&family=Jua&family=Inter:wght@300;400;500;600;700;800;900&family=Montserrat:wght@400;600;700;800;900&family=Playfair+Display:wght@400;600;700;900&family=Poppins:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css"/>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script src="https://unpkg.com/@lottiefiles/lottie-player@2/dist/lottie-player.js"></script>
    <style>

        :root {
            --background: {{theme.background}};
            --foreground: {{theme.foreground}};
            --primary: {{theme.primary}};
            --primary-foreground: {{theme['primary-foreground']}};
            --secondary: {{theme.secondary}};
            --secondary-foreground: {{theme['secondary-foreground']}};
            --muted: {{theme.muted}};
            --muted-foreground: {{theme['muted-foreground']}};
            --accent: {{theme.accent}};
            --border: {{theme.border}};
            --ring: {{theme.ring}};
            --radius: {{theme.radius}};
        }

        body {
            margin: 0;
            padding: 0;
            width: {{width}}px;
            height: {{height}}px;
            overflow: hidden;
            font-family: 'Noto Sans KR', 'Inter', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
            background: hsl(var(--background));
            color: hsl(var(--foreground));
        }

        .slide-container {
            width: {{width}}px;
            height: {{height}}px;
            overflow: hidden;
        }

        /* shadcn Button 스타일 */
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            white-space: nowrap;
            border-radius: var(--radius);
            font-size: 0.875rem;
            font-weight: 500;
            transition: all 0.2s;
            padding: 0.5rem 1rem;
        }
        .btn-default {
            background: hsl(var(--primary));
            color: hsl(var(--primary-foreground));
        }
        .btn-secondary {
            background: hsl(var(--secondary));
            color: hsl(var(--secondary-foreground));
        }
        .btn-outline {
            border: 1px solid hsl(var(--border));
            background: transparent;
        }
        .btn-lg {
            padding: 0.75rem 2rem;
            font-size: 1.125rem;
        }

        /* shadcn Badge 스타일 */
        .badge {
            display: inline-flex;
            align-items: center;
            border-radius: 9999px;
            padding: 0.25rem 0.75rem;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge-default {
            background: hsl(var(--primary));
            color: hsl(var(--primary-foreground));
        }
        .badge-secondary {
            background: hsl(var(--secondary));
            color: hsl(var(--secondary-foreground));
        }

        /* shadcn Card 스타일 */
        .card {
            border-radius: var(--radius);
            border: 1px solid hsl(var(--border));
            background: hsl(var(--background));
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .card-header {
            padding: 1.5rem;
        }
        .card-title {
            font-size: 1.5rem;
            font-weight: 600;
            line-height: 1;
        }
        .card-description {
            font-size: 0.875rem;
            color: hsl(var(--muted-foreground));
            margin-top: 0.5rem;
        }
        .card-content {
            padding: 0 1.5rem 1.5rem;
        }
    </style>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        background: 'hsl(var(--background))',
                        foreground: 'hsl(var(--foreground))',
                        primary: {
                            DEFAULT: 'hsl(var(--primary))',
                            foreground: 'hsl(var(--primary-foreground))'
                        },
                        secondary: {
                            DEFAULT: 'hsl(var(--secondary))',
                            foreground: 'hsl(var(--secondary-foreground))'
                        },
                        muted: {
                            DEFAULT: 'hsl(var(--muted))',
                            foreground: 'hsl(var(--muted-foreground))'
                        },
                        accent: {
                            DEFAULT: 'hsl(var(--accent))',
                            foreground: 'hsl(var(--accent-foreground))'
                        },
                        border: 'hsl(var(--border))',
                    },
                    borderRadius: {
                        lg: 'var(--radius)',
                        md: 'calc(var(--radius) - 2px)',
                        sm: 'calc(var(--radius) - 4px)',
                    }
                }
            }
        }
    </script>
</head>
<body>
    <div class="slide-container">
        {{content|safe}}
    </div>
    <script>
        lucide.createIcons();
    </script>
</body>
</html>
"""

# ============================================
# 슬라이드 타입별 레이아웃
# ============================================

SLIDE_LAYOUTS = {
    # 히어로 슬라이드 (중앙 정렬)
    "hero": """
<div class="w-full h-full flex flex-col items-center justify-center p-16 bg-gradient-to-br from-background to-muted/30">
    {% if badge %}<span class="badge badge-secondary mb-6 animate__animated animate__fadeInDown">{{badge}}</span>{% endif %}
    <h1 class="text-6xl font-black text-center tracking-tight mb-6 animate__animated animate__fadeInUp" style="color: hsl(var(--foreground))">
        {{title}}
    </h1>
    {% if subtitle %}
    <p class="text-2xl text-center max-w-3xl animate__animated animate__fadeInUp animate__delay-1s" style="color: hsl(var(--muted-foreground))">
        {{subtitle}}
    </p>
    {% endif %}
    {% if cta_text %}
    <div class="mt-10 animate__animated animate__fadeInUp animate__delay-2s">
        <span class="btn btn-default btn-lg">{{cta_text}}</span>
    </div>
    {% endif %}
</div>
""",

    # 히어로 + 이미지 (좌우 분할)
    "hero_image": """
<div class="w-full h-full flex">
    <div class="w-1/2 h-full flex flex-col justify-center p-16">
        {% if badge %}<span class="badge badge-secondary mb-4">{{badge}}</span>{% endif %}
        <h1 class="text-5xl font-bold tracking-tight mb-6" style="color: hsl(var(--foreground))">
            {{title}}
        </h1>
        {% if subtitle %}
        <p class="text-xl mb-8" style="color: hsl(var(--muted-foreground))">
            {{subtitle}}
        </p>
        {% endif %}
        {% if cta_text %}
        <div>
            <span class="btn btn-default btn-lg">{{cta_text}}</span>
        </div>
        {% endif %}
    </div>
    <div class="w-1/2 h-full flex items-center justify-center p-8" style="background: hsl(var(--muted))">
        {% if image_data %}
        <img src="{{image_data}}" class="max-w-full max-h-full object-contain rounded-lg shadow-2xl">
        {% else %}
        <div class="w-80 h-80 rounded-lg flex items-center justify-center" style="background: hsl(var(--secondary))">
            <i data-lucide="image" class="w-20 h-20" style="color: hsl(var(--muted-foreground))"></i>
        </div>
        {% endif %}
    </div>
</div>
""",

    # 기능 그리드 (3열)
    "features": """
<div class="w-full h-full p-16">
    {% if title %}
    <div class="text-center mb-12">
        <h2 class="text-4xl font-bold mb-4" style="color: hsl(var(--foreground))">{{title}}</h2>
        {% if subtitle %}<p class="text-xl" style="color: hsl(var(--muted-foreground))">{{subtitle}}</p>{% endif %}
    </div>
    {% endif %}
    <div class="grid grid-cols-3 gap-8">
        {% for feature in features %}
        <div class="card p-6">
            <div class="w-12 h-12 rounded-lg flex items-center justify-center mb-4" style="background: hsl(var(--primary) / 0.1)">
                {% if feature.icon %}
                <span class="text-2xl">{{feature.icon}}</span>
                {% else %}
                <i data-lucide="star" class="w-6 h-6" style="color: hsl(var(--primary))"></i>
                {% endif %}
            </div>
            <h3 class="text-xl font-semibold mb-2" style="color: hsl(var(--foreground))">{{feature.title}}</h3>
            <p class="text-sm" style="color: hsl(var(--muted-foreground))">{{feature.description}}</p>
        </div>
        {% endfor %}
    </div>
</div>
""",

    # 통계 (4열)
    "stats": """
<div class="w-full h-full flex flex-col justify-center p-16" style="background: hsl(var(--primary)); color: hsl(var(--primary-foreground))">
    {% if title %}
    <h2 class="text-4xl font-bold text-center mb-16">{{title}}</h2>
    {% endif %}
    <div class="grid grid-cols-4 gap-8">
        {% for stat in stats %}
        <div class="text-center">
            <p class="text-5xl font-bold mb-2">{{stat.value}}</p>
            <p class="text-lg opacity-80">{{stat.label}}</p>
        </div>
        {% endfor %}
    </div>
</div>
""",

    # 인용/후기
    "testimonial": """
<div class="w-full h-full flex items-center justify-center p-16" style="background: hsl(var(--muted) / 0.3)">
    <div class="max-w-4xl text-center">
        <i data-lucide="quote" class="w-16 h-16 mx-auto mb-8 opacity-20" style="color: hsl(var(--primary))"></i>
        <p class="text-3xl font-medium mb-8 leading-relaxed" style="color: hsl(var(--foreground))">
            "{{quote|default('인용문을 입력하세요')}}"
        </p>
        <div class="flex items-center justify-center gap-4">
            {% if avatar_data %}
            <img src="{{avatar_data}}" class="w-16 h-16 rounded-full">
            {% else %}
            <div class="w-16 h-16 rounded-full flex items-center justify-center text-xl font-bold" style="background: hsl(var(--primary)); color: hsl(var(--primary-foreground))">
                {{(author|default('익명'))[:2]|upper}}
            </div>
            {% endif %}
            <div class="text-left">
                <p class="font-semibold" style="color: hsl(var(--foreground))">{{author|default('익명')}}</p>
                <p class="text-sm" style="color: hsl(var(--muted-foreground))">{{role|default('')}}</p>
            </div>
        </div>
    </div>
</div>
""",

    # 가격표
    "pricing": """
<div class="w-full h-full p-12">
    {% if title %}
    <h2 class="text-4xl font-bold text-center mb-8" style="color: hsl(var(--foreground))">{{title}}</h2>
    {% endif %}
    <div class="grid grid-cols-3 gap-6 h-[calc(100%-80px)]">
        {% for plan in plans %}
        <div class="card flex flex-col {% if plan.highlighted %}border-2{% endif %}" {% if plan.highlighted %}style="border-color: hsl(var(--primary))"{% endif %}>
            {% if plan.highlighted %}
            <div class="text-center py-2 text-sm font-medium" style="background: hsl(var(--primary)); color: hsl(var(--primary-foreground))">추천</div>
            {% endif %}
            <div class="p-6 flex-1 flex flex-col">
                <h3 class="text-xl font-semibold" style="color: hsl(var(--foreground))">{{plan.name}}</h3>
                <p class="text-sm mt-1" style="color: hsl(var(--muted-foreground))">{{plan.description}}</p>
                <div class="my-6">
                    <span class="text-4xl font-bold" style="color: hsl(var(--foreground))">{{plan.price}}</span>
                    <span style="color: hsl(var(--muted-foreground))">{{plan.period|default('/월')}}</span>
                </div>
                <ul class="space-y-2 flex-1">
                    {% for feature in plan.features %}
                    <li class="flex items-center gap-2 text-sm">
                        <i data-lucide="check" class="w-4 h-4" style="color: hsl(var(--primary))"></i>
                        <span style="color: hsl(var(--foreground))">{{feature}}</span>
                    </li>
                    {% endfor %}
                </ul>
                <div class="mt-6">
                    <span class="btn {% if plan.highlighted %}btn-default{% else %}btn-outline{% endif %} w-full justify-center">
                        {{plan.cta_text|default('선택하기')}}
                    </span>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
""",

    # CTA 배너
    "cta": """
<div class="w-full h-full flex flex-col items-center justify-center p-16" style="background: hsl(var(--primary)); color: hsl(var(--primary-foreground))">
    <h2 class="text-5xl font-bold text-center mb-6">{{title}}</h2>
    {% if subtitle %}
    <p class="text-xl text-center opacity-90 max-w-2xl mb-10">{{subtitle}}</p>
    {% endif %}
    <span class="btn btn-lg" style="background: hsl(var(--primary-foreground)); color: hsl(var(--primary))">
        {{cta_text|default('시작하기')}}
    </span>
</div>
""",

    # 콘텐츠 + 이미지
    "content_image": """
<div class="w-full h-full flex {% if image_position == 'left' %}flex-row-reverse{% endif %}">
    <div class="w-1/2 h-full flex flex-col justify-center p-16">
        <h2 class="text-4xl font-bold mb-6" style="color: hsl(var(--foreground))">{{title}}</h2>
        <p class="text-lg leading-relaxed" style="color: hsl(var(--muted-foreground))">{{content}}</p>
        {% if cta_text %}
        <div class="mt-8">
            <span class="btn btn-default">{{cta_text}}</span>
        </div>
        {% endif %}
    </div>
    <div class="w-1/2 h-full">
        {% if image_data %}
        <img src="{{image_data}}" class="w-full h-full object-cover">
        {% else %}
        <div class="w-full h-full flex items-center justify-center" style="background: hsl(var(--muted))">
            <i data-lucide="image" class="w-24 h-24" style="color: hsl(var(--muted-foreground))"></i>
        </div>
        {% endif %}
    </div>
</div>
""",

    # 타임라인/단계
    "steps": """
<div class="w-full h-full p-16">
    {% if title %}
    <h2 class="text-4xl font-bold text-center mb-12" style="color: hsl(var(--foreground))">{{title}}</h2>
    {% endif %}
    <div class="flex justify-between items-start gap-4">
        {% for step in steps %}
        <div class="flex-1 text-center">
            <div class="w-16 h-16 rounded-full mx-auto mb-4 flex items-center justify-center text-2xl font-bold" style="background: hsl(var(--primary)); color: hsl(var(--primary-foreground))">
                {{loop.index}}
            </div>
            <h3 class="text-xl font-semibold mb-2" style="color: hsl(var(--foreground))">{{step.title}}</h3>
            <p class="text-sm" style="color: hsl(var(--muted-foreground))">{{step.description}}</p>
        </div>
        {% if not loop.last %}
        <div class="flex-shrink-0 mt-8">
            <i data-lucide="arrow-right" class="w-8 h-8" style="color: hsl(var(--border))"></i>
        </div>
        {% endif %}
        {% endfor %}
    </div>
</div>
""",

    # 커스텀 (Tailwind 자유 작성)
    "custom": """
{{custom_html|safe}}
"""
}


def get_image_base64(image_path: str) -> str:
    """이미지를 Base64로 변환"""
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        with open(image_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode('utf-8')
            ext = os.path.splitext(image_path)[1].lower()
            mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".gif": "image/gif"
            }.get(ext, "image/png")
            return f"data:{mime};base64,{encoded}"
    except Exception as e:
        print(f"이미지 로드 실패: {e}")
        return None


def render_slide(slide_data: dict, theme_name: str = "default", width: int = 1280, height: int = 720) -> str:
    """슬라이드 HTML 생성"""
    from jinja2 import Environment, BaseLoader, Undefined

    # Undefined 변수에 대해 빈 문자열 반환하는 환경 설정
    class SilentUndefined(Undefined):
        def _fail_with_undefined_error(self, *args, **kwargs):
            return ''
        def __str__(self):
            return ''
        def __iter__(self):
            return iter([])
        def __bool__(self):
            return False
        def __getitem__(self, key):
            return ''
        def __getattr__(self, name):
            return SilentUndefined()

    env = Environment(loader=BaseLoader(), undefined=SilentUndefined)

    # 테마 가져오기
    theme = THEMES.get(theme_name, THEMES["default"])

    # 레이아웃 타입
    layout_type = slide_data.get("layout", "hero")
    layout_template = SLIDE_LAYOUTS.get(layout_type, SLIDE_LAYOUTS["hero"])

    # 이미지 처리
    if slide_data.get("image_path"):
        slide_data["image_data"] = get_image_base64(slide_data["image_path"])
    if slide_data.get("avatar_path"):
        slide_data["avatar_data"] = get_image_base64(slide_data["avatar_path"])

    # 레이아웃 렌더링 (SilentUndefined 사용)
    layout_tpl = env.from_string(layout_template)
    content_html = layout_tpl.render(**slide_data)

    # 베이스 템플릿에 삽입
    base_tpl = env.from_string(SLIDE_BASE_TEMPLATE)
    full_html = base_tpl.render(
        theme=theme,
        width=width,
        height=height,
        content=content_html
    )

    return full_html


def create_shadcn_slides(tool_input: dict, output_base: str) -> str:
    """
    shadcn 스타일 슬라이드 생성

    Args:
        tool_input: {
            "slides": [
                {
                    "layout": "hero",  # hero, hero_image, features, stats, testimonial, pricing, cta, content_image, steps, custom
                    "title": "제목",
                    "subtitle": "부제목",
                    ... (레이아웃별 속성)
                }
            ],
            "theme": "blue",  # default, blue, green, purple, orange, dark
            "output_dir": "경로" (선택)
        }

    Returns:
        생성 결과 JSON
    """
    slides_data = tool_input.get("slides", [])
    theme_name = tool_input.get("theme", "default")
    custom_output_dir = tool_input.get("output_dir")
    width = tool_input.get("width", 1280)
    height = tool_input.get("height", 720)

    output_dir = custom_output_dir if custom_output_dir else os.path.join(output_base, f"shadcn_slides_{uuid.uuid4().hex[:8]}")
    os.makedirs(output_dir, exist_ok=True)

    generated_paths = []
    html_paths = []

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})

            for i, slide in enumerate(slides_data):
                # HTML 생성
                html_content = render_slide(slide, theme_name, width, height)

                # HTML 파일 저장 (디버깅용)
                html_path = os.path.join(output_dir, f"slide_{i+1:02d}.html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                html_paths.append(html_path)

                # 렌더링
                page.set_content(html_content)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(800)  # Tailwind/폰트/아이콘 로딩 대기

                # 스크린샷
                png_path = os.path.join(output_dir, f"slide_{i+1:02d}.png")
                page.screenshot(path=png_path)
                generated_paths.append(png_path)

            browser.close()

        return json.dumps({
            "success": True,
            "message": f"{len(generated_paths)}개의 슬라이드가 생성되었습니다",
            "output_dir": output_dir,
            "images": generated_paths,
            "html_files": html_paths,
            "theme": theme_name
        }, ensure_ascii=False)

    except ImportError:
        return json.dumps({
            "success": False,
            "error": "Playwright가 설치되어 있지 않습니다. 'pip install playwright && playwright install chromium' 실행 필요"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        }, ensure_ascii=False)


# 도구 실행 함수 (handler.py와 통합용)
def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """도구 실행"""
    if tool_name == "create_shadcn_slides":
        output_base = os.path.join(project_path, "outputs")
        os.makedirs(output_base, exist_ok=True)
        return create_shadcn_slides(tool_input, output_base)

    return json.dumps({"error": f"알 수 없는 도구: {tool_name}"})


if __name__ == "__main__":
    # 테스트
    test_input = {
        "theme": "blue",
        "slides": [
            {
                "layout": "hero",
                "badge": "New Release",
                "title": "IndieBiz OS",
                "subtitle": "AI 기반 통합 비즈니스 관리 시스템",
                "cta_text": "시작하기"
            },
            {
                "layout": "features",
                "title": "주요 기능",
                "features": [
                    {"icon": "🤖", "title": "AI 에이전트", "description": "맞춤형 AI 비서가 업무를 도와줍니다"},
                    {"icon": "📊", "title": "데이터 분석", "description": "실시간 인사이트를 제공합니다"},
                    {"icon": "🔗", "title": "통합 연동", "description": "다양한 서비스와 연결됩니다"}
                ]
            },
            {
                "layout": "stats",
                "title": "성과",
                "stats": [
                    {"value": "10K+", "label": "활성 사용자"},
                    {"value": "99.9%", "label": "가동률"},
                    {"value": "24/7", "label": "지원"},
                    {"value": "50+", "label": "통합 서비스"}
                ]
            },
            {
                "layout": "cta",
                "title": "지금 시작하세요",
                "subtitle": "무료로 체험해보고 비즈니스를 성장시키세요",
                "cta_text": "무료 체험 시작"
            }
        ]
    }

    result = create_shadcn_slides(test_input, "/tmp/test_slides")
    print(result)
