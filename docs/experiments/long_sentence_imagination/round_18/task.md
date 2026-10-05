# 18회차 사전 고정

시작 2026-10-05 10:58:00 KST, 상한 11:58:00(60분). 정본 HEAD 3b07ff7e154ccc564ae60c54b838af728e5c29c0. 코어 수리 없음(훈련만).

## 자연어 요구
request.txt(기본)·variant_request.txt(변형)가 시스템 AI에 보내는 원문이다. 훈련자도 같은 요구를 풀고 출력만 trainer/ 로 바꾼다.
자료는 전부 합성: 작업 2,400(CSV 1,200·JSON 1,200, JSON 기간은 숫자·문자열 숫자·null 혼합), 선후관계 3,806줄(중복 7), 변형 지연 180줄.

## 새 연결(이전 회차와 다른 점)
**그래프 전파 = 횟수를 미리 모르는 반복(고정점)**. 1~17회차는 결합·집계·구간 겹침이었고 선후관계를 따라 값이 여러 단계 퍼지는 계산은 없었다.
앞방향(가장 빠른 시작)·뒤방향(여유) 두 번의 전파, 순환 판정(전파가 멈춘 뒤 남은 작업), 제외 사유가 겹치는 프로젝트의 우선순위(17회차 미검증 항목)를 본다.
변형은 요구 변경(지연 적용)이며 읽기·정규화·제외 판정은 그대로다 — 17회차 후속 수리(자기 결과 재사용 지시, 평가 증거 발췌, groupby 순수 효과)가 새 분야에서 통하는지도 본다.

## 완료 조건(실행 전 고정)
1. 세 파일 전건 처리, summary 8개 수치 일치(2400/60/48/12/3806/3799/403/102).
2. excluded 12건의 project·reason·detail_count 전건 일치(bad_duration 5·missing_dep 4·cycle 3; P044=bad_duration, P026=missing_dep 우선순위).
3. tasks 1,920건의 es·ef·slack·critical 전건 일치.
4. projects 48건 전건 일치.
5. top10 순서 포함 일치.
6. owners 12건 전건 일치.
7. result.json·report.md 존재, report.md 의 요약 8수치·이유별 수·상위10·팀별 임계 수가 JSON 과 일치, 규칙·근거·미확인 기재.
8. 저장 후 재읽기 확인이 실제로 수행됨.
변형: variant result.json 6섹션 일치(critical 406, longest 110) + delta.json 6키 일치(적용 133, 변경 30, 흡수 14, 미적용 41, 새 임계 39, 임계 해제 36). 기본 폴더 불변.
기준 구현 = harness/generate.py 의 독립 Python(층별 위상 정렬). 기대값 harness/expected_*.json. 기준도 틀릴 수 있으므로 두 실행자와 어긋나면 원인을 가린다.

## 분해와 계약(훈련자)
P1 준비: 읽기 3 → 기간 정규화(해석 실패=null) → 선후관계 중복 제거 → bad_duration·missing_dep 판정 → 후보 프로젝트의 작업·관계 반환(참조).
P2 일정: (작업·관계·추가기간) → 앞방향 층별 전파(repeat until) → 남은 작업=cycle → 뒤방향 전파 → 집계 → 저장·재읽기. 변형은 P1 참조 + 지연 파일만 새로 읽는다.
P3 delta: 두 P2 결과 참조 → 차이.
프로그램 안 모델 호출 0 예상.

## 실험 조건과 격리
훈련자: 조합 교재·가이드·describe 만, 내부 구현 미열람(개발 세션이라 내부 지식 완전 분리는 불가). `/ibl/execute`, origin:training.
시스템 AI: `POST /system-ai/chat` {message, origin:"training"}. 기본 → 같은 리허설 대화에 변형 후속. 입력 폴더에는 정답·생성기 없음(harness/ 는 inputs 밖, 같은 계정이라 OS 차단은 아님 → 궤적에서 접근 검사).
쓰기는 회차 폴더뿐, 외부 발송·예약 없음.

## 비용
훈련자 토큰 미측정. IBL elapsed·steps, 시스템 AI 는 episode_log.total_ms·trajectory model.usage(billable_usage). 같은 원인 2주기 무진전이면 중단.
