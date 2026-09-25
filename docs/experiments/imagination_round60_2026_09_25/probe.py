"""24 domain compositions; all checked, only pure/local reads executed."""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
CASES = [
    ('T01', '강의 배점 함수를 만들어 두 반의 점수를 별도로 계산', '''
[def:weight]($factor){return ($row)=>{score:$row.score*$factor}}
$a=[fn:weight]{factor:2}
$b=[fn:weight]{factor:3}
$x=[{score:4}] >> [table:select]{columns:$a}
$y=[{score:4}] >> [table:select]{columns:$b}
return [$x,$y]''', [[{'score':8}],[{'score':12}]]),
    ('T02', '가족신문 코너별 지역 함수가 서로의 제목을 바꾸지 않는지 확인', '''
[def:family]($title){[def:label]($x){return "가족: "+$x}; [fn:label]{x:$title}}
[def:lecture]($title){[def:label]($x){return "강의: "+$x}; [fn:label]{x:$title}}
[fn:family]{title:"소식"} & [fn:lecture]{title:"소식"}''', ['가족: 소식','강의: 소식']),
    ('T03', '추천 강의 세 개까지 인덱스로 차례로 읽어 제목 누적', '''
$rows=["기초","실습","심화","보충"]
$titles=[]
[repeat:while $i<3]{$titles=$titles+[$rows[$i]]}
return $titles''', ['기초','실습','심화']),
    ('T04', '읽은 지출이 한도 이상인 항목에 도달하면 그 자리에서 종료', '''
$rows=[10,20,50,80]
$out=[]
[repeat:until $cost>=50]{$cost=$rows[$i]; $out=$out+[$cost]}
return $out''', [10,20,50]),
    ('T05', '각 강의의 장 번호와 안쪽 반복 번호를 구분해 목차 작성', '''
$out=[]
[repeat:3]{
  $chapter=$i
  [repeat:2]{$out=$out+[{chapter:$chapter,section:$i}]}
  $out=$out+[{chapter:$i,section:9}]
}
return $out''', [{'chapter':c,'section':s} for c in range(3) for s in (0,1,9)]),
    ('T06', '첫 매물 비교 결과를 한 번 계산한 뒤 후속 선택에 사용', '''
[repeat:1]{$winner={id:"a",price:100}}
return $winner.id''', 'a'),
    ('T07', '각 자료의 전처리 중 짧은 반복 계산이 바깥 행을 바꾸지 않는지 확인', '''
[{n:2},{n:3}] >> [table:each]{parallel:2}{
  $value=0
  [repeat:$it.n]{$value=$value+2}
  return {n:$it.n,value:$value}
}''', [{'n':2,'value':4},{'n':3,'value':6}]),
    ('T08', '선택 비용이 없는 항목에는 기본값을 적용해 견적 계산', '''
[{id:"a",fee:0},{id:"b"}] >> [table:compute]{set:($r)=>{fee:get($r,"fee",10)}} >> [table:select]{columns:["id","fee"]}''', [{'id':'a','fee':0},{'id':'b','fee':10}]),
    ('T09', '신문 기사 중 연락처가 있는 행만 골라 주소 추출', '''
[{name:"가",email:"a@example.invalid"},{name:"나"}] >> [table:filter]{where:($r)=>has($r,"email")} >> [table:select]{columns:($r)=>{name:$r.name,email:get($r,"email","")}}''', [{'name':'가','email':'a@example.invalid'}]),
    ('T10', '지출 배열을 구조화한 누적으로 합계와 건수 동시 계산', '''
return reduce([10,20,30],{total:0,n:0},($acc,$v)=>{total:$acc.total+$v,n:$acc.n+1})''', {'total':60,'n':3}),
    ('T11', '중도 탈락 성적을 건너뛰고 합격 점수를 함수에서 조기 반환', '''
[def:first]($rows){[repeat:len($rows)]{[if:$rows[$i]>=60]{return $rows[$i]}}; return null}
[fn:first]{rows:[30,70,90]}''', 70),
    ('T12', '빈 강의 목록은 빈 목차를 반환하고 대체 자료를 끼워 넣지 않기', '''
[def:toc]($rows){$rows >> [table:each]{return $it.title}}
[fn:toc]{rows:[]} ?? ["대체"]''', []),
    ('T13', '재료가 없을 때 계산 실패를 복구해 확인할 품목 표시', '''
[1,0,2] >> [table:each]{parallel:2}{
  [try]{return 10/$it}[catch]{return "확인 필요"}
}''', [10,'확인 필요',5]),
    ('T14', '하위 보고서 함수가 반환한 목록 두 개를 명시적으로 결합', '''
[def:summary]($name){return [{name:$name}]}
$pair=[fn:summary]{name:"강의"} & [fn:summary]{name:"가족"}
$pair >> [table:each]{mode:"flat_map"}{return $it}''', [{'name':'강의'},{'name':'가족'}]),
    ('T15', '같은 정리 함수를 매물과 강의 레코드에 재사용', '''
[def:identity]($row){return $row}
$a=[fn:identity]{row:{price:100}}
$b=[fn:identity]{row:{title:"강의"}}
return {price:$a.price,title:$b.title}''', {'price':100,'title':'강의'}),
    ('T16', '지난 지출과 이번 지출의 공통 ID를 찾아 달라진 금액만 선별', '''
$j=[table:join]{left:[{id:"a",old:10},{id:"b",old:20}],right:[{id:"a",new:10},{id:"b",new:30}],on:"id"}
$j.items >> [table:filter]{where:($r)=>$r.old!=$r.new} >> [table:select]{columns:($r)=>{id:$r.id,delta:$r.new-$r.old}}''', [{'id':'b','delta':10}]),
    ('T17', '강의별 추천 문헌 제목을 재사용 함수로 정리하고 가나다순 정렬', '''
[def:bibliography]($rows){$rows >> [table:each]{mode:"flat_map"}{return $it.refs}}
$r=[fn:bibliography]{rows:[{refs:[{title:"나"}]},{refs:[{title:"가"}]}]}
$r >> [table:sort]{by:"title"} >> [table:select]{columns:["title"]}''', [{'title':'가'},{'title':'나'}]),
    ('T18', '코너별 기사 건수와 글자수를 집계해 제작 분량 확인', '''
$r=[{section:"가족",chars:10},{section:"가족",chars:20},{section:"강의",chars:5}] >> [table:groupby]{by:"section",agg:{n:["count"],chars:["sum","chars"]}}
return $r.items''', [{'section':'가족','n':2,'chars':30},{'section':'강의','n':1,'chars':5}]),
    ('T19', '함수의 기본 단가와 명시 단가를 구분해 비용 계산', '''
[def:cost]($qty,$price=10){return $qty*$price}
[fn:cost]{qty:2} & [fn:cost]{qty:2,price:0} & [fn:cost]{qty:3,price:5}''', [20,0,15]),
    ('T20', '훈련 가이드에서 보고서 절차가 실제로 읽히는지 확인', '''
$r=[self:read]{path:"~workspace/data/guides/imagination_training.md"}
return len($r.text)>100''', True),
    ('T21', '오늘 날짜와 비용을 묶어 파일에 축적하는 문장 검사', '''
$date=[self:time]{format:"%Y-%m-%d"}
[self:write]{path:f"outputs/IT60_${date}.txt",content:json({total:60})}''', None),
    ('T22', '가족신문 목차를 이메일로 전달하는 문장 검사', '''
$toc=["가족","강의"]
[others:channel_send]{channel_type:"email",to:"나",subject:"IT60 검수",body:json($toc)}''', None),
    ('T23', '매일 아침 강의 준비 확인을 예약하는 문장 검사', '''
[self:schedule]{repeat:"daily",time:"09:00",do:"#!ibl edition=2\\n[self:time]{}"}''', None),
    ('T24', '견적 한도를 넘는 경우에만 알림 문장 검사', '''
$total=sum([30,40])
[if:$total>60]{[self:notify_user]{message:f"견적 ${total}원 확인"}}''', None),
]


