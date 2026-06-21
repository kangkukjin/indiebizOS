# 다른 몸 일반화 — forager 핸드오프 (2026-06-20 작성)

> **상태 업데이트(2026-06-20)**: **코드·웹 두 몸 thin 구현·실LLM 종단 검증 완료.** 설계 결정은
> `FORAGER_MULTIBODY_DESIGN.md`. body가 이제 *포식 공간*을 키잉(`mac`/`code:<repo>`/`web`), 하드웨어
> 자아는 게이트로 분리. 구현=`agent_cognitive._forage_space`(code→web→disk 추론)·`_repo_root_path`(코드 locus 정규화),
> `file_index.code_candidate_paths`(residual 코드 모집단), 증류 프롬프트 공간-인식(code/web/disk), `forage_consolidation`
> 공간-중립. **웹 음성단언(§3.2·§6.4)은 *재정의가 아니라 scope-out*으로 닫음**: 모집단 무한·비열거→균일표본 정의
> 불가→residual은 열거가능 공간(디스크·코드) 전용, 웹 "충분함"은 AI의 berrypicking 포화 판단(`DESIGN.md` §8).
> 웹의 가치는 owner_model 교차-몸 전이(§12.1 실증·복리 루프).
>
> **★collapse(2026-06-20)**: 코드·웹을 키워드-cue+per-medium 분기로 짠 게 *매체마다 코드 느는 냄새*라,
> **불변 2축**으로 접음(DESIGN §9) — ① body=문자열(증류기 LLM이 명명) ② 열거 가능한가(이진). cue 리스트·
> per-medium 분기 삭제, 회상=전-body 자기스코핑, residual=이진(code vs path-walk). **결과: 책·외장볼륨·
> 미래 매체 = 새 코드 0**(AI가 `book:<제목>`/`disk:<라벨>` 명명, 실사용 시 검증만). 아래 §0~9 는 원래
> 항해도(역사적 맥락 — 웹 음성단언 §3.2·§6.4, "매체마다 뭘 하나" §4 모두 위 두 결정으로 대체됨).

*성격: **다음 세션 진입점.** "하나의 forager, 여러 몸"(디스크→코드·웹·책)을 어떻게 실현하나. 포식 기억 시스템(디스크)은 완성됨 — 이건 그 *몸 확장* 설계 출발점. 깊은 연구는 `FILE_FORAGING_RESEARCH.md`(§1.2·§3.3·§6·§7.7), 디스크 구현은 `FORAGER_MEMORY_GUIDE.md`·`FORAGER_MEMORY_SCHEMA.md`.*

> **한 줄**: forager 정책(싼것먼저·가지치기·회상·증류·잔여측정)은 *몸 독립*이고 이미 작동한다. 남은 건 **probe(손)를 몸마다 바인딩**하고 **기억을 "하드웨어 자아"가 아니라 "포식 공간"별로** 키잉하는 것. 절반은 이미 됐다.

---

## 0. 30초 요약

- **명제**(연구 §1.2·§6): 큰 공간에서 *이미 있는 걸 찾기*의 골격은 몸과 무관 — 디스크·코드베이스·웹·책·실종아이가 같다. **포식 정책=상부구조(몸 독립), 싼 탐침·내용 열기=하부구조(몸별)** — 헌법 [[architecture_substrate_superstructure_seam]].
- **이미 된 절반**: ① `owner_model`(주인모델)은 *설계상 몸 독립*이고 **교차-몸 전이 실증됨**(디스크서 쌓은 모델이 웹 질의 "강국진"을 본인 논문으로 핀포인트 — RESEARCH §12.1). ② forage 루프=AI 자체(몸 무관). ③ 증류·정리·안전판·`residual` *로직*은 몸 무관. ④ 다른 몸 probe들이 *이미 어휘에 있음*(`grep`/`glob`/`read`=코드, web 패키지=웹).
- **★중심 갭**: 현재 `body`가 **"포식 공간"이 아니라 "하드웨어 자아"(mac/phone)** 로 conflate돼 있다. `_search_forage_memory`/`_distill_forage_memory`가 `detect_body().profile`(="mac")을 body로 넘김 → 모든 지도가 "mac" 한 통에. 다중 몸은 body를 *포식되는 공간*(이 디스크/이 레포/웹/이 책)으로 분리해야.
- **다음 1순위**: 연구→설계(probe 계약 + body 재정의) 먼저, 그다음 **첫 몸=코드베이스** thin 구현(probe가 이미 다 있어 가장 싸게 검증 가능).

