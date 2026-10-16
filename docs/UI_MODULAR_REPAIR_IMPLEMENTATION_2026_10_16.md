# 화면 수리 이행 표

상태: 닫힌 범위의 코드 구현과 자동 검증, Android 두 앱의 실제 표시 교체 검사를 마쳤다. 운영 서명 피드 배포와 Windows 실제 설치 인수는 미실행이다. 기준 정본 `51ca80f7`. 이 표는 계획서 0단계의 완료 집합이며 구현 검증과 전체 배포 인수를 구분한다. 범위 추가·제외는 이유와 검사 영향을 이 문서에 먼저 기록한다.

## 확정한 경계

원본은 `frontend/surfaces/`와 기존 React `frontend/src/`, 공용 렌더 코어는 기존 `backend/static/app_render_core.js`다. HTML 표면의 Python 파일에는 자산 로딩·명시적 조립만 남긴다. 판본 빌더의 산출 위치는 `frontend/dist-surfaces/<sha256>/`, 활성 포인터는 같은 루트의 `active.json`이다. 설치 앱에서는 앱 데이터의 판본 저장소를 사용한다. Android 저장소는 `indiebiz_base` 바깥이며 APK 기본 번들은 초기 복구 판본이다. 단순 화면 자산은 RED 보호를 유지하되 Python 재기동 대상이 아니다.

처음에는 현재 출력과 같은 원본 추출을 완료한다. 다음으로 표시 모듈과 상태 소유자를 분리한다. 마지막으로 검증된 판본의 활성화·복구를 연결한다. 각 기존 진입점은 처음부터 새 원본의 산출물을 소비한다. 단계마다 병렬 소스가 생기지 않는다.

## 닫힌 이행 표

