# 세션 핸드오프 — 2026-07-01~02

> 이 문서만 읽으면 대화 맥락 없이 이어갈 수 있게 쓴다.
> 상태: 아래 12개 커밋(`31501c7`~`a0214d2`) **전부 origin/main 푸시 완료**. 워킹트리 clean.
> 백엔드는 dev 모드 상시(HMR). 핸들러 편집=`/packages/reload`, 부팅로드(.env·레지스트리)=재시작.

---

## 0. 이번 세션 한 일 (커밋 순)

| 커밋 | 내용 |
|---|---|
| `31501c7` | fix(cctv): 미커밋 필수 모듈 `cctv_common.py`·`enrich_kakao_coords.py` 추적(Phase3 이관 누락→clone시 붕괴) |
| `56f8e47` | **Phase 5**(능력 자기완결화 종결): 표준 에디션+로케일 설치 선택 `scripts/apply_edition.py` |
| `260856b` | 죽은 unified_search 도구 제거 |
| `b881ca8` | **web 이질 패키지 분할** → web(보편)/web-kr(네이버 한국). web가 keyless됨 |
| `a981696` | 도구 관리 UI **4카테고리**(표준/한국전용/키필요/개인어휘) |
| `e444270` | **engines:newspaper 어휘 은퇴** → NewspaperInstrument가 search_gnews 조합 |
| `475e15b` | **search_news → search_gnews** 리네임(land-grab 해소+3층 이름 정렬+코퍼스 마이그레이션) |
| `260e14c`~`a0214d2` | **op-통합 레거시 죽은 코드 정리**(12패키지, 5커밋) |

---

## 1. 능력 자기완결화 — **종결** (Phase 0~5 전부 완료)
- 상세: `docs/CAPABILITY_SELF_CONTAINMENT_HANDOFF.md`, 기억 `project_capability_self_containment`.
- Phase 5 = `scripts/apply_edition.py`(에디션 standard/full · 로케일 universal/kr/all로 도구팩 installed↔not_installed 분할, 파킹 마커 `.edition_parked`로 가역). bootstrap.md step 3 연결.
- **후속(선택)**: 원격/폰 표면의 에디션 선택 UX. (핵심 리팩터는 끝남.)

## 2. web 이질 패키지 분할 (완료)
- `search_naver`(+tool_naver_search.py)를 신규 **web-kr**로 분리. web=universal·keyless, web-kr=kr·NAVER키.
- 기억 `project_newspaper_app`·`architecture_ibl_naming_law`.
- **남은 이질 패키지**(감사됨, 미분할): culture(classic=구텐베르크 keyless vs kr), investment(crypto vs DART), location-services(weather/map vs kakao). **사용자 판단**=location-services는 weather 하나뿐이라 분할 보류. 나머지는 필요시.

## 3. 도구 관리 4카테고리 UI (완료)
- `frontend/src/components/launcher-components/dialogs/ToolboxDialog.tsx` + backend `/packages`에 locale/weight/needs_key/dormant 부착(`api_packages.py` `_enrich_with_meta`).
- 상위 4섹션(열림/닫힘, 기본 닫힘): ⭐표준/🇰🇷한국전용/🔑키필요/👤개인어휘. 각 섹션에 설치+미설치 함께.
- **멤버십은 임시**(`categoryOf()`+`STANDARD_OVERRIDE`/`PERSONAL_PACKAGES` 두 셋에 격리) — 사용자가 계속 재조정 중. 이 두 함수만 고치면 됨.
  - 현재: 표준예외=cloudflare·context7·web / 개인어휘=android·blog·house-designer·lecture_workspace·media_producer·memory·publishing·remotion-video·web-builder.

## 4. engines:newspaper 은퇴 + 새 신문 앱 (완료)
- **원칙**(사용자): 디자인은 어휘가 아니라 앱에. 앱=어휘 조합+약간의 코딩. 반복=어휘 승격, 앱별=앱에서 한 번.
- `NewspaperInstrument.tsx` 재작성: 키워드마다 `[sense:search_gnews]` 팬아웃→제호+섹션+2단 카드 인앱 렌더. ActionDesktop에서 OVERRIDE→STATIC 계기.
- web에서 generate_newspaper 클러스터+GUARDIAN 제거→**web keyless**. 코퍼스 정리(ibl_usage.db 23·distilled 3).
- 기억 `project_newspaper_app`.
- **남은 것**: (a) `table:document{theme:newspaper}` 테마는 일반 emitter 옵션이라 보존(원하면 후속 제거). (b) 원격/폰 신문은 데스크탑 전용(bespoke 리치 계기라 원격 미적용). (c) 신문에 가디언 섹션 원하면 앱이 `[sense:search_guardian]`(study, GUARDIAN키) 추가 호출.

## 5. search_news → search_gnews 리네임 (완료)
- **근거**: "news"는 넓은 범주(구글·가디언·네이버·주식뉴스…)인데 search_news가 일반 이름을 구글뉴스 하나에 씀=land-grab. 3층(액션/tool/함수) 이름도 제각각이었음.
- 결과: 액션=tool=함수 모두 `search_gnews`. "news"는 주인없는 범주로 해방. search_guardian과 대칭.
- 코퍼스 마이그레이션(ibl_usage.db 38행 ibl_code+nodes, FTS 트리거 동기, intent 임베딩 불변→재임베딩 불요) + distilled/fixtures + 문서/가이드/생성기.
- **함정 교훈**: repo 전역 sweep이 gitignore된 빌드산출물(frontend/release)·로그·유저데이터도 디스크에서 건드림. `git add -u`가 추적파일만 스테이징해 커밋은 깨끗했으나, sweep 시 주의.
- **잠재 후속**: `search_gnews` 함수의 impl은 여전히 `search_google_news`였다가 리네임됨. 다른 액션들도 3층 이름 드리프트 있을 수 있음(tool명·함수명이 액션명과 어긋난 경우) — 원하면 전체 드리프트 감사.