---

## 1. 이미 된 것 (재확인 — 재발명 금지)

| 자산 | 상태 | 몸 독립? |
|---|---|---|
| **forage 루프** | AI 자체(인지층). 싼것먼저·가지치기·정지를 NL로 | ✅ 완전 몸 독립 |
| **`owner_model`** | 정체·분야·소속·신호·어휘·습관. `forage_memory.db` | ✅ 설계상 몸 독립 + **교차-몸 전이 실증**(§12.1) |
| **`forage_map`** | 폴더 정체·관습·죽은가지·기질. `body` 컬럼으로 키잉 | ⚠️ 키잉은 몸별인데 *값이 conflate*(아래 §3.1) |
| **증류/정리/surface/안전판** | `_distill_forage_memory`·`forage_consolidation`·prior_class·defeasible | ✅ 로직 몸 무관 (probe·candidate만 디스크 가정) |
| **`residual`(F3)** | 균일표본+Wilson 추정 | ⚠️ 로직 몸 무관 / `candidate_paths`는 디스크 전용(§3.3) |
| **probe 어휘** | 디스크: `fs_query`/`grep`/`find`/`glob`/`read`/`residual`/`describe`. 코드: `grep`/`glob`/`read`(scope project/workspace). 웹: web 패키지(search/crawl/fetch). 라이브러리: context7 | ✅ *대부분 이미 존재* |

**함의**: 새로 "지을" 게 적다. forager·정책·기억 스키마·안전판은 그대로 쓰고, **(a) body를 공간별로 키잉 (b) residual의 candidate 열거를 몸별로 (c) 각 몸 probe를 forage 루프에 묶기**만 하면 된다.

---

## 2. "몸"이란 무엇인가 — 핵심 재정의 (★이 절이 설계를 지배)

### 2.1 두 가지 "몸"이 섞여 있다
- **하드웨어 자아**(`detect_body()`): mac vs phone. *누가 포식하나*. 주관적 기억(대화·해마)이 갈리는 축([[project_body_proprioception_detection]]).
- **포식 공간**(forage_map이 키잉해야 할 것): 이 디스크 / 이 외장볼륨 / 이 코드레포 / 웹 / 이 책. *무엇을 포식하나*.

현재 코드는 전자(`mac`)를 `forage_map.body`에 넣어 둘을 conflate한다. 스키마 주석은 이미 `"mac" | "disk:<uuid>" | "phone"`을 의도했으나 배선이 못 따라감.

### 2.2 올바른 그림
- `owner_model` = **주인(나)** 1명, 모든 공간·모든 하드웨어 자아 공유. (이미 맞음.)
- `forage_map` = **포식 공간**별. body 키 = `disk:<volume-uuid>` / `code:<repo-root>` / `web` / `book:<id>` 등.
- 하드웨어 자아(mac/phone)는 *별개 축* — 맥 자아가 디스크A·레포B·웹을 포식하면 forage_map에 body가 3개. (폰 자아는 자기 기억 따로.)

### 2.3 그래서 할 일
- `forage_memory`의 `body` 인자를 **포식 공간 식별자**로 받도록(이미 문자열이라 스키마 변경 0 — *의미*만 바꿈).
- `_search_forage_memory`/`_distill_forage_memory`가 **공간을 추론**해 넘기게: 질의/스코프의 경로→`disk:`/`code:`, URL→`web`, 활성 프로젝트·레포 루트 등. (작은 추론 문제 — 첫 버전은 AI가 명시하거나 경로에서 파생.)

---

## 3. probe 계약 (probe / peek / cost) — 설계 질문

연구 §3.3·§7.7이 가리킨 인터페이스. 각 몸이 forager에게 제공해야 할 *능력 3종*:

