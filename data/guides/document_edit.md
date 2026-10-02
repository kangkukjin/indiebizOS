# 기존 Word 문서 편집 — [self:document]

본문·표·머리말·꼬리말의 문구를 고치고 Word 변경 추적과 주석을 남길 때 쓴다.
새 문서 생성은 `[table:document]`, 기존 DOCX 편집은 `[self:document]`다.

## 조회 → 확인한 문구 편집 → 검수

```ibl
[self:document]{op:"inspect", path:"제안서.docx"}
```

반환 `sha256`은 파일 버전, `items`의 `block_id`는 문단 주소다.
각 행은 `part`, `text`, `in_table`, `editable`을 포함한다.
`offset`(0부터)·`limit`(기본 200, 최대 2000)으로 나누어 읽는다.
다음 예의 해시·문단 주소·기존 문구는 **실제 inspect 결과로 채운다**.

```ibl
[self:document]{op:"edit", path:"제안서.docx", expected_sha256:"조회한 sha256", output:"제안서_검토.docx", author:"검토자", edits:[{block_id:"word/document.xml#p0", old_string:"9월 30일", new_string:"10월 15일", comment:"납기 변경"}]}
```

- `edits`: 1~200건. 같은 문단은 한 번만, `old_string`은 해당 문단에 정확히 한 번 있어야 한다.
- 여러 글자 서식에 나뉜 문구도 바꾼다. 새 문구는 교체 시작 글자의 서식을 이어받는다.
- `track_changes:true` 기본. 삭제/삽입을 실제 Word 추적 요소로 기록한다.
  추적 없는 확정본이 필요하면 `false`. 수정 수락·거절은 문서 편집기에서 한다.
- `comment` 선택. 본문·표 안의 새 문구에 연결된다. 머리말·꼬리말 주석, 삭제만 하는
  변경의 주석은 지원하지 않는다.
- 원본은 보존하고 `output` 또는 `<원본명>_edited.docx`를 만든다. 이미 있는 결과 파일은
  덮어쓰지 않는다. 전체 편집을 검증한 뒤 한 번 저장한다. 해시가 달라지면 재조회한다.
- 결과 `items`에 변경 전후 문구·추적/주석 여부, `path`, `changed_count`를 반환한다.

## 보존과 지원 경계

수정하지 않은 ZIP 파트는 바이트 그대로 보존한다. 표 구조·그림·스타일을 재생성하지 않는다.
단, 필드·링크·책갈피·기존 변경 추적/주석 등 복잡한 요소가 든 **문단은 조회만 허용**한다
(`editable:false`). 이런 문단을 편집하려 하면 파일을 만들지 않고 실패한다.
문단 추가·표 행 삽입·페이지 배치 변경·DOC/HWP 편집은 이 op의 범위 밖이다.

수정 후 inspect로 새 문구를 확인하고 `[engines:render]{op:"docx", path:"제안서_검토.docx"}`로
레이아웃을 확인한다. 렌더러에 따라 추적/주석 표시는 다르므로 화면만으로 기록의 존재를
판정하지 않는다. Word에서 추적 변경 및 주석을 확인할 수 있다.

## 문서 앱의 활성 세션과 소스 원문

런처의 **문서** 앱은 DOCX/ODT/RTF/PDF를 로컬 ONLYOFFICE에서 편집한다. 앱의
`원본 저장`은 편집기의 저장 콜백을 확인하고 원본 해시를 다시 검사한 뒤 파일을 교체한다.
편집기 안의 저장은 편집 서버 반영이며, 원본 파일 확정과 구분한다. `작업 저장`은
복구 초안, `사본 저장`은 같은 형식, `내보내기`는 원본을 보존하는 변환이다.

TXT/MD/HTML/LaTeX/Typst 원문은 같은 저장·버전·세션 계약을 IBL로 사용한다.

```ibl
[self:document]{op:"open", path:"보고서.md"}
[self:document]{op:"capabilities", args:{document_id:"open에서 받은 document.id"}}
[self:document]{op:"session", args:{document_id:"문서 ID", client_id:"작성 창 ID"}}
```

- `draft`는 `args:{session_id,client_id,epoch,expected,operation_id,text}`를 받는다.
  `epoch`는 `engine_epoch`, `expected`는 직전 `session_revision`이다. `document_id`는
  args에 함께 넣는다. `snapshot` 뒤 `read`가 고정된 원문을 읽는다.
- `propose`는 스냅샷 ID·문자 범위·선택 SHA-256·교체 문구를, `apply`는 제안 ID와
  현재 세션 인자를 받는다. 다른 창·과거 버전의 제안은 거절한다.
- `save`는 세션 인자·operation_id·expected_revision을, `export`는 세션 인자·
  operation_id·새 파일명(filename)을 받는다. 중복 요청은 같은 operation_id를 유지한다.
- `versions`로 저장 버전을 조회하고 `restore`로 초안에 복구한다. `recover`는
  파일 기록 뒤 끊긴 저장의 결과를 확인한다. `close`는 미저장 초안이 없을 때만 가능하다.
- 사무 문서의 선택 수정은 앱 안의 공식 편집기 플러그인을 거친다. 바이너리를 문자열로
  덮어쓰거나 활성 편집기를 우회하지 않는다. `inspect/edit`는 위의 별도 사본 계약을 유지한다.
- XLSX/XLSM 범위는 등록한 원본 버전에서 읽어 Markdown에 표로 삽입한다. 원본 변경 확인과
  새 버전 등록은 명시적으로 수행한다. 소스 선택을 강의 재료로 전달하면 원본 버전과 범위를 남긴다.

운영·검증·미완료 범위는 [구현 상태](../../docs/DOCUMENT_APP_DESIGN_2026_10_02.md#구현-상태-2026-10-02)를 따른다.
