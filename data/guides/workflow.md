# 워크플로우 저장 & 실행 가이드

## 워크플로우란?

자주 쓰는 IBL 파이프라인을 **이름 붙여 저장**하고, 나중에 이름만으로 실행하는 기능.
저장된 워크플로우는 `data/workflows/{id}.yaml` 파일로 관리된다.

---

## 저장

```
[self:save_workflow]{name: "구글신문", description: "구글 뉴스 수집 후 신문 생성", pipeline: "[engines:newspaper]{keywords: \"AI, 경제, 문화\"} >> [self:open]"}
```

### params 필드

| 필드 | 필수 | 설명 |
|------|------|------|
| name | ✅ | 워크플로우 이름 (실행 시 workflow_id로 사용) |
| description | - | 설명 |
| pipeline | ✅ | IBL 파이프라인 문자열 |

저장 시 name을 기반으로 ID가 자동 생성된다 (예: "구글신문" → `구글신문`).

---

## 실행

```
[self:run]{workflow_id: "구글신문"}
```

workflow_id에 워크플로우 이름 또는 ID를 넣으면 저장된 pipeline이 실행된다.

---

## 목록 조회

```
[self:list_workflows]
```

---

## 상세 조회

```
[self:get_workflow]{workflow_id: "구글신문"}
```

---

## 삭제

```
[self:delete_workflow]{workflow_id: "구글신문"}
```

---

## 파이프라인 연산자

### >> (순차 실행)
이전 step의 결과가 다음 step에 **자동 전달**된다. 변수 참조 문법(`$prev`, `$result` 등)은 존재하지 않는다.

```
RIGHT: [engines:newspaper]{keywords: "AI, 경제"} >> [self:open]
WRONG: [engines:newspaper]{keywords: "AI"} >> [self:open]{path: $prev.file}
```

### & (병렬 실행)
여러 step을 동시에 실행. 모든 결과가 합쳐져서 다음 step에 전달된다.
각 브랜치에 **90초 타임아웃**이 적용됨 — 한 브랜치가 멈춰도 나머지 결과는 정상 수집됨.

```
[sense:search_news]{query: "AI", count: 7} & [sense:search_news]{query: "경제", count: 7}
```

### ?? (폴백)
앞의 step이 실패하면 뒤의 step을 실행.

```
[sense:price]{symbol: "AAPL"} ?? [sense:web_search]{query: "AAPL stock price"}
```

### 타임아웃
- 개별 도구 실행: **60초** (IBL 엔진 레벨). 초과 시 에러 반환하고 다음 동작으로 진행.
- 병렬 브랜치: **90초**. 한 브랜치가 타임아웃되면 해당 브랜치만 에러, 나머지는 정상.

---

## 사용 시나리오

### 사용자가 워크플로우 저장을 요청할 때
1. 사용자의 요청에서 이름, 설명, 파이프라인 추출
2. `[self:save_workflow]`로 저장
3. 저장된 ID 반환

### 사용자가 워크플로우 실행을 요청할 때
1. `[self:list_workflows]`로 목록 확인
2. 매칭되는 워크플로우 찾기
3. `[self:run]{workflow_id: "이름"}`으로 실행

### "OOO 워크플로우 만들어줘" 같은 요청
1. 사용자의 의도를 파악하여 적절한 파이프라인 작성
2. `[self:save_workflow]`로 저장
3. 저장 완료 안내

---

*최종 업데이트: 2026-03-08*