| ID | 판정·대상·소유자 | 소비자·기존 진입점 | 작업과 제거 대상 | 완료 증거 |
| --- | --- | --- | --- | --- |
| shell | 변경: HTML/CSS/JS 원본. `frontend/surfaces/{remote,phone,member,shared}` | `launcher_surface_remote.launcher_html`, `launcher_surface_phone.phone_html`, `api_launcher_web` lite, `member_html`, `browser_html`, `frame_html`; helper Go embed; Android 두 빌더; desktop 빌더; i18n exporter | 문자열 원본 추출, 명시적 슬롯, Python import 시점 본문 고정·태그/문구 치환 제거. 출력 동일성 뒤 상태 분리 | 구현·전체 회귀 통과 |
| conversation | 변경: 헤더의 이전 대화·히스토리·새 세션·사전 구성, 기록 표시 범위 계산, 사전 검색·입력 삽입 규칙. `surfaces/shared` | React ChatView/ActionGrimoire, remote sessions/autopilot/shell, lite, member workspace. 데이터 요청·권한·작업 시작은 각 어댑터 | 공통 규칙의 사본 제거. 렌더러별 DOM/React 표현만 유지 | 구현·자동 검사 통과; 배포 인수는 아래 기록 |
| member-display | 변경: 회원 대화·탐색·파일 화면 표시. `surfaces/member` | 회원 웹/Go/desktop/Android, 작업 API·iframe 요청 어댑터 | 표시 함수와 작업 드라이버 분리. DOM에만 있던 초안·선택·파일 hash 상태의 소유권 명시. 반복 boot/타이머 생성 금지 | 구현·자동 검사 통과; 배포 인수는 아래 기록 |
| launcher-display | 변경: 원격·폰의 탭/대화/앱 주변 화면 및 lite 표시. `surfaces/remote`, `surfaces/phone` | 원격 API, 폰 로컬 API; common/render core와 appmode/manual/autopilot/warehouse | 화면 표시와 요청·작업·장치 수명 분리. 공통 탭 차이는 표면 구성으로 유지. 외부 엔진 인스턴스 보존 | 구현·자동 검사 통과; 배포 인수는 아래 기록 |
| owner-display | 변경: owner React 대화/런처 구성과 해당 표시 모듈 | ChatView, Launcher, App, surface-navigation, electron/windows | 공통 동작 소비, 상태 소유 host와 표시 경계, 배포 앱의 활성 자산 로더. React 전체 이식·모든 도구창 재작성 없음 | 구현·자동 검사 통과; 배포 인수는 아래 기록 |
| navigation | 변경: 런처에서 실제 노출하는 도구 메뉴의 제목·순서·route ID | Launcher 메뉴, App route, surface-navigation, Electron tool window | 공유 상수에서 연결; native 크기/권한은 Electron 어댑터. 선언형 instrument 목록은 기존 manifest 소유 | 구현·자동 검사 통과; 배포 인수는 아래 기록 |
| release-web | 변경: 판본 빌드·제공·열린 화면 적용 | Python 원격/회원 서버, 주인 폰 로컬 서버, React 제공자 | 완성된 불변 자산·지문·호환·원자적 활성화·이전 판본 유지. 구성/표시 코드 모듈 인계. 소스 저장 자체로 운영 배포하지 않음 | 구현·자동 검사 통과; 배포 인수는 아래 기록 |
| release-desktop | 변경: 기존 RuntimeUpdates 종류 확장 및 owner 로더 | member updates/publish/main/preload/workspace; owner Electron 로더 | UI-only에는 Go/DB 조작 없음. 종류별 sequence·호환·pending 복구·설치 확인. 첫 loader 지원은 전체 설치물 필요 | 구현·자동 검사 통과; 배포 인수는 아래 기록 |
| release-android | 변경: 서명 검증 로컬 자산 선택·적용 | owner BaseBundle/phone_api; member MemberRuntime/Activity | APK 기본 화면 및 base 바깥 판본 저장소, 사용자 확인·동일 배포자 신뢰·실패 복구. 최초 APK 이후 UI만 갱신 | 구현·자동 검사 통과; 배포 인수는 아래 기록 |
| repair-check | 변경: 실제 빌드 입력을 이용한 검사/수리 범위 | select_tests, repair_staging, body bundle, Gradle, helper/desktop 빌더, ui catalog | 기존 입력 목록 재사용, 새 경로 누락/낡은 생성물 감지. 소스 적용과 활성 판본 구분 | 구현·자동 검사 통과; 배포 인수는 아래 기록 |
| execution | 유지: 작업 원장·요청·권한·네이티브 브리지·DB·편집/미디어 엔진 | 기존 backend/Go/native/Electron 서비스 | 표시 변경으로 재시작·재실행하지 않음. 이 계약 변경은 전체 실행부 업데이트 경로 | 전체 회귀·실행부 통합 통과 |
| frameworks | 제외: 범용 DSL/플러그인 관리자, 전체 React 이식, 모든 서비스 분리, 임의 실행 스택 HMR | 해당 없음 | 목표에 불필요한 새 체계를 만들지 않음 | 설계 경계 |

## 상태 소유자와 인계 계약

| 대상 | 현재 → 최종 소유자 | 보존·보류·복구 |
| --- | --- | --- |
| 회원 대화 | workspace 전역의 currentTask/taskSelectionVersion/memberDrafts와 message DOM → 지속 workspace host | 표시 교체 전후 같은 task/초안, 최신 입력과 selection/scroll. 진행 요청은 host가 계속 받음. 갱신 시 send/boot 재실행 금지 |
| 회원 파일 | fileEditor/filePath DOM + memberFileHash/Path → file host | 초안과 원본 hash를 함께 보존. save 중 보류 후 재개. 실패 시 최신 초안 유지 |
| 회원 승인/미디어 | member_shell 요청 루프·native pending map·audio → 기존 실행 host | 승인 영역은 권한 경계로 유지. 결정 처리 중 보류. media/audio/pending/iframe 실제 노드를 유지 |
| 회원 앱 | iframe srcdoc/CUR/pending, parent queue/generation → 앱 frame host | 주변 화면 교체로 iframe 재로드 금지. bridge generation 유지, 중복 명령 금지 |
| 원격/폰 대화 | autopilot/session 전역 + DOM → conversation host | 요청/스트림/선택 task 유지, 최신 초안/스크롤, 종료 callback 세대 확인. IME 조합 종료 후 인계 |
| 원격/폰 도구 | appmode/manual/warehouse 상태 및 render 엔진 → 기능별 host | 실행 요청/엔진은 유지, 주변 표시만 교체. save/권한 처리 중 보류; latest 상태로 rollback |
| React | ChatView/Launcher hooks → 지속 host + 표시 컴포넌트 | host unmount 없이 표시 교체. 입력/선택/task/subscription 유지. 새 타이머 중복 금지 |
| 메뉴·구성 | 각 렌더러의 상수 → shared 정의 | 상태 없음. 선택/권한 판단은 host에서 계속 수행 |
| 판본 | 기존 installer 상태 → 같은 installer의 종류별 UI 상태 | 이전/후보/확인 단계 내구 기록. 확인 전 종료는 이전 UI, UI 실패에 DB snapshot 복원 금지 |

