# Web Builder & Homepage Manager 사용 가이드

홈페이지/웹사이트를 만들거나 수정하라는 요청을 받으면 이 가이드를 따른다.

- **기술**: Next.js + shadcn/ui + TypeScript
- **배포**: Vercel
- **강점**: 완전한 코드 제어, 컴포넌트 단위 설계, React 생태계 활용
- **적합**: 홈페이지, 블로그, 포트폴리오, 랜딩 페이지, 웹앱 등 모든 웹사이트

## 운영 모드 매트릭스 (2026-05-27 IBL 4기준 재분류)

| 영역 | 모드 | 처리 방식 |
|---|---|---|
| 외부 행동 (Playwright/Lighthouse/HTTP 서버/Next.js/Vercel CLI/shadcn CLI) | **M1 풀 IBL** | 전용 액션 (web_snapshot/live_check/preview/build/deploy/web_component) |
| 어드민 CRUD (sites.json, 카탈로그 조회) | **M3 직접 편집 + 통합 진입점** | `web_site`/`web_catalog` 한 액션에 op로 분기. 빈번하지 않은 어드민 |
| 생성 (프로젝트 디렉토리/페이지) | **M2 얇은 IBL + 가이드** | `web_create` 진입점 + 이 가이드. 복잡한 경우 [self:write]로 직접 작성 |
| 스타일 편집 (globals.css/tailwind.config.*) | **M3 직접 편집** | IBL 액션 없음. [self:edit]로 globals.css 등 직접 수정 |

## 액션 빠른 참고

| 액션 | 용도 | 핵심 파라미터 |
|---|---|---|
| `web_site` | 사이트 레지스트리 CRUD | op: list/register/remove/update |
| `web_catalog` | 컴포넌트/섹션 카탈로그 조회 | kind: components/sections |
| `web_create` | 새 프로젝트/페이지 생성 | target: site/page |
| `web_component` | 컴포넌트 가져오기/추가 | op: fetch/add |
| `web_snapshot` | 사이트 스크린샷 | site_id |
| `web_live_check` | Lighthouse 품질 검사 | site_id + checks (status/lighthouse/screenshot) |
| `web_preview` | 로컬 미리보기 서버 제어 | project_path + action: start/stop/status |
| `web_build` | 프로덕션 빌드 | project_path |
| `web_deploy` | Vercel 배포 | project_path + production |

## 두 가지 시나리오 명확 구분

### A. 새 홈페이지 만들기

```
web_create(site) → web_component(add) → web_create(page) → 스타일 직접 편집 → web_preview → web_build → web_deploy → web_site(register)
```

1. **web_create(target=site)**: 새 Next.js + shadcn/ui 프로젝트 생성
2. **web_component(op=add)**: shadcn/ui 컴포넌트 추가 (또는 `run_command('npx shadcn@latest add button card --yes')`로 여러 개 한꺼번에)
3. **web_create(target=page)**: 섹션 조합으로 페이지 생성
4. **스타일 편집**: `[self:read]`로 `{project_path}/src/app/globals.css` 읽기 → CSS 변수 직접 수정 → `[self:edit]`로 저장
5. **web_preview(action=start)**: 로컬에서 미리보기 → 문제 시 코드 수정 → 재확인
6. **web_build**: 프로덕션 빌드 → 빌드 실패 상태에서 배포하지 마세요
7. **web_deploy(production=true)**: Vercel 프로덕션 배포 → 출력에서 URL 확인
8. **web_site(op=register)**: 새 사이트를 레지스트리에 등록

### B. 기존 홈페이지 수정

⚠️ **중요: 홈페이지 수정 요청을 받으면 반드시 첫 번째로 `[engines:web_site]{op: "list"}`를 호출하세요.**
파일 시스템을 탐색하거나 ls/cat 명령으로 파일을 찾지 마세요. registry에 모든 사이트 정보(경로, 배포 URL, 기술 스택)가 있습니다.

```
[반드시 이 순서]
web_site(list) → 현재 페이지 확인 → web_snapshot → 파일 직접 읽기/수정 → git push → web_live_check
```

