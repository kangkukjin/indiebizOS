# 코딩 앱 = 코딩 프로젝트를 문서처럼

작성일: 2026-10-07. 상태: **설계(미착수)** — §8 판정 뒤 §7 순서대로 집행한다. 독자: 이 일을 이어받는 구현자.
상위 계획: [공통 기반 위의 앱 구성](APP_COMPOSITION_ON_IBL_PLAN_2026_10_05.md) §6-4~5 의 코딩 몫.
선행 사례: [문서 앱 = 빈노트의 얼굴 + 형식별 엔진](DOCUMENT_APP_ON_BINNOTE_PLAN_2026_10_05.md) · [스프레드시트 앱](SPREADSHEET_APP_ON_IBL_PLAN_2026_10_07.md) — 같은 틀.
옛 설계: [코딩 앱 설계 2026-10-02](CODING_APP_DESIGN_2026_10_02.md) — 실행자 계약(모델↔실행자 구분·코딩 프로필·쓰기 경계)과 자기수리 연결 절은 유효. "diff 중심 화면·과제별 worktree·검토 묶음 승인" 은 이 문서가 대체한다(§8 판정 ②).

사용자 명제(2026-10-07): *이것은 하네스의 코딩 앱이다 — 기본적으로 내가 코딩을 하는 것이 아니다. 그래서 (1) 프로젝트 관리가 중요하다: 프로젝트마다 코드를 다른 폴더에 분리하고 지금 어떤 코딩 프로젝트들이 있는지 보기 쉽게. (2) 프로젝트에 들어가면 **코딩 목표 문서**를 편집·저장하는 것이 중요하다 — 내가 원하는 것을 말하면 AI 가 목표 문서로 정리하고 그것을 기반으로 코딩한다. (3) 프로젝트 안의 파일을 눌러 보거나 편집할 수 있어야 한다 — 기본은 코드를 읽지 않지만 원하면. (4) 만든 코드를 실행하고 결과를 보는 곳. 화면은 지저분하면 안 된다. 코딩 프로젝트를 문서 앱의 문서처럼: 첫 화면은 프로젝트 목록(아이콘/리스트), 열면 목표 문서 편집 화면, 상단에 메신저의 이웃 레벨 단추처럼 탭 셋 — 목표 문서 · 코드 파일 · 실행.*

같은 날 먼저 낸 "하네스 3열(과제 목록·대화/변경 탭·과제 패널)" 안은 **기각**됐다 — 지저분하고, 사용자가 코딩하는 사람의 화면이지 맡기는 사람의 화면이 아니다. 조사한 하네스 13종(Claude Code·Codex·Cursor·Copilot·Cline·Zed·Aider·OpenCode·Conductor·Devin·Jules·Warp)에서 가져갈 것은 둘뿐이다: **프로젝트(세션) 목록이 첫 화면**(Devin·Jules·Codex 의 작업 목록) · **계획 문서를 먼저 합의하고 코딩**(Jules 계획 승인·Claude Code 계획 모드). diff 패널·도구 카드·권한 모드·터미널은 가져가지 않는다.

## 0 출발점

| | 지금 코딩 앱 (`CodingWorkspace.tsx`, 2026-10-02) | 목표 |
| --- | --- | --- |
| 첫 화면 | 저장소 경로 입력 + 과제 textarea + 파일 목록 + diff + 검증 + 대화가 한 화면 | **프로젝트 카드 목록**(아이콘·이름·한 줄 설명·상태·마지막 활동) + 새 프로젝트 |
| 단위 | 저장소 → 과제(worktree) → 실행 → 검토 묶음 → 승인 → 커밋 | **프로젝트 = 폴더 하나**(`outputs/coding/<이름>/`). 그 안에 목표 문서 `목표.md` + 코드 |
| 중심 | diff | **목표 문서** — AI 와 대화하며 다듬고, "목표대로 코딩" 이 AI 를 시작 |
| 코드 | textarea 편집 | 코드 파일 탭 — 트리에서 누르면 본다, 원하면 편집 |
| 실행 | 검증 명령 한 줄 + 사건 목록 | 실행 탭 — 실행 단추·출력·(웹이면) 미리보기 |
| 구성 | React 전용 + HTTP 10경로 | 선언 `coding.yaml` + `engine` 뷰 + `[self:workspace]`·`[others:delegate]`·`[self:task]` — **새 낱말 0** |

