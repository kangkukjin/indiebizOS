# Web Builder & Homepage Manager 사용 가이드

홈페이지/웹사이트를 만들거나 수정하라는 요청을 받으면 이 가이드를 따른다.

- **기술**: Next.js + shadcn/ui + TypeScript
- **배포**: Vercel
- **강점**: 완전한 코드 제어, 컴포넌트 단위 설계, React 생태계 활용
- **적합**: 홈페이지, 블로그, 포트폴리오, 랜딩 페이지, 웹앱 등 모든 웹사이트

## 먼저 — 목적을 생각하고, 전문가처럼 짓는다

손대기 전에 묻는다: **이 페이지는 무엇을 위해 있는가? 누가 보고, 무엇을 느끼고, 무엇을 하길 바라는가?** 요청을 글자 그대로 기계처럼 만족시키지 말고, *그 목적에 더 잘 복무하도록* 고친다. "이미지 넣어줘"는 표면이고, 진짜 일은 그 페이지가 *목적을 더 잘 달성하게* 만드는 것이다 — 좋은 디자이너·카피라이터라면 어떻게 할지를 기준 삼는다.

- **목적에서 출발한다**: 이 페이지가 전해야 할 *한 가지*가 첫 화면에서 즉시 와닿는가.
- **진실 소스와 *메시지*를 맞춘다**: 이 사이트가 설명하는 대상(제품·README·스펙)이 *지금* 무엇을 말하는지 읽고, 페이지의 메시지가 그것과 어긋나면 *페이지를 고친다.* 수치만 맞추는 게 아니라 — 강조점·포지셔닝이 바뀌었으면 그게 페이지에 올라와야 한다. (예: README의 핵심 메시지가 바뀌었는데 히어로 카피가 옛 메시지 그대로면, 그 카피를 바꾼다.)
- **디폴트로 수렴하지 않는다**: 손대고 나면 아래 [디자인 품질 체크리스트]로 스스로 끌어올린다. 파란 버튼·가운데 히어로에서 멈추지 않는다.

## 너에겐 web-builder보다 큰 몸이 있다

이 작업은 web 액션만의 일이 아니다. **indiebizOS의 IBL 전체가 네 재료 창고다.** 텍스트만 채우거나, 누가 미리 넣어둔 파일만 쓰지 말고, 필요한 걸 *만들어서* 쓴다. 막히면 먼저 떠올린다 — *"이 일에 indiebizOS의 어떤 능력이 도움이 되나?"*

- **이미지가 빈약하면 만든다**: `[engines:image_gemini]`(Nano Banana 2)로 히어로 배경·일러스트·아이콘을 생성하고 `[engines:image_critic]`로 채점해 통과분만 쓴다. (단, 추상 일러스트보다 *실제 제품·화면 스크린샷*이 신뢰를 준다 — 있으면 그쪽이 우선.)
- **도식·목업이 필요하면**: `[engines:slide]` / `[engines:render_html]`로 다이어그램을 PNG로 렌더해 임베드.
- **데이터를 보여줘야 하면**: `[engines:chart]`로 차트를. 그리고 *진짜 수치*는 추측하지 말고 소스(README·레지스트리·실제 데이터)에서 길어온다.
- **결과를 눈으로 본다**: `[engines:image_read]`로 스크린샷을 실제로 읽어 확인한다(아래 [배포 후 시각 검증]).

web 액션은 *출발점*이지 울타리가 아니다.

## 운영 모드 매트릭스 (2026-05-27 IBL 4기준 재분류)

| 영역 | 모드 | 처리 방식 |
|---|---|---|
| 외부 행동 (Playwright/Lighthouse/HTTP 서버/Next.js/Vercel CLI/shadcn CLI) | **M1 풀 IBL** | `web`{op: build/deploy/preview/snapshot/check} + `web_component` |
| 어드민 CRUD (sites.json, 카탈로그 조회) | **M3 직접 편집 + 통합 진입점** | `web_site`(레지스트리)/`web_component`{op:catalog}. 빈번하지 않은 어드민 |
| 생성 (프로젝트 디렉토리/페이지) | **M2 얇은 IBL + 가이드** | `web`{op:create} 진입점 + 이 가이드. 복잡한 경우 [self:write]로 직접 작성 |
| 스타일 편집 (globals.css/tailwind.config.*) | **M3 직접 편집** | IBL 액션 없음. [self:edit]로 globals.css 등 직접 수정 |

