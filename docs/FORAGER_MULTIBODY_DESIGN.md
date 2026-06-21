# 다른 몸 일반화 — 설계 결정 (2026-06-20)

*핸드오프 `FORAGER_MULTIBODY_HANDOFF.md` §6 열린 질문에 답하는 결정 노트. 첫 몸=코드베이스를
thin 구현하기 전에 "무엇을 어떻게 키잉하나"를 결정화한다. 연구 골격은 `FILE_FORAGING_RESEARCH.md`
§1.2·§3.3·§6·§7.7, 디스크 구현은 `FORAGER_MEMORY_GUIDE.md`·`FORAGER_MEMORY_SCHEMA.md`.*

> **한 줄**: forager 정책·기억 스키마·안전판은 그대로 둔다. 바꾸는 건 단 하나 — `body`가
> "하드웨어 자아"가 아니라 **"포식 공간"** 을 키잉하게. 첫 공간으로 `code:<repo>`를 디스크(`mac`)
> 옆에 *추가*한다. 데이터 마이그레이션 0, 스키마 변경 0(컬럼은 이미 TEXT), 의미만 분리.

> **★§9 갱신(2026-06-20, collapse)**: 코드·웹을 키워드-cue + per-medium 분기로 구현했더니
> *매체마다 코드가 늘어나는 냄새*가 났다(`_CODE_CUES`/`_WEB_CUES`/`if code/elif web`). 매체는
> 가짜 축이다. 진짜 축은 둘뿐 — **① body=문자열(AI가 명명) ② 열거 가능한가(이진)**. 분기를 이
> 둘로 접었다(§9). 이제 책·외장볼륨·미래 매체 = **새 코드 0**.

---

## 0. 결정 요약 (TL;DR)

| 질문(핸드오프 §6) | 결정 | 근거 |
|---|---|---|
| 1. probe 계약 = 코드냐 문서냐 | **문서 + 얇은 매핑** (OO 추상 금지) | forager=AI. AI가 이미 grep/read/fetch를 골라 씀 — 추상층은 흡수될 죽은 무게 [[architecture_body_vs_absorbable]] |
| 2. 공간 식별 입도 | 디스크=`mac`(홈 1통, 볼륨 세분은 나중) / 코드=`code:<repo-basename>` | 첫걸음은 *몸 분리*가 목표. 같은 몸 안 세분은 yagni |
| 3. 공간 추론 위치 | **인지층 자동 추론**(메시지+응답 단서) + AI가 `body` 명시로 override | 디스크판이 이미 자동(`_search`/`_distill`) — 대칭 유지. IBL 직접호출은 명시 가능 |
| 4. 웹의 음성 단언 | **apparatus 안 지음**(아래 §8) | 모집단 무한·비열거 → 균일표본 정의 불가. 연구 §9 "정지는 AI". residual은 열거가능 공간(디스크·코드) 전용 |
| 5. owner_model 풍부화 루프 | 기존 증류 경로 그대로(공간 무관) | owner_model은 이미 몸 독립·교차전이 실증(§12.1) |
| 6. 하드웨어 자아 × 공간 | **두 축 분리.** 하드웨어자아(누가 포식: mac/phone)=게이트 / 공간(무엇을 포식)=body 키 | §2.1 conflate 해소. 폰 자아 미디어-한정 게이트는 `detect_body()`로 별도 유지 |

---

## 1. 핵심 재정의 — 두 "몸"의 분리 (이 설계의 척추)

현재 코드는 `body = detect_body().profile`(="mac")를 `forage_map.body`에 넣어 두 개념을 섞는다:

- **하드웨어 자아**(`detect_body()`): *누가* 포식하나 — mac vs phone. 주관적 기억(대화·해마·forage_map)이
  자아별로 사적([[project_body_proprioception_detection]]). → **게이트** 용도(폰 자아는 미디어-한정, skip).
- **포식 공간**(forage_map이 키잉할 것): *무엇을* 포식하나 — 이 디스크 / 이 코드레포 / 웹.
  → **body 키** 용도.