몸은 대부분 있다: `[self:workspace]` code 어댑터(open/read{files|path|diff}/propose/apply/save), `coding_runs`(실행자 Codex 네이티브·API 모델, 샌드박스 명령 실행, 사건 원장·취소·에피소드), 문서 엔진의 원문 캔버스 + `ai_dock`(목표 문서 편집이 그대로 이것), 위임 접수증(`[others:delegate]`→`[self:task]`). 없는 것은 **프로젝트라는 단위**와 **세 탭의 얼굴**이다.

## 1 목표 형태 — 네 화면

목업: [`mockups/coding_app_mockup_2026_10_07.html`](mockups/coding_app_mockup_2026_10_07.html)(탭이 실제로 바뀐다) + 스크린샷 4장 `…_1_projects.jpg` `…_2_goal.jpg` `…_3_files.jpg` `…_4_run.jpg`(1440×900).

### 1-1 첫 화면 — 프로젝트 목록
```
💻 코딩   [프로젝트 검색]                         기존 폴더 가져오기  [＋ 새 프로젝트]
outputs/coding — 프로젝트마다 폴더 하나
┌ ＋ 새 프로젝트 ┐ ┌ 📈 kospi-board ──────┐ ┌ 🧾 가계부-정리 ───────┐ ┌ 🛒 content-shop ─┐
│               │ │ 코스피 종목 현황판… │ │ 은행 CSV 를 읽어…    │ │ 콘텐츠 쇼핑몰…  │
│               │ │ ● AI 작업 중 · 2분 전│ │ ● 실행 중 · 어제     │ │ 5일 전          │
```
카드 = 아이콘(목표 문서 머리의 이모지, 없으면 💻)·이름(폴더명)·한 줄(목표 문서 "무엇을 만드나" 첫 문장)·상태 칩(AI 작업 중 / 실행 중 / 없음)·마지막 활동. 누르면 프로젝트 화면. 카드 아니면 리스트(토글) — 문서 앱 문서함과 같은 밀도.

### 1-2 프로젝트 화면 — 상단 탭 셋
```
← 프로젝트  📈 kospi-board        [ 목표 문서 │ 코드 파일 │ 실행 ]        ● AI 작업 중 · 3/5  [목표대로 코딩]  ⚙
```
탭은 메신저의 이웃 레벨 단추와 같은 분절 단추. 오른쪽에 AI 상태 칩(진행 n/m, 누르면 진행 기록으로)과 **목표대로 코딩** 한 단추, ⚙(이름 바꾸기·폴더 열기·실행 명령·되돌리기·삭제).

- **목표 문서 탭(기본)** — 문서 앱의 원문 캔버스 그대로(`목표.md`, 마크다운). 아래 AI 한 줄: 선택이 있으면 선택, 없으면 문서 전체를 지시대로 다듬어 **제안 → 문서에 반영/다시/닫기**. "로그인 기능 넣고 싶어" 라고 말하면 AI 가 목표 문서의 문장으로 정리해 준다. 문서 틀(새 프로젝트가 만든다): `무엇을 만드나 / 꼭 되어야 하는 것 / 안 해도 되는 것 / 실행 방법 / 진행 기록`. **진행 기록**은 AI 가 코딩을 끝낼 때마다 한 줄씩 덧붙인다(무엇을 했고 무엇이 남았는지) — 사용자는 코드를 읽지 않고도 여기서 안다.
- **코드 파일 탭** — 왼쪽 파일 트리(AI 가 방금 만든/고친 파일은 ● 표시), 오른쪽 원문(줄 번호, 읽기 전용). `편집` 을 누르면 같은 캔버스가 편집 모드(Ctrl+S 저장), `이전 기록 보기`(이 파일의 지난 판본), `편집기로 열기`(바깥 편집기). 트리의 `목표.md` 도 여기 보인다(한 폴더가 전부).
- **실행 탭** — 실행 명령(목표 문서 "실행 방법" 절 또는 ⚙ 에서) `[▶ 실행] [■ 중지]` 상태 칩(실행 중·경과 / 마지막 실행 성공·실패), 왼쪽 출력(검은 바탕), 오른쪽 미리보기(실행 방법에 URL 이 있으면 iframe, 없으면 출력만 전체 폭). 서버형 실행은 중지할 때까지 살아 있다.
- 원격·폰: 1차는 첫 화면 + 목표 문서 읽기/AI 한 줄 + 진행 기록(문서 앱의 열람 강등과 같은 조건). 코드 파일·실행은 데스크탑.

