# 교육 자료 최종 인계

| 반 | 상태 | 필요 수 | 검증 수 | 누락 | ZIP 경로 |
|---|---|---|---|---|---|
| gamma | ready | 36 | 36 | 없음 | /Users/kangkukjin/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-10-08_36회차/ai/recovery/gamma.zip |
| beta | ready | 36 | 36 | 없음 | /Users/kangkukjin/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-10-08_36회차/ai/base/beta.zip |
| alpha | ready | 36 | 36 | 없음 | /Users/kangkukjin/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-10-08_36회차/ai/base/alpha.zip |

- 이 문서는 앞 인계(base/result.json)를 이어받아, 보충된 source/gamma/lesson07.txt로 막혔던 gamma 반만 새로 준비한 완결판이다.
- gamma: source/catalog.json의 필요 목록 36개로 등록 스크립트 `압축`(op:pack, base=source)을 써서 recovery/gamma.zip을 새로 만들었다.
- alpha·beta: 기존 ZIP(base 폴더)을 재생성·복사·덮어쓰기 하지 않았다. 경로·상태·필요 목록·누락·검증 수는 base/result.json 값 그대로다.
- 검증(이번 실행, 세 반 전건): ZIP을 열어 항목 이름 집합 = 필요 목록, 중복 0, 디렉터리 항목 0, CRC 이상 없음, 항목별 바이트·sha256 = 현재 source 원본을 확인했다(base/work/verify_zip.py와 같은 코드).
- 필요 파일 전체 목록은 같은 폴더의 result.json kits[].files에 있다.
