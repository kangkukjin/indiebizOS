# 공통 기반 위의 앱 구성 — 코딩·문서·스프레드시트 재계획

작성일: 2026-10-05. 상태: **준비(§6-1~3) 집행 완료, 앱별 구성(§6-4~5)은 다음 작업.** 사용자가 같은 날
"필요한 걸 준비해봐"로 §7 판정 항목(낱말 신설·뷰 낱말·이벤트·은퇴 방향)을 승인했다.

집행 결과(2026-10-05):
- 몸: `backend/services/workspace_sessions.py` — document/sheet/code 어댑터 위 공통 계약(office_sessions·coding_workspace 재사용). 회귀 `backend/test_workspace_sessions.py`.
- 어휘: `[self:workspace]` 12 op(system_essentials `essentials_workspace.py`). `self:document` 는 inspect/edit 만, `self:sheet` 는 파일 op 6개만 남김(세션 op 25개 흡수). 가이드 `data/guides/workspace.md`, 용례 3건 이관·재검토 ack.
- 표면 언어: 뷰 `engine`(`frontend/src/components/generic/prims-engine.tsx`, 원격은 열람 강등) + 뷰-이벤트 `selection`/`saved` + "이벤트 페이로드는 $변수로 남는다(keep)" 규약. 검증기·문서 2줄·렌더러 플랜 갱신. 회귀 `backend/test_app_view_engine.py`.
- 관용구: `data/idioms/workspace_seeds.json` 6정의+6용례(선택교정·검토본저장·범위제안·과제열기·파일고치기·검토반영) 해마 등록(id 4924~4929, always_on 아님).
- 아직 안 한 것: 계기 선언 3장(§4), 기존 React 작업 공간·HTTP 작업표 은퇴(§5 은퇴 행), AI 원샷 함수 은퇴. 지금은 옛 표면과 새 어휘가 같은 서비스 위에 공존한다.
독자: 세 앱을 다시 구성할 구현자와 설계 검토자.
전제(사용자, 2026-10-05): *앱 4개보다 중요한 것은 앱의 구성이다. 앱을 만들면서 필요한 IBL
어휘나 문법이 있었다면 그것을 추가해서라도 공통 기반 위에 앱을 만들었어야 한다.*

판정 기준은 [IBL 진화 목적](IBL_EVOLUTION_PURPOSE.md)과 [IBL 명세](../data/system_docs/ibl.md)의
"언어의 경계"·"표현 언어의 층위"·"뷰 어휘 승격 4기준"이다. 결정화 사다리(용례 → 관용구 →
워크플로 → 가이드)와 "능력은 어휘, 계기는 표현만"(custom_app_instrument.md 철칙 0)을 따른다.

## 0 무엇이 잘못됐나 (2026-10-02~05 실측)

| 앱 | 코드 | 자기 저장소·세션 | HTTP 작업 | 어휘 | 관용구 |
| --- | --- | --- | --- | --- | --- |
| 코딩 | 약 1,160줄 | coding_store·coding_workspace | 10 경로 | 없음 | 0 |
| 문서 | 약 1,800줄 + RHWP 40MB | document_store·document_workspace (+office_*) | 19 경로, 닫힌 작업표 25 | `self:document` 16 op(서비스 1:1 포장) | 0 |
| 스프레드시트 | 약 1,620줄 | spreadsheet_workspace (+office_*) | 별도 경로 | `self:sheet` 세션 op 9 | 0 |

세 설계 문서가 모두 "UI는 서비스 API를 직접 호출한다. AI는 기존 op를 확장해 같은 서비스에
접근"으로 시작한다. 서비스가 먼저 생기고 어휘가 그 모양을 되비췄다. 그래서 앱마다 저장소·세션·
작업표·React 작업 공간이 따로 생겼고, 앱 안의 AI 수정은 인지 파이프라인 밖의 원샷 모델 호출
(`document_workspace.generate_selection`)로 고정됐다. 관용구는 세 앱 모두 0건이다.

## 1 세 앱을 같은 축으로 분해한다

앱이 다르다고 믿었던 것은 **자료의 종류와 엔진**뿐이다. 나머지 축은 셋이 같다.

| 축 | 코딩 | 문서 | 스프레드시트 | 공통인가 |
| --- | --- | --- | --- | --- |
| 자료 | git 저장소·파일 | DOCX/HWP/PDF/MD/TXT… | XLSX/ODS/CSV | 종류만 다름 |
| 작업 공간 | 과제별 worktree, 파일 지문 | 세션·epoch·스냅샷·조건부 저장·버전·복구 | 같음 | **공통** |
| 읽기 | 파일·diff | 문단·표·페이지 | 범위·수식·계산값 | 어휘 있음 |
| 고치기 | 텍스트 편집·AI 실행 | 선택 교정·엔진 편집 | 범위 쓰기·엔진 편집 | 공통 + 엔진 바인딩 |
| 검증 | 테스트·실행 출력 | 렌더 확인 | 재계산 | 어휘 있음 |
| 반영 | diff 검토 → 커밋 | 원본 저장·사본·내보내기 | 같음 | **공통** |
| AI | 실행자(네이티브 가능) | 선택 교정 제안 | 범위 변경 제안 | **공통**(시스템 AI·table:ai) |
| 표면 | diff·대화·실행 출력 | 엔진 편집기·검토 | 엔진 편집기·검토 | 뷰 어휘 + 엔진 뷰 1종 |

