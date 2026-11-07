# 작업 공간 — [self:workspace]

문서(TXT/MD/HTML/LaTeX 원문, DOCX/PDF/HWP), 스프레드시트, 코딩(프로젝트 폴더)을 **같은 계약**으로
연다. 종류는 자료가 정한다 — 호출자는 `resource` 하나만 들고 다닌다. 세션·epoch·작업 ID 같은
배관은 몸이 숨긴다. 접수(`state: queued`)는 완료가 아니다.

## 한 흐름

```ibl
$w = [self:workspace]{op:"open", path:"~workspace/outputs/보고서.md"}
$r = [self:workspace]{op:"read", resource:$w.resource, selector:{start:0, end:400}}
$p = [self:workspace]{op:"propose", resource:$w.resource, selector:{start:0, end:400, selected_sha256:$r.selected_sha256}, replacement:"고친 문단"}
[self:workspace]{op:"apply", resource:$w.resource, proposal:$p.proposal}
[self:workspace]{op:"save", resource:$w.resource}
```

- `open` → `resource`(자료 ID)·`kind`·`capabilities`·`session`(어느 창이 쥐고 있는지). 같은 경로는 같은 자료.
- `read` → `snapshot`(고정 증거)·`text`/`table`/`items`. `selector` 생략은 전체. 사무 문서(DOCX/PDF/HWP)는
  읽기 **투영**(편집 주소가 아니다 — `projection: true`).
- `propose` → `proposal`. 스냅샷에 고정되므로 그 뒤 사람이 고치면 `apply` 가 충돌로 거절한다. 다시 읽고 제안한다.
- `apply`·`save`·`export`·`restore`·`close` 는 **작성 창이 세션을 쥐고 있으면 그 창의 `client`** 만 된다.
  창이 없으면 행위자 신원으로 세션을 얻는다. 빼앗지 않는다.
- `save` 는 기대 원본 버전을 확인하고 원본을 교체한다. 외부에서 바뀌었으면 거절하고 초안을 보존한다.
- `versions`/`restore(revision)`/`recover`/`capabilities` 는 읽기·복구.

## 종류별 selector

| kind | read | propose |
|---|---|---|
| document(원문) | `{start, end}` 문자 범위 → `selected_sha256` | `{start, end, selected_sha256?}` + `replacement` |
| document(DOCX/PDF/HWP) | `{offset, limit, pages, tables}` 읽기 투영 | 앱의 편집 표면에서(엔진 bookmark). 서버 제안 없음 |
| sheet | `{sheet, range}` → `table`(값·수식·`calc_status`) | `{sheet, range}` + `values`(같은 행·열) + `kind: set_values|set_formulas` |
| code | `{path, start_line, end_line}` / `{diff: true}` / `{files: true}` / `{project: true}`(목표 문서·실행 방법·변경 요약) · 자료 없이 `kind:"code", selector:{projects:true}` = 프로젝트 목록 | `{path, start_line?, end_line?}` + `replacement`(줄 범위 교체·전체 본문·`null`=삭제) |

- 시트 `snapshot` 은 편집창 엔진의 응답을 `wait`(≤30초) 기다린다. 닫힌 파일은 저장본에서 고정 투영을 만든다
  (`source: saved_file`). `apply`·`save` 는 편집기에 **접수**된다 — 영수증을 확인한다.
- 코딩 `open` 은 **프로젝트 폴더**를 연다(git 이 없으면 조용히 init, 목표 문서 `목표.md`가 없으면 설명·실행법을 추론해 만들며 `goal`이 설명에 우선한다).
  `save` 는 **기록** — `message` 필수, 폴더의 모든 변경을 한 커밋으로(바뀐 것이 없으면 `state: clean`). `versions` 가 기록 목록,
  `restore{revision, path?}` 가 그 기록으로 되돌리기(되돌리기 전 상태를 먼저 기록해 둔다). AI 코딩은 이 낱말이 아니라
  `[others:delegate]{scope:"system", role:"coding", context:{project: $path, resource: $resource}}` — 실행 에이전트가 목표 문서대로
  짓고 진행 기록에 한 줄을 남긴다. 프로젝트 명령 실행(개발 서버)은 코딩 앱 실행 탭(엔진 I/O)의 몫.
  콘솔 프로그램이 값을 요청하면 출력 아래 입력칸에 적고 Enter 또는 **입력 보내기**를 누른다.
  입력 연결이 없다는 안내가 나오면 중지한 뒤 다시 실행한다.

