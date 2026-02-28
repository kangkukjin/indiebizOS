# Web Builder & Homepage Manager 사용 가이드

홈페이지/웹사이트를 만들거나 수정하라는 요청을 받으면 이 가이드를 따른다.

- **기술**: Next.js + shadcn/ui + TypeScript
- **배포**: Vercel
- **강점**: 완전한 코드 제어, 컴포넌트 단위 설계, React 생태계 활용
- **적합**: 홈페이지, 블로그, 포트폴리오, 랜딩 페이지, 웹앱 등 모든 웹사이트

---

## Web-builder (forge 노드) 상세 가이드

### 두 가지 시나리오 명확 구분

### A. 새 홈페이지 만들기

```
create_project → add_component → create_page → edit_styles → preview_site → build_site → deploy_vercel
```

1. **create_project**: 새 Next.js + shadcn/ui 프로젝트 생성 → 실패 시: npm 설치 오류 확인, 디스크 공간/네트워크 확인 후 재시도
2. **add_component**: 필요한 UI 컴포넌트 추가 → 실패 시: 컴포넌트 이름 확인, list_components로 사용 가능 목록 재확인
3. **create_page**: 섹션 조합으로 페이지 생성 → 실패 시: 섹션 타입/props 확인 후 재시도
4. **edit_styles**: 테마/색상 적용
5. **preview_site**: 로컬에서 미리보기 → 실패 시: 에러 로그 확인, 코드 수정 후 재시도
6. **build_site**: 프로덕션 빌드 → 실패 시: 빌드 에러 분석, 타입 에러/import 오류 수정 후 재빌드. **빌드 실패 상태에서 배포하지 마세요.**
7. **deploy_vercel**: Vercel에 배포

### B. 기존 홈페이지 수정

⚠️ **중요: 홈페이지 수정 요청을 받으면 반드시 첫 번째로 site_registry(action='list')를 호출하세요.**
파일 시스템을 탐색하거나 ls/cat 명령으로 파일을 찾지 마세요. registry에 모든 사이트 정보(경로, 배포 URL, 기술 스택)가 있습니다.

```
[반드시 이 순서대로]
site_registry(list) → site_snapshot → 파일 직접 읽기/수정 → git push → site_live_check
```

1. **site_registry(action='list')**: 등록된 사이트 목록 확인 — ⚠️ 반드시 첫 번째! 이 결과에 local_path, repo_url, deploy_url, tech_stack 모두 포함됨
2. **site_snapshot**: 현재 구조 파악 (파일, 커밋, 페이지, 의존성)
3. **파일 직접 읽기/수정**: read_file → edit_file로 기존 코드 수정
4. **git push**: 변경사항 푸시 (자동 배포 설정 시 자동 반영)
5. **site_live_check**: 배포된 사이트 상태 점검

### 핵심 주의사항
- **기존 사이트를 수정할 때 절대 `create_project`를 호출하지 마세요.**
- **절대 run_command로 ls, cat, find 등을 사용해 사이트 파일을 찾지 마세요.** registry에 경로가 있습니다.
- 기존 사이트 개선은 반드시: `site_registry(list)` → `site_snapshot` → 파일 읽기 → 직접 수정 → git push

---

## site_registry 상세

### action 종류

| action | 설명 | 필수 파라미터 |
|--------|------|-------------|
| `register` | 새 사이트 등록 | name, local_path |
| `list` | 등록된 사이트 목록 조회 | (없음) |
| `remove` | 사이트 등록 해제 | site_id |
| `update` | 사이트 정보 수정 | site_id + 수정할 필드 |

### 사용 예시
```python
# 새 사이트 등록
site_registry(
    action='register',
    name='내 블로그',
    local_path='/path/to/site',
    repo_url='https://github.com/user/my-blog',
    deploy_url='https://my-blog.vercel.app'
)

# 목록 조회
site_registry(action='list')

# 삭제
site_registry(action='remove', site_id='my-blog')

# 수정
site_registry(action='update', site_id='my-blog', deploy_url='https://new-url.vercel.app')
```

