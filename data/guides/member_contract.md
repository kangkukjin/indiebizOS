# 회원 액션 계약

## 회원 프로파일에 공개할 때

- 기본은 비공개다. lands_on을 선언하기 전에 회원의 위치·출력·캐시·로그를 확인한다.
- body는 limb_op:{op,...}를 어휘 소스에 선언하고 helper/Android 봉투 계약과 맞춘다.
- hub는 side_effect:false와 path_audited:{at,impl}가 필요하다. 지문은 패키지 하위 Python 파일도 포함한다.
  공유 라이브러리·외부 실행기까지 실제 경로 접근을 감사한다. 지문만 적어 접근 격리가 생겼다고 판정하지 않는다.
- 공개 사전 필터와 실제 중첩/직접 IBL 잎 실행 모두에서 거절 시험을 둔다.
- backend/test_member_* 검사는 영속 경로를 모두 임시화한다. 원문·경로가 주인 로그에 남는지 함께 본다.
- build_ibl_nodes.py로 파생하고 --check, backend 층·파일 크기 검사, 해당 플랫폼 봉투 검사를 통과시킨다.

설계와 단계별 잔여 검증: docs/EXTERNAL_SERVICE_APP_HANDOFF.md §11. 회원 시작 예시: member_start.md.
