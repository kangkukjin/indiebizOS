"""24 domain ranking/reporting tasks; external effects are check-only."""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
CASES=[('T01',
  '강의 분반별 평가 합계를 높은 순서로 보고',
  '$r=[{반:"A",점수:30},{반:"B",점수:50},{반:"A",점수:10}] >> [table:groupby]{by:"반",agg:{합계:["sum","점수"]}}; $r.items '
  '>> [table:sort]{by:"합계",descending:true}',
  'value',
  [{'반': 'B', '합계': 50}, {'반': 'A', '합계': 40}]),
 ('T02',
  '매물 가격 열 이름이 바뀌었으면 낡은 기준으로 추천 순위를 만들지 않기',
  '$r=[{id:"a",price:300},{id:"b",price:100}] >> [table:rename]{map:{price:"가격"}}; $r.items >> '
  '[table:sort]{by:"price"} >> [table:take]{n:1}',
  'runtime_error',
  'MISSING_FIELD'),
 ('T03',
  '평가 기준 필드가 없는 자료는 확인 필요로 표시',
  '[try]{[{id:"a",점수:30},{id:"b",점수:80}] >> [table:sort]{by:"총점",descending:true}; return '
  '"순위완료"}[catch]{return "기준확인"}',
  'value',
  '기준확인'),
 ('T04',
  '원고 묶음별 정렬 중 잘못된 원천을 실패로 수집',
  '$r=[[{id:"a",rank:2}],[{id:"b",priority:1}]] >> [table:each]{parallel:2,on_error:"collect"}{ $it >> '
  '[table:sort]{by:"rank"} }; return [is_ok($r[0]),is_ok($r[1])]',
  'partial',
  [True, False]),
 ('T05',
  '해당 조건의 매물이 없으면 빈 추천 목록 유지',
  '$r=[{price:100}] >> [table:filter]{where:($r)=>$r.price>500}; $r >> [table:sort]{by:"price"} >> '
  '[table:take]{n:3}',
  'value',
  []),
 ('T06',
  '일부 매물의 가격 미정은 가격이 있는 매물 뒤에 배치',
  '[{id:"a"},{id:"b",price:300},{id:"c",price:100}] >> [table:sort]{by:"price"}',
  'value',
  [{'id': 'c', 'price': 100}, {'id': 'b', 'price': 300}, {'id': 'a'}]),
 ('T07',
  '미평가 학생의 명시된 빈 점수는 입력 순서 유지',
  '[{id:"a",score:null},{id:"b",score:null}] >> [table:sort]{by:"score",descending:true}',
  'value',
  [{'id': 'a', 'score': None}, {'id': 'b', 'score': None}]),
 ('T08',
  '가족신문은 우선순위 내림차순, 동점은 작성자 이름순',
  '[{author:"나",rank:2},{author:"가",rank:2},{author:"다",rank:3}] >> [table:sort]{by:"author"} >> '
  '[table:sort]{by:"rank",descending:true}',
  'value',
  [{'author': '다', 'rank': 3}, {'author': '가', 'rank': 2}, {'author': '나', 'rank': 2}]),
 ('T09',
  '강의 두 차시별 제출 수를 집계하고 많은 순으로 정리',
  '$r=[{반:"A",차시:1},{반:"A",차시:2},{반:"A",차시:2}] >> [table:groupby]{by:["반","차시"]}; $r.items >> '
  '[table:sort]{by:"count",descending:true}',
  'value',
  [{'반': 'A', '차시': 2, 'count': 2}, {'반': 'A', '차시': 1, 'count': 1}]),
 ('T10',
  '가족신문 원고 중복을 제거하고 최근 원고부터 추출',
  '$r=[{id:"a",date:"2026-09-24"},{id:"b",date:"2026-09-26"},{id:"a",date:"2026-09-25"}] >> '
  '[table:dedup]{by:"id"}; $r.items >> [table:sort]{by:"date",descending:true} >> [table:take]{n:1}',
  'value',
  [{'id': 'b', 'date': '2026-09-26'}]),
 ('T11',
  '평가에 가중치를 적용하고 최고 점수 학생만 추출',
  '[{id:"a",score:20,weight:3},{id:"b",score:40,weight:1}] >> '
  '[table:compute]{set:($r)=>{weighted:$r.score*$r.weight}} >> [table:sort]{by:"weighted",descending:true} '
  '>> [table:select]{columns:["id","weighted"]} >> [table:take]{n:1}',
  'value',
  [{'id': 'a', 'weighted': 60}]),
 ('T12',
  '정렬된 매물의 가격을 한 번에 총합',
  '$r=[{price:300},{price:100}] >> [table:sort]{by:"price"}; return '
  'reduce($r,0,($acc,$row)=>$acc+$row.price)',
  'value',
  400),
 ('T13',
  '가족신문 작성자별 원고 수에서 가장 많은 작성자 추출',
  '$r=[{author:"가"},{author:"나"},{author:"가"}] >> [table:groupby]{by:"author"}; $r.items >> '
  '[table:sort]{by:"count",descending:true} >> [table:take]{n:1}',
  'value',
  [{'author': '가', 'count': 2}]),
 ('T14',
  '관심 매물이 없을 때 사용자 안내 문구 준비',
  '$r=[] >> [table:sort]{by:"price"}; [if:len($r)==0]{return {message:"대상 없음"}}[else]{return {message:"추천 '
  '있음"}}',
  'value',
  {'message': '대상 없음'}),
 ('T15',
  '가족신문 분류별로 이름을 붙인 집계를 제목 목록으로 변환',
  '$r=[{topic:"여행"},{topic:"강의"},{topic:"여행"}] >> [table:groupby]{by:"topic",agg:{편수:["count"]}}; '
  '$s=$r.items >> [table:sort]{by:"편수",descending:true}; $s >> [table:each]{return f"${$it.topic}: '
  '${$it.편수}편"}',
  'value',
  ['여행: 2편', '강의: 1편']),
 ('T16',
  '하나의 순위 함수를 강의와 매물에 재사용',
  '[def:상위]($rows,$key){$rows >> [table:sort]{by:$key,descending:true} >> [table:take]{n:1}}; '
  '$a=[fn:상위]{rows:[{score:1},{score:5}],key:"score"}; '
  '$b=[fn:상위]{rows:[{price:200},{price:100}],key:"price"}; return {강의:$a,매물:$b}',
  'value',
  {'강의': [{'score': 5}], '매물': [{'price': 200}]}),
 ('T17',
  '분반별 점수표를 병렬 정렬해 원래 분반 순서로 유지',
  '[[{score:3},{score:1}],[{score:4},{score:2}]] >> [table:each]{parallel:2}{$it >> '
  '[table:sort]{by:"score"}}',
  'value',
  [[{'score': 1}, {'score': 3}], [{'score': 2}, {'score': 4}]]),
 ('T18',
  '바뀐 매물 가격 필드를 명시적으로 사용하면 정상 추천',
  '$r=[{id:"a",price:300},{id:"b",price:100}] >> [table:rename]{map:{price:"가격"}}; $r.items >> '
  '[table:sort]{by:"가격"} >> [table:take]{n:1}',
  'value',
  [{'id': 'b', '가격': 100}]),
 ('T19',
  '실제 강의 준비용 교재와 현재 날짜를 함께 확인',
  '$r=[self:list]{path:"~workspace/data/guides",pattern:"ibl_composition.md"} & '
  '[self:time]{format:"%Y-%m-%d"}; return len($r[0])>0 and len($r[1])==10',
  'value',
  True),
 ('T20',
  '실제 조합 교재를 읽어 보고서 자료 길이 확인',
  '$r=[self:read]{path:"~workspace/data/guides/ibl_composition.md"}; return len($r.text)>100',
  'value',
  True),
 ('T21',
  '최고 평가 학생 안내 이메일 검수',
  '$r=[{id:"a",score:10}] >> [table:sort]{by:"score",descending:true} >> [table:take]{n:1}; '
  '[others:channel_send]{channel_type:"email",to:"나",subject:"평가 현황",body:json($r)}',
  'check',
  None),
 ('T22',
  '매물 순위 자료 저장 검수',
  '$r=[{price:100}] >> [table:sort]{by:"price"}; '
  '[self:write]{path:"outputs/IT66_ranking.json",content:json($r)}',
  'check',
  None),
 ('T23',
  '강의 준비 시간을 매일 예약하는 문형 검수',
  '$do="#!ibl edition=2\\n[self:time]{}"; [self:schedule]{repeat:"daily",time:"09:00",do:$do}',
  'check',
  None),
 ('T24',
  '정렬 기준 누락 때 알림을 보내는 문형 검수',
  '[try]{[{score:10}] >> [table:sort]{by:"총점"}}[catch]{[self:notify_user]{message:"평가 기준을 확인하세요"}}',
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