코딩 프로젝트의 `[self:workspace]{op:"close", resource:$resource, unregister:true}`는 등록만 해제한다.
폴더·파일·git 기록·진행 중인 실행은 보존한다. 목록과 기본 폴더 자동 발견에서 제외되고,
같은 폴더를 `open`하면 재등록된다. `unregister`를 생략한 닫기는 등록을 유지하며,
문서·시트에는 `unregister:true`를 지원하지 않는다.

## AI 제안은 새 낱말이 아니다

```ibl
$r = [self:workspace]{op:"read", resource:$w.resource, selector:{start:$sel.start, end:$sel.end}}
$fix = [table:ai]{items:[{text:$r.text}], instruction:"문장의 뜻을 유지하며 자연스럽게 다듬어라. 설명 없이 본문만.", schema:"text", input_fields:["text"]}
[self:workspace]{op:"propose", resource:$w.resource, selector:{start:$sel.start, end:$sel.end, selected_sha256:$r.selected_sha256}, replacement:$fix.items[0].text}
```

판단이 필요한 긴 수정은 `[others:delegate]{scope:"system", mode:"sync", message:…}` 로 시스템 AI 에게 맡기고
돌아온 본문을 `propose` 에 넣는다. 어느 쪽이든 적용·저장은 사람이 보는 표면에서 한다.

## 경계

- DOCX 사본 편집(변경 추적·주석)은 `[self:document]{op:"edit"}`, 새 문서 생성은 `[table:document]`, 양식은 `[self:fill]`,
  엑셀 파일 작업(행 찾기·추가·범위 쓰기·재계산)은 `[self:sheet]`. 이 낱말은 **열린 자료의 세션·버전**을 맡는다.
- 실행 코드·사전 경로의 저장은 거절한다(수리 격리 경로). 범위 밖 경로도 거절한다.

## Pages 문서 열기

`[self:workspace]{op:"open", path:"보고서.pages"}`는 Pages 원본을 보존하고 DOCX 작업 사본을 자동으로 열어 `resource`로 반환한다. 이후 읽기·스냅샷·저장은 이 DOCX 자료 ID에 대해 수행한다. 사무 문서의 선택 수정은 기존 문서 앱 편집 표면을 사용한다.

같은 원본을 다시 열면 작업 사본과 초안을 이어 쓴다. `conversion.source_changed`가 true이면 Pages 원본이 바뀐 것이며 기존 DOCX 편집은 유지된다. 변경된 원본으로 새 사본을 만들려면 `conversion:"refresh", request_id:"고유한 재시도 식별자"`를 지정한다. 같은 request_id의 재시도는 같은 사본을 반환한다. `conversion:"source"`는 원본만 등록하고 편집하지 않는다. 기존 변환 사본이 여러 개면 원본 정보의 후보에서 `working_resource`를 선택한다.

문서 앱에서는 파일 선택 한 번으로 변환하며 “DOCX 저장”으로 작업 사본을 확정한다. Pages 원본과 사본 경로는 도구 패널에 표시한다. `.pages` 출력은 제공하지 않는다. 로컬 ONLYOFFICE가 필요하며 엔진 중단·암호·손상·지원하지 않는 판본은 실패 원인을 표시한다. 단일 파일과 디렉터리형 Pages 패키지를 처리한다. 채팅·노트북 첨부의 `textutil` 읽기는 별도 경로다.


## 코드의 의미 기반 분석

`open kind:"code", mode:"inspect"`는 Git 초기화·목표 문서 생성 없이 코드를 읽는다.
일반 코딩 프로젝트는 기존 `open`을 사용한다. 서버는 모델 공급자와 무관하게 백엔드가 소유하고,
코드 분석을 처음 요청할 때 시작한다. `capabilities`의 `analysis`에서 설치·서버 능력·환경을 확인한다.

```ibl
$w = [self:workspace]{op:"open",kind:"code",mode:"inspect",path:"~workspace"}
$d = [self:workspace]{op:"read",resource:$w.resource,selector:{analysis:"definition",path:"backend/services/coding_projects.py",line:29,column:9}}
[self:workspace]{op:"read",resource:$w.resource,selector:{analysis:"references",target:$d.items[0].target,include_declaration:true}}
```

