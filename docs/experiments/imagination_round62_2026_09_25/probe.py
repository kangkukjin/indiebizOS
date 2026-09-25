"""Double-sized domain rehearsal; only check external writes."""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
CASES = [
('T01','강의 점수 보정 함수를 인자로 받아 여러 반에 적용', '''
[def:apply]($rows,$adjust){$rows >> [table:each]{return $adjust($it)}}
[fn:apply]{rows:[60,80],adjust:($x)=>$x+5}''', [65,85]),
('T02','매물 목록마다 다른 상한으로 선택 함수를 만들어 재사용', '''
[def:limit]($cap){return ($row)=>$row.price<=$cap}
$f=[fn:limit]{cap:200}
[{id:"a",price:150},{id:"b",price:250}] >> [table:filter]{where:$f}''',[{'id':'a','price':150}]),
('T03','신문 코너별 접두 함수를 만들어 제목 가공', '''
$make=($prefix)=>($title)=>$prefix+$title
$f=$make("가족: ")
return $f("여행")''','가족: 여행'),
('T04','강의 점수의 절댓값 계산을 변수에 보관해 재사용', '''
$normalize=abs
[-3,4] >> [table:each]{return $normalize($it)}''',[3,4]),
('T05','제작비를 반올림 함수 인자로 전달해 공통 출력', '''
[def:format]($value,$normalize){return text($normalize($value))}
[fn:format]{value:12.7,normalize:round}''','13'),
('T06','매물 검토 건수 함수를 레코드에 보관', '''
$ops={count:len}
$count=$ops.count
return $count(["a","b"])''',2),
('T07','가족신문 기사 길이를 내장 함수 목록에서 선택', '''
$ops=[len,text]
$size=$ops[0]
return $size("여행")''',2),
('T08','누적 제작비를 큰 값 선택 함수로 집계', '''
return reduce([10,30,20],0,max)''',30),
('T09','강의 채점의 기본 보정 함수를 생략해도 호출', '''
[def:score]($x,$f=abs){return $f($x)}
[fn:score]{x:-7}''',7),
('T10','신문 원고가 비어도 공통 누적기로 초기 제목 유지', '''
$f=($acc,$row)=>$acc+" / "+$row
return reduce([],"가족신문",$f)''','가족신문'),
('T11','부동산 매물별 비용과 조건을 함수 두 개로 순서대로 계산', '''
$compose=($f,$g)=>($x)=>$g($f($x))
$f=$compose(($x)=>$x+10,($x)=>$x*2)
return $f(100)''',220),
('T12','신문 코너별 함수를 each에서 만든 후 원고에 적용', '''
$fs=["가족","강의"] >> [table:each]{return ($title)=>$it+": "+$title}
$fs >> [table:each]{return $it("소식")}''',['가족: 소식','강의: 소식']),
('T13','강의별 보정 함수를 병렬로 만들고 각 점수에 적용', '''
$fs=(($x)=>$x+1) & (($x)=>$x+2)
$first=$fs[0]; $second=$fs[1]
return [$first(10),$second(10)]''',[11,12]),
('T14','누적기에서 가족신문 코너와 건수를 한 레코드로 축적', '''
return reduce(["여행","강의"],{titles:[],count:0},($acc,$row)=>{titles:$acc.titles+[$row],count:$acc.count+1})''',{'titles':['여행','강의'],'count':2}),
('T15','강의 통과자에 복합 조건과 보정 함수를 같이 적용', '''
$min=60
$f=($r)=>$r.score>=$min and $r.active
$r=[{id:"a",score:70,active:true},{id:"b",score:90,active:false}] >> [table:filter]{where:$f}
$r >> [table:compute]{set:($row)=>{score:$row.score+5}}''',[{'id':'a','score':75,'active':True}]),
('T16','매물 메모가 없는 경우의 기본값과 가격순 정렬 조합', '''
$r=[table:join]{left:[{id:"a",price:200},{id:"b",price:100}],right:[{id:"a",memo:"역세권"}],on:"id",how:"left",defaults:{memo:"미검토"}}
$r.items >> [table:sort]{by:"price"} >> [table:select]{columns:["id","memo"]}''',[{'id':'b','memo':'미검토'},{'id':'a','memo':'역세권'}]),
('T17','분류별 가족신문 비용 집계 후 요약문 함수로 전달', '''
$r=[{kind:"인쇄",cost:10},{kind:"인쇄",cost:20}] >> [table:groupby]{by:"kind",agg:{total:["sum","cost"]}}
[def:label]($rows){$rows >> [table:each]{return f"${it.kind} ${it.total}원"}}
[fn:label]{rows:$r.items}''',['인쇄 30원']),
('T18','강의 채점 실패 항목의 사유와 성공값을 나란히 표시', '''
$r=[2,0] >> [table:each]{on_error:"collect"}{return 10/$it}
$r >> [table:each]{[if:is_ok($it)]{return {ok:true,value:unwrap($it)}}[else]{return {ok:false}}}''',[{'ok':True,'value':5},{'ok':False}]),
('T19','가족신문 기본 제목 함수를 실패 복구에도 재사용', '''
$f=($x)=>"대체: "+$x
[try]{1/0}[catch]{return $f("가족신문")}''','대체: 가족신문'),
('T20','실제 교재 파일에서 길이 계산 함수를 명시 인자로 적용', '''
$r=[self:read]{path:"~workspace/data/guides/ibl_composition.md"}
[def:present]($body,$size){return $size($body)>100}
[fn:present]{body:$r.text,size:len}''',True),
('T21','검토 매물 목록에서 만든 제목과 본문을 이메일로 전달 검수', '''
$rows=[{id:"a",price:200}]
[others:channel_send]{channel_type:"email",to:"나",subject:f"매물 ${len($rows)}건",body:json($rows)}''',None),
('T22','강의 채점 기록을 날짜별 JSON 파일에 축적 검수', '''
$date=[self:time]{format:"%Y-%m-%d"}
[self:write]{path:f"outputs/IT62_${date}.json",content:json({scores:[65,85]})}''',None),
('T23','매일 가족신문 준비 시간 확인 예약 검수', '''
[self:schedule]{repeat:"daily",time:"09:00",do:"#!ibl edition=2\\n[self:time]{}"}''',None),
('T24','제작비 합계가 한도를 넘었을 때 알림 검수', '''
$total=reduce([10,20],0,($acc,$cost)=>$acc+$cost)
[if:$total>25]{[self:notify_user]{message:f"제작비 ${total}원"}}''',None),
]