인계는 상태 판본 1에서 시작하며 호환 불가 상태/실행 계약 변경은 UI-only로 허용하지 않는다. 표시 변경 중 생긴 입력·작업 결과를 과거 snapshot으로 덮어쓰지 않는다. 각 적용은 직렬화하고 임시 보류는 끝나는 사건으로 같은 적용을 재개한다.

## 초기 증거

소스 추출 전 6개 산출물을 `/tmp/indiebiz-ui-baseline/`에 저장했다. remote는 번역 결과와 원문을 구분해 비교한다. 이벤트/API/권한 동등성은 기존 회귀와 브라우저 검사로 보강한다. 최종 main 입력과 지문을 다시 대조한다.

Android 실기기 설치·표시 교체는 아래 기록대로 확인했다. 모의 시험과 빌드 성공을 Windows/Linux 실제 설치 성공으로 쓰지 않는다. 미확인 배포 표면은 미완료로 유지한다.

## 원본 추출 검사

회원 웹의 HTML 태그·문구 치환을 명시적 슬롯으로 바꾸고, remote/phone/lite/member/browser/frame 6개 출력이 추출 전과 바이트 동일함을 확인했다. 기존 Python import 이름은 얇은 자산 어댑터로 유지하며 화면 본문 사본은 제거했다. 새 `build_surfaces.py`는 불변 판본을 생성하고 `--activate`를 명시할 때만 포인터를 바꾼다. 같은 응답의 조각은 한 판본으로 고정한다. 생성 helper도 바이트 동일하다.

전이 선택 81개 시험 파일에서 1,168개 통과. 샌드박스가 Chromium을 막은 28개는 샌드박스 밖에서 재실행해 통과했다. 이전 사적 경로 `_CORE_PATH`를 직접 읽던 시험 1개는 실제 자산 로더 사용으로 바꾸고 렌더 코어 시험 3개를 통과했다. 새 판본 계약 시험 7개는 소스 저장/활성화 분리·불완전 후보·동시 수정·응답 판본 고정·손상·조립 변경·슬롯 비재해석을 검증했다. 검사 중 별도 파일 편집이 있어 live-store 가드가 보고했으며 해당 두 파일은 이번 구현의 편집이었다.

이후 열린 화면 적용·플랫폼별 UI-only 경로·공통 동작/메뉴를 연결했다. 아래 기록은 코드 구현과 실제 설치 인수를 구분한다.


## 연결한 활성화 계약

