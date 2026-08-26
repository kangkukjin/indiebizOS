# [engines:render]{op:"xlsx"} 핸드오프 (2026-08-26 설계 → **2026-08-27 집행 완료**)

> **집행 결과 (2026-08-27)**: Phase 0~5 전부 완료. LibreOffice 설치(brew cask) · 재계산 관문
> 첫 실측 GREEN(OOXMLRecalcMode=0 **실측 확정** — 캐시 없는 =A1+A2 가 PDF 텍스트에 5) ·
> `render_op_xlsx`(임시 프로파일·원자 검증·pdf_path 동봉) · op 확장자 추론(Phase 1.5) ·
> 어휘 정의+빌드 `--check` GREEN · `data/criteria/sheet.yaml` · 시드 10건(+distilled 824) 색인·
> 회상 top-1 확인 · 계약 배터리 **10건** GREEN · 라이브 종단 2회(명시 op + 추론, 재계산 값
> 15000/14000/29000 픽셀 실증) · handler 오류 계약 회귀 GREEN.
> **곁수리(설계에 없던 실측 결함)**: 맥 헤드리스 LibreOffice 는 시스템 폰트 폴백이 죽어 있어
> **한글이 텍스트 층에만 있고 픽셀에서 조용히 증발**했다(폰트명 명시·기본 프로파일·샌드박스
> 무관 — 번들 라틴 폰트만 임베드). 수리 = 임시 프로파일 `user/fonts` 에 CJK 시스템 폰트
> 심볼릭 링크(`_link_fallback_fonts`, AppleGothic·AppleSDGothicNeo·Arial Unicode). 관문 =
> 한글 잉크 픽셀 검사(test_korean_glyphs_not_silently_lost — OS·폰트명 무관 판정).
> 잔여: ⏳풀 재학습 대기열 합류(시드 10) · 실사용 관찰(sheet 편집→검수 파이프 실전) ·
> 리눅스 한글 폰트(fonts-nanum)는 실사용 등장 시.

