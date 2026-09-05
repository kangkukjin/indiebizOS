# 핸드오프 — 정적 통화 검사(실행 전 타입 검사) + 함수 서명의 반환 모양 (2026-09-05, 설계)

> 사용자 문제 제기(2026-09-05, 원문 취지): **"관용구든 새 어휘든 워크플로·스크립트든, 중요한 건 AI 모델의 IBL 구사능력을
> 극대화해 시간·토큰을 아끼면서 답의 품질을 잃지 않는 것이고 새 해결책을 찾는 것이다 — 새 IBL 문장이 새 해결책이다.
> 반복 보고서를 얼린 워크플로로 돌리는 건 항상 거부한다. 창의적으로 IBL 을 조합하는 능력이 없으면 새 과제에서 결국
> 비효율적이다. 핵심 기제는 아마 모델 호출 수를 줄이는 것 아닌가."**
>
> 판정: **"1·2번 핸드오프로 설계해줘"** (1=정적 통화 검사, 2=함수 서명에 반환 모양) → **"핸드오프대로 진행해줘"** (2026-09-05 오후).
>
> ✅ **집행 완료(2026-09-05)** — §4 1~5 전부: `flow` 선언 17건+빌더 관문+`columns_from: data` · `backend/ibl/ibl_typecheck.py` · 창구 셋+초안 관문 ⑤ · parity `--typecheck`(fixture 138·교재 10·코퍼스 3752 error 0) · 함수 반환 서명(`ibl_examples.returns`, 표시 3표면, 27건 산정) · 문서. 시험 `backend/test_ibl_typecheck.py` T1~T12.
> §6 판정은 권고대로 집행(error 차단·인자 `check`·관측 카탈로그는 **보류** — 스칼라 승격 실측 뒤). 집행 중 개정 2건: ①**스칼라는 확답 불가** — script stdout·JSON 파일 읽기가 items 로 승격되므로(코퍼스 실측 21건) 스칼라 입력은 error 가 아니라 warning/침묵 ②검사기(ibl 층)가 workflow_store 를 직접 부르면 workflow_engine→cognition 으로 되돌아오는 층 순환이 생겨(관문 실측) 워크플로·관용구 몸은 cognition(ibl_idiom)이 **등록**하는 소스로만 받는다. §4-6 관찰은 열려 있다.
>
> 자매 문서: `IBL_IDIOM_TIER_HANDOFF.md`(관용구 층) · `IBL_FUNCTION_SYNTAX_HANDOFF.md`(`[def:]`/`[fn:]`) ·
> `IBL_QUALITY_CONTRACT_HANDOFF.md`(criteria) · 커밋 `e871a21c`(이름으로 부르는 학습 루프). 이 문서는 그 루프가 손대지 않은
> 뿌리 — **모델이 문장을 하나씩 실행해 보며 쓰는 이유** — 를 다룬다.

## 0. 진단 — 창의적 조합과 호출 수 감소는 같은 것이다

실측(2026-09-05 정기 보고서 3주행, `world_pulse.db` trajectory_event · episode_log):

| | 동향 ep2827 | 부동산 ep2834 | 팁 ep2832 |
|---|---|---|---|
| execute_ibl 호출 | 23 | 45 | 13 |
| 액션 1개짜리 호출 | 7 | 20 | 4 |
| 모델이 타이핑한 IBL | 18K자 | 18K자 | 11K자 |
| 모델이 되읽은 결과 | 208K자 | 203K자 | 112K자 |
| 실패 호출 | 7 | 4 | 0 |
| 이전 주행과 동일 프로그램 재사용 | 2/23 | 4/45 | 1/13 |

- 모델은 IBL 을 **프로그램이 아니라 REPL** 로 쓴다: 한 문장 실행 → 결과 확인 → 다음 문장. 읽는 양이 쓰는 양의 10배.
- 실패 11건의 대부분이 **언어 안의 실패**다(세계의 실패가 아니다): `union: 모든 입력의 통화 종류가 같아야 합니다 … 분기별 통화:
  1=없음(스칼라/평문)`, `join: 두 입력이 같은 통화여야`, `변수 $투자 이(가) 아직 값을 기록하지 않았습니다(분기 미진입)`,
  `keywords 에는 string 이 와야 하는데 7개짜리 목록`. 전부 **실행 전에 알 수 있는 것**이다.
