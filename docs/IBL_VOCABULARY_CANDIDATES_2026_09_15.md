# 일상 수요에서 고른 IBL 어휘 후보 10개

조사일: 2026-09-15. 정본 저장소의 빌드된 6노드·165액션, 중앙 선언,
설치 패키지 선언과 관련 핸들러·Gmail 확장·등록 스크립트를 대조했다.
조사 시 기준 커밋: `135895ac`. 아래 이름과 op는 **제안이며 실행 가능한 현재 계약이 아니다.**
어휘 신설·자동 등록·실계정 실행은 하지 않았다.

## 결론과 선정 기준

유망한 방향은 사용자가 이미 가진 문서·장부를 제대로 고치고, 실제 자료와 일정이 있는
외부 서비스에 접속하며, 일상 정보를 구조화된 값으로 가져오는 능력이다.

[NBER의 How People Use ChatGPT](https://www.nber.org/papers/w34255)는 실용적 안내·정보 탐색·글쓰기가
주요 사용 부류라고 보고한다. [Anthropic의 2026년 1월 Economic Index](https://www.anthropic.com/research/anthropic-economic-index-january-2026-report)는
글쓰기·편집과 사무 행정 사용도 분석한다. 이는 과제 분야를 고르는 근거이며, 아래 열 가지의
개별 빈도나 순위를 직접 입증하는 통계는 아니다. 제품별 이용자 편향도 있다.

우선순위는 (1) 다양한 사람·과제에 쓰일 가능성, (2) 현재 등록 계약의 공백,
(3) 다른 어휘와의 조합 가능성, (4) 공식 구현 경로를 함께 본 정성 판단이다.
새 낱말이 적합한 후보 7개와 기존 어휘 확장이 적합한 후보 3개를 구분했다.
셸·브라우저·등록 스크립트로 우회 가능한 것을 시스템 전체의 불가능으로 표현하지 않는다.
실제 호출·시간·토큰 절약 폭은 아직 미측정이다.

## 1. 기존 문서 편집 — `self:document` 후보

- **요구:** “이 제안서에서 납기와 금액만 바꾸고, 고친 부분은 변경 추적으로 보여 줘.
  표와 머리말은 그대로 둬.”
- **현재:** `self:read`는 DOCX를 읽고, `self:fill`은 `{{자리표시자}}`를 채운다.
  `self:edit`는 텍스트 교체이고 `table:document`는 새 산출물을 렌더한다.
  일반 DOCX의 문단·표를 찾아 구조적으로 편집하고 변경 추적·주석을 남기는 등록 계약은 확인되지 않았다.
- **최소 능력:** 블록 조회 → 대상 블록 편집 → 변경 내역·출력 파일 반환. 처음은 DOCX로 한정한다.
  HWP·Google Docs까지 지원한다고 선언하지 않는다.
- **구현 근거:** [Word change tracking API](https://learn.microsoft.com/en-us/javascript/api/word/word.changetrackingmode?view=word-js-preview).
  Word 호스트가 필요한 API 경로와 로컬 OOXML 편집 경로는 별도 구현 선택이다.
- **검증:** 내용 변경 외에 표·머리말·스타일의 보존 범위를 문서 표본과 렌더 비교로 확인한다.
  임의 문서의 모든 요소 보존을 처음부터 약속하지 않는다.

## 2. 엑셀 계산·범위 편집 — `self:sheet` 확장

- **요구:** “매출 장부에 다음 달 열과 수식을 추가하고, 합계가 실제로 계산됐는지 확인해 줘.”
- **현재:** `find/append/update`가 있으며 `=SUM(...)` 같은 수식 문자열 쓰기도 이미 된다.
  핵심 공백은 수식 입력 자체가 아니라 계산 엔진을 통한 재계산·범위 단위 조작·서식 지정이다.
  현재 읽기는 계산 캐시를 사용하며 캐시가 없을 때 수식 정보를 보완한다.
- **최소 능력:** 주소 범위 읽기·쓰기, 수식/서식 배치, 명시적 재계산과 계산 오류 반환.
  새 `excel` 액션을 중복 생성하기보다 기존 어휘의 계약을 확장한다.
- **구현 근거:** [Excel 범위 값·수식 API](https://learn.microsoft.com/en-us/office/dev/add-ins/excel/excel-add-ins-ranges-set-get-values),
  [Application.calculate](https://learn.microsoft.com/en-us/javascript/api/excel/excel.application?view=excel-js-1.9).
  실제 Excel 호스트 또는 다른 계산 엔진 연결이 필요하며, openpyxl 저장만으로 재계산을 보장하지 않는다.
- **검증:** 알려진 수식의 계산값·오류를 대조하고 변경 대상 밖 요소를 검사한다.

## 3. 클라우드 파일 접근 — `self:cloud_file` 후보

- **요구:** “구글 드라이브에서 최근 수정한 제안서를 찾아 내려받고 이 견적서와 비교해 줘.”
- **현재:** 로컬 `file_find/read`와 URL `download`가 있다. 로그인된 Drive의 파일 id·폴더·
  권한·문서 내보내기를 처리하는 전용 IBL 계약은 확인되지 않았다. 로컬 동기화 사본은 기존 경로로 가능하다.
- **최소 능력:** 한 공급자의 검색·상세·다운로드/문서 내보내기부터. `id/name/mimeType/modifiedTime/url`
  등의 items를 내어 기존 read·notebook·문서/표 어휘로 잇는다. 업로드와 공유 변경은 후속 범위다.
- **구현 근거:** [Drive 파일 검색](https://developers.google.com/workspace/drive/api/guides/search-files),
  [다운로드·내보내기](https://developers.google.com/workspace/drive/api/guides/manage-downloads).
- **검증:** 같은 이름의 파일 구분, 페이지네이션, 권한 거절, Google 문서와 바이너리 파일의 차이를 확인한다.

## 4. 외부 캘린더와 빈 시간 — `self:manage_events` 확장

- **요구:** “내 캘린더와 공유받은 동료 캘린더에서 다음 주 30분 빈 시간을 찾아 줘.”
- **현재:** SQLite 기반 일정·자동 실행 이벤트의 CRUD가 있다. 외부 Calendar 계정과
  free/busy 조회를 나타내는 provider/calendar_id 계약은 확인되지 않았다.
- **최소 능력:** 외부 일정 조회와 바쁜 구간 반환. 공통 빈 시간 계산은 기존 표현·스크립트로
  먼저 구성하고, ‘회의 잡기’ 전체를 별도 원샷 낱말로 만들지 않는다.
- **구현 근거:** [Google Calendar freebusy.query](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query),
  [이벤트 생성](https://developers.google.com/workspace/calendar/api/guides/create-events).
- **검증:** 종일 일정·시간대·반복 일정·접근 권한 차이를 확인한다. 접근할 수 없는 상대의
  캘린더를 빈 시간으로 취급하지 않는다. 시간 지정 지원 범위가 다른 운영 스케줄러와 계약을 구분한다.

## 5. 메일함 관리 — `others:mailbox` 후보

- **요구:** “답장 초안을 메일함에 저장하고, 처리한 안내 메일은 분류해서 보관해 줘.”
- **현재:** `channel_read/channel_send`와 대화 조회가 있고 첨부 발송 구현도 있다.
  Gmail 확장에는 읽음 표시도 있다. 부족한 것은 초안 CRUD와 라벨·보관을 안정된 메시지 id로
  조작하는 IBL 계약이다. ‘이메일을 못 보낸다’는 진단은 틀리다.
- **최소 능력:** 초안 저장·조회·수정, 라벨 추가/제거·보관. 기존 읽기·발송을 중복 구현하지 않는다.
  초안 본문 작성은 기존 AI 어휘가 맡는다.
- **구현 근거:** [Gmail drafts](https://developers.google.com/workspace/gmail/api/guides/drafts),
  [Gmail labels](https://developers.google.com/workspace/gmail/api/guides/labels).
- **검증:** 대역/시험 계정에서 초안 id·메일 id, 라벨 보존, 이미 보관한 메시지의 재요청을 확인한다.
  실제 계정 초안 저장도 실제 변경이다. 발송 없이 작성 검증이 가능하다는 사실과 격리를 혼동하지 않는다.

## 6. 사용자의 할 일 목록 — `self:tasks` 후보

- **요구:** “내 To Do에서 이번 주 마감인데 아직 끝나지 않은 일을 모아 줘.”
- **현재:** 에이전트 계획용 `todo_write`, AI 실행 목표 `self:goal`, JSON 상태 원장 `self:ledger`가 있다.
  사용자가 별도 서비스에서 관리하는 업무 목록의 동기화·완료 처리는 다른 접근 능력이다.
- **최소 능력:** 서비스 목록·작업 조회, 생성·수정·완료. 목록/작업 id, 기한·완료 상태를 items로 반환한다.
  첫 공급자는 Microsoft To Do 같은 명확한 API 한 곳으로 좁힌다. 공동 담당자 기능은 공급자별로 검토한다.
- **구현 근거:** [Microsoft Graph To Do API](https://learn.microsoft.com/en-us/graph/todo-concept-overview).
- **검증:** 기한 없는 작업·시간대·반복 작업·완료 상태 갱신을 시험한다. 로컬 할 일 원장을
  하나 더 만드는 것만으로 외부 업무 관리 공백이 해결됐다고 하지 않는다.

## 7. 기존 PDF 가공 — `self:pdf` 후보

- **요구:** “서류에서 필요한 페이지만 뽑아 합치고, 연락처를 지운 제출용 PDF를 만들어 줘.”
- **현재:** PDF 읽기·표 추출·폼 채우기·렌더·새 PDF 생성은 있다.
  기존 PDF 페이지의 병합/선택/순서 변경과 실제 내용 삭제를 묶은 등록 계약은 확인되지 않았다.
- **최소 능력:** 페이지 선택·병합·회전부터. 지정 영역 내용 삭제는 별도 검증을 갖춘 확장으로 한다.
  개인정보 위치 판단은 사용자 지정 또는 기존 AI/OCR 능력의 결과를 받아 수행한다.
- **구현 근거:** [PyMuPDF Document](https://pymupdf.readthedocs.io/en/latest/document.html),
  [Page redactions](https://pymupdf.readthedocs.io/en/latest/page.html).
- **검증:** 순서·페이지 수·렌더를 확인하고, 삭제 작업은 추출 텍스트·이미지와 필요한 메타데이터도
  검사한다. 검은 사각형을 덧그린 것만으로 정보 삭제 성공이라고 하지 않는다.
  로컬 결정론 스크립트로 먼저 검증하기 쉬운 후보이며 반복 이득이 작으면 스크립트로 유지한다.

## 8. 대중교통 길찾기 — `sense:navigate_route` 확장

- **요구:** “서울역에서 약속 장소까지 대중교통으로 가는 길 중 환승이 적은 것을 골라 줘.”
- **현재:** 카카오 자동차 길찾기와 장소 검색은 있다. 현재 핸들러는 자동차 경로 API를 호출한다.
- **최소 능력:** 이동수단 축을 추가해 대중교통의 구간·환승·도보 연결·소요시간을 구조화한다.
  공급자가 주지 않는 실시간 도착/배차 정보는 추정으로 채우지 않는다.
- **구현 근거:** [ODsay 대중교통 API](https://lab.odsay.com/guide/guide).
  도시간 경로에서는 터미널까지/터미널에서 목적지까지의 연결 구간을 추가로 구해야 한다.
- **검증:** 전체 구간 누락, 자동차 응답으로의 조용한 대체, 시간 단위 혼동을 잡는다.
  한국 공급자 한 곳의 지원을 전세계 지원으로 표현하지 않는다.

## 9. 채용 공고 조회 — `sense:job` 후보

- **요구:** “내 경력으로 지원할 만한 지역 내 채용 공고를 찾고 마감일과 자격요건을 비교해 줘.”
- **현재:** 일반 웹 검색, 외주 서비스 검색 `sense:freelance`, 지원사업 `sense:startup`은 있다.
  외주 서비스를 구매하는 목록과 구직자가 지원할 채용 공고는 다른 데이터다.
- **최소 능력:** 한 공급자의 채용 목록/상세를 공고 id·기업·근무지·요건·마감일·원문 링크가 있는
  items로 반환한다. 적합도 판단·이력서 작성·신규 공고 감시는 기존 AI/table/since/trigger와 조합한다.
- **구현 근거:** [고용24 채용정보 Open API](https://m.work24.go.kr/cm/e/a/0110/selectOpenApiSvcInfo.do?fullApiSvcId=000000000000000000000000000000%5E000000000000000000000000000001%5E000000000000000000000000000003).
  인증키·출처 표시·제공사이트 연결 조건을 지키며 공급자 밖 공고까지 포함한다고 주장하지 않는다.
- **검증:** 마감·상시채용·요건 미기재를 구분하고, 같은 공고의 중복·갱신을 구분한다.
  웹 검색보다 구조화 계약이 실제로 절약하는 과정이 적다면 신설 우선순위를 낮춘다.

## 10. 택배 배송 상태 — `sense:shipment` 후보

- **요구:** “이 운송장 세 개 중 아직 도착하지 않은 것과 마지막 이동 시각을 알려 줘.”
- **현재:** 상품 가격·중고 검색, 메시지 읽기는 있지만 배송사·운송장으로 이동 사건을 얻는
  등록 어휘는 확인되지 않았다.
- **최소 능력:** 배송사와 운송장 → 상태·발생 시각·이동 사건·조회 시각. 주문 메일에서 운송장
  추출은 기존 struct가, 반복 확인·알림은 기존 trigger/since가 담당한다.
- **구현 근거:** [Delivery Tracker track API](https://tracker.delivery/en/docs/api-schema/operations/queries/track),
  [인증을 포함한 클라이언트 예제](https://tracker.delivery/en/docs/client-libraries/nodejs-graphql-request).
- **검증:** 미등록 번호·이력 없음·조회 실패를 ‘미도착’과 구분한다. 배송사 지원과 인증 조건은
  실제 연결 시 확인한다. 판매점 주문 관리·반품 접수까지 되는 어휘로 확대하지 않는다.

## 기존 능력이 있어 이번 열 개에서 제외한 것

- 요약·번역·회의록 작성·일반 튜터링: `self:ask`, `table:ai/brief`, `sense:listen`의
  조합을 먼저 시험한다. 새로운 이름만으로 별도 능력이 생기지 않는다.
- 영수증/문서의 항목 추출: `self:struct`, `engines:image_read`와 재무/건강 ingest를 먼저 검증한다.
- 새 문서·슬라이드 생성: `table:document`, `self:slide/deck`가 이미 있다.
- 메일 발송·주소록·일정 생성·엑셀 수정 자체: 이미 있다. 위 후보는 구체적으로 빠진 계약만 제안한다.
- 영상 자르기·파일 압축처럼 로컬 라이브러리로 해결하는 능력도 가능하지만, 먼저 등록 스크립트의
  재사용 비용과 비교한다. ‘흔한 일’이라는 이유만으로 모든 작업을 기본 카탈로그에 추가하지 않는다.

## 다음 판정 방법

각 후보에 대해 위 자연어 과제와 해법을 미리 주지 않은 변형 과제를 실제로 수행한다.
현재 조합·스크립트/브라우저 경로와 후보 구현을 같은 입력으로 비교해 다음을 본다.

1. 실제 자료/결과에 접근하거나 편집할 수 있는 범위가 넓어졌는가.
2. 정답성과 비대상 데이터 보존이 유지되는가.
3. 전체 모델 호출·입력/출력 토큰·벽시계·재작업이 줄었는가.
4. 다른 과제에서도 같은 계약이 재사용되는가.

어휘 정의와 공급자 드라이버를 분리하고, 조회는 items·파일 작업은 출력 참조와 변경 내역을
반환한다. 제공사별 사실은 데이터/개인 사전에 두며 표준 문법은 이번 후보 때문에 바꾸지 않는다.
외부 쓰기는 상상행동 가이드의 격리 조건을 충족한 시험 환경에서 검증한다.

## 로컬 근거 지도

- 전체 어휘: [빌드 카탈로그](../data/ibl_nodes.yaml), [중앙 self](../data/ibl_nodes_src/self.yaml),
  [중앙 others](../data/ibl_nodes_src/others.yaml).
- 문서/장부: [system_essentials 선언](../data/packages/installed/tools/system_essentials/ibl_actions.yaml),
  [office_ops](../data/packages/installed/tools/system_essentials/office_ops.py),
  [sheet_ops](../data/packages/installed/tools/system_essentials/sheet_ops.py).
- 메일: [channel_engine](../backend/ibl/channel_engine.py),
  [Gmail 확장](../data/packages/installed/extensions/gmail/gmail.py).
- 내부 todo: [system_essentials handler](../data/packages/installed/tools/system_essentials/handler.py)의
  에이전트별 todo_state 경로와 todo_write 선언.
- 교통: [location-services 선언](../data/packages/installed/tools/location-services/ibl_actions.yaml),
  [자동차 길찾기 구현](../data/packages/installed/tools/location-services/handler.py).
- 중복 점검: 설치/미설치 패키지 선언, [등록 스크립트](../data/scripts/registry.yaml).

공식 문서 확인은 구현 경로가 존재한다는 근거다. 이 조사에서는 외부 계정 인증·API 호출·
문서 변환을 실제 수행하지 않았으므로 연동 성공이나 성능 향상을 측정한 보고서가 아니다.