- 공통 헤더의 순서·문구는 `surfaces/shared/conversation.json`, 날짜·부분 표시·낱말 일치·삽입은 `conversation.js`다. React/원격/폰/lite/회원은 해당 동작을 소비한다. React 마법책은 검색창·문자열 삽입이 없는 선택 토글이므로 그 차이를 유지한다. 서버 세션 페이지 조회와 회원 이벤트의 부분 표시는 서로 다른 저장 계약이다.
- 여덟 도구의 제목·route와 그중 런처에 노출하는 항목의 순서는 `navigation.json`이 소유한다. React 라우트·런처·창 열기·Electron 창 생성이 소비한다. 크기·권한은 native 어댑터에 남는다.
- HTML 표면은 `display-host.js`로 교체한다. lite에는 ES5/XHR 인계 어댑터가 있다. DOM 3자 비교는 사용 중인 입력·미디어·iframe 노드를 유지하고 호스트 상태 영역 삭제를 거절한다. IME와 파일/승인 처리 중에는 종료 사건을 기다린다. 함수·DOM·CSS 인계 실패는 이전 판본으로 복구한다.
- 회원 안쪽 앱은 별도 frame 표시 모듈이다. opaque iframe의 기존 parent 메시지 경계로만 표시 인계 응답을 주고받는다. 대화 헤더 수정으로 frame host가 달라지지 않는 검사가 있다. 요청 큐·허용 명령·토큰·editor/media 수명은 유지한다.
- 주인 React는 `ChatView`/`Launcher` hooks가 계속 살아 있고 `ChatDisplayView`/`LauncherDisplayView`만 교체한다. 운영 컴파일러는 React를 다시 싣지 않고 기존 컴포넌트·핸들러를 명시된 bindings로 받는다. 상태 소유 컴포넌트의 구조 이동은 거절한다. CSS·번역도 함께 인계하며 설치물/소스 실행부의 host와 맞는 로컬 판본만 사용한다. 개발 HMR을 운영 적용으로 사용하지 않는다.
- 주인 데스크톱의 신뢰 출처는 기존 로컬 수리 권한으로 활성화한 백엔드 판본이다. `/launcher/owner-display`는 기존 launcher 인증 경계이며 쓰기 API가 아니다. Electron 파일 화면도 같은 백엔드의 완성된 자산을 읽고 사용자 선택 후 적용한다. 브라우저 로컬 저장에는 성공한 표시만 남기고 새 설치물과 host가 다르면 무시한다. 배포 앱의 서버 저장 위치는 `INDIEBIZ_BASE_PATH/frontend/dist-surfaces`, 별도 설정은 `INDIEBIZ_UI_STORE`다.
- 회원 데스크톱은 기존 RuntimeUpdates 안의 `kind: ui`/한 파일 `display.json`, shell 3이다. runtime과 UI 순번만 분리하며 기존 설치 확인·서명 체계는 유지한다. UI에는 실행부 정지·DB snapshot/restore가 없다.
- Android 두 앱은 동일 Kotlin 검증기·설치기, `filesDir/ui-releases`, APK 기본 복구 판본을 쓴다. Ed25519는 minSdk 28에서도 동작하도록 Tink Android를 사용한다. 공개키·피드는 빌드 설정이며 허브 초대로 바뀌지 않는다. 주인 폰 로컬 서버와 회원 MemberRuntime도 검증된 같은 선택을 읽는다. 설정·발행법은 `phone-companion/member/README.md`에 있다.
- `repair_staging`은 기존 checks/적용 영수증에 surface_build 지문과 surface_activation 결과를 담는다. 적용은 `--expect`로 검사한 판본과 일치할 때만 포인터를 바꾼다. 선택기는 HTML 자산 참조와 JS/TS import의 전이 소비자를 따라간다. 화면 때문에 backend Python을 수정하지 않는다.

### 운영 순서

1. 공통 원본 수정 후 필요한 번역 카탈로그와 해당 소비자 검사를 실행한다.
2. `python3 scripts/build_surfaces.py`는 후보만 생성한다. `--check`는 같은 입력의 산출물을 대조한다.
3. 로컬/웹 배포는 검증한 지문으로 `python3 scripts/build_surfaces.py --activate --expect <지문>`을 실행한다. 소스 저장만으로 활성화되지 않는다. 수리 도구의 apply는 이 연결을 자동 수행한다.
4. 설치형 회원 PC/Android는 해당 display 디렉터리를 기존 서명 발행기로 발행하고, 사용자 선택 후 검증·인계·확정한다. 구형 설치물에는 최초 shell/APK 갱신이 필요하다.
5. 이전 불변 판본은 보존한다. 활성 판본 손상은 이전 완성 판본을 사용하며 열린 화면은 가지고 있던 자산을 계속 쓴다. 강제 새로고침은 하지 않는다.