맥 자아 한 명이 디스크도·코드레포도 포식하면 forage_map에 body가 둘(`mac`, `code:indiebizOS`).
owner_model은 여전히 1명(모든 공간 공유, 이미 맞음).

```
                 하드웨어 자아 (게이트)        포식 공간 (body 키)
  맥 자아  ───────────  mac  ───────────┬──▶  forage_map[body="mac"]          (홈 디스크)
                                        ├──▶  forage_map[body="code:indiebizOS"]
                                        └──▶  (web — 나중)
  폰 자아  ───────────  phone  ─────────────▶  (미디어-한정, A3 후속 — skip)
                                              owner_model  (몸 독립, 전 공간 공유)
```

## 2. 공간 식별 scheme

| 공간 | body 키 | 식별 방법 (thin) |
|---|---|---|
| 홈 디스크(맥) | `mac` | 기본값 — 기존 데이터 보존(레거시 호환). "맥의 홈 파일시스템" |
| 코드레포 | `code:<repo-basename>` | 응답 속 소스파일 절대경로 → `.git` 조상 탐색 → basename. 폴백=cwd의 git 루트 |
| 웹 | `web` | URL/온라인 의도 단서. 도메인 세분(`web:<domain>`)은 yagni — 웹 지식 대부분이 owner_model(몸 독립)이라 공간-특정 map이 적음 |
| 외장 볼륨 | `disk:<uuid>` | **나중** — 볼륨 세분이 필요해질 때(yagni) |

`mac`을 `disk:mac`으로 개명하지 **않는다**: ① 기존 `body="mac"` 데이터를 고아로 만들지 않음
② 첫걸음 목표는 *몸 분리*지 디스크 세분이 아님. 볼륨 UUID 키잉은 다중 볼륨이 실제로 필요할 때.

## 3. probe 계약 = 문서 (코드 추상 금지)

forager=AI 원칙([[architecture_body_vs_absorbable]]) → **OO probe 클래스를 짓지 않는다.**
AI가 이미 어떤 IBL 액션이 probe/peek인지 안다. "계약"은 *어떤 액션이 어느 몸의 probe/peek/cost인지*의
얇은 표 — 코드가 아니라 문서로(이 절이 그 표):

| 능력 | 디스크 | 코드 | 웹 |
|---|---|---|---|
| **probe**(싼 메타·열거) | `[self:fs_query]`/`find`(이름·메타) | `[self:glob]`·`[self:grep]`(이름/심볼) | `[web:search]` 결과 목록 |
| **peek**(비싼 내용) | `[self:read]` | `[self:read]`·`[self:grep]` 본문 | `[web:crawl]`/`fetch` 본문 |
| **cost/기질** | Spotlight/EXIF 색인 유무 | 레포 크기·언어·.git 유무 | rate limit·페이월·중의성 |

세 몸 모두 probe·peek가 *이미 어휘에 있음*(web 패키지 search/crawl) → 새 probe 구축 0.

## 4. residual(음성 단언)의 몸별 일반화 — 열거 가능 공간만

`[self:residual]{sample}`은 모집단−seen 균일표본→Wilson 추정이다. **전제=모집단이 열거 가능**.

- **디스크**: `file_index.candidate_paths`(mdfind/walk). ✅
- **코드**: `file_index.code_candidate_paths`(repo walk+소스확장자). ✅ 디스크판과 *구조 동일*, 열거만 walk로.
- **웹**: ❌ — 모집단이 무한·비열거 → **균일표본이 정의 불가**. residual을 웹에 *억지로 이식하지 않는다*(§8).

## 4b. (요지) 웹 음성단언을 안 짓는 이유는 §8.

## 5. 코드를 어디서 만지나 (구현 갭 — thin)

1. **공간 추론 헬퍼** `_forage_space(user_message, ai_response="")` — 코드 단서/소스 확장자 감지 →
   `code:<repo>` vs `mac`. (`agent_cognitive.py`)
