# 설치 패키지 1회성 경계 감사 — 2026-09-29

정본 저장소에서 **52개 설치 패키지(도구 47 + 확장 5)를 전수 스캔**했다. Python 구현 281파일·3,254함수, 설명/도움말/가이드의 IBL 언급 717곳을 대상으로 삼았다. **수리 대상 8부류를 확인**했다. 이는 발견된 결함의 수이며, 나머지 모든 경로가 정상이라는 증명이 아니다.

이번 작업은 조사다. 제품 코드·설정·DB·교재를 수정하지 않았고, 자동 빌드 관문도 추가하지 않았다. 실제 기억 조회·브라우저 조작·CCTV 접근·유튜브 재생·파일 저장·외부 발신은 실행하지 않았다. 검증은 합성 데이터와 부작용 없는 대역으로 수행했다.

## 확인된 수리 대상

| ID | 우선순위 | 문제와 영향 | 근거 |
|---|---|---|---|
| R1 | 높음 | **기억 전문 조회가 성공해도 판본 2에서는 실패**한다. `self:memory op:read`는 출처+본문을 평문으로 반환하고 `stamp_success`도 평문은 그대로 둔다. legacy-envelope는 이를 `ADAPTER_SHAPE`로 거절한다. | `memory/handler.py:293–319,97–123`, `backend/common/currency.py:188`, `backend/ibl/ibl_v2_adapters.py:146`. 합성 DB 1행으로 재현. |
| D1 | 높음 | **유튜브 앱의 재생·다운로드 버튼이 선언과 충돌**한다. 버튼과 실제 구현은 `mode:"client"`를 사용하지만 스키마는 audio/video만 허용한다. 현재 판본 2 검사에서 두 호출 모두 `ARGUMENT_CONTRACT`. | `youtube/ibl_actions.yaml:112,115,237`, `youtube/tool_youtube.py:626`, `youtube/tool_transcript.py:76`. 구체적인 값으로 대입한 두 문장 정적 재현. |
| P1 | 중간 | **브라우저 PDF 저장이 요청한 path를 무시**한다. Playwright는 항상 `outputs/pdfs/page_<시각>.pdf`를 만든다. Chrome 구현은 파일을 저장하는 대신 인쇄 대화상자를 열고 성공을 반환한다. 두 드라이버의 달성 조건도 다르다. | `browser-action/browser_content.py:478–510`, `browser_chrome.py:766–780`; path는 `ibl_actions.yaml:154`에 선언됨. Playwright의 경로 무시는 대역 재현, Chrome은 코드 확인. |
| P2 | 중간 | **브라우저 스크린샷이 공통 경로 표기를 해소하지 않는다.** `~workspace/reports/a.png`를 프로젝트 아래의 문자 그대로 `~workspace` 폴더로 취급한다. `~`도 동일한 구조다. | `browser-action/browser_content.py:139–176`, `browser_chrome.py:642–669`, 진입점 `handler.py:216` 이후에 경로 전처리 없음. Playwright 대역 재현·Chrome 코드 대조. |
| P3 | 중간 | **CCTV 캡처가 호출 프로젝트를 내부 저장 함수에 전달하지 않는다.** context.project_path가 execute에서 빠지고, cctv_capture도 capture_cctv에 project_path를 넘기지 않는다. 상대 save_path가 작업 프로젝트 대신 몸의 outputs/cctv_captures 아래로 간다. | `cctv/handler.py:383–420,567`, `capture.py:288–311`, `cctv_common.py:80`. 가짜 캡처 함수로 경로 전달 재현. |
| R2 | 낮음 | **파일 찾기의 한 오류 경로가 도구 오류 대신 봉투 오류가 된다.** 디렉토리 포함 glob 분기에서 예외가 나면 `"검색 오류: ..."` 평문을 반환한다. self:file_find에는 이를 받는 텍스트 오류 계약이 없다. | `system_essentials/handler.py:908–938`. glob 예외를 대역으로 주입해 `ADAPTER_SHAPE` 재현. |
| D3 | 낮음 | **부동산 README의 필터 예제가 현재 문법과 다르다.** `where:"deposit >= 20000"`은 현재 콜백 자리의 문자열이어서 TYPE 오류다. | `real-estate/README.md:16`. 합성 items를 보충해 검사하면 `Callable가 필요하지만 Text`로 거절됨. |
| D4 | 낮음 | **사진 가이드가 이미 가능한 조회를 불가능하다고 가르친다.** “반드시 Python으로 DB 직접 쿼리”하라는 안내와 예시의 날짜+GPS 유무 조건은 현재 self:photo의 start/end/has_gps로 표현 가능하다. 현재 IBL 입구는 가이드의 스캔 DB를 사용하지 않는다. | `photo-manager/guide.md:23–47` 대 `ibl_actions.yaml:18,23` 및 handler의 _query_photos. 같은 날짜+GPS 조건의 현재 문장 정적 통과. 실제 사진 내용은 읽지 않음. |

