# 커스텀 앱(계기) 만들기·수정 — 리치 React 계기

앱 모드에 **새 앱(계기)을 붙이거나 기존 앱을 고치는** 방법. **만들 때도 고칠 때도 이 문서를 먼저 읽는다.**

## 도구 — 모델 불문 (Claude Code 아니어도 됨)
이 작업은 **어떤 본격 모델이든**(Claude Code·Gemini·기타) 아래 기본 도구만으로 한다. 특정 모델의 네이티브 기능에 의존하지 않는 게 정본이다:
- **파일 읽기/편집/검색/생성**: `[self:read]` · `[self:edit]` · `[self:write]` · `[self:grep]` · `[self:file_find]` (execute_ibl). **소스 파일 편집은 절대경로(또는 리포 상대경로)로 — `project_id` 불필요.**
- **빌드·타입체크·검증 실행**: `run_command` 도구 (예: `run_command("cd frontend && npx tsc -b")`). system_essentials가 모든 실행 에이전트에 주는 기본 도구.
- **가이드 읽기**: `read_guide`.

> Claude Code 본격 모델은 네이티브 Read/Edit/Bash도 갖지만 **필수가 아니다.** 위 IBL·`run_command` 어휘가 모델 독립적인 정본 경로다. (네이티브 Edit은 사전 Read를 요구해 막히기도 한다 — 막히면 그냥 `[self:edit]`를 쓴다.)

### 속도 = 도구 호출 **왕복 횟수** (앱 개발 특유)

느린 건 편집 도구 *자체*가 아니라 **왕복 횟수**다 — 매 도구 호출이 한 번의 LLM 턴이라(큰 시스템 프롬프트 재소비), 편집 30번이면 그게 곧 시간이다. `[self:edit]` 한 번과 셸 `sed` 한 번은 별 차이 없다. 줄이는 법(효과 큰 순):
1. **인라인 기본(철칙1)** — 별도 창의 6파일 배선(main.js/preload/types/App.tsx)이 통째로 사라진다. 커스텀 계기는 보통 컴포넌트 1 + ActionDesktop 2줄이면 끝. **가장 큰 절감.**
2. **새 파일은 한 번에** `[self:write]` 로 통째 작성(조각 편집으로 쌓지 말 것).
3. **탐색은 `read_guide("코드 구조")` 한 번**(grep 열 번 말고).
4. **기존 파일 여러 곳을 고칠 땐 배치** — `run_command` 한 방에 여러 치환을 몰아 왕복을 줄인다(앱 개발 같은 기계적 편집에 유효). 예:
   ```
   run_command("cd repo && python3 - <<'EOF'\nimport pathlib\n# 파일별 (old,new) 치환을 한 번에\nEOF")
   ```
   단 **배치는 per-edit 확인이 없다** → 끝나고 반드시 `run_command("... tsc -b")` 로 검증. 확신 없는 수술 편집은 `[self:edit]`(왕복당 "Successfully edited" 확인)로.

## 만드는 갈래 판별 (신규일 때)
두 갈래가 있고 **먼저 어느 갈래인지부터 정한다.**

| 갈래 | 언제 | 어디서 | 가이드 |
|---|---|---|---|
| **선언형 `app:` 블록** | 데이터-모양 앱(목록·지표·폼·차트) — 뷰 어휘 14종으로 표현 가능 | src 액션에 `app:` 블록 한 개 | `new_action_checklist.md` "앱 표면 노출" 절 |
| **커스텀 React 계기(escape hatch)** | 뷰 어휘를 넘는 것 — 자유 편집 캔버스, 그리기, 채팅, 특수 인터랙션 (예: 빈노트·신문·길찾기) | `frontend/src/components/*.tsx` 컴포넌트 | **이 문서** |

> 판별: 만들려는 화면을 `metric/kv/card_list/image_grid/form/thread/map/calendar/...` 조합으로 그릴 수 있으면 **선언형이 먼저다**(표면별 코드 0줄, 원격·폰 자동 파리티). 안 되면 이 문서의 커스텀 계기.

