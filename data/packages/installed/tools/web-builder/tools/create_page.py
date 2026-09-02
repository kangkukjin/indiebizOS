"""
create_page.py
섹션을 조합하여 페이지를 생성합니다.
"""

import json
import os
from pathlib import Path
from typing import Any

TOOL_NAME = "create_page"
TOOL_DESCRIPTION = "섹션을 조합하여 페이지를 생성합니다"
TOOL_PARAMETERS = {
    "project_path": {
        "type": "string",
        "description": "프로젝트 경로",
        "required": True
    },
    "page_name": {
        "type": "string",
        "description": "페이지 이름 (예: index, about, contact)",
        "required": True
    },
    "sections": {
        "type": "array",
        "description": "섹션 구성",
        "required": True,
        "items": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "섹션 타입 (예: hero-simple, features-grid)"},
                "props": {"type": "object", "description": "섹션 속성"}
            }
        }
    },
    "metadata": {
        "type": "object",
        "description": "페이지 메타데이터 (title, description)",
        "required": False
    }
}

# 패키지 경로
PACKAGE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = PACKAGE_DIR / "templates" / "sections"


# ============================================
# 섹션 컴포넌트 코드 생성
# ============================================

def generate_hero_simple(props: dict) -> tuple[str, str]:
    """심플 히어로 섹션 생성"""
    component_name = "HeroSimple"
    code = f'''import {{ Button }} from "@/components/ui/button"

export function {component_name}() {{
  return (
    <section className="py-20 px-4 md:py-32">
      <div className="container mx-auto max-w-4xl text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl">
          {props.get('title', '환영합니다')}
        </h1>
        {props.get('subtitle') and f"""
        <p className="mt-6 text-lg text-muted-foreground md:text-xl">
          {props.get('subtitle', '')}
        </p>
        """}
        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
          <Button size="lg" asChild>
            <a href="{props.get('cta_link', '#')}">{props.get('cta_text', '시작하기')}</a>
          </Button>
          {props.get('secondary_cta_text') and f"""
          <Button variant="outline" size="lg" asChild>
            <a href="{props.get('secondary_cta_link', '#')}">{props.get('secondary_cta_text', '')}</a>
          </Button>
          """}
        </div>
      </div>
    </section>
  )
}}
'''

    # 실제 렌더링 코드 (조건부 렌더링 적용)
    subtitle_jsx = ""
    if props.get('subtitle'):
        subtitle_jsx = f'''
        <p className="mt-6 text-lg text-muted-foreground md:text-xl">
          {props['subtitle']}
        </p>'''

    secondary_btn_jsx = ""
    if props.get('secondary_cta_text'):
        secondary_btn_jsx = f'''
          <Button variant="outline" size="lg" asChild>
            <a href="{props.get('secondary_cta_link', '#')}">{props['secondary_cta_text']}</a>
          </Button>'''

    code = f'''import {{ Button }} from "@/components/ui/button"

export function {component_name}() {{
  return (
    <section className="py-20 px-4 md:py-32">
      <div className="container mx-auto max-w-4xl text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl">
          {props.get('title', '환영합니다')}
        </h1>{subtitle_jsx}
        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
          <Button size="lg" asChild>
            <a href="{props.get('cta_link', '#')}">{props.get('cta_text', '시작하기')}</a>
          </Button>{secondary_btn_jsx}
        </div>
      </div>
    </section>
  )
}}
'''
    return component_name, code


def generate_hero_centered(props: dict) -> tuple[str, str]:
    """중앙 정렬 히어로 섹션 생성"""
    component_name = "HeroCentered"

    badge_jsx = ""
    if props.get('badge_text'):
        badge_jsx = f'''
        <Badge variant="secondary" className="mb-4">
          {props['badge_text']}
        </Badge>'''

    subtitle_jsx = ""
    if props.get('subtitle'):
        subtitle_jsx = f'''
        <p className="mt-6 text-lg text-muted-foreground md:text-xl max-w-2xl mx-auto">
          {props['subtitle']}
        </p>'''

    code = f'''import {{ Button }} from "@/components/ui/button"
import {{ Badge }} from "@/components/ui/badge"

export function {component_name}() {{
  return (
    <section className="py-20 px-4 md:py-32 bg-gradient-to-b from-background to-muted/20">
      <div className="container mx-auto max-w-4xl text-center">{badge_jsx}
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl">
          {props.get('title', '환영합니다')}
        </h1>{subtitle_jsx}
        <div className="mt-10">
          <Button size="lg" asChild>
            <a href="{props.get('cta_link', '#')}">{props.get('cta_text', '시작하기')}</a>
          </Button>
        </div>
      </div>
    </section>
  )
}}
'''
    return component_name, code


