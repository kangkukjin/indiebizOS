# 엑셀 장부 부분 편집 — [self:sheet] + PDF 표 추출

> 2026-08-07 신설. 시장 실측(ep951 크몽 조사)의 수요 실체 — 재고·입출고·근태·연차는 전부
> "기존 장부에 행을 더하고 셀을 고치는" 일이지 새 파일 만들기가 아니다 — 를 어휘화.

## 세 어휘의 분업

| 일 | 어휘 | 비고 |
|---|---|---|
| 새 xlsx 만들기 | `[table:spreadsheet]` | 값만. 기존 파일에 쓰면 수식·서식 소멸 |
| 전체 읽기 | `[self:read]` | 수식 셀은 캐시값, 캐시 없으면 수식 원문 표시 |
| **기존 장부 부분 편집** | `[self:sheet]` | 수식·서식·병합·다른 시트 **보존** |
| **PDF 표 추출** | `[self:read]{tables: true}` | table{columns,rows} 통화로 |
| **장부 눈으로 확인** | `[engines:render]{op:"xlsx"}` | 수식 **재계산**+페이지별 PNG, pdf_path 동봉 |

## 헤더 기반 행 작업 — find·append·update

```
[self:sheet]{op: "find", path: "재고장.xlsx", where: {"품목": "B형 부품"}}
[self:sheet]{op: "append", path: "재고장.xlsx", items: [{"품목": "C형", "수량": 30, "금액": "=B6*C6"}]}
[self:sheet]{op: "update", path: "재고장.xlsx", where: {"품목": "B형 부품"}, set: {"수량": 45}}
```

- **find** (기본): `where`({열: 값} 전부 일치, 생략 시 전체)·`limit`(기본 50). items 에 `_row`(행 번호) 포함.
  매칭은 문자열 정규화 + **숫자 동치**(3500 == "3,500"). 부등호 조건은 find 가 아니라
  `[self:read] >> [table:filter]` 로.
- **append**: 마지막 *데이터* 행 뒤에 추가(서식만 있는 유령 행 무시). 값이 `"=..."` 문자열이면
  수식으로 들어가고, 기존 수식(`=SUM` 합계 등)은 건드리지 않는다.
  **파이프 결합**: items 생략 시 직전 step 의 items/table 자동 사용.
- **update**: `where` **필수**(전행 갱신 사고 방지 — 먼저 find 로 확인). 매칭된 모든 행에 `set` 적용.
- 공통: `sheet`(생략 시 활성 시트) / `header_row`(헤더가 1행이 아니면 지정) / 저장은 원자 교체.
- `.xlsm` 은 keep_vba 로 매크로 보존. 쓰기 op 는 RED 구역 경로 가드를 지난다.

## PDF → 장부: 시장의 "수기 옮기기" 노동이 한 줄

```
[self:read]{path: "거래명세서.pdf", tables: true} >> [self:sheet]{op: "append", path: "재고장.xlsx"}
[self:read]{path: "견적서.pdf", tables: true} >> [table:sort]{by: "단가"} >> [table:spreadsheet]{path: "정렬본.xlsx"}
```

`tables: true` — 전 페이지의 표를 추출해 가장 큰 표를 `table{columns,rows}` 통화로(read_xlsx 와
같은 계약), 나머지는 `tables` 목록에. PDF 표의 첫 행이 헤더로 간주되므로 append 대상 장부의
열 이름과 맞아야 한다(다르면 `table:select` 로 먼저 다듬기).

## 편집 후 검수 — 장부를 눈으로 확인하기 (2026-08-27, [engines:render]{op:"xlsx"})

sheet 로 편집한 직후의 장부는 **수식 캐시가 낡아 있다** — [self:read] 가 보여주는 계산값은
Excel 이 마지막으로 열었을 때 것이다. `[engines:render]{op:"xlsx"}` 가 LibreOffice 헤드리스로
수식을 **재계산**해 페이지별 PNG 로 투영한다(원본 불변·재계산 PDF 경로 `pdf_path` 동봉).

```
# 편집 → 지각 → 심사 (취향 파일 "sheet" — #### 잘림·수식 오류 노출·페이지 절단 검사)
[self:sheet]{op: "append", path: "재고장.xlsx", items: [{"품목": "C형", "수량": 30}]} >>
  [engines:render]{op: "xlsx", path: "재고장.xlsx"} >>
  [table:each]{do: "[engines:image_read]{op: 'critic', image_path: '$it.path', intent: '새 행이 표에 맞게 들어가고 합계가 성립하는가', criteria: 'sheet'}"}

# 계산된 값을 텍스트로 확인 (재계산 PDF 를 변수 필드로)
$r = [engines:render]{op: "xlsx", path: "정산표.xlsx"}
[self:read]{path: "${r.pdf_path}"}
```