- 동향 주행의 문장 4~7번은 `query: "a"`·`query: "b"`·`take n: -4` 같은 **문법 탐침**이었고, 성공했으므로 가지 문서 `## 주행` 절에
  '성공 문장'으로 저장됐다(`data/hippocampus_tree/보고서/AI 동향/memory.md`). 모델은 언어를 시험할 안전한 자리가 없어 생산 주행
  안에서 시험한다.

### 뿌리 한 문장
**뒷문장을 쓰려면 앞문장의 반환 모양을 봐야 한다** — `scripts/ibl_shape_sweep.py` 머리말이 이미 이것을 "IBL 조합의 가장 큰 구조적
한계"라 적었다(2026-08-21). ⟨열⟩ 카탈로그가 *낱말 하나*의 반환 열은 말해 주지만, **문장을 지나며 통화와 열이 어떻게 변하는지**는
아무도 실행 전에 말해 주지 않는다. 그래서 모델은 확신이 없는 자리마다 실행해 본다. 함수를 부르지 않는 이유도 같다 —
`[fn:이름]` 이 무엇을 돌려주는지 서명에 없으니 뒤에 무엇을 이을지 모른다.

창의적 조합 = 결과를 안 보고도 긴 프로그램을 한 번에 맞게 쓰는 것. 그 전제는 **언어의 예측 가능성**이고, 예측 가능성을 주는
것은 컴파일러의 타입 검사에 해당하는 **정적 통화 검사**다. 얼린 워크플로는 이 능력을 우회하지만, 타입 검사는 이 능력을 키운다.

## 1. 있는 것과 없는 것

### 있는 것(재사용 대상 — 새로 짓지 않는다)
| 조각 | 자리 | 무엇을 하나 |
|---|---|---|
| dry-run `validate_code` | `backend/surface/api_ibl.py:518` (`/ibl/validate`) | 파싱·어휘 실존·safety(read/write)·ai_call 고지. 구조 step(병렬·폴백·블록·`do` 컨테이너)을 가지 단위로 펼친다. 조종실 검수기. |
| 거짓 빨강 관문 | `scripts/check_validate_parity.py` | fixture 전수·교재 코드 블록·(`--corpus`) 해마 코퍼스에 `valid:false` 0 을 강제. **검수기가 실행기보다 좁아지는 것을 기계로 막는 선례.** |
| param 정적 검사 | `ibl_param_vocab.check_code_params` | 선언 안 된 param 이름(증류 게이트·도구용). |
| 조건식 검사 | `ibl_predicates.validate_condition(cond, known_vars)` | `[if:]` 조건의 미할당 변수·문법. |
| 어휘 생존 검사 | `workflow_engine.preflight_sentence` | 저장 문장의 은퇴 어휘. |
| `returns:` 선언 | `data/ibl_nodes_src/*.yaml` · 패키지 `ibl_actions.yaml` | 4종 = `items`(72) · `effect`(46) · `scalar`(18) · `transform`(17). op 별 `ops.returns` 맵도 있음. |
| ⟨열⟩ 카탈로그 | `data/ibl_return_shapes.json`(sweep 산출, 111건 전부 kind=items) · `ibl_access._shape_suffix/_variant_shapes` | 색인 키 `node:action[#op]`, 변이 `node:action@param=값`(F20-1). 교재 `<ibl_actions>` 줄에 `⟨열: a·b⟩` 로 이미 노출. |
| 런타임 통화 판정기 | `ibl_envelope.classify_currency`(단일 지점, B27-1) · `common.currency.derive_items` | shape ∈ {error, items, message, effect, dict, list, text}. 표(columns/rows)·blocks → items 파생. |
| 함수 시그니처 | `workflow_contract._free_vars` · `ibl_parser._bind_fn_defs/_FN_TABLES` | 미할당 `$이름` = 인자. 반환은 없음. |
| 변환자의 통화 규칙 | data-ops `handler.py`(union 975~, join 1236~) | **런타임에만** 산다 — 코드 안 규칙이라 실행 전엔 아무도 못 읽는다. |

### 없는 것(이 문서가 채우는 자리)
1. **통화 종류의 정적 추론** — `returns: transform` 은 "입력을 따라간다"까지만 말한다. brief 는 산문을 내고, union 은 동종 입력만
   받고, select 는 열을 줄이는데 이 사실이 선언에 없다.
