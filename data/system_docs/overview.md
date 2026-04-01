# IndieBiz OS 개요

## 정의

IndieBiz OS는 AI에게 지능적인 몸을 만들어주는 하네스(harness)다. AI의 본질적 가치는 **연결** — 사람과 세계를, 사람과 사람을, 알고 있는 것과 아직 모르는 것을 잇는 것. 몸이 없으면 연결할 수 없다.

하네스는 에이전틱 루프와 다르다. 에이전틱 루프는 AI의 처리량(throughput)을 올린다 — 도구를 더 많이 호출. 하네스는 AI의 판단력(intelligence)을 올린다 — 같은 모델이라도 하네스에 따라 결과의 질이 달라진다.

## 신체 구조 (생명체 메타포)

| 신체 시스템 | IndieBiz OS 구현 | 역할 |
|------------|------------------|------|
| 신경계 | IBL (5노드, 308액션) | 감각/행동의 상시 연결 |
| 감각기관 전처리 | 감각 전처리 (postprocess) | 원시 정보를 압축하여 뇌에 전달 |
| 선택적 주의력 | 의식 에이전트 | 매 턴 메타 판단 — 문제 정의, 초점, 달성 기준 |
| 반사 신경 | 무의식 에이전트 | EXECUTE/THINK 분류, 단순 요청은 의식 건너뜀 |
| 자기 교정 | 평가 에이전트 | 달성 기준 대비 평가, NOT_ACHIEVED 시 재시도 |
| 자의식/각성 | World Pulse | 매시간 세계/사용자/자기 상태 수집 |
| 면역계 | Self-Check | 매 6시간 IBL 액션 자가 점검 (5노드 전체) |
| 자율신경계 | 스케줄러, 이벤트 엔진 | 의식 없이 돌아가는 리듬 |
| 해마 | 실행기억 (해마 + discover) | 1회 생성, 전 에이전트 공유. fine-tuned 임베딩으로 관련 기억 자동 인출 |

## IBL — AI의 신경계

IBL(IndieBiz Logic)은 명령어가 아니라 **환경 모델(body schema)**이다. `[node:action]{params}` 문법.

| 노드 | 역할 | 액션 수 | 예시 |
|------|------|---------|------|
| **sense** | 세계를 감각 | 78 | search_ddg, summarize_video, search_library_docs, restaurant |
| **self** | 자기 자신 | 75 | read, write, memory_save, todo, schedule |
| **limbs** | 세계에 행동 | 96 | os_open, web_build, cf_pages_deploy, play, browser_action |
| **others** | 소통 | 13 | gmail_send, delegate_project, nostr_send |
| **engines** | 내부 처리 | 46 | execute_python, execute_nodejs, transform, visualize |

연산자: `&` (병렬), `>>` (순차), `??` (폴백)

## 4단 인지 아키텍처

```
사용자 메시지
    ↓
실행기억 생성 (해마 + discover + implementation, 1회)
    ↓
무의식 에이전트 ← 실행기억 (EXECUTE/THINK 분류)
    ↓ THINK만
의식 에이전트 ← 실행기억 (문제 정의 + 달성 기준 + 자기 인식)
    ↓
실행 에이전트 ← 실행기억 + 달성 기준 (IBL로 도구 사용)
    ↓
평가 에이전트 ← 실행기억 (달성 기준 대비 평가, 최대 3라운드)
```

- **실행기억**: 파이프라인 최상단에서 1회 생성, 전 에이전트 공유. 과거 코드 사례(해마) + 추천 도구(discover) + 액션 implementation
- **해마**: IBL 도메인 fine-tuned 임베딩 모델 (Top-5 80.9%, 범용 대비 +28.3%p)
- **무의식**: gemini-2.5-flash-lite 기반 경량 게이트키퍼. 실행기억을 보고 1초 이내 판단.
- **의식**: 메타 판단 — task_framing, achievement_criteria, history_summary, capability_focus, self_awareness, world_state
- **실행**: 달성 기준을 시스템 프롬프트로 받아 처음부터 목표에 맞춘 코드 생성
- **평가**: 실행기억의 도구 정보를 활용하여 도구 활용의 적절성까지 평가

시스템 AI와 프로젝트 에이전트 모두에 동일하게 적용.
상세: `system_docs/execution_memory.md`

## 프로젝트 & 에이전트

- 프로젝트 단위로 독립된 작업 공간. 각 프로젝트에 역할별 에이전트 배치
- 에이전트 간 위임: 단일/순차/병렬 (`[others:delegate_project]`)
- 시스템 AI: 전체 노드 접근, 프로젝트 에이전트에 위임 가능
- 프로젝트 에이전트: 허용된 노드만 접근 (allowed_nodes)

## 외부 연동

- **통신**: Gmail, Nostr, Telegram
- **NAS**: 음악 스트리밍, 자막 관리, 웹앱 호스팅
- **안드로이드**: ADB 기반 기기 제어
- **원격**: Cloudflare Tunnel (Finder + 런처)
- **브라우저**: Playwright 기반 자동화

## 감각 전처리

정보성 액션(검색, 크롤링 등)의 출력을 경량 AI로 노이즈 제거 후 에이전트에 전달. 눈이 시신경을 통해 정보를 보낼 때 이미 전처리하는 것과 같다. 각 액션의 `ibl_actions.yaml`에 `postprocess` 블록으로 선언적 설정. 뉴스 검색은 같은 사건 기사를 자동 병합.

## 패키지 시스템

- 35개 도구 패키지 + 9개 확장 패키지
- 폴더 기반 탐지, 동적 로딩
- `ibl_actions.yaml`이 원본(source of truth), `ibl_nodes.yaml`은 파생
- 서버 시작 시 mtime 비교로 변경된 패키지만 자동 재등록

## 참조

- AI용 시스템 핸드북: `system_docs/ai_handbook.md`
- IBL 명세: `system_docs/ibl.md`
- 아키텍처 상세: `system_docs/architecture.md`
- 실행기억 & 해마 & RAG: `system_docs/execution_memory.md`
- 패키지 현황: `system_docs/inventory.md`
- 설계 철학 (백서): `WHITEPAPER.md`

## 시스템 통계

- 활성 프로젝트: 20개
- 도구 패키지: 35개 (설치됨), 확장 9개
- IBL: 5노드, 308액션
- 마지막 업데이트: 2026-04-01