### 확인한 증거와 남은 인수

- 주인 실제 React 브라우저 검사: 세션 생성/전환/재접속/과거 기록, 320·390·1280px 배치, 운영 표시 모듈 교체, 초안·selection·DOM 동일성, 추가 요청 없음, 실패 유지 통과.
- 표시/판본/선택기 묶음: 새 버튼 삽입, IME 중 입력, 파일 초안, iframe/audio/요청 함수 동일성, 실패 복구, 공유 버튼 변경 시 host 불변을 검사했다. 전체 비시스템 회귀는 10,468 통과·1 건너뜀이다. 마지막 수리 입력 목록 연결은 판본 시험 11개와 실제 격리 수리 배터리로 추가 검증했다.
- Node 회원 업데이트·실행 바이너리 통합 32 통과(건너뜀 없음), Go 전체 통과. 번역/표면 Node 40 통과. TypeScript 검사·React 운영 빌드 통과. Android 두 앱 Kotlin 컴파일, 주인 arm32/arm64 및 회원 APK 빌드, 실제 Ed25519 검증 JVM 4 통과. macOS 회원 설치 묶음도 생성했다.
- 관련 system 검사 27개는 첫 실행에서 25개가 통과했고, 형제 모듈 로딩·이벤트 루프 위반 2개를 수정 후 모두 통과했다. 마지막 입력 목록 변경 후 격리 수리 배터리를 다시 통과했다. 원격/lite/X-Ray/포털 HTML 조립은 서버 스레드풀에서 수행한다.
- Android 실제 연결 기기에 회원 APK 신규 설치와 주인 arm64 APK 데이터 유지 업데이트를 실행해 모두 성공했다. 실제 WebView에서 버튼 문구를 교체하고 초안·선택·입력 DOM·요청 함수 동일성과 원래 표시 복구를 검증했다. 회원은 iframe/window 동일성도 확인했다. 실제 작업 전송 없이 예약된 `.invalid` 검사 주소를 사용했고, 새 회원 앱의 임시 주소·키·초안은 검사 후 삭제했다. 주인 앱의 기존 설정은 보존했다.
- 운영 서명 피드 발행·Windows/Linux 실제 설치·구형 iOS 브라우저 실기기는 미검증이다. 현재 로컬 빌드 환경에는 운영 공개키/피드 설정이 없어 APK는 기본 화면으로 동작하며 운영 화면 릴리스를 받는 배포물로 간주하지 않는다. 서명 검증/확인/저장/복구 코드는 연결했고 시험했지만, 실제 배포자 키와 HTTPS 피드를 지정한 첫 설치물 및 배포 인수는 필요하다. 개발 APK나 모의 피드를 운영 배포 완료로 계산하지 않는다.

수리 패키지 지문 재감사: 변경은 repair_staging의 검증/적용 경로와 그 전용 repair_surfaces뿐이다. fixed argv 빌더는 검증된 저장소 안에서 실행되고 활성화에는 기존 수리 grant와 검사 지문 일치가 필요하다. 회원 read/fill/write/script의 member_documents·기기 path/hash·요청 세션 경로는 수정하지 않았다. 패키지 전체 Python 지문 변경에 따라 네 path_audited 표식을 갱신하며 회원 격리 회귀를 최종 검사에 포함한다.

최종 수리 입력 판정은 `surface_assets.source_files()`를 재사용한다. 번역 remote.json·runtime, 공용 static 렌더 코어, package-lock 같은 간접 입력도 화면 빌드·활성화에 포함한다. 새 파일·삭제된 파일은 원본 폴더 경계로 추가 포착한다. 수리 helper는 형제 파일에서 직접 로드해 프로세스별 sys.path 차이에도 검증 경로가 끊기지 않는다.