없는 것(일부러): diff 패널, 도구 호출 카드, 권한 모드, 터미널, 검토 묶음·승인 단추, 커밋 메시지. AI 가 한 일은 **진행 기록 + 되돌리기**(⚙ → "이 작업 전으로")로 충분하다.

## 2 프로젝트 = 폴더 하나

- 자리: `outputs/coding/<이름>/`(기본 폴더 — 문서 앱 `outputs/binnote`, 시트 `outputs/sheets` 와 같은 결). "기존 폴더 가져오기" 는 다른 자리의 git 폴더(예: `outputs/web-projects/kospi-board`)를 **옮기지 않고 등록**한다(프로젝트 원장 `data/coding/projects.json` 에 경로만).
- 폴더 안: `목표.md`(필수 — 이것이 프로젝트의 정체) + 코드 + `.git`(앱이 조용히 `git init`; 사용자에게 git 은 보이지 않는다).
- **기록 = 커밋.** AI 코딩 한 번이 끝나면 앱이 그 변경을 한 묶음으로 각인한다(`[self:workspace]{op:"save", message: <지시 요약>}` — 지금 CodeAdapter.save 의 "검토 묶음 고정·승인·경로 한정 커밋" 을 **자동**으로, 사람 승인 단추 없이). 사용자가 코드 파일 탭에서 직접 편집·저장해도 같은 길. 되돌리기 = `versions` → `restore{revision}`(⚙ "이 작업 전으로", 코드 파일 탭 "이전 기록 보기"). worktree 는 쓰지 않는다 — 프로젝트 폴더가 곧 작업 공간(사용자는 동시에 코딩하지 않고, 병렬은 프로젝트 단위).
- 자기 저장소(indiebizOS)는 프로젝트로 등록 거절(이유 표시). 자기수리는 REPAIR/RED 경로 — 옛 설계 그대로, 후속.

## 3 몸 — IBL 구성 (새 낱말 0)

### 3-1 계기 선언 초안

