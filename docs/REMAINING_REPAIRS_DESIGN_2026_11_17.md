# 남은 수리 네 가지 — 추천 설계 (2026-11-17)

다른 세션이 이어서 하기 위한 인계 문서다. 2026-11-17 하루의 에피소드 6192 점검에서 나온 것을 고치고 남은
네 가지를 다룬다. 이 문서의 수치는 2026-11-17 밤에 운영 기록(`data/world_pulse.db`)과 코드에서 직접 센 것이다.
코드 위치는 그때의 작업 트리 기준이며, 그날의 변경은 이 문서를 쓴 시점에 **커밋되지 않았다**(0절).

| 항목 | 추천 | 상태 (2026-11-17 밤, 구현 뒤) |
|---|---|---|
| 1-가. 자기수리 턴에서 실행자 안내와 하네스가 어긋나는 것 | 고친다 | **구현함** (1.5) |
| 1-나. 자기수리 턴에도 심층실행을 돌릴지 | 정본 반영 전(사본 단계)에만 돌린다 | 사용자 채택, **구현함** (1.5) — 실제 수리 턴은 아직 못 봄 |
| 2. `#repair`를 직접 붙이면 의식 없이 가는 경로 | 없앤다 | 사용자 채택, **구현함** (2.4) |
| 3. 세션 리셋 | 자동 리셋은 되살리지 않는다. 새로 여는 것은 "새 세션" 버튼으로 이미 되고, 크기를 사실로 보여 준다 | 사용자 결정(대화창 상단에 숫자로), **구현함** (3.4) |
| 4. `framing_inheritance.py` 모듈 이름 | 맡은 일대로 셋으로 나눈다 | **구현함** (4.4) |

네 가지 모두 구현했다(이 문서를 받은 다음 세션, 2026-11-17 밤). 남은 것은 0.2의 "확인하지 못하고 남긴 것"뿐이다.

사용자의 말(2026-11-17 밤): "일관성을 가지자면 수리판정을 받으면 모두 의식이 생각하고 수리하는 게 좋겠어.
사용자가 #repair로 수리판정을 내린 건 무의식이 수리판정 내린 것과 같은 거지. 재기동 뒤나 검수 지점 복원은
규정에 따라서 하는 거니까 예외로 두더라도." / "네가 추천한 대로 자기수리 턴에도 정본 반영 전에는 심층실행을
돌리도록 해. 세션 크기는 대화창 상단에 숫자로 보여 주면 될 거 같아."

남은 사용자 판정은 없다. 2.5의 "업무 도중의 한정 수리"는 지금대로 둔다(사용자 "지금대로 둬"). 이 문서를
처음 쓸 때는 그 경로를 몰랐다.

남은 일의 권하는 순서: 1-가 → 4 → 1-나 → 3. 1-가는 작고 독립적이다.

---

## 0. 이 문서를 받는 세션이 먼저 알 것

### 0.1 그날 고친 것과 저장소 상태

2026-11-17에 아래를 고쳤고, 이 문서를 쓰는 시점에 `git status`로 49개 파일이 커밋 전이다. 커밋 여부는
`git log`로 확인한다. 변경 이력은 `data/system_docs/changelog.log`의 `[2026-11-17]` 항목들이 정본이다.

- 모델 공급자의 과금 키를 실행자 명령에 건네지 않음(몸의 셸, CLI 기동 환경, Codex 셸 정책)
- HWP 읽기의 서로게이트 쌍, 구글 뉴스 주소 풀기의 같은 결함
- 명령과 함께 끝낸 하위 프로세스를 결과에 적음, 실패 진단에 오류 글이 빠지던 것
- 규정 계승 제거 — THINK 판정이면 의식이 새로 규정한다
- 수리 재개 판정을 의식 축 모델로, 멈춘 수리의 재개는 의식이 지금 상태에서 남은 일을 규정
- 심층실행 '계속' 판정에도 의식의 갈래·질문 전달, 없어진 끝 확인 문장 삭제

사용자 판정은 `data/decisions.yaml`에 올렸다: `model-work-through-body`, `think-always-fresh-framing`,
`repair-resume-rethinks-from-present-state`.

### 0.2 확인하지 못하고 남긴 것

수리가 아니라 확인이 남은 것이다. 해당 상황이 생기면 기록으로 본다.

- **실제 수리 재개 턴**: 멈춘 수리와 주인의 수리 승인이 있어야 해서 만들지 못했다. 볼 것은 사건
  `repair.resume_rethink`(used 참/거짓)와 그 턴이 다시 멈추는지다. 예행(`origin: training`)에는 수리 권한이
  없어 이 경로를 타지 않는다.
- **Codex를 실행자로 둔 운영 턴**: 모델 키 차단은 실제 CLI를 공급자의 환경·옵션으로 직접 띄워 확인했다.
- **'계속' 판정에 갈래·질문이 붙는 경우**: 검사로만 확인했다. 실제 턴(6202)의 판정은 '마무리'였다.
- **자기수리 턴의 심층실행(1-나)**: 검사로만 확인했다. 예행에는 수리 권한이 없다. 볼 것은 사건
  `supervision.deep.started`(수리 턴에서 depth 1 이상)·`deep.reflection`·`deep.not_applied`이고, 되돌아보기가
  수리 도구의 거절과 겹쳐 혼란을 만드는가, 판정이 방향을 바꾸는가, 재기동 뒤 사용자가 이었을 때 차례 번호가
  이어지는가(인계 기록의 `deep` 칸), 반영되지 않은 주문이 최종 응답에 드러나는가다.
