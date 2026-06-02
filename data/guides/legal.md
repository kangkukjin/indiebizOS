# 법률 정보 가이드

`[sense:legal]` 단일 액션으로 국가법령정보센터(law.go.kr) 10개 영역을 통합 검색·조회한다. **query/id × target** 매트릭스가 핵심 분기.

대한민국 법령·판례 *공식 데이터*. 해석·의견은 별도 — 변호사 상담이나 학술 자료는 이 액션 범위 밖.

---

## 핵심 분기: query(검색) vs id(상세)

```
[sense:legal]{query:"전세 사기"}                          # 검색 (목록)
[sense:legal]{id:"123456", target:"prec"}                # 상세 (단일)
```

| 입력 | 호출 | 결과 |
|---|---|---|
| `query:"..."` | `/lawSearch.do` | 매칭 목록 (제목·ID·요약) |
| `id:"..."` | `/lawService.do` | 단일 항목 전문 |

`query`와 `id` 같이 들어오면 **id 우선**.

---

## target 10종 (영역 분기)

`target` 파라미터로 검색·조회 대상 지정. 기본값은 `law`(법령).

| target | 영역 | 예시 |
|---|---|---|
| `law` (기본) | 법령 | 민법, 주택임대차보호법, 도로교통법 |
| `prec` | 판례 | 대법원·하급심 판결문 |
| `admrul` | 행정규칙 | 각 부처 훈령·예규·고시 |
| `ordin` | 자치법규 | 시·도·구·군 조례 |
| `exp` | 법령해석 | 법제처 유권해석 |
| `detc` | 헌재결정 | 헌법재판소 결정문 |
| `trty` | 조약 | 양자·다자 조약 |
| `eng_law` | 영문법령 | 영문 번역본 |
| `law_term` | 법률용어 | 용어 사전 |
| `law_form` | 법률서식 | 양식·서식 |

---

## 파라미터

| 키 | 필수 | 설명 |
|---|---|---|
| `query` | (둘 중 하나) | 검색어 (자연어 가능) |
| `id` | (둘 중 하나) | 항목 ID. `law_id`/`precedent_id`도 호환 |
| `target` | (기본 law) | 위 10종 |

---

## 표준 워크플로우

### 1) 법령 텍스트 찾기
```
[sense:legal]{query:"주택임대차보호법"}
→ 법령 ID 확보
[sense:legal]{id:"...", target:"law"}
→ 전문 조회
```

### 2) 판례 검색
```
[sense:legal]{query:"전세 사기 임차인 보호", target:"prec"}
→ 관련 판례 목록
[sense:legal]{id:"...", target:"prec"}
→ 판결문 전문
```

### 3) 행정규칙 찾기
```
[sense:legal]{query:"공공 데이터 활용", target:"admrul"}
```

### 4) 자치법규 (특정 지자체 조례)
```
[sense:legal]{query:"서울특별시 옥외광고물 조례", target:"ordin"}
```

### 5) 법률 용어 확인
```
[sense:legal]{query:"선의의 제3자", target:"law_term"}
```

### 6) 영문 법령 (외국인 대응)
```
[sense:legal]{query:"Foreign Investment Promotion Act", target:"eng_law"}
```

---

## 활용 패턴

### "법적 근거"가 필요한 작업
계약서 검토·민원 답변·정책 인용 시:
1. `query` + `target:"law"`로 관련 법령 검색
2. 판단에 영향 주는 판례는 `target:"prec"`
3. 모호한 경우 `target:"exp"`(법령해석) 확인

### 강의/책 인용 자료
법령 인용 시 정확한 조항·시행일이 필요. ID 조회로 전문을 가져와 해당 조항 인용.

### 지자체 사업
자치법규(`ordin`)는 지자체별로 다름. 지자체명을 query에 포함해야 정확.

---

## 자주 하는 실수

- **target 오타**: 정확히 `law`/`prec`/`admrul`/... 중 하나. `precedent` 같은 별칭 안 됨.
- **id 형식**: 숫자 ID 그대로. URL 디코딩 필요한 경우는 거의 없음.
- **query만으로 전문**: 검색 결과는 *목록*만 반환. 전문은 id로 다시 조회 필요.
- **외국 법령**: 영문 *번역* 법령은 `eng_law`. 외국 법령 자체는 이 API에서 안 됨.

## 관련

- `data/packages/installed/tools/legal/` — 패키지 폴더 (API 키는 config.json에)
- 법령 변경 알림 — `[self:trigger]{type:"schedule"}`로 정기 점검 트리거 등록 가능