---

## site_live_check 점검 항목

### checks 옵션

| 항목 | 설명 |
|------|------|
| `status` | HTTP 응답 상태 확인 |
| `lighthouse` | 성능, 접근성, SEO 점수, Core Web Vitals, 개선 기회 |
| `screenshot` | 스크린샷 캡처 |

### 사용 예시
```python
# 전체 점검 (기본)
site_live_check(site_id='indiebiz-homepage')

# 상태만 확인
site_live_check(site_id='indiebiz-homepage', checks=['status'])

# Lighthouse만
site_live_check(site_id='indiebiz-homepage', checks=['lighthouse'])

# URL 직접 지정 (등록되지 않은 사이트도 가능)
site_live_check(url='https://example.com')
```

---

## create_project 상세

### 템플릿 종류

| 템플릿 | 설명 | 포함 섹션 |
|--------|------|----------|
| `blank` | 빈 프로젝트 | (없음) |
| `landing` | 랜딩페이지 | 히어로, 기능소개, CTA |
| `portfolio` | 포트폴리오 | 프로필, 작업물, 연락처 |
| `blog` | 블로그 | 포스트 목록, 상세 |
| `business` | 비즈니스 | 서비스, 가격, 문의폼 |

### 추가 기능 (features)
- `dark_mode`: 다크 모드 토글
- `i18n`: 다국어 지원
- `analytics`: 분석 도구 연동
- `seo`: SEO 메타태그 최적화
- `pwa`: Progressive Web App

### 예시
```python
create_project(
    name="my-homepage",        # 영문, 소문자, 하이픈 허용
    template="landing",
    features=["dark_mode", "seo"],
    output_dir="/path/to/output"
)
```

---

## shadcn/ui 컴포넌트 카테고리

### add_component에서 사용 가능한 주요 컴포넌트

| 카테고리 | 컴포넌트 |
|---------|---------|
| **기본** | button, input, label, badge, separator |
| **레이아웃** | card, dialog, sheet, tabs, accordion |
| **폼** | form, select, checkbox, radio-group, switch |
| **네비게이션** | navigation-menu, dropdown-menu, breadcrumb |

### list_components 카테고리 옵션
`all`, `layout`, `form`, `data`, `feedback`, `navigation`, `overlay`

### 사용 예시
```python
# 여러 컴포넌트 한 번에 추가
add_component(
    project_path="/path/to/project",
    components=["button", "card", "dialog", "tabs"]
)

# 카테고리별 목록 조회
list_components(category='form')

# 프로젝트에 설치된 컴포넌트 확인
list_components(project_path="/path/to/project")
```

---

## 섹션 카테고리

### list_sections / create_page에서 사용 가능한 섹션

| 카테고리 | 섹션 타입 | 설명 |
|---------|----------|------|
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
```python
# hero-simple
{"title": "메인 제목", "subtitle": "부제목", "cta_text": "시작하기"}

# features-grid
{"title": "주요 기능", "features": [{"title": "기능1", "description": "설명", "icon": "아이콘"}]}

# pricing-cards
{"title": "가격", "plans": [{"name": "Free", "price": "0원", "features": ["기능1"]}]}
```

---

## 테마 프리셋 (edit_styles)

| 프리셋 | 설명 |
|--------|------|
| `default` | 기본 (무채색/회색) |
| `blue` | 파랑 계열 |
| `green` | 녹색 계열 |
| `purple` | 보라 계열 |
| `orange` | 주황 계열 |
| `red` | 빨강 계열 |
| `custom` | 커스텀 색상 (`custom_colors` 파라미터로 지정) |

### 테두리 반경 (border_radius)
`none`, `sm`, `md`, `lg`, `full`

### 사용 예시
```python
# 프리셋 테마 적용
edit_styles(project_path="/path", theme="blue", border_radius="lg")

# 커스텀 색상
edit_styles(
    project_path="/path",
    theme="custom",
    custom_colors={"primary": "#3b82f6", "secondary": "#10b981"}
)
```

