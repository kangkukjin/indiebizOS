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