```yaml
# 코딩 앱 — 코딩 프로젝트를 문서처럼 (docs/CODING_APP_ON_IBL_PLAN_2026_10_07.md). 어휘 없는 순수 매니페스트.
instrument: coding
edition: 2
icon: 💻
name: 코딩
order: 14

modes:
  # ── 첫 화면: 프로젝트 카드 목록. 누르면 그 프로젝트를 열어 세 탭 엔진이 선다. ──
  - name: 프로젝트
    auto_run: true
    action: '[self:workspace]{op: "read", kind: "code", selector: {projects: true}}'   # 등록 원장 + outputs/coding 폴더 → 카드 행(name·icon·summary·status·mtime·path). 틈 §6-2
    view:
      - type: card_list
        from: items
        title: '{name}'
        subtitle: '{summary}'
        badge: '{status}'
        item_click:
          action: '[self:workspace]{op: "open", path: $item.path}'
          view:
            - &project
              type: engine                      # kind=code → 세 탭 엔진(목표 문서·코드 파일·실행). 틈 §6-1
              ref: '{resource}'
              'on': {selection: keep, saved: refresh}
              ai_dock:                          # 목표 문서 탭의 AI 한 줄 — 문서 앱과 같은 낱말·같은 흐름
                action: '[self:ask]{prompt: $dock, context: $text, system: "너는 코딩 목표 문서의 편집자다. context 는 목표 문서(선택 부분 또는 전체)다. 사용자의 말을 목표 문서의 문장으로 정리해, 설명 없이 고친 본문만 답한다. 코드는 쓰지 않는다."}'

  - name: 새 프로젝트
    run_label: 만들기
    inputs:
      - {key: name, type: text, required: true, placeholder: "프로젝트 이름 (폴더 이름이 된다)"}
      - {key: wish, type: textarea, required: true, placeholder: "무엇을 만들고 싶은지 — 말하듯이"}
    # 폴더 + 목표 문서 틀을 만들고, 사용자의 말을 AI 가 목표 문서로 정리해 넣은 뒤 연다. 같은 이름이 있으면 멈춘다.
    action: |
      $folder = f"outputs/coding/${name}"
      $있음 = [self:file_find]{pattern: "목표.md", path: $folder}
      [if: len($있음.items) > 0] { return {error: f"이미 있는 프로젝트입니다: ${name}"} }
      $초안 = [self:ask]{prompt: $wish, system: "사용자의 바람을 코딩 목표 문서(마크다운)로 정리한다. 절: '# <이름> — 코딩 목표', '## 무엇을 만드나', '## 꼭 되어야 하는 것'(목록), '## 안 해도 되는 것', '## 실행 방법'(모르면 '정해지지 않음'), '## 진행 기록'(빈 채로). 설명 없이 문서만."}
      $쓴 = [self:write]{path: f"${folder}/목표.md", content: $초안.text}
      [self:workspace]{op: "open", path: $folder}
    view:
      - *project

  - name: 기존 폴더 가져오기
    run_label: 가져오기
    inputs:
      - {key: path, type: text, browse: "outputs/coding", browse_kind: folder, required: true, placeholder: "코드가 있는 폴더 (git 이 아니어도 된다)"}
    # 목표.md 가 없으면 코드 구조를 읽어 AI 가 초안을 만든다(틈 §6-3). 폴더는 옮기지 않고 등록만.
    action: '[self:workspace]{op: "open", path: $path, kind: "code", register: true}'
    view:
      - *project
```

### 3-2 엔진 안의 단추 = 기존 낱말

| 화면 조작 | 낱말 |
| --- | --- |
| 목표 문서 캔버스 열기·저장·버전 | 프로젝트 자료 안의 `목표.md` 를 **문서 자료**로 `open` → 문서 엔진 그대로(원문 캔버스·자동 초안·Ctrl+S·버전). 프로젝트 자료와 문서 자료는 다른 두 자료(같은 폴더). |
| AI 한 줄(목표 문서) | 선언의 `ai_dock` — `[self:ask]`(경량 원샷). 반영은 사람이 누른다. |
| **목표대로 코딩** | `[others:delegate]{scope:"system", role:"coding", mode:"async", message:"목표 문서대로 구현한다. 끝나면 진행 기록에 한 줄.", context:{resource:$resource}}` → 접수증. 상단 칩 = `[self:task]{op:"status"}`(진행 n/m 은 접수증 progress), 중지 = `op:"cancel"`. 끝나면 `saved` 이벤트로 트리·목표 문서 새로 고침. |
| 코드 파일 탭 트리·원문 | `read{selector:{files:true}}` · `read{selector:{path}}`. 편집 저장 = `propose{selector:{path}, replacement}` → `apply` → 자동 각인 `save{message:"직접 편집: <path>"}`. |
| 이전 기록 보기 / 이 작업 전으로 | `versions` → `restore{revision}`(파일 하나 또는 전체 — 틈 §6-4). |
| 실행 | `[others:delegate]{scope:"system", role:"coding", context:{resource, command:$run, serve:true}}` — 실행자 없이 명령만 도는 실행(지금 `coding_runs` 의 command 실행 + 샌드박스). 접수증으로 출력 스트림·중지. URL 이 있으면 미리보기 iframe. |
| 기존 폴더 가져오기 초안 | `read{selector:{files:true}}` → `[self:ask]`(파일 목록·README 로 목표 초안) → `[self:write]` — 엔진이 처음 열 때 `목표.md` 가 없으면 한 번. |

### 3-3 실행자(AI 코딩) — 위임 한 문장

