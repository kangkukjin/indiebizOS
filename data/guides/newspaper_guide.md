# 신문 제작 가이드

키워드 목록으로 Google News를 검색하고 HTML 신문을 자동 생성합니다.

---

## 신문 생성

```
execute_ibl(node="forge", action="newspaper", target=["AI", "경제", "문화", "주식", "여행", "과학"])
```

### 파라미터

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| target | ✅ | 키워드 배열 |
| params.title | - | 신문 제목 (기본: "IndieBiz Daily") |
| params.exclude_sources | - | 제외할 뉴스 출처 배열 |

### 예시

기본:
```
execute_ibl(node="forge", action="newspaper", target=["AI", "청주", "세종", "경제"])
```

제목 지정 + 출처 제외:
```
execute_ibl(node="forge", action="newspaper", target=["AI", "경제", "주식"], params={"title": "투자 뉴스", "exclude_sources": ["조선일보"]})
```

---

## 결과

- `outputs/newspaper_{타임스탬프}.html` 파일 생성
- 반환값에 `file` 경로 포함
- 키워드당 7개 기사 수집
- 반응형 3단 그리드 레이아웃

---

## 브라우저에서 열기

신문 생성 후 반환된 file 경로로:
```
execute_ibl(node="system", action="open", target="{file 경로}")
```

---

*최종 업데이트: 2026-02-25*