2. **하드웨어 게이트 분리** — `_search`/`_distill`에서 `detect_body()`(phone skip)와 공간 body를 **분리**.
3. **의도 게이트 확장** — `_FORAGE_CUES`에 코드 단서. `_distill`의 2차 게이트(`disk_cue`)에 코드 analog.
4. **증류 프롬프트 공간-인식** — code body면 폴더정체→모듈정체, 명명관습→코드관습 예시로 분기.
5. **residual 코드 candidate**(light) — `_residual_op`이 code 공간이면 repo root+소스확장자 walk 열거.
6. **self.yaml 어휘** — forage/residual target_description에 `code:` body 예시 명시.

over-design 금지: probe OO·몸별 엔진 짓지 않음. AI가 루프, 우리는 *키잉·추론·candidate만 얇게.*

## 6. 검증 시나리오 (§5 handoff)

1. **콜드 포식**: "이 코드베이스에서 X 하는 곳 찾아줘" → forage(grep/read) → 증류 → `code:indiebizOS` body에
   지도 누적("IBL 액션은 self.yaml src에 정의, build로 생성" 류).
2. **웜 직행**: *별도 프로세스*(교차세션)에서 같은 주제 회상 → `<forage_memory>`에 code 지도 주입.
3. **residual**: "X 처리하는 데 더 없나" → 코드 모집단 균일표본 → 망라 측정.
4. build --check 통과(액션 수 불변 — 어휘 추가 아닌 의미 일반화).

## 5b. 웹 몸 — 어디를 만지나 (thin, 2026-06-20)

코드 몸과 *대칭*. 웹의 진짜 가치는 망라가 아니라 **owner_model 교차-몸 전이**(연구 §12.1, 이미 실증).

1. **공간 추론** — `_forage_space`에 web 분기. URL(`https?://`)·온라인 의도 단서(웹/구글/스칼라/arxiv/위키). 우선순위 **code → web → disk**(코드 확장자가 가장 특정적). `web` 단일 공간(도메인 세분 yagni).
2. **의도 게이트** — `_FORAGE_CUES`에 웹 단서. `_distill`의 2차 게이트는 웹이면 *응답 속 URL/출처*로.
3. **증류 프롬프트 웹-인식** — map은 적게(예: "이 사람 논문=NYU Scholars", "arxiv=신경과학 preprint 1차"), **owner_model을 무겁게**(정체·분야·소속·내용신호·로마자 — §12.1 복리 루프: 웹 결과가 디스크 모델을 역확증·풍부화).
4. **residual 없음** — §8.

over-design 금지: 웹 saturation 측정기·berrypicking 컨트롤러 짓지 않음(§8).

## 6. 검증 시나리오 (§5 handoff)

1. **콜드 포식**: "이 코드베이스에서 X 하는 곳 찾아줘" → forage(grep/read) → 증류 → `code:indiebizOS` body에
   지도 누적("IBL 액션은 self.yaml src에 정의, build로 생성" 류).
2. **웜 직행**: *별도 프로세스*(교차세션)에서 같은 주제 회상 → `<forage_memory>`에 code 지도 주입.
3. **residual**: "X 처리하는 데 더 없나" → 코드 모집단 균일표본 → 망라 측정.
4. **웹**: 웹 포식 → 증류가 `web` map + **owner_model 강화**(교차전이) → 별도 프로세스 회상 시 owner가 전 공간 공유 확인. residual은 web 미지원.
5. build --check 통과(액션 수 불변 — 어휘 추가 아닌 의미 일반화).

## 7. 남는 것 (이 설계 후)

- 책 몸·외장 볼륨 — **§9 collapse 후 새 코드 0**(AI가 `book:<제목>`/`disk:<라벨>`로 명명, 열거는 path-walk 재사용). 실사용 시 검증만 하면 됨.
- residual 능동 호출 넛지(핸드오프 §9, 사용자 재고 중 — 독립).
- 폰 자아의 자기 공간 포식(`phone-fs:` body, A3) — 자아별 사적 기억 원칙과 정합 확인 필요.

## 8. ★결정 — 웹 음성단언 apparatus를 짓지 않는다

핸드오프 §6.4가 "웹에선 '충분히 찾았나'를 어떻게?"를 열린 질문으로 남겼다. **답: 측정기를 짓지 않는다.**