- **실제 턴 뒤의 세션 크기 갱신(3)**: 이미 적힌 크기가 운영 백엔드에서 내려오고 대화창 머리에 보이는 것은
  확인했다(시스템 AI 대화, 116,643 → `11.7만`). 이 변경 뒤에 돈 실제 턴이 표식(`cli_session.json`)을 남기고
  숫자가 바뀌는 것은 검사로만 확인했다.

### 0.3 이 저장소에서 일할 때

- 라이브 백엔드는 정본 파일을 저장하면 세대를 봉인해 교체한다. 예행 전에 `data/restart_control/state.json`의
  `phase`가 `ACTIVE`인지 본다. 어휘 소스(`ibl_actions.yaml`)를 고치고 빌드하면 수십 초 동안 요청을 못 받는다.
- 전체 회귀: `.venv/bin/python3 -m pytest -m "not system" -n auto --dist loadfile -rfE`(저장소 루트에서, 4~5분).
  도는 동안 추적 파일을 고치지 않는다.
- 패키지 `.py`를 고치면 그 패키지의 회원 개방 액션 지문(`path_audited.impl`)이 어긋난다. 빌드 `--check`가
  알려 주는 값으로 `ibl_actions.yaml`을 고치고 다시 빌드한다(`system_essentials`=self:read·fill·write·script,
  `web`=sense:search·sense:crawl).
- 예행: `POST /system-ai/chat`에 `{"message": …, "origin": "training"}`. 요청문에 "저장·기억·발행·원장 갱신
  없이 결과만 대화로"를 넣는다. 의식만 불러 보려면 `consciousness_agent.get_consciousness_agent().process(…)`를
  `PYTHONPATH=backend .venv/bin/python3`에서 직접 부른다(구독 CLI로 돌고 저장하지 않는다).
- 주인의 API 키를 쓰는 길로 시험하지 않는다(`decisions.yaml` `model-work-through-body`).

---

## 1. 자기수리 턴의 심층실행

### 1.1 지금 상태

심층실행은 수리 권한이 있는 턴에서 돌지 않는다. 막는 곳이 둘이다.

- `backend/cognition/deep_execution.py`의 `_state`: `controller.repair_granted`이면 단계를 0으로 둔다.
- 같은 파일의 `depth_of`: 규정 출처(`_framing_source`)가 `repair`로 시작하면 0이다(수리 인계, `#repair` 직접).

설계 문서(`docs/DEEP_EXECUTION_DESIGN_2026_11_15.md`)는 8.1에서 "심층연구·자기수리·되묻기 턴과 EXECUTE로 간
일에는 없다"고 적고, 9절 3번에 "자기수리로 간 일에도 1단계를 적용할지"를 열린 결정으로 남겼다.

심층실행이 들어온 11월 15일 이후 수리 권한이 있는 턴은 **1건**(에피소드 6155, 84초)뿐이다. 운영 기록으로는
어느 쪽도 뒷받침할 수 없다. 참고로 5000번 이후 의식이 규정하고 권한이 발급된 수리 턴은 21건, 소요 중앙값
354초, 5분을 넘긴 턴 13건이다.

### 1.2 결함 (1-가): 실행자 안내와 하네스가 어긋난다

실행자에게 주는 안내는 규정만 보고 만든다(`prompt_builder.py` 753행 근처 → `deep_execution.execution_block` →
`depth_of`). 수리 권한은 보지 않는다. 그래서 의식이 새로 규정한 수리 턴(출처 `fresh_consciousness`)에서:

- 실행자는 "심층실행 1단계: 실행 도중 1번, 정해진 지점에서 방향 담당자에게 돌아가 방향을 다시 받는다"를 받는다.
- 하네스의 단계는 0이다. 실행자가 돌아오면 "이 턴에는 되돌아보기가 없다. 그대로 진행한다"를 받는다.

사용자가 수리 요청에 단계 수를 붙인 경우도 같다. 의식이 `deep_execution`에 옮겨 적지만 돌지 않고, 돌지
않았다는 사실은 사용자에게 가지 않는다. 그런 요청은 아직 한 번도 없었다(6100번 이후 0건). 같은 날 아침의
단계 상한 5, 저녁의 규정 계승과 같은 부류다 — 주문이 반영되지 않았는데 그 사실이 남지 않는다.

`prompt_builder.py`의 주석 "심층실행(기본 꺼짐)"도 낡았다(기본 켜짐이다).

### 1.3 추천 (1-가): 한 곳에서 정하고, 반영되지 않은 주문은 말한다

1. 이 턴에 몇 단계가 도는지를 한 함수가 정한다. `_state`와 `execution_block`이 같은 함수를 쓴다. 입력은
   규정과 "수리 권한이 있는가"다. 지금은 `_state`만 권한을 본다.
