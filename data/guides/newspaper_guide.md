# 신문 제작 가이드

키워드 목록으로 Google News를 검색하고 HTML 신문을 자동 생성합니다.

---

## 신문 생성 + 브라우저 열기

```
[engines:newspaper]{keywords: "AI, 청주, 세종, 문화, 여행, 과학, 경제"} >> [self:open]
```

파이프라인(`>>`)을 쓰면 newspaper의 결과(file 경로 포함)가 자동으로 open에 전달되어 브라우저에서 열립니다.

### 파라미터

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| keywords | ✅ | 키워드 (쉼표 구분) |
| title | - | 신문 제목 (기본: "IndieBiz Daily") |
| exclude_sources | - | 제외할 뉴스 출처 배열 |
| count | - | 키워드당 기사 수 (기본: 7) |

### 예시

기본 (생성만):
```
[engines:newspaper]{keywords: "AI, 청주, 세종, 경제"}
```

생성 후 브라우저 열기:
```
[engines:newspaper]{keywords: "AI, 경제, 주식"} >> [self:open]
```

제목 지정 + 출처 제외:
```
[engines:newspaper]{keywords: "AI, 경제, 주식", title: "투자 뉴스", exclude_sources: ["조선일보"]} >> [self:open]
```

---

## 결과

- `outputs/newspaper_{타임스탬프}.html` 파일 생성
- 반환값에 `file` 경로 포함
- 반응형 3단 그리드 레이아웃

---

## 주의: 파이프라인 변수 참조 금지

`$prev.file`, `$result.path` 같은 변수 참조 문법은 **존재하지 않습니다**.
`>>` 연산자가 이전 step의 결과를 자동으로 다음 step에 전달합니다.

```
WRONG: [engines:newspaper]{keywords: "AI"} >> [self:open]{path: $prev.file}
RIGHT: [engines:newspaper]{keywords: "AI"} >> [self:open]
```

---

*최종 업데이트: 2026-03-08*