- **왜 디스크판이 안 맞나**: residual은 *모집단−seen 균일표본*이 핵심. 웹 모집단은 무한·비열거(검색엔진 인덱스는 우리 것이 아니고, 랭킹돼 들어옴) → "미관측 더미에서 균일 무작위"가 **정의 불가**. 디스크/코드의 Wilson 추정을 웹에 이식하면 *가짜 정밀도*다.
- **연구 결론과 정합**(§9): "정지는 AI 판단, elusion만 얇게." 웹에 얇은 elusion이 *없다*면, 남는 건 AI 판단뿐 — 그게 옳다([[architecture_body_vs_absorbable]] apparatus 짓지마).
- **웹의 "충분함"은 berrypicking 포화**: 새 출처가 새 주장(claim)을 안 더하면 포화(Bates). 이건 *의미 판단*(LLM)이라 도구화하면 apparatus 창궐. AI가 자기 추론에서 출처 다양성을 직접 본다.
- **그래서 `[self:residual]`은 열거가능 공간(디스크·코드) 전용**으로 둔다. 웹 forage는 owner_model 복리 루프로 가치를 내고, 망라 단언은 AI 몫.
- **재개 조건**: 만약 *제한된* 웹 모집단(예: 한 사이트 sitemap·한 저자의 논문 목록 = 열거 가능)을 포식하는 패턴이 잦아지면, 그땐 그 *유한 모집단*에 residual을 쓸 수 있다(웹 일반이 아니라 "열거된 하위집합"). 그건 그때.

## 9. ★결정 — 매체별 분기를 *불변 2축*으로 접는다 (2026-06-20 collapse)

**문제**(사용자 지적): 코드·웹을 키워드-cue 리스트(`_CODE_CUES`/`_WEB_CUES`) + per-medium 분기(`if is_code / elif is_web / else`)로 구현하니, 책·외장볼륨·메일·… 매체마다 *코드가 늘어나는* 목록이 됐다. [[architecture_body_vs_absorbable]](흡수 가능한 건 짓지마)에 정면으로 걸린다.

**진단 — 무엇이 늘어나고 무엇이 안 늘어나나**:

| 요소 | 매체마다 늘어나나 | 본질 |
|---|---|---|
| body 키·2층 스키마·forager 루프·owner_model | ✗ | 이미 몸 독립(불변) |
| 공간 추론 키워드 리스트 | ✅ ← 냄새 | 제거 |
| 증류 프롬프트 per-medium 분기 | ✅ ← 냄새 | 제거 |
| residual 모집단 열거기 | 부분 | 이진으로 |

**"매체"는 가짜 축이다. 진짜 축은 둘뿐**:

1. **body = 문자열, AI가 명명**. AI는 자기가 코드/웹/디스크 중 무엇을 포식하는지 *이미 안다*(자기가 forager니까). 키워드로 재유추하는 건 중복 apparatus. → 증류기 LLM 이 출력 JSON 에 `space`를 **명명**한다. cue 리스트 삭제. 매체가 늘어도 코드 0(`book:<제목>`·`disk:<라벨>`도 그냥 라벨).
2. **열거 가능한가 = 이진 속성**(per-medium 아님). 열거 가능(디스크·코드·책의 장·외장볼륨·sitemap) → residual이 *하나의 "루트 walk" 열거기* 재사용. 외장볼륨=`candidate_paths(path=/Volumes/X)` *이미 동작*. 열거 불가(열린 웹) → residual 옵트아웃, AI 포화 판단(§8).

**접은 결과**(코드):
- `_CODE_CUES`/`_WEB_CUES`/`_CODE_EXT_RE`/`_URL_RE`/`_forage_space` **삭제**. 대신 `_FORAGE_CUES`(단일 일반 의도 게이트)+`_FORAGE_EVIDENCE_RE`(단일 일반 포식-증거 게이트).
- 회상 `_search_forage_memory`: **전 body 회상**(`recall(body=None)`)+query 자기-스코핑. 매체 추론 없음. owner_model은 본디 몸 독립.
- 증류 `_distill_forage_memory`: **공간-중립 단일 프롬프트**. LLM이 `space` 명명 → `_normalize_space`가 body 키로(케이스 보존, bare "code"만 .git basename 보강).
- residual `_residual_op`: 이진(`space:code`→code_candidate_paths / else→candidate_paths `path=`). 외장볼륨·책=else 재사용, 새 코드 0.

