# 내 어휘 묶음의 경계와 분리 비용 조사

조사일: 2026-09-13. 조사 기준 코드: `dc543224`.
대상: 정본 저장소의 보유 패키지 선언 전체, 주요 혼합 패키지의 핸들러·형제 모듈, 등록·활성·회상·내보내기·폰 배포 경로.
범위: 조사와 임시 디렉터리 실험. 실제 어휘·패키지·사용자 선택은 변경하지 않았다.

## 판단

**현재 일부 묶음은 사용자가 함께 선택할 능력의 단위로 자연스럽지 않다. 그 묶음들은 나누는 편이 좋다. 모든 묶음을 작게 만들거나 낱말마다 패키지를 만드는 일은 필요하지 않다.**

분리 비용은 인증·공통 라이브러리를 새로 만드는 비용이 아니다. 공통 기반은 새 패키지도 사용한다. 비용은 주로 기존 패키지 내부의 함수·파일 직접 참조를 정리하고, 소유 묶음 ID에 연결된 선택·배포 정보를 옮기는 데 있다. 독립적인 HTTP 조회 기능은 비교적 쉽고, 시스템 쓰기 보호·미디어 제작처럼 여러 소비자가 내부 구현을 공유하는 부분은 어렵다.

묶음 경계는 다음 세 질문으로 정하는 것이 적절하다.

1. 이 기능들을 사용자가 함께 깨우고 잠재울 이유가 있는가?
2. 하나의 지속되는 대상이나 작업을 다루며, 함께 주고받을 이유가 있는가?
3. 한쪽을 떼어도 나머지 큰 묶음을 함께 켜야 하는 의존성이 남지 않는가?

함께 조합해 쓴다는 사실만으로 같은 묶음이어야 하는 것은 아니다. IBL은 원래 묶음을 넘어 조합한다. 공통 라이브러리를 쓰거나 같은 넓은 분야에 속한다는 사실도 묶음의 충분조건이 아니다.

## 전체에서 문제가 차지하는 위치

보유 폴더 두 곳을 합쳐 **46개 묶음**을 확인했다. 빌드된 사전집은 **165개 액션**이다. 이 수는 잠든 어휘와 폰 전용 어휘를 포함하므로 현재 PC 실행 가능 액션 수와 다르다.

- 액션 1개인 묶음: 21개.
- 액션 2~7개인 묶음: 18개.
- 액션 10개 이상인 묶음: 4개 — `house-designer` 10, `data-ops` 16, `system_essentials` 21, `ibl-core` 표시 28.
- 현재 사전집에 액션이 없는 보유 묶음: 3개 — `nodejs`, `publishing`, `python-exec`.

따라서 전체가 큰 묶음으로 편중됐다고 보기는 어렵다. **혼합된 몇몇 묶음과 넓은 필수 묶음이 선택을 거칠게 만드는 문제**다. 특히 `ibl-core`의 28개는 패키지 fragment에서 세는 값이 아니다. 내 어휘의 `package_words()`가 패키지 소유자를 찾지 못한 중앙 액션을 그 아이콘 아래 표시하는 값이다.

큰 묶음의 반례도 있다. 집 설계의 10개 액션은 같은 설계의 생성·수정·평면·단면·입면·내보내기를 다룬다. 강의 작업공간의 4개는 같은 강의·슬라이드·자료·덱을 다룬다. 숫자가 크다는 이유로 나누면 사용자의 선택 부담과 의존성만 늘 수 있다.

## 후보별 권고

난이도는 실제 종단 이관 전의 코드 조사 판단이다. ‘낮음’도 아래 공통 이관·검증을 생략한다는 뜻은 아니다. 새 묶음 이름은 제안이며 확정 ID가 아니다.