2. **변수의 정적 타입** — `$x` 가 items 인지 산문인지, `$x.items.*.url` 의 `url` 이 있는 열인지 실행 전엔 모른다. 분기 안에서 태어난
   변수를 분기 밖 병렬에서 읽는 것(ep2827 `$투자 미기록`)도 파서는 인덱스만 알 뿐 "진입 안 될 수 있다"를 모른다.
3. **열의 흐름** — select/rename/compute/ai(fields) 가 열 집합을 바꾸는데 뒤 filter/sort 가 없는 열을 집어도 실행해야 안다(ep1325 부류).
4. **함수의 반환 모양** — `[fn:]`·관용구·워크플로 서명에 반환이 없다(`<ibl_idioms>` 의 `[fn:이름]{슬롯: "…"}` 줄, `hippo_tree.phrase_call_line`).
5. **모델에게 열린 검사 창구** — validate 는 조종실 것이고 에이전트 도구 목록(`system_tools.py`)에 검사 도구가 없다. 모델에게는
   *실행이 곧 검사*라서 탐침이 생산 주행에 섞인다.
6. **변환자의 입력 요구 선언** — brief 는 items 가 필요하고(선언 산문에만 "통화 없음=거절"), union 은 동종이어야 한다는 것이 데이터에 없다.

## 2. 설계

### 2-1. 정적 통화 격자(Type)
```
T ::= items⟨C⟩ | prose | scalar | effect | bundle[T…] | unknown
C ::= 열 집합(확정) | 열 집합+open(추가 열 허용) | 미상
```
- 런타임 shape 과의 대응: items↔`items`(파생 포함), prose↔`message`, effect↔`effect`, scalar↔`dict/text/list/스칼라`, unknown↔모름.
  판정기는 하나여야 한다(B27-1) — 정적 격자는 `classify_currency` 의 분류를 **예측**하는 것이지 다른 분류가 아니다.
- `bundle[T…]` = `&` 병렬의 결과(가지별 통화 목록). 소비자(union/join/merge)가 요구를 검사한다. 파이프 없이 문장이 끝나면 봉투 그대로.
- `unknown` 은 격자의 꼭대기다: **unknown 이 들어간 판정은 절대 빨강이 아니다.** 검사기는 아는 것만 말한다(거짓 빨강 금지 — parity 관문의 정신).
- 열 집합은 `⟨열⟩` 카탈로그(fixture 실측)에서 온다. 카탈로그에 없으면 `미상`. 열 이름은 관측 데이터다 — 정규화하지 않는다(F20-1 판정, 명사의 자리).

### 2-2. 선언 확장 — 흐름 규칙은 코드가 아니라 사전 데이터에
`returns: transform` 인 액션(17건)에 `flow:` 를 선언한다(단일 소스 yaml → `build_ibl_nodes.py` 가 `ibl_nodes.yaml`·`tool.json` 으로
파생, `--check` 가 **transform 액션의 flow 누락을 빨강**으로). 검사기는 이 선언만 읽는다 — 액션 이름을 검사기 코드에 넣지 않는다
(헌법: 내용어는 데이터, 파서·엔진에 어휘 이름 금지. 문법인 것은 `fn`·블록·`$변수`·`&`·`>>` 뿐).

```yaml
flow:
  accepts: items | prose | any | same-kind          # 입력 요구. same-kind = bundle 의 가지가 전부 같은 종류(union)
  emits:   same | items | prose | scalar | effect   # 출력 종류. same = 입력 종류 그대로
  columns: keep | subset | rename | add | reset | open   # 열 변화(emits 가 items 일 때)
  columns_param: columns | map | set | fields        # subset/rename/add/open 이 읽는 param 이름
```
초안(선언 값은 각 핸들러 실측과 대조해 확정 — 여기 표가 정본이 아니라 yaml 이 정본):

| 액션 | accepts | emits | columns | 근거 |
|---|---|---|---|---|
| table:filter / sort / take / dedup / since | items | same | keep | 행만 고른다 |
| table:select | items | items | subset(`columns`) | 열이 확정된다 → 뒤 문장의 없는 열은 **확정 오류** |
| table:rename | items | items | rename(`map`) | |
| table:compute | items | items | add(`set`) | 파생 열이 확정 추가된다 |
| table:flatten / groupby | items | items | reset | 열 미상으로 떨어뜨린다(정직) |
| table:union | same-kind(bundle) | items | 합집합 | effect 가지는 1행 통화로 허용(2026-09-05 개정 반영), prose 가지 = 오류 |
| table:join / merge | items×items | items | 합집합 | |
| table:chunk | prose\|items | items | reset | 2026-09-05 신설 |
| table:each | items | items | open(`keep` + do 의 emits 열) | do 문장을 재파싱해 `$it` = 입력 행으로 타입(검수기의 `_walk_do_param` 선례) |
| table:reduce | items | scalar | — | |
| table:ai | items | items | open, `fields` 있으면 subset 확정 | ai-ops 선언 "fields 생략=입력 필드 보존+추가 허용" |
| table:brief | items | **prose** | — | "반환 message=산문 정본" |
| table:structure | prose | items | reset | |
| table:document | items | effect | — | |