2. 단계가 0이면 실행자 안내에 심층실행 문장을 넣지 않는다.
3. 사용자가 단계를 주문했는데(규정의 `deep_execution`이 1 이상) 돌지 않으면:
   - 사건 `deep.not_applied`를 남긴다(주문한 수, 이유).
   - 실행자 안내에 사실 한 문장을 넣는다: 사용자가 N단계를 주문했고, 이 턴에는 되돌아보기가 없다. 최종
     보고에 적으라는 말은 붙이지 않아도 된다 — 사실을 받은 실행자가 보고할지 판단한다. 다만 반영되지 않은
     주문이 응답에 드러나는지는 예행으로 확인한다.

`prompt_builder`는 규정만 받으므로, 권한 여부를 건네는 방법이 필요하다. `_refresh_execution_prompt`가 불리는
자리(`agent_pipeline.py`)에는 `_repair_granted_task`가 있다. 규정에 임시 칸을 넣지 말고 인자로 건넨다.

검사: 권한 있는 수리 규정으로 안내를 만들면 심층실행 문장이 없다 / 주문이 있으면 그 사실 문장이 있고 사건이
남는다 / THINK 턴의 안내는 글자 하나 달라지지 않는다.

1-나를 채택하면 이 수리의 일부는 필요 없어지지만, 2번과 3번은 "수리 인계 턴"에서 여전히 쓰인다.

### 1.4 채택 (1-나): 사본 단계에서만 돌린다 — 2026-11-17 사용자 채택

권하는 것은 **의식이 새로 규정한 수리가 사본에서 작업하는 동안(정본 반영 전)에는 THINK와 같이 돌린다**이다.
말이 없으면 1단계, 사용자가 시키면 그 단계. 정본에 반영된 뒤와 검수 지점에서는 돌리지 않는다.

이유:

- 사용자가 같은 날 한 말과 같은 방향이다("수리야말로 중요하니까 의식이 제대로 판단해야").
- 수리가 길다(중앙 354초, 21건 중 13건이 5분 이상). 첫 걸음 직후의 되돌아보기가 방향을 바로잡을 여지가 있다.
- 사본 단계는 되돌릴 수 있다. 정본 반영 뒤에는 수리 도구가 활성 확인만 받으므로 방향을 바꿀 것이 없다.

얽힌 것 셋을 같이 풀어야 한다.

1. **재기동을 넘는 횟수.** 되돌아보기 상태(`controller._deep`)는 메모리에 있다. 수리는 적용하면서 백엔드를
   재기동하고, 이어지는 턴은 새 감독으로 시작한다. 횟수와 작업 메모를 인계 기록(`repair_continuation`의 행)에
   실어야 한다. 그러지 않으면 재기동 뒤에 처음부터 다시 센다.
2. **적용을 예약한 뒤에는 세우지 않는다.** 되돌아보기를 청할 때 하네스는 실행자의 다음 도구 호출을 세운다.
   적용 예약과 재기동 사이에 호출을 세우면 수리 절차가 꼬일 수 있다. 사본 단계(`phase == "execution"`이고
   세션 상태가 `staging`)에서만 청한다.
3. **수리 인계 턴.** 사용자의 말로 이은 수리는 의식이 그 자리에서 다시 규정한다(`repair_resume.rethink`). 그
   규정이 곧 되돌아보기이므로 인계 턴에서는 남은 횟수만 이어 쓴다. 지금 `rethink`는 의식이 적은 `deep_execution`과
   `first_step`을 버린다 — 1-나를 채택하면 사본 단계의 재개에서는 버리지 않는다.

근거가 없으므로 채택하더라도 처음 몇 번의 실제 수리 턴을 본다. 볼 것: 되돌아보기가 수리 도구의 거절과 겹쳐
혼란을 만드는가, 판정이 실제로 방향을 바꾸는가, 재기동 뒤 횟수가 이어지는가.

구현하면서 정할 것(사용자 판정 불필요, 구현하는 세션이 정한다):

- 사용자의 말로 이은 수리 턴: 의식이 그 자리에서 다시 규정하므로 그것이 되돌아보기다. 남은 횟수만 이어 쓰고,
  사용자가 그 말에 단계를 붙였으면 그 단계를 따른다.
- 업무 도중의 한정 수리(2.5)와 `#repair` 없이 하네스가 자동으로 잇는 턴에는 돌리지 않는다(규정 출처가
  `repair`로 시작하면 0 — 지금의 `depth_of` 그대로).
- 설계 문서(`DEEP_EXECUTION_DESIGN_2026_11_15.md`) 9절 3번을 "사본 단계의 수리 턴에 적용"으로 닫고 8.1에 적는다.

### 1.5 구현한 것 (2026-11-17 밤, 다음 세션)

1-가와 1-나를 한 번에 했다. 정본 서술은 `docs/DEEP_EXECUTION_DESIGN_2026_11_15.md` 8.1 '자기수리 턴의 심층실행'.

- `deep_execution.turn_plan(규정, 설정, repair=, handoff=)`이 이 턴에 도는 횟수를 정한다. 감독은 `configure`
  때 `prepare`로 한 번 정해 두고(`controller._deep_plan`), `_state`·`execution_block`·턴 도중의 재규정 안내
  (`reframe.render_for_executor`)가 같은 값을 쓴다. 수리 권한은 `_refresh_execution_prompt(…, repair=)` →
  `compile_user_command(…, repair=)`로 인자로 건넨다(규정에 임시 칸을 넣지 않았다).
