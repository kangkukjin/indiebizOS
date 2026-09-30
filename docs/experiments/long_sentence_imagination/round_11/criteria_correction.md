# 事前 기준 보정
21:47 경 첫 초안 저장 호출이 감독 검토에서 미실행으로 반환됨. 자연어는 동일 숫자 중복을 요구했지만 oracle은 충돌의 추가 행까지 extra_rows에 합산했다. 입력·요구는 변경하지 않고 extra_rows는 동일 숫자 중복만 센다. 최초 expected 파일은 initial 이름으로 보존한다. 이 작성자 기준 오류를 시스템 AI 실패로 세지 않는다. 정상 중복2행+충돌1행의 최소 시험에서 extra_rows=1을 검증한다. 훈련자 최초 작성안에도 같은 잘못이 있었음을 기록한다. 실행 중 시스템 AI 재시작 없음.

## 실행 뒤 드러난 기준 오류와 독립 요청의 공백

시스템 AI 산출물과 교차 대조하여, 훈련자 IBL과 Python oracle이 모두 요율 없는 구간을 status=ok로 두었다는 오류를 확인했다. 원래 request.txt는 unpriced를 요구한다. 따라서 합격 기준을 완화한 것이 아니라 원래 요구로 복원했다. status ok는 2,842→2,812, unpriced=30이며 금액·사용량은 불변이다. initial_generator.py, main_before_status_fix.ibl, variant_before_status_fix.ibl과 로컬 expected*_before_status_fix.json에 이전 판본을 보존했다. 수정 후 주 과제·변형을 다시 실행하고 전건 대조했다.

M095의 by_meter.known_charge는 사전 oracle에서 null이지만 시스템 AI는 0이다. 구간 charge=null·미정산30·사용량420은 동일하다. 자연어 원문은 빈 집계 합계의 뜻을 명시하지 않았다. 시스템 AI에 사후 정답을 주어 재시험하거나 기준을 낮추지 않고 이 한계를 그대로 남긴다. 엄격한 사전 기준상 시스템 AI 두 실행은 부분 달성이며, 구현 결함이라는 결론은 내리지 않는다.