---

## 철칙 0 — 능력은 **기존 어휘 조합**, 계기는 **표현만**

계기를 짜기 전에 **그 분야의 IBL 어휘가 이미 있는지 먼저 찾는다.** 새 계기는 대개 *기존 어휘 조합 + 약간의 표현 코드*다 (NewspaperInstrument 주석: **"앱 = 어휘 조합 + 약간의 코딩"**). 컴포넌트는 **표현(무엇을 어떻게 보여줄까)** 만 맡고, **능력(무엇을 하는가)은 어휘**가 맡는다.

**먼저 조사 (셋 다):**
1. **해마 연상** — 하려는 일을 자연어로 떠올려 이미 그 액션이 있는지. (예: "문서 저장", "뉴스 검색", "주가", "날씨")
2. **어휘 grep** — `[self:grep]{path: "data", pattern: "관련어"}` 또는 `grep -rn` 로 `data/ibl_nodes.yaml`·패키지 `ibl_actions.yaml` 훑기.
3. **기존 계기 모방** — 가장 비슷한 계기가 어떤 어휘를 부르는지.

**살아있는 선례 (표현은 커스텀, 능력은 기존 어휘):**
- 빈노트(문서) = `[self:write]` · `[self:read]` · `[self:file_find]` · `[self:delete]` (파일 어휘 그대로)
- 신문 = `[sense:search_gnews]` 를 키워드마다 팬아웃
- 길찾기 = `[sense:navigate_route]` · `[sense:cctv]`
- 정기보고 = `[self:file_find]`→`[self:read]` + 작성은 `[others:delegate]{scope:system}`

**어휘가 없으면?** 그 능력이 IBL 액션 기준(조합성·빈도·실시간성·외부 접근)을 만족하면 **먼저 `new_action_checklist.md` 로 액션을 만들고**, 그 다음 이 계기(표현)를 붙인다. **능력 로직을 컴포넌트에 하드코딩하지 말 것** — 그러면 재사용도, 모델 불문도, 조합(`>>`)도 안 되고, 다른 앱·자율주행·조종실이 같은 능력을 못 쓴다. (IBL 명명 헌법: *특수보다 보편 우선, 중복 금지*.)

> 한 줄 요약: **표현은 컴포넌트, 능력은 어휘.** 앱을 짜다 "여기서 데이터를 가져와야 하는데" 싶으면 fetch 를 새로 짜기 전에 그 일을 하는 **액션이 이미 있는지부터** 본다.

---

## 철칙 1 — 기본은 **인라인**(별도 창 아님)

커스텀 계기는 **앱 모드 안의 인라인 계기(`el`)** 로 만든다. 그러면 `ActionDesktop`이 상단에 **`‹ 뒤로` BackBar**를 자동으로 붙여줘 사용자가 빠져나올 수 있다.

**별도 Electron 창은 갇힘의 원인이다** — 별도 창엔 BackBar가 없어 사용자가 나갈 길을 잃는다(실제 사고 이력). 별도 창은 **다음일 때만**:
- 지도·네이티브 OS 창·파일 피커처럼 렌더 어휘·메인 창 밖의 것
- 강의 워크스페이스처럼 진짜로 자기 OS 창이 필요한 3패널급 대형 도구

애매하면 **인라인**. 편집기·뷰어·대화형은 전부 인라인으로 된다.

---

## 인라인 계기 만들기 (표준 경로 — 이것만 하면 끝)

기존 인라인 계기를 **모방하라**: `NewspaperInstrument.tsx`(뷰어), `DirectionsInstrument.tsx`(입력+결과), `BinNote.tsx`(편집기+AI채팅).

### 1) 컴포넌트 작성 — `frontend/src/components/MyThing.tsx`
```tsx
// 루트는 부모(flex-1 min-h-0)를 꽉 채우게 h-full w-full flex flex-col.
export function MyThing() {
  return (
    <div className="h-full w-full flex flex-col bg-[#F5F1EB] text-stone-800">
      {/* 헤더 / 본문 / ... 자유롭게 */}
    </div>
  );
}
```

