"""24 domain compositions; external effects are checked, never executed."""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
CASES = [('T01',
  '출석 명단에 평가표를 붙여 원래 점수와 평가 점수를 구별',
  '$r=[table:join]{left:[{id:"a",score:10},{id:"b"}],right:[{id:"a",score:20},{id:"b",score:30}],on:"id"}; '
  'return $r.items',
  'value',
  [{'id': 'a', 'score': 10, 'score_2': 20}, {'id': 'b', 'score_2': 30}]),
 ('T02',
  '출석 결합 결과에서 평가 점수만 합산',
  '$r=[table:join]{left:[{id:"a",score:10},{id:"b"}],right:[{id:"a",score:20},{id:"b",score:30}],on:"id"}; '
  '$r.items >> [table:select]{columns:($r)=>{score:$r.score_2}}',
  'value',
  [{'score': 20}, {'score': 30}]),
 ('T03',
  '기존 매물 별칭 열이 일부 행에만 있어도 두 원천 가격 구별',
  '$r=[table:join]{left:[{id:"a",price:100,price_2:90},{id:"b",price:200}],right:[{id:"a",price:110},{id:"b",price:210}],on:"id"}; '
  'return $r.items',
  'value',
  [{'id': 'a', 'price': 100, 'price_2': 90, 'price_3': 110},
   {'id': 'b', 'price': 200, 'price_3': 210}]),
 ('T04',
  '내부 결합과 왼쪽 보존 결합에서 평가 열 이름 일치',
  '$a=[{id:"a",score:10},{id:"b"}]; $b=[{id:"a",score:20},{id:"b",score:30}]; '
  '$x=[table:join]{left:$a,right:$b,on:"id"}; '
  '$y=[table:join]{left:$a,right:$b,on:"id",how:"left"}; return '
  'get($x.items[1],"score_2",-1)==$y.items[1].score_2',
  'value',
  True),
 ('T05',
  '강의 표의 마지막 선택 셀이 비어도 평가값이 올바른 열에 위치',
  '$r=[table:join]{left:{table:{columns:["id","memo"],rows:[["a"],["b","출석"]]}},right:{table:{columns:["id","score"],rows:[["a",20],["b",30]]}},on:"id"}; '
  'return $r.table',
  'value',
  {'columns': ['id', 'memo', 'score'], 'rows': [['a', None, 20], ['b', '출석', 30]]}),
 ('T06',
  '선택 메모가 생략된 가족신문 원고 표를 작성자 표와 결합',
  '$r=[table:join]{left:{table:{columns:["id","memo"],rows:[["a"]]}},right:{table:{columns:["id","author"],rows:[["a","가족"]]}},on:"id"}; '
  '$s=$r >> [table:rename]{map:{author:"작성자"}}; return $s.items',
  'value',
  [{'id': 'a', 'memo': None, '작성자': '가족'}]),
 ('T07',
  '메모가 빠진 표와 제목이 빠진 표를 결합해 빈 셀 보존',
  '$r=[table:join]{left:{table:{columns:["id","memo"],rows:[["a"]]}},right:{table:{columns:["id","title"],rows:[["a"]]}},on:"id"}; '
  'return $r.table',
  'value',
  {'columns': ['id', 'memo', 'title'], 'rows': [['a', None, None]]}),
 ('T08',
  '선택 열이 빠진 표도 왼쪽 보존 결합에서 정확한 위치 유지',
  '$r=[table:join]{left:{table:{columns:["id","memo"],rows:[["a"]]}},right:{table:{columns:["id","score"],rows:[["a",20]]}},on:"id",how:"left"}; '
  'return $r.table',
  'value',
  {'columns': ['id', 'memo', 'score'], 'rows': [['a', None, 20]]}),
 ('T09',
  '미평가 출석자에 기본 안내문 부여',
  '$r=[table:join]{left:[{id:"a"},{id:"b"}],right:[{id:"a",memo:"완료"}],on:"id",how:"left",defaults:{memo:"대기"}}; '
  'return $r.items',
  'value',
  [{'id': 'a', 'memo': '완료'}, {'id': 'b', 'memo': '대기'}]),
 ('T10',
  '평가표가 완전히 비었을 때도 출석자 보존',
  '$r=[table:join]{left:[{id:"a"}],right:[],on:"id",how:"left",defaults:{memo:"대기"}}; return '
  '$r.items',
  'value',
  [{'id': 'a', 'memo': '대기'}]),
 ('T11',
  '출석 명단에 없는 제출자까지 전체 대조',
  '$r=[table:join]{left:[{id:"a",name:"가"}],right:[{id:"b",score:30}],on:"id",how:"full"}; return '
  '$r.items',
  'value',
  [{'id': 'a', 'name': '가', 'score': None}, {'id': 'b', 'name': None, 'score': 30}]),
 ('T12',
  '과제 제출자의 출석 원본만 추리기',
  '$r=[table:join]{left:[{id:"a",name:"가"},{id:"b",name:"나"}],right:[{id:"a"},{id:"a"}],on:"id",how:"semi"}; '
  'return $r.items',
  'value',
  [{'id': 'a', 'name': '가'}]),
 ('T13',
  '미제출자 명단을 알림 대상으로 준비',
  '$r=[table:join]{left:[{id:"a"},{id:"b"}],right:[{id:"a"}],on:"id",how:"anti"}; return $r.items',
  'value',
  [{'id': 'b'}]),
 ('T14',
  '강의와 학생의 복합 식별자로 점수를 정확히 결합',
  '$r=[table:join]{left:[{course:"A",id:"a"},{course:"B",id:"a"}],right:[{course:"B",id:"a",score:30}],on:["course","id"]}; '
  'return $r.items',
  'value',
  [{'course': 'B', 'id': 'a', 'score': 30}]),
 ('T15',
  '가족신문 복수 작성자의 기여를 모두 보존',
  '$r=[table:join]{left:[{id:"a",title:"소식"}],right:[{id:"a",author:"가"},{id:"a",author:"나"}],on:"id"}; '
  'return $r.items',
  'value',
  [{'id': 'a', 'title': '소식', 'author': '가'}, {'id': 'a', 'title': '소식', 'author': '나'}]),
 ('T16',
  '서로 다른 매물 ID 열 이름을 맞춰 관심 메모 결합',
  '$a=[{매물:"a",price:100}] >> [table:rename]{map:{매물:"id"}}; '
  '$r=[table:join]{left:$a,right:[{id:"a",memo:"방문"}],on:"id"}; return $r.items',
  'value',
  [{'id': 'a', 'price': 100, 'memo': '방문'}]),
 ('T17',
  '매물 원천 세 개를 병합하고 중복 제거 후 가격 정렬',
  '$r=([{id:"a",price:100}] & [{id:"b",price:200}] & [{id:"a",price:110}]) >> '
  '[table:merge]{by:"id"}; $r.items >> [table:sort]{by:"price"}',
  'value',
  [{'id': 'a', 'price': 100}, {'id': 'b', 'price': 200}]),
 ('T18',
  '분반별 평가 합계를 집계하고 출석 인원과 결합',
  '$a=[{course:"A",score:10},{course:"A",score:20}] >> '
  '[table:groupby]{by:"course",agg:{total:["sum","score"]}}; '
  '$r=[table:join]{left:$a,right:[{course:"A",count:2}],on:"course"}; $r.items >> '
  '[table:compute]{set:($r)=>{avg:$r.total/$r.count}}',
  'value',
  [{'course': 'A', 'total': 30, 'count': 2, 'avg': 15}]),
 ('T19',
  '실제 교재 목록을 날짜와 함께 조회해 존재 확인',
  '$r=[self:list]{path:"~workspace/data/guides",pattern:"ibl_composition.md"} & '
  '[self:time]{format:"%Y-%m-%d"}; return len($r[0])>0 and len($r[1])==10',
  'value',
  True),
 ('T20',
  '실제 조합 교재를 읽고 보고서 준비 조건 확인',
  '$r=[self:read]{path:"~workspace/data/guides/ibl_composition.md"}; return len($r.text)>100',
  'value',
  True),
 ('T21',
  '미제출자 집계 이메일 조합 검수',
  '$r=[table:join]{left:[{id:"a"}],right:[],on:"id",how:"anti"}; '
  '[others:channel_send]{channel_type:"email",to:"나",subject:"미제출 현황",body:json($r.items)}',
  'check',
  None),
 ('T22',
  '매물 결합표 파일 축적 검수',
  '$r=[table:join]{left:[{id:"a"}],right:[{id:"a",price:100}],on:"id"}; '
  '[self:write]{path:"outputs/IT65_summary.json",content:json($r.items)}',
  'check',
  None),
 ('T23',
  '강의 준비 예약 문형 검수',
  '$do="#!ibl edition=2\\n[self:time]{}"; [self:schedule]{repeat:"daily",time:"09:00",do:$do}',
  'check',
  None),
 ('T24',
  '관심 매물 부재 조건부 알림 검수',
  '$r=[table:join]{left:[{id:"a"}],right:[],on:"id",how:"anti"}; '
  '[if:len($r.items)>0]{[self:notify_user]{message:"확인이 필요합니다"}}',
  'check',
  None)]

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