행·열은 **1부터 세는 유니코드 문자 수**, 범위 끝은 제외한다. 결과 `target`은 원문 지문을 포함하며
다시 조회할 때 원문이 바뀌었으면 거절한다. 미지원 기능은 빈 성공 목록으로 바꾸지 않는다.

| selector.analysis | 추가 입력 |
|---|---|
| symbols | path(파일) 또는 server·query(프로젝트), ref로 resolve |
| definition/declaration/type_definition/implementation/references/hover/signature | path·line·column 또는 앞선 target |
| calls/types | 처음에는 위치, 이후 ref·direction(incoming/outgoing 또는 supertypes/subtypes) |
| diagnostics | path 또는 paths, scope:files/workspace, wait(최대 10초) |
| completion | 위치 또는 resolve할 ref |
| actions | path·range, 또는 resolve할 ref |
| batch | requests:[읽기 selector,…] (최대 50), 각 요청의 path/server로 언어 선택 |

`limit`(기본 200, 최대 1000)·`offset`으로 결과를 줄일 수 있다. 잘린 결과는 `truncated`와 기존
스필 계약의 `full_result`를 반환한다. 서버 원문 후보의 `ref`는 작업 공간·뷰·서버 세대·원문에 결속된다.
`analysis.project_graph_confirmed:false`는 프로젝트 전체 인덱스 완료를 증명하지 못했다는 뜻이다.
진단의 `pending`·`stale`·`version_unconfirmed`는 오류 0건 확정이 아니다. 전체 합격은 기존 타입 검사·빌드로 확인한다.

변경 가능한 코딩 작업 공간에서 다음처럼 여러 파일의 심볼 이름을 바꾼다.

```ibl
$p = [self:workspace]{op:"propose",resource:$코딩공간,selector:{analysis:"rename",target:$정의위치,new_name:"새이름"}}
[self:workspace]{op:"apply",resource:$코딩공간,proposal:$p.proposal}
```

제안은 `rename`·`code_action(ref)`·`completion(ref)`·`format(path, range?)`를 지원한다.
inspect 뷰는 제안을 확인할 수 있지만 원본 적용 권한은 없다. 같은 제안의 apply는 기존 영수증을 반환한다.
복수 파일의 원본·파일 권한을 적용 전에 대조하고 중단되면 `recover`로 원장을 복구한다.
외부 편집과 충돌한 파일은 덮어쓰지 않는다. 코드 `snapshot`은 고정 소스 뷰를 반환하고 read의 `snapshot`으로 읽는다.
스냅샷의 외부 의존 환경은 공유되므로 원문 고정과 의존성 전체 고정은 구별한다.

코딩 화면의 **코드 분석**에서 정의·참조·타입·진단·완성·계층을 조회하고 변경을 적용한다.
편집 중 분석은 해당 창의 별도 초안 뷰를 사용하며, 저장할 때 원래 파일과 충돌을 검사한다.
파일을 옮겨 열어도 초안을 유지하며 **초안 전체 저장**은 여러 파일의 변경을 함께 저장한다.
언어 서버 설정의 **고정 버전 설치·복구**는 관리된 package-lock으로 설치한다.
터미널 설치는 저장소에서 `npm ci --ignore-scripts --prefix data/code_analysis` (Node.js 20 이상).
서버 선언은 `data/code_analysis/servers.yaml`, Python은 Pyright, JS/TS/TSX/JSX는 TypeScript LSP 어댑터다.

협업 실행자는 API·Claude Code·Codex 모두 같은 읽기 IBL과 격리된 `run_command`를 사용한다.
`read kind:"code"`에 resource를 생략하면 발행된 현재 사본을 분석한다.
의미 기반 편집은 실행자가 알려준 `backend/code_analysis_cli.py`에 JSON stdin으로
`{"op":"propose","selector":…}` / `{"op":"apply","proposal":…}`를 전달한다.
접속 정보는 실행자가 환경으로 전달한다. 일반 호스트 HTTP·모델 제공 LSP 도구는 사용하지 않는다.
자기수리는 현재 수리 후보의 resource를 해소하며 검사·정본 반영은 기존 수리 경로가 소유한다.

### 코드 수정 뒤 자동 진단

