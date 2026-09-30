# 8회차 task — 6회차 가계부 과제를 자연어로 시스템 AI에 맡김 (2026-09-30)

요청 원문:

> 2025년 가계부 연간 결산해 줘. /Users/kangkukjin/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-09-30_8회차/input 의 ledger 폴더에 월별 카드 내역 CSV 12개가 있고, rules.json 에 가게→분류 규칙, fixed.json 에 매달 나가야 하는 고정지출 목록이 있어. 규칙으로 분류하고 규칙에 없는 가게는 AI 로 분류하되 AI 가 붙인 분류는 표시해 줘. 월별·분류별 지출 표, 같은 날 같은 가게 같은 금액이 두 번 찍힌 중복 결제 의심, 고정지출이 빠진 달이나 금액이 평소와 다른 달, 분류별로 평소보다 지출이 크게 튄 달(다른 달 평균의 2배 이상), 구독 중에 서로 겹치는 서비스(음악 둘, 영상 둘 같은 것)를 찾아 줘. 환불(음수)은 지출에서 빼고 따로 합쳐 줘. 못 읽은 파일이나 금액을 못 읽은 줄은 따로 알려 줘. 사람이 볼 보고서(md)와 후속 처리용 이상 목록(json)으로 /Users/kangkukjin/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-09-30_8회차/out 폴더에 report.md, anomalies.json 으로 저장해 줘.

6회차 원문에 자료·저장 위치만 더함. 입력은 6회차 input 에서 ledger·rules.json·fixed.json 만 복사(expected.json·gen.py 는 정답이 새므로 제외).
완료 조건 8개와 기대값 = docs/experiments/long_sentence_imagination/round_6/task.md·input/expected.json. 기준선 = 6회차 훈련자(원래 달성 7/8, 14분, 수정 P1 2·P2 2, opus 3요청 17,862/1,415·Jev 3요청).
훈련 표식 없음(사용자 결정), /system-ai/chat.
