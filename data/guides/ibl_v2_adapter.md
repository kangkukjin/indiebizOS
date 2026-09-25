# IBL 사전 어댑터 작성


## 선언과 검증

어휘를 새로 늘리지 않고 원천 YAML의 `callable_contract`에 version/params/required/pipe_input/result/effects/adapter를 선언한다.
빌더와 런타임은 같은 validator를 사용한다. callable_contract는 현재 IBL이 소비한다. 기존 returns/flow는 저장 원문 호환 실행을 위해 유지한다.
두 판본의 입력 의미가 달라지는 경우 하나를 다른 하나로 자동 파생하지 않는다(예: where 문자열과 순수 Callable).
도구 성공·실패·원천 절단을 선언된 외부 봉투에서만 해석하고 사용자 value/items 안의 동명 키는 건드리지 않는다.
0/1/N건, Unit, 실제 파일/프로세스, 부분 실패·권한·취소·재생 및 기존 호출 회귀를 시험한다.
지원 범위와 예제는 주 교재 ibl_composition.md와 문법 전문에 함께 갱신하며, 추가 계약은 build_ibl_nodes.py로 파생한다.

실행 계약과 연결된 범위는 [주 IBL 교재](ibl_composition.md)를 함께 읽는다.

기존 저장 관용구를 연결할 때는 기존 본문의 파이프 입력 자리 판정도 계약에 보존한다.
첫 파이프의 맨몸 자유 변수만 `pipe_input`이 되며, 인자 순서로 추측하지 않는다.
명시 인자와 파이프가 같은 자리에 들어가면 실행 전에 거부한다.

여러 출처를 결합하는 도구는 `flow.input_bundle_param`을 `callable_contract.pipe_input`에
연결하고, 묶음과 개별 입력을 두 스키마(`params`, `callable_contract.params`)에 모두 선언한다.
`required_any`는 대안, `requires`는 함께 필요한 인자, `exclusive`는 동시에 줄 수 없는 인자를
선언한다. 검사와 실행 모두 파이프로 주입되는 입력까지 포함해 판정한다.
빌드는 pair/same-kind flow의 입력 연결과 컨테이너 타입 누락을 거부한다.

단항 `flow.accepts: items/prose` 계열도 명시 `pipe_input`을 선언한다. 기존 봉투 어댑터의
`adapter.input_envelopes: [items]`는 그 입력 슬롯의 Record 또는 JSON Record가 원천 상태를
담은 봉투임을 선언한다. 목록 자체와 목록 안 업무 필드는 상태로 해석하지 않는다.
변환 중 잎 도구가 입력을 행 목록으로 바꾸더라도 어댑터가 원래 입력의 실패·원천 누락을
반환값과 함께 보존한다. 의도한 선택(`scope: selection`)은 불완전 원천과 구별한다.
반환은 기존 Record를 유지하므로 다음 목록 변환에는 `.items`를 명시한다.
빌드는 단항 입력 자리와 봉투 근거 연결이 빠진 선언도 거부한다.

정상 반환이 평문인 기존 잎 도구는 **성공이 확정된 반환 지점**에서 `ibl_edition.text_result`로
현재 판본의 실행 봉투를 만든다. 기존 판본은 원래 문자열을 유지한다. JSON처럼 생긴 본문이나
`Error:`로 시작하는 업무 텍스트를 상태로 해석하지 않도록 JSON 판정보다 먼저 감싼다.
실패 반환에 이 함수를 쓰거나 공통 어댑터에서 모든 문자열을 성공으로 받아서는 안 된다.
결합에서 건너뛴 분기는 공통 정직 표지 `branches_skipped`와 완료 증거로 보존한다.
