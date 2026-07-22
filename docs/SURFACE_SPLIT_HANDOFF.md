# 표면 분리 핸드오프 — 원격런처(PC의 일부) vs 폰네이티브(독립 시스템)

2026-07-22 세션 종료 시점. 몸 독립 소통 연구(docs/BODY_CARD_RESEARCH.md)의 다음
착수 과제.

## ✅ 구현 완료 (2026-07-22 후속 세션, 커밋 `4feb402`·`6d1ea80`)

- **1단계(모듈화, `4feb402`)**: launcher_web_app.py 1517줄 → 탭별 5모듈
  (launcher_app_common/warehouse/autopilot/manual/appmode) + launcher_web_shell.py 를
  조각 상수(머리·표면 탭줄·패널별·꼬리)로 분해. LAUNCHER_APP_JS·LAUNCHER_SHELL_HTML
  이름으로 원래 순서 재조립 — git HEAD 값 비교 + 라이브 /launcher/app sha1(84f1aec4)
  동일. setSurface·appHome·탭줄을 별도 상수로 둔 것이 폰 변형의 이음매.
- **2단계(표면 조립, `6d1ea80`)**: launcher_surface_remote(5탭 전판, 바이트 동일) /
  launcher_surface_phone(3탭 + PHONE_SURFACES/SETSURFACE/APPHOME 변형) 신설.
  phone_api /launcher/app → 폰 표면. /portal/warehouse-admin/* 4종 + _wh_proxy +
  _relay_raw 철거(남는 호출=catch-all census+404).
- **발견**: clip-to-mac 은 _forward_to_mac 경로 — _mac_proxy·_relay·_list_or_empty 는
  이제 **사용처 0**(아래 원문의 "clip-to-mac 정도" 가정은 실측과 다름). 매장은 인구조사
  확인 후 별도(열린 과제의 관문 dead code 매장과 같은 묶음).
- **조종실 폰-로컬 완결**: 원문 함정 항목("폰-로컬 번역 실측 필요")의 실측 결과 —
  /ibl/translate 는 폰에 **아예 없어** catch-all 404 였다(리모컨 은퇴 때 이미 끊김).
  phone_api 에 4 라우트 신설: translate(=body_ask._compile 재사용 — 해마 없는 몸이라
  사전-동봉 gemini-2.5-flash 경로, 소유-필터) / validate(정본 api_ibl.validate_ibl 직접
  재사용) / distill(정본 동형, 폰-로컬 ibl_distilled.json 축적) / actions/catalog(폰 번들
  사전 124 어휘 그대로). A36 실측: 번역 "수원 날씨"→`[sense:weather]{city:"수원"}` →
  검수 valid·read → 실행 실날씨 → 조종실 탭 실렌더(피어·기어·의식 토글 포함).
- **폰 재빌드·회귀 완료**: setup_phone.sh --build + force-stop 재기동. 폰 3탭 실기 확인
  (창고 탭 자체 없음·warehouse-admin 404 census·REMOTE 배지 숨김·자율주행 스위치 없음),
  원격런처는 라이브 sha1 84f1aec4 불변(회귀 0).
- **잔여**: IS_PHONE 런타임 분기(부트·클립 경로·자율주행 스위치 숨김)는 공통 조각에
  남아 폰 config(host=phone-local)로 작동 — 정적 흡수는 후속 후보.
  phone_proxy_census.jsonl 며칠 관찰 후 _mac_proxy·_relay·_list_or_empty 매장 판단.

이하 원문(조사·결정 기록).

## 원칙 (사용자 확정)

- 원격런처 = **PC의 일부**(맥의 얼굴·리모컨). 폰네이티브 = **독립된 다른 시스템**.
- 이쪽을 저쪽과 합쳐서 바꾸기 시작하면 안 됨 — 둘을 코드에서 **구분**하는 것이 핵심.
- 갈라야 할 선: **라이브러리는 공유 OK**(renderPrim·문서 틀 = 기질, IBL 엔진 공유와
  동급) / **표면 정의(어떤 탭이 존재하는가 = 정체)는 몸별 파일**.

## 현재 코드 상태 (조사 완료)

```
backend/launcher_web_shell.py   610줄  문서 틀·CSS          ← 공용 라이브러리로 유지
backend/launcher_web_app.py    1517줄  표면 JS(탭 정의·부팅·전 탭 로직) ← 분해 대상 (1500줄 규칙도 위반 중)
backend/launcher_web_render.py  965줄  renderPrim 뷰 렌더러  ← 공용 라이브러리로 유지
```
- `api_launcher_web.get_launcher_webapp_html()` = 세 문자열 이어붙임(바이트 동일 조립).
- 맥이 서빙 → 원격런처 / **폰도 같은 HTML 서빙**(phone_api:159 `_lw.get_launcher_webapp_html()`) → 폰네이티브 UI.
- 구분 = 깃발 하나: `IS_PHONE=(c.host==='phone-local')` (launcher_web_app.py:102).
- 탭 목록 하드코딩 공유: `['autopilot','manual','app','forage','warehouse']` (:318).
- 폰의 창고 탭 → phone_api 의 `/portal/warehouse-admin/*` 4종 프록시 + `_wh_proxy`(맥 관리 API 뒷문).

## 확정된 결정

1. **폰네이티브 탭 = 자율주행 · 수동(조종실) · 앱** 3개.
   - **조종실 유지는 사용자 강조**: "기억도 바꾸고 의식도 조절 — indiebizOS의 핵심."
   - 포식(forage) 제외(맥 디스크 중심), **창고 제외 확정**.
2. **창고 결론**(이 세션 후반 논의): 창고 = 숙주(맥) 몸의 살림 + 네트워크 얼굴(주소=정체,
   R2=지연캐시, 원본=맥 `공유창고/`). 폰네이티브는 창고 화면을 갖지 않는다 — 폰에서
   창고를 만지려면 **원격런처**(이미 기능 완비). 회원-쓰기 문 신설은 **불요 판정**(과잉
   설계 — 남과 공유=기존 회원 시스템/런처 부여로 충분).
3. **소비 원칙**(드롭박스 유비로 확정): 창고는 당김(pull)이 기본 — 매니페스트(목록)만
   자동, 내용물은 청할 때만 청한 자의 비용으로. 미러/오프라인 사본은 몸별 **옵트인
   구독**(한도·Wi-Fi 조건 자기 설정)이어야 하며 기본 동작이면 안 됨. 통화의 bytes 가
   몸별 소비 판단 재료(폰 LTE 경고 등).

## 작업 순서 (다음 세션)

1. **분해**: launcher_web_app.py → 탭별 모듈(공통부팅 / autopilot / manual / app /
   forage / warehouse). 원격런처는 매일 쓰는 표면 — **바이트-동일 조립 검증**으로
   회귀 0 보장하며 쪼갤 것(모듈화 커밋과 표면 변경 커밋을 분리).
2. **표면 조립 2개 신설**(정체의 거처):
   - 런처 표면(맥 서빙): 5탭 전부 그대로.
   - 폰 표면(phone_api 서빙): 3탭(자율주행·수동·앱) — IS_PHONE 분기들을 폰 표면
     쪽으로 흡수·소멸시킬 것.
3. **창고 프록시 철거**: phone_api 의 `/portal/warehouse-admin/*` 4종 + `_wh_proxy`
   + `_relay_raw`(창고 전용이면) 삭제. `_mac_proxy` 잔존 사용처 = clip-to-mac 정도
   (의도적 편의 — 사용자 판단 대상으로 남김).
4. 폰 재빌드(`setup_phone.sh --build` + force-stop→재기동) + 두 표면 회귀:
   원격런처 5탭 정상 / 폰 3탭 + 창고 404 없음(탭 자체가 없음) / 조종실 폰-로컬
   번역·실행 확인.

## 함정·가드

- **뷰-렌더러 가드**: build_ibl_nodes 가드가 `launcher_web_render.py` 경로를 스캔
  (APP_VIEW_TYPES p.type 케이스) — 파일 이동·개명 시 가드 경로 갱신 필요.
- Python-내-JS 정규식 함정(메모리 remote-launcher-design-polish): JS 문자열 안 `\\`.
- 폰 최신화 절차: `./phone-companion/scripts/setup_phone.sh --build` → force-stop →
  재기동(번들 재추출). adb forward tcp:8788 tcp:8765 로 검증.
- 조종실의 폰-로컬 번역: /ibl/translate 는 폰에서 system_ai_call→gemini_http(폰 AI
  config)로 돌 것 — 실측 확인 필요(안 되면 body_ask 의 해마-축 선례 참고).
- phone_proxy_census.jsonl(폰): catch-all 은퇴 자리에서 404 난 경로 적재 중 —
  표면 분리 후 이 파일을 열어 폰 UI 가 실제로 부딪힌 경로 확인(추가 로컬화 후보).

## 배경 (이 세션의 커밋들 — 상세는 docs/BODY_CARD_RESEARCH.md)

`dda7075` 명함·부탁·교환·인구조사 / `8a68753` 이전세션분 / `9f89d3a` 컴파일러 축=해마 /
`0f1dec4` others:ask+소유필터 / `aa2d2b3` here 지표어 / `7d1d3c5` see·listen 지표어 /
`6cb85ea` 사전 물리 분리 / 이후: 몸 신뢰 원장(이웃 통합)·폰 리모컨 은퇴(스위치 로컬화·
채팅 폴백 제거·catch-all 404) — 전부 main. 미커밋: media_producer/handler.py(아이콘
Gemini 수리 — 별도 백그라운드 태스크 소유).

## 열린 과제 (표면 분리 이후)

- 관문 자동-빌림 분기 매장(인구조사 며칠 0 확인 후 dead code 제거)
- 특권 실게이트(body_trust.PRIVILEGE_LEVELS — 코어 위임·동기화·해마 렌트를 원장 레벨로 집행)
- ask 푸시큐 폴백(LTE 폰 직결 불가 시 — 오늘 실제 발생)
- 신원 npub 서명화(device_id 자기보고 → 서명 검증) · 낯선 몸 부여 UI(소유주 승인)
- 재학습 코퍼스 몸별 분리(code_is_own 필터) · 윈도우 낯선-몸 실증 · 진열 층
