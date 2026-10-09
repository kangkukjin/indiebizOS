# 홍보 준비 1바퀴 — 결과 보고 (2026-10-09)

실제 발행·게시·발송·예약은 하나도 하지 않았다. 발행 결정은 사용자 몫.

## 1. 고객 목소리 — 축별 건수
123행 = 유효 111 + 제외 12 (광고 4: R109·R114·R115·R120 / 무관 8: R110·R111·R112·R113·R116·R117·R118·R119). 미배정 0.

| 순위 | 축 | 건수 |
|---|---|---|
| 1 | P1 시간 부족 | 31 |
| 2 | P2 초보 불안 | 24 |
| 3 | P3 긴 과정·등록 부담 | 18 |
| 4 | P4 혼자 하다 실패 | 13 |
| 5 | P5 비용·맡기는 번거로움 | 13 |
| 6 | P6 버리기 아까움 | 12 |

대표 인용 12건(축당 2)은 brief.md §3·analysis/voice_axes.json 에 있다. 원문 문자열과 일치하는지 기계로 대조했다(불일치 0).
교차 검사: 판정 CSV를 table:groupby로 다시 집계한 값이 스크립트 결과와 같다.
주의: 같은 문장이 꼬리말만 바뀌어 반복된 행이 많다. 행 단위로 셈으며, 같은 사람이 반복해 쓴 글인지는 미확인이다. P2와 P4를 한 축으로 합치면 37건으로 1위가 된다. 순위는 축 정의에 따라 달라진다.

## 2. 금지어 검수
검수 필요 0건이다. 대상은 A1~A3의 후킹·해결·CTA·카드 하단 문구, 카피 후보 5개, 한 줄 정의이며 금지어 6개를 부분 문자열로 대조했다. 후킹에 브랜드명이 들어간 소재도 0건이다. 걸린 것이 없어 고친 문구도 없다. (copy/banned_word_check.json)

## 3. 검색어 근거 — 9칸 모두 조회됨(미확인 0)
네이버 검색 응답의 total_estimate(결과 건수)를 2026-10-09 12:35에 조회했다. 검색량이 아니라 이미 쓰인 글의 수이므로 간접 지표다.

| 검색어 | blog | cafe | kin |
|---|---|---|---|
| 옷 수선 배우기 | 59,515 | 47,835 | 5,321 |
| 바느질 기초 클래스 | 13,422 | 1,261 | 44 |
| 단추 달기 방법 | 105,633 | 63,721 | 17,702 |

## 4. 생성 파일 (모두 out/ 아래, 다시 읽어 확인)
- brief.md, brief.json (양식 7항목, RTB는 verified 2건만 넣었고 '지역 신문 소개'는 제외, 카피 후보 5)
- analysis/: review_judgments.csv(123행 행별 판정), voice_axes.json, competitors.json, search_terms_evidence.json, classify_run_result.json
- assets/A1~A3/: image.png(1:1, Gemini 생성 성공), card.png(1080×1080), card.html, copy.json
- copy/: assets_copy.json, banned_word_check.json, build_result.json
- bundle/: nostr_longform_draft.md(DRAFT), checklist.md, channel_guide.md
- campaign_ledger.json (A1~A3, draft, 성과 null. 두 번 재실행해도 행이 중복되지 않음을 확인)
- scripts/: classify_reviews.py, build_campaign.py

## 5. 이미지 검수 (image_read critic)
1차 검수에서는 A2가 불합격(6점)이었다. 한글 어절이 중간에서 줄바꿈되고 여백이 치우쳐 있었다. 문구는 그대로 두고 레이아웃만 고쳐(keep-all 적용, 세로 배치) 다시 검수했다. 결과는 A1 8점, A2 8점, A3 7점으로 모두 합격이다.
남은 경미한 점은 세 가지다. A2 일러스트에 손 해부학이 어색한 곳이 보인다. A3는 CTA에서 '2만 / 5천원'이 두 줄로 나뉘고, 일러스트에 살구색 계열이 섞여 있다. 사용자 확인 대상이다.

## 6. 절차 메모
분류 스크립트를 처음 실행할 때 [self:script]가 시스템 작업 폴더(~turn)의 경로만 받아서, 그곳에 스크립트 사본 1개가 남았다. 시스템 임시 폴더이며 7일 뒤 자동 정리된다. 이후 실행은 모두 out/scripts 의 파일을 직접 돌렸고, 산출물은 전부 out/ 에만 썼다.
