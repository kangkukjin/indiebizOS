# UI 국제화

한국어 소스가 정본이다. 데스크톱 React와 서버 생성 원격런처(`/launcher/app`)는 같은 카탈로그·번역 메모리·언어 저장 키를 사용한다. 각 브라우저/프로필에서 선택한 언어를 유지하고 Electron 창 사이에는 storage 이벤트로 동기화한다. UI 런타임은 네트워크 번역을 하지 않는다.

## 개발과 자동 갱신

기존 `npm run dev`와 `npm run build`에 Vite `uiCatalogPlugin`이 연결되어 있다. 시작/빌드 시, dev 소스 추가·변경·삭제 시 문구를 다시 수집한다. 문맥과 원문으로 메시지 ID를 만들고 `translations.json`에 동일 ID·원문인 번역이 있으면 그대로 재사용한다. 변경된 원문은 새 ID가 되므로 낡은 번역을 적용하지 않는다. 실패는 성공 번역으로 기록하지 않고 다음 실행에서 다시 시도하며 화면은 한국어로 사용할 수 있다.

번역은 `ui-translate.py`가 기존 `oneshot_ai_call(role="background")`을 이용한다. 모델과 키는 몸의 설정을 그대로 따른다. Python은 `INDIEBIZ_PYTHON`, 저장소 `.venv/bin/python3`, `python3` 순으로 선택한다. 격리 개발에서 설정이 다른 디렉터리에 있다면 기존 `INDIEBIZ_BASE_PATH` 설정을 이용한다. 선택적으로 `INDIEBIZ_TRANSLATE_URL`에 기존 texts/target → translations HTTP 프록시를 지정할 수 있다. 키·설정·사용자 데이터는 카탈로그에 복제하지 않는다.

## 번역 대상 선언과 안전 경계

React의 UI 위치(JSX·fragment 정적 텍스트, 직접 표시되는 문자열/템플릿·조건식, 네이티브 및 컴포넌트의 표시 속성)가 대상이다. TypeScript 바인딩으로 const 목록·사전·map/분해할당의 유한한 소스 문구를 표시 지점까지 추적한다. 등록과 변환은 .ts/.tsx 양쪽을 처리한다. 모르는 런타임 값은 이 추론으로 번역하지 않는다. alert/confirm/prompt와 동적 title/placeholder의 원문도 수집한다. 템플릿의 동적 값은 `{0}` 같은 자리로 분리하고 번역 서비스에 보내지 않는다. JSX 밖 UI 메타데이터는 `uiMessage(context, koreanSource)`로 명시하고 `<UiText id={...}/>`로 표시한다. `translate="no"` 또는 `data-ui-skip`은 하위 수집·표시를 제외한다. code/pre/textarea 본문과 런타임 변수, 채팅·프로젝트명·파일명·입력값은 번역하지 않는다.

원격 셸은 소스 HTML 텍스트/속성, 명시된 apCard UI 인자, 정적 HTML 조각 및 textContent 상태 문구를 컴파일러가 표시한다. 런타임에는 표시된 요소만 textContent/속성으로 갱신한다. 임의 DOM 텍스트와 런타임 데이터는 검사하거나 외부로 보내지 않는다. 번역은 실행 코드로 평가하지 않으며 스크립트 경계·HTML 경계를 각각 이스케이프한다. 원격 셸 원문 지문이 맞지 않거나 카탈로그가 깨지면 서버는 원래 한국어 셸을 제공한다. 원격 Python 수정 배포에는 frontend 빌드도 함께 수행한다.

모델기어·연결 상태는 시스템 표시 경계를 명시한다. API의 기어/축/티어 식별자, 프리셋 저장값과 사용자 에이전트/피어 이름은 바꾸지 않는다. 모델 설명은 ui-system-sources.py가 소스 코드에서 추출하며 해당 Python 소스 변경도 Vite watcher가 갱신한다. 기본 앱 이름은 내장 id와 원문이 모두 일치할 때만 번역하고, 같은 이름의 사용자 앱은 보존한다. 원격의 분할 HTML 속성 뒤에 붙는 문구도 수집한다.