def generate_features_grid(props: dict) -> tuple[str, str]:
    """기능 그리드 섹션 생성"""
    component_name = "FeaturesGrid"

    features = props.get('features', [])
    columns = props.get('columns', 3)

    grid_cols = {
        2: "md:grid-cols-2",
        3: "md:grid-cols-3",
        4: "md:grid-cols-2 lg:grid-cols-4"
    }

    features_jsx = ""
    for f in features:
        icon = f.get('icon', '⭐')
        title = f.get('title', '')
        desc = f.get('description', '')
        features_jsx += f'''
          <Card className="border-0 shadow-sm">
            <CardHeader>
              <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4 text-2xl">
                {icon}
              </div>
              <CardTitle className="text-xl">{title}</CardTitle>
            </CardHeader>
            <CardContent>
              <CardDescription className="text-base">{desc}</CardDescription>
            </CardContent>
          </Card>'''

    header_jsx = ""
    if props.get('title') or props.get('subtitle'):
        title_jsx = f'<h2 className="text-3xl font-bold tracking-tight sm:text-4xl">{props.get("title", "")}</h2>' if props.get('title') else ""
        subtitle_jsx = f'<p className="mt-4 text-lg text-muted-foreground max-w-2xl mx-auto">{props.get("subtitle", "")}</p>' if props.get('subtitle') else ""
        header_jsx = f'''
        <div className="text-center mb-12">
          {title_jsx}
          {subtitle_jsx}
        </div>'''

    code = f'''import {{ Card, CardContent, CardDescription, CardHeader, CardTitle }} from "@/components/ui/card"

export function {component_name}() {{
  return (
    <section className="py-16 px-4 md:py-24">
      <div className="container mx-auto">{header_jsx}
        <div className="grid gap-6 {grid_cols.get(columns, 'md:grid-cols-3')}">{features_jsx}
        </div>
      </div>
    </section>
  )
}}
'''
    return component_name, code


def generate_features_cards(props: dict) -> tuple[str, str]:
    """기능 카드 섹션 생성"""
    component_name = "FeaturesCards"
    features = props.get('features', [])

    features_jsx = ""
    for f in features:
        icon = f.get('icon', '📦')
        title = f.get('title', '')
        desc = f.get('description', '')
        link = f.get('link')

        link_jsx = ""
        if link:
            link_jsx = f'''
                <Button variant="ghost" className="p-0 h-auto" asChild>
                  <a href="{link}" className="flex items-center gap-2 text-primary">
                    자세히 보기
                    <ArrowRight className="w-4 h-4" />
                  </a>
                </Button>'''

        features_jsx += f'''
          <Card className="group hover:shadow-lg transition-shadow">
            <CardHeader>
              <div className="text-4xl mb-4">{icon}</div>
              <CardTitle className="text-xl">{title}</CardTitle>
            </CardHeader>
            <CardContent>
              <CardDescription className="text-base mb-4">{desc}</CardDescription>{link_jsx}
            </CardContent>
          </Card>'''

    title_jsx = ""
    if props.get('title'):
        title_jsx = f'''
        <h2 className="text-3xl font-bold tracking-tight text-center mb-12 sm:text-4xl">
          {props['title']}
        </h2>'''

    code = f'''import {{ Card, CardContent, CardDescription, CardHeader, CardTitle }} from "@/components/ui/card"
import {{ Button }} from "@/components/ui/button"
import {{ ArrowRight }} from "lucide-react"

export function {component_name}() {{
  return (
    <section className="py-16 px-4 md:py-24 bg-muted/30">
      <div className="container mx-auto">{title_jsx}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">{features_jsx}
        </div>
      </div>
    </section>
  )
}}
'''
    return component_name, code


