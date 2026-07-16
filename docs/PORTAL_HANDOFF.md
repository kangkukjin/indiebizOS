# 개인 포털(커뮤니티 홈) 핸드오프 — 2026-07-16 설계 확정 → **같은 날 구현 완료**

> **구현 상태(2026-07-16 저녁)**: 조각 ①~④ 전부 구현·맥 로컬 종단 검증 완료. 포털 주소
> `/h/BZVAB/`, 진열 켜짐=icon·ytmusic·news:FCLKR·weather(손님 3/일). 검증 배터리 §4 중
> 2~4·7·8·9 통과(로컬), 1 통과(build --check + /s/·/n/ 회귀).
> **Worker 배포 완료(같은 날)**: `/h/BZVAB/` 공개 라이브. 공개 인터넷 종단 검증 —
> 가입→302+쿠키→회원 절단면→승급→계기 실행→**오디오 프록시**(`/h/<슬러그>/tune/<vid>`,
> googlevideo 맥-IP 잠금 해소=외부망 재생, Range 206, 쿠키 없음 403)·`/s/`·`/n/` 회귀 무손상.
> **⏳남은 것**: §4-5 아내 실기(아이콘 꾹눌러복사→카톡)·§4-6 폰 실기(음악 소리). 커밋·재학습 대기열.
> 상세는 `data/guides/portal.md` + community-portal 패키지 guide.md.

다음 세션 구현용. 설계 대화 전체의 수렴본. 전략 배경은 메모리
`strategy_one_node_per_community.md` ("커뮤니티당 노드 하나 · 카페 마이너스 네이버").

## 0. 한 문장

**가입을 받는 공개 홈(`/h/<슬러그>/`)** 을 만들어 이웃을 수집하고, 이웃의 **레벨에 따라**
콘텐츠(신문·공개파일)와 **계기(아이콘·유튜브뮤직·조회형 앱)를 원격으로 쓰게** 한다.
아내가 사용자 1호(🎨 아이콘 계기) — indiebizOS 설치 없이 남편 노드의 능력을 빌려 쓰는 첫 사례.

> **★3차 개정(2026-07-16 저녁, 사용자 설계 수정 — 아래 "확정 설계" 중 2개 항목 대체)**:
> ① **포털=여러 개** — 대상별 주소(가족용·친구용)가 각자 첫페이지 진열·회원 명부를 소유
> (§1-1의 단일 주소 전제 대체). ② **가입/로그인=아이디+비밀번호(네이버식, 자동 로그인)** —
> §1-2·3의 "개인 링크=유일한 로그인" 대체. 개인 링크는 운영자 발급 즉시 로그인 열쇠
> = **비밀번호 분실 복구 경로**로 재정위. 상세=data/guides/portal.md.

## 1. 확정 설계 (대화에서 합의된 것 — 바꾸지 말 것)

1. **홈 주소 = 완전 공개 가능** (`/h/<5자 슬러그>/`, 바스켓 slug 발급 패턴 재사용).
   손님(레벨 0) 화면: 커뮤니티 소개 + 공개 타일 + **가입 신청 폼**.
2. **가입 신청 = 레벨 0 자동 등록** (승인 대기열 없음 — 레벨 0은 공개층뿐이라 무위험,
   **승급 행위가 곧 승인**). 등록 시 개인 링크 자동 발급.
3. **개인 링크 = 열쇠 = 로그인** (`/h/<슬러그>/k/<회원키>` 클릭 → 장수 쿠키 → 홈으로 리다이렉트).
   비밀번호 없음. 분실=재발급, 유출=그 사람 것만 회수(revoke). 로그인 화면이라는 것이 존재하지 않음.
4. **계기·콘텐츠마다 다이얼 하나**: `{min_level, 손님 한도, 회원 한도}`. 운영자 설정.
   - 기본값은 **노드에서 유도**: `sense`(조회형)=레벨 1 후보 / `engines`(비용 발생)=회원+한도 /
     `self`·`limbs`·`others`=진열 목록 밖. ★이름으로 넘겨짚지 말 것 — CCTV는 이름과 달리
     공공 교통 CCTV 조회(sense)라 **레벨 0 적합**이었음(오분류 교훈).
   - 무료 조회 계기(날씨·도서·CCTV·맛집·문화·숙소·여행·실거래가·상권·길찾기·사업공고)는
     레벨 0(로그인 전)도 사용 가능 — **공개층의 콘텐츠=획득 표면**. 단 빡빡한 한도.
   - 크롤형(직방·당근·여기어때 등 `source` 크롤)은 **레벨 1+** — 남용 시 대상 사이트가
     집 IP를 차단(= "팔의 평판" 손실)하므로 손님에게 안 연다.
