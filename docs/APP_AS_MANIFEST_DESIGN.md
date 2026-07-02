# 앱 = 매니페스트: 앱을 어휘에서 떼어내기 (탈어휘화)

*작성: 2026-07-02 · 시발점: report-viewer 패키지 어휘 비판*

## 0. 한 줄 요약

앱은 **일반 어휘 위의 얇은 매니페스트**여야 한다. 앱마다 전용 노드 액션을
새로 찍으면 IBL이 막으려던 *도구 폭증*을 *어휘 폭증*으로 되풀이한다.
`report-viewer`가 그 첫 위반 사례다 — 이미 존재하는 일반 부품
(`self:file_find`·`self:read`·`others:delegate`·`self:trigger`)을 무시하고
전용 `self:report` 액션 + 200줄 핸들러 + 직접 `SystemAIRunner.send_message`
파이썬 호출을 지었다. 이 문서는 (1) 앱 매니페스트를 어휘에서 분리하는 인프라를
도입하고, (2) report-viewer를 그 인프라의 **레퍼런스 소비자**로 전환한다.
순증 어휘 = **0개** (오히려 `self:report` 1개 제거).

## 1. 문제: 앱이 어휘로 위장하면 조합성이 없다

`[self:report]{op}`는 5개 op을 가진다:

| op | 실제로 하는 일 | 일반 부품이면 |
|----|----------------|----------------|
| `list` | `outputs/*_reports/`의 `.md` 나열 | `[self:file_find]{pattern, path}` |
| `read`/`latest` | 보고서 본문 읽기 | `[self:read]{path}` |
| `types` | 하드코딩 타입 enum | 매니페스트 static select |
| `new` | 고정 프롬프트를 시스템 AI에 큐잉 | `[others:delegate]{message, mode:async}` |

두 가지 병이 겹쳐 있다:

- **보기 계열**은 "특정 폴더의 마크다운 뷰어"를 핸들러로 다시 짠 것이다.
  보고서 타입이 `handler.py`의 닫힌 enum(`ai_trend`/`ai_startup`)이라
  조합되는 데가 없다.
- **쓰기(`new`)**는 능력이 아니라 **통조림 트리거**다. 등록된 2개 타입의
  고정 프롬프트("AI 동향 보고서 써줘")만 시스템 AI에 되던진다. 임의 주제
  보고서에 작동하지 않는다.

### 자율주행 검증 (핵심 결함)

자율주행에서 "부동산 시장 보고서 써줘"라고 하면 `[self:report]`는 **작동하지
않는다**: (1) 그 주제 `type`이 없고, (2) `new`는 사용자 주제를 무시하고
"AI 동향 보고서 써줘"만 재주입하며, (3) 그래서 에이전트는 옳게도 `self:report`를
건너뛰고 일반 어휘를 조합한다(`sense`→`table`→`table:document`→`self:write`).
즉 진짜 "보고서 쓰기" 능력은 이미 일반 조합 + 가이드에 살고, `self:report`는
거기 전혀 참여하지 않는 **앱 전용 죽은 어휘**다.

## 2. 발견: 필요한 일반 부품은 이미 다 있다

report-viewer가 소비했어야 할 부품:

| 앱이 필요로 하는 것 | 이미 있는 일반 부품 | 통화 |
|---|---|---|
| 저장된 보고서 나열 | `[self:file_find]{pattern:"*.md", path:"outputs/ai_trend_reports"}` | items |
| 보고서 본문 | `[self:read]{path}` | scalar(text/pdf/docx) |
| 최신순 정렬 | `[table:sort]` (파이프 `\| sort`) | items |
| "새로 하나 써" | `[others:delegate]{agent_id, message, mode:"async"}` | effect |
| 정기 실행 | `[self:trigger]{op:"create", pipeline, cron}` | effect |
| 무엇을 어떻게 쓰나(레시피) | 가이드 `data/guides/ai_trend_report.md` | — |

`[others:delegate]`가 결정적이다. 이것이 **자연어 의도를 에이전트에게 비동기로
넘겨 알아서 수행**하는 일반 verb다(`mode:async` 기본). report의 `new`는 이
verb를 무시하고 `SystemAIRunner.send_message`를 직접 때린 우회였다 —
실제로 delegate 체계 자체가 내부에서 `channel=='system_ai'` +
`_send_to_system_ai`(→`SystemAIRunner`)로 **같은 기질**을 쓴다.