def main():
    phase = sys.argv[1]
    evidence = []
    for name, intent, code, expected in CASES:
        for check in ([True] if expected is None else [True, False]):
            payload = dict(code='#!ibl edition=2\n' + code, edition=2,
                           project_id='컨텐츠', origin='training', check=check)
            started = time.monotonic()
            proc = subprocess.run(
                ['curl', '-sS', '--max-time', '60', 'http://127.0.0.1:8765/ibl/execute',
                 '-H', 'Content-Type: application/json', '--data-binary', '@-'],
                input=json.dumps(payload), text=True, capture_output=True, check=True)
            response = json.loads(proc.stdout)
            result = response.get('result', response)
            passed = (result.get('status') in ('valid','incomplete') and not result.get('issues')) if check else (
                result.get('success') is True and result.get('value') == expected
                and result.get('source_complete') is True)
            evidence.append(dict(name=name, intent=intent, request=payload, expected=expected,
                                 response=response, passed=bool(passed),
                                 seconds=round(time.monotonic()-started,4)))
            (HERE / f'{phase}.json').write_text(
                '[\n'+',\n'.join(json.dumps(r,ensure_ascii=False) for r in evidence)+'\n]\n')
            print(name,'check' if check else 'run', 'PASS' if passed else 'FAIL',
                  json.dumps({k:result[k] for k in ('status','success','value','issues','diagnostic','error')
                              if k in result},ensure_ascii=False)[:1800],flush=True)
    print('SUMMARY',sum(r['passed'] for r in evidence),'/',len(evidence),flush=True)


if __name__ == '__main__':
    main()