5. **절대금지군은 다이얼 자체가 없음** (진열 가능 목록 밖, UI로 못 엶 — 공급망 게이트 철학):
   사진·메신저·비즈니스(타인 개인정보)·파일·시스템(host)·일정·정기보고·오디오브리핑·즐겨찾기·
   개인 신문 편집기·showcase/family_news **관리 계기**(폴더 토글·발행 버튼!)·IndieNet(아버지 명의
   발신)·android/computer-use 등 몸 제어 전부. 회원에게 가는 건 산출물 링크(`/s/`,`/n/`)뿐.
6. **회원 실행 게이트 — 범용 `/ibl/execute` 직결 금지.** 계기의 `app:` 블록 선언이 곧 권한 경계:
   화이트리스트에 오른 계기의 선언된 모드·버튼·폼이 만드는 액션만 조립·실행(앱 모드
   매니페스트-구동과 같은 원리). + 회원별 사용량 한도 + 감사로그(누가·언제·뭘).
7. **첫 회원 계기 2개**:
   - 🎨 아이콘: 맥에서 생성→이미지 반환. ★클립보드 자동복사 불가(그건 폰 네이티브 Kotlin 경로)
     → "꾹 눌러 복사" 안내 문구. ★비용 ~93원/장(gemini image) → 회원별 일일 한도(예: 20장).
   - 🎵 유튜브뮤직: ★**브라우저 재생판만**(원격판 native `<audio>` 스트리밍 — 이미 존재).
     데스크탑 모드는 ffplay=**맥 스피커에서 소리 남** — 절대 노출 금지. 회원 전용(익명 공개
     스트리밍=유튜브 공개 프록시가 되므로).
8. **콘텐츠 타일**: 가족신문(`/n/FCLKR/`), 공개파일 바스켓(`/s/…`)을 레벨별로 진열
   (이웃 레벨=열람 등급). 신문·바스켓 자체는 무변경 — 홈은 개인화된 색인일 뿐.
9. **운영자 관리면 = 앱 모드 "포털" 계기**: 이웃 탭(신청 확인·레벨 승급·링크 재발급·회수) /
   진열 탭(계기·콘텐츠 다이얼) / 기록 탭(감사로그). 선언형 계기로 짓는다.

## 2. 구현 조각 (권장 순서)

### ① 상태 + 어휘 `[others:portal]` (신규 패키지 `community-portal/`)
- `data/portal_state.json`: `{slug, title, intro, members[], display{}, settings}`
  - member: `{id, name, contact, level, key(긴 랜덤), joined_at, revoked, usage{tool: {date: n}}}`
  - display: `{인스트루먼트id|콘텐츠id: {min_level, guest_daily, member_daily}}`
- ops: `status / members / promote(member_id, level) / issue(재발급) / revoke / join(내부용) /
  display(다이얼 설정) / audit / config(title·intro)`
- app: 블록 = "포털" 관리 계기 3탭 (★form은 `fields` 필수 — family_news 교훈. 드릴 form 대신
  card_list+list_action 조합 패턴 재사용).
- 진열 가능 목록: `build 시 노드로 유도한 기본 display` 를 생성하는 헬퍼 — self/limbs/others 계기는
  목록에 아예 안 들어감(설정 파일 수동 편집으로만 추가 가능).

### ② 맥 서빙 `backend/api_portal.py`
- `GET /portal/page/{slug}?path=` — 홈 렌더(쿠키의 회원키 → 레벨 판정 → 그 레벨 타일만).
  손님/회원이 같은 홈의 다른 절단면. HTML 렌더러는 패키지 `portal_html.py`(가족신문
  `newspaper_html.py` 선례 — 디자인 단일 소스, api가 importlib).
- `GET /portal/key/{slug}/{memberkey}` — 쿠키 심고 홈으로 리다이렉트(개인 링크 착지).
- `POST /portal/join/{slug}` — 가입 신청(이름·연락처, 길이 캡+IP 간격 제한 — 방명록 패턴)
  → 레벨 0 member 생성+개인 링크 반환(화면 표시 "이 링크를 저장하세요"+운영자에게 알림).
- `POST /portal/tool/{slug}/{instrument}` — **회원 실행 게이트**: 쿠키→회원·레벨 확인 →
  display 다이얼 확인 → 한도 확인 → `app:` 선언에서 액션 조립 → 실행 → 결과 반환 + 감사로그.
- `GET /portal/inst/{slug}/{instrument}` — 계기 페이지(제네릭 HTML 렌더러 재사용.
  ★api_launcher_web 렌더러는 dispatch 를 런처 엔드포인트로 쏘므로 **dispatch URL 주입
  파라미터**가 필요 — 렌더러 포크 금지, 매개변수화할 것).
