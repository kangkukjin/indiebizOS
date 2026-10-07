# 스프레드시트 앱 = 엑셀의 얼굴 + IBL 몸

작성일: 2026-10-07. 상태: **구현 중(§11 진행 기록)** — 사용자 승인(2026-10-07) 뒤 §7 순서대로 집행. 독자: 이 일을 이어받는 구현자.
상위 계획: [공통 기반 위의 앱 구성](APP_COMPOSITION_ON_IBL_PLAN_2026_10_05.md) §6-4~5 의 스프레드시트 몫.
선행 사례: [문서 앱 = 빈노트의 얼굴 + 형식별 엔진](DOCUMENT_APP_ON_BINNOTE_PLAN_2026_10_05.md) — 이 문서는 그 틀을 그대로 쓴다.
옛 설계(엔진·형식·저장 계약의 정본): [스프레드시트 앱 설계 2026-10-02](SPREADSHEET_APP_DESIGN_2026_10_02.md) §3·§8·§9 는 유지한다.

사용자 명제(2026-10-07): *스프레드시트 앱을 IBL 기반으로 다시 만든다. 지금과 달리 UI 는 윈도우의 엑셀처럼 보이게.
얼마 전 만든 문서 앱을 참고해 설계한다.*

## 0 출발점

| | 지금 시트 앱 (`SpreadsheetWorkspace.tsx`, 2026-10-02) | 문서 앱 (`document.yaml`, 2026-10-06) |
| --- | --- | --- |
| 모습 | 경로 입력·업로드·템플릿 폼 + 통합문서 탭 + ONLYOFFICE iframe + 오른쪽 "AI와 변경 검토"(JSON 값 입력) | 빈 페이지가 바로 서고, 탭은 ⚙ 안, 하단 AI 한 줄 |
| 구성 | React 전용 화면 ↔ HTTP 작업표(`/spreadsheets/*`) ↔ `spreadsheet_workspace` | 선언 한 장(`data/instruments/document.yaml`) + `engine` 뷰 + `[self:workspace]` |
| 엔진 | ONLYOFFICE 만(컨테이너). **지금 이 맥에서 colima 가 꺼져 있어 편집기가 뜨지 않는다** | 원문=항상 뜨는 캔버스(textarea), DOCX=ONLYOFFICE, HWP=RHWP(npm 엔진, 서버 없음) |
| AI | 범위·JSON 을 사람이 적어 제안 → 적용 | 선택(없으면 전체)을 `[self:ask]` 한 줄에 → 제안 → 반영 |
| 저장 | 공통 `OfficeSessions`(작성 권한·해시·멱등 저장·버전·복구) — 이건 맞다 | 같은 계약 |

문서 앱이 "모습은 빈노트, 몸은 문서 서비스"였듯, 시트 앱은 **모습은 엑셀, 몸은 `[self:workspace]` + 기존 시트 서비스**다.
그리고 문서 앱의 원문 캔버스처럼 **서버 없이 항상 뜨는 격자 엔진**이 기본이어야 한다. 지금처럼 컨테이너가 꺼지면 앱이 빈 껍데기인
구성은 일상 사용에 맞지 않는다(0 절 실측). 새 낱말은 없다 — `[self:workspace]`·`[self:sheet]`·`[table:spreadsheet]`·`[self:read]`·`[table:ai]` 와
뷰 `engine`(+`ai_dock`) 위에 선다.

## 1 목표 형태 — 엑셀의 얼굴

`data/instruments/spreadsheet.yaml` 한 장, 앱 모드 인라인 + 단독 창(`#/spreadsheets`)은 같은 선언.
화면은 윈도우 엑셀(Office 컬러풀 테마)의 다섯 층을 그대로 둔다. 선언에는 레이아웃 키가 없다 — 시트 엔진이 이 얼굴을 맡는다.