| 현재 묶음 | 제안 경계 | 분리 가치 | 난이도와 근거 |
|---|---|---|---|
| `study` — 4개 | **논문·연구자** / **개체 식별** / **세계은행 통계** | 높음. 학술 검색을 켠다고 국가별 경제·인구 통계나 범용 Wikidata 조회까지 고를 이유는 약하다. | **낮음.** 함수 호출 관계가 세 갈래로 나뉜다. 논문·연구자는 국회도서관 호출을 공유하므로 함께 유지할 근거가 있다. |
| `culture` — 4개 | **책·고전** / **공연·전시** | 높음. 읽을거리와 외출할 문화행사의 선택을 분리할 수 있다. | **낮음~중간.** 제공자 구현이 이미 별도 `tool_*.py`다. 공통 결과 정리 함수와 가이드·폰 배포를 옮겨야 한다. |
| `shopping-assistant` — 3개 | **상품·중고 검색** / **외주 서비스 검색** | 높음. 외주 인력·서비스 탐색은 물건 가격비교와 별도 용도다. 상품과 중고는 우선 함께 둔다. | **낮음.** 외주 검색은 `tool_freelance.py`와 작은 호출 래퍼로 독립돼 있다. |
| `location-services` — 7개 | 우선 **날씨** / **장소·이동·숙박**. 이후 필요하면 숙박을 별도 선택. | 날씨 분리는 높음. 나머지 전부를 즉시 쪼갤 근거는 부족하다. | **중간.** 날씨 좌표 해소를 함께 옮겨야 한다. 장소 상세는 기존 네이버 검색·블로그 근거 함수를 주입받는다. 사진 API도 주소 변환 함수를 직접 불러 쓴다. |
| `web` — 6개 | **웹 자료 접근**(search/crawl/http/feed) / **신문 제작**. 사이트 열기·즐겨찾기의 위치는 별도 검토. | 신문 제작 분리는 높음. 웹을 찾는 능력과 편집·발행하는 능력은 별도 선택이 자연스럽다. | **중간.** 신문은 형제 모듈이지만 핸들러의 뉴스 검색 경로를 콜백으로 재사용한다. 취재 의존을 유지할지 공통 서비스로 뺄지 정해야 한다. |
| `pc-manager` — 4개 | **기기 상태** / **저장소·폴더 주석** / **포식 기억** | 중간~높음. CPU·실행 앱, 디스크 색인, 기억의 위치 지도는 서로 다른 선택이다. | **낮음~중간.** host는 psutil, storage/folder_note는 같은 storage_db, forage는 backend 기억 모듈을 사용한다. REST가 storage_db의 기존 경로를 참조하므로 저장소 쪽 ID를 유지하면 이관을 줄일 수 있다. |
| `media_producer` — 4개 | **음성 생성** / **이미지 생성·읽기** / **문서·화면 렌더링** | 높음. TTS 때문에 이미지 모델과 산출물 렌더링까지 한꺼번에 선택할 필요는 없다. | **중간~높음.** 표면 구현은 이미 tts_engines/gemini_image/vision_read/render_artifact로 나뉘지만 강의 제작이 이 패키지의 영상 함수·슬라이드 모듈을 직접 참조한다. 숨은 공용 구현의 소유권 정리가 먼저다. |
| `business` — 5개 | **사업 관리**와 **이웃·대화** 분리를 검토. 자동응답·폰 동기화는 서비스 의존을 확인한 뒤 배치. | 중간. 사용 목적은 다르지만 같은 사업·이웃 데이터와 통신 흐름을 공유한다. | **중간.** BusinessManager는 backend 공통 기반이다. 다만 동기화는 여러 원장을 함께 다루고 자동응답은 서비스 수명 문제도 있어, 함수 묶음만 보고 완전 독립이라고 할 수 없다. 우선순위는 뒤다. |
| `system_essentials` — 21개 | **파일·자기수리 기반**을 유지하고 **원장·시트·SQLite**, **웹앱 등록** 등의 분리를 검토. 모든 기능을 한 번에 재배치하지 않는다. | 높음. 현재 필수 패키지라 일반 원장·시트 등도 선택적으로 잠재울 수 없다. | **높음.** sheet 쓰기는 핸들러가 주입하는 경로 보호 함수를 받는다. 쓰기·수리 보호는 backend와 여러 실행 경로가 이용한다. 공통 기반 유지와 필수 정책 조정을 함께 설계해야 한다. |
| `ibl-core` 표시 — 28개 | **언어·실행 기반**과 **채널·공개 소통 기능** 등의 선택 경계를 별도로 조사·설계. | 선택성 개선 가능성이 큼. Nostr·게시·구독 등이 문법·반복·실행 기반과 같은 아이콘에 나타난다. | **높음, 별도 과제.** 단순 핸들러 패키지가 아니라 중앙 정의·system/channel_engine 등 backend 라우터다. 명시적 소유권과 필수 범위가 필요하고, 현재 `.iblpack`은 동봉 handler 실행만 허용한다. |

