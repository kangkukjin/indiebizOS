# 판본 2 어댑터 작성


## 선언과 검증

어휘를 새로 늘리지 않고 원천 YAML의 `callable_contract`에 version/params/required/pipe_input/result/effects/adapter를 선언한다.
빌더와 런타임은 같은 validator를 사용한다. 기존 returns/flow는 판본 1에 남으며 새 계약은 판본 2가 소비한다.
두 판본의 입력 의미가 달라지는 경우 하나를 다른 하나로 자동 파생하지 않는다(예: where 문자열과 순수 Callable).
도구 성공·실패·원천 절단을 선언된 외부 봉투에서만 해석하고 사용자 value/items 안의 동명 키는 건드리지 않는다.
0/1/N건, Unit, 실제 파일/프로세스, 부분 실패·권한·취소·재생 및 기존 호출 회귀를 시험한다.
지원 범위와 예제는 ibl_v2.md에 함께 갱신하며, 추가 계약은 build_ibl_nodes.py로 파생한다.

실행 계약과 연결된 범위는 [ibl_v2.md](ibl_v2.md)를 함께 읽는다.