IBL 사전의 description/target_description/ops/implementation은 소스 정의에서 수집해 표시할 때만 번역한다. API 응답과 실행 계약은 원문 그대로다. 코드 예시·명명된 템플릿 자리·메타데이터의 따옴표로 감싼 예시값은 마스킹 후 바이트 그대로 복원한다. 계기 매니페스트는 내장 id·원문 이름·필드 경로·원문 값이 모두 맞는 표시 사본만 번역한다. action/args/params/value/default 및 입력 키는 대상에서 제외한다. YAML 원문 변경도 개발 watcher가 재수집한다.

정적 검사는 등록 문구의 카탈로그 일치 및 미번역 0을 검사하며 모든 동적 UI의 등록을 증명하지 않는다. 원문 Markdown·프롬프트·코드·사용자 기록은 콘텐츠이므로 보존한다. 실행 중 서버가 새로 만드는 오류/상태 문구, 매니페스트 drill 상세·동적 옵션, 폰 독립 셸·OS 네이티브 창은 별도 실화면 검증이 필요하다. 검사 보고에 이 미검증 범위를 명시한다. 적용 후 검증은 data/system_ai_state/ui_release_verification.json에 명령·종료 코드·출력·완료 여부를 보존하며, 성공한 경우만 지정 경로를 정본 main에 커밋한다. 공통 런처 변경은 회원 셸(helper/member_app.html)과 폰 엔진 매니페스트를 모두 재생성·검사한다. --live-url 검사에서는 ui-live-check.py가 실제 원격 주소와 API에 접속해 영어 기어 버튼·현재 기어 재선택·한국어 복귀·언어 유지·동적 설정을 확인한다. 모의 API 브라우저 검사와 이 실제 서버 검사를 구분하며, Electron 창의 직접 확인은 별도다.

## 시스템 상태 표시

조종실의 점검 항목명·시스템 진단은 `UiSystemText`로 표시한다. `ui-system-sources.py`가 건강 점검과 설명 감사의 소스에서 `system:status` 문구·전체 템플릿을 수집하고 기존 카탈로그/번역 메모리를 재사용한다. 숫자·예외 본문·파일명·액션 식별자는 템플릿 자리의 원문으로 유지한다. 서버 응답·상태 판정·원장에는 번역을 쓰지 않는다. 등록되지 않은 진단 원문과 누락된 언어는 한국어 원문으로 폴백한다. 이 경계는 조종실의 시스템상태이며 별도 `/xray/app` 화면 전체의 국제화를 뜻하지 않는다.

`node --test scripts/ui-status.test.mjs`는 원천 수집·영어 완전성·일본어 테스트 등록·미번역 폴백·진단 값 보존을 검사한다. `ui-browser-check.py`는 실제 React 빌드의 상태 항목·제목·배지·서비스 표시, 영어/한국어 전환과 재열기·새 API 조회를 검사한다. 일본어는 테스트 전용 카탈로그와 공통 DOM 런타임에서 갱신/복귀를 확인하며, 전체 일본어 UI 출시는 아니다. API 데이터는 합성이므로 라이브 Electron 실창·실데이터 검증과 구분한다.

## X-Ray

`data/xray/index.html`도 같은 빌드·번역 메모리·언어 레지스트리에 연결한다. `ui-xray.mjs`는 이 명시된 UI 소스의 HTML/템플릿 표시 문자열을 수집한다. 객체 키·비교식·동적 값은 보존하며 문서 본문·사용자 요청을 번역하거나 외부로 보내지 않는다. `xray.json`은 생성물이며 직접 편집하지 않는다. 서버는 원문 지문이 일치하는 생성물만 제공한다.