`data-ops`, `house-designer`, `lecture_workspace`, `radio`, `cctv`는 이번 조사에서 크기만을 이유로 분리할 대상이 아니다. 특히 data-ops의 통화 변환과 집 설계의 뷰들은 응집력이 높다. 투자(stock/company/crypto)나 부동산의 세분화도 가능하지만, 위의 분명한 혼합 사례보다 먼저 처리할 근거는 부족하다.

## 분리가 쉬운 곳과 어려운 곳의 실제 증거

### 공통 기반은 패키지를 넘어 이미 재사용된다

- `backend/common/auth_manager.py`: 서비스 인증·환경변수 조회. 필요하면 패키지 config fallback도 지원하므로 로컬 설정이 있는 기능은 그 경로를 별도 확인해야 한다.
- `backend/common/api_client.py`, `backend/common/geocode.py`, `backend/common/response_formatter.py`: API 호출·좌표 조회·응답 처리.
- `backend/ibl/tool_context.py`: 모든 핸들러가 받는 프로젝트·도구·경로 컨텍스트.
- `backend/common/pkg_utils.py`: 형제 모듈 로딩 도우미.

새 패키지를 만드는 추가 틀은 `handler.py`의 얇은 진입점, `ibl_actions.yaml`의 액션·패키지 메타, 초기화 파일 등이다. `tool.json`은 빌더가 만든다. 공통 인증·런타임을 복제할 이유가 없다.

### 낮은 결합: 학술·통계·외주

`study/handler.py`를 AST로 읽어 로컬 함수 참조의 전이 집합을 조사했다.

- 세계은행: `_fetch_world_bank_data`, `_norm_wb_key`, `_resolve_wb_country`, `_resolve_wb_indicator`. 논문·연구자·Wikidata 함수에 연결되지 않는다. 관련 상수 표와 imports는 함께 옮겨야 한다.
- Wikidata: `_entity_*`, `_wd_*`, `_wikidata_*` 갈래. 논문·세계은행 함수와 분리된다.
- 논문과 연구자: `_nanet_call`을 공유한다. 이 둘은 함께 두는 편이 자연스럽다.
- 외주: `shopping-assistant/handler.py`의 `_handle_freelance`는 `tool_freelance.py`를 불러 호출한다. 상품·중고 검색 함수에 연결되지 않는다.

정적 함수 참조 조사이므로 동적 호출·외부 API 정상 동작을 증명하지는 않는다. 그러나 같은 파일에 있다는 것과 실제 구현이 얽혀 있다는 것을 구분할 근거는 충분하다.

### 높은 결합: 밖에서 내부 파일을 직접 불러 쓰는 곳