`returns: items|scalar|effect` 인 생산자(낱말)는 선언이 이미 충분하다 — 열은 카탈로그에서.

### 2-3. 추론기 `backend/ibl/ibl_typecheck.py` (ibl 층, `check_backend_layers.LAYERS` 등록)
입력 = `parse_with_vars(code)` 의 (steps, variables) — **파싱을 다시 하지 않는다**(`_execute_ibl_unified_impl` 은 이미 두 번 파싱한다: `_pre_parse`·`parse_ibl`; 검사기는 그 결과를 받는다).

걷기 규칙(문장 순서대로, 환경 Γ: 변수 이름 → T):
- **낱말 step** `{_node, action, params}`: T = `returns`(op 있으면 `ops.returns[op]`, `api_ibl._resolve_op` 재사용) + 열 = 카탈로그
  `node:action[#op]`(+ param 리터럴로 변이 `@param=값`). transform 이면 `flow` 로 prev 에서 계산.
- **파이프 `>>`**: prev T 를 다음 step 의 입력으로. 앞이 effect/scalar 인데 accepts 가 items 면 **오류**; prev 가 unknown 이면 통과.
- **`_parallel{branches}`**: 가지별 T → `bundle`. 가지가 `_branch_steps` 면 그 파이프를 먼저 타입.
- **`_fallback_chain`**: 가지 T 의 격자 합(종류 다르면 unknown 종류, 열은 교집합).
- **`_var_emit{name, path}`**: Γ[name] 에 경로 적용 — `.items`→items(같은 열), `.count`→scalar, `.message`→prose, `.items.*.col`→
  scalar 목록(col 이 확정 열 밖이면 확정 오류, 미상이면 통과). params 안의 `{{_step_N_result[.path]}}`(`workflow_binding._inject_step_results`
  자리표)도 같은 규칙으로 param 의 정적 값 종류를 정한다 — `items: "$x"` 에 prose 가 들어가면 오류.
- **블록** `[if:]`·`[case:]`·`[try]`·`[repeat:]`: 몸을 타입하고 블록의 T = 가지 결과의 격자 합. 몸에서 태어난 변수(`_born_vars`)는
  Γ 에 **조건부** 표식으로 등록 — 밖에서 읽으면 `warning`("분기 미진입이면 값이 없다 — 블록 앞에서 초기화하거나 `??` 로 기본값").
  ep2827 의 `$투자 미기록` 부류가 실행 전에 경고로 나온다.
- **`$x = 식`**(`_assign`): scalar.
- **`[def: 이름]{…}`**: 인자 = `_free_vars` → unknown 으로 두고 몸을 타입, 반환 T(`$return` 있으면 그 문장, 없으면 마지막 통화 —
  `_promote_final_currency` 규약과 같은 규칙)를 정의 표에 기록. **`[fn:이름]`**: 정의 표 → 저장 워크플로 → 이름 붙은 관용구 순으로
  몸을 얻어 같은 방식으로 반환 T 를 얻는다(`_execute_fn` 의 해소 순서와 한 벌, 결과는 코드 해시로 캐시). 없으면 unknown.
- **`do`/`pipeline` 문자열 param**(each·trigger·schedule·workflow save): `api_ibl._DO_CARRYING` 과 같은 목록으로 재파싱해 타입.
  each 의 `$it` = 입력 items 의 행(열 = 입력 열).