def generate_testimonials(props: dict) -> tuple[str, str]:
    """고객 후기 섹션 생성"""
    component_name = "Testimonials"
    testimonials = props.get('testimonials', [])
    title = props.get('title', '고객 후기')

    items_jsx = ""
    for t in testimonials:
        quote = t.get('quote', '')
        author = t.get('author', '')
        role = t.get('role', '')
        avatar = t.get('avatar_url', '')
        initials = author[:2].upper() if author else 'AN'

        avatar_img = f'<AvatarImage src="{avatar}" alt="{author}" />' if avatar else ""

        items_jsx += f'''
            <Card className="bg-background">
              <CardContent className="pt-6">
                <Quote className="w-8 h-8 text-primary/20 mb-4" />
                <p className="text-muted-foreground mb-6 italic">"{quote}"</p>
                <div className="flex items-center gap-3">
                  <Avatar>
                    {avatar_img}
                    <AvatarFallback>{initials}</AvatarFallback>
                  </Avatar>
                  <div>
                    <p className="font-semibold">{author}</p>
                    <p className="text-sm text-muted-foreground">{role}</p>
                  </div>
                </div>
              </CardContent>
            </Card>'''

    code = f'''import {{ Card, CardContent }} from "@/components/ui/card"
import {{ Avatar, AvatarFallback, AvatarImage }} from "@/components/ui/avatar"
import {{ Quote }} from "lucide-react"

export function {component_name}() {{
  return (
    <section className="py-16 px-4 md:py-24 bg-muted/30">
      <div className="container mx-auto">
        <h2 className="text-3xl font-bold tracking-tight text-center mb-12 sm:text-4xl">
          {title}
        </h2>
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">{items_jsx}
        </div>
      </div>
    </section>
  )
}}
'''
    return component_name, code


def generate_stats(props: dict) -> tuple[str, str]:
    """통계 섹션 생성"""
    component_name = "Stats"
    stats = props.get('stats', [])

    stats_jsx = ""
    for s in stats:
        value = s.get('value', '0')
        label = s.get('label', '')
        stats_jsx += f'''
            <div className="text-center">
              <p className="text-4xl font-bold md:text-5xl">{value}</p>
              <p className="mt-2 text-primary-foreground/80">{label}</p>
            </div>'''

    title_jsx = ""
    if props.get('title'):
        title_jsx = f'''
        <h2 className="text-3xl font-bold tracking-tight text-center mb-12 sm:text-4xl">
          {props['title']}
        </h2>'''

    code = f'''export function {component_name}() {{
  return (
    <section className="py-16 px-4 md:py-24 bg-primary text-primary-foreground">
      <div className="container mx-auto">{title_jsx}
        <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-4">{stats_jsx}
        </div>
      </div>
    </section>
  )
}}
'''
    return component_name, code


