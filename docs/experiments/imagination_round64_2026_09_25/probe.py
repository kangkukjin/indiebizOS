"""24 domain compositions; external effects are checked, never executed."""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
CASES = [
('T01','강의별 배점을 함수로 만들어 학생 점수에 적용', '''
[def:weight]($factor){return ($r)=>{id:$r.id,score:$r.score*$factor}}
$f=[fn:weight]{factor:2}
[{id:"a",score:30},{id:"b",score:40}] >> [table:select]{columns:$f}''','value',[{'id':'a','score':60},{'id':'b','score':80}]),
('T02','관심 매물의 예산 조건을 만든 뒤 예산을 바꾸어도 기존 기준 보존', '''
$budget=200; $f=($r)=>$r.price<=$budget; $budget=100
[{id:"a",price:150},{id:"b",price:250}] >> [table:filter]{where:$f}''','value',[{'id':'a','price':150}]),
('T03','가족신문 원고 제목에 코너별 접두사를 함수로 적용', '''
[def:prefix]($head){return ($r)=>{title:$head+$r.title}}
$f=[fn:prefix]{head:"가족: "}
[{title:"여행"}] >> [table:select]{columns:$f}''','value',[{'title':'가족: 여행'}]),
('T04','강의별 채점 규칙 준비 결과를 모은 뒤 성공한 규칙으로 점수 계산', '''
$rules=[2,3] >> [table:each]{on_error:"collect"}{return ($r)=>{score:$r.score*$it}}
$f=unwrap($rules[0])
[{score:20}] >> [table:select]{columns:$f}''','value',[{'score':40}]),
('T05','채점 규칙 준비 이력을 남겨 둔 상태에서 별도 출석표 정리', '''
$rules=[2] >> [table:each]{on_error:"collect"}{return ($r)=>$r*$it}
[{name:"가",attended:true}] >> [table:select]{columns:($r)=>{name:$r.name}}''','value',[{'name':'가'}]),
('T06','성공한 채점 규칙을 감싼 콜백으로 다음 표 변환 수행', '''
$rules=[2] >> [table:each]{on_error:"collect"}{return ($r)=>$r*$it}
$f=unwrap($rules[0]); $apply=($r)=>{score:$f($r.score)}
[{score:30}] >> [table:select]{columns:$apply}''','value',[{'score':60}]),
('T07','채점 규칙 결과 목록을 콜백 안에서 직접 꺼내 사용', '''
$rules=[2] >> [table:each]{on_error:"collect"}{return ($r)=>$r*$it}
$apply=($r)=>{score:reduce([$r.score],0,unwrap($rules[0]))}
[{score:30}] >> [table:select]{columns:$apply}''','runtime_error','CALLABLE'),
('T08','선택 필드가 없는 관심 메모에 기본값을 넣고 매물 정렬', '''
[{id:"a",price:200},{id:"b",price:100,memo:"방문"}] >> [table:compute]{set:($r)=>{memo:get($r,"memo","미검토")}} >> [table:sort]{by:"price"}''','value',[{'id':'b','price':100,'memo':'방문'},{'id':'a','price':200,'memo':'미검토'}]),
('T09','채점 실패를 항목별로 수집하고 성공 점수만 합산', '''
$r=[2,0,5] >> [table:each]{on_error:"collect",parallel:3}{return 10/$it}
$ok=$r >> [table:each]{mode:"flat_map"}{[if:is_ok($it)]{return [unwrap($it)]}[else]{return []}}
return sum($ok)''','partial',7),
('T10','가족신문 비용의 서로 다른 환산 규칙을 순서대로 조합', '''
[def:compose]($first,$second){return ($v)=>$second($first($v))}
$f=[fn:compose]{first:($x)=>$x+10,second:($x)=>$x*2}
return $f(20)''','value',60),
('T11','분반별 기본 채점 함수와 전달한 함수를 함께 사용', '''
[def:grade]($rows,$f=($r)=>{score:$r.score*2}){$rows >> [table:select]{columns:$f}}
$a=[fn:grade]{rows:[{score:10}]}; $b=[fn:grade]{rows:[{score:10}],f:($r)=>{score:$r.score+5}}
return [$a,$b]''','value',[[{'score':20}],[{'score':15}]]),
('T12','비어 있는 제출 명단에도 재사용 채점 규칙을 정상 적용', '''
[def:grade]($rows,$f){$rows >> [table:select]{columns:$f}}
[fn:grade]{rows:[],f:($r)=>{score:$r.score*2}}''','value',[]),
('T13','집계 함수를 함수 인자로 전달하여 가족신문 비용 합산', '''
[def:total]($rows,$fold=reduce){return $fold($rows,0,($a,$r)=>$a+$r.cost)}
[fn:total]{rows:[{cost:10},{cost:25}]}''','value',35),
('T14','채점 규칙을 분반별로 보관하고 병렬로 점수 계산', '''
$rules=[2,3] >> [table:each]{return ($r)=>{score:$r.score*$it}}
[0,1] >> [table:each]{parallel:2}{
$f=$rules[$it]; $r=[{score:10}] >> [table:select]{columns:$f}; return $r[0].score}''','value',[20,30]),
('T15','여러 채점 준비 결과를 보관한 뒤 성공 규칙의 목록을 다시 변환', '''
$rules=[2] >> [table:each]{on_error:"collect"}{return ($acc,$score)=>$acc+$score*$it}
[{score:30}] >> [table:select]{columns:($r)=>{score:reduce([$r.score],0,unwrap($rules[0]))}}''','value',[{'score':60}]),
('T16','제출표의 단일 실패는 복구하되 정상 자료는 유지', '''
$rules=[0,2] >> [table:each]{on_error:"collect"}{ $factor=10/$it; return ($r)=>{score:$r.score*$factor}}
$f=unwrap($rules[1]); [{score:4}] >> [table:select]{columns:$f}''','partial',[{'score':20}]),
('T17','코너별 원고 수를 중첩 함수로 집계', '''
[def:summary]($rows){[def:count]($rows){return len($rows)}; $n=[fn:count]{rows:$rows}; return {count:$n}}
[[{title:"여행"}],[]] >> [table:each]{[fn:summary]{rows:$it}}''','value',[{'count':1},{'count':0}]),
('T18','실제 교재의 본문 길이를 콜백 기준으로 확인', '''
$r=[self:read]{path:"~workspace/data/guides/ibl_composition.md"}
[$r] >> [table:select]{columns:($row)=>{ready:len($row.text)>100}}''','value',[{'ready':True}]),
('T19','교재 폴더 목록을 읽고 재사용 필터로 존재 확인', '''
$r=[self:list]{path:"~workspace/data/guides",pattern:"ibl_composition.md"}
$size=len; return $size($r)>0''','value',True),
('T20','보고서 날짜를 함수 인자로 받아 제목 생성', '''
[def:title]($date,$format=($x)=>"가족신문 "+$x){return $format($date)}
$date=[self:time]{format:"%Y-%m-%d"}; $title=[fn:title]{date:$date}; return len($title)==15''','value',True),
('T21','채점 요약을 이메일로 전달하는 조합 검수', '''
$r=[{score:20}] >> [table:compute]{set:($r)=>{weighted:$r.score*2}}
[others:channel_send]{channel_type:"email",to:"나",subject:"채점 요약",body:json($r)}''','check',None),
('T22','코너별 원고 길이를 파일로 축적하는 조합 검수', '''
$r=[{text:"가족 소식"}] >> [table:select]{columns:($r)=>{chars:len($r.text)}}
[self:write]{path:"outputs/IT64_summary.json",content:json($r)}''','check',None),
('T23','강의 준비 시각을 예약하는 조합 검수', '''
$self="#!ibl edition=2\\n[self:time]{}"
[self:schedule]{repeat:"daily",time:"09:00",do:$self}''','check',None),
('T24','매물 예산을 넘긴 후보 수에 따라 알림 검수', '''
$r=[{price:300}] >> [table:filter]{where:($r)=>$r.price>200}
[if:len($r)>0]{[self:notify_user]{message:f"초과 매물 ${len($r)}건"}}''','check',None),
]