`role:"coding"` + `context.resource` 가 있는 위임은 몸이 **코딩 프로필**로 실행자를 띄운다(옛 설계 그대로: 네이티브 도구 허용·IBL 선택·MCP 브리지 없음·cwd = 프로젝트 폴더·샌드박스 = 프로젝트 폴더만 쓰기). 실행자는 ⚙ 설정(기본 = 준비된 것 중 첫째): **번들 Claude Code**(2.1.289 설치됨 — 지금 `choices()` 에 없어 추가) / Codex(바이너리 PATH 밖 — 실측) / API 모델. 실행자의 프롬프트는 목표 문서 전체 + "진행 기록에 한 줄 덧붙이고, 실행 방법 절이 비었으면 채워라". 끝나면 몸이 각인(§2). 큐는 **프로젝트 단위**(프로젝트당 활성 실행 1, 프로젝트끼리 병렬 — 시스템 AI 전역 순차 큐에 서지 않는다, §8 판정 ③). 도중에 사용자가 또 말하면 "다음 지시로 대기"(steering 은 후속).

## 4 기능 — 1차와 후속

| 1차 | 후속 |
| --- | --- |
| 프로젝트 카드/리스트 첫 화면·검색·새 프로젝트·기존 폴더 가져오기 | 프로젝트 보관·태그·폰에서 새 프로젝트 |
| 목표 문서 캔버스 + AI 한 줄 + 문서 틀 + 진행 기록 | 목표 문서에서 할 일 체크박스 자동 갱신 |
| 목표대로 코딩(위임·접수증·진행 칩·중지) + 자동 각인 + 되돌리기 | 도중 지시(steering), 실행자 둘 경주 |
| 코드 파일 탭(트리·원문·편집·이전 기록·편집기로 열기) | 변경 비교(diff) 보기 — 원하는 사람만 ⚙ 에서 |
| 실행 탭(명령·출력·중지·미리보기 iframe) | 실행 결과를 AI 에게 바로("이 오류 고쳐") 한 단추 — 사실 목표 문서 AI 한 줄에 출력을 붙이면 되므로 1차 끝에 넣을 수도 |
| 실행자: 번들 Claude Code·Codex·API 모델, 준비 표시 | 자기수리(REPAIR/RED), git push·PR(낱말 없음 — 바깥 도구) |
| 원격·폰: 첫 화면 + 목표 문서 열람·AI 한 줄 | 폰에서 실행·출력 |

## 5 지저분하지 않게 — 규칙

1. 한 화면에 패널은 둘까지(트리+원문, 출력+미리보기). 세 탭 밖의 상설 패널 없음.
2. 상단 단추는 넷(탭 셋 + 목표대로 코딩) + 상태 칩 하나 + ⚙. 나머지는 ⚙ 안.
3. 죽은 단추를 그리지 않는다(미리보기는 URL 이 있을 때만, 중지는 실행 중일 때만, 목표대로 코딩은 실행자가 준비됐을 때만 — 아니면 회색 + 이유).
4. 사용자가 읽지 않는 것(diff·도구 호출·커밋 해시·접수증 ID)은 화면에 없다. 알아야 할 것은 목표 문서의 진행 기록 한 줄로.

## 6 메울 틈