- 의식이 새로 규정한 수리 턴은 THINK와 같이 돈다. `_state`에서 `repair_granted`로 0을 만들던 조건을 지웠다.
- 사본 단계의 문: `deep_execution.past_copy` — `controller.apply_scheduled`이거나 수리 사본 상태가 `staging`이
  아니면(`repair_continuation.before_canonical`) 청하지도 되돌아보지도 않는다. 감시 주기(`tick`)·실행자의
  복귀(`checkpoint`)·대신 되돌아보기(`reflect`) 세 곳에 걸었다.
- 인계: `deep_execution.record` → 인계 기록의 `deep` 칸(`{depth, done, ordered, memo}`). 싣는 곳은
  `repair_continuation.defer`·`review_checkpoint`, `repair_resume.preserve_unfinished`. `inherited_framing`은
  `deep_execution`·`first_step`을 뺀다. `repair_resume.rethink`는 사본 단계의 재개에서 의식이 적은 둘을 둔다.
- 반영되지 않은 주문: 실행자 안내의 사실 한 문장 + 사건 `deep.not_applied`. 보고하라는 말은 붙이지 않았다.
- `prompt_builder.py`의 낡은 주석("기본 꺼짐")을 고쳤다.

구현하면서 정한 것:

- 사용자의 말로 이은 수리에서 남은 횟수가 0이면(앞선 턴이 다 썼거나, 심층실행이 들어오기 전에 시작한 수리라
  기록이 없으면) 그 턴에는 되돌아보기가 없다. 의식이 그 자리에서 다시 규정한 것이 되돌아보기다.
- 사용자가 이으면서 단계를 붙이면 그만큼 더 돈다. 차례 번호는 앞선 턴에서 잇는다(2번 하고 3단계를 붙이면 3/5부터).
- 적용이 물려 사본 상태가 `staging`으로 돌아오면 다시 돈다(문은 그때그때 사본 상태를 읽는다).
- 턴 도중의 재규정은 규정 출처를 `fresh_consciousness_revision`으로 바꾼다. 단계는 턴을 열 때 정한 것을 그대로 쓴다.

검사: `backend/test_deep_execution.py`의 자기수리 절 7개, `backend/test_repair_resume.py` 2개(사본 단계에서는
주문·첫 걸음을 두고 정본 반영 뒤에는 뺀다 / 인계 기록이 횟수를 싣고 턴 전용 칸을 뺀다). THINK 턴의 안내가
옛 판과 글자까지 같은 것은 옛 판(`git show HEAD:…`)과 12건을 대조해 확인했다. 전체 회귀 13,011 통과, 빌드
`--check`·층·파일 크기·문서 드리프트·의식 스키마 검사 통과. 바뀐 경로로 보통 THINK 턴이 끝까지 가는 것은 운영
백엔드의 예행 1건으로 봤다(`task_sysai_afbc8783`, `deep.started` depth 1).

---

## 2. `#repair`를 직접 붙이면 의식 없이 가는 경로

### 2.1 지금 상태

`backend/cognition/cognitive_consciousness.py`의 `_run_consciousness_or_reuse`:

```
수리 턴이고, 사용자가 직접 친 말이고, 메시지에 #repair 가 있고 #think 가 없으면
    → repair_policy.direct_framing(message)   (의식을 부르지 않는다)
```

`direct_framing`(`backend/cognition/repair_policy.py`)은 사용자의 요청문을 그대로 과제와 완료 기준 하나로
쓰고, 고정된 안내 문단을 접근 힌트로 붙인다. 출처는 `repair_execution`이다. 이 출처에서는 실행 중 감독
검토도 돌지 않는다(`conscious_supervisor.py`의 `review` 첫머리 — "직접 수리의 도구 실패는 같은 실행자가 받는다").

들어온 때는 2026-10-03(`edd33bb5` "자기수리 실검사 재사용과 조건별 검토로 반복 심사·새 실행 제거")이다.
수리에서 심사가 되풀이되던 것을 줄이려는 변경이었다.

| | `#repair` 직접 | 의식이 규정한 수리(권한 있음) |
|---|---|---|
| 턴 수 | 13 (10-03 ~ 11-02, 그 뒤 0) | 21 (5000번 이후) |
| 소요 중앙값 | 380초 | 354초 |
| 도구 호출 중앙값 | 23 | 26 |
| 그 턴에서 끝까지 감 | 2 | 1 (판정이 로그에 없는 턴 12) |

두 경로는 걸린 시간과 호출 수가 비슷하다. 판정 기록이 고르지 않아 어느 쪽이 더 잘 끝나는지는 이 표로 말할
수 없다. 의식을 건너뛰어 아끼는 것은 의식 호출 한 번(같은 날 실측 10~35초)이다.

### 2.2 추천: 없앤다 — 사용자 결정 필요

`#repair`는 차선(수리)만 정하고, 규정은 다른 수리와 같이 의식이 쓴다.

이유:

