# 웹앱 짓기 (webapp) — 하우스 레시피

웹앱을 만들라는 요청을 받으면 **기초부터 재발명하지 않는다** — 이 시스템에는 이미 검증된 선례·이음매·규약이 있다. 이 가이드는 그 결정화다. 홈페이지(Next.js+Vercel)는 별도 가이드(`web_builder.md`)를 따른다.

웹앱이 강력한 이유: 브라우저는 모든 하드웨어에 이미 깔린 유일한 범용 런타임이다. 만들면 ①다른 하드웨어에서 쓰고 남에게 줄 수 있고 ②PWA로 일반앱처럼 설치되고 ③파일 업/다운로드 등 그 하드웨어를 제한적으로 쓰고 ④중앙(맥 백엔드)에서 업데이트된다. **분할선: 웹앱=표면(진열·대여·리모컨) / 네이티브=몸(자아·셸·상주)** — 브라우저 샌드박스를 넘어야 할 때만 몸(guest-helper·폰 네이티브)을 만든다.

## 0. 결정 트리 — 이 웹앱은 어디 사나

| 부류 | 판단 기준 | 선례 |
|------|-----------|------|
| **A. 몸 공개면** | 내 라이브 데이터·회원·익명 방문이 필요 | 포털 `/h/`, 게시판 `/b/`, 가족신문 `/n/`, 공개파일 `/s/`, 정기보고 `/r/` |
| **B. 포털 계기 대여** | 이미 IBL 계기(app: 블록)로 있는 기능을 브라우저로 빌려주기 | 포털의 🎨아이콘·🎵유튜브뮤직·날씨 — **신규 코드 0** |
| **C. 외부 서버리스** | 맥이 꺼져도 살아야 하는 독립 앱 | kospi-board(Cloudflare Worker, `outputs/web-projects/`) |
| **D. 단일 HTML 자족 문서** | 받아가서 열어도 살아야 함(오프라인·재배포) | 창고 카탈로그(사진 data URI 임베드, `warehouse_catalog.py`) |

순서대로 묻는다: 이미 계기로 있나? → B(가장 싸다). 내 라이브 데이터가 필요한가? → A. 맥 독립 상시가 필요한가? → C. 문서 하나로 돌아다녀야 하나? → D.

## 1. A 레시피 — 몸 공개면 한 벌 신설

3층 이음매: **브라우저 → Cloudflare Worker → 터널 → 맥 백엔드**. 새 면 하나 = 아래 다섯 조각.

1. **네임스페이스 예약**: `/<한글자>/<5자 슬러그>/` — 기존 `/s/ /n/ /b/ /h/ /r/` 과 충돌 금지.
2. **맥 서빙**: `backend/api_<이름>.py` 신설 + `X-Showcase-Secret` 게이트(공개파일과 공유 시크릿, 익명 직접 접근 차단) + `api.py` include. 상태 저장은 `data/<이름>/state.json`(flock append — bulletin 선례).
3. **공개 경로 등록**: `api_launcher_web.is_public_remote_path` 에 추가(자체 게이트 보유 경로만). 미등록 = 외부 익명 401(관리자 전용 경로는 의도적으로 미등록).
4. **Worker 분기**: `public-files` worker.js 에 라우트 추가 + **캐시 판단표** — 쿠키·개인화·실시간·글쓰기 면 = `no-store`(포털 `/h/`·게시판 선례, no-cache 는 엣지 stale) / 불변 판·미디어 = R2 지연 캐시(생성시각 `?v=` 로 캐시 오염 방지, 가족신문 선례). 재배포 = `cdn_provision.provision_cdn`(같은 이름·같은 오리진이면 주소 불변).
5. **익명 쓰기 방어 5종**(방문자가 쓰는 면이면): 이미지 PIL 재인코딩=EXIF/GPS 전부 제거+1600px 다운스케일 / 매직바이트 검사 / IP 간격 429 / 허니팟 필드 / 글자수 상한. (family-news·bulletin 배관 재사용)

## 2. PWA — 설치형으로 만들기

3종 세트: **manifest.webmanifest**(이름·아이콘·`display:standalone`·★`scope` 는 좁게: `/launcher/`·`/nas/` 처럼 자기 경로만) + **서비스워커**(빈 fetch 핸들러 = 설치 판정용. **캐시하지 않는다** — 개인화·실시간 표면은 캐싱이 곧 버그) + **아이콘** 192/512/maskable + apple 메타 태그. 셋 다 **로그인보다 먼저** 읽히도록 공개 경로 등록(설치 판단이 로그인보다 먼저). 선례 = 원격런처(`api_launcher_web.py` "홈 화면 설치" 절)·IBFind(`api_nas.py` finder_manifest).

★**함정(2026-08-01 실증)**: 같은 origin 에 PWA 가 여러 개면(런처+IBFind) 안드로이드가 **알림 권한을 origin 단위로 WebAPK 하나에 위임**해 다른 PWA 의 알림이 얽힌다 — 설정을 다 켜도 안 울릴 수 있다. 알림이 중요한 앱은 **서브도메인 분리(origin 독점)를 먼저 설계**할 것. (웹푸시 자체는 이 함정으로 은퇴 — 재시도 금지, `notify_dispatch.py` 헤더 참조)

## 3. 하우스 규약 (어느 부류든)