AI가 일반 파일 쓰기·편집·공통 패치를 적용하면 지원 언어의 변경 파일을 기존 LSP로
자동 분석한다. 별도 분석 호출 없이 API의 다음 모델 입력, CLI의 다음 IndieBiz MCP
결과에 판본·위치·오류/경고를 전달한다. Claude 네이티브 Edit/Write/MultiEdit에는
PostToolUse로도 전달한다. 코딩 협업의 run_command와 자기수리 사본 명령은 실행 전후의
변경 파일을 관측하며 실패한 명령이 남긴 코드 변경도 포함한다.

진단은 변경 파일 범위다. 언어 서버의 기존 프로젝트 설정을 사용하고 전체 빌드 성공을
대신하지 않는다. 동일 파일·동일 내용의 반복 통지는 합치고, 한 전달의 대기는 총 4초로
제한한다. 늦은 결과는 pending으로 표시하고 다음 전달 경계에서 회수한다. 파일당 표시
최대 8건·조회 100건, 한 번에 최대 8파일이며 원문 근거와 생략 수를 보존한다. 공통 AI 맥락에는
파일당 900바이트 이내의 진단 요약을 일반 상태·도구 결과보다 먼저 배치한다. 수정 후 진단은
최신 판본만 싣고 이전 오류는 원문 이력으로 보존한다. 전체 입력 예산을 넘는 다중 파일 진단은
`omitted.by_kind.diagnostics`로 명시하고 전달되지 않은 사실을 수신 처리하지 않는다.
2MiB 초과 파일은 자동 분석에서 제외한다. 변경 도중의
stale, 서버 판본이 없는 version_unconfirmed, 서버 미설치·실패를 오류 0건으로 취급하지 않는다.
진단 실패는 이미 완료된 쓰기나 명령의 성공 여부를 바꾸지 않는다.

Codex 네이티브 파일 변경은 구조화된 변경 영수증으로 관측하지만, 네이티브 도구 직후
맥락 주입 훅은 없으므로 다음 MCP 호출 또는 앱이 소유한 다음 모델 입력에서 전달한다.
임의의 외부 셸·원격 PC·백그라운드 프로세스 변경은 전수 감시하지 않는다. 셸 변경 관측은
명시적으로 발행된 코딩/수리 사본에 한정하며 Git 변경 후보 128개 또는 비Git 파일 10,000개
한도를 넘으면 해당 명령의 자동 변경 관측은 생략한다. 지원 언어는 서버 선언을 따른다.

## Git 없는 일반 파일과 다중 파일 패치

`[self:workspace]{op:"open",kind:"files",path:"/작업/폴더"}`는 Git이나 목표 문서를 만들지 않는다.
반환 resource로 read, propose, apply, recover, close를 사용한다. 파일은 apply 때 저장된다.
코딩 기록(커밋)이 필요한 폴더는 기존 kind:code를 사용한다.

```text
*** Begin Patch
*** Update File: src/a.py
@@
-old_value = 1
+old_value = 2
*** Add File: notes.txt
+새 파일 내용
*** End Patch
```

이 문자열을 `[self:edit]{resource,patch,request_id}`로 전달하거나 UTF-8 파일의 경로를 patch_ref로 전달한다.
두 입력과 기존 old_string/start_line 방식은 섞지 않는다. preview:true는 proposal을 만들며
`[self:workspace]{op:"apply",resource,proposal}`로 확정한다. 기본은 한 호출 안에서 제안·적용한다.
형식은 indiebiz-patch/1 또는 codex-patch이며 OpenAI API V4A 형식과 동일하지 않다.

Update File 뒤 `*** Move to: 목적지`는 이동을 뜻한다. Delete File과 기존 목적지를 덮어쓰는 이동에는
expected의 상대 경로별 SHA256이 필요하다. 문맥은 공백까지 정확히 한 곳이어야 한다.
BOM·기존 줄바꿈·실행 권한을 유지하며 바이너리 패치는 거절한다.
전체 파일을 먼저 검사하지만 OS 수준의 다중 파일 원자 교체는 아니다.
중도 실패는 recovery_required로 남으며 recover는 이미 적용된 파일을 건너뛰고 원본 그대로인 파일만 이어간다.
외부 수정은 덮어쓰지 않는다. 수리 후보의 effect_scope:candidate는 라이브 반영이 아니다.
