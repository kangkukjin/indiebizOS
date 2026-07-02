# Goal / Time / Condition — 목적 기반 실행

> 이 가이드는 IBL의 **goal 블록 문법** 정본이다 (2026-07-03 교재 12_ibl_only.md에서 주문형 가이드로 이동 — 어휘는 상시, 저빈도 문법은 주문형 원칙).
> 반복·예약·조건부 실행을 선언할 때 이 문법대로 작성하고, 진행 중인 목표 관리는 카탈로그의 `[self:goal]{op}` 액션을 쓴다.

IBL은 일회성 명령뿐 아니라 **목적 선언**도 지원한다. Goal을 선언하면 에이전트가 달성 여부를 스스로 판단하고 반복한다.

## Goal Block (목적 선언)

```
[goal: "에어컨 최적 구매"]{
  success_condition: "가격/성능/배송 비교 완료",
  resources: ["shopping-assistant", "web"],
  max_rounds: 20,
  max_cost: 1000,
  by: "오늘 저녁",
  report_to: "사용자"
}
```

- `success_condition`: 에이전트가 달성 여부를 판단하는 기준
- `resources`: 사용할 도구 패키지
- `report_to`: 완료 시 보고 대상
- **필수 안전장치**: 모든 Goal에 `max_rounds` 또는 `max_cost` 중 하나 이상 필수 (무한루프 방지)

## 시간 표현

**종료 통제 (언제 멈추는가):**

| 표현 | 의미 | 예시 |
|------|------|------|
| `deadline` | 최종 기한 | `deadline: "2026-12-31"` |
| `until` | 조건 달성까지 | `until: "매수결정"` |
| `within` | 기한 내 완료 | `within: "2h"` |
| `by` | 특정 시점까지 보고 | `by: "오늘 저녁"` |

**빈도 통제 (얼마나 자주 하는가):**

| 표현 | 의미 | 예시 |
|------|------|------|
| `every` | 반복 실행 주기 | `every: "매일 08:00"` |
| `schedule` | 일회성 예약 실행 | `schedule: "2026-04-01 09:00"` |

**종료 우선순위**: `until` 충족 > `deadline` 도달 > `max_rounds`/`max_cost` 도달

## 조건문 (if/else)

상황에 따라 다른 Goal을 활성화한다:

```
[if: sense:stock{op: "quote", ticker: "^KS11"}.current_price < 2400]{
  [goal: "방어적 포트폴리오 재편"]{deadline: "즉시", max_rounds: 10}
} [else]{
  [goal: "성장주 모니터링 유지"]{every: "매일 09:00", max_rounds: 30}
}
```

조건식의 좌변은 `node:action{params}.field` 형태로 쓸 수 있다. `.field`는 액션 결과 dict에서 점 표기법으로 값을 꺼낸다. 생략하면 결과의 `value` → `result` → 전체 dict 순으로 폴백한다.

## 케이스문 (case)

여러 경우를 분기할 때:

```
[case: sense:stock{op: "quote", ticker: "^KS11"}.current_price]{
  "> 3000": [goal: "공격적 매수"]{max_rounds: 20},
  "2400~3000": [goal: "추가 비교"]{max_rounds: 15},
  "< 2400": [goal: "손절 점검"]{max_rounds: 10},
  default: [goal: "관망"]{max_rounds: 5}
}
```

범위 표현식: `> N`, `>= N`, `< N`, `<= N`, `== N`, `N~M` 지원.

## Goal 프로세스 관리

`[self:goal]` 단일 액션의 `op` 파라미터로 분기한다.

```
[self:goal]{op: "list", status: "active"}        # 진행 중인 목표 조회
[self:goal]{op: "status", goal_id: "goal_001"}   # 특정 목표 상태 조회
[self:goal]{op: "kill", goal_id: "goal_001"}     # 목표 중단
```

**Goal 상태**: `pending` → `active` → `achieved` / `expired` / `limit_reached` / `cancelled`

## 전략 전환 규칙

- 매 시도 후 `[self:goal]{op: "log", goal_id, strategy, result}`로 접근 범주·결과·배운 점을 기록
- 동일 접근이 3회 연속 실패하면 근본적으로 다른 접근으로 전환
- 새 시도 전에 `[self:goal]{op: "attempts", goal_id}`로 이전 이력 확인하여 같은 실수 반복 방지
- 모든 접근 범주가 소진되면 사용자에게 상황 보고

## 통합 예시

```
[goal: "청주 투자 적기 판단"]{
  every: "매일 08:00",
  deadline: "2026-09-30",
  until: "매수 결정",
  max_rounds: 200,
  max_cost: 50000,
  strategy: [case: sense:stock{op: "quote", ticker: "^IRX"}.current_price]{
    "< 4": [sense:realty]{type: "apt", deal: "trade", region: "청주"},
    "> 5": [goal: "관망"]{max_rounds: 1},
    default: [sense:realty]{type: "apt", deal: "trade", region: "청주"}
  }
}
```

→ 금리 상황을 읽고, 그에 맞는 깊이로 탐색하고, 조건 충족까지 매일 반복한다.