> **결론**: report-viewer는 새 어휘가 필요했던 적이 없다. 전부 일반 부품의
> 조합 + 가이드로 표현된다. 순증 어휘 0.

## 2.5 실측 검증 (2026-07-02, 라이브 백엔드)

`/ibl/execute`로 각 부품을 실제 실행해 확인한 결과 — §2의 일부가 수정됐다:

- ✅ **목록(view)**: `[self:file_find]{pattern:"*.md", path:"<abs>"}` → 7건 items
  반환(경로는 `url` 필드, 제목 `title`, 날짜 `meta`). item_click →
  `[self:read]{path:"{url}", scope:"workspace"}` 본문 읽기 정상.
- ⚠️ **최신(view)**: `file_find | sort: title desc | take: 1 >> [self:read]`는
  **read가 이전 단계 파일 경로를 자동 바인딩 못 함** — `items[0].url`이 중첩돼
  `_extract_path_from_prev`(top-level file/path/url만 봄)가 못 찾고 project_path로
  폴백 → "Is a directory" 오류. **이건 report 전용이 아니라 "방금 찾은 파일을
  읽기"라는 일반 통화-대수 갭.**
- ❌ **작성(generate)**: `[others:delegate]{agent_id:"system_ai"|"시스템 AI"}` →
  "에이전트를 찾을 수 없습니다". delegate는 **프로젝트 에이전트만** 타겟팅하고
  **시스템 AI는 위임 대상이 아니다**(요청자/부모일 뿐, `_send_to_system_ai`는
  결과 보고용). 즉 "자율주행에 의도를 fire-and-forget으로 던지는" 일반 verb는
  **없다** — report의 `new`가 파이썬 `SystemAIRunner.send_message`를 직접 때린
  근본 이유.
- ⚠️ **경로 이식성**: `file_find`의 상대 `path`는 프로젝트 디렉토리
  (`projects/앱모드/`) 기준으로 해소된다. 보고서는 레포-루트 `outputs/`에 살아
  절대경로가 필요한데, 하드코딩은 폰/타 머신 비호환. → 매니페스트 전용
  **`%BASE%` 토큰**을 `_derive_instruments`가 서버측에서 `get_base_path()`로 치환
  (클라이언트는 실경로만 봄, `$key`·`{field}` 치환과 무충돌).

### 결론: 필요한 일반 부품 강화 2가지 (둘 다 report-비종속·재사용)

1. **`[others:delegate]`가 시스템 AI를 타겟으로 수용** → 앱의 "생성" 버튼이
   자율주행에 의도를 넘길 수 있게. `_send_to_system_ai`(보고) 있던 배관의
   *발신* 방향 개통. **새 어휘 0**(기존 delegate 확장). 모든 미래 앱의
   "이거 해줘" 버튼이 재사용.
2. **파일 경로를 이전 단계 `items`에서 바인딩** (`_extract_path_from_prev`가
   `items[0]`의 url/path/file도 파고, `self:read`가 path 없을 때 `_prev_result`
   참조) → "찾은 파일 읽기" 조합 일반 개통([architecture_currency_algebra]
   통화→통화 깊이 심화). 모든 파일 앱이 재사용.

→ 순증 어휘 여전히 **0** (delegate·read는 *확장*, self:report는 *삭제*).

## 3. 진짜 결핍은 어휘가 아니라 인프라

그럼 왜 report는 전용 액션을 찍었나? `app:` 블록(앱 매니페스트)이 **노드 액션에
결합**돼 있기 때문이다. `_derive_instruments`(api_launcher_web.py:77)는
`ibl_nodes.yaml`의 각 **액션**에서 `app:` 블록만 스캔한다. 그래서 "어휘 없이
앱을 만들 곳"이 없다 — 앱을 두려면 액션 하나를 새로 찍어 거기 `app:`를 매달아야
한다. **이 결합이 어휘 폭증을 강제하는 구조적 원인이다.**

중요: `app:` 블록 안 각 모드의 `action:` 필드는 이미 **아무 IBL 코드나** 호출할
수 있다(호스트 액션과 무관). 결합은 순전히 *발견(discovery)*을 위한 것이다.
따라서 발견 경로만 하나 더 열면 결합을 끊을 수 있다.

### 헌법 정합성

이 분리는 [architecture_substrate_superstructure_seam] "하부구조(어휘)/
상부구조(앱)의 깨끗한 이음매"와 [architecture_ibl_as_vocabulary]
"앱마다 도구 찍지 말고 어휘로"의 직접 실현이다. 앱은 상부구조,
어휘(IBL 노드)는 하부구조 — 둘의 파일 위치까지 분리한다.

