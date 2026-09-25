"""24 domain tasks; external writes are validated only."""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
# expectation: value, error (must reject without a complete result), check only.
CASES = [
('T01','매물 식별자 열을 맞춰 관심 메모와 결합', '''
$r=[{listing:"a",price:200},{listing:"b",price:100}] >> [table:rename]{map:{listing:"id"}}
$j=[table:join]{left:$r,right:[{id:"a",memo:"역세권"}],on:"id",how:"left",defaults:{memo:"미검토"}}
$j.items >> [table:sort]{by:"price"} >> [table:select]{columns:["id","memo"]}''','value',[{'id':'b','memo':'미검토'},{'id':'a','memo':'역세권'}]),
('T02','강의별 출석과 점수를 복합 키로 맞춰 가중 점수 계산', '''
$j=[table:join]{left:[{course:"A",id:1,score:80},{course:"B",id:1,score:60}],right:[{course:"A",id:1,weight:2},{course:"B",id:1,weight:3}],on:["course","id"]}
$j.items >> [table:select]{columns:($r)=>{course:$r.course,total:$r.score*$r.weight}}''','value',[{'course':'A','total':160},{'course':'B','total':180}]),
('T03','세 코너에서 모은 가족신문 기사를 합쳐 중복 제거', '''
$r=([{id:"a",title:"여행"}] & [{id:"b",title:"강의"}] & [{id:"a",title:"여행"}]) >> [table:merge]{by:"id"}
$r.items >> [table:select]{columns:["title"]}''','value',[{'title':'여행'},{'title':'강의'}]),
('T04','가족신문 제작비를 누적하고 총액 표시', '''
$r=[{cost:10},{cost:20}] >> [table:reduce]{init:0,step:"acc + cost",as:"total"}
return f"제작비 ${r.value}원"''','value','제작비 30원'),
('T05','잘못 읽힌 영수증 행이 섞이면 합계를 완전한 총액으로 보고하지 않기', '''
[{cost:10},"읽기 실패",{cost:20}] >> [table:reduce]{init:0,step:"acc + cost"}''','error',None),
('T06','매물 응답에 잘못된 행이 있으면 관심 목록 결합을 실패로 알리기', '''
[table:join]{left:{items:[{id:"a",price:200},"잘못된 매물"]},right:[{id:"a",memo:"역세권"}],on:"id"}''','error',None),
('T07','가족신문 비용 자료가 전부 잘못된 행이면 0원으로 오인하지 않기', '''
["원문 누락",null] >> [table:reduce]{init:0,step:"acc + 1"}''','error',None),
('T08','제출 명단에만 있는 학생을 뽑아 점수 정렬', '''
$r=[table:join]{left:[{id:"a",score:80},{id:"b",score:70}],right:[{id:"a"},{id:"a"}],on:"id",how:"semi"}
$r.items >> [table:sort]{by:"score",descending:true}''','value',[{'id':'a','score':80}]),
('T09','미제출 학생만 골라 독촉 대상 초안 만들기', '''
$r=[table:join]{left:[{id:"a",name:"가"},{id:"b",name:"나"}],right:[{id:"a"}],on:"id",how:"anti"}
$r.items >> [table:select]{columns:($r)=>{id:$r.id,title:$r.name+" 제출 확인"}}''','value',[{'id':'b','title':'나 제출 확인'}]),
('T10','비어 있는 비용 명세는 초기 예산 그대로 유지', '''
$r=[] >> [table:reduce]{init:100,step:"acc + cost"}
return {total:$r.value,rows:$r.reduced_rows}''','value',{'total':100,'rows':0}),
('T11','분야별 강의 평균 점수와 실제 채점 건수 집계', '''
$r=[{course:"A",score:80},{course:"A",score:null},{course:"B",score:60}] >> [table:groupby]{by:"course",agg:{average:["avg","score"],graded:["count","score"]}}
$r.items >> [table:sort]{by:"course"}''','value',[{'course':'A','average':80,'graded':1},{'course':'B','average':60,'graded':1}]),
('T12','원고별 참고 자료를 펼쳐 원고 식별자와 함께 중복 제거', '''
$r=[{id:"a",refs:[{url:"u1"},{url:"u1"}]},{id:"b",refs:[]}] >> [table:flatten]{field:"refs",keep:["id"]}
$d=$r >> [table:dedup]{by:["id","url"]}
return $d.items''','value',[{'url':'u1','id':'a'}]),
('T13','매물 가격의 이전 값과 현재 값을 모두 보존하고 변동 계산', '''
$r=[table:join]{left:[{id:"a",price:200}],right:[{id:"a",price:180}],on:"id"}
$r.items >> [table:select]{columns:($r)=>{id:$r.id,change:$r.price_2-$r.price}}''','value',[{'id':'a','change':-20}]),
('T14','비용이 빠진 영수증을 숨기지 않고 실패 사유 반환', '''
[try]{[{cost:10},{memo:"금액 없음"}] >> [table:reduce]{init:0,step:"acc + cost"}}
[catch]{return {failed:true}}''','partial',{'failed':True}),
('T15','수집 결과에 잘린 원문이 있으면 집계 후에도 불완전성을 알리기', '''
[try]{{items:[{kind:"인쇄",cost:10}],truncated:true} >> [table:groupby]{by:"kind",agg:{total:["sum","cost"]}}}
[catch]{return {partial:true}}''','partial',{'partial':True}),
('T16','반별 비용 누적을 병렬 처리하고 반 순서 유지', '''
[[{cost:10},{cost:20}],[{cost:5}]] >> [table:each]{parallel:2}{
$r=$it >> [table:reduce]{init:0,step:"acc + cost"}
return $r.value}''','value',[30,5]),
('T17','관심 매물이 없는 날에도 원래 매물과 기본 메모 유지', '''
$r=[table:join]{left:[{id:"a",price:200}],right:[],on:"id",how:"left",defaults:{memo:"미검토"}}
return $r.items''','value',[{'id':'a','price':200,'memo':'미검토'}]),
('T18','강의 폴더의 실제 가이드 목록에서 사용 중인 교재 확인', '''
$r=[self:list]{path:"~workspace/data/guides",pattern:"ibl_composition.md"}
return len($r)>0''','value',True),
('T19','실제 교재 본문과 확인 날짜를 병렬로 읽어 보고서 준비 확인', '''
$r=([self:read]{path:"~workspace/data/guides/ibl_composition.md"} & [self:time]{format:"%Y-%m-%d"})
return len($r[0].text)>100 and len($r[1])==10''','value',True),
('T20','비어 있는 제출 목록을 순수 함수와 합산해 수업별 현황 작성', '''
[def:summary]($name,$rows){return {course:$name,count:len($rows),total:reduce($rows,0,($a,$r)=>$a+$r.score)}}
$a=[fn:summary]{name:"A",rows:[]}; $b=[fn:summary]{name:"B",rows:[{score:80}]}
return [$a,$b]''','value',[{'course':'A','count':0,'total':0},{'course':'B','count':1,'total':80}]),
('T21','검토 매물 요약을 이메일 초안으로 전달 검수', '''
$r=[{id:"a",price:200}] >> [table:select]{columns:["id","price"]}
[others:channel_send]{channel_type:"email",to:"나",subject:"매물 검토",body:json($r)}''','check',None),
('T22','강의 집계 결과를 날짜별 파일로 축적 검수', '''
$r=[{course:"A",score:80}] >> [table:groupby]{by:"course",agg:{total:["sum","score"]}}
$date=[self:time]{format:"%Y-%m-%d"}
[self:write]{path:f"outputs/IT63_${date}.json",content:json($r.items)}''','check',None),
('T23','매일 가족신문 준비 시각을 예약 검수', '''
[self:schedule]{repeat:"daily",time:"09:00",do:"#!ibl edition=2\\n[self:time]{}"}''','check',None),
('T24','제작비가 한도를 넘으면 사용자 알림 검수', '''
$r=[{cost:30}] >> [table:reduce]{init:0,step:"acc + cost"}
[if:$r.value>25]{[self:notify_user]{message:f"제작비 ${r.value}원"}}''','check',None),
]