결론: **몸 하나(범용 작업 공간) + 어휘 한 낱말(작업 공간) + 엔진 어댑터 종류별 + 뷰 낱말 하나(엔진
표면) + 앱별 관용구 묶음 + 계기 선언 한 장**이면 세 앱이 선다. 네 번째 앱부터는 어댑터(필요할
때만)·관용구·계기 선언만 는다.

## 2 지금 언어에 이미 있는 것 (새로 만들지 않는다)

- 읽기·쓰기: `[self:read]`(텍스트·PDF·DOCX·XLSX·HWP, blocks·tables), `[self:write]`, `[self:edit]`(문자열·줄 범위), `[self:grep]`, `[self:file_find]`, `[self:fill]`(PDF 폼·DOCX 자리표시자).
- 생성·조판: `[table:structure]`(문서 IR), `[table:document]`(html/pdf/docx/pptx/typst), `[table:spreadsheet]`, `[engines:render]`(docx 미리보기).
- 시트 파일 작업: `[self:sheet]`의 find/append/update/range/range_write/calculate — 파일 단위 능력은 유지.
- 실행·검증: `[self:script]`(등록·run·status 유한 대기), `run_command`, 결과 참조(`$ref`·read_result).
- 변화·반영: `[self:body]`의 changes/diff/file/writes/**commit**(임시 인덱스·pre-commit 관문).
- AI 낱말: `[table:ai]`(행 단위 의미 변환, 기준 있음), `[table:brief]`, `[table:judge]`. 시스템 AI 위임 `[others:delegate]{scope:system, mode:sync|async}`(2026-10-05 수리로 접수증·대기·봉투가 선다).
- 관용구 층: `[def:이름](인자){…}`, 해마 관용구 회상, `data/workflows/*.yaml`(IBL 원문 보존), 가이드.
- 표면 언어: 뷰 15종(metric·kv·card_list·form·editable_list·blocks·thread·list_action·…), 폼 11종, textarea `ai_dock`(선택 텍스트에 대한 임시 AI 제안·반영), 뷰 이벤트 4종(지도용). 선언형 계기 정본 사례 `data/instruments/report.yaml`("어휘 없는 순수 매니페스트").
- 코드(몸): `office_sessions`·`office_store`·`office_resources`(자료 ID·세션·스냅샷·조건부 저장·복구·사건 원장), 과제 원장 `pursuit_ledger`, 엔진 I/O 경계(`api_document_engine`의 ticket·callback), RHWP·ONLYOFFICE 바인딩, OCR, 형식 변환, git worktree 운영(`coding_git`).

## 3 빠졌던 것 — 층별로

### 3-a 몸(코드, 하부구조) — 판정 불요, 수리로 집행
**범용 작업 공간 하나.** `office_sessions`+`office_store`를 자료 종류 무관의 작업 공간으로
승격한다. 책임: 자료 등록(`resource_id`)·단독 작성 세션·스냅샷(`revision`)·제안·조건부 저장
(`expected_revision`·`operation_id` 멱등)·버전·복구·사건 원장(`sequence/after/next`).
`coding_store`·`document_store`는 여기로 흡수하고 과제 의미는 기존 `pursuit_ledger`가 유지한다.

**어댑터 계약(설계 문서가 이미 정한 것)**: `probe/open/capabilities/barrier/read/apply/flush/export/close`.
종류별 바인딩: office(ONLYOFFICE)·hancom(RHWP)·pdf·source(TXT/MD/HTML/LaTeX)·sheet 엔진·**git worktree**
(코딩의 과제 작업 공간도 "자료=저장소, 세션=worktree, 스냅샷=커밋 지문, 저장=반영"으로 같은 계약에
맞는다). 형식 내부 DOM은 어댑터가 소유하고 언어로 새지 않는다.

### 3-b 어휘 — 언어 개정, 판정 필요
**`[self:workspace]` 한 낱말**(이름은 판정). op는 의도 고도 9개로 닫는다:
`open`(자료 등록, 종류 자동 판별) · `snapshot` · `read`(selector: 문단/범위/파일·줄/diff) · `propose`(selector+교체 또는 변경안) ·
`apply` · `save`(expected_revision) · `export` · `versions`/`restore` · `close`.
반환은 공통 통화: `{resource_ref, revision, selector, items|blocks|table}`. **`session_id·client_id·
epoch·operation_id`는 언어에 나오지 않는다** — 몸이 행위자 봉투(principal·task)에서 세션을 해소하고
멱등 키는 호출 신원 지문으로 만든다. 이것이 이음매 고도를 올리는 핵심이다.

이 낱말은 **어휘를 늘리는 것이 아니라 줄인다**: `self:document`의 세션 op 14개와 `self:sheet`의 세션
op 9개, 코딩 HTTP 작업 25개를 흡수한다. `self:document`는 inspect/edit(DOCX 사본 편집)만, `self:sheet`는
파일 작업 op만 남긴다. 새 코어 노드·문법은 없다.

**AI 제안은 새 낱말이 아니다.** 선택 교정은 `$sel=[self:workspace]{op:"read", selector}` →
`[table:ai]{instruction, criteria}` 또는 `[others:delegate]{scope:"system", mode:"sync"}` →
`[self:workspace]{op:"propose"}`. 앱 속 원샷 호출 함수(`generate_selection`)는 은퇴한다. 시스템 AI가
회상·평가·증류를 지나므로 앱 안의 AI 수정도 몸의 경험이 된다.

### 3-c 표면 언어 — 언어 개정(뷰 어휘), 판정 필요
**뷰 낱말 `engine` 1종**: 외부 편집 엔진 표면을 `resource_ref + capabilities`로 바인딩한다(iframe·
ticket·callback은 기존 엔진 I/O 경계 재사용). 승격 4기준 대조: ① escape 3개(OfficeDocumentEditor·
HwpDocumentEditor·SpreadsheetWorkspace의 편집기) 은퇴 ✓ ② 통화(resource_ref) 소비 ✓ ③ 3표면 — 데스크탑·
원격은 편집, 폰은 열람과 제한 편집(엔진 capabilities가 결정) ✓ ④ 레이아웃이 아니라 데이터·상호작용 계약 ✓.

**뷰 이벤트 2종 추가**: `selection`(엔진·blocks·editable_list에서 선택 범위를 `selector` 통화로
내보냄 — 코딩 diff 줄·문서 문단·시트 범위가 같은 모양) · `saved`(엔진 저장 콜백 도착). `ai_dock`는
selection 기반으로 일반화하고 `$sel`을 주입한다. 현재 이벤트 어휘 4종이 전부 지도용이라 이 둘은
언어 개정이다. 빌드의 뷰-어휘 문서-동기 가드가 두 문서 줄을 대조하므로 같은 커밋에서 갱신한다.

코딩의 diff 검토는 새 뷰가 아니다: `[self:body]{op:"diff"}`·workspace `read{selector: diff}`의 결과를
`blocks`(code 블록)로 렌더하고 `selection`으로 줄을 고른다. 실행 출력은 `thread`, 과제·변경 파일은 `list_action`.

### 3-d 관용구·가이드 — 데이터, 판정 불요
앱마다 흐름을 `[def:]`로 쌓고 가이드 한 장이 레시피를 맡는다. 첫 묶음(이름은 저술 때 정함):
- 문서: `선택교정(resource, selector, 지시)` · `양식채우기검토(template, data)` · `검토본저장(resource)`.
- 스프레드시트: `범위제안적용(resource, range, 지시)` · `재계산검증(resource)` · `연결보고서갱신(doc, sheet, range)`.
- 코딩: `과제열기(repo, goal)` · `고치고검증(resource, 지시, 명령)` · `검토반영(resource, message)`.
가이드: `document_edit.md` 확장, `sheet_session.md`, `coding_task.md`. 해마 시딩은 `add_examples_batch` 단일 경로.

## 4 세 앱의 구성 (각 앱 = 계기 선언 1장 + 관용구 + 가이드)

```yaml
# data/instruments/document.yaml — 형(型)만 보인다. 능력은 전부 어휘·관용구.
instrument: document   icon: 📄   name: 문서   order: 12
modes:
  - name: 열기        inputs: [{key: path, type: files}]
    action: '[self:workspace]{op:"open", path:"$path"}'
    view:   [{type: engine, ref: '{data.resource_ref}', on: {selection: set:$sel, saved: refresh}}]
  - name: 고치기      inputs: [{key: 지시, type: textarea, ai_dock: {action: '[fn:선택교정]{resource:$resource, selector:$sel, 지시:"$dock"}'}}]
  - name: 검토·저장   action: '[self:workspace]{op:"versions", resource:$resource}'
    view:   [{type: list_action, button: {label: 복구, action: '[self:workspace]{op:"restore", …}'}},
             {type: list_action, button: {label: 원본 저장, action: '[fn:검토본저장]{resource:$resource}', confirm: true}}]
```

- **문서 앱**: 위 틀. 엔진=office/hancom/pdf/source 어댑터. OCR·변환은 기존 어휘(`self:read{ocr}`·
  `table:document`)로 모드 하나씩. 강의 재료 전달은 `[others:delegate]`나 `resource_ref` 전달.
- **스프레드시트 앱**: 같은 틀. 엔진=sheet 어댑터. 범위 읽기·제안은 `self:workspace`(selector=range),
  파일 단위 작업은 `self:sheet`, 정리·집계는 `table` 변환자. 문서에 넣는 표는 `resource_ref+revision+range` 고정 참조.
- **코딩 앱**: 같은 틀, 엔진 뷰 없음. 자료=저장소(git worktree 어댑터). AI 실행은
  `[others:delegate]{scope:"system"|agent, mode:"async"}`에 실행자 프로필(네이티브 CLI 허용)을 넘기고 접수증·
  상태 조회로 진행을 본다 — "코딩 중 IBL 비강제"는 **실행자** 원칙이고 **앱 구성**은 IBL이다. 둘은 모순이 아니다.
  검증은 `[self:script]`/`run_command`, 검토는 diff `blocks`+`selection`, 반영은 `[self:body]{op:"commit"}`.
  자기수리는 기존 REPAIR 격리·RED 경로 그대로.

## 5 기존 코드의 처분

| 처분 | 대상 |
| --- | --- |
| 유지(하부구조) | ONLYOFFICE·RHWP 바인딩, 엔진 I/O 경계(ticket·callback), OCR, 형식 변환·HWP·PDF, `coding_git`, `office_store`, `pursuit_ledger` |
| 흡수 | `coding_store`·`document_store` → 작업 공간 저장소; `coding_workspace`·`document_workspace`·`spreadsheet_workspace` → 어댑터 + 범용 작업 공간 |
| 은퇴 | 세 React 작업 공간과 편집기 escape 3개 → `GenericInstrument`; `api_documents` 닫힌 작업표 25·`api_coding` 과제 경로 → `/ibl/execute` + 엔진 I/O 경로 몇 개; `generate_selection`; `self:document` 세션 op 14·`self:sheet` 세션 op 9 |

예상 잔존 코드는 세 앱 합계 약 5,600줄 중 엔진·형식 바인딩 2,000줄 안팎이다(실측은 집행 뒤).
지금 기능을 잃지 않는 것이 조건: 세 앱의 기존 회귀(문서 44·시트·코딩 인수)를 새 경로로 모두 통과시킨다.

## 6 실행 순서 (의존 관계)

1. **몸 통합**: `office_sessions`를 범용 작업 공간으로 승격, 어댑터 6종(office·hancom·pdf·source·sheet·git) 계약 고정. 기존 HTTP는 그대로 둔 채 내부만 바꾼다.
2. **언어 개정(판정 뒤)**: `[self:workspace]` 신설·흡수, 뷰 `engine`·이벤트 `selection`/`saved`. 빌드 `--check`·문서 7표면·뷰-어휘 가드 같은 커밋.
3. **관용구·가이드·시딩**: §3-d. 해마 회상에 잡히는지 `search_hybrid`로 확인.
4. **계기 선언 3장**: `data/instruments/{document,spreadsheet,coding}.yaml`. 데스크탑·원격·폰 파리티 확인.
5. **기존 표면 은퇴**: React 작업 공간·HTTP 작업표·원샷 AI 함수 제거. 회귀 전부 새 경로.
6. **검증**: 세 앱 기존 시험 + 폰 표면 열람 + 종합 회귀. 성능(토큰·시간)은 동작 확인과 분리해 보고.

## 7 판정 요청 (언어 개정·파괴적 변경만)

1. `[self:workspace]` 신설과 이름, `self:document`·`self:sheet` 세션 op 흡수(어휘 순감).
2. 뷰 낱말 `engine`, 뷰 이벤트 `selection`·`saved` 추가(표면 언어 개정).
3. 세 React 작업 공간·편집기 escape·앱별 HTTP 작업표 은퇴(기존 표면 파괴).
4. 코딩 앱 원칙의 재서술: "실행자는 네이티브 허용, 앱 구성은 IBL".

판정이 나지 않은 동안에도 §6-1(몸 통합)은 결함 수리 범주라 바로 집행할 수 있다.

## 8 위험과 미측정
- 엔진 뷰를 generic 표면에 올릴 때 보안 경계(소유자 전용·origin 검사·ticket)는 기존 코드를 그대로 쓴다. 폰 표면은 capabilities가 허용하는 범위만.
- 관용구는 해마에 용례가 있어야 회상된다 — 시딩 없이 가이드만 두면 결정화 절반이다(crystallized-but-unrouted).
- 성능은 측정하지 않았다. 구성 변경이 빨라졌다는 뜻이 아니다.