1. **코드 엔진(세 탭)** — `prims-engine.tsx` 의 `kind === 'code'` 분기를 `generic/code/` 모듈로: `ProjectFrame`(상단 탭·칩·단추·⚙), `GoalTab`(문서 엔진 `DocumentEngine` 을 `목표.md` 자료로 마운트 — 캔버스·ai_dock 재사용), `FilesTab`(트리·원문·편집), `RunTab`(명령·출력 스트림·미리보기). 단독 창 `CodingApp.tsx` 는 `DocumentApp.tsx` 와 같은 한 장. 파일마다 1500줄 아래. 2026-10-05 의 "코딩은 엔진 표면 없음" 주석·ibl.md 줄 개정.
2. **프로젝트 투영** — code 어댑터에 `read{selector:{projects:true}}`(등록 원장 + 기본 폴더 스캔 → 카드 행: 이름·아이콘·요약(목표 문서 첫 절)·상태(활성 접수증·실행)·mtime·path), `open{path, register:true}`(원장 등록·`git init`·`목표.md` 없음 표시). 선택자·인자 추가이지 새 op 가 아니다 — `workspace.md` code 행 + 용례 재검토 ack.
3. **프로젝트 단위 몸** — 지금 `coding_workspace` 는 저장소→과제→worktree. 프로젝트 = 폴더 자체를 작업 공간으로 두는 어댑터 경로(worktree 없음), 각인은 지금 `review/approve/apply` 를 한 함수로(자동). `coding_runs` 의 cwd·샌드박스 루트 = 프로젝트 폴더. 실행자 선택지에 번들 Claude Code(`find_claude_binary`, coding 프로필 명령줄: cwd·권한 모드·MCP 없음) 추가.
4. **되돌리기** — `versions`(각인 목록: 시각·메시지·바뀐 파일) · `restore{revision, path?}`(전체 또는 파일 하나) 구현(지금 capabilities `restore: False`).
5. **위임 역할 coding** — `[others:delegate]` role:"coding"+context.resource → `coding_runs` 로, 접수증 종류 `coding_run` 을 `task_receipts` 어댑터(`task_kinds` 데이터 길)로, 프로젝트 단위 큐. `context.command`(+`serve`) 는 명령만 도는 실행(출력 스트림은 접수증 progress 또는 사건 스트림 — 엔진 I/O 경로 하나).
6. **문서 엔진의 재사용 경계** — 목표 문서 자료(document kind)와 프로젝트 자료(code kind)가 한 폴더를 가리킨다. 문서 엔진이 `목표.md` 를 저장하면 프로젝트의 각인 대상이기도 하다 — 자동 각인은 코딩 끝·직접 편집 저장 때만(문서 자동 초안마다 커밋하지 않는다).
7. **문서 표면** — `ibl.md` engine 줄·`new_action_checklist.md`·`workspace.md`·새 가이드 `coding_project.md`(짧게: 프로젝트=폴더, 목표 문서 틀, 위임 문장). `build_dist_filter.py`(새 instruments 파일).
8. **은퇴** — `CodingWorkspace.tsx`·`coding-workspace.css`·`/coding/*` 10경로(엔진 I/O 로 남길 출력 스트림 1개 외) → `/ibl/execute`. 시험 이전: `test_coding_surface.py`·`test_coding_live.py`(`-m system`) → 계기 선언 + IBL 운반 + 위임 접수증 경로. `test_coding_workspace.py`·`test_coding_runs.py` 는 몸 시험으로 유지·확장(프로젝트 경로·자동 각인·restore).

## 7 순서

1. **관문**(반나절) — 번들 Claude Code 를 코딩 프로필로 프로젝트 폴더에서 돌려 파일 생성·실행까지(쓰기 경계: Codex 의 이중 샌드박스 거절 사례처럼 바깥 샌드박스를 씌울 수 있는지 실측). Codex 바이너리 경로. 결과를 §9 에.
2. **렌더러** — 틈 1. 임시 `coding.yaml`(프로젝트 한 모드)로 네 화면. 화면 확인 = `preview_start {name:"indiebiz-frontend-attach"}` → 앱 모드 → 코딩.
3. **백엔드** — 틈 2·3·4·5·6. **모아서 쓴다**(재기동 제어자 FAILED 함정).
4. **데이터** — §3-1 선언 전체, 가이드, `build_ibl_nodes.py --check`, 문서 표면, 해마 관용구 3정의 재검토(`과제열기`→프로젝트 단위로 고치거나 은퇴).
5. **검증** — 화면으로: 새 프로젝트(말로) → 목표 문서가 정리돼 열림 → AI 한 줄로 다듬기 → 목표대로 코딩 → 칩 진행 → 끝나면 진행 기록 한 줄·트리에 ● → 코드 파일 열어 보기·편집·저장 → 실행 → 출력·미리보기 → ⚙ 이 작업 전으로 → 첫 화면 상태 칩. 프로젝트 둘 병렬. 기존 폴더 가져오기(목표 초안). 원격 첫 화면·목표 문서 열람. 인수 시험 이전(틈 8).
6. **은퇴** — 틈 8. 홈 타일 `coding` 은 `instrument: coding` 이 자리 상속.
7. **후속** — §4 오른쪽 열.

## 8 판정 요청 (언어 개정·파괴적 변경·기록된 결정의 번복만)