## 4. 설계: standalone 앱 매니페스트

### 4.1 새 소스 위치

```
data/instruments/<id>.yaml        # 앱 하나 = 파일 하나 (어휘 아님)
```

한 파일이 하나의 `app:` 매니페스트를 담는다(현행 `app:` 블록과 **동일 스키마**):

```yaml
# data/instruments/report.yaml
instrument: report
icon: 📑
name: 정기보고
order: 16
modes:
  - name: 최신
    auto_run: true
    inputs:
      - {key: type, type: select, placeholder: 보고서 종류,
         options: [{value: ai_trend,   label: AI 동향 보고서, folder: outputs/ai_trend_reports},
                   {value: ai_startup, label: AI 창업·응모 정보 보고서, folder: outputs/ai_startup_reports}]}
    # 최신 = 폴더 나열 → 최신순 → 첫 파일 읽기 (일반 부품 파이프라인)
    action: '[self:file_find]{pattern: "*.md", path: "$folder"} | sort by:name desc | take 1'
    on_empty: 아직 작성된 보고서가 없습니다 — "작성" 탭에서 만들어 보세요.
    view:
      - {type: thread, from: items, text: "{text}"}
  - name: 목록
    auto_run: true
    inputs: [ ... 위와 동일 select ... ]
    action: '[self:file_find]{pattern: "*.md", path: "$folder"} | sort by:name desc'
    view:
      - type: card_list
        from: items
        card: {title: "{name}", lines: ["{name}"]}
        item_click:
          action: '[self:read]{path: "{path}"}'
          view: [{type: thread, from: items, text: "{text}"}]
  - name: 작성
    buttons:
      - label: ✍ AI 동향 보고서 작성
        action: '[others:delegate]{agent_id: "system_ai", message: "AI 동향 보고서 써줘", mode: "async"}'
      - label: ✍ AI 창업·응모 보고서 작성
        action: '[others:delegate]{agent_id: "system_ai", message: "AI 창업·응모 정보 보고서 써줘", mode: "async"}'
```

정기(daily) 실행은 매니페스트 밖 일반 트리거로:
```
[self:trigger]{op:"create", name:"AI 동향 보고서 정기",
               pipeline:'[others:delegate]{agent_id:"system_ai", message:"AI 동향 보고서 써줘", mode:"async"}',
               cron:"0 9 * * *"}
```

### 4.2 발견 경로 확장

`_derive_instruments`가 **두 소스를 병합**하도록 확장:
1. (기존) 노드 액션의 `app:` 블록 — 데이터가 진짜 그 액션인 앱들(사진·투자
   등 풍부판)은 그대로 둔다.
2. (신규) `data/instruments/*.yaml` — 어휘 없는 순수 앱.

같은 `instrument` id면 병합(현행 로직 재사용). 캐시 mtime 감시에 디렉토리 포함.

### 4.3 빌드 검증 확장

`scripts/build_ibl_nodes.py`의 `validate_app_blocks`가 standalone 매니페스트도
검증: 모드의 `action:`이 파싱 가능한 IBL인지, 참조 액션이 실존하는지,
`options_action` 등 로컬 키 규약 준수. **이로써 앱→어휘 참조가 깨지면 build
--check가 잡는다**(좀비 앱 방지, [architecture_harness_sturdiness]).

## 5. report-viewer 은퇴

- `data/packages/installed/tools/report-viewer/` 의 `self:report` 액션 정의
  (`ibl_actions.yaml`)·`handler.py`·`tool.json` 제거.
- `app:` 블록은 `data/instruments/report.yaml`로 이관(§4.1).
- REPORT_TYPES의 folder/pattern은 매니페스트 select의 `folder` 파라미터로 이관.
- 작성 프롬프트는 delegate `message` 리터럴로 이관.
- 가이드(`ai_trend_report.md`·`ai_startup_report.md`)는 **그대로** — 레시피는
  이미 올바른 집(가이드)에 산다.

### 남은 작은 갭 (전부 일반적으로 해소)