- `lecture_workspace/deck_video.py`: `media_producer/handler.py`를 파일 경로로 읽어 영상 생성 함수를 차용한다.
- `lecture_workspace/lecture_store.py`, `slide_ai.py`, `slide_edit_ops.py`: media_producer의 톤·렌더러·오버레이 모듈을 직접 참조한다. 일부 이미지 호출은 이미 tool_loader를 사용하므로 두 유형을 구분해 이관해야 한다.
- `backend/surface/api_photo.py`: location-services 핸들러의 `reverse_geocode_kakao`를 직접 호출한다. 날씨만 떼면 주소 변환을 기존 패키지에 남겨 이 영향을 줄일 수 있다.
- `backend/surface/api_pcmanager.py`: pc-manager 내부 `storage_db`를 경로로 찾아 import한다.
- `web/tool_webcrawl.py`: system_essentials의 `office_ops.py`를 직접 읽는다.
- `backend/datastore/red_apply.py`, `red_watchdog.py`: system_essentials의 핸들러·수리 파일을 경로로 참조한다.
- `system_essentials/sheet_ops.py`: `_path_guard`와 `_project_path`를 주입받는다. 새 핸들러에서 이를 빠뜨리면 같은 어휘 이름을 유지해도 쓰기 계약이 달라진다.

이런 의존은 ‘나눌 수 없음’의 증거가 아니다. 공용 서비스로 옮기거나 지원 구현의 소유권을 명확히 해야 한다는 증거다. 옛 거대 핸들러를 통째로 계속 import하는 작은 껍데기만 만들면 독립 선택·공유의 이점이 줄어든다.

## 임시 분리 실험

실제 패키지 선언을 읽어 다음 이동을 임시 디렉터리에서 시험했다. 제안 ID는 시험용이다.

| 원본 | 옮긴 액션 | 임시 새 묶음 |
|---|---|---|
| study | sense:world_bank | world-statistics |
| study | sense:entity | entity-lookup |
| shopping-assistant | sense:freelance | freelance-services |
| culture | sense:book, sense:classic | books |

검사 결과:

1. 실제 `collect_package_fragments`·`merge_fragments`로 전체 패키지 fragment를 합쳤다. 이동 전후 파싱된 액션 계약 dict가 완전히 같았다. 액션 5개를 묶음 4개로 옮겨도 어휘 이름·op·인자·반환·fixture가 바뀌지 않는다.
2. 원본에서 액션과 대응 tool 정의를 제거하고 새 선언으로 옮겼다. 실제 `derive_tool_json_docs`가 원본 3개와 새 묶음 4개의 tool.json을 오류 없이 생성했다. `inventory`의 액션·도구 소유자가 각각 유일했다.
3. 기존 활성 원장의 원본 ID만 옮겨 넣으면 새 ID는 기본 잠듦이었다. 원본 study의 paper는 깨어 있어도 새 world_bank는 잠들었다. **폴더를 만들어 옮기는 것만으로 현재 동작이 보존되지 않는다.**
4. 원본의 활성 선택을 자식 ID에 명시적으로 이어 주자 접근이 복원됐다. 이후 통계 묶음만 잠재우면 `action_reason`과 `require_tool_active`가 해당 액션·직접 도구만 막고 논문은 남겼다.

이 실험은 **정의·소유권·선택 경계의 성립**을 검증했다. 분리한 실제 핸들러의 실행, `.iblpack` 왕복, 전체 빌드 검증, 네트워크, 폰 종단 동작을 검증한 것은 아니다. 사용자 활성 원장·기억 DB는 수정하지 않았다.

## 실제 이관에서 공통으로 필요한 일