### 2) `ActionDesktop.tsx`에 등록 (2곳)
`STATIC_DOMAINS` 배열에 도메인 추가 — 인라인은 `el`:
```tsx
import { MyThing } from './MyThing';   // 파일 상단
// ...
const STATIC_DOMAINS: Domain[] = [
  // ...
  {
    id: 'mything', icon: '🧩', label: '내 앱',
    instruments: [
      { id: 'mything', icon: '🧩', label: '내 앱', el: <MyThing /> },  // el = 인라인
    ],
  },
];
```
그리고 `HOME_ORDER` 배열에 `'mything'` 을 추가(홈 그리드 기본 자리).

**이게 전부다.** `ActionDesktop`이 계기를 열 때 `<BackBar/> + <MyThing/>`으로 감싼다(레벨2, 코드 327~332). App.tsx·main.js·preload 배선 **불필요**. 앱 홈에 아이콘이 자동 등장하고, 방금 추가된 **런처 승격**(아이콘 우클릭 → "런처에 승격")으로 상단 바에도 올릴 수 있다.

---

## 철칙 2 — 앱 모드에서 `[self:*]` 는 **`project_id: '앱모드'` 필수**

계기에서 IBL로 저장/읽기/파일탐색(`[self:write/read/file_find/...]`)을 호출할 때, **반드시 `project_id: '앱모드'`** 를 함께 보낸다. 앱 모드 표면엔 활성 프로젝트가 없어서, 안 주면 상대경로 해소가 실패한다:

> `"활성 프로젝트 경로를 확보할 수 없어 도구를 실행할 수 없습니다: write_file..."` ← `project_id` 누락 시 나는 에러(실제 사고 이력).

**복붙하지 말고 공용 헬퍼를 import 하라** — `project_id:'앱모드'` 가 헬퍼 안에 박혀 있어 **실수 자체가 불가능**하다:
```tsx
import { iblExecuteApp } from '../lib/instrument';   // project_id:'앱모드' 내장 + 견고한 응답 언랩

const r = await iblExecuteApp(`[self:write]{path: ${JSON.stringify(`outputs/mything/${fname}`)}, content: ${JSON.stringify(text)}}`);
// r 은 언랩된 payload. 단일 통화 = {items:[{title,meta,url,...}]} (예: file_find)
```
- 헬퍼 정본: `frontend/src/lib/instrument.ts` (`iblExecuteApp`·`askSystemAI`·`APP_PROJECT_ID`). **새 계기는 여기서 import**, 손수 fetch 재작성 금지.
- 상대경로는 이 컨텍스트에서 `projects/앱모드/<경로>` 로 일관 해소된다(예: `outputs/mything/*.md`).
- **응답 shape은 추측하지 말고** 라이브 `/ibl/execute`로 먼저 확인하고 파싱한다. 단일 통화 = `{items: [{title, meta, url, ...}]}`.

---

## AI를 계기에 붙이기 — **AI 호출도 어휘다** (철칙0)

AI 호출은 raw fetch 로 새로 짜지 말고 **어휘로** 부른다. 세 모양이 있고 앱마다 맞는 걸 고른다:

**① 원샷 질문 (기본) — 지금 답을 받는다.** `[self:ask]` — 도구 없이 가볍고 **빠르다**. 요약·개선·설명·번역·답변.
- 선언형 앱(코드 0): 버튼/폼 `action:` 에 그대로.
  ```yaml
  action: '[self:ask]{prompt: "이 표를 세 줄로 요약해줘"}'   # 파이프도 됨: [sense:...]{} >> [self:ask]{prompt: "요약"}
  view: [{ type: kv, from: items }]    # 결과 {result} 렌더
  ```