```
┌ 제목줄(녹색 #217346)  장부_2026.xlsx — 스프레드시트            [자동 저장 ●]  [⤢] ┐
│ 파일 │ 홈 │ 삽입 │ 페이지 레이아웃 │ 수식 │ 데이터 │ 검토 │ 보기 │            [AI ✦] │
│ ┌클립보드┐┌글꼴──────────────┐┌맞춤────────┐┌표시 형식────┐┌셀────┐┌편집──────┐      │
│ │붙여넣기││맑은 고딕 ▾ 11 ▾ B I U││≡ ≡ ≡ 줄바꿈 ││일반 ▾ ₩ % , ││삽입 삭제││Σ 정렬 찾기│      │
│ [ B2  ▾ ] [✗ ✓ fx] [ =SUM(B2:B9)                                                  ] │
│   │  A   │  B   │  C   │  D   │  E   …                                            ║ AI │
│ 1 │ 날짜 │ 거래처│ 수입 │ 지출 │                                                   ║ 작업│
│ 2 │ …    │ ▓▓▓▓ 선택 범위(녹색 테두리·채우기 핸들)                                 ║ 창  │
│ … │                                                                                ║    │
│ ◂ ▸ │ 매출 │ 재고 │ ⊕ │                                                                 │
└ 준비            평균: 1,234  개수: 8  합계: 9,872            ▦ ▤ ▥   −──●──+ 100% ┘
```

- **파일 탭 = 계기의 모드 탭.** 엑셀의 백스테이지 자리에 선언의 모드(새 통합문서·열기·틀로 새 통합문서)와 엔진 도구
  (다른 이름으로·형식 변환 사본·버전 되살리기·인쇄/PDF·문서에 표 보고서·사무 편집기로 열기)가 들어간다. 문서 앱의 ⚙ 와 같은 통로
  (`InstrumentMenuContext.claim`) — 캔버스가 서 있는 동안 계기 탭 줄은 화면에서 빠진다.
- **홈·삽입·수식·데이터·보기** 는 격자 엔진의 서식·구조·수식·정렬/필터·틀 고정·확대 명령. 1차는 홈 전체 + 삽입(행/열·차트 자리 표시)
  + 수식(자동 합계·함수 삽입) + 데이터(정렬·필터·텍스트 나누기 자리) + 보기(틀 고정·눈금선·확대). 안 되는 버튼은 그리지 않는다 — 죽은 버튼이 있는 리본은 엑셀이 아니다.
- **이름 상자·수식 입력줄·열 문자·행 번호·녹색 선택 테두리·채우기 핸들·시트 탭·상태줄 집계(평균·개수·합계)·확대 슬라이더** 는 모두 있어야 한다.
  이것들이 "엑셀처럼 보인다"의 실체다.
- **AI 작업창** = `ai_dock` 선언을 엑셀의 Copilot 자리(오른쪽 작업창, 리본 끝 `AI ✦` 로 토글)에 그린다. 문서 앱의 하단 한 줄과 같은 낱말·같은 흐름
  (요청 → 제안 → 반영/닫기), 자리만 엑셀식. 제안은 **바뀌는 셀 목록 + 격자 위 미리보기 강조**로 보이고, 반영은 엔진이 사람의 편집으로 넣는다(되돌리기 1회 = Ctrl+Z).
- 원격·폰은 1차에 **열람 강등**(`[self:workspace]{op:"read"}` 투영 → `blocks` 표) — 문서 앱과 같은 조건. 격자 엔진이 원격 렌더러에 서는 것은 후속.

## 2 엔진 — 격자는 몸 안에, 사무 엔진은 보조

| | 격자 엔진(기본) | 사무 엔진(보조, ONLYOFFICE) |
| --- | --- | --- |
| 뜨는 조건 | 항상(브라우저 안 npm 엔진 — RHWP 와 같은 자리) | 컨테이너가 떠 있을 때(파일 탭 "사무 편집기로 열기" → 꺼져 있으면 `/documents/engine/start`) |
| 맡는 파일 | 셀·수식·서식·병합·열폭·틀 고정·유효성·조건부 서식으로 이뤄진 통합문서 | 차트·피벗·그림·주석·매크로(보존만)·외부 연결 등 격자가 그리지 못하는 부품이 있는 통합문서 |
| 계산 권위 | 그 자료를 연 동안 격자 엔진 | 그 자료를 연 동안 ONLYOFFICE |
| 저장 | 격자 → XLSX(§4) → 공통 저장(해시 확인·원자 교체·버전) | 지금 경로 그대로(엔진 포획 → 공통 저장) |

