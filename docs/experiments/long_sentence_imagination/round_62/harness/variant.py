"""Controlled input change, after preserving each executor's base outputs."""
import argparse,hashlib,json,shutil
from pathlib import Path
from prepare import OUT,write
p=argparse.ArgumentParser();p.add_argument('who');a=p.parse_args();root=OUT/a.who
shutil.copytree(root/'out',root/'base_snapshot',dirs_exist_ok=False)
shutil.copytree(root/'input',root/'input_base_snapshot',dirs_exist_ok=False)
changes=[]
for i in (3,11,19):
 rid=f'SYN-R{i:02d}'
 for folder,field in [('artifacts','values'),('checks','checks')]:
  f=root/f'input/synthetic/{folder}/{rid}.json'
  write(f,{'run_id':rid,'revision':'v1',field:{'C1':True,'C2':True,'C3':True}});changes.append(str(f))
for folder,field in [('artifacts','values'),('checks','checks')]:
 f=root/f'input/synthetic/{folder}/SYN-R00.json';write(f,{'run_id':'SYN-R00','revision':'v2',field:{'C1':True,'C2':False,'C3':True}});changes.append(str(f))
write(OUT/f'{a.who}_changes.json',{'changes':changes})
if a.who=='agent':
 message=f'''조건은 그대로고 입력 증거가 바뀌었어. {root}/input/synthetic/artifacts와 checks에 SYN-R03,R11,R19의 누락 자료가 들어왔고 SYN-R00의 같은 경로 파일 내용이 v2로 바뀌었어. 입력 전체의 신선도를 확인해서 결과를 갱신해 줘. 너 자신의 직전 결과·중간 참조·스크립트는 재사용해도 돼. 다른 실행자의 trainer/source/runs/harness/정답은 참조하지 마. {root}/out에 verdicts_variant.json과 report_variant.md를 저장·재독하고 기본 대비 판정 변화, 실제 재독/재계산·재사용 범위, 관측과 미측정을 적어 줘. 요구별 의미와 비용 규칙은 이전 요청과 같아. 다음 훈련 제안은 이번 관측으로 갱신하되 시작하지 마. 시간 상한 10분. 시스템 코드·설정 수리 금지.'''
 write(OUT/'agent_variant_request.json',{'message':message,'origin':'training','background':True})
print({'who':a.who,'changed_files':len(changes)})
