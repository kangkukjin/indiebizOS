# Memory & Skill 가이드

## 메모리 구조

```
영구메모 (핫)          항상 프롬프트에 포함. UI에서 편집. 간결하게.
  │
심층 메모리 (에이전트별)  필요할 때 검색. memory_save/search/read.
  │
스킬 DB (공유)          전 에이전트 공유 지식. skill_search/read.
```

영구메모에는 현재 상태, 핵심 약칭 정도만 넣는다.
나머지는 전부 심층 메모리에 저장하고 필요할 때 꺼내 쓴다.

---

## 저장 규칙: 언제 memory_save를 호출하는가

### 반드시 저장

| 상황 | category | 저장 내용 |
|------|----------|----------|
| 파일을 생성/수정/이동/삭제했을 때 | `작업기록` | 무엇을, 어디에, 왜 |
| 에러를 해결했을 때 | `에러해결` | 에러 메시지, 원인, 해결법 |
| 사용자 선호를 발견했을 때 | `사용자선호` | 코드 스타일, 이름 규칙, 별명, 약칭 |
| 중요한 결정을 내렸을 때 | `의사결정` | 선택지, 선택 이유, 트레이드오프 |
| 환경/설정을 파악했을 때 | `환경정보` | 경로, 포트, DB 위치, 의존성 |

### 판단해서 저장

| 상황 | category | 판단 기준 |
|------|----------|----------|
| 분석 결과가 나왔을 때 | `분석결과` | 다시 만들기 비용이 큰가? |
| 외부 API/서비스 정보 | `환경정보` | 다음에 또 필요한가? |
| 복잡한 작업 중간 상태 | `작업기록` | 이어서 할 가능성이 있는가? |

### 원칙

**의심스러우면 저장하라.** INSERT 한 건의 비용보다 기억하지 못해서 처음부터 다시 탐색하는 비용이 훨씬 크다.

### 좋은 저장 예시

```
memory_save(
  content="프론트엔드 빌드 에러: node 18에서 crypto 모듈 누락. --openssl-legacy-provider 플래그로 해결. package.json scripts에 추가함.",
  keywords="빌드에러,crypto,openssl,node18,프론트엔드",
  category="에러해결"
)
```

```
memory_save(
  content="사용자가 '홈페이지'라고 하면 /Users/xxx/Desktop/AI/HomePages/indiebiz-homepage를 뜻함. Cloudflare Pages로 배포 중.",
  keywords="홈페이지,경로,배포,cloudflare",
  category="사용자선호"
)
```

```
memory_save(
  content="api_scheduler.py 리팩토링 완료. 기존 단일 파일(1200줄)을 scheduler_core.py + scheduler_jobs.py + api_scheduler.py로 분리. 테스트 통과 확인.",
  keywords="스케줄러,리팩토링,분리,api_scheduler",
  category="작업기록"
)
```

### keywords 작성법

- 검색할 때 떠올릴 단어를 넣는다
- 쉼표로 구분, 5~10개
- 한글/영어 혼용 가능 (에러 메시지는 영어 그대로)
- 파일명, 함수명, 패키지명 등 고유명사를 포함

---

## 검색 규칙: 언제 memory_search를 호출하는가

### 반드시 검색

| 상황 | 검색 쿼리 예시 |
|------|---------------|
| 이전에 같은/비슷한 작업을 한 적이 있을 때 | `memory_search(query="스케줄러 리팩토링")` |
| 에러를 만났을 때 | `memory_search(query="crypto openssl 에러")` |
| 사용자가 이전 작업을 언급할 때 | `memory_search(query="홈페이지 배포")` |
| 사용자가 약칭/별명을 쓸 때 | `memory_search(query="그 서버", category="사용자선호")` |

### 판단해서 검색

| 상황 | 이유 |
|------|------|
| 새 세션에서 복잡한 작업 시작 전 | 이전 맥락이 있을 수 있다 |
| 환경 경로나 설정을 모를 때 | 이전에 파악해둔 정보가 있을 수 있다 |
| 코드 구조를 파악해야 할 때 | 이전 분석 기록이 있을 수 있다 |

### 검색 → 읽기 흐름

```
1. memory_search(query="키워드")
   → 결과 목록 (id, 미리보기 100자, created_at, used_at)

2. 관련 있는 항목 발견?
   → memory_read(memory_id=N) 으로 전문 읽기
   → used_at이 자동 갱신됨

3. 못 찾으면?
   → 직접 탐색 후, 알게 된 내용을 memory_save
```

---

## 시간 정보 활용

모든 메모리에는 `created_at`(작성 시각)과 `used_at`(마지막 참조 시각)이 기록된다.

- `used_at`이 null → 저장 후 한 번도 안 읽은 기록
- `used_at`이 최근 → 자주 참조하는 활성 기록
- `created_at`이 오래되고 `used_at`도 오래됨 → 낡은 기록, 정리 대상 가능

---

## 스킬 시스템

심층 메모리가 "내가 한 일, 내가 알게 된 것"이라면,
스킬은 **"이런 일은 이렇게 하라"는 작업 절차에 대한 장기 기억**이다.
모든 에이전트가 공유한다.

- 복잡한 작업의 단계별 절차
- 도메인별 판단 기준이나 체크리스트
- 반복되는 작업의 베스트 프랙티스

### 언제 검색하는가

처음 하거나 복잡한 작업 전에 관련 스킬이 있는지 확인한다.

```
skill_search(query="계약서 검토")
  → 관련 스킬 목록
skill_read(skill_id=N)
  → 전문 읽기, 참조하여 작업 수행
```

### 스킬 등록

스킬은 주로 사용자나 관리자가 등록한다.

- 직접: `skill_add(name, content, keywords, ...)`
- 파일: `skill_import_md(file_path="경로")`
- 일괄: `skill_import_md(import_all=true)` → data/skills/ 전체 임포트

---

## 도구 레퍼런스

| 도구 | 용도 |
|------|------|
| `memory_save(content, keywords, category)` | 심층 메모리 저장 |
| `memory_search(query, category?, limit?)` | 키워드 검색 (미리보기 반환) |
| `memory_read(memory_id)` | 전문 읽기 + used_at 갱신 |
| `memory_delete(memory_id)` | 삭제 |
| `skill_search(query, category?, limit?)` | 스킬 검색 |
| `skill_read(skill_id)` | 스킬 전문 읽기 |
| `skill_add(name, content, keywords?, ...)` | 스킬 등록 |
| `skill_delete(skill_id)` | 스킬 삭제 |
| `skill_import_md(file_path?, import_all?)` | 마크다운에서 스킬 임포트 |