한 자료는 **한 번에 한 엔진**이 연다(옛 설계 §1 "두 계산기 금지" 는 그대로). 어느 엔진인지는 **자료 capabilities 가 정한다** — 문서 앱이 원문/DOCX/HWP 를
가르는 것과 같은 자리(`spreadsheet_files.inspect` 에 drawing·chart·pivot·comment 부품 수를 더해 `capabilities.engine: "grid" | "office"`).
격자가 못 그리는 부품이 있으면 ① 사무 편집기로 열기 ② 열람만 ③ "부품 뺀 사본으로 편집"(원본 보존) — 문서 앱의 ".docx 사본으로 열기" 와 같은 모양.

**격자 엔진 채택안: Univer**(`@univerjs/presets` 1.0.x, Apache-2.0). 이유 — 수식 엔진(행/열 삽입 시 참조 갱신 포함)·숫자 서식·병합·틀 고정·정렬/필터·찾기/바꾸기·
실행 취소·한글 IME·캔버스 렌더(만 행 급)를 다 갖고 있고, 자체 도구줄을 숨기고 **Facade API** 로 우리 리본이 명령할 수 있다. 서버가 없다.
대안 — 자체 격자 + `fast-formula-parser`(MIT): 전부 우리 손이라 모습은 완전히 자유롭지만 참조 갱신·숫자 서식·클립보드·IME·실행 취소를 다시 짓는다.
HyperFormula 는 GPL-3.0 이라 MIT 저장소에 넣지 않는다. ONLYOFFICE 도구줄만 숨기고 리본을 덧씌우는 안은 **실행 취소·찾기·확대·인쇄가 공개 플러그인 API 에 없어**
죽은 버튼을 피할 수 없고 컨테이너 의존도 그대로라 버린다.

**엔진 선정 관문(§7-1)** — 채택안이 아래를 통과해야 2단계로 간다. 하나라도 막히면 대안(자체 격자)으로 간다. 라이브러리 존재나 문서의 문장은 통과 근거가 아니다.
1. 1만 행×20열 열기 3초 이내, 10만 행 파일은 열리되 "큰 파일" 표시.
2. 한글 IME 입력(조합 중 Enter·방향키)·Ctrl+Z/Y·채우기 핸들·복사/붙여넣기(TSV·다중 행) 실조작.
3. 기존 함수 대표식 63개(`test_spreadsheet_functions_live.py` 표) 값 일치 — LET 포함 여부를 기록(ONLYOFFICE 는 LET 실패였다).
4. 도구줄 숨김 + Facade 로 굵게·채우기·테두리·표시 형식·행/열 삽입·정렬·필터·틀 고정·병합·실행 취소·확대 호출.
5. 격자 JSON ↔ XLSX(§4) 왕복에서 값·수식·서식·병합·열폭·틀 고정 보존, LibreOffice 독립 재열기.
6. React 19 공존·번들 크기(앱 첫 로드 증가분 기록)·ko 로케일(없으면 우리 리본이 전부 한글이라 무관).

## 3 계기 선언 초안