산출:
```json
{"ok": true|false,
 "issues": [{"severity": "error|warning", "statement": 3, "step": 2, "at": "table:union",
             "message": "union 은 같은 종류의 가지만 받습니다 — 가지 1 = prose([table:brief] 의 산문), 가지 2 = items",
             "hint": "산문은 `[self:write]` 로 저장하거나 items 가 필요하면 brief 대신 [table:ai]{fields: […]}",
             "expected": "same-kind", "got": ["prose", "items"]}],
 "types": ["$재료: items⟨title·url·summary⟩", "$본문: prose", "(3) effect"],
 "fn_returns": {"모으기": "items⟨title·url⟩"}}
```
- `error` = **확정 정보만으로 반드시 실패하는 것**(종류 불일치, 확정 열 밖 참조, 미할당 변수 경로). `warning` = 관측 열 밖 참조·조건부
  변수·미상 입력 등 "아마". 분류가 흔들리면 warning 으로 내린다 — 거짓 error 하나가 참 error 열 개보다 해롭다(같은 부류 B49-1·B53-1).
- 오류문은 **통화의 언어**로(종류·열·문장 번호·고칠 자리) — 런타임 union 오류문("분기별 통화: 1=없음")이 이미 이 어조다. 자가교정 단서 동반(F16-1 선례).

### 2-4. 세 창구 — 구현은 하나, 호출자는 셋(B53-1 선례)
| 창구 | 자리 | 동작 |
|---|---|---|
| **실행 관문** | `system_tools_ibl._execute_ibl_unified_impl` — 노드 접근 체크 뒤, 실행 분기 전 | `error` 가 있으면 **실행하지 않고** `{"success": false, "error_type": "typecheck", "issues", "types"}` 즉시 반환. 부수효과 0·앞 단 재실행 0·오류 위치 정확. `warning` 은 실행하되 봉투에 `_typecheck_warnings` 로 신고(정직 표지 목록 `ibl_honesty` 에 등록). |
| **검사만** `execute_ibl{code, check: true}` | `mcp_server.execute_ibl` 인자 + 통합 실행기 | 실행 없이 issues+types 만. 0 토큰(모델 밖)·부작용 0. **모델의 탐침 자리** — `query: "a"` 를 돌려 보는 대신 여기서 통화를 확인하고 긴 프로그램을 한 번에 실행한다. |
| **조종실 검수** `/ibl/validate` | `api_ibl.validate_code` | 기존 반환에 `issues`·`types` 병합. parity 관문이 같은 함수를 쓰므로 거짓 빨강 방지가 자동 승계. |

parity 관문 확장: `check_validate_parity.py --typecheck` — fixture 전수·교재 코드 블록·(`--corpus`) 해마 코퍼스 **실행 성공 문장**에
typecheck `error` 0. 추론기의 어떤 규칙도 이 관문을 통과해야 배포된다. (실행이 성공한 문장에 error 를 내면 규칙이 틀린 것이다 — 규칙을
고치지 문장을 고치지 않는다.)

### 2-5. 함수 서명의 반환 모양
- **파서/실행기**: `_FN_TABLES[tid][name]` 에 `returns`(추론 T 문자열) 추가. `_execute_fn` 결과 봉투에 `fn_returns`. 인자 누락 오류문의
  "시그니처는 $a, $b 입니다" 뒤에 `→ items⟨…⟩` 를 붙인다.
- **저장 시 계산**: 관용구(`ibl_idiom._distill_phrase`·`replay_idioms`)·워크플로(`save_workflow`) 저장 관문에서 추론기로 반환 T 를 계산해
  저장 — `ibl_examples` 새 컬럼 `returns TEXT`(예 `items⟨title·url⟩` / `prose` / `?`). 슬롯 값이 미상이면 열은 미상으로 정직하게(`?`).
  기존 19건은 `replay_idioms.py --type-idioms --apply` 로 일괄.
- **표시 3표면**(이름 먼저 원칙 그대로 — 본문은 여전히 expand 때만):
  - `<ibl_idioms>`(`ibl_access._idioms_block`): `[fn:이름]{슬롯: "…"} → items⟨title·url·summary⟩`
  - recall 이름 먼저(`hippo_tree.render_names_first`·`phrase_call_line`) 와 가지 문서 머리 `· 반환 items⟨…⟩`(구문 관문 `PHRASE_CALL_RE` 확장)
  - 교재 함수 절(`12_ibl_only.md` "함수") 예제 한 줄: `[def: 모으기]{…}  → items⟨title·url⟩`
- **의미**: 이제 `[fn:이름]` 은 부르기 전에 무엇이 나올지 안다. 관용구는 "이름 있는 덩이"에서 **"서명 있는 덩이"**가 되고, `[def:]` 로 긴
  프로그램을 덩이로 나눠 한 번에 실행하는 하향식 작문(정의는 `todo` 로 걸어 두고)이 타입 검사 아래서 안전해진다 — 함수의 본래 쓸모는
  어제 것을 재사용하는 게 아니라 **한 프로그램 안의 분해**다.

