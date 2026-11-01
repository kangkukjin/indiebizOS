"""관측 사실이 아닌 반례: 판단 규칙의 누락된 전제를 산술로 확인한다."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 적용 건수가 1%여도 그 건의 시간이 길면 전체 평균 감소의 전부를 설명한다.
before = 99 * 4 + 804
after = 99 * 4 + 404
assert before / 100 == 12 and after / 100 == 8
assert (804 - 404) / (before - after) == 1

# 채용 건수 1.5배와 지원 2배만으로 방문자당 채용 증가를 알 수 없다.
old_visitors, new_visitors = 100, 200
old_applications, new_applications = 100, 200
old_hires, new_hires = 20, 30
assert new_applications / old_applications == 2
assert new_hires / old_hires == 1.5
assert new_hires / new_visitors < old_hires / old_visitors

# 두 해 모두 원래 지표 X를 썼어도 새 지표 Y로 감소폭이 달라질 수 있다.
old_x, new_x = 12, 8
old_y, new_y = 4, 4  # 상담 활동; X의 나머지는 대기라고 가정한 가상 경우
assert old_x-new_x == 4 and old_y-new_y == 0

result = {
    'status': 'passed',
    'kind': '가상 반례 산술; 실제 센터·사이트의 관측이나 가능성 우열을 주장하지 않음',
    'low_exposure_bound': {'counts': [99, 1], 'old_minutes': [4, 804], 'new_minutes': [4, 404],
                           'old_mean': before/100, 'new_mean': after/100,
                           'applied_fraction': .01, 'share_of_total_decrease': 1},
    'denominator_assumed': {'visitors': [old_visitors, new_visitors], 'applications': [old_applications, new_applications],
                            'hires': [old_hires, new_hires], 'hires_per_visitor': [old_hires/old_visitors, new_hires/new_visitors]},
    'redefinition_attribution': {'old_x': old_x, 'new_x': new_x, 'old_y': old_y, 'new_y': new_y,
                                 'interpretation': 'X는 두 해 모두 대기+상담, Y는 두 해 모두 상담. 지표를 바꿔 감소폭이 사라져도 연도 간 정의 변경은 없다.'},
    'experience_absence': {'observed_anecdote': False, 'compatible_worlds': ['해당 경험이 없었다', '있었으나 면담에 표현되지 않았다'],
                           'interpretation': '면담에 표현되지 않음에서 경험을 놓쳤다는 전제로 연구 방향을 닫을 수 없다. 실제 어느 경우인지는 미확인이다.'}
}
(HERE / 'counterexamples.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(result, ensure_ascii=False))
