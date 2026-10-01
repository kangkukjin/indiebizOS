# UI 국제화

한국어 소스가 정본이다. 데스크톱 React와 서버 생성 원격런처(`/launcher/app`)는 같은 카탈로그·번역 메모리·언어 저장 키를 사용한다. 각 브라우저/프로필에서 선택한 언어를 유지하고 Electron 창 사이에는 storage 이벤트로 동기화한다. UI 런타임은 네트워크 번역을 하지 않는다.

## 개발과 자동 갱신

기존 `npm run dev`와 `npm run build`에 Vite `uiCatalogPlugin`이 연결되어 있다. 시작/빌드 시, dev 소스 추가·변경·삭제 시 문구를 다시 수집한다. 문맥과 원문으로 메시지 ID를 만들고 `translations.json`에 동일 ID·원문인 번역이 있으면 그대로 재사용한다. 변경된 원문은 새 ID가 되므로 낡은 번역을 적용하지 않는다. 실패는 성공 번역으로 기록하지 않고 다음 실행에서 다시 시도하며 화면은 한국어로 사용할 수 있다.

번역은 `ui-translate.py`가 기존 `oneshot_ai_call(role="background")`을 이용한다. 모델과 키는 몸의 설정을 그대로 따른다. Python은 `INDIEBIZ_PYTHON`, 저장소 `.venv/bin/python3`, `python3` 순으로 선택한다. 격리 개발에서 설정이 다른 디렉터리에 있다면 기존 `INDIEBIZ_BASE_PATH` 설정을 이용한다. 선택적으로 `INDIEBIZ_TRANSLATE_URL`에 기존 texts/target → translations HTTP 프록시를 지정할 수 있다. 키·설정·사용자 데이터는 카탈로그에 복제하지 않는다.

## 번역 대상 선언과 안전 경계

React의 UI 위치(JSX 정적 텍스트, 직접 표시되는 문자열/템플릿·조건식, 네이티브 title/placeholder/aria-label/alt)가 대상이다. 템플릿의 동적 값은 `{0}` 같은 자리로 분리하고 번역 서비스에 보내지 않는다. JSX 밖 UI 메타데이터는 `uiMessage(context, koreanSource)`로 명시하고 `<UiText id={...}/>`로 표시한다. `translate="no"` 또는 `data-ui-skip`은 하위 수집·표시를 제외한다. code/pre/textarea 본문과 런타임 변수, 채팅·프로젝트명·파일명·입력값은 번역하지 않는다.

원격 셸은 소스 HTML 텍스트/속성, 명시된 apCard UI 인자, 정적 HTML 조각 및 textContent 상태 문구를 컴파일러가 표시한다. 런타임에는 표시된 요소만 textContent/속성으로 갱신한다. 임의 DOM 텍스트와 런타임 데이터는 검사하거나 외부로 보내지 않는다. 번역은 실행 코드로 평가하지 않으며 스크립트 경계·HTML 경계를 각각 이스케이프한다. 원격 셸 원문 지문이 맞지 않거나 카탈로그가 깨지면 서버는 원래 한국어 셸을 제공한다. 원격 Python 수정 배포에는 frontend 빌드도 함께 수행한다.

아직 등록하지 않은 JSX 밖 메타데이터, 복잡한 문자열 연결, 서버/API에서 오는 상태·계기 설명은 자동 번역 범위 밖이다. 사용자 콘텐츠인지 UI인지 판단 없이 모든 문자열을 번역하지 않는다. 필요한 UI 메타데이터는 같은 등록 경계로 편입한다. 폰 독립 네이티브 셸과 OS 네이티브 대화상자는 이번 적용 대상이 아니다.

## 교정과 언어 추가

`translations.json`의 해당 언어·ID 레코드에서 text만 교정한다. source를 바꾸지 않으면 이후 빌드가 유효한 교정을 보존한다. 자리표시자 개수·번호는 원문과 같아야 한다. 조사가 다른 언어에서 생략되어야 하는 등 사람이 확인한 빈 번역은 text를 빈 문자열로 두고 reviewed:true를 지정하면 보존한다. 번역 실패·한국어 잔여·마크업은 검증에서 거절한다. 생성물 `catalog.json`, `remote.json`은 직접 고치지 않는다. 번역 메모리를 포함한 세 JSON은 배포와 함께 버전 관리한다.

`languages.json`에 `"ja":"日本語"` 또는 `"zh-CN":"简体中文"`을 추가하면 다음 dev/build에서 같은 경로로 해당 언어 번역을 생성하고 두 표면의 선택기에 자동 추가한다. 화면별 구현은 필요 없다. 신규 언어의 번역 품질 검토는 별도다.

## 검사

- `node --test scripts/ui-i18n.test.mjs`: 대상 경계·변수·번역 메모리·실패 폴백·선택 유지.
- `node scripts/ui-source-check.mjs`: 전체 React 변환 구문 및 생성 원격 JS 구문.
- `npx tsc -p tsconfig.app.json` 및 `npm run build`: 실제 타입 검사와 자동 갱신/산출.
- Python으로 `scripts/ui-server-check.py`: 원격 서버 소비·낡음/손상 폴백.
- Playwright 설치 Python으로 `scripts/ui-browser-check.py`: 실제 빌드 산출물 양쪽 표면의 전환·재접속·콘텐츠 보존·변경 문구 표시. API 업무 데이터만 모의하며 번역은 실제 생성본을 사용한다.