### 2-6. 카탈로그 커버리지
- sweep 정본은 fixture 우주(부작용 없는 낱말)만 — transform 은 입력이 필요해 fixture 가 없고, 그래서 `flow` 선언이 그 자리를 덮는다.
- 런타임 관측: `classify_currency` 가 이미 `action_health` 에 shape 을 기록한다(2026-08-24). 같은 자리에서 **열 이름**도 기록해
  `data/ibl_return_shapes_observed.json`(기계 생성, 관측일 동반)에 쌓는다. 추론기는 fixture 정본 우선·관측은 보조(`warning` 근거로만,
  확정 오류 근거로는 쓰지 않는다 — 관측은 한 변이일 수 있다).
- 열이 미상인 액션은 `types` 에 `⟨열: 미상⟩` 으로 보인다 — 모델이 "어느 열이 있나"를 물을 자리는 여전히 `check: true` + 짧은 실행이다.
  카탈로그 공백 자체가 sweep 의 fixture 추가 신호다(기존 라이프사이클).

### 2-7. 가르치는 표면(최소)
- `12_ibl_only.md`: 두 줄 — ①"긴 프로그램은 `check: true` 로 통화·열을 먼저 보고 한 번에 실행한다(탐침을 돌리지 않는다)" ②봉투의
  `types`/`issues` 읽는 법. 41.7KB 교재에 문단을 더하지 않는다 — 대신 §2-2 의 규칙이 산문으로 적혀 있던 자리(예: "union 은 동종만",
  "brief 는 산문") 는 검사기가 잡으므로 **그 산문을 줄이는 것**이 이 개정의 부수 효과다(교재 예산 관문은 별도 항목).
- `mcp_server.execute_ibl` docstring 에 `check` 한 줄. 가이드는 무관(문법책 아님).

## 3. 하지 말 것(헌법 대조)
- 검사기 코드에 액션 이름을 넣지 않는다 — 흐름 규칙은 yaml `flow` 데이터로만(`ibl_standard_core`: 문법+기능어 코어만 코드).
- 열 이름을 정규화하거나 추측하지 않는다 — 열은 관측 데이터(F20-1·명사의 자리). 미상은 미상이라 말한다.
- unknown 을 빨강으로 만들지 않는다 — 거짓 빨강은 멀쩡한 문장의 차단이다. 확신 없는 규칙은 warning 으로 내리고, parity 관문이 error 0 을 집행한다.
- 자동 수정·자동 재작성 금지 — 검사기는 위치와 이유를 말하고 **모델이 고친다**(`feedback_ai_work_not_fixed_program`).
- 카운터를 심어 두고 보지 않는다 — 빌더 `--check`(flow 누락)·parity `--typecheck`(거짓 error)·시험 픽스처가 실패시킨다(`feedback_no_counter_watch`).
- 이 검사로 보고서 배관을 얼리지 않는다 — 검사기는 어떤 문장이든 같은 눈으로 본다. 반복 여부는 관심사가 아니다.

## 4. 작업 순서(착수 판정 뒤)
1. **선언**: transform 17건에 `flow` — `data/ibl_nodes_src/table.yaml`(each·reduce)·`data-ops/ibl_actions.yaml`·`ai-ops/ibl_actions.yaml`;
   `build_ibl_nodes.py` 스키마 + `--check`(transform 이면 flow 필수); 재빌드 → 마커 구간 즉시 커밋 → `/packages/reload`.
   `data/guides/new_action_checklist.md` 에 "transform 이면 flow 선언" 한 줄(어휘 변경 문서 표면 규약).
2. **추론기**: `backend/ibl/ibl_typecheck.py` + `backend/test_ibl_typecheck.py` T1~T9 (fixture 격리, 실 DB·트리 무접촉):
   T1 낱말 T·열 / T2 파이프 흐름(keep·subset·add·reset) / T3 union same-kind(오늘 ep2827·2834 재현: prose+items, scalar 가지) /
   T4 join·merge / T5 변수 경로(`.count`·`.items.*.col`·prose 에 `.items`) / T6 분기 태생 변수 warning(ep2827 `$투자`) /
   T7 `[def:]`/`[fn:]` 반환 T(정의·워크플로·관용구 세 길) / T8 each 의 `do` 재파싱과 `$it` 열 / T9 unknown 은 절대 error 가 아니다(음성 시험).