## 액션 빠른 참고 (2026-06-03 어휘 정리: 9개 → 3개)

| 액션 | op | 용도 |
|---|---|---|
| `[engines:web]` | create | 새 프로젝트/페이지 생성 (target: site/page) |
| | build | 프로덕션 빌드 (project_path) |
| | deploy | Vercel 배포 (project_path + production) |
| | preview | 로컬 미리보기 서버 (project_path + action: start/stop/status) — **기본 op** |
| | snapshot | 사이트 스크린샷 (site_id) |
| | check | Lighthouse 품질 검사 (site_id + checks) |
| | styles | shadcn 테마 편집 (project_path + theme 프리셋/custom_colors HSL + border_radius) |
| `[engines:web_component]` | catalog | 컴포넌트/섹션 카탈로그 조회 (kind: components/sections) |
| | fetch | 컴포넌트 다운로드 (component) — **기본 op** |
| | add | shadcn/ui 설치 (component + project_path) |
| `[engines:web_site]` | list/register/remove/update | 사이트 레지스트리 CRUD |

## 두 가지 시나리오 명확 구분

### A. 새 홈페이지 만들기

```
web_create(site) → web_component(add) → web_create(page) → web(styles) → web_preview → web_build → web_deploy → web_site(register)
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

기존 사이트는 처음부터 만들지 않는다 — `web_create(target=site)`는 새 사이트 전용이다. 시작은 `[engines:web_site]{op: "list"}`: registry가 사이트의 *루트 경로·배포 URL·기술 스택*을 알려준다. 프로젝트 *위치*를 ls/find로 다시 찾을 필요는 없다(registry가 안다). 단, *무엇을 고칠지* 알려면 그 프로젝트 *안*(`src/app`, `src/components/sections` 등)은 `[self:list]`·`[self:read]`로 둘러봐 구조를 파악한다 — 위치 찾기와 구조 파악은 다른 일이다.

권장 흐름(상황에 맞게 조정):
```
web_site(list) → 현재 페이지가 뭘 말하는지 읽기 → 목적에 맞게 수정 → 빌드 → 배포 → 시각 검증
```

1. **web_site(op=list)**: 사이트의 루트 경로·배포 URL 확보.
2. **현재 페이지 파악**: `[sense:crawl]{url: "배포URL"}`로 라이브 텍스트를 빠르게 읽고, `[self:read]`로 관련 컴포넌트(page.tsx·해당 섹션들)를 읽어 *지금 페이지가 무엇을·어떻게 말하는지* 본다. (전체 화면을 픽셀로 봐야 하면 `[engines:web]{op:snapshot}` 또는 `[limbs:browser]{op:screenshot}`.)
3. **목적에 맞게 수정**: `[self:edit]`로 코드를 고친다 — 단순 문자열 교체가 아니라, 위 [목적] 절 기준으로 페이지가 그 목적에 더 잘 복무하도록.
4. **빌드**: `[engines:web]{op:build}` — 빌드 성공 전엔 배포하지 않는다.
5. **배포**: 이 사이트가 *어떻게* 배포되는지부터 확인한다(아래 [빌드 및 배포]). git 연동 자동배포일 수도, vercel CLI 토큰 방식일 수도 있다.
6. **시각 검증**: 아래 [배포 후 시각 검증]을 거쳐야 "완료".

`web_create(target=site)`는 기존 사이트엔 쓰지 않는다(새 사이트를 또 만들어버린다). 그 외엔 위 흐름을 상황에 맞게 줄이거나 늘린다.

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

## web {op:"check"} 점검 항목

### checks 옵션

| 항목 | 설명 |
|---|---|
| `status` | HTTP 응답 상태 확인 |
| `lighthouse` | 성능, 접근성, SEO 점수, Core Web Vitals, 개선 기회 |
| `screenshot` | 스크린샷 캡처 |

### 사용 예시
```
# 전체 점검 (기본)
[engines:web]{op: "check", site_id: "indiebiz-homepage"}