1. **web_site(op=list)**: 등록된 사이트 목록 확인 — ⚠️ 반드시 첫 번째!
2. **현재 배포된 페이지 내용 확인**: `[sense:crawl]{url: "배포URL"}`로 현재 페이지 내용 크롤링. ⚠️ 브라우저 자동화(`[limbs:navigate]`, `[limbs:content]`)를 사용하지 마세요 — 크롤링이 훨씬 빠르고 가볍습니다.
3. **web_snapshot**: 현재 구조 파악 (스크린샷)
4. **파일 직접 읽기/수정**: `[self:read]` → `[self:edit]`로 기존 코드 수정
5. **git push**: 변경사항 푸시 (자동 배포 설정 시 자동 반영)
6. **web_live_check**: 배포된 사이트 상태 점검

### 핵심 주의사항
- **기존 사이트 수정 시 절대 `web_create(target=site)`를 호출하지 마세요.**
- **절대 run_command로 ls, cat, find 등을 사용해 사이트 파일을 찾지 마세요.** registry에 경로가 있습니다.
- 기존 사이트 개선은 반드시: `web_site(list)` → `web_snapshot` → 파일 읽기 → 직접 수정 → git push

## web_site 상세

### op 종류

| op | 설명 | 필수 파라미터 |
|---|---|---|
| `list` | 등록된 사이트 목록 조회 | (없음) |
| `register` | 새 사이트 등록 | name, local_path |
| `remove` | 사이트 등록 해제 | site_id |
| `update` | 사이트 정보 수정 | site_id + 수정할 필드 |

### 사용 예시
```
# 새 사이트 등록
[engines:web_site]{op: "register", name: "내 블로그", local_path: "/path/to/site", repo_url: "https://github.com/user/my-blog", deploy_url: "https://my-blog.vercel.app"}

# 목록 조회
[engines:web_site]{op: "list"}

# 삭제
[engines:web_site]{op: "remove", site_id: "my-blog"}

# 수정
[engines:web_site]{op: "update", site_id: "my-blog", deploy_url: "https://new-url.vercel.app"}
```

빈번한 호출이면 sites.json 직접 읽기도 가능:
```
[self:read]{path: "/Users/.../indiebizOS/data/packages/installed/tools/web-builder/sites.json"}
```

## web_live_check 점검 항목

### checks 옵션

| 항목 | 설명 |
|---|---|
| `status` | HTTP 응답 상태 확인 |
| `lighthouse` | 성능, 접근성, SEO 점수, Core Web Vitals, 개선 기회 |
| `screenshot` | 스크린샷 캡처 |

### 사용 예시
```
# 전체 점검 (기본)
[engines:web_live_check]{site_id: "indiebiz-homepage"}

# 상태만 확인
[engines:web_live_check]{site_id: "indiebiz-homepage", checks: ["status"]}

# Lighthouse만
[engines:web_live_check]{site_id: "indiebiz-homepage", checks: ["lighthouse"]}

# URL 직접 지정 (등록되지 않은 사이트도 가능)
[engines:web_live_check]{url: "https://example.com"}
```

## web_create 상세

### target=site (신규 프로젝트)

#### 템플릿 종류

| 템플릿 | 설명 | 포함 섹션 |
|---|---|---|
| `blank` | 빈 프로젝트 | (없음) |
| `landing` | 랜딩페이지 | 히어로, 기능소개, CTA |
| `portfolio` | 포트폴리오 | 프로필, 작업물, 연락처 |
| `blog` | 블로그 | 포스트 목록, 상세 |
| `business` | 비즈니스 | 서비스, 가격, 문의폼 |

#### 추가 기능 (features)
- `dark_mode`: 다크 모드 토글
- `i18n`: 다국어 지원
- `analytics`: 분석 도구 연동
- `seo`: SEO 메타태그 최적화
- `pwa`: Progressive Web App

#### 예시
```
[engines:web_create]{target: "site", name: "my-homepage", template: "landing", features: ["dark_mode", "seo"], output_dir: "/path/to/output"}
```

### target=page (기존 프로젝트에 페이지 추가)

먼저 사용 가능한 섹션 카탈로그 확인:
```
[engines:web_catalog]{kind: "sections"}
```
원하는 섹션을 골라 페이지 생성:
```
[engines:web_create]{target: "page", project_path: "/path/to/project", page_name: "about", sections: ["hero-centered", "features-grid", "cta-banner"], metadata: {title: "About"}}
```

