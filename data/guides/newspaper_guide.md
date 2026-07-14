# 신문 제작 가이드

뉴스를 수집하여 신문 형태로 발행합니다. 신문은 **앱 모드의 계기(NewspaperInstrument)**이자, 위임("신문 만들어줘")으로도 만들 수 있습니다. 두 경로가 **같은 판(edition) 파일**을 쓰도록 맞춰야 데스크탑·폰·원격이 같은 신문을 봅니다.

> ⚠️ 옛 `[engines:newspaper]` 어휘는 **은퇴**했습니다(브라우저 자동 열기 포함). 현행 신문은 `[sense:search_gnews]` 팬아웃 + 판 파일 저장 모델입니다. 아래는 실제 계기(`frontend/src/components/NewspaperInstrument.tsx`) 동작에 맞춘 정본입니다.

## 발행 모델 — '판(edition)'

신문은 **열 때마다 재취재하지 않습니다.** '새로 발행'을 누를 때(또는 위임으로 만들 때)만 뉴스를 긁어 **판**을 만들고, 다음에 열면 저장된 판을 그대로 보여줍니다. 판은 앱모드 프로젝트 `outputs/` 아래 **최신 하나**만 유지(덮어쓰기)하며, 같은 `sections`에서 **세 파일**을 파생합니다:

| 파일 | 용도 | 누가 읽나 |
|------|------|-----------|
| `outputs/newspaper_current.json` | 구조화 판(sections 원본) | **데스크탑 계기가 카드 그리드로 재렌더** (`loadEdition`) |
| `outputs/newspaper_current.md` | 사람이 읽는 마크다운 | 폰/원격 뷰어(@hub), 파일 공유 |
| `outputs/newspaper_current.html` | 자기완결 HTML(제호·마스트헤드) | 폰 '저장·공유'(카톡 등) |

★ 셋 다 `project_id: "앱모드"` 로 저장. **데스크탑 계기는 JSON을 읽으므로**, 위임으로 신문을 만들 때 MD만 쓰면 데스크탑 화면에 반영되지 않습니다 — 반드시 JSON도 함께 쓸 것.

JSON 판 구조(`loadEdition`이 기대하는 형태):
```json
{ "title": "청주 데일리", "keywords": ["AI", "청주", ...],
  "sections": [ { "keyword": "🔥 오늘의 핫토픽", "items": [ {"title":..., "url":..., "summary":..., "role":"hot"} ] }, ... ],
  "dateLabel": "2026년 7월 11일 (토)", "issuedAt": "2026-07-11T..." }
```

## ★현행 발행 레시피 ("신문 만들어줘"/"새로 발행" 위임 시 이대로)

1. **핫토픽**: `[sense:search_gnews]{headlines: true, curate: 7}` — 오늘 가장 많이 다뤄진 사건. 섹션 이름은 `🔥 오늘의 핫토픽`, 맨 위에.
2. **섹션별 기사**: 사용자 관심 키워드마다 `[sense:search_gnews]{query: "<키워드>", curate: 7}` 로 섹션 하나씩. (계기 기본 키워드 12개: 청주·AI·문화·드라마·영화·만화·세종·경제·주식·부동산·AI 에이전트·중국 경제. 제호 기본값 `청주 데일리`. 뒤 3개=2026-07-14 발아 대조가 찾은 실타래 공백 반영 — 키워드는 정적이 아니라 실타래 따라 갱신하는 취재 prior.)
3. **조립·저장(판 3파일, 전부 `project_id: "앱모드"`)**:
   - JSON: `[self:write]{path: "outputs/newspaper_current.json", content: "<위 구조 JSON 문자열>", project_id: "앱모드"}` — **데스크탑 반영 필수**.
   - MD: 섹션 items를 `[table:document]{format: "markdown", title: ..., meta: "<날짜>", group_by: "section", items: [...]}` 로 직렬화 → `[self:write]{path: "outputs/newspaper_current.md", project_id: "앱모드"}`.
   - (선택) HTML: 폰 공유가 필요하면 자기완결 HTML도 같은 경로에.
   - **아카이브(발아 대조용)**: 같은 JSON을 `[self:write]{path: "outputs/newspaper_archive/newspaper_<YYYY-MM-DD>.json", project_id: "앱모드"}` 로도 저장 — 고정 파일은 덮어쓰기라 과거 판이 사라지는데, 편집장 픽(role/why) ↔ 이후 에피소드·vault 발아 대조에는 판별 이력이 필요. (데스크탑 '새로 발행' 버튼은 자동으로 남김.)
   - 완료 조건 = `projects/앱모드/outputs/newspaper_current.json` + `.md` 갱신.

`curate`는 넓게 오버페치(~100 후보) 후 경량 AI '편집장'이 dedup + 뉴스가치 순 상위 N(=curate 값)을 뽑고, 각 기사에 role을 붙입니다:
- `hot` — 여러 매체가 널리 다룸
- `delta` — 사용자 관점 코어(`vault/위키/관점 코어.md`) 대비 새 정보. **관점 코어가 없으면 조용히 뉴스가치 휴리스틱으로 폴백**(개인화 미반영일 수 있음).
- `surface` — 지배 프레임과 결이 다른 이질 1건(필터버블 반대힘).

뽑히지 않은 나머지는 응답의 `pool` 필드로 반환되어, 편집신문(사용자 큐레이션)에서 대체 후보로 쓰입니다. 응답의 `perspective` 필드(true/false)가 관점 코어 반영 여부이며, 판 JSON에도 저장되어 데스크탑 상단바에 "💡 관점 반영/일반 판"으로 표시됩니다.

**소스**: 영어 키워드 섹션에는 **가디언(The Guardian)**이 자동 합류합니다 — `sources` 파라미터(기본 `"gnews,guardian"`, `"gnews"`로 끔). 정본 구현은 study 패키지 `search_guardian`(+`GUARDIAN_API_KEY`), web이 빌려 씀. 한국어 키워드는 가디언 코퍼스에 없어 자동 생략.

## 핵심 원칙

1. **"신문 만들어"라고 하면 항상 같은 포맷** — 2컬럼 카드 그리드 + 기사 링크.
2. **섹션당 기사 수 기본 7개** (`curate: 7`, 계기의 `SECTION_SIZE = 7` 과 일치). 핫토픽·키워드 섹션 모두 7.
3. **브라우저 자동 열기 없음** — 판 파일에 저장하고, 계기/뷰어가 읽어 표시합니다. (옛 `>> [limbs:os_open]` 는 은퇴.)
4. **위임과 계기는 같은 판 파일을 공유** — 위임으로 만들면 JSON+MD를 쓰고, 데스크탑에서 열면 JSON을 읽어 그대로 보입니다.

## 공유

- **파일 공유**: 파생된 `newspaper_current.html` 을 카톡 등으로 첨부(폰 뷰어의 '저장·공유' 버튼). 또는 데스크탑 'HTML 내보내기'(Blob 다운로드).
- **링크 발행**: `[table:document]{format: "markdown", ...}` >> `[others:publish]{title: ..., slug: "newspaper-<YYYYMMDD>"}` → Nostr NIP-23 njump 링크. 같은 slug 재발행 = 같은 주소 갱신.

---

*최종 업데이트: 2026-07-11 — 판(edition) 3파일 모델·curate 7·브라우저 열기 없음·위임/계기 저장 경로 통일로 정본화. 옛 `[engines:newspaper]` 사용법 절 제거.*