```yaml
# 스프레드시트 앱 — 엑셀의 얼굴 + IBL 몸 (docs/SPREADSHEET_APP_ON_IBL_PLAN_2026_10_07.md). 어휘 없는 순수 매니페스트.
instrument: spreadsheet
edition: 2
icon: 📊
name: 스프레드시트
order: 13

modes:
  # ── 빈 통합문서: 앱을 열면 바로 서는 격자. 비어 있고 아무 창도 쥐지 않은 가장 최근 "무제 ….xlsx" 를 다시 쓰고, 없으면 만든다. ──
  - name: 빈 통합문서
    auto_run: true
    action: |
      $빈 = [self:list]{path: "outputs/sheets"} >> [table:filter]{where: ($r) => $r.is_dir != true && $r.name[0:2] == "무제" && $r.name[-5:] == ".xlsx"} >> [table:sort]{by: "mtime", descending: true}
      [if: len($빈) > 0] {
        $열린 = [self:workspace]{op: "open", path: $빈[0].path}
        [if: $열린.session == null && $열린.capabilities.empty == true] { return $열린 }
      }
      $t = [self:time]
      $쓴 = [table:spreadsheet]{path: f"outputs/sheets/무제 ${t[0:10]} ${t[11:13]}${t[14:16]}${t[17:19]}.xlsx", rows: []}
      [self:workspace]{op: "open", path: $쓴.path}
    view:
      - &grid
        type: engine
        ref: '{resource}'
        ai_dock:
          # 선택 범위($sel={sheet,range}·$table=값 2차원·$text=TSV)가 있으면 범위, 없으면 사용 범위 전체. 값·수식 2차원을 돌려받아 엔진이 미리보기 → 반영.
          action: '[table:ai]{items: [{range: $sel.range, cells: $table}], instruction: $dock, schema: "values(범위와 같은 행·열 수의 2차원 배열, 수식은 = 로 시작, 집계는 수식으로)", input_fields: ["range", "cells"], preserve_rows: true}'

  - name: 새 통합문서
    run_label: 만들기
    inputs:
      - {key: name, type: text, required: true, placeholder: "통합문서 이름 (확장자 없이)"}
      - {key: folder, type: text, default: "outputs/sheets", placeholder: "만들 폴더 (없으면 생긴다)"}
      - key: template
        type: select
        default: blank
        options:
          - {value: blank,      label: 빈 통합문서}
          - {value: ledger,     label: 수입지출 장부}
          - {value: quotation,  label: 견적서}
          - {value: inventory,  label: 재고·입출고}
          - {value: attendance, label: 근태}
          - {value: schedule,   label: 일정}
          - {value: budget,     label: 프로젝트 예산}
    # 틀은 선언 데이터(머리글 + 첫 행 수식). 같은 이름이 있으면 멈춘다.
    action: |
      $file = f"${name}.xlsx"
      $있음 = [self:file_find]{pattern: $file, path: $folder}
      [if: len($있음.items) > 0] { return {error: f"이미 있는 통합문서입니다: ${file} — 열기로 여세요"} }
      $틀 = {
        blank: [],
        ledger: [["날짜", "구분", "거래처", "수입", "지출", "잔액"], ["", "", "", 0, 0, "=D2-E2"]],
        quotation: [["품목", "수량", "단가", "금액"], ["", 1, 0, "=B2*C2"]],
        inventory: [["품목코드", "품목", "입고", "출고", "재고"], ["", "", 0, 0, "=C2-D2"]],
        attendance: [["날짜", "이름", "출근", "퇴근", "근무시간", "비고"], ["", "", "", "", "=D2-C2", ""]],
        schedule: [["날짜", "일정", "담당", "상태"]],
        budget: [["항목", "예산", "실제", "차이"], ["", 0, 0, "=B2-C2"]]
      }
      $쓴 = [table:spreadsheet]{path: f"${folder}/${file}", rows: $틀[$template]}
      [self:workspace]{op: "open", path: $쓴.path}
    view:
      - *grid

  - name: 열기
    run_label: 열기
    inputs:
      - {key: path, type: text, browse: "outputs/sheets", required: true, placeholder: "통합문서 경로 — xlsx · xlsm · csv · tsv · ods"}
    # csv/tsv 는 [self:read] 로 읽어 xlsx 사본을 만들어 연다(원본 보존). 열 타입(식별자 텍스트 보존)은 격자의 파일 탭 "CSV 열 타입" 에서 바꾼다.
    action: |
      $ext = $path[-4:]
      [if: $ext == ".csv" || $ext == ".tsv"] {
        $읽은 = [self:read]{path: $path}
        $사본 = [table:spreadsheet]{path: f"outputs/sheets/${$path | basename}.xlsx", table: $읽은.data.table}
        return [self:workspace]{op: "open", path: $사본.path}
      }
      [self:workspace]{op: "open", path: $path}
    view:
      - *grid
```

선언에서 결정한 것: 기본 폴더 `outputs/sheets`(새 자리 — 옛 앱은 폴더 개념 없이 "최근 통합문서" 목록이었다). 틀은 서비스(`spreadsheet_templates.py`)가 아니라 선언 데이터
(옛 인쇄용 견적서·청구서 틀은 서식이 있어 1차는 파일 탭 "틀로 새 통합문서"에서 `[self:copy]` 로 틀 파일 복사 — 문서 앱의 한글 빈 틀과 같은 길).
`$path | basename` 같은 경로 조각은 판본 2 문자열 함수로 — 없으면 `split`/`join` 으로 계산(문서함 폴더 탐색이 그렇게 했다).

## 4 저장 — 격자 JSON ↔ XLSX

