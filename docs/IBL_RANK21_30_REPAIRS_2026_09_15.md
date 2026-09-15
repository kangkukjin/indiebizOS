# IBL 사용 순위 21–30 구현 수리 (2026-09-15)

## 범위
로컬 사용 기록으로 선정한 21–30위: self:script, table:union, self:notebook,
sense:host, table:groupby, self:body, table:dedup, self:memory, sense:book,
limbs:browser. 감사에서 재현한 12개 결함을 수리했다. union은 새 결함이 없었다.

## 변경과 재현 검사

| 어휘 | 결함 → 수정 | 검증 |
|---|---|---|
| limbs:browser | 사라진 참조가 같은 역할의 다른 버튼으로 대체됨 → 이름·역할·선택자가 일치하는 유일한 요소만 허용 | 잘못된 버튼·입력·중복 요소 거절, 유일한 대상 허용 |
| self:script | 같은 초의 작업 파일 충돌 및 완료 상태 덮어쓰기 → UUID 식별자, 고유 임시 파일, 러너가 상태 파일 소유 | 동시 생성과 즉시 완료 재현 |
| self:script | exit 0이 JSON 실패를 성공으로 바꿈 → 공통 결과 판정, 실패 원장·job·status 일치 | 동기/분리 러너 실제 subprocess의 3가지 실패 JSON |
| self:memory | 본문 쓰기 트랜잭션 중 다른 연결로 벡터 갱신 → commit 후 갱신, 실패 ID 영속 큐와 재시도 | 실제 sqlite-vec 벡터 변경, 실패 후 fresh 문서 재시도 |
| self:notebook | 본문 답변의 source/loc 환각 → 제공한 본문과 실제 청크 위치 검증, 원문 quote, 무효/무인용 답변 실패 | 유효·무효 위치·무인용 답변 |
| self:notebook | 검색 후보 절단 후 source 필터 → FTS/KNN 후보 선택 전에 자료 범위 제한 | FTS 및 실제 sqlite-vec의 지정 자료 검색 |
| table:dedup | 비객체 행 침묵 유실 → 오류 반환 | 혼합 행·스칼라 행 |
| table:groupby | 비객체 행 침묵 유실 → 오류 반환 | 혼합 행·스칼라 행 |
| table:groupby | 빈 table을 통화 부재로 오인 → 스키마로 집계 검증, 빈 결과 스키마 반환 | 빈 표 정상/잘못된 필드 |
| sense:book | 정보나루 page 누락 → 제목·통합 검색 모두 전달 | page 3 전달 |
| sense:book | 국립중앙도서관 HTML 파싱 실패를 소장 없음으로 오인 → 명시적 total=0만 빈 결과 | 점검 HTML·진짜 0건·파싱 누락 |
| self:body | rename numstat 경로 오해석 → NUL 구분 파싱, 이전/새 경로 pathspec | 한글·탭·중괄호 rename |
| sense:host | 최초 CPU 표본의 허위 0% → 전체 프로세스 1차 표본, 공통 0.2초 간격, 2차 표본 | 호출 순서·측정 결과 |

dedup/groupby의 비객체 행 유실은 하나의 공통 결함이며 표에는 어휘별로 나누었다. 문서·카탈로그 원본도 실제 계약으로 갱신하고 빌드로 파생했다.

## 회원 파일 접근 경로 재감사
system_essentials 패키지 실행 소스 변경으로 self:read/fill의 path_audited 지문을 다시 계산했다.
backend/ibl/member_files.py, member_bridge.py와 패키지 member_documents.py를 점검했다.
회원 장치 요청 → 턴별 전용 임시 작업대 → read/fill 변환 → 회원 장치 전송 경계는 그대로다.
변경한 body_ops/script_ops/script_runtime은 이 변환 경로에서 호출하지 않는다.
파일 누락 시 허브 파일 폴백 금지, 전송 거부, 턴 범위 참조, PDF/DOCX/XLSX 변환을 회원 회귀 검사로 확인했다.

## 검증 상태
- 신규 결함 회귀: 29개 통과.
- 관련 기존 회귀: 87개 통과 (노트북 저장소·모델을 임시 환경으로 격리).
- 회원 파일·격리 회귀: 24개 통과. 마지막 설명/형식 정리 뒤 신규 회귀·회원 회귀·단일 러너 관문을 함께 다시 실행해 57개 통과.
- 어휘 빌드/--check, Android 몸 번들 재생성, 커밋 전 필수 검사 전부 통과.
- 실제 호스트 프로세스 조회 성공, 실행 백엔드 healthy 및 실행 코드 지문=디스크 지문 일치. 변경 감지 재기동으로 적용됨.
- 전체 백엔드 최종 검사: **4511 passed, 1 skipped**, 450.47초. 첫 실행의 실패 9개(갱신 전 회원 감사 지문 8개 + 새 테스트 직접 실행 진입점 1개)는 모두 해소했다.

## 한계
브라우저 DOM/외부 도서관 응답은 결정론 fixture로 검사했다. 외부 사이트 전체의 실시간 동작을 보증하지 않는다.
문서 인용 검증은 출처 위치의 실재를 보장하며, 자연어 주장과 원문 사이의 의미적 함의까지 판정하지 않는다.