1. **IBL 이름과 tool 이름 유지.** 기존 `[node:action]`을 그대로 두고 소유 정의와 구현을 함께 옮긴다. 기존·새 패키지에 정의를 중복으로 남기면 충돌한다. 소스만 편집하고 파생물은 빌더로 생성한다.
2. **기존 선택·배치 계승.** `activation.json`은 패키지 ID를 키로 쓴다. 새 묶음에 기존 활성 상태를 이어 주고 revision을 올려야 한다. 폴더·저장고·쓰레기통·복원 배치도 같은 의미를 유지해야 한다. 분리 이관을 새 기능 자동 활성화와 혼동하지 않는다.
3. **기억은 유지.** 실행용 회상은 코드에 등장한 node:action의 현재 사용 가능 여부로 거른다(`ibl_registry.foreign_actions`/`code_is_own`). 이름이 같으면 기존 용례·임베딩을 전체 삭제·재학습할 이유가 없다. 다만 배포용 examples와 패키지 ID가 붙은 시딩 출처·태그·공유 기록은 확인해 옮긴다.
4. **앱·예약 작업 의존 점검.** IBL 이름이 같으면 호출 문장 자체는 유지할 수 있다. 이후 사람이 일부 묶음을 잠재우면 그 어휘에 의존한 프로그램이 못 도는 것은 의도된 결과다. 필요한 묶음을 안내할 근거가 있어야 한다. 일반 폴더로 보기만 재분류해서는 이 선택 문제가 해결되지 않는다.
5. **빌드·폰·배포 갱신.** 액션 소유권, package_meta, 문서 마커, core_manifest 등을 해당 빌더로 갱신한다. `PHONE_VERIFIED_PACKAGES`는 패키지 ID 기준이므로 원본에 있던 폰 지원이 새 ID로 자동 승계되지 않는다. 폰 검증·등재·번들을 함께 처리한다.
6. **공유 독립성 확인.** 새 `.iblpack`에는 해당 코드·형제 모듈·자원·용례가 필요하다. 현재 import는 같은 ID의 다른 버전을 자동 덮어쓰지 않으며, 새 ID에 같은 어휘가 있어도 충돌한다. 예전에 배포한 큰 묶음의 사용자에게는 명시적 교체 이관이 필요하다. 직접 의존 선언은 지원하지만 해결기·자동 활성화는 없다.
7. **재시작과 회귀 확인.** 형제 모듈은 handler 리로드만으로 교체되지 않는다. 재시작 후 대상과 잔류 액션의 실행·결과 계약, 잠재우기/깨우기, 회상 필터, 대표 앱·프로그램, 공유 왕복을 확인한다. 전체 검사 중 인자 검증은 패키지 파일 범위에도 의존하므로 분리로 기존 미선언 인자가 드러날 수 있다.

## 구현 방식과 권장 순서

**현재 패키지 체계 안에서 경계가 분명한 묶음을 실제로 나누는 방식을 우선 권한다.** 새 액션이나 문법 개정은 필요하지 않다. 원본 ID를 남은 주기능에 유지하고 독립 기능만 옮기면 경로·사용자 배치의 변경량을 줄일 수 있다. 예를 들어 study에는 논문·연구자를 남긴다.

다른 선택은 ‘배포 패키지’와 ‘선택용 어휘 묶음’을 별도 개념으로 만드는 것이다. 물리 코드를 적게 옮길 수 있지만, 현재 소유권·직접 도구 차단·필수 정책·회상·내보내기가 패키지 ID에 연결되어 있다. 선택과 배포를 분리하면 부분 내보내기의 코드·의존 범위까지 새로 정의해야 한다. 독립성이 이미 높은 몇 개 패키지를 정리하기 위한 첫 수단으로는 범위가 크다.

권장 순서:

1. **학술/개체/통계, 책/문화행사, 상품/외주**를 먼저 나눈다. 위 임시 실험과 정적 호출 조사로 경계가 가장 명확하다. 이것만으로 원본 3개가 7개 묶음이 되며, 전체 아이콘은 4개 늘어난다.
2. **날씨, 기기 상태·저장소·포식 기억**을 정리한다. 원본의 직접 참조 경로를 최대한 유지하며 분리한다.
3. **신문 제작, 미디어**의 기능 표면과 공용 구현을 구분해 나눈다. 큰 묶음 의존을 그대로 강제하는 껍데기 분리는 피한다.
4. **system_essentials와 ibl-core의 필수 범위**를 별도로 설계한다. 가장 큰 선택성 개선 여지가 있지만 단순 파일 이사로 다루면 안 된다. 노드의 `always_on`과 패키지의 필수 선택은 서로 다른 규칙이다. 실제 언어 코어의 의미를 바꾸면 기존 헌법·검증 규약을 따른다.