- 커스텀 앱: `askAI` 헬퍼.
  ```tsx
  import { askAI } from '../lib/instrument';
  const reply = await askAI('더 간결하게 고쳐줘', content);   // (지시, 대상텍스트) → 답 텍스트
  ```

**② 작업 위임 — 가서 이 일을 해 → 산출물 생성.** "보고서 써줘"처럼 결과가 파일/시스템에 남는 것. 에이전트(도구·다단계), 비동기, **코드 0**:
```
[others:delegate]{scope: "system", message: "AI 동향 보고서 써줘", from_agent: "내앱"}
```
선언형 버튼 `action:` 에 넣고(정기보고 선례 `data/instruments/report.yaml`), 산출물은 나중에 `[self:file_find]`/`[self:read]` 로 읽어 보여준다.

**③ 무거운 동기 대화 (드묾)** — 지금 답이 필요한데 **도구까지** 써야 할 때(예: "이 글 PDF로 저장하고 경로 알려줘"). `askSystemAI` — 전체 인지 파이프라인이라 느리다(수십 초~분). ①·②로 안 될 때만.

> 판별: **가볍게 지금 답** = ① `askAI`/`[self:ask]`(기본) · **가서 만들어 둬** = ② `[others:delegate]` · **도구+지금 답** = ③ `askSystemAI`. 대부분 ①로 충분하다.

---

## 별도 창 경로 (정말 필요할 때만)

지도·네이티브급이라 별도 창이 불가피하면 이 배선이 필요하다(전부 해야 함):
1. `frontend/electron/main.js` — 창 변수 + `createXWindow()`(hiddenInset·`loadURL('.../#/x')`) + `ipcMain.handle('open-x-window', ...)`
2. `frontend/electron/preload.js` — `openXWindow: () => ipcRenderer.invoke('open-x-window')`
3. `frontend/src/types/index.ts` — `ElectronAPI` 에 `openXWindow` 선언
4. `frontend/src/App.tsx` — `#/x` 해시 감지 → state → 렌더 분기 (전체 화면)
5. `ActionDesktop.tsx` — 도메인을 `onOpen: () => window.electron?.openXWindow?.()` (el 아님)
6. **★자체 나가기 UI 필수** — 별도 창은 BackBar가 없다. 창 안에 명시적 닫기(또는 OS 트래픽라이트 확인)를 반드시 둔다. 안 두면 사용자가 갇힌다.

> main.js/preload 변경은 **Electron 메인 프로세스라 HMR 안 됨 → 앱 완전 재시작 필요**. 인라인 경로는 이 6단계가 전부 불필요하다(그래서 기본).

---

## 기존 앱 수정하기

이미 있는 계기를 고칠 때도(버그·기능 추가·UX 변경) 위 **철칙과 도구**가 그대로 적용된다. 순서:

1. **찾기 (탐색 먼저, 바닥부터 grep 금지)** — `read_guide("코드 구조")`(codebase_map)로 위치를 잡고, `[self:grep]`로 해당 계기를 짚는다. 예: 라벨/아이콘/기능 문자열로 `[self:grep]{path: "frontend/src/components", pattern: "빈노트|BinNote"}`. 계기 컴포넌트는 `frontend/src/components/*.tsx`, 앱 모드 등록은 `ActionDesktop.tsx`(STATIC_DOMAINS·HOME_ORDER·OVERRIDES).
2. **읽기** — 고치기 전 `[self:read]`로 대상 파일을 통째로 읽어 현재 구조를 파악한다(추측 편집 금지). 어떤 표면에 걸쳐 있는지도 확인: 순수 프론트 컴포넌트면 그 `.tsx`만, 별도 창이면 main.js/preload/App.tsx까지.
3. **고치기** — `[self:edit]{path: "<절대경로>", old_string: "...", new_string: "..."}`. old_string은 파일에서 **유일**하게 매칭되도록 충분한 맥락을 포함한다. 앱이 IBL을 호출하는 코드면 **철칙2(`project_id: '앱모드'`)** 를 깨지 않았는지 확인.
4. **별도 창 → 인라인 전환 같은 구조 변경**이면, 죽는 배관(main.js 창 생성·ipc·preload·types·App.tsx 분기)을 **함께 걷어낸다** — 좀비 코드 방지. `[self:grep]`로 잔여 참조 0을 확인.
5. **검증(아래)** — 고친 뒤 반드시 `run_command`로 `tsc -b` 재실행 + 라이브 스모크.