> 목적: 장부(xlsx/xlsm)의 피드백 3층 중 아직 열려 있는 두 층을 **외부 실행기 하나로 동시에** 닫는다.
> ② 수식 층 — [self:sheet] 편집 후 **계산된 숫자**를 관찰할 길이 없다(캐시는 낡음, 현행은 정적 분석 예측뿐).
> ③ 시각 층 — 장부의 겉모습(##### 잘림·열 폭·서식)을 볼 길이 없다.
> 통로: xlsx → **LibreOffice 헤드리스(재계산+투영)** → PDF → 기존 `render{op:pdf}` 픽셀화 →
> `each critic` / GoalEval — ARTIFACT_PERCEPTION(2026-08-26) 기반시설 전부 재사용. 지을 것은 변환기 한 칸.

## 0. 탐사로 확정된 전제 (2026-08-26 실측)

1. **이 맥에 LibreOffice 가 없다** (`/Applications`·brew·Spotlight 모두 부재). Phase 0 = 설치가 선행 조건.
   soffice 는 pip 아닌 **시스템 의존성** — 부재 시 op:xlsx 만 정직 실패하고 다른 op 는 무영향이어야 한다.
2. **LibreOffice 는 xlsx 수식을 기본으로 재계산하지 않는다**(저장된 캐시값 사용). 재계산 강제는
   프로파일 설정 `org.openoffice.Office.Calc/Formula/Load/OOXMLRecalcMode`(0=항상 재계산으로 추정 —
   **enum 값은 집행 시 실측 필수**, Phase 0 관문이 겸한다). 이걸 빼먹으면 **낡은 숫자가 찍힌 그림을
   "관찰했다"고 믿는** 최악의 침묵 — 이 설계 전체의 존재 이유가 무너지는 지점이라 기계 관문으로 못박는다(§Phase 0).
3. **헌법 정합 확인**: xlsx 는 인쇄 투영 명세(페이지 설정·인쇄 영역)를 형식 안에 가진다 — render 의
   "자기 투영법을 가진 형식의 결정론적 픽셀화" 요건 충족. 판단 없음 유지(재계산은 계산이지 판단이 아니다).
   **원본 파일은 절대 불변** — 재계산은 LibreOffice 메모리 안에서만, 산출은 별도 PDF/PNG (지각 순수성).
4. **지을 것이 적다**: 변환 후엔 `render_op_pdf`(PyMuPDF·max_pages 정직 보고·GoalEval 절대경로 연동)를
   그대로 태운다. `화면검수` 워크플로우·`data/criteria/` 취향 파일·`each critic` 조합도 문장 변경 없이 재사용(§Phase 1.5).

## Phase 0 — LibreOffice 설치 + 재계산 실측 관문 ★선행 조건

- 설치: `brew install --cask libreoffice` (맥). 리눅스 `apt install libreoffice-calc`, 윈도우 공식 인스톨러 —
  정본 설치 경로 문서(3 OS)에 "선택 의존성: 장부 렌더" 로 한 줄 기재.
- **재계산 관문 fixture** (pytest 계약 배터리에 상주):
  1. openpyxl 로 `A1=2, A2=3, A3="=A1+A2"` 파일 생성 — openpyxl 은 캐시값을 안 쓰므로 A3 캐시 없음.
  2. op:xlsx 실행 → 중간 PDF 를 PyMuPDF `get_text()` 로 열어 **"5" 가 있어야 GREEN**.
  3. 캐시 없는 수식이 빈칸/0 으로 나오면 재계산 미작동 = RED — 프로파일 시딩이 안 먹은 것.
  - 이 관문이 OOXMLRecalcMode enum 실측을 겸한다(0 이 아니면 값을 바꿔가며 GREEN 을 찾고 문서에 실측값 기록).
  - "카운터 말고 관문" 원칙 그대로 — 재계산 여부는 사람이 눈으로 확인하는 게 아니라 테스트가 실패시킨다.

## Phase 1 — `render_op_xlsx` (render_artifact.py 확장)

- **soffice 발견** `_find_soffice()`: ① env `SOFFICE_PATH` → ② `shutil.which("soffice")` →
  ③ OS별 후보(`darwin`: `/Applications/LibreOffice.app/Contents/MacOS/soffice` / `win`:
  `C:\Program Files\LibreOffice\program\soffice.exe`(+x86) / 리눅스: `/usr/bin/soffice`).
  부재 시 정직 실패: `{"success": false, "error": "...설치: brew install --cask libreoffice"}` —
  B21-1 규약(평문 오류 금지) 준수. windows-portability 위험지대(data/packages/)라 3 OS 후보 필수.
- **실행마다 임시 프로파일**: `-env:UserInstallation=file://<output_base 하위 임시 디렉토리>` + 그 안에
  `user/registrymodifications.xcu` 를 매번 생성(OOXMLRecalcMode·ODFRecalcMode 시딩, 몇 줄짜리 XML).
  사용자 프로파일 오염 0 · 동시 실행 레이스 0. 첫 기동 1~3s 비용은 수용(결정론이 우선).
- **변환**: `soffice --headless --norestore --convert-to pdf --outdir <tmp> <src>` + timeout(기본 120s,
  param 으로 조정). 실패/타임아웃 = 정직 오류(변환 로그 꼬리 동봉).
- **픽셀화**: 나온 PDF 를 **`render_op_pdf` 에 위임**(scale·max_pages·pages·truncated 정직 보고 전부 승계).
  행의 `op` 는 `"xlsx"` 로 바꿔 단다. 결과 extra 에 **`pdf_path`(절대 경로) 동봉** — 이게 ②층의 텍스트 통로:
  `[engines:render]{op:"xlsx", path:"재고장.xlsx"}` 후 `[self:read]{path: <pdf_path>}` 로 **계산된 숫자를
  텍스트로** 읽는 조합이 열린다(새 param 없이 조합이 해결 — param 증식 금지 원칙).
- **.xlsm**: 렌더 대상 O. 매크로는 헤드리스에서 실행되지 않음(보안상 정상) — desc 에 명시.
- 대상 확장자 검증: `.xlsx/.xlsm` 외 정직 거절(sheet_ops `_resolve` 와 같은 어투로 대안 어휘 안내).

## Phase 1.5 — op 확장자 추론 (화면검수 워크플로우 무수정 연동)

- 현행: op 생략 = 무조건 html → `화면검수`($path)에 xlsx 를 주면 바이너리를 html 로 렌더하는 오배치.
- 개정: **op 명시 없음 + path 있음 → 확장자로 결정론 라우팅**(.pdf→pdf, .svg→svg, .xlsx/.xlsm→xlsx,
  .html/.htm→html). path 없음(html/svg 문자열·파이프 통화)은 현행 기본 html 유지. 명시 op 항상 우선.
- handler.py 디스패치 분기 몇 줄 — `_OP_DEFAULTS` 는 유지(선언상 기본은 여전히 html), 추론은 path 가
  있을 때만의 정련. 기존 호출 전부 하위호환(오히려 op:pdf 누락 오류가 사라짐). `화면검수`·얼린 문장 무수정.
- 주의: xlsx 는 뷰포트 무의미(pdf 와 동일) — viewports 지정 시 무시하고 note 로 알림(조용한 무시 금지).

## Phase 2 — 어휘 정의 (ibl_actions.yaml src)

- `ops.values` 에 `xlsx: XLSX/XLSM 장부 → LibreOffice 재계산 → 페이지별 PNG 1행 (pdf_path 동봉 — self:read 로 계산값 텍스트 확인)`.
- params 추가: `timeout: integer` (xlsx 전용, 기본 120). target_description 에 xlsx 절 + op 추론 규칙 서술.
- `achievement_criteria` 갱신: "xlsx — PNG 의 수식 셀 값이 **캐시가 아닌 재계산 값**(Phase 0 fixture 가 보증),
  soffice 부재 시 설치 안내를 담은 정직 실패".
- `_OP_DISPATCHERS["render_artifact"]["xlsx"] = render_op_xlsx` (handler.py — AST 삼각검증 대상).
- `python3 scripts/build_ibl_nodes.py && --check` GREEN.

## Phase 3 — 취향 파일 `data/criteria/sheet.yaml` (최소치)

- `extends: visual_base` + 장부 전용 체크 4~6개만(증축은 사용례가 이끈다):
  숫자 열이 `#####` 로 잘리지 않는가 / 열 폭이 내용에 맞는가 / 합계·소계 행이 데이터와 시각적으로 구분되는가 /
  표가 페이지 경계에서 행 중간 절단되지 않는가 / 통화·날짜 표시 형식이 열 안에서 일관되는가.
- `forbidden`: 수식 오류 표식(`#REF!`·`#DIV/0!`·`#VALUE!`) 노출 — **이게 ②층 심사의 시각 그물**이다.

## Phase 4 — 시딩·재색인 (규약 준수: .venv 파이썬 · add_examples_batch 단일 경로 · distilled 병기)

- 8~12건: op:xlsx 단독(경로·scale·pages 변주) / `화면검수`{path: 장부, criteria: "sheet"} /
  **[self:sheet]{op:"append"} 후 render{op:"xlsx"} >> each critic** (편집→지각→심사 전체 루프) /
  render 후 `[self:read]{path: pdf_path}` 로 계산값 확인(②층 텍스트 통로) / repeat·goal 재시도 형태 각 1.
- 후처리: `rebuild_index()` → `scripts/ibl_param_sweep.py`.

## Phase 5 — 검증·문서·재기동

- pytest 계약: Phase 0 재계산 관문 / soffice 부재 mock 정직 실패 / .csv 등 타 확장자 거절 /
  truncated 승계 / viewports 무시 note / 원본 mtime 불변(지각 순수성).
- 문서 표면(new_action_checklist 규약): guides/sheet.md 에 "편집 후 검수 파이프" 절 + 함정 갱신
  (②층 예측→관찰 승격, 차트 유실 한계는 **openpyxl 저장 시**의 일이고 렌더 지각은 차트를 본다 — 단 sheet 로
  저장한 파일은 이미 유실 후일 수 있음을 명시) / criteria 가이드에 sheet.yaml 한 줄 / technical.md 선택 의존성.
- **재기동**: render_artifact.py 는 spec-load 서브모듈 — `/packages/reload` 로 안 산다, 백엔드 재기동 필요.

## 곁가지 (범위 밖)

- 단일 시트만 렌더(`sheet` param): LibreOffice 헤드리스에서 시트 선택은 매크로 경유라 복잡 —
  보류. 재론 조건: 수십 시트 장부에서 max_pages 잘림이 실사용 불편으로 등장.
- CognitiveEval `_VISUAL_EXTS` 에 xlsx 부재 — render 가 PNG 로 내리므로 무해(ARTIFACT_PERCEPTION 곁가지와 동일 판단).
- 계산값의 구조적(셀 좌표 단위) 텍스트 관찰 — pdf_path 텍스트 추출로 당장 충분. 재론 조건:
  "몇 행 몇 열의 값" 단위 검증 수요가 실사용에 등장하면 그때 sheet 쪽 어휘로(read 계열, render 밖).