묶음을 나누어도 전부 켜 두면 액션 수는 줄지 않으며, 성능이 저절로 좋아지지 않는다. 이득은 필요한 기능만 선택하고 공유할 수 있다는 점이다. 실제 토큰·지연·요금·메모리 개선은 선택을 바꾼 뒤 별도 측정해야 한다. 현재 잠재우기는 상주 자원 해제도 보장하지 않는다.

## 근거와 조사 한계

- 구성: 각 `data/packages/{installed,not_installed}/tools/*/ibl_actions.yaml`, `tool.json`, `data/ibl_nodes.yaml`.
- 소유권·선택: `backend/datastore/vocabulary_state.py`, `backend/ibl/vocabulary_lifecycle.py`, `backend/ibl/vocabulary_desktop.py`, `data/vocabulary_policy.yaml`.
- 로딩·회상: `backend/ibl/tool_loader.py`, `backend/datastore/ibl_registry.py`, `backend/cognition/ibl_usage_rag.py`.
- 빌드·배포: `scripts/iblbuild_derive.py`, `scripts/iblbuild_common.py`, `scripts/build_core_manifest.py`, `backend/ibl/vocabulary_archive.py`, `backend/ibl/vocabulary_import.py`.
- 정본 설계: `data/system_docs/anatomy.md`, `data/system_docs/packages.md`, `data/system_docs/ibl.md`, `docs/VOCAB_LEGO_PLAN_2026_09_13.md`, `docs/IBLPACK_FORMAT.md`.

전체 선언은 조사했고, 후보의 주요 핸들러·직접 의존 경로를 집중해서 읽었다. 모든 구현 파일의 완전한 동적 호출 그래프를 복원한 것은 아니다. 실제 사용자의 공동 사용 빈도나 외부 서비스의 현재 가용성을 측정하지 않았다. 따라서 분리 가치는 사용 목적·독립 선택·코드 결합에 대한 설계 판단이며, 실사용 빈도나 성능 실측으로 포장하지 않는다.

## 부록: 조사 시점의 묶음별 액션 목록

아래는 조사 스냅샷이다. op의 개수가 아니라 node:action의 개수를 센다. 중앙 정의 중 패키지 소유자를 찾지 못한 액션은 내 어휘 화면과 같이 ibl-core에 배정했다.