# 상태만 확인
[engines:web]{op: "check", site_id: "indiebiz-homepage", checks: ["status"]}

# Lighthouse만
[engines:web]{op: "check", site_id: "indiebiz-homepage", checks: ["lighthouse"]}

# URL 직접 지정 (등록되지 않은 사이트도 가능)
[engines:web]{op: "check", url: "https://example.com"}
```

## web {op:"create"} 상세

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
[engines:web]{op: "create", target: "site", name: "my-homepage", template: "landing", features: ["dark_mode", "seo"], output_dir: "/path/to/output"}
```

### target=page (기존 프로젝트에 페이지 추가)

먼저 사용 가능한 섹션 카탈로그 확인:
```
[engines:web_component]{op: "catalog", kind: "sections"}
```
원하는 섹션을 골라 페이지 생성:
```
[engines:web]{op: "create", target: "page", project_path: "/path/to/project", page_name: "about", sections: ["hero-centered", "features-grid", "cta-banner"], metadata: {title: "About"}}
```

### 자유 코드 (M2 보조)
복잡한 구조는 [self:write]로 직접 디렉토리 골격을 만들고, package.json·Next.js 설정을 직접 작성한 뒤 `[engines:web_site]{op: "register"}`로 레지스트리에 등록하는 흐름이 더 유연합니다.

## web_component 상세

### op 종류 (catalog/fetch/add)

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
[engines:web_component]{op: "catalog", kind: "components", category: "form"}
```
category 옵션: `all`, `layout`, `form`, `data`, `feedback`, `navigation`, `overlay`

## 섹션 카테고리

### 사용 가능한 섹션 (`[engines:web_component]{op:"catalog", kind:"sections"}` 결과 일부)

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

## web {op:"preview"} 사용법

### action 종류

| action | 설명 |
|---|---|
| `start` | 개발 서버 시작 (기본) |
| `stop` | 실행 중인 서버 중지 |
| `status` | 서버 상태 확인 |

### 사용 예시
```
# 서버 시작 (기본 포트 3000)
[engines:web]{op: "preview", project_path: "/path", action: "start"}

# 다른 포트로 시작
[engines:web]{op: "preview", project_path: "/path", port: 3001}

# 서버 상태 확인
[engines:web]{op: "preview", project_path: "/path", action: "status"}

# 서버 중지
[engines:web]{op: "preview", project_path: "/path", action: "stop"}
```

실행 후 브라우저에서 `http://localhost:3000` 접속.

## 빌드 및 배포

### 빌드
```
[engines:web]{op: "build", project_path: "/path/to/project"}
```
실패 시: 에러 로그 분석 → 타입 에러/import 오류 수정 후 재빌드. 빌드 성공 전까지 배포 금지.

### 배포
```
# 프로덕션 배포
[engines:web]{op: "deploy", project_path: "/path/to/project", production: true}

# 프로젝트 이름 지정
[engines:web]{op: "deploy", project_path: "/path/to/project", production: true, project_name: "my-site"}
```

**배포 방식부터 확인한다 (사이트마다 다름):**
- git 연동 자동배포가 설정된 사이트면 `git push`만으로 반영된다.
- 아니면 vercel CLI 토큰 배포: 이 환경은 `vercel whoami`가 자격증명 없음으로 실패할 수 있지만, `$VERCEL_TOKEN`이 있고 프로젝트 폴더에 `.vercel/project.json`이 연결돼 있으면 토큰으로 배포된다.
```
run_command('cd {project_path} && vercel deploy --prod --yes --token="$VERCEL_TOKEN"')
```
`whoami` 실패만 보고 "배포 불가"로 판단하지 말 것 — 토큰 경로를 먼저 확인한다.

### 파이프라인
```
[engines:web]{op: "build", project_path: "/path"} >> [engines:web]{op: "deploy", project_path: "/path", production: true} >> [engines:web]{op: "check", site_id: "내-사이트"}
```