- 시크릿 게이트: Worker 경유 전 경로 `X-Showcase-Secret`(showcase/family-news 패턴 그대로).
- `api.py` 라우터 등록 + `api_launcher_web.is_public_remote_path` 에 `/portal/` (GET+POST) 등록.

### ③ Worker `/h/` 네임스페이스 (public-files/site/worker.js — `/n/` 블록 옆에)
- `/h/<slug>/…` → 맥 `/portal/…` 프록시. **HTML·tool 응답은 no-cache**(개인화라 캐시 금지!),
  정적 자산 없음(스타일 인라인). Cookie 헤더 왕복 전달 필수. `CF-Connecting-IP`→`X-Client-Ip`.
- 배포: `cd data/packages/installed/tools/public-files/site && CLOUDFLARE_API_TOKEN=… npx wrangler@4 deploy`
  (.env 에 토큰·계정 있음). 배포 후 `/s/`·`/n/` 회귀 curl.

### ④ 첫 계기 배선
- 아이콘: `[engines:icon]` 은 `prompt_hidden`+`runs_on: anywhere` — 게이트에서 직접 호출.
  반환 blocks 의 data URI 를 계기 페이지에 렌더 + "꾹 눌러 복사" 안내.
- 유튜브뮤직: 원격판 스트리밍 경로 확인 후 회원 게이트 뒤로. (원격 런처의 native audio 재사용)

### ⑤ 후속 (어휘 변경 의무)
- build --check 삼각 → `/packages/reload` + **백엔드 수동 재시작**(api_portal.py 는 backend 모듈)
- 해마 시딩 `add_examples_batch(source='manual_seed')` (★rebuild_usage_db.py 금지)
  + ibl_distilled 누적 + `rebuild_index()`
- guide: `data/guides/portal.md` + guide_db 등록 + 패키지 guide.md
- CLAUDE.md 마지막 업데이트 갱신, 메모리 갱신

## 3. 함정 (이번 세션 실측 교훈 포함)

- **백엔드 재시작 vs /packages/reload**: backend/*.py=수동 재시작, 패키지 handler=/packages/reload.
  새 액션은 reload 해야 레지스트리에 등장(가족신문 때 실측).
- **app form 은 fields 필수** — 빈 fields 는 build --check 거부. 버튼만 필요하면 list_action.
- **card_list 에 섹션 제목 없음** — 카드 title 에 라벨을 넣을 것.
- **geo/외부 API 캐시에 실패 빈값 저장 금지** (가족신문 교훈 — 포털 한도 카운터도 동일 주의).
- **공개 페이지 JS 는 encodeURIComponent** — curl 비인코딩 한글 쿼리는 "Invalid HTTP request"
  (제품 버그 아님, 테스트 시 주의).
- **Worker 에서 개인화 HTML 캐시 절대 금지** — `/n/` 은 무상태라 안전했지만 `/h/` 는 쿠키 개인화.
- **한도는 이중**: 회원별(감사로그 겸) + 손님 IP별 + 계기별 일일 전역 캡(키 쿼터 보호).
- 아이콘 클립보드: 폰 네이티브에서만 자동복사 — 브라우저는 수동(길게 누르기).
- 테스트 시 라이브 백엔드와 fresh-process 로 같은 상태 파일 동시 쓰기 금지(showcase 교훈).

## 4. 검증 배터리 (구현 완료 판정)

1. build --check 전 가드 + `/s/`·`/n/` 회귀 무손상
2. 손님: `/h/<slug>/` 공개 홈 렌더(공개 타일만) + 무료 계기 사용(날씨 등) + 한도 초과 429
3. 가입: 신청 → 레벨 0 등록 + 개인 링크 발급 → 운영자 "포털" 계기에 신청자 표시
4. 승급: 레벨 1 승급 → 개인 링크 클릭(쿠키) → 회원 타일 등장
5. **아이콘 e2e (사용자 1호=아내 실기)**: 아내 폰 브라우저 → 아이디어 입력 → 이미지 →
   꾹 눌러 복사 → 카톡 붙여넣기. 일일 한도 동작.
6. 유튜브뮤직: 회원 폰 브라우저에서 검색→재생(소리가 **그 폰에서**, 맥 스피커 아님 확인)
7. 회수: revoke 후 옛 링크·쿠키 무효 확인
8. 감사로그: 누가·언제·뭘 이 기록됨
9. 미리보기/관리 경로 터널 차단(401) — 사적 계기가 `/h/` 어디서도 안 보임 확인