| 묶음 ID | 액션 수 | 액션 |
|---|---:|---|
| `ai-ops` | 3 | `self:struct`, `table:ai`, `table:brief` |
| `android` | 6 | `sense:phone`, `sense:here`, `sense:listen`, `sense:see`, `limbs:android`, `limbs:phone` |
| `blog` | 1 | `self:blog` |
| `browser-action` | 1 | `limbs:browser` |
| `bulletin` | 1 | `others:bulletin` |
| `business` | 5 | `self:business`, `self:phone_sync`, `others:messages`, `others:neighbor`, `others:auto_response` |
| `cctv` | 3 | `sense:cctv`, `self:cctv`, `limbs:cctv` |
| `cloudflare` | 1 | `limbs:cloudflare_api` |
| `community-portal` | 1 | `others:portal` |
| `computer-use` | 1 | `limbs:screen` |
| `contest` | 1 | `sense:contest` |
| `context7` | 1 | `sense:devdocs` |
| `culture` | 4 | `sense:performance`, `sense:book`, `sense:classic`, `sense:exhibit` |
| `data-ops` | 16 | `table:filter`, `table:sort`, `table:take`, `table:chunk`, `table:select`, `table:compute`, `table:rename`, `table:flatten`, `table:dedup`, `table:since`, `table:groupby`, `table:join`, `table:union`, `table:merge`, `table:structure`, `table:document` |
| `family-news` | 1 | `others:family_news` |
| `finance-record` | 1 | `self:finance` |
| `guest-helper` | 2 | `self:limb`, `limbs:guestpc` |
| `health-record` | 1 | `self:health` |
| `house-designer` | 10 | `engines:arch_create`, `engines:arch_modify`, `engines:arch_get`, `engines:arch_floor_plan`, `engines:arch_view_3d`, `engines:arch_report`, `engines:arch_section`, `engines:arch_elevation`, `engines:arch_export`, `engines:arch_list` |
| `ibl-core` | 28 | `sense:world`, `sense:self_check`, `self:recent_chats`, `self:manage_events`, `self:switch`, `self:schedule`, `self:goal`, `self:notify_user`, `self:workflow`, `self:trigger`, `self:output`, `self:download`, `self:package`, `self:install_lib`, `limbs:os_open`, `limbs:open_window`, `others:delegate`, `others:ask`, `others:agents`, `others:channel_send`, `others:publish`, `others:channel_read`, `others:feed`, `others:nostr`, `others:board`, `others:follow`, `table:each`, `table:reduce` |
| `investment` | 3 | `sense:stock`, `sense:company`, `sense:crypto` |
| `kosis` | 1 | `sense:kosis` |
| `lecture_workspace` | 4 | `self:lecture`, `self:slide`, `self:material`, `self:deck` |
| `legal` | 1 | `sense:legal` |
| `location-services` | 7 | `sense:weather`, `sense:restaurant`, `sense:place`, `sense:navigate_route`, `sense:reverse_geocode`, `sense:stay`, `limbs:show_map` |
| `media_producer` | 4 | `engines:tts`, `engines:image_gemini`, `engines:render`, `engines:image_read` |
| `memory` | 1 | `self:memory` |
| `music-player` | 1 | `self:music` |
| `nodejs` | 0 | 현재 사전집에 없음 |
| `notebook` | 1 | `self:notebook` |
| `pc-manager` | 4 | `sense:host`, `self:storage`, `self:folder_note`, `self:forage` |
| `photo-manager` | 1 | `self:photo` |
| `public-files` | 1 | `others:showcase` |
| `publishing` | 0 | 현재 사전집에 없음 |
| `python-exec` | 0 | 현재 사전집에 없음 |
| `radio` | 3 | `sense:radio`, `limbs:radio`, `limbs:radio_favorite` |
| `real-estate` | 2 | `sense:commercial`, `sense:realty` |
| `remotion-video` | 1 | `engines:remotion` |
| `shopping-assistant` | 3 | `sense:search_shopping`, `sense:used`, `sense:freelance` |
| `startup` | 1 | `sense:startup` |
| `study` | 4 | `sense:paper`, `sense:researcher`, `sense:entity`, `sense:world_bank` |
| `system_essentials` | 21 | `sense:sqlite`, `self:time`, `self:ask`, `self:read`, `self:fill`, `self:write`, `self:list`, `self:file_find`, `self:grep`, `self:edit`, `self:copy`, `self:move`, `self:delete`, `self:mkdir`, `self:patch`, `self:webapp`, `self:body`, `self:sheet`, `self:script`, `self:ledger`, `table:spreadsheet` |
| `visualization` | 1 | `table:chart` |
| `web` | 6 | `sense:search`, `sense:crawl`, `sense:http`, `sense:feed`, `limbs:launch`, `engines:newspaper` |
| `web-builder` | 3 | `engines:web_site`, `engines:web`, `engines:web_component` |
| `youtube` | 3 | `sense:video`, `sense:search_youtube`, `limbs:music` |