**검증**: 같은 단일 경로로 code/web/disk 증류가 각각 `code:indiebizOS`/`web`/`mac`을 AI-명명·누적, 전-body 회상이 code 질의엔 code 항목·person 질의엔 owner 교차전이를 자기-스코핑, residual 이진 확인(volume=path 재사용). build --check 140 유지.

**원칙**: 매체 목록이 멈췄다. "책 추가"=코드 변경 아니라 *AI가 `book:<제목>`이라 부르고 장을 walk*. forager=AI를 끝까지 지킴.

## 10. ★결정 — 포식기억 회상은 *실행기억처럼 항상-on*, owner는 상시 노출=냄새 (2026-06-20, 최종)

**이력**: ①처음엔 0단계 *키워드 의도 게이트*로 항상-on → ②"키워드 거칠다"는 지적에 **THINK 의식-게이트**로 이동 → ③**되돌림(최종)**: 항상-on 복귀 + 키워드/THINK 게이트 모두 폐지. 아래가 *왜 ③이 옳은지*.

**핵심 통찰**(사용자): 비싼 건 *서치(포식)*지 *회상*이 아니다. 회상=SQLite+키워드필터(LLM 0, 마이크로초), 비용은 프롬프트 길이뿐. 그리고 **query 필터가 *공짜로* 관련성 게이트** — 무관한 메시지엔 빈 결과(비용~0). 실행기억(해마)이 항상 켜져 있어도 무관하면 조용하듯, 포식 회상도 그렇다. tier로 게이팅할 이유가 없다.

**THINK-게이트가 틀린 이유**: "분업"(빠른 경로엔 덜 유용)은 *덜 유용*이지 *해롭다*가 아니다 — 싸고 자기-억제되는데 *숨길* 이유가 없다. 게다가 THINK-게이트는 owner_model(냄새)을 "포식하기로 한 뒤에야" 보여주는 **순환**을 만들어, *능동 포식의 방아쇠를 빼앗았다*. 항상-on이면 냄새가 늘 떠 있어 능동 포식 갭까지 같이 풀린다.

**최종 설계 — 진짜 게이트는 tier가 아니라 *관련성*(2층)**:

| 층 | 게이트 | 역할 |
|---|---|---|
| **map**(지도, 큼·위치특정) | query 필터 (관련 위치만) | 일단 포식할 때 길 안내 — 관련 없으면 0 |
| **owner**(주인모델, 작음) | *상시 노출*(query 면제) | 냄새(scent) — "이 주제로 내 자료 있을 수 있다"를 늘 상기 → 능동 포식 촉발 |

**읽기/쓰기**: 회상(읽기)=항상-on(query 자기-게이트). 증류(쓰기)=전 티어 post-response(매 포식서 학습). 둘 다 게이트가 *관련성*이지 tier가 아니다.

**구현**(인지층, 재시작 후 라이브):
- 0단계 `_build_execution_memory`에 forage 회상 **항상-on 복귀**(키워드 게이트 없이). `_search_forage_memory(user_message)`가 `recall_xml(body=None, query=user_message, filter_owner=False)` 호출.
- `forage_memory.recall`/`recall_xml`에 `filter_owner` 파라미터: False면 owner를 query 무관 전부 반환(=냄새). map-only/owner-only에 따라 note 길이 분기(owner-only=짧은 냄새 note로 비용 절약).
- THINK 플러밍 **제거**: `_attach_forage_if_requested`·`_fold_forage`·빌더 fold·consciousness_prompt `recall_forage`/`forage_query`/§5b 전부 삭제(단순화).

**검증**: 포식 질의→map(mypaper)+owner / 주제 안 밝힌 질의("이 데이터 분석해줘")→map 비고 owner(냄새)만 짧은 note(능동 포식 단서) / 빈 owner면 "" / 전 모듈 임포트·build --check 통과.