def generate_pricing_cards(props: dict) -> tuple[str, str]:
    """가격표 카드 섹션 생성"""
    component_name = "PricingCards"
    plans = props.get('plans', [])
    title = props.get('title', '가격 안내')
    subtitle = props.get('subtitle', '')

    plans_jsx = ""
    for p in plans:
        name = p.get('name', '')
        price = p.get('price', '0')
        period = p.get('period', '/월')
        desc = p.get('description', '')
        features = p.get('features', [])
        cta_text = p.get('cta_text', '선택하기')
        highlighted = p.get('highlighted', False)

        features_jsx = ""
        for f in features:
            features_jsx += f'''
                    <li className="flex items-center gap-2">
                      <Check className="w-5 h-5 text-primary flex-shrink-0" />
                      <span className="text-sm">{f}</span>
                    </li>'''

        highlight_class = "border-primary shadow-lg scale-105" if highlighted else "border-border"
        badge_jsx = '<Badge className="absolute -top-3 left-1/2 -translate-x-1/2">추천</Badge>' if highlighted else ""
        btn_variant = "default" if highlighted else "outline"

        plans_jsx += f'''
            <Card className="relative {highlight_class}">
              {badge_jsx}
              <CardHeader>
                <CardTitle className="text-xl">{name}</CardTitle>
                <CardDescription>{desc}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="mb-6">
                  <span className="text-4xl font-bold">{price}</span>
                  <span className="text-muted-foreground">{period}</span>
                </div>
                <ul className="space-y-3">{features_jsx}
                </ul>
              </CardContent>
              <CardFooter>
                <Button className="w-full" variant="{btn_variant}">
                  {cta_text}
                </Button>
              </CardFooter>
            </Card>'''

    subtitle_jsx = ""
    if subtitle:
        subtitle_jsx = f'''
            <p className="mt-4 text-lg text-muted-foreground max-w-2xl mx-auto">
              {subtitle}
            </p>'''

    code = f'''import {{ Button }} from "@/components/ui/button"
import {{ Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle }} from "@/components/ui/card"
import {{ Badge }} from "@/components/ui/badge"
import {{ Check }} from "lucide-react"

export function {component_name}() {{
  return (
    <section className="py-16 px-4 md:py-24">
      <div className="container mx-auto">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">{title}</h2>{subtitle_jsx}
        </div>
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 max-w-5xl mx-auto">{plans_jsx}
        </div>
      </div>
    </section>
  )
}}
'''
    return component_name, code


def generate_cta_banner(props: dict) -> tuple[str, str]:
    """CTA 배너 섹션 생성"""
    component_name = "CtaBanner"
    title = props.get('title', '')
    subtitle = props.get('subtitle', '')
    cta_text = props.get('cta_text', '시작하기')
    cta_link = props.get('cta_link', '#')
    background = props.get('background', 'primary')

    bg_classes = {
        "primary": "bg-primary text-primary-foreground",
        "secondary": "bg-secondary text-secondary-foreground",
        "gradient": "bg-gradient-to-r from-primary to-primary/80 text-primary-foreground"
    }

    btn_variant = "default" if background == "secondary" else "secondary"

    subtitle_jsx = ""
    if subtitle:
        subtitle_jsx = f'''
          <p className="mt-4 text-lg opacity-90 max-w-2xl mx-auto">
            {subtitle}
          </p>'''

    code = f'''import {{ Button }} from "@/components/ui/button"

export function {component_name}() {{
  return (
    <section className="py-16 px-4 md:py-20 {bg_classes.get(background, bg_classes['primary'])}">
      <div className="container mx-auto text-center">
        <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
          {title}
        </h2>{subtitle_jsx}
        <div className="mt-8">
          <Button size="lg" variant="{btn_variant}" asChild>
            <a href="{cta_link}">{cta_text}</a>
          </Button>
        </div>
      </div>
    </section>
  )
}}
'''
    return component_name, code


def generate_contact_form(props: dict) -> tuple[str, str]:
    """문의 폼 섹션 생성"""
    component_name = "ContactForm"
    title = props.get('title', '문의하기')
    subtitle = props.get('subtitle', '')
    fields = props.get('fields', ['name', 'email', 'message'])
    submit_text = props.get('submit_text', '보내기')

    field_config = {
        'name': ('이름', 'text', '홍길동'),
        'email': ('이메일', 'email', 'example@email.com'),
        'phone': ('전화번호', 'tel', '010-0000-0000'),
        'company': ('회사명', 'text', '회사명을 입력하세요'),
        'subject': ('제목', 'text', '문의 제목을 입력하세요'),
        'message': ('메시지', 'textarea', '문의 내용을 입력하세요'),
    }

    fields_jsx = ""
    for field in fields:
        if field in field_config:
            label, field_type, placeholder = field_config[field]
            if field_type == 'textarea':
                fields_jsx += f'''
                <div className="space-y-2">
                  <Label htmlFor="{field}">{label}</Label>
                  <Textarea id="{field}" placeholder="{placeholder}" rows={{4}} required />
                </div>'''
            else:
                fields_jsx += f'''
                <div className="space-y-2">
                  <Label htmlFor="{field}">{label}</Label>
                  <Input id="{field}" type="{field_type}" placeholder="{placeholder}" required />
                </div>'''

    subtitle_jsx = ""
    if subtitle:
        subtitle_jsx = f'<CardDescription>{subtitle}</CardDescription>'

    code = f'''"use client"

import {{ Button }} from "@/components/ui/button"
import {{ Input }} from "@/components/ui/input"
import {{ Textarea }} from "@/components/ui/textarea"
import {{ Label }} from "@/components/ui/label"
import {{ Card, CardContent, CardDescription, CardHeader, CardTitle }} from "@/components/ui/card"

export function {component_name}() {{
  return (
    <section className="py-16 px-4 md:py-24">
      <Card className="max-w-lg mx-auto">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">{title}</CardTitle>
          {subtitle_jsx}
        </CardHeader>
        <CardContent>
          <form className="space-y-4">{fields_jsx}
            <Button type="submit" className="w-full">
              {submit_text}
            </Button>
          </form>
        </CardContent>
      </Card>
    </section>
  )
}}
'''
    return component_name, code


