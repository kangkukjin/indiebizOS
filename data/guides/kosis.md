# 통계청 KOSIS 가이드

`[sense:kosis]` 단일 액션으로 통계청 KOSIS(국가통계포털) 데이터를 통합 검색·조회한다. **query / indicator / (org_id+tbl_id)** 3가지 모드가 핵심 분기.

GDP·물가·인구·고용·산업 등 한국 공식 통계의 원천. 시계열 차트나 정책 분석의 기초 자료.

---

## 핵심 분기: 3가지 입력 모드

| 모드 | 호출 | 용도 |
|---|---|---|
| **query** (검색) | `query:"실업률"` | 통계표 찾기 (org_id/tbl_id 확보 단계) |
| **indicator** (주요지표) | `indicator:"DT_2KAA101"` 또는 `indicator:""` | KOSIS가 정한 주요 거시지표 (GDP·CPI·인구·고용 등) |
| **org_id + tbl_id** (특정 통계표) | `org_id:"101", tbl_id:"DT_1B040A3"` | 통계표 데이터 직접 조회 |

우선순위: `org_id+tbl_id` > `indicator` > `query`. 셋 중 하나 필수.

---

## 모드 1: 검색 (query)

자연어로 통계표 찾기. **org_id/tbl_id를 확보하기 위한 1단계** 용도가 대부분.

```
[sense:kosis]{query:"실업률", count:20}
→ 매칭 통계표 목록 (org_id, tbl_id, 제목 포함)
```

| 키 | 설명 |
|---|---|
| `query` | 검색어 (한국어 자연어) |
| `count` | 반환 건수 (기본 10, 최대 50) |

---

## 모드 2: 주요지표 (indicator)

KOSIS가 큐레이션한 거시지표 빠른 조회. **지표 목록부터 보고 싶으면 indicator를 빈 문자열로**.

```
[sense:kosis]{indicator:""}                # 주요지표 전체 목록
[sense:kosis]{indicator:"DT_2KAA101"}      # 특정 지표 시계열
```

| 키 | 설명 |
|---|---|
| `indicator` | 지표 ID (빈 문자열이면 전체 목록) |
| `start_prd_de` / `end_prd_de` | 기간 (`YYYYMM` 또는 `YYYY`) |

자주 보는 지표 ID 예: `DT_2KAA101`(GDP), `DT_2KAA1` 시리즈(국민계정), CPI/고용 지수 등. 모르면 `indicator:""`로 목록부터.

---

## 모드 3: 특정 통계표 (org_id + tbl_id)

가장 풍부한 모드. `info:true`면 통계표 *메타*만, 아니면 *데이터*.

```
[sense:kosis]{org_id:"101", tbl_id:"DT_1B040A3", info:true}        # 메타 (변수 목록 등)
[sense:kosis]{org_id:"101", tbl_id:"DT_1B040A3"}                   # 데이터 (실제 값)
```

| 키 | 설명 |
|---|---|
| `org_id` | 기관 코드 (101=통계청, 116=고용부, ...) |
| `tbl_id` | 통계표 ID (`DT_xxx`) |
| `info` | true면 메타만 — items 한 줄 = 분류 차원(`objL1..N`)·항목(`ITEM`)과 코드 목록(`codes`) |
| `itm_id` | 항목 ID (기본 `ALL`) |
| `obj_l1` | 분류1 (기본 `ALL`) |
| `obj_l2` / `obj_l3` (…`obj_l8`) | 추가 분류. 미지정이면 표 메타의 차원 수만큼 `ALL` 로 **자동 보충**(응답 `classification_filled`·`note`). 좁히려면 `info:true` 로 본 코드를 명시 |
| `prd_se` | 주기 (`Y`/`Q`/`M`. 기본 `Y` 연간) |
| `start_prd_de` / `end_prd_de` | 기간 |

---

## 표준 워크플로우

