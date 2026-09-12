# 에피소드 3632: 경로와 원문 조회 계약 수리

유튜브 AI 팁 보고서 주행에서 IBL 실행 외의 불필요한 왕복 두 종류를 제거한다.

1. `self:struct`가 `~workspace/outputs/...json`을 그대로 열어 파일 없음으로 실패했다.
   파일 입구에서 공통 `runtime_utils.expand_body_path`로 해소한다. JSON 봉투,
   일반 문서, `saved_to_file.file_path`가 같은 규약을 쓴다. 절대·상대 경로의 뜻은 보존한다.
2. `read_result(limit:25000)` 세 번이 숨은 상한 24000에 걸렸고, 본문이 `text`인
   결과를 `transcript`로 추측한 두 번의 변수 참조가 실패했다. 저장 결과의 표시 참조에
   실제 큰 필드의 `paths`(최대 6개), `max_limit`, 바로 쓸 `read_args`를 제공한다.
   조회 응답의 `next_read`는 같은 ID·경로·페이지 크기와 다음 offset을 보존하고,
   마지막 페이지에서는 null이다. 기존 `next_offset`과 원 봉투 조회도 유지한다.

`backend/base/result_read_contract.py`가 문자 한도와 조회 스키마를 소유하며,
네이티브 도구와 FastMCP가 같은 스키마를 내보낸다. `limit`는 문자 수 1~24000,
기본 12000, `offset`은 0 이상이다. 잘못된 경로나 한도를 자동 보정하지 않는다.
본문 필드에 임의 별칭을 추가하지 않으며, 저장 원문과 IBL 변수도 수정하지 않는다.
`paths`는 최종 봉투의 큰 직접 필드 목록이고 완전한 스키마가 아니다. path를 생략하면
원 봉투 전체를 조회할 수 있다.

회귀: `backend/test_episode3632_result_reads.py`에서 JSON/텍스트/외부 파일 참조와
네 가지 경로 표기, 실제 본문 키 세 종류, 중첩 JSON 봉투, 한글·이모지 페이지 복원,
상한 거절, MCP 실물 스키마를 검사한다. 기존 원문 보존·미리보기·조회 회귀도 통과했다.
전체 `.venv/bin/python -m pytest backend/ -q`가 종료 코드 0으로 통과했고,
IBL 파생물 `--check`, backend 층 검사, Android 몸 번들 재생성도 완료했다.
실제 주행의 시간·토큰 절감량은 후속 에피소드에서 측정해야 한다.