def generate_newsletter(props: dict) -> tuple[str, str]:
    """뉴스레터 섹션 생성"""
    component_name = "Newsletter"
    title = props.get('title', '뉴스레터 구독')
    subtitle = props.get('subtitle', '')
    placeholder = props.get('placeholder', '이메일을 입력하세요')
    submit_text = props.get('submit_text', '구독하기')

    subtitle_jsx = ""
    if subtitle:
        subtitle_jsx = f'''
          <p className="text-muted-foreground mb-6">{subtitle}</p>'''

    code = f'''"use client"

import {{ Button }} from "@/components/ui/button"
import {{ Input }} from "@/components/ui/input"

export function {component_name}() {{
  return (
    <section className="py-16 px-4 md:py-20 bg-muted/50">
      <div className="container mx-auto max-w-xl text-center">
        <h2 className="text-2xl font-bold mb-2 sm:text-3xl">{title}</h2>{subtitle_jsx}
        <form className="flex gap-2 max-w-md mx-auto">
          <Input type="email" placeholder="{placeholder}" required className="flex-1" />
          <Button type="submit">{submit_text}</Button>
        </form>
      </div>
    </section>
  )
}}
'''
    return component_name, code


def generate_header(props: dict) -> tuple[str, str]:
    """헤더 섹션 생성"""
    component_name = "Header"
    logo_text = props.get('logo_text', 'Logo')
    nav_items = props.get('nav_items', [])
    cta_text = props.get('cta_text', '')
    cta_link = props.get('cta_link', '#')

    nav_items_jsx = ""
    mobile_nav_items_jsx = ""
    for item in nav_items:
        label = item.get('label', '')
        href = item.get('href', '#')
        nav_items_jsx += f'''
            <Link href="{href}" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
              {label}
            </Link>'''
        mobile_nav_items_jsx += f'''
              <Link href="{href}" className="text-lg font-medium">
                {label}
              </Link>'''

    cta_jsx = ""
    mobile_cta_jsx = ""
    if cta_text:
        cta_jsx = f'''
          <Button asChild>
            <Link href="{cta_link}">{cta_text}</Link>
          </Button>'''
        mobile_cta_jsx = f'''
              <Button className="mt-4" asChild>
                <Link href="{cta_link}">{cta_text}</Link>
              </Button>'''

    code = f'''"use client"

import {{ useState }} from "react"
import Link from "next/link"
import {{ Button }} from "@/components/ui/button"
import {{ Sheet, SheetContent, SheetTrigger }} from "@/components/ui/sheet"
import {{ Menu }} from "lucide-react"

export function {component_name}() {{
  const [isOpen, setIsOpen] = useState(false)

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto flex h-16 items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-xl font-bold">{logo_text}</span>
        </Link>

        <nav className="hidden md:flex items-center gap-6">{nav_items_jsx}{cta_jsx}
        </nav>

        <Sheet open={{isOpen}} onOpenChange={{setIsOpen}}>
          <SheetTrigger asChild className="md:hidden">
            <Button variant="ghost" size="icon">
              <Menu className="h-5 w-5" />
            </Button>
          </SheetTrigger>
          <SheetContent side="right">
            <nav className="flex flex-col gap-4 mt-8">{mobile_nav_items_jsx}{mobile_cta_jsx}
            </nav>
          </SheetContent>
        </Sheet>
      </div>
    </header>
  )
}}
'''
    return component_name, code