## 전체 워크플로우 예시

### 새 랜딩 페이지 만들기
```
1. [engines:web]{op: "create", target: "site", name: "my-landing", template: "landing"}
2. run_command('cd {path} && npx shadcn@latest add button card --yes')
3. [engines:web]{op: "create", target: "page", project_path: "...", page_name: "index", sections: [...]}
4. [self:read]/{self:edit}으로 globals.css의 CSS 변수 수정
5. [engines:web]{op: "preview", project_path: "...", action: "start"}  # 문제 발견 시 코드 수정 반복
6. [engines:web]{op: "build", project_path: "..."}  # 빌드 성공 전까지 배포 금지
7. [engines:web]{op: "deploy", project_path: "...", production: true}
8. [engines:web_site]{op: "register", name: "My Landing", local_path: "..."}
```

### 기존 사이트 수정하기
registry로 *위치*를 잡고(파일을 ls로 다시 찾지 말 것), 프로젝트 *안*은 둘러봐 구조를 안다.
```
1. [engines:web_site]{op: "list"}                      # 루트 경로·배포 URL 확보
2. [self:read]{path: ".../page.tsx"} + 관련 섹션 읽기    # 지금 페이지가 뭘 말하는지
3. [self:edit]{...}                                    # 목적에 맞게 수정
4. [engines:web]{op: "build", project_path: "..."}     # 빌드 성공 전 배포 금지
5. 이 사이트의 배포 방식대로 (git push 자동배포 또는 vercel CLI 토큰)
6. [engines:web]{op: "check", ...} + 배포 후 시각 검증(아래)
```
- *위치* 찾기는 registry로: ❌ `run_command('ls ~/Desktop/AI/HomePages/')` → ✅ `[engines:web_site]{op: "list"}`가 local_path를 알려줌.
- *구조* 파악(`[self:list]`로 src/components 둘러보기)은 정상이고 필요하다 — 무엇을 고칠지 알아야 하니까.

## 마이그레이션 노트 (2026-05-27)

기존 16종 액션 → 9종으로 정리. 옛 액션명은 모두 alias로 자동 정규화되므로 학습 데이터/외부 호출은 그대로 동작.

| 옛 액션 | 새 표기 |
|---|---|
| web_site_list/register/remove/update | `web_site {op}` |
| web_list_components / web_list_sections | `web_catalog {kind}` |
| web_create_site / web_create_page | `web_create {target}` |
| web_fetch_component / web_add_component | `web_component {op}` |
| web_edit_styles | `[engines:web]{op: "styles"}` (shadcn 테마/색상/반경 편집) |

---

## 이미지가 필요할 때 (생성 → public/ 저장 → 참조)

섹션 카탈로그에 `hero-image` · `image-text` · `hero-video`가 있지만, **그 이미지를 어디서 구하는지**는 위 매뉴얼이 말해주지 않습니다. 그래서 이미지 없이 텍스트만 채우거나, `public/`에 누가 미리 넣어둔 파일만 쓰게 되기 쉽습니다. indiebizOS에는 이미지 생성·검증 액션이 이미 있으니 연결해서 씁니다 (꼭 매번 생성하라는 뜻은 아님 — 적당한 실사진/소재가 있으면 그걸 우선).

**원칙**: `public/`에 적당한 이미지가 없으면 → 생성 → `public/`에 저장 → 코드에서 참조.

| 액션 | 용도 |
|---|---|
| `[engines:image_gemini]` | AI 이미지 생성 (Nano Banana 2). **`style_preset`을 사이트 톤과 통일**해 일관된 일러스트/배경/아이콘 생성 |
| `[engines:slide]` / `[engines:render_html]` | 도식·목업·다이어그램을 이미지(PNG)로 렌더 (HTML→PNG) |
| `[engines:image_critic]` | 생성된 이미지가 의도와 맞는지 1차 채점 (반환: passed / score / issues / notes) |