| 능력 | 디스크(있음) | 코드 | 웹 | 책 |
|---|---|---|---|---|
| **probe**(싼 메타·열거) | `fs_query`/`find`(이름·메타) | `glob`/심볼 | search 결과 목록 | 목차·장 제목 |
| **peek**(비싼 내용) | `read` | `read`/`grep` | `fetch` | 본문 구절 |
| **cost/기질**(가용성) | Spotlight/EXIF 색인 유무 | 인덱스 유무 | rate limit·페이월 | OCR 필요 여부 |

### 3.1 결정 질문 A — probe 계약을 *코드 추상*으로 지을까, *문서 프로토콜*로 둘까
- forager=AI 원칙([[architecture_body_vs_absorbable]]) → **OO 추상 클래스를 짓지 말 것**이 1순위 가설. AI가 이미 grep/read/fetch를 골라 쓴다.
- 그렇다면 "계약"=각 몸에 대해 *어떤 IBL 액션이 probe/peek 역할인지* 매핑 + body 키잉 + 기질 점검을, 코드가 아니라 *얇은 레지스트리/문서*로. (침식 테스트 적용.)

### 3.2 결정 질문 B — `residual`의 몸별 candidate 열거
- `residual{sample}`은 `file_index.candidate_paths`(mdfind/walk)로 모집단을 뽑는다 = 디스크 전용.
- 코드: candidate = `glob`/`grep` 매칭 파일. 웹: candidate = search 결과(유한·랭킹됨, 균일표본 의미 약함). 책: candidate = 장·절.
- → `residual`을 **몸별 candidate provider**로 일반화하거나, 몸별 얇은 analog. *웹은 균일표본 전제가 깨짐*(모집단이 무한·비열거) → "음성 단언"의 의미가 디스크와 다름(연구 숙제).

### 3.3 결정 질문 C — 기질 부재 1급 대응 (§7.7, F1)
- 여행 트레이스 교훈: 싼 메타(EXIF/Spotlight)가 *아예 없을* 수 있음. probe 계약은 "이 몸에서 이 신호가 가용한가"를 1급으로 점검+폴백해야. (`forage_map.kind='substrate'`가 이미 이걸 기록 — 활용.)

---

## 4. 구체 갭 목록 (코드를 어디서 만지나)

1. **body 재정의**(§2.3): `backend/agent_cognitive.py`의 `_search_forage_memory`·`_distill_forage_memory`가 `detect_body().profile` 대신 *포식 공간 식별자*를 산출·전달. 공간 추론 헬퍼(경로→`disk:`/`code:`, URL→`web`).
2. **공간 식별**: `disk:<volume-uuid>`를 실제로 얻기(외장볼륨 UUID — `diskutil`/마운트 경로). 코드=레포 루트(.git 상향 탐색). 첫 버전은 마운트 경로/레포 경로 문자열로 충분.
3. **residual 일반화**(§3.2): `[self:residual]`이 몸별 candidate provider를 받게(디스크=file_index, 코드=glob/grep). 웹은 별도 취급(연구).
4. **probe 매핑**(§3.1): 어떤 액션이 어느 몸의 probe/peek인지 얇은 매핑(문서 우선, 코드 최소).
5. **forage 의도 게이트 확장**: `_FORAGE_CUES`가 디스크 어휘 위주 — 코드·웹 포식 의도도 감지하게(또는 공간 추론으로 대체).

---

## 5. 첫 몸 추천 = **코드베이스**

- **이유**: probe(`grep`/`glob`/`read`)가 *이미 다 있음* → 새 probe 구축 0. body 키잉·residual 일반화 갭만 깨끗이 드러남. 검증 쉬움(이 레포를 직접 포식). owner_model의 "개발 습관·코드 관습"이 즉시 유용.
- **검증 시나리오**: "이 코드베이스에서 X 하는 곳 찾아줘" → forage(grep/read) → 증류(`code:indiebizOS` body에 "ibl 액션은 self.yaml src에 정의" 같은 지도) → 새 세션이 그 지도로 직행. residual로 "X 처리하는 데가 더 없나" 측정.
- **그다음**: 웹(균일표본 전제 깨짐 = 음성단언 재정의 연구) → 책(목차 probe).