def generate_footer(props: dict) -> tuple[str, str]:
    """푸터 섹션 생성"""
    component_name = "Footer"
    logo_text = props.get('logo_text', 'Logo')
    description = props.get('description', '')
    columns = props.get('columns', [])
    social_links = props.get('social_links', [])
    copyright = props.get('copyright', '')

    desc_jsx = ""
    if description:
        desc_jsx = f'''
            <p className="text-sm text-muted-foreground mb-4">{description}</p>'''

    social_jsx = ""
    if social_links:
        social_items = ""
        for link in social_links:
            platform = link.get('platform', '')
            url = link.get('url', '#')
            icon_map = {
                'github': 'Github',
                'twitter': 'Twitter',
                'linkedin': 'Linkedin',
                'instagram': 'Instagram'
            }
            icon = icon_map.get(platform, 'Link')
            social_items += f'''
                <a href="{url}" target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-foreground transition-colors">
                  <{icon} className="h-5 w-5" />
                </a>'''
        social_jsx = f'''
            <div className="flex gap-4">{social_items}
            </div>'''

    columns_jsx = ""
    for col in columns:
        col_title = col.get('title', '')
        links = col.get('links', [])
        links_jsx = ""
        for link in links:
            label = link.get('label', '')
            href = link.get('href', '#')
            links_jsx += f'''
                  <li>
                    <Link href="{href}" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                      {label}
                    </Link>
                  </li>'''
        columns_jsx += f'''
          <div>
            <h3 className="font-semibold mb-4">{col_title}</h3>
            <ul className="space-y-3">{links_jsx}
            </ul>
          </div>'''

    copyright_text = copyright if copyright else f"© {{new Date().getFullYear()}} {logo_text}. All rights reserved."

    code = f'''import Link from "next/link"
import {{ Github, Twitter, Linkedin, Instagram, Link as LinkIcon }} from "lucide-react"

export function {component_name}() {{
  return (
    <footer className="border-t bg-muted/30">
      <div className="container mx-auto px-4 py-12 md:py-16">
        <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-4">
          <div className="lg:col-span-1">
            <Link href="/" className="flex items-center gap-2 mb-4">
              <span className="text-xl font-bold">{logo_text}</span>
            </Link>{desc_jsx}{social_jsx}
          </div>{columns_jsx}
        </div>

        <div className="mt-12 pt-8 border-t text-center text-sm text-muted-foreground">
          {copyright_text}
        </div>
      </div>
    </footer>
  )
}}
'''
    return component_name, code


# ============================================
# 섹션 타입 -> 생성 함수 매핑
# ============================================

SECTION_GENERATORS = {
    "hero-simple": generate_hero_simple,
    "hero-centered": generate_hero_centered,
    "features-grid": generate_features_grid,
    "features-cards": generate_features_cards,
    "testimonials": generate_testimonials,
    "stats": generate_stats,
    "pricing-cards": generate_pricing_cards,
    "cta-banner": generate_cta_banner,
    "contact-form": generate_contact_form,
    "newsletter": generate_newsletter,
    "header": generate_header,
    "footer": generate_footer,
}


