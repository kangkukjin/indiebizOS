# Legal 도구 가이드

## 도구 선택 가이드

| 목적 | 도구 | 설명 |
|------|------|------|
| 통합 검색 | `search_legal_info` | 법령, 판례, 행정규칙 등 모두 검색 |
| 법령만 검색 | `search_laws` | 법령만 대상으로 검색 |
| 법령 상세 | `get_law_detail` | 법령 ID로 상세 조회 |
| 판례만 검색 | `search_precedents` | 판례만 대상으로 검색 |
| 판례 상세 | `get_precedent_detail` | 판례 ID로 상세 조회 |
| 범용 상세 | `get_legal_detail` | ID + target으로 모든 종류 상세 조회 |

---

## search_legal_info vs search_laws

| 항목 | search_legal_info | search_laws |
|------|-------------------|-------------|
| 검색 범위 | 법령, 판례, 행정규칙, 자치법규 등 전체 | 법령만 |
| 사용 시점 | 어떤 종류의 법률정보가 있는지 넓게 탐색할 때 | 법령(법률/시행령/시행규칙)만 필요할 때 |
| 결과 | 다양한 target 유형의 결과 혼합 | 법령 결과만 반환 |

---

## target 옵션 참조

`get_legal_detail` 사용 시 target 파라미터에 지정하는 값:

| target | 설명 |
|--------|------|
| `law` | 법령 |
| `prec` | 판례 |
| `admrul` | 행정규칙 |
| `ordin` | 자치법규 |
| `exp` | 법령해석 |
| `detc` | 헌재결정 |
| `trty` | 조약 |
| `eng_law` | 영문법령 |
| `law_term` | 법률용어 |
| `law_form` | 법률서식 |

---

## 기본 워크플로우

```
1. 검색 (search_*)
   - search_legal_info: 넓은 범위 통합 검색
   - search_laws: 법령만 검색
   - search_precedents: 판례만 검색

2. 목록에서 ID 확인
   - 검색 결과에서 원하는 항목의 ID를 확인

3. 상세 조회 (get_*_detail)
   - get_law_detail: 법령 상세
   - get_precedent_detail: 판례 상세
   - get_legal_detail: ID + target으로 범용 상세 조회
```

### 예시: 특정 법령 조회

```
search_laws("개인정보보호법")
→ 결과 목록에서 법령 ID 확인
→ get_law_detail(법령ID)
→ 전문 조회
```

### 예시: 판례 조회

```
search_precedents("임대차 보증금 반환")
→ 결과 목록에서 판례 ID 확인
→ get_precedent_detail(판례ID)
→ 판결 전문 확인
```

### 예시: 통합 검색 후 상세 조회

```
search_legal_info("근로기준법 해고")
→ 법령, 판례, 행정규칙 등 다양한 결과 확인
→ 원하는 항목의 ID와 target 확인
→ get_legal_detail(ID, target="prec")
→ 상세 내용 확인
```
