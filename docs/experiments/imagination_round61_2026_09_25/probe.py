"""24 new domain compositions; external writes are checked only."""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
CASES = [
 ('T01','강의 수강료가 숫자 또는 숫자 문자열로 올 때 표시와 합산', '''
$rows=[{fee:10},{fee:"20"}]
$rows >> [table:each]{return {label:f"수강료 ${it.fee}",value:number($it.fee)}}''', [{'label':'수강료 10','value':10},{'label':'수강료 20','value':20}]),
 ('T02','무료와 유료 강의의 조건부 가격을 보고서 제목에 표시', '''
[if:true]{$fee=0}[else]{$fee="미정"}
return f"강의료 ${fee}"''','강의료 0'),
 ('T03','가족신문 코너별 제목의 길이를 공통 함수에서 계산', '''
[def:title]($family){[if:$family]{return "가족"}[else]{return "강의"}}
$x=[fn:title]{family:true}
return len($x)''',2),
 ('T04','지출 숫자와 텍스트 입력을 받아 단위를 붙이는 함수 조합', '''
[def:label]($n){return f"${n}원"}
$rows=[10,"20",30]
$rows >> [table:each]{[fn:label]{n:$it}}''',['10원','20원','30원']),
 ('T05','가족신문 섹션이 비어도 최종 기록에는 빈 제목을 유지', '''
[def:section]($empty){[if:$empty]{return {title:""}}; return {title:"가족"}}
$s=[fn:section]{empty:true}
return $s.title''',''),
 ('T06','매물 선택 함수가 모든 분기에서 반환한 뒤 공통 필드 읽기', '''
[def:pick]($cheap){[if:$cheap]{return {id:"a"}}[else]{return {id:"b"}}; "검토 완료"}
$r=[fn:pick]{cheap:true}
return $r.id''','a'),
 ('T07','강의 채점 실패 전 계산된 값을 catch에서 활용해 보완', '''
$x=0
[try]{$x={score:70}; 1/0}[catch]{return $x.score}''',70),
 ('T08','자료 가공 실패 뒤 finally가 정리 표시를 남기고 결과 반환', '''
$state="시작"
[try]{$state="처리"; 1/0}[catch]{$state=$state+" 실패"}[finally]{$state=$state+" 정리"}
return $state''','처리 실패 정리'),
 ('T09','가족신문 기사별 잘못된 비용만 수집하고 정상 합계 계산', '''
$r=[10,0,5] >> [table:each]{on_error:"collect",parallel:3}{return 100/$it}
$r >> [table:each]{[if:is_ok($it)]{return unwrap($it)}[else]{return 0}}''',[10,0,20]),
 ('T10','할인 함수를 만든 시점의 할인율을 다른 강의에도 재사용', '''
$rate=2
$f=($row)=>{price:$row.price*$rate}
$rate=3
[{price:10}] >> [table:select]{columns:$f}''',[{'price':20}]),
 ('T11','선택 코너에 따라 목록 또는 제목에서 첫 항목을 읽기', '''
[if:true]{$x=["가족","강의"]}[else]{$x="소식"}
return $x[0]''','가족'),
 ('T12','같은 매물 비교의 숫자와 문자열 가격을 합산해 추정 총액 계산', '''
$rows=[{price:10},{price:"20"}]
$rows >> [table:each]{return $it.price+5}''',[15,25]),
 ('T13','조건부 가족신문 제목을 JSON 보관용 문자열로 변환', '''
[if:false]{$title=2026}[else]{$title="가족신문"}
return text($title)''','가족신문'),
 ('T14','요약 실패를 복구한 함수 반환값을 다른 함수에서 재사용', '''
[def:summary]($n){[try]{return 10/$n}[catch]{return 0}}
[def:double]($n){return $n*2}
[fn:summary]{n:0} >> [fn:double]{}''',0),
 ('T15','문헌 제목과 글자 수를 서로 다른 함수 기본값으로 가공', '''
[def:decorate]($title,$prefix="참고: "){return {title:$prefix+$title,chars:len($title)}}
[fn:decorate]{title:"논문"} & [fn:decorate]{title:"기사",prefix:""}''',[{'title':'참고: 논문','chars':2},{'title':'기사','chars':2}]),
 ('T16','다른 출처의 매물 공통 식별자와 선택 메모를 함께 추출', '''
$rows=[{id:"a",memo:"역세권"},{id:"b"}]
$rows >> [table:each]{return {id:$it.id,memo:get($it,"memo","")}}''',[{'id':'a','memo':'역세권'},{'id':'b','memo':''}]),
 ('T17','가족신문 지출을 분류별 집계한 뒤 건수와 합계 표시', '''
$r=[{kind:"인쇄",cost:10},{kind:"인쇄",cost:20}] >> [table:groupby]{by:"kind",agg:{n:["count"],total:["sum","cost"]}}
$r.items >> [table:each]{return f"${it.kind}: ${it.n}건 ${it.total}원"}''',['인쇄: 2건 30원']),
 ('T18','코너 선택이 실패하면 대체 제목만 만들고 후속 정렬', '''
[def:load](){ $v=1/0; return [{title:"원본"}] }
$r=[fn:load]{} ?? [{title:"대체"}]
$r >> [table:sort]{by:"title"}''',[{'title':'대체'}]),
 ('T19','강의별 승인 여부를 케이스 분기로 바꾼 뒤 문자열 작성', '''
[case:"ready"]{[when:"ready"]{$label="승인"}[else]{$label=0}}
return f"상태 ${label}"''','상태 승인'),
 ('T20','실제 가이드 본문에서 공통 출력 계약을 읽어 기록용 제목 구성', '''
$r=[self:read]{path:"~workspace/data/guides/ibl_composition.md"}
return {present:len($r.text)>100,title:"조합 교재"}''',{'present':True,'title':'조합 교재'}),
 ('T21','매물 검토 결과와 수신자를 묶어 전달하는 문장 검사', '''
$row={id:"a",price:100}
[others:channel_send]{channel_type:"email",to:"나",subject:"IT61 검수",body:json($row)}''',None),
 ('T22','가족신문 비용 요약을 날짜별 파일에 축적하는 문장 검사', '''
$date=[self:time]{format:"%Y-%m-%d"}
[self:write]{path:f"outputs/IT61_${date}.json",content:json({total:30})}''',None),
 ('T23','매일 강의 준비 시작 시간을 조회하도록 예약 문장 검사', '''
[self:schedule]{repeat:"daily",time:"09:00",do:"#!ibl edition=2\\n[self:time]{}"}''',None),
 ('T24','가족신문 제작비가 예산을 넘을 때만 확인 알림 검사', '''
$total=sum([10,20,30])
[if:$total>50]{[self:notify_user]{message:f"제작비 ${total}원"}}''',None),
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
                result.get('success') is True and result.get('value') == expected and result.get('source_complete') is (name != 'T09'))
            evidence.append(dict(name=name,intent=intent,request=payload,expected=expected,
                                 response=response,passed=bool(passed),seconds=round(time.monotonic()-started,4)))
            (HERE/f'{phase}.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
            print(name,'check' if check else 'run','PASS' if passed else 'FAIL',
                  json.dumps({k:result[k] for k in ('value','issues','diagnostic','error') if k in result},ensure_ascii=False)[:1600],flush=True)
    print('SUMMARY',sum(r['passed'] for r in evidence),'/',len(evidence),flush=True)

if __name__ == '__main__':
    main()