| 갭 | 해소 |
|----|------|
| 최신순 정렬 | `[table:sort] by:name desc` (파일명에 날짜) |
| "최신" 자동 본문 | `file_find \| sort \| take 1` — items 1건을 thread로 |
| date-title("— 2026-06-17") | 코스메틱. 우선 `{name}` 표시, 필요 시 view층 파일명 예쁘게(일반 기능) |
| delegate 타겟 | `agent_id:"system_ai"`(자기 위임=시스템 AI 큐, §2에서 확인). 미지원 판명 시 대안=보고서 소유 프로젝트 에이전트 |
| `.md`-only 보안 | 앱이 자기 폴더만 조회 → 실질 무위험. file_find는 pattern 한정 |

## 6. 마이그레이션·검증 체크리스트

[feedback_vocab_change_docs] 준수:

- [ ] 해마: `self:report` 용례 14건(ibl_distilled.json) purge
      (`purge_action_records`) — 자율주행이 죽은 어휘 연상 안 하도록.
- [ ] `build_ibl_nodes.py --check` 삼각 통과(액션 카운트 −1, standalone 검증 포함).
- [ ] `/launcher/instruments` 파생에 report 3모드 여전히 등장(standalone 경유).
- [ ] 라이브 종단: 최신(file_find→sort→read 렌더)·목록(드릴 read)·작성
      (delegate async 큐잉 → 잠시 후 폴더에 파일 → 목록 반영).
- [ ] 문서 표면: CLAUDE.md 패키지표, packages.md, 인벤토리(35→34 도구).
- [ ] 재시작 필요: `_derive_instruments`·build는 백엔드 재시작 후 라이브.

## 7. 미래 앱 = 이 패턴 (왜 이게 장기적으로 옳은가)

report.yaml이 자리잡으면 다음 앱들은 **어휘 0개**로 만들어진다:

- **신문 아카이브** = `file_find outputs/newspapers/` + `read`
- **일기 뷰어** = `file_find diary/` + `read` + `delegate("오늘 일기 정리해줘")`
- **회의록/조사자료** = 같은 파일-폴더 + delegate 패턴
- 공통 "새로 하나 만들어" 버튼 = 전부 `[others:delegate]{message}` 재사용

즉 "앱을 잘 쓴다"가 "특수 어휘를 하나 만든다"로 굳지 않는다. 앱은 폴더 경로·
의도 문자열·가이드 이름만 바꿔 끼우는 선언이 되고, 어휘 카탈로그는 성장을 멈춘다.
이것이 사용자가 제기한 우려("나중에 다른 앱 만들 때 일반화할 게 없다")의 해소다.

## 7.5 구현 완료 (2026-07-02)

전부 라이브 검증(dev 백엔드 `reload=True` + `/packages/reload`):

- **일반 강화 ①** `others:delegate {scope: "system"}` — `ibl_routing._delegate_unified`
  에 분기, `SystemAIRunner.send_message` 라우팅. others.yaml 어휘 갱신. ✅라이브.
- **일반 강화 ②** `self:read {blocks}` + 파이프 경로 자동 바인딩 —
  `_extract_path_from_prev` 가 `items[0]` 파고, read 핸들러가 path 없을 때
  `_prev_result` 참조. `file_find | take:1 >> read` 개통. ✅라이브(20블록).
- **인프라** `data/instruments/*.yaml` — `_derive_instruments` 병합 +
  `%BASE%` 서버측 치환 + `_instruments_mtime` 캐시. ✅`/instruments` 에 report 3모드.
- **build 가드** `validate_standalone_instruments` + `_validate_app_block` 추출 —
  build --check 에 합류. ✅음성테스트로 깨진 참조 포착 확인.
- **report.yaml** standalone 매니페스트(최신/목록/작성). ✅3탭 종단.
- **은퇴** report-viewer → `_archive/report-viewer_retired_2026-07-02/`. self:report
  소멸(액션 142→141). 해마 14용례 회수(ibl_examples+FTS+distilled 638→624). ✅build --check.
- **문서** packages.md·inventory.md 갱신. 데스크탑·원격 UX 동일 보존(프론트 무변경).

미적용(선택): fine-tune 재학습(현 모델은 self:report 어휘를 아직 앎 — 무해,
다음 임베더 재학습 시 자연 소거) · 정기 실행 트리거 등록은 사용자 재량.

## 8. 열린 결정 1가지 (해소됨 — standalone 채택)

**standalone 매니페스트 소스를 도입할지** (§4) 대 **얇은 앵커 액션으로
버틸지**. 후자는 여전히 액션을 하나 남기므로 어휘 폭증을 못 막는다.
→ 권고: **standalone 도입**. 이것이 사용자 논지의 정면 실현이자
substrate/superstructure 이음매의 완성이다.
