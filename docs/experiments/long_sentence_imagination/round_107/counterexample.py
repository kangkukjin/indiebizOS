"""6개월 합계 -30%만으로 개점 전 감소를 추론할 수 없다는 결정론적 반례."""
import json
from pathlib import Path
prior=[100,100,100,100,100,100]
only_after=[100,100,100,100,10,10]
already_before=[60,60,60,60,90,90]
assert sum(only_after)==sum(already_before)==420
assert sum(prior)==600
assert sum(only_after[:4])==sum(prior[:4])
assert sum(already_before[:4])<sum(prior[:4])
out={'units':'가상 동일 금액 단위, 전년 각 월=100','opening':'최근 두 달 시작 시점',
     'prior_monthly':prior,'only_after_opening':only_after,'decline_before_opening':already_before,
     'six_month_totals':{'prior':600,'both_current':420,'decline_percent':30},
     'conclusion':'동일한 6개월 합계 감소율에서 개점 전 감소의 존재가 달라진다. 주어진 요청만으로 앞 4개월 감소를 확정할 수 없다.',
     'scope':'계획의 전제 반례이며 실제 서점 데이터·경쟁점 인과효과 증거가 아니다.'}
p=Path(__file__).with_name('counterexample.json');p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(out['conclusion'])