### 1) 자연어로 통계표 찾기 → 조회 (가장 흔한 패턴)
```
[sense:kosis]{query:"인구 시도별"}
→ org_id, tbl_id 확보
[sense:kosis]{org_id:"101", tbl_id:"DT_1B040A3", info:true}
→ 어떤 차원이 있는지 메타 확인
[sense:kosis]{org_id:"101", tbl_id:"DT_1B040A3",
              prd_se:"Y", start_prd_de:"2015", end_prd_de:"2025"}
→ 실제 데이터
```

### 2) 주요지표 빠른 확인
```
[sense:kosis]{indicator:""}              # 어떤 지표가 있나
[sense:kosis]{indicator:"<선택한 ID>", start_prd_de:"202001"}
```

### 3) 시각화로 연결
```
[sense:kosis]{org_id:"101", tbl_id:"...", prd_se:"M", start_prd_de:"202101"}
  >> [table:chart]{chart_type:"line", x:"period", y:"value"}
```

### 4) 정책/창업 분석용 추세
```
[sense:kosis]{query:"사업체 수 규모별"}
[sense:kosis]{query:"자영업 매출"}
[sense:kosis]{query:"청년 실업률"}
```

---

## 활용 패턴

### 시장 규모 추정
창업·사업 모델 검토 시 KOSIS로 시장 규모·성장률 확인. `query`로 관련 통계표 찾고 시계열로 추세 파악.

### 정책 영향 분석
[[architecture_ibl_action_criteria]]의 모드 1(풀 IBL)로 풍부한 데이터를 가져온 뒤, 차트·요약 액션으로 엮어 보고서 생성.

### 정기 모니터링
주요 지표를 매월/분기 자동 수집:
```
[self:trigger]{op:"create", trigger_id:"monthly_macro",
  type:"schedule", config:{repeat:"monthly", day:5, time:"09:00"},
  pipeline:'[sense:kosis]{indicator:"<지표ID>"} >> [self:write]{path:"reports/macro.md"}'
}
```

---

## 자주 하는 실수

- **세 모드 혼동**: 셋 중 하나만. org_id 있는데 query도 주면 org_id 모드 우선.
- **info 잊음**: 차원 수는 자동 보충되지만(전 분류 ALL = 넓은 표) 특정 성별·연령·지역으로 좁히려면 `info:true` 로 코드를 먼저 봐야 한다.
- **prd_se 누락**: 기본 `Y`(연간). 월별 데이터는 `M`, 분기는 `Q` 명시.
- **start_prd_de 형식**: 연간은 `2024`, 월간은 `202401`. 자릿수 일치 필요.
- **모든 통계표가 매월 갱신 안 됨**: 통계 종류별로 발표 주기 다름. 최신 데이터가 1~2년 전일 수 있음.
- **API 키 부재**: 환경/패키지 config에 KOSIS API 키 필요. 패키지 폴더 config.json 확인.

## 관련

- `data/packages/installed/tools/kosis/` — 패키지
- 차트화: `[table:chart]{chart_type:"line"|"bar"|"pie"|"scatter"|"heatmap"|"candlestick"|"multi"}` (기본 line — 옛 `chart_line`·`chart_bar` 는 이 하나로 통합)
- 정기 모니터링: `self:trigger` schedule 타입

### 분류 오류 복구

차원 수가 모자란 요청은 도구가 표 메타(getMeta)에서 차원을 읽어 빈 자리를 `ALL` 로 채워 한 번
다시 묻는다 — 성공하면 `classification_filled` 가 어느 자리를 채웠는지 말한다. 그래도 `objL`
오류면 코드가 틀린 것이다: 같은 호출을 반복하지 말고 `info:true` 로 차원·코드를 확인한다.
명시한 값은 API 요청에 그대로 실린다. 넓은 표는 필요한 항목·분류로 좁힌다.
요청 규격: [KOSIS 공식 개발가이드](https://kosis.kr/openapi/devGuide/devGuide_0201List.do).