- 같은 날 사용자가 정한 것과 같은 꼴이다. 규정 계승은 "의식 호출을 아끼려고 의식을 건너뛰는 길"이라 없앴고,
  수리에 대해서는 "수리야말로 중요하니까 의식이 판단해야 한다"고 했다. 이 경로는 사용자가 수리라고 분명히
  말한 요청에서 의식을 건너뛴다.
- 완료 기준이 요청문 한 줄이 된다. "계속해", "고쳐줘" 같은 짧은 말이 그대로 기준이 된다.
- 고정된 안내 문단이 실행자의 접근 힌트 자리를 차지한다(관용구 저장법, 검사 계획 인자 같은 처방). 같은 날
  수리 재개에서 고정 지시문을 사실로 바꾼 것과 반대 방향이다.
- 11월 2일 이후 한 번도 쓰이지 않았다. 없애도 잃는 운영 흐름이 없다.

남기는 것: 영수증으로 완료를 판정하는 길(`repair_policy.receipt_completion`·`finalize`·`completion`)은
`_repair_policy == 2`에 달려 있고, 의식이 규정한 수리에도 같은 값이 붙는다(`_run_consciousness_or_reuse`가
넣는다). 직접 경로를 없애도 이 길은 그대로다.

### 2.3 손댈 곳

1. `cognitive_consciousness.py`: `#repair` 분기를 지운다. `#think` 예외도 같이 없어진다.
2. `repair_policy.py`: `direct_framing`을 지운다. 나머지 함수는 그대로 둔다.
3. `conscious_supervisor.py`의 `review`: `repair_execution` 출처를 건너뛰는 줄을 지운다. 이 줄이 없어지면
   수리 턴에서도 실행 중 감독 검토(연속 실패 2회 방아쇠, 최대 2번)가 돈다 — 10월 3일에 줄이려던 "반복 심사"가
   되살아나는지 본다. 그때의 반복은 적용 전 검토가 여러 번 돌던 것이고, 지금의 방아쇠는 실패에만 걸린다.
4. 출처 이름 `repair_execution`을 읽는 다른 곳: `deep_execution.depth_of`의 `startswith("repair")`는
   `repair_continuation`에도 걸리므로 그대로 둔다.
5. 지문: `data/common_prompts/fragments/13_repair.md`, `14_consciousness_repair.md`에 직접 수리를 전제한 문장이
   있는지 읽고, 있으면 고친다(이 문서를 쓰며 읽지 않았다).
6. 검사: `repair_execution`·`direct_framing`을 쓰는 검사를 찾아 고친다(`grep -rn "repair_execution\|direct_framing" backend/test_*.py`).
   새 검사 하나 — `#repair`가 붙은 사용자 요청도 의식이 규정한다(의식 호출 1번, 출처 `fresh_consciousness`).
7. `data/decisions.yaml`에 판정을 올리고(예: `repair-always-framed-by-consciousness`), `anatomy.md`와 변경 이력에 적는다.

확인: 예행으로는 수리 권한이 없어 이 경로를 끝까지 볼 수 없다. 의식이 `#repair` 요청을 어떻게 규정하는지는
의식만 직접 불러 볼 수 있다. 실제 턴은 사용자가 다음에 `#repair`를 쓸 때 본다.

### 2.4 구현한 것 (2026-11-17 밤, 사용자 채택 뒤)

`cognitive_consciousness._run_consciousness_or_reuse`에서 `#repair` 분기를 지웠다. 이제 사용자의 수리 요청은
`#repair`를 붙였든 무의식이 판정했든 의식이 규정한다(`#repair`는 차선만 정한다). 검사 둘
(`test_user_repair_tag_goes_to_the_planning_model`, `test_every_repair_turn_is_framed_by_consciousness`).
판정은 `data/decisions.yaml`의 `repair-always-framed-by-consciousness`.

2.3에 적은 손댈 곳 가운데 2번과 3번은 **하지 않았다**. 아래 2.5 때문이다.

### 2.5 이 문서가 몰랐던 세 번째 경로 — 업무 도중의 한정 수리

`direct_framing`은 사용자의 `#repair`만 쓰는 것이 아니었다. 수리 권한이 없는 보통 업무 도중에 실행자가 구현을
고쳐야 한다고 요청하면(`patch_op`의 `propose`), 하네스가 그 요청문을 그대로 규정으로 삼아 범위가 한정된 자식
수리를 연다(`backend/datastore/task_repair.py`의 `request`, 패키지 `system_essentials/handler.py`가
`framing_factory=repair_policy.direct_framing`으로 부른다. 2026-10-31 `35f8d306`). 이 수리도 의식 없이 가고,
규정 출처가 `repair_execution`이라 실행 중 감독 검토도 돌지 않는다. 끝나면 부모 업무로 돌아온다.

2.1의 표에 적은 "`#repair` 직접 13턴"은 규정 출처가 `repair_execution`인 턴을 센 것이라 이 자식 수리가 섞여
있을 수 있다. 둘을 가르지 않았다.

그래서 남긴 것: `repair_policy.direct_framing`(머리말에 남은 용도를 적음), 감독 `review`의 `repair_execution`
건너뛰기, 기준 계약의 `owner: execution`. 처음에 셋을 다 지웠다가 관련 검사 69개가 깨져 되돌렸다.