세션·버전·복구는 `OfficeSessions` 그대로(작성 권한·`engine_epoch`·기대 원본 해시·원자 교체·버전·복구 후보). 바뀌는 것은 **엔진 포획이 ONLYOFFICE 콜백이 아니라 격자 직렬화**라는 점뿐이다.

- `GET /spreadsheets/{id}/grid` — 저장본(또는 초안 blob)의 격자 투영: 시트별 셀(값·수식·숫자 서식·글꼴·채우기·테두리·맞춤)·병합·열폭·행높이·틀 고정·유효성·조건부 서식.
  읽기는 `openpyxl`(값은 저장 캐시 — 격자가 열자마자 재계산해 최신값을 만든다).
- `POST /spreadsheets/{id}/grid-capture` — 격자 → XLSX bytes → 세션 초안 blob(기존 `engine-capture` 와 같은 자리). **1차 기록기 = openpyxl 왕복**(셀·서식·병합·열폭·틀 고정·유효성·
  조건부 서식·정의 이름·하이퍼링크 보존). openpyxl 이 잃는 부품(차트·그림·피벗·주석·슬라이서)이 있는 파일은 §2 capabilities 가 처음부터 사무 엔진으로 보내므로
  이 경로에 오지 않는다. **2차 기록기 = `sheet_range_ops` 확장**(sheetN.xml 의 `sheetData`·`cols`·`mergeCells`·`sheetViews` 만 교체하고 나머지 파트 보존) — 차트가 있는 파일까지
  격자에서 편집하되 차트 자체는 그리지 않는 단계. 계산 캐시는 격자 값을 `<v>` 로 쓰고 `fullCalcOnLoad` 를 켠다(엑셀·LibreOffice 가 열며 재계산).
- 두 HTTP 경로는 **엔진 I/O** 다(문서 앱이 `/documents/*` 중 엔진 I/O 만 남긴 것과 같은 기준). 선언이 부르지 않는다.
- 자동 초안: 입력이 멈춘 뒤 2초, 그리고 Ctrl+S = 원본 저장(문서 앱 원문 캔버스와 동일). 제목줄 "자동 저장 ●" 는 초안 상태 표시다.
- `[self:workspace]` 시트 어댑터의 `snapshot`·`apply`·`save` 는 지금처럼 편집창에 **접수**되고(`pending` 큐), 격자 엔진이 큐를 소비한다 — `engine_state` 는 플러그인 대신
  격자가 만든 JSON(시트별 사용 범위의 값·수식·숫자 서식). 시스템 AI 의 `[fn:범위제안]`(해마 관용구) 은 그대로 돌아간다.

## 5 AI — 선택 범위를 통화로

- 선택 이벤트 페이로드(engine `selection`)에 시트용 칸을 더한다: `$sel={sheet, range}`·`$sheet`·`$range`(지금 있음) + **`$table`(선택 범위 값 2차원, 10,000셀 상한)·
  `$text`(같은 범위의 TSV)**. `$text` 가 있으면 문서 앱의 `[self:ask]` 독 그대로 질문형("이 표의 추세를 말해줘")도 된다. 뷰 낱말·이벤트 이름은 그대로 — 페이로드 칸 추가(검증기 주석·ibl.md 한 줄).
- 독 action 은 `values` 2차원을 돌려준다(§3). 엔진은 **바뀌는 셀만** 목록(주소 · 전 → 후)과 격자 강조로 보이고, 반영은 Facade `setValues`(수식은 `=` 로 시작) — 사람의 편집과 같은 길이라
  초안·저장·실행 취소가 한 경로다. 선택이 없으면 사용 범위 전체(20,000셀 상한 — 넘으면 "범위를 선택하세요").
- 요청 뒤 격자가 바뀌면 그 제안은 버린다(문서 앱의 "요청 뒤 그 자리가 바뀌면 거절" 과 동일 — 제안은 요청 시점 `$table` 의 해시에 묶인다).
- 판단이 긴 일(여러 시트 정리·피벗 설계)은 독이 아니라 시스템 AI 에게 — `[others:delegate]{scope:"system"}` 가 `[self:workspace]` 로 같은 자료를 고치고 격자가 접수증을 소비한다. 독은 가볍게 지금 답.

## 6 메울 틈

