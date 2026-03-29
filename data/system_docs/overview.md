# IndieBiz OS 개요

IndieBiz OS는 개인과 소규모 비즈니스를 위한 AI 기반 통합 관리 시스템입니다. 사용자가 프로젝트 단위로 목표를 설정하고, 다양한 전문성을 가진 AI 에이전트 팀을 구성하여 업무를 자동화하고 효율화할 수 있도록 돕습니다.

## 핵심 차별점: AI 페르소나 설계

IndieBiz OS의 가장 큰 차별점은 **AI의 인격(페르소나)을 직접 설계**할 수 있다는 점입니다.

단순히 "의사 역할을 해줘"가 아닌, **어떤** 의사인지, **어떻게** 대화하는지까지 정의합니다:
- "말 끝에 농담을 섞는 친근한 내과의사"
- "팩트 위주로 간결하게 말하는 세무사"
- "내 투자 성향을 아는 금융 조언자"
- "나의 고민을 기억하는 친구"

## 핵심 가치
- **개인화**: 사용자의 지식과 취향을 학습하여 최적의 조력 제공
- **자동화**: 반복적인 웹 검색, 데이터 수집, 문서 작성을 AI가 수행
- **연결성**: 다양한 도구 패키지를 통해 실제 운영체제 및 웹 서비스와 상호작용

## 주요 기능
- **다중 프로젝트 관리**: 목적에 따른 독립적인 작업 공간 생성
- **에이전트 팀**: 역할과 **페르소나**가 정의된 여러 AI 에이전트 간의 협업
- **위임 체인**: 에이전트 간 단일/순차/병렬 위임 지원 → [상세 문서](delegation.md)
- **실시간 스트리밍**: 모든 AI 프로바이더에서 응답을 실시간으로 스트리밍
- **IBL (IndieBiz Logic)**: 5개 노드 기반 정보 흐름 추상화 → [상세 문서](ibl.md)
- **IBL 용례 RAG**: 유사 사용 사례 검색으로 에이전트의 IBL 생성 품질 향상 → [상세 문서](ibl_rag.md)
- **도구 패키지(노드)**: IBL 노드의 실제 구현체, 동적 로딩 (설치/제거 가능)
- **다중채팅방**: 여러 에이전트와 사용자가 함께하는 그룹 채팅방
- **스케줄러**: 정기적인 정보 수집 및 리포트 자동 생성
- **비즈니스 관리**: 이웃(파트너) 관리, 메시지 수신/발송
- **통신 채널**: Gmail, Nostr DM 통한 외부 소통 → [상세 문서](communication.md)
- **자동응답 V3**: Tool Use 기반 단일 AI 호출로 판단/검색/발송 통합 → [상세 문서](auto_response.md)
- **원격 접근**: Cloudflare Tunnel 기반 원격 Finder(파일/스트리밍) + 원격 런처(AI 제어/스위치 실행) → [상세 문서](remote_access.md)
- **에이전트 자기조절 (Phase 26)**: 목표/시간/조건 시스템 + 전략 에스컬레이션 + 라운드 메모리 → [상세 문서](phase26_goal_time_condition.md)
- **의식 시스템**: 매시간 세계/사용자/자신 상태 수집 (Consciousness Pulse) + 매 6시간 IBL 액션 자가 점검 (Self-Check, 전체 5개 노드 대상)
- **3단 인지 아키텍처 (Phase 28)**: 무의식(반사) -> 의식(계획) -> 평가(성찰)의 3단 처리
  - **무의식 에이전트**: gemini-2.5-flash-lite 기반 경량 게이트키퍼. 요청을 EXECUTE(단순) / THINK(복잡)로 분류. 파일: `unconscious_prompt.md`, `agent_runner._classify_request()`
  - **의식 에이전트**: 메타적 판단 수행. 태스크 프레이밍, 자기 인식, 히스토리 정제, IBL 포커싱, 가이드 파일 선택, 상황 메모. 이제 **achievement_criteria**(달성 기준)도 별도 필드로 출력. 핵심 철학: "문제는 나의 한계와 환경의 제약이 만나는 곳에서 생긴다"
  - **평가 에이전트**: 실행 후 achievement_criteria 대비 결과 평가. NOT_ACHIEVED 시 피드백과 함께 재실행 (최대 3라운드). 파일: `evaluator_prompt.md`, `agent_runner._run_goal_evaluation_loop()`