def passed(result, mode, expected, check):
    if check:
        return result.get('status') in ('valid','incomplete') and not result.get('issues') and result.get('executed') is False
    if mode == 'error':
        return result.get('success') is False and result.get('executed') is True
    return result.get('success') is True and result.get('value') == expected and result.get('source_complete') is (mode != 'partial')


def main():
    phase = sys.argv[1]
    rows = []
    for name, intent, code, mode, expected in CASES:
        for check in ([True] if mode == 'check' else [True, False]):
            payload = dict(code='#!ibl edition=2\n'+code,edition=2,project_id='컨텐츠',origin='training',check=check)
            started=time.monotonic()
            proc=subprocess.run(['curl','-sS','--max-time','60','http://127.0.0.1:8765/ibl/execute','-H','Content-Type: application/json','--data-binary','@-'],input=json.dumps(payload),text=True,capture_output=True,check=True)
            response=json.loads(proc.stdout); result=response.get('result',response)
            ok=passed(result,mode,expected,check)
            rows.append(dict(name=name,intent=intent,request=payload,mode=mode,expected=expected,response=response,passed=ok,seconds=round(time.monotonic()-started,4)))
            (HERE/f'{phase}.json').write_text('[\n'+',\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n]\n')
            print(name,'check' if check else 'run','PASS' if ok else 'FAIL',json.dumps({k:result[k] for k in ('value','issues','diagnostic','error') if k in result},ensure_ascii=False)[:700],flush=True)
    print('SUMMARY',sum(r['passed'] for r in rows),'/',len(rows))


if __name__=='__main__':
    main()