def run(project_path: str, page_name: str, sections: list, metadata: dict = None) -> dict:
    """
    섹션을 조합하여 페이지 생성

    Args:
        project_path: 프로젝트 경로
        page_name: 페이지 이름
        sections: 섹션 구성 리스트
        metadata: 페이지 메타데이터

    Returns:
        생성 결과
    """
    if not os.path.exists(project_path):
        return {"success": False, "error": f"프로젝트를 찾을 수 없습니다: {project_path}"}

    # Next.js 프로젝트인지 확인 (package.json에 next가 있거나 next.config 존재)
    is_nextjs = False
    pkg_file = os.path.join(project_path, "package.json")
    if os.path.exists(pkg_file):
        try:
            with open(pkg_file, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            is_nextjs = "next" in deps
        except Exception:
            pass

    if not is_nextjs:
        for cfg in ["next.config.js", "next.config.mjs", "next.config.ts"]:
            if os.path.exists(os.path.join(project_path, cfg)):
                is_nextjs = True
                break

    if not is_nextjs:
        return {
            "success": False,
            "error": f"이 프로젝트는 Next.js 프로젝트가 아닙니다: {project_path}. "
                     "create_page는 Next.js 프로젝트 전용입니다. "
                     "기존 HTML/CSS 사이트를 수정하려면 파일을 직접 읽고 편집하세요."
        }

    # src 디렉토리 확인
    src_path = os.path.join(project_path, "src")
    if not os.path.exists(src_path):
        src_path = project_path  # src 폴더가 없는 경우

    app_path = os.path.join(src_path, "app")
    components_path = os.path.join(src_path, "components", "sections")
    os.makedirs(components_path, exist_ok=True)

    results = {
        "components_created": [],
        "page_created": None,
        "errors": []
    }

    # 섹션 컴포넌트 생성
    component_imports = []
    component_usages = []

    for section in sections:
        section_type = section.get("type", "")
        props = section.get("props", {})

        if section_type not in SECTION_GENERATORS:
            results["errors"].append(f"알 수 없는 섹션 타입: {section_type}")
            continue

        try:
            generator = SECTION_GENERATORS[section_type]
            component_name, component_code = generator(props)

            # 컴포넌트 파일 저장
            component_file = os.path.join(components_path, f"{section_type}.tsx")
            with open(component_file, "w", encoding="utf-8") as f:
                f.write(component_code)

            results["components_created"].append({
                "name": component_name,
                "file": component_file,
                "type": section_type
            })

            component_imports.append(f'import {{ {component_name} }} from "@/components/sections/{section_type}"')
            component_usages.append(f"      <{component_name} />")

        except Exception as e:
            results["errors"].append(f"{section_type} 생성 실패: {str(e)}")

    # 페이지 파일 생성
    if page_name == "index" or page_name == "home":
        page_file = os.path.join(app_path, "page.tsx")
    else:
        page_dir = os.path.join(app_path, page_name)
        os.makedirs(page_dir, exist_ok=True)
        page_file = os.path.join(page_dir, "page.tsx")

    # 메타데이터
    meta = metadata or {}
    title = meta.get("title", "My Website")
    description = meta.get("description", "Welcome to my website")

    page_code = f'''import type {{ Metadata }} from "next"
{chr(10).join(component_imports)}

export const metadata: Metadata = {{
  title: "{title}",
  description: "{description}",
}}

export default function Page() {{
  return (
    <main>
{chr(10).join(component_usages)}
    </main>
  )
}}
'''

    with open(page_file, "w", encoding="utf-8") as f:
        f.write(page_code)

    results["page_created"] = page_file

    # 하나라도 생성되었으면 부분 성공
    if results["components_created"]:
        results["success"] = True
        if results["errors"]:
            results["warning"] = f"{len(results['errors'])}개 섹션을 건너뜀 (알 수 없는 타입)"
    else:
        results["success"] = False

    return results


if __name__ == "__main__":
    # 테스트
    result = run(
        project_path="outputs/web-projects/test-project",
        page_name="index",
        sections=[
            {
                "type": "hero-centered",
                "props": {
                    "title": "IndieBiz OS",
                    "subtitle": "AI 기반 통합 비즈니스 관리 시스템",
                    "badge_text": "New",
                    "cta_text": "시작하기"
                }
            },
            {
                "type": "features-grid",
                "props": {
                    "title": "주요 기능",
                    "features": [
                        {"icon": "🤖", "title": "AI 에이전트", "description": "맞춤형 AI 비서"},
                        {"icon": "📊", "title": "분석", "description": "데이터 인사이트"},
                        {"icon": "🔗", "title": "연동", "description": "다양한 서비스 통합"}
                    ]
                }
            }
        ],
        metadata={"title": "IndieBiz OS", "description": "AI 기반 비즈니스 플랫폼"}
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