대안: 웹부터 하면 owner_model 교차-몸 전이(이미 실증)를 *생산화*하는 매력이 있으나, residual·candidate 열거가 디스크와 가장 다른 몸이라 설계 부담 큼. 코드가 가장 싼 첫걸음.

---

## 6. 열린 질문 (설계 단계서 답할 것)

1. **probe 계약 = 코드냐 문서냐**(§3.1) — forager=AI면 문서+얇은 매핑이 1순위 가설.
2. **공간 식별의 입도**: 디스크=볼륨? 폴더? / 코드=레포? 패키지? / 웹=도메인? 사이트? — forage_map 키의 입도.
3. **공간 추론 위치**: 인지층이 자동 추론(경로/URL) vs AI가 명시 vs 활성 프로젝트서 파생.
4. **웹의 음성 단언**(§3.2): 모집단이 무한·비열거 → residual 디스크판이 안 맞음. "충분히 찾았나"를 웹에선 어떻게? (berrypicking 종료 + 출처 다양성?)
5. **owner_model 풍부화 루프**: 교차-몸이 owner_model을 역확증·풍부화(§12.1④ 복리). 그 쓰기를 어디서 트리거?
6. **하드웨어 자아 × 공간**: 폰 자아도 자기 공간(폰 파일)을 포식하면 forage_map에 `phone-fs:` body? 자아별 사적 기억 원칙과 정합?

---

## 7. 추천 접근

포식 기억이 그랬듯 **research(얇게)→design 결정화→thin 구현→검증**. 단 연구는 가벼워도 됨(골격은 이미 RESEARCH에 있음):
1. **§2 body 재정의 + §3 probe 계약**을 짧은 설계 노트로 결정화(이 핸드오프 §3 열린질문 답).
2. **코드 몸 thin 구현**(§5): body 키잉 + 공간 추론 + (필요시) residual candidate provider.
3. **검증**: 이 레포를 두 세션 포식(콜드→증류→웜 직행), residual로 망라 측정.
4. **과(過)설계 금지**: probe OO 추상·몸별 엔진 짓지 말 것. AI가 루프, 우리는 키잉·매핑·candidate provider *얇게*.

---

## 8. 재사용 자산 / 포인터

- **교차-몸 실증**(이미 됨): owner_model(Kukjin Kang 신경과학 모델)이 웹 질의 "강국진"을 본인 논문으로 핀포인트 — RESEARCH §12.1. 시드 모델은 거기.
- **디스크 구현**(복제 대상 패턴): `backend/forage_memory.py`(2층·증류·정리·lazy부패)·`forage_consolidation.py`·`agent_cognitive.py`(`_search_forage_memory`/`_distill_forage_memory`)·`data/ibl_nodes_src/self.yaml`(`forage`/`residual`).
- **probe 후보**: 코드=`self:grep`/`glob`/`read`(scope project/workspace). 웹=web 패키지(search/crawl/fetch). 라이브러리=context7.
- **헌법 닻**: [[architecture_substrate_superstructure_seam]](탐침=하부/정책=상부)·[[architecture_body_vs_absorbable]](forager=AI, 흡수 가능한 건 짓지마)·[[architecture_avoid_vendor_layer]](개인 누적).
- **연구**: `FILE_FORAGING_RESEARCH.md` §1.2(보편성)·§3.3(finder 계약)·§6(델타 #4 하나의 forager 여러 몸)·§7.7(기질 부재)·§12.1(교차-몸).
- **메모리**: [[project_personal_search_forager]], [[project_filesystem_comprehension_direction]].
- **검증**: `python3 scripts/build_ibl_nodes.py --check`.

---

## 9. 보류 중 (별개)
- **residual 능동 호출 넛지**(인지층이 강한 음성단언/망라 전 residual을 자동 호출): 능력(`[self:residual]`)은 있으나 AI가 *스스로 안 부름*. 능동 프롬프트가 옳은 방식인지 **사용자 재고 중** — 다른 길(예: 평가 에이전트가 음성단언 시 측정 요구) 가능성. 다른 몸 작업과 독립.
