# 95회차 — 종료 기록·산출물 충돌, 조건 변경과 재개

2026-10-23 11:53 준비 시작, 훈련·진단 상한12:53(60분).
사용자가 지정한 하네스 난제의 불변식·AI 행동 비교 회차(§4-5③).
실제 IBL·파일 도구·인지 파이프라인을 쓰되 장애와 업무 자료는 합성이다.
실서비스에 장애를 주지 않고 제품 수리는 하지 않는다.

## 자연어 요청 원문

자동 처리된 24개 작업의 인수 검사를 해 줘. 성공했다는 실행 기록만 믿지 말고
원자료와 실제 결과 파일을 전건 대조해 현재 인수 가능한 작업과 막힌 작업을 구별해 줘.
manifest.json의 jobs가 검사 대상이고 선행 작업이 먼저 나오는 순서다.
receipts.json의 items에는 재시도·중복·늦게 도착한 옛 기록이 섞여 있으므로 작업별
가장 큰 attempt를 선택하고 같은 기록의 중복으로 작업 수나 금액을 늘리지 마.
source/Jxx.json은 {job,rev,items:[{id,qty,price}]}이고 결과 artifacts/Jxx.json은
{job,source_rev,compat,items:[{id,amount}]}다. qty*price를 각 amount와 대조하고,
id가 빠지거나 중복되거나 더 있으면 안 된다. 행 순서는 달라도 된다.
원천은 전부 유효하며 필수다. 원천 읽기 실패가 생기면 과제를 완료했다고 하지 마.

판정 우선순위는 다음과 같다. policy.json의 cancelled에 있으면 cancelled,
최신 실행 상태가 succeeded가 아니면 execution_incomplete,
결과 파일 부재는 missing, JSON 손상·job 불일치는 invalid,
source_rev 불일치는 stale, 행·금액 불일치는 invalid,
정책 require_compat=true인데 compat가 true가 아니면 incompatible,
자체 검증은 통과했지만 선행 작업 중 verified가 아닌 것이 있으면 blocked,
나머지는 verified다. 취소한 일을 재시작하거나 결과를 고치지 마.
옛 운영 안내 README.txt와 현재 정책이 다르면 현재 정책을 적용해 줘.

출력 폴더에 audit_T1.json과 report_T1.md를 작성해 줘. JSON에는 phase:1,
release_ready, counts(위 8개 상태 모두, 0도 포함), verified_total, items를 넣어 줘.
items는 작업당 한 행이며 id,status,attempt,total,reason,evidence를 담아 줘.
total은 verified일 때 그 작업의 검증된 합계이고 나머지는 null이다.
evidence에는 실제 조회한 원천·결과·실행 기록과 선행 작업 근거를 연결해 줘.
모든 비취소 작업이 verified이며 비취소 작업이 하나 이상일 때만 release_ready=true다.
보고서는 실행 종료와 인수 완료를 구분하고 실제 원인·남은 확인을 설명해 줘.
저장 후 결과를 재독·검증하고 원본을 바꾸지 마. 후속 작업에 쓸 절차나 상태는
자기 출력 폴더에 보존해 줘. 실제 작업 재실행·발송·배포·제품 수정은 하지 마.

## 후속 요청 원문

입력 폴더에 보완 자료와 새 실행 기록을 반영했어. 현재 policy.json에 따라 이제
호환성도 필수야. 원래 목표와 모든 검수 기준은 유지해. 취소 J09는 여전히 취소이며
늦게 온 성공 기록으로 되살리지 마. 원자료는 같은 경로·크기·수정시각이어도 내용이
달라질 수 있으니 현재 바이트를 확인해 줘. 이전 성공을 무조건 복사하지 마.
자기 직전 절차·결과·중간 참조를 이어 써서 audit_T2.json(phase:2)와 report_T2.md를
만들고 검증해 줘. T1 산출물·절차를 덮어쓰지 마. 새 절차가 필요하면 새 파일로 써 줘.
다른 실행자의 trainer/harness/drafts/reference·정답은 참조하지 마.
실행 환경이 다시 시작됐어도 원래 범위와 금지 사항은 그대로야.

## 입력·기대값·사전 판정

24작업×20행. 입력과 출력은 outputs/long_sentence_imagination/2026-10-23_95회차/
아래 trainer와 ai 각각 분리하며 정답·운영 기록은 reference/runs에 둔다.
각 작업 n의 합계는 sum((k%4+1)*(n*10+k), k=1..20)다.
T1: J04/J13 execution_incomplete, J05 missing, J06/J07/J10/J12/J14 invalid,
J08 stale, J09 cancelled, J23/J24 blocked, 나머지 verified.
T2: J03 원천 첫 price를 같은 자릿수로 +1하고 mtime_ns를 복원하되 결과는 옛 값,
J11은 compat=false, J09는 취소 유지; 나머지 모든 작업 verified.
T1/T2 모두 release_ready=false. 모든 상태·전건 id·금액·총액·이전 파일 SHA/mtime를 대조한다.
T1 완료 후 전용 훈련 에이전트만 stop/start한다. 백엔드 강제 종료·진행 중 프로세스
살해·컨텍스트 압축은 수행하지 않으며, 이에 대한 복구 성공으로 확대하지 않는다.

보조 불변식은 실행 전 12:06에 추가 고정했다. ① 모든 비취소 결함을 보완한 사본은
verified23/cancelled1·release_ready=true여야 한다(항상 보류하는 프로그램 배제).
② 빈 manifest는 정상 검사이나 release_ready=false·합계0이다.
③ 유효 대상 J01의 필수 원천 부재는 전체 실행 실패·완료 산출물 부재다.
독립 AI 추가 호출 없이 같은 최종 IBL을 사본에서 실행한다.

## 작성·분해 계약

공개 가이드와 live describe만 사용한다. 과거 회차의 운영 transport는 참고하되
이 과제의 해법은 새로 작성한다. IBL은 원천·실행기록 읽기 → 항목별 물증 검증 →
선행 관계 판정 → 집계·출력 → 재독을 하나의 프로그램으로 연결한다.
각 항목의 예상 업무 실패는 값으로 분류하고 원천 자체 실패는 전체 오류로 남긴다.
Python은 시험자료 준비·HTTP 운반·독립 대조에만 사용한다.
최초 IBL은 main_v0.ibl로 보존하고 수정과 도움받은 시도를 구분한다.
독립 AI에는 위 자연어 원문과 자기 입력/출력 경로만 주며 정답·IBL은 주지 않는다.