**사용자 판정(2026-11-17): 지금대로 둔다.** 이 자식 수리는 의식 없이 요청문을 그대로 규정으로 쓴다. 권한 이유는 이렇다. 사용자의 요청을
수리로 판정한 것이 아니라, 이미 목표가 정해진 업무 안에서 실행자가 필요한 구현을 고치는 한 걸음이다. 범위가
요청한 파일로 묶여 있고 끝나면 부모 업무로 돌아오며, 부모 업무의 목표는 그대로다. 사용자가 예외로 둔 "규정에
따라서 하는" 자동 이어가기와 같은 쪽에 가깝다. 다만 이 자식 수리가 엉뚱한 방향으로 가는 일이 기록에 보이면
다시 연다 — 그때는 의식을 새로 부르기보다 1-나의 되돌아보기를 이 턴에도 돌리는 쪽이 싸다.

---

## 3. 세션 리셋

### 3.1 지금 상태

Claude Code 실행자는 에이전트·대화마다 CLI 세션을 이어 쓴다(`--resume`). 세션은 턴을 넘어 자란다. 크기로
세션을 새로 여는 장치는 2026-10-02에 껐다(`8ae58b25` "문맥 압축을 모델 최대 용량에 맞추고 조기 세션 리셋
제거", `backend/providers/cli_provider.py`의 `SESSION_RESET_TOKEN_THRESHOLD = None`). 문맥 상한은 CLI의 자체
압축이 맡는다. 코드(`_should_reset_session`)는 남아 있어 값을 넣으면 다시 돈다.

에피소드 6192(92분, 도구 143회)에서 실행자 입력은 4,179만 토큰이었고 99%가 캐시 읽기였다. 라운드당 평균
40만, 끝날 때 세션은 67만이었다. 그 대화의 다음 턴은 그 크기에서 시작한다.

### 3.2 잰 것

**세션 크기** (`data/claude_code_session_sizes.json`, 508개): 중앙값 9만 1천, 30만 초과 32개, 50만 초과 6개,
최대 67만.

**문맥 크기와 라운드당 모델 시간** (6000번 이후 Claude Code 실행 턴 92개, 턴 시간에서 도구·감독 시간을 뺌):

| 라운드당 문맥 | 턴 수 | 라운드당 모델 시간(중앙) | 라운드당 출력(중앙) |
|---|---|---|---|
| ~10만 | 38 | 4.2초 | 456토큰 |
| 10만~20만 | 35 | 7.3초 | 744토큰 |
| 20만~40만 | 14 | 7.9초 | 824토큰 |
| 40만~ | 5 | 9.5초 | 1,089토큰 |

문맥이 크면 라운드가 느리지만 출력도 같이 길다. 큰 세션은 무거운 과제에서 생기므로, 이 표로는 문맥 크기가
느려지는 원인이라고 말할 수 없다.

**사용 한도** (11-07 ~ 11-17, Claude Code 사용 기록 744건을 5시간 창으로 묶음): 한도 도달 문구가 남은 것은
세 번이다. 도달 직전 5시간의 입력은 1,130만·6,130만·850만 토큰이었다. 한도에 닿지 않은 창 가운데 입력이
1억 1,700만~1억 2,200만인 창이 넷 있다. 이 하네스의 사용량으로는 한도 도달을 설명하지 못한다. 구독은
하네스 밖의 사용(사람이 직접 쓰는 Claude Code 세션 등)과 함께 쓰이고, 그 사용량은 이 기록에 없다.

**압축**: 압축 사건(`context.compacted`)은 전체 기간에 7건이다.

### 3.3 추천: 자동 리셋은 되살리지 않는다

근거가 없다. 큰 세션이 느려지게 하거나 한도를 닿게 한다는 것이 이 기록에서 보이지 않는다. 10월 2일의 결정을
뒤집을 이유도 그 뒤에 생기지 않았다. 크기 문턱은 과제 도중에 세션을 끊어 일을 탈선시킨 적이 있다
(에피소드 718 — `_should_reset_session`의 주석).

대신 권하는 것은 둘이다.

1. **크기를 사실로 보여 준다.** 세션을 새로 여는 수단은 이미 있다. 대화창의 **"새 세션" 버튼**
   (`frontend/src/components/chat/SessionWorkspace.tsx`, 이름은 `frontend/surfaces/shared/conversation.json`)을
   누르면 새 대화 세션이 만들어지고, CLI 세션의 열쇠가 `에이전트@session:<대화 세션 id>`라서
   (`cli_provider._get_session_key`) 실행자의 CLI 세션도 빈 채로 새로 시작한다. 앞의 대화는 히스토리에 제
   CLI 세션과 함께 남는다. 같은 대화를 유지한 채 CLI 세션만 비우는 버튼("Claude Code 새 세션 시작")도
   프런트에 있었지만, 세션 작업대가 들어온 2026-10-15(`b765137a`) 뒤로는 화면에 나온 적이 없는 죽은 코드라
   2026-11-17에 지웠다(버튼·핸들러·프런트 호출 둘). 서버의 주소 둘(`/system-ai/reset-session`,
   `/projects/{id}/agents/{id}/reset-session` → `chat_session_service.reset_cli_session`)은 남아 있고 화면에서
   부르는 곳은 없다. 없는 것은 **크기를 볼 곳**이다.
   사용자는 지금 대화의 세션이 얼마나 큰지 모른 채 이어 쓴다(6192는 첫 라운드 입력이 약 24만 토큰인 세션에서 시작해 67만이 됐다).
   **사용자 결정(2026-11-17): 대화창 상단에 숫자로 보인다.** 보이는 값은 그 대화 세션의 크기(마지막 라운드의
   문맥 토큰, `data/claude_code_session_sizes.json`에 이미 적힌다)다. 문턱도 자동 판단도 넣지 않는다.
   구현하면서 정할 것: 자리(세션 머리줄의 "새 세션" 버튼 곁이 자연스럽다), 표기(예: `24만`), 갱신 시점(턴이
   끝날 때), CLI 세션이 없는 공급자에서는 보이지 않음, 크기를 내려 주는 서버 쪽 통로(세션 목록 응답에 싣거나
   따로 묻거나).
2. **다시 판단할 조건을 적어 둔다.** 아래 둘 중 하나가 보이면 이 절을 다시 연다.
   - 같은 과제를 새 세션과 큰 세션에서 돌렸을 때 결과나 시간이 달라진다. 재는 법: 과제 하나를 정하고, 한
     번은 새 세션에서, 한 번은 50만 이상인 세션에서 돌려 소요·도구 호출 수·결과를 댄다. 과제 내용은 두 번을
     다르게 해야 한다(같은 대화에서 같은 과제를 두 번 주면 기억이 오염된다).
   - CLI의 압축이 과제 도중에 돌아 일을 놓친다(압축 사건 `context.compacted` 직후의 턴이 앞의 일을 다시 하거나
     조건을 잊는다).

하지 말 것: 크기 문턱을 다시 넣는 것, 과제가 바뀌었는지를 경량 모델에게 물어 세션을 끊는 것(같은 날 없앤
규정 계승과 같은 구조다).

### 3.4 구현한 것 (2026-11-17 밤, 다음 세션)

- **자리와 표기**: 대화창 머리줄의 세션 메뉴 맨 앞("히스토리"·"새 세션" 버튼 왼쪽)에 숫자만 보인다. 지역 표기를
  따른다(한국어 `11.7만`, 영어 `116.6K` — `ui.number(…, {notation:'compact'})`). 마우스를 올리면 무엇의 크기인지
  한 줄이 뜬다. 색·문턱·경고는 없다. CLI 세션이 없으면(API 공급자, 턴이 없는 새 세션, 세션 초기화·되감기 직후)
  아무것도 보이지 않는다.
- **통로**: 대화창이 이미 1.2초마다 받는 세션 스냅숏(`GET /chat-sessions/{id}`)에 `context: {tokens, provider}`
  칸을 실었다(`chat_session_service.context_size`). 따로 묻는 주소를 만들지 않았다. 턴이 끝나 크기가 다시
  적히면 다음 스냅숏에서 바뀐다.
- **어느 기록이 지금 것인가**: 한 대화 세션에 열쇠가 여럿 남을 수 있다(도구 정책이 바뀌면 열쇠 끝의 지문이
  바뀐다 — 실측 345개 대화 세션 가운데 10개). 공급자가 크기를 적을 때 대화 세션 곁
  (`conversation_state/<세션>/cli_session.json`)에 "이 대화가 방금 쓴 CLI 세션"의 표식(공급자·열쇠)을 남기고
  (`cli_provider._record_context_size` → `conversation_sessions.note_cli_session`), 읽을 때는 표식이 가리키는
  열쇠가 크기 기록에 그대로 있을 때만 그 값을 쓴다(`cli_sessions.session_context_size`). 세션 초기화나
  되감기로 기록이 지워졌으면 표식이 남아 있어도 옛 크기를 보이지 않는다. 표식이 없는 옛 세션은 크기 기록에서
  같은 대화 세션의 열쇠를 찾아 가장 나중 것을 쓴다. 예행 세션은 세지 않는다. 크기의 정본은 그대로
  `data/<공급자>_session_sizes.json`이다.
- **같이 한 것**: `cli_provider.py`가 1,499줄이어서 세션 저장소(`CliSessionStore`·세션 지우기·크기 읽기)를
  `backend/providers/cli_sessions.py`로 뗐다(재수출로 기존 import 경로 유지).
- 검사: `backend/test_chat_session_service.py` 3개. 화면은 개발 서버를 브라우저로 열어 시스템 AI 대화에서
  `11.7만`(116,643)이 보이는 것을 확인했다. 새 문구 한 줄의 영어·일본어 번역은 개발 서버의 카탈로그 갱신이 넣었다.

---

## 4. `framing_inheritance.py` 모듈 이름

### 4.1 지금 상태

규정 계승은 없어졌는데 모듈 이름은 그대로다(`backend/cognition/framing_inheritance.py`, 205줄). 머리말에 무엇이
없어졌고 무엇이 남았는지 적어 두었다. 남은 것은 서로 다른 세 가지 일이다.

| 남은 것 | 쓰는 곳 |
|---|---|
| 직전 규정의 기록 (`remember`, `_load`, `_save`, `agent_key`, `_age_s`, `_storable`, `STRIP_ALWAYS`, `FOLLOWUP_MAX_AGE_S`) | `agent_pipeline.py`(턴 끝에 적음), `cognitive_consciousness.py`(최근 연구계획 후보), `repair_resume.py`(멈춘 수리 찾기) |
| 수리 재개 판정 (`_judge_relation`, `_prompt`, `_oneshot`, `_RELATION_PROMPT`) | `repair_resume.py`뿐 |
| 위임 완료 통지 판별 (`is_delegation_report`) | `cognitive_consciousness.py`의 무의식 분기뿐 |

### 4.2 추천: 이름만 바꾸지 말고 맡은 일대로 나눈다

1. 수리 재개 판정을 `repair_resume.py`로 옮긴다. 쓰는 곳이 거기뿐이다. 이름은 `judge_resume` 정도로.
2. `is_delegation_report`를 `cognitive_consciousness.py`(분류가 사는 곳)로 옮긴다.
3. 남은 기록 부분의 모듈 이름을 `framing_record.py`로 바꾼다. 상수 `FOLLOWUP_MAX_AGE_S`도 뜻에 맞게
   바꾼다(직전 기록을 최근 것으로 보는 창).
4. 디스크의 저장소 폴더(`data/system_ai_state/framing_inherit/`, 243개 파일)는 옮기지 않는다. 이름을 바꾸면
   기록을 옮기는 절차와 백업이 필요한데 얻는 것이 없다. 모듈 머리말에 폴더 이름이 옛 이름인 이유를 한 줄 적는다.

### 4.3 걸린 곳

- 코드: `cognitive_consciousness.py`, `repair_resume.py`, `agent_pipeline.py`, `base/program_boundary.py`(모듈
  이름을 키로 한 표), `scripts/consciousness_schema_check.py`(소비 파일 목록), `scripts/git-hooks/pre-commit`(정규식).
- 검사 12개 파일. 문자열로 붙잡는 곳이 있다(`monkeypatch.setattr('framing_inheritance.remember', …)`).
  `grep -rn "framing_inheritance" backend/test_*.py`로 전부 찾는다. 검사 파일 이름 둘
  (`test_framing_inheritance.py`, `test_framing_inheritance_2026_10_07.py`)도 내용에 맞게 바꾼다.
- 파생물: `data/bodies/android.engine.json`(폰 엔진 번들 목록)은 손으로 고치지 않고
  `python3 scripts/build_body_bundle.py android`로 다시 만든다. 새 모듈 파일은 `git add`한 뒤 빌드한다.
- 문서: `data/system_docs/architecture.md`·`anatomy.md`의 현재 서술만 고친다. 지난 설계 문서(`docs/*.md`)와
  변경 이력의 옛 이름은 그대로 둔다(그때의 기록이다).

한 커밋으로 하고, 전체 회귀와 빌드 `--check`, 층 검사, 문서 드리프트 검사를 통과시킨다. 동작이 바뀌지 않는
정리이므로 급하지 않다. 2번을 먼저 하면 `repair_resume.py`를 한 번만 건드린다.

### 4.4 구현한 것 (2026-11-17 밤, 다음 세션)

- 기록: `backend/cognition/framing_record.py`(`git mv`). 상수 `FOLLOWUP_MAX_AGE_S` → `RECENT_WINDOW_S`.
  저장소 폴더 `framing_inherit/`는 그대로 두고 머리말에 이유를 적었다.
- 수리 재개 판정: `repair_resume.judge_resume`(옛 `_judge_relation`), `_prompt`·`_oneshot`도 같이 옮겼다.
- 위임 완료 통지 판별: `cognitive_consciousness.is_delegation_report`.
- 걸린 곳: `agent_pipeline.py`, `base/program_boundary.py`, `scripts/consciousness_schema_check.py`,
  `scripts/git-hooks/pre-commit`, 검사 12개 파일. 검사 파일 이름은 `test_framing_record.py`(옛
  `test_framing_inheritance.py`)와 `test_think_always_fresh_framing.py`(옛 `test_framing_inheritance_2026_10_07.py`).
  `data/bodies/android.engine.json`은 빌드로 다시 만들었다. 문서는 `architecture.md`·`anatomy.md`의 현재 서술과
  `decisions.yaml`의 검색어만 고쳤다.

---

## 5. 이 문서가 다루지 않는 것

- 하네스가 자동으로 잇는 수리 턴(재기동 뒤, 검수 지점 복원)에 붙는 고정 지시문(`repair_continuation.resume_context`).
  사용자의 말로 이은 턴에서는 사실 묶음(`state_facts`)으로 바꿨고, 자동 턴은 그대로 두었다. 자동 턴에도 같은
  사실 묶음을 주는 것은 다음에 볼 만하다.
- 키 파일(`.env`, 셸 설정)을 실행자가 직접 읽는 것. 막지 않았다. 하지 않게 하는 것은 판정(`decisions.yaml`)이다.
- `docs/DEEP_EXECUTION_DESIGN_2026_11_15.md` 9절의 나머지 열린 결정(숫자 없는 "심층실행"의 뜻, 단계가 시간으로도
  읽히게 할지, 효과 측정).