주인 화면의 공통 동작도 표시 경계에 포함한다. 대화 규칙(pageSize) 변경은 host 지문을 유지하고 표시 모듈에 반영되며, preload 변경은 host 지문을 바꿔 UI-only 교체를 거절한다. 임시 소스 사본과 실제 React 교체 검사로 양쪽을 확인했다.

최종 활성화: 검증한 판본 `09c8f055b3387bee3acd33e52e77618af94d3c7bafa5d9bf1f738ff98369a2f0`을 정본의 `frontend/dist-surfaces/active.json`에 지정했다. 같은 프로세스의 자산 읽기와 주인/원격/회원 제공이 이 완성 판본을 사용하는지 확인했다. 실행 중인 창의 강제 새로고침이나 원격 설치물의 자동 설치는 수행하지 않았다.

macOS Electron 실제 실행 검사: 임시 userData를 사용하고 OS 프로토콜 등록만 시험에서 막은 뒤 실제 main/preload/workspace를 실행했다. 표시 변경과 복구 전후 초안·selection·입력 DOM·DesktopMember 브리지·iframe/window 동일성이 모두 통과했다. 배포용 서명과 다른 OS 설치 인수와는 구분한다.

별도 서버 저장소(`INDIEBIZ_UI_STORE`)를 지정하는 경우 수동 빌더도 같은 위치를 `--store`로 지정한다. 자동 수리 apply는 정본의 기본 저장소를 사용한다. 현재 정본은 기본 저장소다.

### 맥12 실제 연결 재검증 (2026-10-16)

맥12(`guestpc-3fd796167b18`, Intel macOS 15.7.9)는 중앙 앱 기동 뒤 재연결됐으며 실제 `info`·원격 셸 실행을 확인했다. 설치된 `/Applications/IndieBiz.app`는 주인용 0.1.0이고 새 회원 데스크톱 설치물은 확인되지 않았다. 따라서 이 기기의 연결 성공을 회원 앱 UI-only 배포 인수로 계산하지 않는다.

중앙 주인 앱의 실제 기동에서 `windows.js`의 공통 메뉴 JSON 로딩이 `require is not defined`로 실패했다. ESM에서 `createRequire(import.meta.url)`로 읽도록 수정했다. 실제 Electron에서 격리된 userData로 창 모듈을 import하고 IPC 등록까지 실행하는 `frontend/electron/windows.test.mjs`를 추가하고, 기본 회귀 경로 `backend/test_electron_windows.py`에 연결했다. 관련 Node 5개·pytest 진입 1개가 통과했고 중앙 앱의 정상 부팅과 health를 확인했다. 앞선 회원 Electron 검사만으로 주인 앱 시작까지 검증했다고 볼 수 없었다.

실제 ScreenShare 화면에서 맥12로 연결했지만 시작 직후 종료됐고 수신 영상은 0장이었다. 맥12의 같은 네이티브 실행부에 frame 요청을 보내 확인한 오류는 `screen permission required`다. 이 실행부는 손쉬운 사용 검사 다음에 화면 기록을 검사하므로, 현재 실패 지점은 화면 기록 권한이다. 시스템 캡처도 실패했다. 사용자에게 맥12의 화면 기록 허용을 요청하고 해당 설정 화면을 열었다. 권한 허용 후 영상·입력 재검증이 필요하며 현재 화면 공유 성공이나 화면 교체 인수 완료로 기록하지 않는다.

중앙 서버는 loopback에서 수신하므로 맥12에서 중앙 LAN 주소로 직접 원격 런처를 여는 시도는 성립하지 않았다. 이 검사 때문에 서버 바인딩이나 인증 설정을 바꾸지 않았다. 화면 공유 시험 창과 세션은 닫았고 기존 기기 등록·사용자 앱 데이터는 유지했다. 운영 서명 피드 및 회원 설치형 앱의 UI-only 실제 배포 인수는 여전히 별도 미완료 항목이다.

### 독립 회원 설치물과 macOS 서명 재검사 (2026-10-16)