## 6. op-통합 레거시 죽은 코드 정리 (12패키지 완료) + ★fall-through 함정
- 상세: 기억 `project_dead_code_op_dispatch_fallthrough`.
- **정리됨**(죽은 분기 ~34+tool.json ~43): memory·health-record·kosis·startup·remotion-video·real-estate·business·legal·radio·web-collector·media_producer·photo-manager. impl 함수 유지.
- **★결정적 함정 — op-분기 fall-through**: op-분기 패키지 두 변종.
  1. **직접 return**(`if op: return func()`) → 레거시 `tool_name==` 분기 진짜 죽음(제거함).
  2. **재할당+fall-through**(`tool_name = mapping[op]` 후 return 없이 떨어져 아래 레거시 분기가 실제 구현) → 레거시 분기 **라이브**(제거하면 깨짐).
- **미완/false positive 3개**(변종2라 손대지 않음): **youtube**(`tool_name=mapping[op]`)·**web-builder**(`tool_name="create_page"` 등)·**visualization**(`tool_name=type_map[chart_type]`). 이들의 tool.json 선언은 기술적으론 죽었으나 분기가 라이브라 전체 보존.
  - **진짜 정리하려면**: op-분기를 "직접 return" 형태로 리팩터(레거시 분기 인라인화)해야 함 — **별건, 다음 세션 후보**.
- **교훈**: 정적 감사(내 스크립트 + 서브에이전트 4개 전부)가 fall-through를 놓침. dict 조회 재할당은 grep으로도 안 잡힘. **반드시 라이브 액션 스모크로 확인**(chart 스모크가 None 뱉어 잡음).
- **미정리 잔여(변종1인데 안 건드린 것)**:
  - `real-estate`: `realty_price` 분기(123) — 에이전트 미플래그라 보존. realty_op가 op=query에서 `tool_name="realty_price"`로 재할당→realty_price가 자체 `_dispatch` dict로 함수직호출·return(변종1). **realty_price 자체가 죽은지**는 재확인 필요(어떤 액션도 tool=realty_price 아님 → 아마 죽었으나 realty_op가 fall-through로 씀=라이브). **손대지 말 것**(realty_op의 fall-through 타겟).
  - `media_producer`: `generate_ai_image` **함수**(1415)는 분기 제거로 고아됨(무해). 원하면 제거.

## 7. Tier 2/3 (비-IBL 병렬 경로) — 미착수, 상위 결정 필요
감사 중 드러난 **두 개의 비-IBL 도구 실행 경로**(IBL 죽은 코드를 살려두는 원인):
- **backend REST**(`api_*.py`)가 패키지 `handler.execute("옛tool명")` 직접 호출 — 예 `api_lecture_workspace.py`가 slide_create 등. 그 분기는 REST-라이브.
- **`data/packages/installed/extensions/ai-agent/tool_executor.py`의 `_execute_legacy_tool`** — pre-IBL 도구경로(blog 등). `architecture_ibl_core_execute_only`("에이전트=execute_ibl 단일도구")상 **이 경로 자체가 은퇴 후보 레거시**.
- **다음 판단**: "REST/레거시 tool_executor 경로를 IBL execute로 수렴시킬 것인가"라는 상위 결정. 수렴하면 lecture_workspace·blog 등의 분기도 죽어 추가 정리 가능.

---

## 8. 다음 세션 착수 후보 (우선순위)
1. ~~**youtube/web-builder/visualization 진짜 정리**~~ **✅완료**(2026-07-02 후속, 커밋 `4798901`·`4eadb4d`·`0e547cb`, push): 세 패키지 모두 op(또는 chart_type)→핸들러 함수 직접-return으로 리팩터(레거시 `if tool_name==` 체인을 `_op_*`/`_render_*`/`_h_*` 모듈함수로 추출), 변종2→변종1 전환. 죽은 tool.json 29개 제거(youtube 9→3·visualization 8→1·web-builder 19→3). `_OP_DISPATCHERS` 이름 유지(값 문자열→함수, `--check`는 키만 읽어 무영향). web-builder는 미지 op→기본 폴백 관용 보존. 각 라이브 스모크 통과.
2. **Tier 2/3 상위 결정**(§7): tool_executor `_execute_legacy_tool`·REST 직접호출 경로를 IBL로 수렴할지.
3. **3층 이름 드리프트 전체 감사**(§5 후속): 액션명 vs tool명 vs 함수명 어긋난 것 전수.
4. (선택) 원격/폰 신문 앱, table:document newspaper 테마 제거, 도구관리 카테고리 멤버십 최종 확정.

## 9. 이번 세션 핵심 교훈 (반복 방지)
- **라이브 스모크 필수**: --check 초록·ast OK로는 fall-through·회귀 못 잡음. 액션 하나 실제 실행해볼 것.
- **감사 에이전트 목록 맹신 금지**: radio에서 라이브 tool(radio_status)을 죽음으로 오분류. `tool.json − 액션tool` 직접 계산으로 교차검증.
- **fall-through 2변종**: op-분기가 return하나 tool_name 재할당하나 확인(`grep 'tool_name = '` + dict조회 `mapping[op]`도).
- **어휘 리네임=코퍼스 마이그레이션**: ibl_code/nodes 텍스트 치환(intent 임베딩은 불변→재임베딩 대개 불요), FTS는 트리거 자동, vec는 sqlite_vec 로드 후 rowid 삭제.
- **1패키지=1커밋·매 커밋 --check**: bisect 가능. pre-commit이 IBL 정합성 자동 검사.
