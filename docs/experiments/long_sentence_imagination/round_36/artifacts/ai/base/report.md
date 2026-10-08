# 교육 자료 인계 v1

| 반 | 상태 | 필요 수 | 검증 수 | 누락 | ZIP 경로 |
|---|---|---|---|---|---|
| alpha | ready | 36 | 36 | 없음 | /Users/kangkukjin/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-10-08_36회차/ai/base/alpha.zip |
| beta | ready | 36 | 36 | 없음 | /Users/kangkukjin/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-10-08_36회차/ai/base/beta.zip |
| gamma | blocked | 36 | 0 | gamma/lesson07.txt | (생성 안 함) |

- 기준: source/catalog.json 의 kits[].files (자료 루트 = source). 목록 밖 파일(draft/·internal/ 등)은 넣지 않았다.
- 검증: ZIP을 다시 열어 항목 이름 집합 = 필요 목록, 중복 0, 디렉터리 항목 0, 항목별 sha256 = 원본 sha256 을 전건 확인했다.
- blocked 반은 ZIP을 만들지 않았다.
- 압축은 등록 스크립트 `압축`(op:pack, base=source)을 썼다. 바이트(sha256) 대조는 등록 기능에 없어 work/verify_zip.py 를 새로 작성했다(압축의 list 기능은 이름·크기만 준다).
