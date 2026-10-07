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
- 코딩 `open` 은 **프로젝트 폴더**를 연다(git 이 없으면 조용히 init, `goal` 을 주면 목표 문서 `목표.md` 틀을 만든다).
  `save` 는 **기록** — `message` 필수, 폴더의 모든 변경을 한 커밋으로(바뀐 것이 없으면 `state: clean`). `versions` 가 기록 목록,
  `restore{revision, path?}` 가 그 기록으로 되돌리기(되돌리기 전 상태를 먼저 기록해 둔다). AI 코딩은 이 낱말이 아니라
  `[others:delegate]{scope:"system", role:"coding", context:{project: $path, resource: $resource}}` — 실행 에이전트가 목표 문서대로
  짓고 진행 기록에 한 줄을 남긴다. 프로젝트 명령 실행(개발 서버)은 코딩 앱 실행 탭(엔진 I/O)의 몫.

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
