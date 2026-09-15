# IBL 사용 순위 12–20 구현 감사 후속 수리

2026-09-15. `each`를 제외하고 확인한 12개 결함을 수리한다. `self:time`은 감사에서 확인된 결함이 없어 변경하지 않는다.

| 감사 | 어휘 | 수정 후 동작 |
|---|---|---|
| F01 | self:file_find | 색인 0건·실패의 순회 폴백도 이름·확장자·종류·최소 크기 필터를 유지한다. 색인 실행 실패는 `index_error`로 구분한다. 촬영/생성 날짜·GPS는 순회에서 검증할 수 없으므로 조건을 버리지 않고 오류를 반환한다. |
| F02 | sense:stock history | 지수 경로와 FMP HTTP 402 폴백에 절대 날짜를 전달한다. Yahoo 종료 경계는 다음 날 0시로 설정해 지정 종료일을 포함하고 네이버에도 양끝을 전달한다. 범위를 적용한 뒤 표본 추출하며 과거 이력에 오늘 시세를 덮어쓰지 않는다. |
| F03 | table:sort | 객체 아닌 items 행이 있으면 입력을 일부 삭제한 성공 결과 대신 명시적 오류를 반환한다. |
| F04 | table:groupby | 그룹 키와 집계 출력 열 이름의 충돌을 거절한다. `by:count`의 행수 집계는 `agg:{건수:[count]}`처럼 별도 출력 열을 지정한다. |
| F05 | self:file_find | Spotlight·macOS 폴백·일반 파일 순회 모두 후보를 파일 검색의 요청 기준(mtime/size/name)으로 정렬한 뒤 limit을 적용한다. 후보 상한 때문에 전체를 비교하지 못하면 경고한다. |
| F06 | self:file_find | 상대 경로는 glob·메타 검색 모두 프로젝트 기준으로 해소한다. |
| F07 | self:file_find | 메타 결과도 list·glob과 같은 파일 뷰 생성기로 name/path/size/mtime/dir/is_dir을 제공한다. |
| F08 | sense:video summarize | 다른 영상 op과 같은 URL 해소기를 사용해 video_id 단독 입력도 받는다. |
| F09 | sense:video summarize | 자막 전체를 50,000자 이하 구간으로 나누어 요약 후 순서대로 통합한다. 필요하면 중간 요약을 두 개씩 재통합한다. 빈 응답·과대 중간 응답은 내용을 절단하지 않고 실패로 알린다. transcript_chars/transcript_chunks/summary_calls로 처리량을 반환한다. |
| F10 | limbs:music skip | 다음 곡 재생 실패 시 success=false·failed_video_id·queue_remaining을 반환한다. 실패한 곡만 소비하고 아직 시도하지 않은 대기열은 보존한다. 재생이 멈춘 상태에서도 다시 skip하면 남은 다음 곡을 시도한다. |
| F11 | table:union | 실패 분기를 제외해도 effect_rows와 오류·경고는 원래 입력 번호를 사용한다. 공용 경로를 쓰는 merge에도 같은 규칙을 적용한다. |
| F12 | self:list | file_find와 같은 basename 패턴 매칭으로 NFC/NFD·대소문자를 정규화하되 반환 경로는 원래 이름을 보존한다. |

## 검증

`backend/test_ibl_rank_12_20_repairs.py`는 임시 파일과 공급자·플레이어 대역으로 위 증상을 재현한다. 실제 금융 API 호출, LLM 호출, 음악 재생 없이 계약을 검증한다. 기존 관련 회귀 및 `pytest backend/ -q` 전체 회귀도 실행한다.

어휘 소스 설명과 파생 카탈로그를 함께 갱신한다. 파일 색인 backend 변경에 따라 Android body bundle도 재생성한다. 긴 영상은 분할 요약 때문에 단일 요약보다 모델 호출 수가 증가한다. 색인 없이 촬영 날짜·GPS를 확인하는 기능을 새로 구현한 것은 아니며, 그 조건을 검증하지 못할 때 정직하게 실패하는 방식이다.

## 회원 경로 재감사

공용 system_essentials 실행 소스 지문 변경에 따라 read·fill을 재감사했다. 변경은 list·file_find의 뷰/루트/패턴 처리에 한정되고 member_documents의 기기 입력·임시 작업공간·기기 출력 영수증 경로에는 영향이 없다. read의 범위 정규화와 fill의 office_ops 위임은 그대로이며, 새 파일 뷰는 파일을 쓰거나 추가 경로를 열지 않는다. 확인 후 path_audited 지문을 갱신한다.

사진 조회가 공유하는 `sort:date`는 기존처럼 최근 수정 후보 창에만 촬영일 정렬을 적용한다. 이번 수리로 후보마다 무거운 메타 프로세스를 실행하지 않도록 limit개 조회 비용을 유지하고, 전체 촬영일 순위가 아니라는 warning을 추가했다.

## 실행 결과

- 기존 관련 회귀 192개 통과.
- 신규 회귀 33개 통과. 회원 문서 검사 10개를 함께 실행한 43개도 통과.
- 전체 `pytest backend/ -q` 실행에서 유일한 실패는 새 테스트의 `__main__` 누락을 잡는 `test_r2_direct_run_delegates_to_pytest`였다. 진입점을 보완한 뒤 러너 규약 4개 + 신규 33개, 총 37개를 재실행해 통과했다. 새 파일의 직접 실행도 33개 통과. 전체 스위트를 두 번째로 실행한 것은 아니다.
- 실제 IBL 진입점으로 sort·groupby·file_find·video 문제 입력을 재확인했다. 긴 자막 요약의 전체 함수도 모델·브라우저 대역으로 실행해 마지막 구간 전달과 보고서 생성까지 확인했다.
- 어휘 빌드 및 `--check`, Android body bundle 생성 통과. 실행 중 백엔드를 수동 재기동하지는 않았다.