1. **코딩에 엔진 표면(세 탭)을 둔다** — 2026-10-05 기록("코딩 작업 공간은 엔진 표면이 없다 — blocks 로 diff")의 번복. 뷰 낱말·이벤트 이름 불변, 새 낱말 0. 구현자 추천 = 승인.
2. **과제별 worktree·검토 묶음·승인·커밋 메시지 흐름 은퇴 → 프로젝트 폴더 = 작업 공간, AI 코딩마다 자동 각인 + 되돌리기**(옛 설계 "작업 공간과 정본 반영" 절의 대체, 파괴적). 근거: 사용자는 코드를 읽지 않으므로 diff 승인은 의미 없는 관문이고, 안전은 샌드박스(폴더 밖 쓰기 차단)와 되돌리기가 맡는다. 자기 저장소는 여전히 거절. 구현자 추천 = 승인.
3. **`[others:delegate]` role:"coding"(+context.resource) 은 실행자 몸을 바꾸고 프로젝트 단위 큐에 선다**(role 의미 확장). 대안 = 전역 순차 큐(프로젝트 병렬 불가). 구현자 추천 = 승인.
4. **옛 코딩 화면·HTTP 작업표 은퇴**(파괴적). 구현자 추천 = 승인.

판정 아닌 것(구현자 결정): 기본 폴더 `outputs/coding`, 목표 문서 파일명 `목표.md` 와 절 이름, 카드/리스트 토글, 색, 기본 실행자.

## 9 미확인

- 번들 Claude Code 의 코딩 프로필 실행과 쓰기 경계(관문 1). Codex 경로.
- 접수증 progress 만으로 실행 탭의 출력 스트림이 충분한지(틈 5) — 렌더러 단계 실측.
- 프로젝트 단위 큐와 시스템 AI 의 다른 작업 사이 자원(토큰 한도·에피소드 동시성).
- 성능(토큰·시간) 미측정.

## 구현 상태 (2026-10-07 — 사용자 "구현해", 미커밋)

사용자 추가 명제: *코딩 앱은 기본적으로 실행 에이전트를 쓴다 — 프로바이더별로 따로 하지 않는다.* 그래서 §3-3 의 "실행자 선택(번들 Claude Code·Codex·API 모델, coding 프로필)" 은 **범위에서 뺐다**.
AI 코딩 = `[others:delegate]{scope:"system", role:"coding", mode:"async", message, context:{project, resource, goal}}` 한 문장 → 시스템 AI(실행 에이전트, 어떤 프로바이더로 도는지는 시스템 AI 설정)가 IBL 로 폴더 안에 짓는다. 프로바이더 무관 몸으로 남은 것은 실행 탭의 샌드박스 프로세스 러너뿐.

