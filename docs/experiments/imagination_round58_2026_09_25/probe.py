"""Round 58: 24 domain tasks; only checks for writes/messages/schedules."""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
CASES = [
    ("T01", "월 지출을 분류별 합산해 큰 순서로 본다", '''
$g=[{category:"식비",amount:30},{category:"교통",amount:10},{category:"식비",amount:20}] >> [table:groupby]{by:"category",agg:{total:["sum","amount"]}}
$g.items >> [table:sort]{by:"total",descending:true}''', False),
    ("T02", "여러 영상에서 수집한 동일 링크를 하나로 줄인다", '''
$d=[{url:"a",title:"첫 자료"},{url:"a",title:"중복"},{url:"b",title:"둘째"}] >> [table:dedup]{by:"url"}
$d.items >> [table:select]{columns:["url"]}''', False),
    ("T03", "매물 자료의 키 이름을 통일하고 관심 목록과 결합한다", '''
$r=[{name:"가",price:300}] >> [table:rename]{map:{name:"id"}}
[table:join]{left:$r.items,right:[{id:"가",memo:"관심"}],on:"id",how:"left"}''', False),
    ("T04", "강의별 참고문헌을 펼치면서 강의명을 유지한다", '''
$f=[{lecture:"기초",refs:[{title:"A"},{title:"B"}]},{lecture:"심화",refs:[]}] >> [table:flatten]{field:"refs",keep:["lecture"]}
$f.items >> [table:sort]{by:"title"}''', False),
    ("T05", "자료 제목을 한 줄 목차로 누적한다", '''
$r=[{title:"가"},{title:"나"}] >> [table:reduce]{init:"",step:"acc + title",as:"toc"}
return $r.value''', False),
    ("T06", "날짜를 붙인 콘텐츠 제목을 만든다", '''
$date=[self:time]{format:"%Y"}
return f"${date} 강의 자료"''', False),
    ("T07", "세 출처 매물의 가격을 합쳐 정렬한다", '''
$r=([{id:"a",price:3}] & [{id:"b",price:2}] & [{id:"c",price:1}]) >> [table:merge]{by:"id"}
$r.items >> [table:sort]{by:"price"}''', False),
    ("T08", "강의 점수와 배수를 재사용 함수로 계산한다", '''
[def:점수]($rows,$factor=2){$rows >> [table:compute]{set:($r)=>{weighted:$r.score*$factor}}}
[{id:"a",score:3}] >> [fn:점수]{} >> [table:select]{columns:["id","weighted"]}''', False),
    ("T09", "한도 이내 매물만 골라 두 개씩 비교한다", '''
$cap=250
[{id:"a",price:300},{id:"b",price:200},{id:"c",price:100}] >> [table:filter]{where:($r)=>$r.price<=$cap} >> [table:take]{n:2}''', False),
    ("T10", "단가 계산이 안 되는 품목도 ID와 원인을 남긴다", '''
$rows=[{id:"a",n:2},{id:"b",n:0}]
$r=$rows >> [table:each]{on_error:"collect",parallel:2}{return 100/$it.n}
[table:each]{items:$r}{[if:is_ok($it)]{return {id:$rows[$i].id,ok:true,value:unwrap($it)}}[else]{return {id:$rows[$i].id,ok:false,error:error_of($it).code}}}''', False),
    ("T11", "자료가 없는 강의도 지우지 않고 빈 목록을 유지한다", '''
[{name:"기초",refs:[]},{name:"심화",refs:["A"]}] >> [table:each]{parallel:2}{$refs=$it.refs ?? ["대체"]; return {name:$it.name,refs:$refs}}''', False),
    ("T12", "콘텐츠 분류별 목표 편수를 합산한다", '''
$rows=[{category:"강의",n:2},{category:"뉴스",n:3}]
return reduce($rows,0,($total,$row)=>$total+$row.n)''', False),
    ("T13", "저장 전에 보고서와 첨부 파일 이름을 검사한다", '''
$date=[self:time]{format:"%Y-%m-%d"}
[self:write]{path:f"outputs/IT58_${date}.txt",content:"훈련 보고서"}''', True),
    ("T14", "새 자료가 있을 때만 자신에게 알림을 준비한다", '''
$rows=[{title:"새 강의"}]
[if:len($rows)>0]{[self:notify_user]{message:f"새 자료 ${len($rows)}건"}}''', True),
    ("T15", "지출 집계 실행을 매일 오전으로 예약할 수 있는지 검사한다", '''
[self:schedule]{repeat:"daily",time:"09:00",do:"#!ibl edition=2\\n[self:time]{}"}''', True),
    ("T16", "완성한 강의 목차의 이메일 발신 문장을 검사한다", '''
$titles=["기초","심화"]
[others:channel_send]{channel_type:"email",to:"나",subject:"IT58 검수",body:json($titles)}''', True),
    ("T17", "가격 변화를 확인하되 검침 기준선을 바꾸지 않는다", '''
$r=[{id:"IT58_a",price:100}] >> [table:since]{key:"IT58_peek",by:"id",watch:["price"],peek:true}
return $r.items''', False),
    ("T18", "기존 강의 파일 목록에서 마크다운 파일 두 개를 확인한다", '''
[self:list]{path:"~workspace/docs/experiments/imagination_round57_2026_09_25",pattern:"*.md"} >> [table:take]{n:2}''', False),
    ("T19", "비어 있는 매물 자료를 그룹 집계해도 오류 없이 끝낸다", '''
$g=[] >> [table:groupby]{by:"region",agg:{count:["count"]}}
return $g.items''', False),
    ("T20", "영상별 팁에 부모 영상 ID를 붙여 전부 펼친다", '''
[{id:"a",tips:[{n:1},{n:2}]},{id:"b",tips:[{n:3}]}] >> [table:each]{mode:"flat_map",parallel:2}{
$id=$it.id
$it.tips >> [table:select]{columns:($r)=>{video:$id,n:$r.n}}
}''', False),
    ("T21", "조건에 맞는 첫 강의를 찾으면 나머지를 계산하지 않는다", '''
[def:first]($rows){[repeat:len($rows)]{[if:$rows[$i].score>=5]{return $rows[$i].id}}; return null}
[fn:first]{rows:[{id:"a",score:2},{id:"b",score:7},{id:"c",score:9}]}''', False),
    ("T22", "매물의 선택 메모가 없을 때 기본 문구를 붙인다", '''
[{id:"a"},{id:"b",memo:"관심"}] >> [table:compute]{set:($r)=>{memo:get($r,"memo","미검토")}}''', False),
    ("T23", "서로 다른 두 강의가 같은 집계 함수를 독립적으로 쓴다", '''
[def:total]($rows){return sum($rows)}
[fn:total]{rows:[2,3]} & [fn:total]{rows:[7,8]}''', False),
    ("T24", "마감 상태에 따라 다음 작업 안내를 정한다", '''
$status="review"
[case:$status]{[when:"draft"]{"작성"}[when:"review"]{"검토"}[else]{"완료"}}''', False),
]


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "before"
    evidence = []
    for name, intent, code, check_only in CASES:
        for check in ([True] if check_only else [True, False]):
            payload = dict(code="#!ibl edition=2\n" + code, edition=2,
                           project_id="컨텐츠", origin="training", check=check)
            start = time.monotonic()
            run = subprocess.run(
                ["curl", "-sS", "--max-time", "60", "http://127.0.0.1:8765/ibl/execute",
                 "-H", "Content-Type: application/json", "--data-binary", "@-"],
                input=json.dumps(payload), text=True, capture_output=True, check=True)
            response = json.loads(run.stdout)
            evidence.append(dict(name=name, intent=intent, request=payload, response=response,
                                 seconds=round(time.monotonic()-start, 4)))
            result = response.get("result", response)
            print(name, "check" if check else "run", json.dumps({k:result[k] for k in
                ("status", "success", "value", "issues", "diagnostic", "error") if k in result},
                ensure_ascii=False)[:1600], flush=True)
    (HERE / f"{phase}.json").write_text(
        '[\n' + ',\n'.join(json.dumps(row, ensure_ascii=False) for row in evidence) + '\n]\n')


if __name__ == "__main__":
    main()
