"""Generate full IBL delegation programs from the public previous-round components."""
import json
import sys
from pathlib import Path

import live

turn=int(sys.argv[1])
folder=live.OUT/'trainer'/f'T{turn}'
folder.mkdir(exist_ok=True)
programs=folder/'programs'; programs.mkdir(exist_ok=True)
previous=live.OUT/'trainer'/f'T{turn-1}'
agents=json.loads((live.OUT/'runs/trainer_agents.json').read_text())
source=live.OUT/'trainer/inputs'
if turn in (3,4):
    data=json.loads((live.BASE/'reference/initial_inputs/records.json').read_text())
    data['version']=turn-1
    if turn==3:data['items']=data['items'][:-1]
    live.save(source/'records.json',data)
q=lambda v:json.dumps(v,ensure_ascii=False,separators=(',',':'))
functions=(live.HERE/'functions.ibl').read_text()
parts={}
for part in functions.split('[def:')[1:]:
    parts[part.split(']')[0]]='[def:'+part


def defs(*names):
    return '#!ibl edition=2\n'+''.join(parts[n] for n in ('시각','보존',*names))


def message(role, path):
    return (f'훈련자 작성 IBL 실행 위임, 단계 T{turn}, 담당 {role}. '
        f'공개 계약에 맞춰 준비한 전체 프로그램 {path}를 읽고 execute_ibl로 실행해 주세요. '
        '계산을 Python/머릿속으로 대체하지 마세요. 예산 steps1000000/rows100000으로 실행하세요. '
        f'입력 읽기는 {source}와 프로그램에 명시한 같은 팀의 이전 산출물만, 쓰기는 {folder} 안만 허용합니다. '
        f'현재 정책 {q(live.policy(turn))}. 개인정보/접근성/1800건 전량 검증과 필수작업은 유지합니다. '
        '담당자 완료 주장만으로 완료 처리하지 않습니다. 달력/인력 정보 없으므로 기한 준수 확정 불가입니다. '
        '외부 발송·배포·예약·구매·설정 변경 없음. 다른 팀·reference·runs·snapshots·회차 docs 접근 금지. '
        '프로그램 오류는 원문과 진단을 보고하고 임의로 계산 계약을 바꾸지 마세요. '
        '작업이 접수되었으면 같은 접수증으로 기다리며 중복 실행하지 마세요. '
        '최종 응답은 생성한 파일 절대경로와 완료/실패 상태만 간결하게 보고하세요.')


prefix=f'$source={q(str(source))}; $output={q(str(folder))}; $policy={q(live.policy(turn))}\n'
for role,fun,key in [('운영','운영조건','D'),('비용','비용검토','B'),('일정','일정검토','C')]:
    code=defs(fun)+prefix
    if turn>2:
        code+=f'$read=[self:read]{{path:{q(str(previous/(key+"_envelope.json")))}}}; $old=$read.data\n'
    else: code+='$old={}\n'
    code+=f'$r=[fn:{fun}]{{source:$source,policy:$policy,output:$output,reload:{str(turn<=2).lower()},old:$old}}\n'
    code+=f'$saved=[self:write]{{path:$output+"/{key}_envelope.json",content:json($r)}}\n'
    code+='return {artifact:$saved.path}\n'
    (programs/(role+'.ibl')).write_text(code)

code=defs('행판정','자료검증','보완대상')+prefix
if turn>1:
    code+=f'$read=[self:read]{{path:{q(str(previous/"ADE_envelope.json"))}}}; $old=$read.data\n'
else:code+='$old={A:{}}\n'
if turn<=2:
    code+=f'$child=[others:delegate]{{agent_id:{q(agents["운영"]["id"])},message:{q(message("운영",programs/"운영.ibl"))}}}\n'
    code+='$saved=[self:write]{path:$output+"/operation_receipt.json",content:json($child)}\n'
live.save(source/'expected_ids.json', [f'D{i:04d}' for i in range(1,1801)])
code+='$ids=[self:read]{path:$source+"/expected_ids.json"}; $expected=$ids.data.items\n'
code+=f'$a=[fn:자료검증]{{source:$source,expected:$expected,output:$output,reload:{str(turn!=2).lower()},old:get($old,"A",{{}})}}\n'
if turn<=2:
    code+='$wait=[self:task]{op:"wait",ref:$child.task_ref,timeout:240,suspend:true}\n'
    code+='$read=[self:read]{path:$output+"/D_envelope.json"}; $d=$read.data\n'
else: code+='$d={**$old.D,reused:true}\n'
code+='$e=[fn:보완대상]{a:$a,d:$d,output:$output}\n'
code+='$saved=[self:write]{path:$output+"/ADE_envelope.json",content:json({A:$a,D:$d,E:$e})}\nreturn {artifact:$saved.path}\n'
(programs/'자료.ibl').write_text(code)

jobs=[dict(role=role,agent=agents[role]['id'],message=message(role,programs/(role+'.ibl'))) for role in (['자료','비용','일정'] if turn<=2 else ['자료'])]
start='''#!ibl edition=2
$receipts=$jobs >> [table:each]{parallel:3} {
  $r=[others:delegate]{agent_id:$it.agent,message:$it.message}
  return {role:$it.role,task_ref:$r.task_ref}
}
$saved=[self:write]{path:$out,content:json($receipts)}
return $receipts
'''
(live.HERE/'start.ibl').write_text(start)
live.save(live.OUT/'runs'/f'trainer_T{turn}_start_request.json',dict(code=start,inputs=dict(jobs=jobs,out=str(folder/'receipts.json'))))
observe='''#!ibl edition=2
$read=[self:read]{path:$file}
$observed=$read.data >> [table:each]{parallel:3} {
  [try] { $r=[self:task]{op:"wait",ref:$it.task_ref,timeout:20}; return {role:$it.role,view:$r} }
  [catch] { return {role:$it.role,error:$error} }
}
return $observed
'''
(live.HERE/'observe.ibl').write_text(observe)
live.save(live.OUT/'runs'/f'trainer_T{turn}_observe_request.json',dict(code=observe,inputs=dict(file=str(folder/'receipts.json'))))
final=defs('최종검토')+prefix
for key,name in [('ade','ADE'),('b','B'),('c','C')]:
    base=live.OUT/'trainer/T2' if turn>2 and key in ('b','c') else folder
    final+=f'$read=[self:read]{{path:{q(str(base/(name+"_envelope.json")))}}}; ${key}=$read.data\n'
if turn>2: final+='$b={**$b,reused:true}; $c={**$c,reused:true}\n'
final+=f'return [fn:최종검토]{{ade:$ade,b:$b,c:$c,policy:$policy,output:$output,phase:"T{turn}"}}\n'
(programs/'총괄.ibl').write_text(final)
live.save(live.OUT/'runs'/f'trainer_T{turn}_final_request.json',dict(code=final,budget=dict(steps=1000000,rows=100000)))
print(folder)