- **몸**: `backend/services/coding_projects.py`(프로젝트=폴더: 등록·목록(등록 + outputs/coding 하위 폴더)·목표 문서 틀/파싱·파일 읽기·제안/적용(삭제 포함)·기록(save=모든 변경 한 커밋)·versions·restore(되돌리기 전 보관, path 로 파일 하나)·실행(CodingProcesses 샌드박스, serve 면 로컬 네트워크)). `workspace_sessions.CodeAdapter` 가 이것을 쓴다(폴더 = kind code, git 없으면 init). `read(kind:"code", selector:{projects:true})` 는 자료 없는 유일한 읽기. 옛 `coding_workspace.py`·`coding_runs.py`(과제별 worktree·검토 묶음·승인·프로바이더별 실행자)와 시험 4개 삭제. `coding_profile.py`·cli_provider 의 coding 분기는 REPAIR 경로(Codex 격리)가 쓰므로 그대로.
- **엔진 I/O**: `api_coding.py` 는 실행만(`POST /coding/projects/{id}/run`·`GET /coding/runs/{id}?offset`·`POST /coding/runs/{id}/stop`·`GET /coding/projects/{id}/runs`). 접수증 종류 `coding_run`(system_essentials `task_kinds` → `essentials_workspace.coding_run_status[_cancel]`).
- **얼굴**: `frontend/src/components/generic/code/{CodeEngine,FilesTab,RunTab}.tsx` + `ibl.ts`(엔진의 고정 IBL 문장). `prims-engine` 의 kind=code 가 띄운다. 목표 문서 탭은 문서 엔진 세션을 쓰지 않고 code 어댑터의 파일 읽기/propose/apply 로 `목표.md` 를 다룬다(AI 가 바깥에서 고친 글을 세션 초안이 가리지 않게). 단독 창 `#/coding` = `DocumentApp id="coding"`. 옛 `CodingWorkspace.tsx`·css 와 코드 정의 코딩 타일 삭제(같은 id `coding` 이라 자리 상속).
- **선언**: `data/instruments/coding.yaml`(프로젝트 카드 → 드릴 engine / 새 프로젝트(`[self:ask]` 가 바람을 목표 문서 틀로) / 기존 폴더 가져오기). 관용구: `과제열기`·`검토반영` 은퇴(4927·4929·4933·4935 삭제, 색인 재생성) → `프로젝트열기`·`기록하기` 시딩(4995~4998), `파일고치기` 유지.
- **검증**: `test_coding_projects.py`(8), `test_workspace_sessions.py` 갱신, `--check` 통과(path_audited 재감사 `73262440cdcfcf1f`, 용례 ack), tsc 통과. **실화면**: 새 프로젝트(말 → 목표 문서 정리) → 목표대로 코딩(시스템 AI 가 `apple_calculator.py`·테스트 작성, 실행 방법·진행 기록 채움, 30초) → 열 때 자동 기록 → 코드 파일 탭 원문 → 실행 탭 `python3 -m unittest -v` 성공·종료 0 → AI 한 줄로 목표 문서 수정 → 저장·기록. 홈 타일·단독 창·앱 모드 인라인 셋 다 확인.
- **실측 함정**: 완료된 시스템 작업은 백엔드 재기동 때 지워진다(`boot_common` 의 completed 정리) → 접수증 조회가 "찾지 못했습니다" — 엔진은 이를 끝난 것으로 보고 폴더를 기록·재독(진행 기록이 사실의 정본). 재기동 중 목표 문서 읽기 실패는 메시지로(탭 다시 누르면 재독).
- **미구현/후속**: 폰·원격 열람, 도중 지시(steering), 미리보기는 실행 방법에 URL 이 있을 때만, 자기 저장소는 거절(REPAIR 경로), 되돌리기 UI 는 ⚙·파일 탭에 있으나 실화면 미확인, 기존 폴더 가져오기 실화면 미확인.

### 기존 폴더의 목표 문서 자동 작성 (2026-10-08)

`CodingProjects.open`은 목표 문서가 없으면 가져오기 시점에 `목표.md`를 만든다.
`package.json`의 설명·dev/start 스크립트, Python 진입 파일·설정, 정적 HTML,
README 첫 문단에서 목표 요약과 실행 방법을 추론한다. 별도 AI 호출은 없다.
사용자가 준 목표가 설명보다 우선하고, 기존 문서와 생성 도중 다른 작성자가 만든 문서는
덮어쓰지 않는다. 추론하지 못한 항목은 기존 자리표시로 남긴다.
실행 주소는 지원하는 개발 서버의 기본 포트 또는 스크립트에 명시된 포트를 사용하므로
별도 설정 파일·환경변수로 바뀐 주소는 사용자가 목표 문서에서 확인·수정해야 한다.
가져오기는 문서를 만들며 명령을 자동 실행하지 않는다.

에피소드 4478·4479의 사본은 정본 적용 전에 프로젝트 소유자 불일치로 멈췄다.
MCP가 프로젝트 경로만 전달해도 `/ibl/execute`가 프로젝트 신원을 복원하고,
프로젝트 밖 요청은 신원을 비우며 요청 종료·실패 때 작업자의 이전 값을 복원하도록 수리했다.
소유자 검사는 유지하며 다른 프로젝트의 같은 에이전트 ID는 계속 거절한다.

## 10 참고 — 기각된 안

같은 날 먼저 낸 하네스 3열 안(과제 목록 | 대화·변경·파일·출력 탭 + 독 | 과제 패널)과 그 목업은 삭제했다. 조사 요지(하네스 13종의 수렴 표면 5·원형 5·기본기)는 메모리 `coding-app-on-ibl-2026-10-07` 에 남겼다 — 이 앱이 **일부러 가져가지 않는 것**의 목록으로.