### 절차
```
1. [engines:image_gemini]{prompt: "...히어로 배경, 미니멀, 사이트 톤과 일관", style_preset: "<사이트 톤과 동일하게 통일>", output_path: "{project_path}/public/hero.png"}
2. [engines:image_critic]{path: "{project_path}/public/hero.png", intent: "히어로 배경으로 적합한가 / 톤 일관 / 텍스트 가독 방해 없음"}   # passed=false면 프롬프트 보정 후 재생성
3. 코드에서 /hero.png 로 참조 (Next.js는 public/ 루트가 / 경로)
```
- **style_preset은 사이트 전체에서 하나로 통일**한다 — 히어로·아이콘·배경이 제각각 톤이면 아마추어처럼 보인다.
- 생성물은 반드시 `image_critic`로 1차 채점하고 통과한 것만 임베드한다.

## 디자인 품질 체크리스트

`[engines:web]{op: "check"}`의 Lighthouse는 **성능·접근성·SEO 점수일 뿐 미적 품질을 측정하지 않는다.** 기준이 없으면 결과물이 shadcn 디폴트(파란 버튼·가운데 정렬 히어로)로 수렴한다. 페이지를 만들거나 고친 뒤 아래를 자가 점검한다.

- [ ] **시각 위계**: 가장 중요한 메시지(주 헤드라인·핵심 CTA)가 한눈에 가장 먼저 들어오는가. 크기·굵기·색 대비로 우선순위가 드러나는가.
- [ ] **여백(breathing room)**: 섹션 간 충분한 상하 패딩, 요소가 빽빽하지 않은가. 여백은 비용이 아니라 디자인이다.
- [ ] **폰트 2종 이내**: 본문/제목 합쳐 글꼴 2종 이내. 무분별한 폰트 혼용 금지.
- [ ] **primary 1색 절제**: 강조색(primary)은 1색으로, CTA·핵심 강조에만. 색을 남발하지 않는다 (globals.css `--primary`).
- [ ] **모바일 우선**: 좁은 화면에서 레이아웃이 깨지지 않는가. 데스크톱 먼저 만들고 모바일을 방치하지 않는다.
- [ ] **실제 제품/화면 임베드**: 가능하면 추상 일러스트보다 실제 제품·서비스 화면 스크린샷을 보여준다 (신뢰).
- [ ] **3초 기준선**: 랜딩이라면 첫 화면(above the fold)에서 "무엇을 하는 제품/서비스인지" 3초 안에 전달되는가.

## 배포 후 시각 검증 (필수)

⚠️ **HTTP 200 ≠ 내용 정확.** `check`의 `screenshot`은 스크린샷을 **찍기만 하고 읽지 않는다.** 캡처 파일이 생겼다고 "통과"로 처리하면, 옛 수치·깨진 이미지·잘못된 카피가 그대로 게시된다 (실제로 stale 숫자가 그대로 배포된 사고의 직접 원인). 아래 단계 **없이 "완료" 선언 금지.**

### 절차
```
1. (배포 전) [self:grep]{pattern: "<바뀌어야 할 옛 수치/카피>", path: "{project_path}/src"}
   # 옛 숫자·문구가 코드 어딘가에 남아있지 않은지 전수 색출. 남아있으면 먼저 고친다.
2. (배포 후) [engines:web]{op: "check", site_id: "my-site", checks: ["screenshot"]}
   # 또는 [engines:web]{op: "snapshot", site_id: "my-site"} 로 실제 배포 화면 캡처
3. [engines:image_read]{path: "<캡처된 스크린샷 경로>", question: "표시된 수치/핵심 카피/이미지/레이아웃이 의도대로인가? 옛 값이 남아있지 않은가?"}
   # Gemini Vision으로 스크린샷을 실제로 '읽어' 눈으로 확인 (시각 QA·OCR)
```
- 스크린샷은 **반드시 `image_read`로 판독**한다. 캡처만 하고 넘어가지 않는다.
- 수치·날짜·가격처럼 자주 바뀌는 값은 배포 전 `self:grep` 색출 + 배포 후 `image_read` 판독, 이중으로 확인한다.
- 위 1~3을 통과해야 "개선 완료"라고 보고한다.