위 경로는 `data/packages/installed/tools/` 기준이다. 행 번호는 조사 당시 소스 기준이다.

**D1은 직전 수리의 영향도 있다.** `2e096a83`에서 스키마 enum을 정적 계약에 연결하면서 기존 스키마와 client 모드의 모순이 실제 사전 거절로 드러났다. 단순한 오래된 문서 문제로 치부하면 안 된다. 다음 수리에서는 play/download의 실제 지원 값과 relay의 모드 의미를 구분해 선언·앱 버튼·시험을 함께 맞춰야 한다.

## 결함으로 세지 않은 것

- **Context7의 문자열 오류 반환**: 내부 `_get_docs`가 평문 오류를 만들지만 `_search`가 실패 봉투로 감싼다. 실제 디코더에서도 TOOL 오류로 처리됨을 확인했다. 문자열 return이라는 이유만으로 위반이 아니다.
- **system_essentials의 편집 성공 문자열**: self:edit에는 `text_success_prefix`와 `text_error_prefixes`가 명시돼 있어 계약에 맞는다.
- **미디어 내부의 basename/abspath**: 외부 진입점에서 이미 `ToolContext.resolve_output_path`로 해소한 절대경로를 받는 사례가 있다. 함수 하나만 보고 경로를 버린다고 판정하지 않았다.
- **shadcn 내부의 평문 오류**: 은퇴한 직접 도구가 아니라 강의 소비자가 JSON 파싱 실패를 잡아 오류로 전환하는 경로다. 진단 품질 개선 여지는 있지만 이번에 성공을 실패로 뒤집는 동일 결함으로 세지 않았다.
- **앱 템플릿의 `$period`, `$sort`, `$lat`**: 실제 값 대입 전의 문자열/미정의 변수다. 원문 그대로 검사한 enum·UNBOUND 오류는 제품 결함 수에 포함하지 않았다.
- **문법 요약·어휘 이름·미완성 파이프**: `[table:each]`, `op:issue/list/revoke` 등의 표기는 완성 프로그램이 아니다. 구문 오류 수를 그대로 결함 수로 세지 않았다.
- **record-ops의 self:record**: 설치 선언과 실행 주체별 노출 경계가 다르다. 일반 레지스트리에서 UNSUPPORTED_ADAPTER가 나오는 것만으로 회원 실행 경로의 결함을 확정하지 않았다.
- **이웃 삭제 pubkey(D2)**: 최초 스캔에서는 UNKNOWN_ARGUMENT였지만, 조사 중 별도 작업이 `npub:[pubkey]` 별칭을 추가했다. 마지막 검사에서는 거절이 없어졌다. 이번 감사의 수리 성과로 세지 않으며 현재 미해결 8부류에도 포함하지 않았다.

## 전수 스캔의 범위와 한계

