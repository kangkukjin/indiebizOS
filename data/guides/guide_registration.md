# 가이드 등록 가이드 (Guide Registration Guide)

이 가이드는 IndieBiz OS 시스템에 새로운 작업 지침(가이드)을 등록하고 관리하는 방법을 설명합니다.

## 1. 가이드 파일 생성
새로운 가이드는 마크다운(`.md`) 형식으로 작성하며, 다음 경로에 저장합니다.
- **경로**: `/Users/kangkukjin/Desktop/AI/indiebizOS/data/guides/`
- **파일명**: 영문 소문자와 언더바(`_`)를 사용한 직관적인 이름 (예: `my_new_guide.md`)

## 2. 가이드 DB 등록
파일을 생성한 후, 시스템이 검색할 수 있도록 DB에 등록해야 합니다.
- **DB 파일**: `/Users/kangkukjin/Desktop/AI/indiebizOS/data/guide_db.json`
- **등록 항목**:
  - `id`: 파일명과 동일한 고유 ID
  - `name`: 가이드의 공식 명칭
  - `description`: 가이드 내용에 대한 간략한 설명
  - `keywords`: 검색에 사용될 키워드 목록 (한글/영문 포함)
  - `file`: 실제 파일명 (확장자 포함)

## 3. 등록 확인
등록이 완료되면 다음 명령을 통해 가이드가 정상적으로 검색되는지 확인합니다.
```bash
[source:search_guide]("가이드명 또는 키워드")
```

## 4. 수정 및 업데이트
기존 가이드를 수정할 때는 해당 `.md` 파일만 편집하면 즉시 반영됩니다. 만약 이름이나 키워드를 변경해야 한다면 `guide_db.json`도 함께 업데이트하십시오.