---

## preview_site 사용법

### 액션 종류

| action | 설명 |
|--------|------|
| `start` | 개발 서버 시작 (기본) |
| `stop` | 실행 중인 서버 중지 |
| `status` | 서버 상태 확인 |

### 사용 예시
```python
# 서버 시작 (기본 포트 3000)
preview_site(project_path="/path", action="start")

# 다른 포트로 시작
preview_site(project_path="/path", port=3001)

# 서버 상태 확인
preview_site(project_path="/path", action="status")

# 서버 중지
preview_site(project_path="/path", action="stop")
```

실행 후 브라우저에서 `http://localhost:3000` 접속

---

## fetch_component 사용법

### 출력 형식 (output_format)

| 형식 | 설명 | 용도 |
|------|------|------|
| `code` | 코드와 사용 예시 반환 | 코드 확인/참고 |
| `json` | 전체 메타데이터 반환 | 의존성 확인 |
| `save` | 프로젝트에 직접 저장 | 컴포넌트 설치 |

### 사용 예시
```python
# 코드 확인
fetch_component(component="button", output_format="code")

# 프로젝트에 저장
fetch_component(
    component="card",
    output_format="save",
    project_path="/path/to/project"
)

# 스타일 선택
fetch_component(component="dialog", style="new-york")  # 또는 "default"
```

---

## 빌드 및 배포

### build_site
```python
build_site(project_path="/path")
# → .next/ 디렉토리에 빌드 파일 생성
# → 빌드 크기 및 라우트 정보 제공

# 번들 분석 포함
build_site(project_path="/path", analyze=True)
```

### deploy_vercel
```python
# 미리보기 배포 (기본)
deploy_vercel(project_path="/path")

# 프로덕션 배포
deploy_vercel(project_path="/path", production=True)

# 프로젝트 이름 지정
deploy_vercel(project_path="/path", production=True, project_name="my-site")
```

**전제조건:**
- Vercel CLI 설치: `npm install -g vercel`
- Vercel 계정 로그인: `vercel login`

---

## 전체 워크플로우 예시

### 새 랜딩 페이지 만들기
```
1. create_project(name="my-landing", template="landing")
   → 실패 시: 에러 확인 후 재시도. 프로젝트 생성 없이는 다음 단계 불가.
2. add_component(project_path="...", components=["button", "card"])
   → 실패 시: 컴포넌트 이름/경로 확인
3. create_page(project_path="...", page_name="index", sections=[...])
4. edit_styles(project_path="...", theme="blue")
5. preview_site(project_path="...", action="start")
   → 문제 발견 시: 코드 수정 → 재확인 반복
6. (확인 후) build_site(project_path="...")
   → 빌드 실패 시: 에러 수정 후 재빌드. 빌드 성공 전까지 배포 금지.
7. deploy_vercel(project_path="...", production=True)
8. site_registry(action="register", name="My Landing", local_path="...")
```

### 기존 사이트 수정하기
⚠️ **절대 파일 시스템을 탐색하지 마세요. registry가 모든 정보를 알려줍니다.**
```
1. site_registry(action='list')              → ⚠️ 반드시 첫 번째! 사이트 목록 + 경로 + URL 확인
2. site_snapshot(site_id='my-site')          → 현재 구조 파악 (어떤 파일이 있는지 여기서 확인)
3. read_file('/path/to/page.tsx')            → 파일 읽기 (경로는 1,2단계에서 이미 알고 있음)
4. edit_file('/path/to/page.tsx', ...)       → 코드 수정
5. run_command('cd /path && git add -A && git commit -m "update" && git push')
6. site_live_check(site_id='my-site')        → 배포 결과 확인
```
❌ 나쁜 예: run_command('ls ~/Desktop/AI/HomePages/') → 이렇게 하지 마세요!
✅ 좋은 예: site_registry(action='list') → registry가 local_path를 알려줌