def main():
    phase = sys.argv[1]
    evidence = []
    for name, intent, code, expected in CASES:
        for check in ([True] if expected is None else [True, False]):
            payload = dict(code='#!ibl edition=2\n'+code, edition=2,
                           project_id='컨텐츠', origin='training', check=check)
            started = time.monotonic()
            proc = subprocess.run(['curl','-sS','--max-time','60',
                'http://127.0.0.1:8765/ibl/execute','-H','Content-Type: application/json',
                '--data-binary','@-'],input=json.dumps(payload),text=True,capture_output=True,check=True)
            response = json.loads(proc.stdout)
            result = response.get('result',response)
            passed = (result.get('status') in ('valid','incomplete') and not result.get('issues')) if check else (
                result.get('success') is True and result.get('value') == expected and result.get('source_complete') is (name != 'T18'))
            evidence.append(dict(name=name,intent=intent,request=payload,expected=expected,
                                 response=response,passed=bool(passed),seconds=round(time.monotonic()-started,4)))
            (HERE/f'{phase}.json').write_text('[\n'+',\n'.join(json.dumps(r,ensure_ascii=False) for r in evidence)+'\n]\n')
            print(name,'check' if check else 'run','PASS' if passed else 'FAIL',
                  json.dumps({k:result[k] for k in ('value','issues','diagnostic','error') if k in result},ensure_ascii=False)[:900],flush=True)
    print('SUMMARY',sum(r['passed'] for r in evidence),'/',len(evidence),flush=True)

if __name__ == '__main__':
    main()
