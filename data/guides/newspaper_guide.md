# 신문 제작 가이드

뉴스를 수집하여 신문 형태로 보여줍니다.

## ★현행 발행 레시피 (2026-07 — "신문 만들어줘"/"새로 발행" 위임 시 이대로)
> 아래 옛 `[engines:newspaper]` 어휘는 **은퇴**했다. 현행 신문은 `[sense:search_gnews]` 팬아웃으로 만든다.

1. **핫토픽**: `[sense:search_gnews]{headlines: true, curate: 7}` — 오늘 가장 많이 다뤄진 사건.
2. **섹션별 기사**: 사용자 관심 키워드(예: AI, 청주, 경제 — 프로필 반영)마다 `[sense:search_gnews]{curate: 5}` 로 섹션 하나씩.
3. **조립·저장(고정명)**: 핫토픽+섹션들을 마크다운 신문으로 엮어 고정 파일에 저장 —
   `[self:write]{path: "outputs/newspaper_current.md", content: "<신문 마크다운>", project_id: "앱모드"}`.
   ★ **project_id: "앱모드"** 필수(폰/원격이 이 고정 파일을 @hub 로 읽는다). 완료 조건 = `projects/앱모드/outputs/newspaper_current.md` 갱신.

---

## 핵심 원칙

1. **"신문 만들어"라고 하면 항상 같은 포맷** — 2컬럼 카드 그리드 + 기사 링크
2. **소스가 달라도 형태는 동일** — 구글 뉴스든, 가디언이든
3. **기본 기사 수는 7개** (별도 지정하지 않는 한)
4. **자동으로 브라우저에 띄움** — "브라우저에 띄워"를 명시하지 않아도 반드시 열기
5. **절대경로 사용** — 브라우저에 띄울 때 반드시 절대경로

---

## 사용법

모든 신문은 `[engines:newspaper]` 하나로 만듭니다.

### 구글 뉴스 (기본)

```
[engines:newspaper]{keywords: "AI, 청주, 경제"} >> [limbs:os_open]
```

### 가디언 뉴스

```
[engines:newspaper]{keywords: "Iran war, AI", source: "guardian"} >> [limbs:os_open]
```

### 파라미터

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| keywords | ✅ | 키워드 (쉼표 구분) |
| source | - | "google" (기본), "guardian" |
| title | - | 신문 제목 (기본: "IndieBiz Daily") |
| language | - | 자동 결정 (google→ko, guardian→en). 수동 지정 가능 |
| exclude_sources | - | 제외할 뉴스 출처 (google만 해당) |
| count | - | 키워드당 기사 수 (기본: 7) |

---

## 주의사항

1. **파이프라인 변수 참조 없음** — `$prev.file` 같은 문법은 없습니다
2. **`>> [limbs:os_open]`을 붙이면** 생성 후 자동으로 브라우저에 열립니다

---

*최종 업데이트: 2026-03-14*
