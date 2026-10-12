"""Post-repair boundary fixture; clarified contract is fixed before executing."""
import json,shutil
from prepare import OUT,write
root=OUT/'repair_boundary'
shutil.copytree(OUT/'repair/input',root/'input')
(root/'out').mkdir();shutil.copy2(OUT/'repair/out/task.md',root/'out/task.md')
clarification='''\n\n## 수리 후 경계 계약 (기존 AI 실행에 소급하지 않음)
이 시험에는 누락 요구, 같은 판본의 모순, 오래된 검수, 키 순서 변경과 문자열 대소문자가 다른 실제 충돌을 추가한다.
조건 판정 우선순위: ① 같은 판본에서 실제 값과 검수가 모두 Bool이고 서로 다르면 미검증 ② 실제 값 false면 미충족(검수 부재·오래된 판본도 실제 실패 증거를 지우지 않음) ③ 실제 true와 같은 판본 검수 true이면 충족 ④ 나머지 미검증. 요구가 0건인 실행은 미검증이다.
내용 동일성은 평면 JSON 기록의 필드 순서를 무시하지만 정확한 키·문자열 원문·타입·필드 부재를 구분한다. 기본 실행자들의 서로 다른 판본 해석은 최초 과제 모호함으로 기록하며 오류로 소급하지 않는다.
'''
with (root/'out/task.md').open('a') as f:f.write(clarification)
write(root/'input/clarified_contract.txt',clarification)
def edit(rel,fn):
 p=root/'input/synthetic'/rel;a=json.loads(p.read_text());fn(a);write(p,a)
edit('runs.json',lambda a:a.__setitem__(-2,dict(reversed(list(a[-2].items())))))
def events(a):
 a[99]=dict(reversed(list(a[99].items())))
 a[1]['tag']='A';a[98]['tag']='a'
edit('events_0.json',events)
edit('checks/SYN-R08.json',lambda a:a.update(revision='old'))
edit('checks/SYN-R01.json',lambda a:a.update(revision='old'))
edit('artifacts/SYN-R09.json',lambda a:a['values'].pop('C1'))
edit('checks/SYN-R02.json',lambda a:a['checks'].update(C2=True))
p=root/'input/synthetic/requirements.json';write(p,[r for r in json.loads(p.read_text()) if r['run_id']!='SYN-R10'])
print({'case':'repair_boundary','input':str(root/'input')})