1. **격자 엔진 바인딩** — `prims-engine.tsx` 의 `SheetEngine`(지금 ONLYOFFICE 전용 40줄)을 `generic/sheet/` 모듈로: `ExcelFrame`(제목줄·파일 탭·리본·수식줄·시트 탭·상태줄),
   `GridEngine`(Univer 마운트·Facade 명령·선택 이벤트·큐 소비·자동 초안), `AiPane`(독 렌더 — `AiDockPanel` 재사용, 제안 미리보기), `OfficeFallback`(기존 `SpreadsheetEditor` 를 그대로 사무 경로로).
   파일마다 1500줄 아래.
2. **capabilities.engine 판정** — `spreadsheet_files.inspect` 에 부품 집계(drawings·charts·pivotTables·comments·vba) → `capabilities.engine`·`empty`(빈 통합문서 판정, 빈 페이지 재사용용).
3. **격자 I/O 경로 2개**(§4) + 기록기 1차(openpyxl).
4. **파일 탭 = 계기 메뉴** — `InstrumentMenuContext.claim` 은 문서 엔진이 쓰는 통로 그대로. 모드 탭은 작은 창(ModeDialog)으로, 성공했을 때만 격자가 그 자료로 바뀐다(문서 앱 10-06 규약).
5. **선택 페이로드 칸**(§5) + 검증기(`iblbuild_appview.py` engine `ai_dock` 주석)·`ibl.md` engine 줄·`new_action_checklist.md`.
6. **CSV** — 1차는 `[self:read]` → `[table:spreadsheet]` 사본(§3). 옛 가져오기 서비스의 열 타입 미리보기(식별자·`00123` 보존)는 파일 탭 "CSV 열 타입" 패널로 옮긴다(`spreadsheet_imports.py` 재사용).
7. **인쇄/PDF** — 격자 엔진의 인쇄 능력을 관문에서 확인. 없으면 1차는 `[self:workspace]{op:"export"}` 사본 → LibreOffice 변환(`spreadsheet_formats`) 으로 PDF — "같은 세대 PDF" 는 계산 캐시가 격자 값이므로 성립.
8. **원격 렌더러**(`app_render_core.js`)는 `engine` 을 모른다 — 1차 열람 강등(`blocks` 표). 격자 엔진의 원격 탑재는 후속.

## 7 순서

1. **관문**(§2) — 임시 페이지에서 Univer 실험. 결과를 이 문서 §9 에 숫자로 적는다. 반나절.
2. **렌더러** — 틈 1·4·5. 엑셀 얼굴 + 격자 + AI 작업창. 임시 `spreadsheet.yaml`(열기 한 모드)로 화면 확인.
3. **백엔드** — 틈 2·3. 격자 I/O·기록기·capabilities. 격자 JSON↔XLSX 왕복 시험(`test_spreadsheet_grid.py`) + LibreOffice 독립 재열기.
4. **데이터** — §3 선언 전체, 틀 파일(견적서·청구서 인쇄 양식 `data/instruments/spreadsheet_templates/`), `build_ibl_nodes.py --check`, 문서 표면(ibl.md·checklist·sheet.md 한 줄).
5. **검증** — 화면으로: 빈 통합문서 → 입력·수식·서식·행 삽입 → AI 제안 → 반영 → Ctrl+S → Excel/LibreOffice 재열기 → 버전 되살리기. xlsx(차트 있음) → 사무 편집기 분기. csv → 사본.
   인수 시험 이전: `test_spreadsheet_browser_live.py` 를 새 얼굴 라벨로(문서 앱이 `test_document_browser.py` 를 옮긴 방식 — 대역 서버에 계기 선언 + IBL 운반). `test_spreadsheet_engine_live.py`(플러그인)는 사무 경로로 남긴다.
6. **은퇴** — `SpreadsheetWorkspace.tsx`·`spreadsheet.css`·`SpreadsheetImport/Conversion/Recovery.tsx`(기능은 파일 탭으로 이전)·홈 타일 `spreadsheets`(`instrument: spreadsheet` 가 자리 상속 — `inheritBinnote` 와 같은 한 줄)·
   Electron `spreadsheets` 창은 `DocumentApp.tsx` 와 같은 `SpreadsheetApp.tsx`(또는 둘을 `InstrumentApp(id)` 하나로). `SpreadsheetEditor.tsx` 는 사무 경로 바인딩으로 남는다. HTTP 작업표는 엔진 I/O 만.