3. **창구 셋 + 관문**: 통합 실행기 error 차단·warning 신고(`ibl_honesty` 목록 등록), `check` 인자(mcp_server·통합 실행기·`/ibl/execute` 본문),
   `validate_code` 병합, `check_validate_parity.py --typecheck`(fixture·교재·`--corpus`) — **관문이 초록이어야 창구를 연다.**
4. **함수 반환**: `_FN_TABLES.returns`·`_execute_fn` 봉투·인자 오류문, 관용구/워크플로 저장 시 계산 + `ibl_examples.returns` 컬럼(마이그레이션은
   `add_examples_batch` 경로 무관 — ALTER 한 줄, 기존 19건 일괄 산정), 표시 3표면, `PHRASE_CALL_RE` 확장 + `test_hippo_syntax_gate`.
5. **문서**: 교재 두 줄 · mcp docstring · `ibl.md` '통화와 변환자' 절(flow 선언·정적 검사 한 단락) · `memory.md`(관용구 서명에 반환) ·
   `technical.md`(validate 응답 필드·`check` 인자) · changelog · 이 문서 머리 상태 갱신.
6. **관찰**(2주, 보고서 제외 — 새 요청에서 잰다): 과제당 execute_ibl 호출 수 · 첫 프로그램 성공률 · 호출당 문장 수 · 실행 실패 중 통화 부류 비율
   (목표: 실행 단계에서 union/join/변수 부류 실패 0 — 전부 check 단계로 이동) · `check: true` 호출 수 · 주행 절의 탐침 문장 수. 반성의 "세 번째 질문"
   (어제와 무엇이 달랐나·이름으로 부를 수 있었나)은 별도 핸드오프 — 이 문서 범위 밖.

## 5. 위험과 한계(정직하게)
- **동적 값**: `columns: "$x"` 처럼 param 이 변수로 오면 열 변화는 미상 → 통과(초록이지만 정보 없음). `types` 에 미상으로 표시.
- **스필 참조**: 이음매의 투명 해소는 통화를 바꾸지 않는다 — 검사기는 스필을 모르는 채로 옳다.
- **표(columns/rows)·blocks 생산자**: `derive_items` 가 items 로 파생하므로 정적으로도 items 로 본다(returns 선언과 어긋나는 straggler 는 sweep 이 이미 신고).
- **세 번째 파싱 금지**: 통합 실행기의 두 파싱 결과를 재사용한다. 검사 비용은 카탈로그 mtime 캐시 + 걷기 한 번 — 실행 대비 무시 가능.
- **폰 번들**: `ibl_nodes.yaml` 파생물은 안드로이드 번들 재파생 대상(`project_ledger_vocab_promotion` 함정).
- **성급한 확정 열**: 카탈로그의 열은 fixture 한 변이의 관측이다. 그래서 "관측 열 밖 참조"는 warning 이고, error 는 **문장 안에서 확정된 열**(select·rename·compute·ai fields)에만 낸다.
- **효과 봉투의 union 허용**(2026-09-05 개정)처럼 런타임 규칙이 바뀌면 flow 선언도 같이 바뀌어야 한다 — parity `--typecheck` 가 그 어긋남을 잡는다(성공 문장에 error).

## 6. 판정이 필요한 것
1. **착수 여부.** 문법 개정은 아니다 — `flow` 는 사전 선언 스키마 확장(데이터), `check` 는 도구 인자, 검사는 실행 관문이다. 다만 표준 코어 `table` 노드의
   선언 스키마가 넓어지므로 `ibl.md` 의 변환자 절을 함께 개정한다(언어 개정으로 분류할지는 판정).
2. **실행 관문에서 `error` 차단** — 권고: 차단. 부수효과 전에 실패하고 오류 위치가 정확하다. 거짓 빨강은 parity 관문이 0 을 보증한다.
   대안(신고만 하고 실행)은 오늘과 같은 왕복을 남긴다.
3. **인자 이름** — 권고 `check`(`verbose`·`recover`·`wait` 와 나란히). 별도 도구(`validate_ibl`)는 도구 수를 늘리므로 비권고.
4. **관측 카탈로그**(`_observed.json`) 를 둘지 — 권고: 둔다, 단 warning 근거로만.