맥12에 Intel용 `IndieBiz Member.app` 0.1.3을 별도 임시 프로필로 설치·실행했다. 기존 헬퍼는 설치물 전달과 검사 명령 운반에만 사용했다. 새 앱은 자체 Go 실행부·작업 DB·작업 폴더와 실제 HTTPS 중앙 연결을 사용한다. 시험 전용 Ed25519 공개키와 기기 loopback HTTPS 피드를 넣었으며 운영 배포물은 아니다. 실제 등록 화면에서 임시 회원 등록과 일회용 초대를 만들고, 새 앱의 등록 폼으로 연결했다.

기존 주인 앱에 활성 턴이 없음을 확인한 뒤, 맥12의 기존 주인 Electron·백엔드와 상주 헬퍼를 일시 정지했다. 별도 복구 프로세스와 finally에서 재개를 보장했다. 모두 정지 상태인 동안 새 앱의 파일 읽기와 중앙 접속이 유지됐다. 중앙에서 요청한 `[self:read]`의 실제 기기 실행·응답·로컬 기억 저장도 완료했다. 종료 후 기존 프로세스의 동작 상태를 확인했다. 이 검사는 기존 헬퍼나 기존 주인 백엔드를 새 앱의 실행 의존으로 사용하지 않는다.

첫 중앙 파일 읽기는 `JSONDecodeError`로 실패했다. 구형 IBL이 정상 파일 본문을 일반 문자열로 반환하는데 `member_session`이 무조건 JSON으로 해석했다. 일반 본문은 그대로 앱 결과로 전달하도록 수정했다. 실제 IBL과 파일 변환을 거치는 회귀에서 일반 텍스트·빈 파일·한글 여러 줄의 실패를 재현하고 수정 후 통과했다. 맥12에서 같은 독립 실행 검사를 다시 수행해 `completed`, `memory_saved:true`를 확인했다.

현재 개발 설치물의 앱과 Go 실행부는 ad-hoc 서명이고 designated requirement가 파일의 cdhash에 묶여 있다. 업데이트 매니페스트의 Ed25519 서명은 macOS 권한을 이어 주는 코드 신원과 별개다. `native-signature.cjs`에서 설치물의 기준 실행부와 새 실행부의 실제 OS 서명·designated requirement를 검증하도록 연결했다. ad-hoc·서명 손상·신원 변경은 실행부 정지나 DB snapshot 전에 거절하며 UI-only는 실행 파일을 바꾸지 않는다. 정식 서명 키는 사용하지 않았다. 정식 서명 설치물에서 최초 권한 허용 → 런타임 갱신 → 재시작의 인수는 남아 있다.

맥12의 새 회원 앱에서 OS 권한을 직접 조회한 결과 화면 기록은 `denied`, 손쉬운 사용은 미허용이었다. 이 결과를 기존 상주 헬퍼의 권한과 혼동하지 않는다. 실제 서명된 UI 후보 0.1.4의 HTTPS 조회·검증은 성공했으나, 설치 확인 요청 뒤 macOS 접근성 조회에는 창이 나타나지 않아 확인 창의 실제 표시 여부를 사용자에게 질문했다. 열린 화면 적용·취소·복구는 이 기기에서 아직 인수하지 않았다. 로컬에서 통과한 표시 교체 시험을 맥12의 성공으로 대신 쓰지 않는다.

변경 관련 회귀 15파일은 92통과·실행부 환경변수 미지정 1건너뜀이었으며, 해당 Go 통합 시험을 실제 빌드 실행부로 다시 실행해 1통과했다. 회원 Node 전체는 실제 Go 실행부와 함께 36통과·건너뜀 없음, macOS 코드 서명/업데이트의 기본 pytest 진입점 1통과. Android 몸 번들을 재생성했다. 이번 좁은 수정에서 backend 전수를 다시 실행하지 않았다. 임시 전달 서버는 종료했고 정본의 무시되는 빌드 신뢰 설정도 미설정으로 복원했다. 임시 회원 앱·등록·loopback 시험 피드는 확인 창 관찰을 위한 시험 상태로 남아 있으므로 인수 종료 시 정리한다.