### 자유 코드 (M2 보조)
복잡한 구조는 [self:write]로 직접 디렉토리 골격을 만들고, package.json·Next.js 설정을 직접 작성한 뒤 `[engines:web_site]{op: "register"}`로 레지스트리에 등록하는 흐름이 더 유연합니다.

## web_component 상세

### op 종류

| op | 설명 | 도구 |
|---|---|---|
| `add` | shadcn/ui 컴포넌트를 프로젝트에 설치 | shadcn CLI |
| `fetch` | 외부 CDN/레지스트리에서 코드 가져오기 | HTTP |

### 사용 예시
```
# shadcn 설치 (단일)
[engines:web_component]{op: "add", project_path: "/path", component: "button"}

# 외부 가져오기 (코드 확인)
[engines:web_component]{op: "fetch", component: "Navigation", style: "new-york", output_format: "code"}
```

여러 개 한꺼번에 설치는 CLI가 더 효율적:
```
run_command('cd /path && npx shadcn@latest add button card dialog tabs --yes')
```

## shadcn/ui 컴포넌트 카테고리

### 사용 가능한 주요 컴포넌트

| 카테고리 | 컴포넌트 |
|---|---|
| **기본** | button, input, label, badge, separator |
| **레이아웃** | card, dialog, sheet, tabs, accordion |
| **폼** | form, select, checkbox, radio-group, switch |
| **네비게이션** | navigation-menu, dropdown-menu, breadcrumb |

### 카테고리별 카탈로그 조회
```
[engines:web_catalog]{kind: "components", category: "form"}
```
category 옵션: `all`, `layout`, `form`, `data`, `feedback`, `navigation`, `overlay`

## 섹션 카테고리

### 사용 가능한 섹션 (`web_catalog{kind:"sections"}` 결과 일부)

| 카테고리 | 섹션 타입 | 설명 |
|---|---|---|
| **hero** | hero-simple | 심플 히어로 |
| | hero-centered | 중앙정렬 히어로 |
| | hero-image | 이미지 히어로 |
| | hero-video | 비디오 히어로 |
| **content** | text-content | 텍스트 콘텐츠 |
| | two-column | 2열 레이아웃 |
| | image-text | 이미지+텍스트 |
| **feature** | features-grid | 기능 그리드 |
| | features-alternating | 교차 레이아웃 |
| | features-cards | 카드 레이아웃 |
| **social** | testimonials | 고객 후기 |
| | logo-cloud | 파트너 로고 |
| | stats | 통계/수치 |
| **commerce** | pricing-cards | 가격표 |
| | cta-banner | CTA 배너 |
| **form** | contact-form | 문의 폼 |
| | newsletter | 뉴스레터 구독 |
| **navigation** | header | 헤더 |
| | footer | 푸터 |

### 섹션 props 예시
```
# hero-simple
{"title": "메인 제목", "subtitle": "부제목", "cta_text": "시작하기"}

# features-grid
{"title": "주요 기능", "features": [{"title": "기능1", "description": "설명", "icon": "아이콘"}]}

# pricing-cards
{"title": "가격", "plans": [{"name": "Free", "price": "0원", "features": ["기능1"]}]}
```

## 스타일 편집 (M3 직접 편집)

IBL 액션 없음. `globals.css` / `tailwind.config.*` / `theme.json`을 `[self:edit]`로 직접 편집합니다. 이는 의도된 것 — 스타일 변경은 작업 중 한두 번이라 IBL 액션화 가치(4기준 점수)가 낮습니다.

### globals.css에서 수정할 주요 CSS 변수
```css
:root {
  --primary: 221.2 83.2% 53.3%;      /* HSL 값 */
  --secondary: 210 40% 96.1%;
  --accent: 210 40% 96.1%;
  --radius: 0.5rem;                   /* none=0, sm=0.25rem, md=0.375rem, lg=0.5rem, full=9999px */
}
```

### 프리셋별 대표 primary 색상
- `blue`: 221.2 83.2% 53.3%
- `green`: 142.1 76.2% 36.3%
- `purple`: 262.1 83.3% 57.8%
- `orange`: 24.6 95% 53.1%
- `red`: 0 84.2% 60.2%

