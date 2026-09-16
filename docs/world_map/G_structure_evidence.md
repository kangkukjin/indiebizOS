# 세계 지도 관계의 근거와 적용 범위

확인: 2026-09-17. 세계의 방법·도구와 관계를 기록하는 편집 자료다.
지도는 사용자의 접근을 평가하거나 교체하라는 지시가 아니다. 이름을 접한 모델이 전문지식을
회상하고 필요하면 원문을 검색하는 입구이며 설치·현재 API·권한을 보증하지 않는다.

## rendering
Blender는 3D 모델링과 렌더링을 제공한다. 장면의 형상·재질·조명·카메라로 이미지를 만드는
방법과 이를 구현한 도구를 구별한다. 집의 외관을 표현하려는 목적에서도 이 연결을 찾을 수 있다.
형상·재질·조명·카메라는 제작 과정에서 마련할 입력이며 모두 사용자에게 미리 요구할 항목은 아니다.
근거: https://www.blender.org/features/rendering/ · https://www.blender.org/features/modeling/
공식 검색 색인의 기능 설명과 기존 data/guides/world_tools.md를 대조했다.
공식 페이지 직접 열람은 402로 막혔으므로 최신 버전·성능 주장을 추가하지 않았다.
이 몸의 기존 실행 접점은 data/guides/arch_render.md와 등록 스크립트 arch_render다.

## interactive
Three.js는 장면·카메라·렌더러로 브라우저에서 3D를 표현하는 라이브러리다.
회전·확대하며 보는 모델과 정지 이미지 렌더는 출력 목적이 다르다. 두 도구를 무조건 대안으로
연결하지 않는다. 웹 문서와 모델/장면이 필요하며 실행 환경·지원 API는 사용 시 확인한다.
근거: https://threejs.org/manual/en/cameras.html (공식 검색 색인의 예제 확인, 직접 열람 404),
기존 data/guides/world_tools.md의 Three.js / Babylon.js 항목.

## scheduling
OR-Tools의 공식 Employee Scheduling 예제는 CP-SAT으로 교대 배치 제약을 모델링한다.
방법을 모르는 근무표 질문에서도 문제→방법→도구 경로로 도달할 수 있다.
인원·기간·가능일·강제 제약을 정의해야 하며 공평의 의미는 사용자 판단으로 남긴다.
근거: https://developers.google.com/optimization/scheduling/employee_scheduling
공식 본문의 간호사 배치·근무 요청 예제 열람. 필수 인원·근무 제약 충족을 검증한다.

## file_query
DuckDB는 CSV·Parquet·JSON의 여러 파일을 glob 또는 파일 목록으로 읽을 수 있다.
여러 파일을 조회하려는 목적에 파일 기반 SQL이라는 방법과 DuckDB를 연결한다.
데이터 형식·열 대응·접근 경로가 필요하며 스키마 차이는 검토한다. 복사·통합을 무조건 금지하거나
기존 엑셀 사용을 틀렸다고 판단하지 않는다.
근거: https://duckdb.org/docs/current/data/multiple_files/overview
공식 본문의 glob·파일 목록·CSV·Parquet 예제 열람.

## scope
이번 관계는 위의 공개 문서/기존 가이드에 한정해 확인했다. verified는 출처 대조 여부다.
전체 방법 지도는 계속 열람할 수 있으며 관계가 없는 항목의 관계를 없다고 단정하지 않는다.
분류 path는 기존 편집 경로이며, 명시한 broader 외에는 일반화 계층으로 추론하지 않는다.