포식 브라우저의 Electron webview는 별도 저장 영역이므로 진입 URL과 dom-ready/언어 변경 구독으로 선택 언어를 전달한다. 외부 사이트에는 주입하지 않는다. 웹 iframe은 검증된 부모 메시지로 갱신한다. X-Ray는 조회한 데이터를 다시 표시하여 현재 탭·선택 문서·열린 노드 상세를 유지한다. 독립 탭은 같은 저장 키를 사용한다. 추가 언어도 공통 레지스트리와 번역 메모리를 따른다.

`python -m pytest frontend/scripts/test_xray_ui.py`는 실제 라우트가 제공하는 생성 HTML을 Chromium에서 검사한다(업무 데이터는 합성). `node --test frontend/scripts/ui-xray.test.mjs`는 번역 경계와 네이티브 주입 주소 제한을 검사한다. 라이브 확인은 `XRAY_LIVE_URL`로 실제 서버 HTML과 검증 생성물의 일치까지 확인하며, Electron OS 실창 조작과 구분한다.

## 교정과 언어 추가

번역 공급자 오류가 나면 진행 중인 최대 3개 요청까지만 회수하고 남은 배치를 중단한다.
유효한 부분 번역은 메모리에 보존하지만 미번역이 하나라도 있으면 빌드는 종료 코드 1로
실패하며 마지막 정상 `catalog.json`·`remote.json`·`xray.json`은 덮어쓰지 않는다.
개발 서버의 재빌드 실패도 콘솔에 남기며 성공으로 새로고침하지 않는다.

격리된 적용 후 검사에서는 `INDIEBIZ_VERIFY_BASE_URL`이 제공된다. 검증 부모의 임시
읽기 통로는 `/health`·`/xray/app`만 전달하고 운영 API 직접 접근과 쓰기는 계속 차단한다.
환경 장애는 `failure_kind=environment`로 남기며 새 개발 모델 세션을 호출하지 않는다.
환경 복구 뒤 운영자는 `api_repair_continuation.retry_environment(task_id, base)`로
같은 파일 묶음의 실패한 검사만 한 번 재예약할 수 있다. 바뀐 파일·불확실한 실행·시간
초과는 재예약하지 않으며 기존 검사 영수증도 보존한다.

`translations.json`의 해당 언어·ID 레코드에서 text만 교정한다. source를 바꾸지 않으면 이후 빌드가 유효한 교정을 보존한다. 자리표시자 개수·번호와 원문의 코드 마커는 원문과 같아야 한다. 번역 배치 실행 도중 디스크에서 수정된 레코드도 체크포인트에서 병합하여 수동 교정을 보존한다. 조사가 다른 언어에서 생략되어야 하는 등 사람이 확인한 빈 번역은 text를 빈 문자열로 두고 reviewed:true를 지정하면 보존한다. 번역 실패·한국어 잔여·마크업은 검증에서 거절한다. 생성물 `catalog.json`, `remote.json`은 직접 고치지 않는다. 번역 메모리를 포함한 세 JSON은 배포와 함께 버전 관리한다.

`languages.json`에 `"ja":"日本語"` 또는 `"zh-CN":"简体中文"`을 추가하면 다음 dev/build에서 같은 경로로 해당 언어 번역을 생성하고 두 표면의 선택기에 자동 추가한다. 화면별 구현은 필요 없다. 신규 언어의 번역 품질 검토는 별도다.

## 검사

- `node --test scripts/ui-i18n.test.mjs`: 대상 경계·변수·번역 메모리·실패 폴백·선택 유지.
- `node scripts/ui-source-check.mjs`: 전체 React 변환 구문 및 생성 원격 JS 구문.
- `npx tsc -p tsconfig.app.json` 및 `npm run build`: 실제 타입 검사와 자동 갱신/산출.
- Python으로 `scripts/ui-server-check.py`: 원격 서버 소비·낡음/손상 폴백.
- Playwright 설치 Python으로 `scripts/ui-browser-check.py`: 실제 빌드 산출물 양쪽 표면의 전환·재접속·콘텐츠 보존·변경 문구 표시. API 업무 데이터만 모의하며 번역은 실제 생성본을 사용한다.