def passed(result, mode, expected, check):
    if check:
        return result.get('status') in ('valid','incomplete') and not result.get('issues') and result.get('executed') is False
    if mode == 'runtime_error':
        return result.get('success') is False and result.get('diagnostic',{}).get('code') == expected
    return result.get('success') is True and result.get('value') == expected and result.get('source_complete') is (mode != 'partial')

def main():
    rows=[]; phase=sys.argv[1]
    for name,intent,code,mode,expected in CASES:
        for check in ([True] if mode=='check' else [True,False]):
            payload=dict(code='#!ibl edition=2\n'+code,edition=2,project_id='컨텐츠',origin='training',check=check)
            started=time.monotonic()
            proc=subprocess.run(['curl','-sS','--max-time','60','http://127.0.0.1:8765/ibl/execute','-H','Content-Type: application/json','--data-binary','@-'],input=json.dumps(payload),text=True,capture_output=True,check=True)
            response=json.loads(proc.stdout); result=response.get('result',response)
            ok=passed(result,mode,expected,check)
            rows.append(dict(name=name,intent=intent,request=payload,mode=mode,expected=expected,response=response,passed=ok,seconds=round(time.monotonic()-started,4)))
            (HERE/f'{phase}.json').write_text('[\n'+',\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n]\n')
            print(name,'check' if check else 'run','PASS' if ok else 'FAIL',json.dumps({k:result[k] for k in ('value','issues','diagnostic','error') if k in result},ensure_ascii=False)[:650],flush=True)
    print('SUMMARY',sum(r['passed'] for r in rows),'/',len(rows))

if __name__=='__main__':
    main()