- 현재 설치된 `data/packages/installed/{tools,extensions}/*`의 모든 패키지를 목록화했다. 패키지별 범위는 [coverage.md](coverage.md), 파일별 SHA-256은 [inventory.jsonl](inventory.jsonl)에 있다. Python 문법 해석 실패는 0개였다.
- 문자열 반환 후보 **385곳**, 파일 열기/저장 API **339곳**, 경로 변환 **163곳**, 명시적인 공통 해소기 호출 **15곳**을 기록했다. open의 읽기 모드, 내부 상태 파일, HTML 렌더 보조 함수도 포함한 **후보 수**다. 예를 들어 “해소기 호출 15곳”은 나머지가 모두 잘못됐다는 뜻이 아니다.
- 설명·가이드·코드 문자열 717곳에서 IBL 후보 조각 **431개**를 추출했다. 원문 검사 결과는 parse_error 106 / invalid 18 / incomplete 298 / valid 9. 자리표·산문·약식 표기 때문에 생긴 오류가 많아 이 수치는 결함 수가 아니다. 또한 incomplete는 실행 성공을 보장하지 않는다.
- Python 외 구현 5개도 목록화했다: house-designer의 Three.js 시각화 템플릿 4개와 public-files의 HTTP Worker 1개. 각각 렌더 함수·HTTP Response 경계이므로 IBL 봉투 검사 대상에서 제외했다. Worker 보안·원격 저장 동작을 검증했다는 뜻이 아니다.
- 외부 라이브러리/캐시/빌드 폴더와 시험 파일은 제품 경계 스캔에서 제외했다. 설치되지 않은 패키지, 원격 서버 구현, 브라우저·네이티브 내부, 모든 shell/subprocess 부작용은 범위 밖이다.
- 이름 기반 호출 관계는 후보 추적용이며, 동적 로딩·콜백·패키지 간 호출의 완전한 데이터 흐름 증명이 아니다. 52패키지를 모두 읽기 목록에 넣고 같은 기준으로 스캔했지만, 모든 분기·모든 값의 실행을 확인한 것은 아니다.

추가 수리 후보로는 browser upload 경로, study의 filename 저장 경로, 드라이버별 저장 완료 의미를 남긴다. 요구한 경로 의미와 호출 전후의 해소 책임을 더 대조해야 하므로 확정 8부류에는 넣지 않았다.

## 증거와 재현

- [요약](summary.json), [문자열 반환 후보](return_candidates.jsonl), [경로 후보](path_candidates.jsonl), [예제 검사](example_checks.jsonl), [예제 출처](example_surfaces.jsonl), [비 Python 목록](non_python_inventory.jsonl).
- [오프라인 검증 결과](verification.json): **11개 탐침**이 예상한 결과와 일치했다. AST에서 해당 함수를 추출하고 가짜 DB·브라우저·파일 경로를 제공했다. 실제 제품의 전체 진입점을 실행한 통합시험은 아니다.
- 재현: `.venv/bin/python docs/experiments/package_boundary_audit_2026_09_29/scan.py` 및 같은 폴더의 `verify_findings.py`. 보고서 폴더에 결과만 쓴다. 실행 당시의 설치 상태를 읽으므로 수리 후에는 결과가 달라지는 것이 정상이다.
- 조사 시작 HEAD는 `2e096a83`. 조사 중 다른 작업이 business/cctv 등의 소스·어휘를 수정했고 이를 [concurrent_changes.json](concurrent_changes.json)에 따로 기록했다. 최초 예제 판정은 initial_example_checks.jsonl에 보존했다. 별도 작업의 수정·커밋은 이 감사에 포함하지 않는다.

결론적으로 **1회성 전수 조사는 유효했다.** 범용 자동 관문부터 만드는 대신, 성공 반환·저장 경로·현재 예제의 확인된 결함부터 수리하고 각각의 회귀 사례를 추가하는 편이 적절하다.

## 후속 수리 — 2026-09-29

위 본문과 JSONL은 **수리 전 감사 증거**다. 이후 사용자의 수리 요청으로 확정 8부류를 다음처럼 수정했다. `verify_findings.py`는 당시 결함을 재현하는 시험이므로 수리 후의 통과 기준으로 사용하지 않는다. 현재 회귀는 `backend/test_package_boundary_repairs.py`에 있다.