- **브라우저 자동화**: Playwright 기반 + Chrome MCP 드라이버(계획) — 실제 Chrome 브라우저를 MCP로 제어, 수동 연결 방식, Playwright 폴백
- **실시간 CCTV**: UTIC(16,000+대) + ITS + Windy 통합 검색 → [가이드](../guides/cctv.md)

## 통합 아키텍처 (Phase 25: 5-Node 통합)
시스템 AI와 모든 프로젝트 에이전트가 **동일한 코드베이스와 동일한 도구 구조**를 공유합니다:
- **execute_ibl 단일 도구**: 시스템 AI와 프로젝트 에이전트 모두 `execute_ibl` 하나로 모든 기능 접근
- **IBL 노드 추상화**: `[node:action]{params}` 문법으로 5개 노드(sense, self, limbs, others, engines)의 308 액션 통합
- **액션 라우팅 다중화**: handler(260), system(22), trigger_engine(9), workflow_engine(6), driver(5), channel_engine(3), api_engine(2), web_collector(1)
- **사용자 소통도 self**: 질문(`[self:ask_user]`), 할일(`[self:todo]`), 승인(`[self:approve]`), 알림(`[self:notify_user]`)
- **접근 범위 차이**: 시스템 AI는 전체 노드, 프로젝트 에이전트는 허용된 노드만 접근
- **프로바이더 통합**: 새 AI 프로바이더 추가 시 시스템 AI + 모든 에이전트에 자동 적용

## 시스템 AI 위임 기능
시스템 AI는 IBL을 통해 프로젝트의 전문 에이전트에게 작업을 위임할 수 있습니다:
- **`[others:list_projects]`**: 프로젝트/에이전트 목록 조회
- **`[others:delegate_project]`**: 특정 에이전트에게 작업 위임
- **병렬 위임**: 여러 프로젝트에 동시 위임 가능
- **조건**: 사용자가 명시적으로 요청한 경우에만 위임

## 패키지 YAML 자동 동기화
서버 시작 시 `_auto_register_packages()`가 각 패키지의 `ibl_actions.yaml` 수정 시간을 `ibl_nodes.yaml`과 비교하여, 변경된 패키지만 자동 재등록합니다. 패키지 YAML이 원본(source of truth)이며, `ibl_nodes.yaml`은 파생 파일입니다.

## 시스템 통계
- **활성 프로젝트**: 20개
- **도구 패키지**: 35개 (설치됨), 확장 패키지 9개
- **IBL 노드**: 5개 (sense 78, self 75, limbs 96, others 13, engines 46), 총 308 액션
- **마지막 업데이트**: 2026-03-29

## 감각 피드백 시스템 (2026-03-15)
IBL 실행 품질을 높이기 위한 피드백 강화:
- **Provider 절삭 확대**: 8KB → 16KB, 파이프라인 시 `_action_count × 16KB`
- **파이프라인 중간 결과 전체 누적**: 500자 절삭 제거, 전체 컨텍스트 유지
- **>> 에러 시 중단**: 앞 단계 실패 시 뒤 단계 실행 안 함 (빠른 실패)
- **검색 도구 _note 필드**: 검색 결과에 후속 액션 안내를 포함하여 에이전트의 다음 행동 유도
- **감각 전처리 (Sensory Preprocessing)**: 정보성 액션(검색, 크롤링, 여행 등)의 출력을 경량 AI로 압축하여 컨텍스트 폭발 방지. 각 액션의 `ibl_actions.yaml`에 `postprocess` 블록으로 선언적 설정. 실측 65-70% 압축 → [상세: architecture.md]

---
*IndieBiz OS - Your Personal AI Assistant Team*