7. **후속** — 2차 기록기(차트 파일까지 격자 편집), 원격·폰 격자, 차트·피벗(관문에서 Univer 능력 확인 뒤), 문서 표 연결 갱신의 격자 선택 연동.

## 8 판정 기록

- **판정 요청(사용자)** — 파괴적 변경 1건: **기본 엔진을 브라우저 안 격자 엔진으로 바꾸고 ONLYOFFICE 는 보조로 내린다.** 옛 시트 화면·"최근 통합문서"·오른쪽 JSON 검토창은 은퇴.
  구현자 추천 = 승인(0 절의 실측: 컨테이너가 꺼지면 앱이 서지 않는다 / 엑셀 얼굴은 격자를 우리가 쥐어야 가능 / 원격·폰 파리티의 길이 열린다).
- 구현체(Univer vs 자체)는 §2 관문이 정한다 — 판정 아님. AI 자리(오른쪽 작업창)·컬러풀 테마·기본 폴더 `outputs/sheets` 는 구현자 결정.
- 새 낱말 0. 뷰 낱말·이벤트 이름 불변(페이로드 칸만 추가).
- 옛 설계 §3 형식 표·§8 저장 계약·§9 제안 계약은 그대로 유효하다. 바뀌는 것은 "엔진 = ONLYOFFICE 단일" 뿐.

## 9 미확인

- Univer 관문 6항목(§2) — 숫자 미측정. 특히 LET·차트·피벗·인쇄의 지원 범위와 번들 증가분.
- 격자 JSON ↔ XLSX 왕복에서 조건부 서식·유효성·정의 이름의 보존 범위(openpyxl 1차).
- 원격 렌더러에 격자 엔진을 싣는 비용(후속).
- 성능(토큰·시간) 미측정.

## 10 참고 — 엑셀 얼굴 목업

`docs/mockups/spreadsheet_excel_face_2026_10_07.html` — 정적 HTML(렌더러 코드 아님). 리본·수식줄·격자·시트 탭·상태줄·AI 작업창의 배치와 색을 눈으로 맞추는 용도.

## 11 진행 기록

- **관문 통과(2026-10-07, 임시 `frontend/gate.html`)** — Univer `@univerjs/preset-sheets-core` 1.0.3(Apache-2.0) + filter/sort/find-replace 프리셋.
  1만 행×20열 `createWorkbook`+2프레임 **36ms**(저장 직렬화 30ms·2.9MB) · 10만 행×20열 **2.57초**(직렬화 312ms·29MB) — 제안 목표(3초/10초) 안.
  함수 대표식 **65/65 일치**(LET·LET 이름 인자 포함. `_xlfn.` 접두사는 격자가 모르므로 파일 경계에서 벗기고 붙인다 — 수리됨) · 리본 명령 Facade 호출 28종 전부 성공
  (굵게·채우기·테두리·표시 형식·병합·행/열 삽입·삭제·틀 고정·확대·정렬·필터·시트 추가·값/수식 쓰기·실행 취소·재실행·눈금선).
  한글 입력("한글 입력 시험")·수식 입력·Cmd+Z 되돌리기 실조작 확인. 공유 수식(autoFill)은 `getFormulas()` 가 셀별로 풀어 준다. React 19 공존.
  미측정: 번들 증가분(빌드 때 적는다)·채우기 핸들·클립보드 다중 행(표준 동작이라 화면 검증 때 눌러 본다).
