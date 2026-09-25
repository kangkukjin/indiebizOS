"""24 domain tasks: inspect all; execute only local read/pure operations."""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
CASES = [
    ('T01', '참고문헌이 모두 빈 강의들의 참고문헌 통합', '''
$r=[{lecture:"기초",refs:[]},{lecture:"심화",refs:[]}] >> [table:flatten]{field:"refs",keep:["lecture"]}
return $r.items''', False),
    ('T02', '잘못된 참고문헌 자료가 섞이면 누락 사실 확인', '''
$r=[{lecture:"기초",refs:[{title:"A"}]},{lecture:"심화",refs:null}] >> [table:flatten]{field:"refs",keep:["lecture"]}
return $r.items''', False),
    ('T03', '강의별 검색 결과를 펼칠 때 원천 검색의 잘림 확인', '''
$r=[{lecture:"기초",refs:{items:[{title:"A"}],truncated:true}}] >> [table:flatten]{field:"refs",keep:["lecture"]}
return $r.items''', False),
    ('T04', '강의 이름과 참고문헌의 같은 이름 필드를 모두 보존', '''
$r=[{title:"기초",refs:[{title:"A",title_2:"별칭"}]}] >> [table:flatten]{field:"refs",keep:["title"]}
return $r.items''', False),
    ('T05', '여러 출처에 모두 신규 매물이 없으면 빈 통합 목록', '''
$r=[table:merge]{inputs:[[],[]],by:"id"}
return $r.items''', False),
    ('T06', '매물과 관심 목록의 복합키를 맞춰 관심 매물만 추출', '''
$r=[table:join]{left:[{id:"a",kind:"매매",price:100},{id:"a",kind:"전세",price:50}],right:[{id:"a",kind:"전세"}],on:["id","kind"],how:"semi"}
return $r.items''', False),
    ('T07', '관심 목록에 중복이 있어도 미관심 매물은 한 번만 표시', '''
$r=[table:join]{left:[{id:"a"},{id:"b"}],right:[{id:"a"},{id:"a"}],on:"id",how:"anti"}
return $r.items''', False),
    ('T08', '식비를 날짜와 결제수단으로 묶어 건수 집계', '''
$r=[{day:"월",method:"카드"},{day:"월",method:"카드"},{day:"화",method:"현금"}] >> [table:groupby]{by:["day","method"],agg:{n:["count"]}}
return $r.items''', False),
    ('T09', '두 자료의 서로 바뀐 열 이름을 동시에 바로잡기', '''
$r=[{title:"홍길동",author:"자료명"}] >> [table:rename]{map:{title:"author",author:"title"}}
return $r.items''', False),
    ('T10', '정상적인 빈 검색 결과 봉투를 펼쳐도 오류 없이 다음 단계로', '''
$r=[{refs:{items:[]}}] >> [table:flatten]{field:"refs"}
return $r.items''', False),
    ('T11', '일부 검색 실패 봉투를 참고문헌에서 발견하면 실패 근거 유지', '''
$r=[{refs:{items:[{title:"A"}],success:false,error:"원천 검색 실패"}}] >> [table:flatten]{field:"refs"}
return $r.items''', False),
    ('T12', '참고문헌 행 안의 error와 truncated는 업무 데이터로 유지', '''
$r=[{refs:[{title:"오류 연구",error:"개념명",truncated:true}]}] >> [table:flatten]{field:"refs"}
return $r.items''', False),
    ('T13', '단계별 할인 계산을 함수 두 개로 재조합', '''
[def:discount]($price,$rate){return $price*(1-$rate)}
[def:bill]($rows){$rows >> [table:each]{[fn:discount]{price:$it.price,rate:$it.rate}}}
$r=[fn:bill]{rows:[{price:100,rate:0.2},{price:200,rate:0.1}]}
return sum($r)''', False),
    ('T14', '점수 계산 콜백은 만든 시점의 배점을 유지', '''
$factor=2
$score=($r)=>{weighted:$r.points*$factor}
$factor=3
[{points:5}] >> [table:select]{columns:$score}''', False),
    ('T15', '월별 비용을 중첩 누적해서 전체 합계 산출', '''
return reduce([[1,2],[3,4]],0,($total,$month)=>$total+reduce($month,0,($acc,$cost)=>$acc+$cost))''', False),
    ('T16', '서로 다른 반의 배점을 병렬 계산해 순서대로 반환', '''
[def:grade]($rows,$factor){$rows >> [table:compute]{set:($r)=>{score:$r.n*$factor}}}
[fn:grade]{rows:[{n:2}],factor:3} & [fn:grade]{rows:[{n:4}],factor:5}''', False),
    ('T17', '재고 없는 품목의 단가 실패를 모아 ID와 대체 안내 표시', '''
$rows=[{id:"a",n:2},{id:"b",n:0}]
$r=$rows >> [table:each]{on_error:"collect",parallel:2}{return 100/$it.n}
$r >> [table:each]{[if:is_ok($it)]{return {id:$rows[$i].id,value:unwrap($it)}}[else]{return {id:$rows[$i].id,value:"확인 필요"}}}''', False),
    ('T18', '한도에 도달할 때까지 비용을 누적한 뒤 상태 반환', '''
$total=0
[repeat:while $total<6]{$total=$total+2}
return $total''', False),
    ('T19', '긴 강의 본문을 분할하고 조각별 글자수를 다시 합산', '''
$r="가나다라마바사아자차" >> [table:chunk]{size:3,by:"chars"}
return reduce($r.items,0,($acc,$row)=>$acc+$row.chars)''', False),
    ('T20', '검증된 훈련 문서를 읽고 본문의 유무 확인', '''
$r=[self:read]{path:"~workspace/docs/experiments/imagination_round58_2026_09_25/report.md"}
return len($r.text)>0''', False),
    ('T21', '날짜별 비용 요약을 파일에 축적하는 문장 검수', '''
$date=[self:time]{format:"%Y-%m-%d"}
[self:write]{path:f"outputs/IT59_${date}.txt",content:json({sum:30})}''', True),
    ('T22', '정리된 강의 목차를 이메일로 전달하는 문장 검수', '''
$toc=["기초","심화"]
[others:channel_send]{channel_type:"email",to:"나",subject:"IT59 검수",body:json($toc)}''', True),
    ('T23', '매일 오전 새 강의 확인을 예약하는 문장 검수', '''
[self:schedule]{repeat:"daily",time:"09:00",do:"#!ibl edition=2\\n[self:time]{}"}''', True),
    ('T24', '지출 한도 초과일 때만 사용자 알림 문장 검수', '''
$total=sum([20,30])
[if:$total>40]{[self:notify_user]{message:f"지출 ${total}원 확인"}}''', True),
]


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else 'before'
    evidence = []
    for name, intent, code, check_only in CASES:
        for check in ([True] if check_only else [True, False]):
            payload = dict(code='#!ibl edition=2\n' + code, edition=2,
                           project_id='컨텐츠', origin='training', check=check)
            started = time.monotonic()
            proc = subprocess.run(
                ['curl', '-sS', '--max-time', '60', 'http://127.0.0.1:8765/ibl/execute',
                 '-H', 'Content-Type: application/json', '--data-binary', '@-'],
                input=json.dumps(payload), text=True, capture_output=True, check=True)
            response = json.loads(proc.stdout)
            evidence.append(dict(name=name, intent=intent, request=payload, response=response,
                                 seconds=round(time.monotonic()-started, 4)))
            (HERE / f'{phase}.json').write_text(
                '[\n' + ',\n'.join(json.dumps(row, ensure_ascii=False) for row in evidence) + '\n]\n')
            result = response.get('result', response)
            print(name, 'check' if check else 'run', json.dumps({k:result[k] for k in
                  ('status', 'success', 'value', 'issues', 'diagnostic', 'error') if k in result},
                  ensure_ascii=False)[:1200], flush=True)


if __name__ == '__main__':
    main()
