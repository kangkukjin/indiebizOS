"""
shadcn_layouts.py — 슬라이드 HTML 골격·레이아웃 템플릿 (shadcn_slides.py 에서 분리, 2026-08-06 1500줄 규칙)

SLIDE_BASE_TEMPLATE = 페이지 골격(Jinja2) / SLIDE_LAYOUTS = 슬라이드 타입별 본문.
순수 데이터 — 로직 금지.
"""

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
    {{design_system_head|safe}}
    <style>
        /* style_overrides — spec.style_overrides 적용 (있을 때만 비어있지 않음) */
        {{style_overrides_css|safe}}
    </style>
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

        /* === Design System CSS (적용된 디자인 시스템의 비주얼 정체성) === */
        {{design_system_css|safe}}

        /* PNG 캡처는 정적이므로 animate.css 지연/지속시간을 0으로 만들어 최종 상태로 즉시 도달 */
        .animate__animated {
            animation-delay: 0s !important;
            animation-duration: 0s !important;
            animation-fill-mode: both !important;
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
        {{design_system_html|safe}}
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

    # 히어로 + 이미지 (좌우 분할 — 일러스트가 배경에 녹아드는 통합형)
    "hero_image": """
<div class="w-full h-full flex slide-illustration-bleed">
    <div class="w-1/2 h-full flex flex-col justify-center p-16">
        {% if eyebrow %}<p class="text-sm font-semibold uppercase tracking-wider mb-3" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
        {% if badge %}<span class="badge badge-secondary mb-4">{{badge}}</span>{% endif %}
        <h1 class="text-5xl font-bold tracking-tight mb-6 leading-tight" style="color: hsl(var(--foreground))">
            {{title}}
        </h1>
        {% if subtitle %}
        <p class="text-xl mb-8 leading-relaxed" style="color: hsl(var(--muted-foreground))">
            {{subtitle}}
        </p>
        {% endif %}
        {% if cta_text %}
        <div>
            <span class="btn btn-default btn-lg">{{cta_text}}</span>
        </div>
        {% endif %}
    </div>
    <div class="w-1/2 h-full flex items-center justify-center p-10">
        {% if image_data %}
        <img src="{{image_data}}" class="max-w-full max-h-full object-contain slide-illustration">
        {% else %}
        <div class="w-80 h-80 flex items-center justify-center opacity-30">
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

    # 콘텐츠 + 이미지 (좌우 분할 — 일러스트가 배경에 녹아드는 통합형)
    "content_image": """
<div class="w-full h-full flex slide-illustration-bleed {% if image_position == 'left' %}flex-row-reverse{% endif %}">
    <div class="w-1/2 h-full flex flex-col justify-center p-16">
        {% if eyebrow %}<p class="text-sm font-semibold uppercase tracking-wider mb-3" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
        <h2 class="text-4xl font-bold mb-6 leading-tight" style="color: hsl(var(--foreground))">{{title}}</h2>
        <p class="text-lg leading-relaxed" style="color: hsl(var(--foreground)); opacity: 0.85">{{content}}</p>
        {% if cta_text %}
        <div class="mt-8">
            <span class="btn btn-default">{{cta_text}}</span>
        </div>
        {% endif %}
    </div>
    <div class="w-1/2 h-full flex items-center justify-center p-10">
        {% if image_data %}
        <img src="{{image_data}}" class="max-w-full max-h-full object-contain slide-illustration">
        {% else %}
        <div class="w-full h-full flex items-center justify-center opacity-20">
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

    # === 강의용 레이아웃 (lecture series) ===

    # 강의 본문 — 제목 + 본문 단락 + 선택적 불릿/인용 (가장 자주 쓰는 강의 슬라이드)
    "lecture_body": """
<div class="w-full h-full flex flex-col p-14">
    <div class="mb-6">
        {% if eyebrow %}<p class="text-sm font-semibold uppercase tracking-wider mb-2" style="color: hsl(var(--primary))">{{eyebrow}}</p>{% endif %}
        <h2 class="text-4xl font-bold tracking-tight" style="color: hsl(var(--foreground))">{{title}}</h2>
        {% if subtitle %}<p class="text-xl mt-2" style="color: hsl(var(--muted-foreground))">{{subtitle}}</p>{% endif %}
    </div>
    <div class="flex-1 flex flex-col gap-5 text-lg leading-relaxed" style="color: hsl(var(--foreground))">
        {% if body %}<p>{{body}}</p>{% endif %}
        {% if bullets %}
        <ul class="space-y-3 pl-2">
            {% for b in bullets %}
            <li class="flex gap-3">
                <span class="flex-shrink-0 mt-2 w-2 h-2 rounded-full" style="background: hsl(var(--primary))"></span>
                <span>{{b}}</span>
            </li>
            {% endfor %}
        </ul>
        {% endif %}
        {% if quote %}
        <blockquote class="border-l-4 pl-6 py-3 italic text-xl my-2" style="border-color: hsl(var(--primary)); background: hsl(var(--muted) / 0.3)">
            {{quote}}
        </blockquote>
        {% endif %}
    </div>
    {% if footer %}<p class="text-sm mt-6 pt-4 border-t" style="color: hsl(var(--muted-foreground)); border-color: hsl(var(--border))">{{footer}}</p>{% endif %}
</div>
""",

    # 메타포 스토리 — 큰 본문 스토리 + 한 줄 부연 (햄릿/깜깜한 계단 같은 핵심 메타포용)
    "metaphor_story": """
<div class="w-full h-full flex flex-col items-center justify-center p-20" style="background: linear-gradient(135deg, hsl(var(--background)), hsl(var(--muted) / 0.4))">
    {% if label %}
    <span class="badge badge-secondary mb-8 text-sm tracking-wider uppercase">{{label}}</span>
    {% endif %}
    <p class="text-3xl text-center leading-loose max-w-5xl font-medium" style="color: hsl(var(--foreground))">
        {{story}}
    </p>
    {% if takeaway %}
    <div class="mt-12 pt-8 border-t max-w-3xl" style="border-color: hsl(var(--border))">
        <p class="text-xl text-center font-semibold" style="color: hsl(var(--primary))">{{takeaway}}</p>
    </div>
    {% endif %}
</div>
""",

    # 비교 표 — 좌우 또는 다열 비교 (v0 vs v5, 마케팅 카드 vs 강의 슬라이드 같은 비교)
    "comparison_table": """
<div class="w-full h-full flex flex-col p-14">
    <div class="mb-8">
        {% if eyebrow %}<p class="text-sm font-semibold uppercase tracking-wider mb-2" style="color: hsl(var(--primary))">{{eyebrow}}</p>{% endif %}
        <h2 class="text-4xl font-bold tracking-tight" style="color: hsl(var(--foreground))">{{title}}</h2>
        {% if subtitle %}<p class="text-lg mt-2" style="color: hsl(var(--muted-foreground))">{{subtitle}}</p>{% endif %}
    </div>
    <div class="flex-1 overflow-hidden">
        <table class="w-full text-base" style="color: hsl(var(--foreground))">
            {% if headers %}
            <thead>
                <tr style="border-bottom: 2px solid hsl(var(--primary))">
                    {% for h in headers %}
                    <th class="text-left py-4 px-4 font-bold text-lg">{{h}}</th>
                    {% endfor %}
                </tr>
            </thead>
            {% endif %}
            <tbody>
                {% for row in rows %}
                <tr style="border-bottom: 1px solid hsl(var(--border))">
                    {% for cell in row %}
                    <td class="py-4 px-4 align-top leading-relaxed">{{cell|safe}}</td>
                    {% endfor %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% if footer %}<p class="text-sm mt-6" style="color: hsl(var(--muted-foreground))">{{footer}}</p>{% endif %}
</div>
""",

    # 팩트박스 — 책의 팩트박스/부연 정보 (역사, 정의, 수치 등 보조 자료)
    "factbox": """
<div class="w-full h-full flex items-center justify-center p-14">
    <div class="max-w-4xl w-full rounded-xl p-12 shadow-lg" style="background: hsl(var(--muted) / 0.4); border: 2px solid hsl(var(--border))">
        <div class="flex items-center gap-3 mb-6">
            <i data-lucide="info" class="w-6 h-6" style="color: hsl(var(--primary))"></i>
            <span class="text-sm font-bold uppercase tracking-wider" style="color: hsl(var(--primary))">{{label|default('팩트박스')}}</span>
        </div>
        <h3 class="text-3xl font-bold mb-6 tracking-tight" style="color: hsl(var(--foreground))">{{title}}</h3>
        <div class="text-lg leading-relaxed space-y-4" style="color: hsl(var(--foreground))">
            {% if body %}<p>{{body}}</p>{% endif %}
            {% if items %}
            <ul class="space-y-2 pl-2">
                {% for it in items %}
                <li class="flex gap-3">
                    <span class="flex-shrink-0 mt-3 w-1.5 h-1.5 rounded-full" style="background: hsl(var(--primary))"></span>
                    <span>{{it}}</span>
                </li>
                {% endfor %}
            </ul>
            {% endif %}
        </div>
        {% if source %}<p class="text-xs mt-6 italic" style="color: hsl(var(--muted-foreground))">출처: {{source}}</p>{% endif %}
    </div>
</div>
""",

    # 인용 풀스크린 — 강력한 핵심 인용 한 줄 (testimonial과 다름: 카드형이 아닌 임팩트 풀스크린)
    "quote": """
<div class="w-full h-full flex flex-col items-center justify-center p-20" style="background: hsl(var(--background))">
    <i data-lucide="quote" class="w-20 h-20 mb-10" style="color: hsl(var(--primary)); opacity: 0.15"></i>
    <p class="text-4xl text-center font-medium leading-relaxed max-w-5xl" style="color: hsl(var(--foreground))">
        "{{quote}}"
    </p>
    {% if attribution %}
    <p class="text-xl mt-10" style="color: hsl(var(--muted-foreground))">— {{attribution}}</p>
    {% endif %}
    {% if context %}
    <p class="text-base mt-4 max-w-3xl text-center italic" style="color: hsl(var(--muted-foreground))">{{context}}</p>
    {% endif %}
</div>
""",

    # === NotebookLM 스타일 통합형 레이아웃 ===
    # 이미지와 텍스트가 한 화면 안에서 융합 — 일러스트는 슬라이드 배경과 자연스럽게 흐른다.
    # 키 포인트: 이미지 영역에 별도 배경/박스 없음, slide-illustration 클래스로 design_system이 후킹.

    # hero_illustration — 중앙 영웅 일러스트 + 상하 텍스트 (NotebookLM 표지/장 표지 스타일)
    # 사용처: 책 표지, 장 도입, 핵심 개념 단일 시각화
    "hero_illustration": """
<div class="w-full h-full flex flex-col items-center justify-center px-16 py-10 slide-illustration-bleed">
    {% if eyebrow %}<p class="text-xs font-semibold uppercase tracking-[0.3em] mb-3 opacity-80" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
    <div class="flex-1 flex items-center justify-center w-full max-w-5xl my-3 min-h-0">
        {% if image_data %}
        <img src="{{image_data}}" class="max-w-full max-h-full object-contain slide-illustration">
        {% else %}
        <div class="w-96 h-96 flex items-center justify-center opacity-20">
            <i data-lucide="image" class="w-24 h-24" style="color: hsl(var(--muted-foreground))"></i>
        </div>
        {% endif %}
    </div>
    <h1 class="text-6xl font-black text-center tracking-tight mb-3 leading-[1.15]" style="color: hsl(var(--foreground))">
        {{title}}
    </h1>
    {% if subtitle %}
    <p class="text-xl text-center max-w-4xl leading-relaxed" style="color: hsl(var(--muted-foreground))">
        {{subtitle}}
    </p>
    {% endif %}
    {% if footer %}<p class="text-sm mt-6" style="color: hsl(var(--muted-foreground))">{{footer}}</p>{% endif %}
</div>
""",

    # illustration_anchor — 상단 큰 일러스트 + 하단 텍스트 (가장 활용도 높은 강의 슬라이드)
    # 사용처: 개념 설명, 다이어그램 + 캡션, 일러스트로 보여주고 글로 마무리
    "illustration_anchor": """
<div class="w-full h-full flex flex-col p-14 slide-illustration-bleed">
    <div class="flex-1 flex items-center justify-center min-h-0 mb-8">
        {% if image_data %}
        <img src="{{image_data}}" class="max-w-full max-h-full object-contain slide-illustration">
        {% else %}
        <div class="w-full h-full flex items-center justify-center opacity-20">
            <i data-lucide="image" class="w-24 h-24" style="color: hsl(var(--muted-foreground))"></i>
        </div>
        {% endif %}
    </div>
    <div class="flex-shrink-0">
        {% if eyebrow %}<p class="text-sm font-semibold uppercase tracking-wider mb-2" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
        <h2 class="text-4xl font-bold tracking-tight mb-3 leading-tight" style="color: hsl(var(--foreground))">{{title}}</h2>
        {% if body %}
        <p class="text-lg leading-relaxed" style="color: hsl(var(--foreground)); opacity: 0.85">{{body}}</p>
        {% endif %}
        {% if takeaway %}
        <p class="text-lg font-semibold mt-4 pl-4 border-l-4" style="color: hsl(var(--accent)); border-color: hsl(var(--accent))">{{takeaway}}</p>
        {% endif %}
    </div>
</div>
""",

    # split_concept — 좌우 개념 대비 (양쪽 모두 일러스트+캡션, 가운데 결론 박스)
    # 사용처: A vs B, 문제 vs 해결, 전/후, 뇌 vs 몸 같은 대조
    "split_concept": """
<div class="w-full h-full flex flex-col slide-illustration-bleed">
    {% if title %}
    <div class="px-14 pt-10 pb-4 flex-shrink-0">
        <h2 class="text-4xl font-bold text-center tracking-tight leading-tight" style="color: hsl(var(--foreground))">{{title}}</h2>
        {% if subtitle %}<p class="text-lg text-center mt-2" style="color: hsl(var(--muted-foreground))">{{subtitle}}</p>{% endif %}
    </div>
    {% endif %}
    <div class="flex-1 flex min-h-0 relative">
        <div class="w-1/2 h-full flex flex-col items-center px-8 py-6" style="background: linear-gradient(180deg, transparent, hsl(var(--secondary) / 0.3))">
            <div class="flex items-center justify-center w-full" style="flex: 1 1 60%; min-height: 0;">
                {% if left_image_data %}
                <img src="{{left_image_data}}" class="max-w-full max-h-full object-contain slide-illustration">
                {% endif %}
            </div>
            <div class="flex-shrink-0 w-full text-center mt-2" style="flex: 0 0 auto;">
                <h3 class="text-2xl font-bold mb-2" style="color: hsl(var(--foreground))">{{left_title}}</h3>
                {% if left_body %}
                <p class="text-base leading-relaxed" style="color: hsl(var(--foreground)); opacity: 0.8">{{left_body}}</p>
                {% endif %}
            </div>
        </div>
        <div class="w-1/2 h-full flex flex-col items-center px-8 py-6" style="background: linear-gradient(180deg, transparent, hsl(var(--accent) / 0.12))">
            <div class="flex items-center justify-center w-full" style="flex: 1 1 60%; min-height: 0;">
                {% if right_image_data %}
                <img src="{{right_image_data}}" class="max-w-full max-h-full object-contain slide-illustration">
                {% endif %}
            </div>
            <div class="flex-shrink-0 w-full text-center mt-2" style="flex: 0 0 auto;">
                <h3 class="text-2xl font-bold mb-2" style="color: hsl(var(--accent))">{{right_title}}</h3>
                {% if right_body %}
                <p class="text-base leading-relaxed" style="color: hsl(var(--foreground)); opacity: 0.8">{{right_body}}</p>
                {% endif %}
            </div>
        </div>
        {% if conclusion %}
        <div class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 max-w-md px-7 py-4 rounded-lg shadow-xl text-center" style="background: hsl(var(--background)); border: 1.5px solid hsl(var(--accent)); z-index: 5;">
            <p class="text-base font-medium leading-relaxed" style="color: hsl(var(--foreground))">{{conclusion}}</p>
        </div>
        {% endif %}
    </div>
</div>
""",

    # comparison_iconic — 시각적 헤더가 있는 비교 표 (NotebookLM 5페이지 스타일)
    # 사용처: A vs B (말하는 챗봇 vs 일하는 에이전트, 도구 없는 AI vs 도구 가진 AI)
    # comparison_table과 다른 점: 헤더 행에 이모지/일러스트 + 큰 컬럼 제목 + 부드러운 배경
    #
    # 데이터 구조:
    #   title, subtitle (선택), eyebrow (선택)
    #   label_header: 좌측 라벨 컬럼 헤더 (예: "구분")
    #   columns: [{title: "도구가 없는 AI", subtitle: "(Chatbot)", icon: "💬"}, {title: "도구를 가진 AI", subtitle: "(Agent + Harness)", icon: "⚙️", highlighted: true}]
    #   rows: [{label: "역할", cells: ["통역사 및 조언자", "실제 문제를 해결하는 작업자"]}, ...]
    #         (주의: values가 아닌 cells — Jinja에서 .values는 dict 메서드와 충돌)
    #   footer (선택)
    "comparison_iconic": """
<div class="w-full h-full flex flex-col p-12 slide-illustration-bleed">
    <div class="mb-6 text-center flex-shrink-0">
        {% if eyebrow %}<p class="text-xs font-semibold uppercase tracking-[0.25em] mb-2 opacity-80" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
        <h2 class="text-4xl font-bold tracking-tight leading-tight" style="color: hsl(var(--foreground))">{{title}}</h2>
        {% if subtitle %}<p class="text-base mt-2" style="color: hsl(var(--muted-foreground))">{{subtitle}}</p>{% endif %}
    </div>
    <div class="flex-1 flex items-center justify-center min-h-0">
        <table class="w-full max-w-6xl border-separate" style="border-spacing: 0; color: hsl(var(--foreground))">
            <thead>
                <tr>
                    <th class="w-[14%] py-5 px-4 text-base font-bold text-center" style="background: hsl(var(--secondary)); border: 1px solid hsl(var(--border)); border-right: none;">
                        {{label_header|default('구분')}}
                    </th>
                    {% for col in columns %}
                    <th class="py-5 px-6 text-center" style="
                        background: {% if col.highlighted %}hsl(var(--accent) / 0.15){% else %}hsl(var(--secondary)){% endif %};
                        border: 1px solid hsl(var(--border));
                        {% if not loop.last %}border-right: none;{% endif %}
                    ">
                        {% if col.icon %}<div class="text-3xl mb-2 leading-none">{{col.icon}}</div>{% endif %}
                        <div class="text-xl font-bold leading-tight" style="color: hsl(var(--foreground))">{{col.title}}</div>
                        {% if col.subtitle %}<div class="text-sm mt-1" style="color: hsl(var(--muted-foreground))">{{col.subtitle}}</div>{% endif %}
                    </th>
                    {% endfor %}
                </tr>
            </thead>
            <tbody>
                {% for row in rows %}
                <tr>
                    <td class="py-5 px-4 text-center font-bold text-base" style="
                        background: hsl(var(--secondary) / 0.5);
                        border: 1px solid hsl(var(--border));
                        border-top: none;
                        border-right: none;
                        color: hsl(var(--foreground));
                    ">
                        {{row.label}}
                    </td>
                    {% for val in row.cells %}
                    <td class="py-5 px-6 text-center text-base leading-relaxed" style="
                        background: {% if columns[loop.index0].highlighted %}hsl(var(--accent) / 0.05){% else %}transparent{% endif %};
                        border: 1px solid hsl(var(--border));
                        border-top: none;
                        {% if not loop.last %}border-right: none;{% endif %}
                        color: hsl(var(--foreground));
                    ">
                        {{val|safe}}
                    </td>
                    {% endfor %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% if footer %}<p class="text-sm mt-4 text-center flex-shrink-0" style="color: hsl(var(--muted-foreground))">{{footer}}</p>{% endif %}
</div>
""",

    # illustration_background — 전면 일러스트 배경 + 오버레이 텍스트
    # 사용처: 강한 인상의 부 도입, 영화 같은 한 장면, 분위기 슬라이드
    # 옵션: text_align="center" (NotebookLM 부 표지 양식) / "left" (영화 자막 양식, 기본)
    "illustration_background": """
<div class="w-full h-full relative slide-illustration-bleed">
    {% if image_data %}
    <img src="{{image_data}}" class="absolute inset-0 w-full h-full object-cover slide-illustration-bg">
    {% endif %}
    {% set _align = text_align|default('left') %}
    {% if _align == 'center' %}
    <!-- center 모드: 일러스트 위에 텍스트가 직접 겹치므로 강한 라디얼 스크림 -->
    <div class="absolute inset-0" style="background: radial-gradient(ellipse 70% 50% at center, hsl(var(--background) / 0.78) 0%, hsl(var(--background) / 0.45) 65%, hsl(var(--background) / 0.65) 100%)"></div>
    <div class="relative w-full h-full flex flex-col items-center justify-center p-16 text-center">
        {% if eyebrow %}<p class="text-base font-semibold tracking-[0.3em] mb-6 opacity-80" style="color: hsl(var(--muted-foreground))">{{eyebrow}}</p>{% endif %}
        <h1 class="text-7xl font-black tracking-tight mb-5 leading-[1.1]" style="color: hsl(var(--foreground))">{{title}}</h1>
        {% if subtitle %}
        <p class="text-xl max-w-4xl leading-relaxed" style="color: hsl(var(--foreground)); opacity: 0.9">{{subtitle}}</p>
        {% endif %}
    </div>
    {% else %}
    <div class="absolute inset-0" style="background: linear-gradient(180deg, hsl(var(--background) / 0.1) 0%, hsl(var(--background) / 0.4) 50%, hsl(var(--background) / 0.85) 100%)"></div>
    <div class="relative w-full h-full flex flex-col justify-end p-16">
        {% if eyebrow %}<p class="text-sm font-semibold uppercase tracking-[0.3em] mb-4" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
        <h1 class="text-6xl font-black tracking-tight mb-4 leading-tight" style="color: hsl(var(--foreground))">{{title}}</h1>
        {% if subtitle %}
        <p class="text-xl max-w-3xl leading-relaxed" style="color: hsl(var(--foreground)); opacity: 0.85">{{subtitle}}</p>
        {% endif %}
    </div>
    {% endif %}
</div>
""",

    # illustration_overlay — NotebookLM 양식: 풀-블리드 일러스트 + 자유 좌표 라벨 박스 N개
    # 사용처: 다이어그램형 슬라이드, 한 일러스트 안의 여러 구성요소를 한국어로 라벨링
    # 필수 키:
    #   - image_path / image_data : 풀-블리드 배경 이미지 (가급적 영문 라벨만 박힌 다이어그램)
    #   - labels : [{text, position}] 리스트
    #              position: "top-left" | "top-center" | "top-right" | "middle-left" |
    #                       "middle-center" | "middle-right" | "bottom-left" | "bottom-center" |
    #                       "bottom-right" 또는 {top: "20%", left: "10%", width: "30%"} 같은 절대 좌표
    #              variant(선택): "label"(작은 캡션, 기본) | "title"(큰 제목) | "panel"(다중행 본문)
    #              subtext(선택): variant=panel일 때 본문 줄들
    # 선택 키:
    #   - title : 상단 헤더 (선택). 없으면 라벨만 그려짐 — NotebookLM 다이어그램 슬라이드처럼.
    #   - eyebrow : 헤더 위 작은 라벨
    #   - footer_quote : 하단 결론 박스 (NotebookLM 5/8/10페이지 양식)
    "illustration_overlay": """
<div class="w-full h-full relative slide-illustration-bleed" style="background: hsl(var(--background));">
    {% if image_data %}
    <img src="{{image_data}}" class="absolute inset-0 w-full h-full object-cover slide-illustration-bg">
    {% endif %}

    {% if title or eyebrow %}
    <div class="absolute top-0 left-0 right-0 px-16 pt-12 pb-4 z-10" style="background: linear-gradient(180deg, hsl(var(--background) / 0.85) 0%, hsl(var(--background) / 0.5) 70%, transparent 100%);">
        {% if eyebrow %}<p class="text-xs font-semibold uppercase tracking-[0.25em] mb-2" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
        {% if title %}<h1 class="text-4xl font-black tracking-tight text-center" style="color: hsl(var(--foreground))">{{title}}</h1>{% endif %}
    </div>
    {% endif %}

    {% set _pos_map = {
        'top-left':       {'top': '14%', 'left': '4%',    'width': '26%', 'text-align': 'left'},
        'top-center':     {'top': '14%', 'left': '32%',   'width': '36%', 'text-align': 'center'},
        'top-right':      {'top': '14%', 'right': '4%',   'width': '26%', 'text-align': 'right'},
        'middle-left':    {'top': '42%', 'left': '4%',    'width': '26%', 'text-align': 'left'},
        'middle-center':  {'top': '42%', 'left': '32%',   'width': '36%', 'text-align': 'center'},
        'middle-right':   {'top': '42%', 'right': '4%',   'width': '26%', 'text-align': 'right'},
        'bottom-left':    {'bottom': '14%', 'left': '4%', 'width': '34%', 'text-align': 'left'},
        'bottom-center':  {'bottom': '14%', 'left': '20%','width': '60%', 'text-align': 'center'},
        'bottom-right':   {'bottom': '14%', 'right': '4%','width': '34%', 'text-align': 'right'}
    } %}

    {% for lbl in labels or [] %}
        {% set _v = lbl.variant or 'label' %}
        {% set _p = lbl.position %}
        {% if _p is string %}
            {% set _coord = _pos_map[_p] %}
        {% else %}
            {% set _coord = _p %}
        {% endif %}
        <div class="absolute z-20 hud-panel"
             style="
                {% if _coord.top %}top: {{_coord.top}};{% endif %}
                {% if _coord.bottom %}bottom: {{_coord.bottom}};{% endif %}
                {% if _coord.left %}left: {{_coord.left}};{% endif %}
                {% if _coord.right %}right: {{_coord.right}};{% endif %}
                {% if _coord.width %}width: {{_coord.width}};{% endif %}
                text-align: {{_coord['text-align'] or 'left'}};
                padding: {% if _v == 'title' %}14px 20px{% elif _v == 'panel' %}16px 22px{% else %}10px 16px{% endif %};
                background: hsl(var(--secondary) / 0.86);
                backdrop-filter: blur(6px);
             ">
            {% if _v == 'title' %}
                <p class="font-black tracking-tight" style="font-size: 1.6rem; color: hsl(var(--foreground)); line-height: 1.2">{{lbl.text}}</p>
                {% if lbl.subtext %}<p class="text-sm mt-1 opacity-80" style="color: hsl(var(--muted-foreground))">{{lbl.subtext}}</p>{% endif %}
            {% elif _v == 'panel' %}
                <p class="font-bold mb-2" style="font-size: 1.05rem; color: hsl(var(--accent))">{{lbl.text}}</p>
                {% if lbl.subtext %}
                    {% if lbl.subtext is string %}
                        <p class="text-sm leading-relaxed" style="color: hsl(var(--foreground))">{{lbl.subtext}}</p>
                    {% else %}
                        {% for line in lbl.subtext %}
                        <p class="text-sm leading-relaxed mb-1" style="color: hsl(var(--foreground))">{{line}}</p>
                        {% endfor %}
                    {% endif %}
                {% endif %}
            {% else %}
                <p class="font-semibold" style="font-size: 0.95rem; color: hsl(var(--foreground)); line-height: 1.4">{{lbl.text}}</p>
                {% if lbl.subtext %}<p class="text-xs mt-1 opacity-75" style="color: hsl(var(--muted-foreground))">{{lbl.subtext}}</p>{% endif %}
            {% endif %}
        </div>
    {% endfor %}

    {% if footer_quote %}
    <div class="absolute left-12 right-12 z-20 hud-panel" style="bottom: 36px; padding: 16px 24px; background: hsl(var(--secondary) / 0.92); backdrop-filter: blur(8px); text-align: center;">
        <p class="font-bold" style="font-size: 1.1rem; color: hsl(var(--foreground)); line-height: 1.5">{{footer_quote}}</p>
    </div>
    {% endif %}
</div>
""",

    # 커스텀 (Tailwind 자유 작성)
    "custom": """
{{custom_html|safe}}
"""
}

