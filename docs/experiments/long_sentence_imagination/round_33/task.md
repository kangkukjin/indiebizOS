# 33회차 사전 과제 — 다단계 자재명세서(BOM) 전개와 소요량·부족량 산출

자연어 원문: [request.txt](request.txt) · 변형: [variant_request.txt](variant_request.txt)

## 선정 이유
19~32회차는 평면 표의 결합·집계였다. 이번 축은 **깊이를 모르는 트리의 전개**다. IBL 명세는 "재귀는 지원하지 않는다"고 못 박았으므로
(ibl.md 「작성과 검사」), 깊이 5~8의 구성 트리를 `[repeat:while]` + `table:join` 한 층씩 전개로 표현할 수 있는지, 순환을 값으로
멈출 수 있는지, 함수 깊이 64·반복 행 1만·단계 10만 예산과 어떻게 만나는지를 본다. 저장된 정답 관용구는 없다.

## 입력(합성, `outputs/long_sentence_imagination/2026-10-07_33회차/source/{base,cycle}/`)
- parts.json 270행(제품 10·반제품 60·구매품 200), bom.json 209행(base)/210행(cycle), orders.json 20행, stock.json 183행(구매품 180 + 반제품 3 — 집계 대상 아님, 구매품 20개는 재고 없음).
- qty_per 는 정수와 소수(0.5·0.25·1.5)가 섞여 있다. 같은 모듈이 여러 제품·여러 경로에 쓰인다(다이아몬드).
- cycle 변형: 첫 주문 제품의 1→2→3층 경로 끝에서 1층으로 되돌아가는 간선 1개, parts 에 없는 R999(구매품 자리)·S99(반제품 자리), 구성을 전부 뺀 반제품 1개.
- 생성기·oracle = `harness/prepare.py`(독립 Python, 재귀 DFS). AI 에게는 `source/` 사본만 준다.

## 완료 조건(실행 전 고정, oracle 과 전건 대조)
1. orders 20행 전건, status(산출/순환)·leaf_rows 가 oracle 과 일치, cycle_path 는 bom 간선으로 이어지고 마지막 원소가 앞에 다시 나오는 유효한 순환 경로(여러 순환이 있으면 어느 것이든). 순환 주문은 집계 제외.
2. requirements 는 oracle 과 part 집합·gross(십진 정확)·on_hand·shortage·status 전건 일치. base 기대: 68행(충분 39·부족 26·재고 미상 3).
3. 재고 없는 구매품의 shortage=null·"재고 미상"(0 추정 금지). parts 에 없는 부품 "정의 없음", 구성 없는 비구매품 "구성 없음".
4. depth_by_product·max_depth(base 5)·events(base 209) 일치.
5. result.json 저장 후 재독 일치, report.md 에 주문 표·부족 상위 10·재고 미상/정의 없음/구성 없음·순환 경로 절 존재.
6. 입력 8파일 바이트 불변.

## 변형
- A(견고성, 같은 프로그램·다른 입력): source/cycle. 기대 = 순환 주문 N건 "순환"+경로, 나머지 정상, R999 "정의 없음", 구성 뺀 반제품 "구성 없음", 반복이 끝나고(무한 전개 아님) 정상 종료.
- B(변경 용이성): 주문 O007 수량을 2배로 바꾼 입력 사본으로 같은 프로그램을 `reuse` 로 재실행 — 읽기 영수증 재사용 여부·변경 집계만 바뀌는지 관측(기대값은 oracle 재계산).

## 작성 조건
공개 교재(ibl_composition·tools)·ibl.md·`describe`(join·groupby·each·write)만 참고. 소스 미열람(내부 지식 분리 불가는 밝힘).
상한 60분. Python 은 자료 생성·HTTP 운반·독립 대조만. 독립 AI: `/system-ai/chat` background + origin training, 같은 request.txt + 경로.