op 를 생략해도 path 확장자(.xlsx/.xlsm)로 자동 라우팅되므로 `화면검수` 워크플로우
(`params: {path: "장부.xlsx", criteria: "sheet"}`)에 그대로 넣을 수 있다.
**비용 계층화(0층)**: render 행의 `prescreen` 에 무비용 기계 관측(빈 쪽·수식 오류 표식
#REF!/#DIV/0! 등)이 실리고, critic 에 `prescreen: '$it.prescreen'` 으로 넘기면 걸린 쪽은
**비전 호출 없이** 즉시 실패 verdict(tier: prescreen) — 유료 심사는 깨끗한 쪽만 받는다.
LibreOffice 가 없으면 설치 안내와 함께 정직 실패(맥 `brew install --cask libreoffice`).
매크로(.xlsm)는 렌더 시 실행되지 않는다(보안상 정상).

## 함정

1. **기존 append/update는 복잡한 차트·이미지의 저장 보존을 보장하지 않는다** (openpyxl 한계). 차트가 든 장부는 데이터 시트와 차트 파일을
   분리해 두는 것이 안전. 로고 박힌 견적서 템플릿 편집엔 부적합. (렌더 지각 자체는 차트를
   보지만, sheet 로 **저장한** 파일은 이미 유실 후일 수 있다.)
2. **PDF 표 추출은 실선 표 기준** (PyMuPDF find_tables). 선 없는 표·스캔 이미지 PDF(OCR 필요)는
   못 잡을 수 있다 — `tables_found: 0` + note 로 정직하게 알림.
3. **PDF 추출값은 전부 문자열**. 숫자 연산이 필요하면 table 파이프(`filter`/`sort`)가 자동
   숫자화하거나, 장부 쪽 수식이 계산하게 하라.
4. items 의 열 이름이 시트 헤더와 다르면 **실행 거부 + 실제 열 목록 반환** (조용한 오배치 방지).
5. 헤더가 1행이 아닌 장부(제목 행이 위에 있는 양식)는 `header_row` 를 지정.

## A1 범위·서식 편집 — range / range_write

```ibl
[self:sheet]{op:"range", path:"장부.xlsx", sheet:"매출", range:"A2:C5"}
```

`items`는 셀별 `cell`, `value`, `formula`, `formula_type`, `style_id`, 바깥 `sha256`은 파일 버전이다.
value는 저장된 캐시이므로 최신값이 필요하면 calculate를 실행한다.
범위는 A1 또는 A1:C10, 최대 10,000셀. sheet 생략 시 활성 시트.

```ibl
[self:sheet]{op:"range_write", path:"장부.xlsx", expected_sha256:"range에서 읽은 해시", range:"A2:B3", values:[[110,5],[220,6]], format:{bold:true,number_format:"#,##0"}, output:"장부_수정.xlsx"}
```

values는 범위와 정확히 같은 크기의 2차원 배열이다. 숫자·문자열·불리언·null(비움),
`=`로 시작하는 수식을 쓴다. format만 지정해 서식만 바꿀 수도 있다.
format은 bold와 Excel number_format만 지원한다. 원본과 별개의 파일을 만들며
기존 결과는 덮어쓰지 않는다. `.xlsx`·`.xlsm` 지원, 매크로 실행 없음.
선택한 셀·관련 서식·계산 캐시 외 ZIP 데이터를 보존하므로 차트·다른 시트의 데이터를
유지한다. 값을 바꾼 뒤에는 전체 수식 캐시를 비우고 재계산 필요로 표시한다.
병합 범위에 걸치는 편집, 보호된 시트, 공유·배열·데이터표 수식이 든 시트는 거절한다.

## 실제 계산값을 XLSX에 저장 — calculate

```ibl
[self:sheet]{op:"calculate", path:"장부_수정.xlsx", output:"장부_계산.xlsx", timeout:60}
[self:sheet]{op:"range", path:"장부_계산.xlsx", range:"C2:C5"}
```

LibreOffice가 임시 사본에서 실제로 계산하고 **계산 캐시만 원래 구조에 옮긴** 결과 XLSX를
저장한다. 원본 수식·차트·그림 등은 보존한다. 차트 자체에 내장된 표시 캐시는 갱신하지
않으므로 차트 화면 갱신은 문서 편집기에서 확인한다. Excel 전용 수식은 엔진에 따라
차이가 있을 수 있으며 오류 셀은 숨기지 않는다.

- LibreOffice 필요: 시스템 설치/PATH 또는 `SOFFICE_PATH`. 없으면 dependency_missing.
- timeout 1~120초(기본 60). `.xlsx`만 지원. 외부 링크·매크로·공유/배열/데이터표·외부 자원
  수식은 거절한다. 임시 독립 프로필에서 매크로를 차단한다.
- 성공 결과의 `items`는 수식 셀의 계산값이다. 계산 오류가 있으면 결과 파일은 남기되
  `success:false`, `recalculated:true`, `errors`로 셀별 오류를 알린다.
- 출력 생략 시 `<원본명>_calculated.xlsx`. 이 기능이 저장한 파일을 range/read로 읽어야
  갱신된 캐시를 본다. PNG/PDF 화면 검수는 기존 engines:render가 담당한다.
