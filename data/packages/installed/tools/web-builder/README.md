# web-builder 패키지

AI가 shadcn/ui를 활용해 홈페이지를 제작하는 도구 패키지입니다.

## 개요

- **Next.js + shadcn/ui** 기반 프로젝트 생성
- **섹션 기반** 페이지 조합 시스템
- **테마 프리셋** 및 커스텀 스타일 지원
- **Vercel 배포** 통합

## 도구 목록

### 프로젝트 관리

| 도구 | 설명 |
|------|------|
| `create_project` | Next.js + shadcn/ui 프로젝트 생성 |
| `add_component` | shadcn/ui 컴포넌트 추가 |
| `list_components` | 사용 가능한 컴포넌트 목록 |

### 페이지 제작

| 도구 | 설명 |
|------|------|
| `create_page` | 섹션을 조합하여 페이지 생성 |
| `list_sections` | 사용 가능한 섹션 템플릿 목록 |
| `edit_styles` | 테마 및 스타일 수정 |

### 빌드 및 배포

| 도구 | 설명 |
|------|------|
| `preview_site` | 로컬 미리보기 서버 |
| `build_site` | 프로덕션 빌드 |
| `deploy_vercel` | Vercel 배포 |
| `analyze_site` | Lighthouse 품질 분석 |

## 사용 예시

### 1. 프로젝트 생성

```python
create_project(
    name="my-homepage",
    template="landing",
    features=["dark_mode", "seo"]
)
```

**템플릿 옵션:**
- `blank` - 빈 프로젝트
- `landing` - 랜딩 페이지
- `portfolio` - 포트폴리오
- `blog` - 블로그
- `business` - 비즈니스 사이트

### 2. 페이지 생성

```python
create_page(
    project_path="/path/to/project",
    page_name="index",
    sections=[
        {
            "type": "header",
            "props": {
                "logo_text": "IndieBiz",
                "nav_items": [
                    {"label": "소개", "href": "#about"},
                    {"label": "기능", "href": "#features"},
                    {"label": "가격", "href": "#pricing"}
                ],
                "cta_text": "시작하기",
                "cta_link": "/signup"
            }
        },
        {
            "type": "hero-centered",
            "props": {
                "badge_text": "New",
                "title": "AI 기반 비즈니스 플랫폼",
                "subtitle": "당신의 비즈니스를 자동화하세요",
                "cta_text": "무료로 시작하기"
            }
        },
        {
            "type": "features-grid",
            "props": {
                "title": "주요 기능",
                "columns": 3,
                "features": [
                    {"icon": "🤖", "title": "AI 에이전트", "description": "맞춤형 AI 비서가 업무를 도와줍니다"},
                    {"icon": "📊", "title": "데이터 분석", "description": "실시간 인사이트를 제공합니다"},
                    {"icon": "🔗", "title": "통합 연동", "description": "다양한 서비스와 연결됩니다"}
                ]
            }
        },
        {
            "type": "pricing-cards",
            "props": {
                "title": "가격 안내",
                "plans": [
                    {
                        "name": "Free",
                        "price": "₩0",
                        "description": "개인 사용자용",
                        "features": ["기본 기능", "이메일 지원"],
                        "cta_text": "시작하기"
                    },
                    {
                        "name": "Pro",
                        "price": "₩29,000",
                        "description": "전문가용",
                        "features": ["모든 기능", "우선 지원", "API 접근"],
                        "cta_text": "업그레이드",
                        "highlighted": True
                    }
                ]
            }
        },
        {
            "type": "footer",
            "props": {
                "logo_text": "IndieBiz",
                "description": "AI 기반 비즈니스 자동화 플랫폼",
                "columns": [
                    {
                        "title": "제품",
                        "links": [
                            {"label": "기능", "href": "#features"},
                            {"label": "가격", "href": "#pricing"}
                        ]
                    }
                ],
                "social_links": [
                    {"platform": "github", "url": "https://github.com"},
                    {"platform": "twitter", "url": "https://twitter.com"}
                ]
            }
        }
    ],
    metadata={
        "title": "IndieBiz - AI 비즈니스 플랫폼",
        "description": "AI 기반 비즈니스 자동화 플랫폼"
    }
)
```

### 3. 스타일 변경

```python
edit_styles(
    project_path="/path/to/project",
    theme="blue",  # default, blue, green, purple, orange, red
    border_radius="lg"  # none, sm, md, lg, full
)
```

### 4. 미리보기 및 배포

```python
# 로컬 미리보기
preview_site(project_path="/path/to/project", port=3000)

# 빌드
build_site(project_path="/path/to/project")

# Vercel 배포
deploy_vercel(project_path="/path/to/project", production=True)

# 품질 분석
analyze_site(url="https://my-site.vercel.app")
```

## 섹션 타입

### Hero (히어로)
- `hero-simple` - 심플 히어로
- `hero-centered` - 중앙 정렬 히어로

### Features (기능)
- `features-grid` - 그리드 레이아웃
- `features-cards` - 카드 레이아웃

### Social (사회적 증거)
- `testimonials` - 고객 후기
- `stats` - 통계

### Commerce (상업)
- `pricing-cards` - 가격표
- `cta-banner` - CTA 배너

### Form (폼)
- `contact-form` - 문의 폼
- `newsletter` - 뉴스레터 구독

### Navigation (네비게이션)
- `header` - 헤더
- `footer` - 푸터

## 테마

| 테마 | 설명 |
|------|------|
| `default` | 기본 (회색/흰색) |
| `blue` | 파란색 계열 |
| `green` | 초록색 계열 |
| `purple` | 보라색 계열 |
| `orange` | 주황색 계열 |
| `red` | 빨간색 계열 |
| `custom` | 커스텀 색상 |

## 요구사항

- Node.js 18+
- npm 또는 yarn
- (선택) Vercel CLI (`npm install -g vercel`)

## 출력 경로

기본 출력 경로: `/Users/kangkukjin/Desktop/AI/outputs/web-projects/`