- **구현(2026-10-07, 미커밋)**:
  - 백엔드 `services/spreadsheet_grid.py`(grid.v1 ↔ XLSX, openpyxl 1차 기록기 + 수식 캐시 `<v>` 주입 + 바이트 결정화) · `spreadsheet_files.inspect` 에 `grid_blockers`·`empty` ·
    `spreadsheet_workspace.capabilities` 가 `engine: grid|office|none` 판정 · `grid`/`grid-capture` 명령(엔진 I/O, 64MB) · 회귀 `test_spreadsheet_grid.py` 4건 + 기존 시트 회귀 통과.
  - 프론트 `generic/sheet/`: `grid-schema.ts`(통화·A1) · `grid-engine.ts`(Univer 껍질 — 도구줄·머리·꼬리 숨김, Facade 명령, 스필 범위 보존) · `ExcelFrame.tsx`(엑셀 얼굴) ·
    `SheetEngine.tsx`(세션·자동 초안·Ctrl+S·pending 큐 소비·AI 작업창·파일 탭) · `excel.css`. `prims-engine.tsx` 의 옛 SheetEngine(ONLYOFFICE 전용) 은 이 모듈로 교체.
    사무 엔진 경로는 `SpreadsheetEditor.tsx` 를 그대로 싣는다(`capabilities.engine === 'office'` 또는 파일 탭 "사무 편집기").
  - 선언 `data/instruments/spreadsheet.yaml`(빈 통합문서·새 통합문서·열기) + 빈 틀 `spreadsheet_templates/blank.xlsx`(`[table:spreadsheet]` 는 0행을 거절하므로 복사).
  - 은퇴: `SpreadsheetWorkspace.tsx`·`SpreadsheetImport.tsx`·`SpreadsheetRecovery.tsx`·홈 타일 `spreadsheets`(자리는 `spreadsheet` 가 상속)·`openSpreadsheets`. `#/spreadsheets` 는 `DocumentApp(id="spreadsheet")`.
  - 문서 표면: ibl.md engine 줄(`$table`/`$text`), `iblbuild_appview.py` 주석, `guides/sheet.md`.
- 판정 기록(구현자): CSV 가져오기 열 타입 미리보기(`spreadsheet_imports.py`)는 1차에서 UI 를 잇지 않았다 — 선언의 열기가 `[self:read]` → xlsx 사본으로 처리(식별자는 문자열 보존).
  세션 복구(`recover`) UI 도 1차 제외(서버 경로는 그대로) — 필요해지면 파일 탭 "버전"에 붙인다. 인쇄/PDF 는 격자 엔진에 없어 후속.
- **화면 검증(2026-10-07, 브라우저 5173 + 라이브 백엔드)**: `#/spreadsheets` 와 앱 모드 타일(📊 스프레드시트, 옛 `spreadsheets` 자리 상속) 둘 다 엑셀 얼굴이 선다(앱 모드는 `--app-chrome` 만큼 빼고 딱 맞음).
  빈 통합문서 자동 생성 → 셀 입력(한글·숫자·`=SUM`) → 상태줄 평균·개수·합계 → 2초 뒤 자동 초안(`grid-capture`, "작업 저장됨") → 리본 굵게·가운데 → 저장(Ctrl+S/버튼, "저장됨")
  → openpyxl 로 파일 확인: 값·수식·굵게·가운데·수식 캐시(=SUM → 2000) 모두 기록. 파일 탭(백스테이지: 새 통합문서·열기·정보·사본/변환·버전·보고서·사무 편집기) 표시.
  AI 작업창: D13:E14 선택 → "두 번째 열에 첫 열 값의 10%를 수식으로" → `[table:ai]` 가 values 2차원을 돌려주고 바뀌는 셀 2개가 노란 미리보기 → 반영 → E13=50·E14=30(수식 `=D13*0.1`) → 저장 → 파일에 수식+캐시 50.
  고친 것: ① Univer 를 render 중(ref 콜백의 setState)에 만들면 "nested component updates" — effect 에서 만든다 ② 부모가 매 렌더 새 `emit` 을 주어 이벤트 effect 가 재구독되며 자동 초안 타이머가 사라짐 — 콜백은 ref, effect 는 엔진에만 ③ 저장 직후 자동 초안 타이머가 상태 문구를 덮던 것
  ④ AI 제안 반영은 **바뀐 셀만 희소 행렬(절대 좌표) 한 명령**으로 — 전체 범위를 다시 쓰면 "그대로" 인 수식 셀이 값으로 덮인다(실측: D15 `=SUM` → 2000). AI 에게도 값 대신 수식을 보인다(`cellsForAI`).
  개발 모드(StrictMode 이중 실행)에서는 랜딩이 두 번 돌아 "무제 … (2).xlsx" 가 하나 더 생긴다 — 운영 빌드엔 없음.
  번들: 측정 빌드 assets 4.4MB → 16MB(비압축). 시트 엔진은 `lazy` 로 분리해 시트를 여는 화면만 내려받는다.