> 수정도 **인라인이 기본**이라는 철칙은 같다. 사용자가 "메인 창 안에서 열리게", "뒤로가기 되게"를 원하면 별도 창 → 인라인 `el` 전환이 정답이다.

---

## 검증 (모델 불문 — `run_command` 로)

- **선언형 `app:` 블록을 만들었거나 고쳤으면 — 완료 조건은 verify 게이트 GREEN/SKIP:**
  `run_command("python3 scripts/build_ibl_nodes.py --check")` (뷰-어휘·뷰-렌더러·앱-템플릿 param 가드 통과) **+**
  `run_command("python3 scripts/ibl_health_check.py --instrument <계기id>")`.
  후자는 그 앱의 액션을 앱모드로 **1회 실제 실행**해 view 가 통화를 받는지 단언한다(GoalEval 원장만 보던 공백을 메움).
  · GREEN=통화 확인 / SKIP=read-only 게이트·입력 필요(정상) / **YELLOW·RED=실패**(통화 미부착 — op·view.from 확인). YELLOW/RED면 미완성.
  · 한계: currency GREEN 은 "액션이 통화를 냈다"까지. override 렌더 컴포넌트가 실제로 그리는지·상호작용은 아래 라이브 스모크로.
- `run_command("cd frontend && npx tsc -b")` — **`tsc -b`** 로(‑‑noEmit 아님). 미사용 import·var까지 잡는다. **커스텀 React(Path B) 계기는 verify 게이트가 N_A 라 tsc + 라이브 스모크가 유일한 안전망** — 더 꼼꼼히.
- 별도 창 경로를 건드렸으면 `run_command("cd frontend && node --check electron/main.js electron/preload.js")`.
- 라이브: 앱 모드에서 아이콘 열기 → **뒤로 나가지는지** → 저장/불러오기/AI 왕복. 인라인이면 HMR 즉시 반영, 별도 창·main.js 건드렸으면 재시작 후.

---

## 자주 하는 실수 (실제 사고 이력)

1. **능력을 컴포넌트에 하드코딩** (철칙0 위반) — 그 분야 어휘를 안 찾고 fetch·로직을 새로 짬. 먼저 기존 액션을 찾아 조합하고, 없으면 액션부터 만든다. 표현만 컴포넌트, 능력은 어휘.
2. **별도 창으로 만들어 갇힘** — 기본은 인라인. 별도 창은 BackBar가 없어 나갈 길이 없다.
3. **`project_id: '앱모드'` 누락** — 앱 모드 `[self:*]` 저장/읽기가 "활성 프로젝트 경로 확보 불가"로 실패. `iblExecuteApp` 헬퍼를 import 하면 구조적으로 방지(복붙 말 것).
4. **응답 shape 추측** — 라이브 `/ibl/execute`로 확인 후 파싱. items 통화 관습(`{items:[{title,meta,url}]}`).
5. **선언형으로 될 걸 커스텀으로** — 데이터-모양이면 `app:` 블록이 먼저(원격·폰 파리티 공짜).
6. **탐색을 바닥부터** — 저술 전 `codebase_map` 가이드와 가장 비슷한 기존 계기(Newspaper/Directions/BinNote)를 먼저 읽어 모방한다.

## 관련
- `new_action_checklist.md` — IBL 액션 저술 + 선언형 `app:` 블록
- `codebase_map.md` — 파일 위치(ActionDesktop/GenericInstrument/App/main.js)
- `open_window.md` — 기존 6개 메인 창 여는 런타임 사용법(저술 아님)