| ID | 반영 내용 | 수리 검증 |
|---|---|---|
| R1 | 기억 read가 content·source·text·메타데이터 Record를 반환한다. 표시용 전문과 출처를 보존하고 read의 반환 선언도 scalar로 바로잡았다. | 합성 DB와 실제 임시 기억 DB → 공개 execute → 판본 2 디코더 통과. 기존 평문 강제 시험도 새 계약으로 교체. |
| R2 | glob 실패를 success:false/error 봉투로 반환한다. | 공개 execute에 파일시스템 오류 주입 → ADAPTER_SHAPE가 아닌 TOOL 진단. |
| P1 | Playwright PDF가 지정 경로와 인쇄 옵션을 지킨다. Chrome PDF는 부작용 없이 명시적 미지원 오류를 반환한다. | 실제 로컬 Chromium에서 지정 경로 PDF 생성. Chrome은 인쇄 대화상자를 열지 않고 TOOL 실패·Playwright 사용 안내. |
| P2 | 두 브라우저 드라이버가 같은 browser_paths → ToolContext.resolve_output_path를 사용한다. Chrome도 file_path를 제공하며 이미지가 없으면 실패한다. | ~workspace·프로젝트 상대경로·파일명·거부 경로 대역 회귀, 실제 PNG 생성 확인. |
| P3 | CCTV 공개 진입점부터 내부 캡처까지 project_path를 전달하고 공통 쓰기 경로 해소기를 사용한다. | 대역 캡처로 중첩 경로·~workspace·파일명·기본 저장 위치·거부 경로 확인. 외부 CCTV 네트워크 호출 없음. |
| D1 | 스키마에 client/server를 반영했다. play(audio/video/client), download(server/client), relay(audio/video)는 실행 전에 모드를 검증한다. | client 재생·다운로드와 server 다운로드의 실제 컴파일·핸들러 전달 통과. 잘못된 op/mode는 부작용 전에 거절. |
| D3 | 부동산 필터를 items 명시·콜백 문법으로 교체했다. 만원 단위 설명은 유지한다. | README의 문장을 추출해 합성 데이터로 실행, 보증금 20,000만원 기준 행을 선택. |
| D4 | 사진 가이드를 현재 라이브 색인·날짜+GPS 필터·구조 필드·제한 사항으로 다시 작성했다. | 가이드 코드 블록을 현재 컴파일러로 검사. 기존 스캔 DB는 별도 REST 풍부창 자료라고 구분. |

- 공통 경로 규약을 재사용했으며 상시 전 패키지 자동 감사는 새로 추가하지 않았다.
- 브라우저 PDF 관련 용례 5개, 기억 read 관련 용례 6개는 결과를 그대로 반환하는 문장이라 본문 변경 없이 유지했다. 브라우저 자동 선택이 Chrome이면 이제 정직하게 실패하며, PDF는 Playwright로 열어 둔 페이지에서 실행해야 한다. 관련 계약 검토 원장을 갱신했다.
- system_essentials의 변경은 glob 실패 봉투 한 곳이다. read/fill/script의 경로 처리 변경이 없음을 대조한 뒤 공유 구현 지문을 갱신했다.
- 신규 회귀 26개와 기존 경로 회귀 12개 통과. 실제 임시 기억 DB를 포함한 추가 묶음 32개 통과(Chromium 시험 1개는 앞 묶음에서 통과).

### 최종 검증

- 전체 backend: **7,633 passed / 2 failed / 1 skipped**, 747.74초. 실패는 CCTV 내부 project_path의 사용자 인자 오인과 새 확장자 비교의 근거 주석 누락이었다. 각각 `_project_path` 배관 표기와 파일 형식 비교의 정당한 예외 주석으로 수정했다.
- 수정 후 영향 범위 전체(신규 수리·기존 경로·기억 봉투·Chrome 연결 진단·액션 인자 관문·값 판정 관문): **87 passed / 실패 0**, 15.09초. 실제 Chromium PDF·PNG 생성도 포함한다. 전체 12분 시험은 수정 후 다시 돌리지 않았으며, 전체 초록으로 기록하지 않는다.
- 어휘 빌드/`--check`, Android 번들, 경로·문자열 반환·은퇴 계약·층 관문 통과.
- 백엔드 공식 재시작 및 후속 자동 갱신 완료. ACTIVE / ready / accepting, 오류 없음. `/health` healthy, 정본 base_path 확인. 실행 코드 지문은 [repairs.json](repairs.json)에 기록한다.
- Chrome MCP·CCTV·유튜브 외부 서비스는 대역 검증이다. 실제 브라우저 산출 검증은 로컬 Chromium으로 수행했고, 개인 기억 조회나 실제 재생·다운로드는 실행하지 않았다.