- **Python-내-JS**: 백슬래시 0(정규식 이스케이프 금지 — `\d` 부류가 파이썬 문자열에서 먹힌다), 경로·따옴표는 jsEsc(NAS 파인더 선례). 검증 = 조립 HTML 에서 `<script>` 추출 → `node --check`.
- **첫 조회 재시도**: 콜드스타트(8765 바인딩 전) 첫 fetch 실패 부류 — 네트워크 거부만 재시도, 4xx 는 즉시 표시.
- **인증 3패턴 중 택1**: 런처 세션 쿠키(내 기기) / 회원 아이디+비번 pbkdf2+레벨(포털 선례) / 키 자체 인증(limb key·session_token — USB·NAS 선례). 새 인증 방식을 발명하지 않는다.
- **자기교착 금지**: 이벤트 루프에서 자기 공개 주소로 동기 HTTP 금지(요청이 Worker→터널로 되돌아오는데 루프가 막혀 못 받음) — `anyio.to_thread` 로 내린다.
- **대용량 미디어**: Range 206 + 스트리밍(인프로세스 프록시는 전체 버퍼링 — 루프백 HTTP 로).
- **이식성**: fcntl 금지(무-flock 원자쓰기 = threading.RLock + os.replace), `/tmp` 금지(gettempdir) — 윈도우 게이트가 잡는다.

## 4. C 레시피 — 외부 서버리스

- **Cloudflare Worker**: `outputs/web-projects/<이름>/` 에 worker.js+wrangler.toml (선례 kospi-board). 라이브 데이터가 필요해지면 그건 A 부류 신호다(맥 API 프록시) — Worker 안에 데이터를 박제하지 않는다(박제 데이터=조용히 썩는다).
- **Next.js/Vercel**: `web_builder.md` + `[engines:web]` 가 정본.

## 5. 완성 의무 — 만들었으면 등기한다

1. **등기부 등록**: `[self:webapp]{op:"register", name, url, kind, memo}` — 단, 몸 공개면(포털·게시판·신문·공개파일·보고서·런처·NAS)과 web-builder 사이트는 **자동 파생**되므로 등록 불필요. 등록이 필요한 건 그 밖(외부 Worker·수제 배포)뿐. `[self:webapp]{op:"status"}` 로 전 함대 생존 확인.
2. **검증 체크리스트**: 실브라우저 렌더+콘솔 무에러 / 공개 종단(외부 URL 로) / 형제 면 회귀(`/s/ /n/ /h/` 200) / 방문자 쓰기 면이면 EXIF 제거·429 실측 / 폰 실기.

## 실측 기록 (자동 누적)

> 실행 에이전트가 턴 종료 후 덧붙인다.
- 2026-08-19 실측: 단일 HTML 자족 문서(D 부류)는 새 Worker·새 공개면 없이 `공유창고/<레벨>/`에 파일 하나로 넣으면 기존 공개면 배관이 그대로 `/f?path=<파일명>` 공개 주소를 내준다 — 서버 상태 0인 웹앱의 최단 배포 경로(레벨 0=손님 공개).
- 2026-08-20 실측(다이어리 PWA): **설치형+완전오프라인 PWA 는 D 부류(공유창고 `/f?path=`)로 못 만든다** — 서비스워커 스크립트 URL 의 *경로*가 `/f`(파일명은 쿼리)라 스코프가 `/` 로 잡히고, 그 origin 의 다른 앱(포털·게시판)까지 삼킨다. 게다가 같은 origin 다중 PWA = 알림 위임 얽힘(2026-08-01 함정). → **자기 데이터가 전부 클라이언트에 있는 앱은 C 부류(전용 Worker)가 정답**: `outputs/web-projects/<이름>/` + `wrangler.toml` 에 `main` 없이 `[assets] directory="./public"` 만 두면 정적자산 Worker 로 배포되고 자체 origin·자체 스코프를 얻는다(`npx wrangler deploy`, .env 의 CLOUDFLARE_API_TOKEN/ACCOUNT_ID 로 인증).
- 2026-08-20 실측(서비스워커 함정): **Cloudflare 정적자산은 `/index.html` 을 307 로 `/` 에 넘긴다.** 이걸 모르고 precache 목록에 `/index.html` 을 넣으면 *리다이렉트된 응답*이 캐시에 들어가고, navigate 요청(redirect mode=manual)에 그걸 돌려주는 순간 브라우저가 network error 를 내 **오프라인에서 앱이 안 뜬다**. 앱 껍데기는 `/` 하나로만 다루고, 배경 갱신 때도 `res.redirected` 를 확인해 넣을 것. 검증은 `caches.match('/')` 의 `redirected === false`.
- 2026-08-20 실측(오프라인 검증법): 헤드리스 브라우저 IBL 액션엔 네트워크 차단 op 이 없다 — **Playwright 를 직접 몰아 `context.set_offline(True)` 후 reload** 하면 진짜 비행기 모드 등가 검증이 된다(`.venv/bin/python` + `PLAYWRIGHT_BROWSERS_PATH=ms-playwright`). 설치 가능 여부는 CDP `Page.getAppManifest` 로 브라우저에게 직접 물어 `errors` 가 빈 배열인지 본다(육안 추정 금지).
- 2026-08-20 실측(연락처): 안드로이드 폰 연락처 직접 읽기는 **Contact Picker API**(`navigator.contacts.select`, 안드 Chrome 전용·사용자 제스처 필요)로 가능하다 — 다만 기능 감지 후 **.vcf 임포트 폴백 필수**. 폰이 내보내는 .vcf 는 대개 **vCard 2.1 + QUOTED-PRINTABLE** 이라 QP 디코드(소프트 줄바꿈 `=` 이어붙이기 포함) 없이는 한글 이름이 전부 깨진다.
