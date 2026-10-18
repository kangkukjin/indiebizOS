# 작성 발견 (내부 구현 열람 전)

21:46 KST. folder_survey.md는 “현재 IBL 결과의 source_observation_refs”를 note observation_refs로 연결하라고 안내하지만, 공개 read 계약은 Document{text,blocks,data}이고 실제 read 결과는 data.source_observation_ref 단일 문자열이다. 훈련자는 소규모 읽기 탐침으로 경로를 발견했다. 최초 탐침은 edition:2 누락으로 거절되어 메타데이터를 교정했으며 전체 IBL 초안은 수정0회였다. AI도 실제 read 탐침으로 경로를 찾아 사용했다(가이드 열람으로 인한 직접 실패라는 증거는 없음).

L76-1: 근거 영수증 연결의 작성·발견 마찰. 자료만으로 복사 가능한 read→note 예제가 없고 복수 필드명은 현재 Document에서 접근할 수 없다. 내부 구현을 열기 전에 전체 초안·관측·재현을 보존한다. 수리는 전체 훈련/AI 후속 종료 뒤 안내 정정·실행 가능한 예제를 추가하는 것으로 제한할 수 있다.