### 편집 예시
```
[self:read]{path: "/path/to/project/src/app/globals.css"}
[self:edit]{path: "/path/to/project/src/app/globals.css", old_string: "--primary: 221.2 83.2% 53.3%", new_string: "--primary: 262.1 83.3% 57.8%"}
```

## web_preview 사용법

### action 종류

| action | 설명 |
|---|---|
| `start` | 개발 서버 시작 (기본) |
| `stop` | 실행 중인 서버 중지 |
| `status` | 서버 상태 확인 |

### 사용 예시
```
# 서버 시작 (기본 포트 3000)
[engines:web_preview]{project_path: "/path", action: "start"}

# 다른 포트로 시작
[engines:web_preview]{project_path: "/path", port: 3001}

# 서버 상태 확인
[engines:web_preview]{project_path: "/path", action: "status"}

# 서버 중지
[engines:web_preview]{project_path: "/path", action: "stop"}
```

실행 후 브라우저에서 `http://localhost:3000` 접속.

## 빌드 및 배포

### 빌드
```
[engines:web_build]{project_path: "/path/to/project"}
```
실패 시: 에러 로그 분석 → 타입 에러/import 오류 수정 후 재빌드. 빌드 성공 전까지 배포 금지.

### 배포
```
# 프로덕션 배포
[engines:web_deploy]{project_path: "/path/to/project", production: true}

# 프로젝트 이름 지정
[engines:web_deploy]{project_path: "/path/to/project", production: true, project_name: "my-site"}
```

**전제조건 (실패 시 확인):**
```
run_command('vercel --version')   # 미설치면: npm install -g vercel
run_command('vercel whoami')      # 미로그인이면: vercel login
```

### 파이프라인
```
[engines:web_build]{project_path: "/path"} >> [engines:web_deploy]{project_path: "/path", production: true} >> [engines:web_live_check]{site_id: "내-사이트"}
```

## 전체 워크플로우 예시

### 새 랜딩 페이지 만들기
```
1. [engines:web_create]{target: "site", name: "my-landing", template: "landing"}
2. run_command('cd {path} && npx shadcn@latest add button card --yes')
3. [engines:web_create]{target: "page", project_path: "...", page_name: "index", sections: [...]}
4. [self:read]/{self:edit}으로 globals.css의 CSS 변수 수정
5. [engines:web_preview]{project_path: "...", action: "start"}  # 문제 발견 시 코드 수정 반복
6. [engines:web_build]{project_path: "..."}  # 빌드 성공 전까지 배포 금지
7. [engines:web_deploy]{project_path: "...", production: true}
8. [engines:web_site]{op: "register", name: "My Landing", local_path: "..."}
```

### 기존 사이트 수정하기
⚠️ **절대 파일 시스템을 탐색하지 마세요. registry가 모든 정보를 알려줍니다.**
```
1. [engines:web_site]{op: "list"}            # ⚠️ 반드시 첫 번째!
2. [engines:web_snapshot]{site_id: "my-site"}  # 현재 구조 파악
3. [self:read]{path: "/path/to/page.tsx"}   # 경로는 1,2단계에서 알고 있음
4. [self:edit]{path: "/path/to/page.tsx", ...}
5. run_command('cd /path && git add -A && git commit -m "update" && git push')
6. [engines:web_live_check]{site_id: "my-site"}
```
- ❌ 나쁜 예: `run_command('ls ~/Desktop/AI/HomePages/')`
- ✅ 좋은 예: `[engines:web_site]{op: "list"}` → registry가 local_path를 알려줌

## 마이그레이션 노트 (2026-05-27)

기존 16종 액션 → 9종으로 정리. 옛 액션명은 모두 alias로 자동 정규화되므로 학습 데이터/외부 호출은 그대로 동작.

| 옛 액션 | 새 표기 |
|---|---|
| web_site_list/register/remove/update | `web_site {op}` |
| web_list_components / web_list_sections | `web_catalog {kind}` |
| web_create_site / web_create_page | `web_create {target}` |
| web_fetch_component / web_add_component | `web_component {op}` |
| web_edit_styles | (폐기 — `[self:edit]`로 globals.css 직접 편집) |
