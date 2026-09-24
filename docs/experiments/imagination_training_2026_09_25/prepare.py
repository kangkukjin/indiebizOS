"""Round 56 synthetic tasks; prepares requests, never calls external services."""
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
HERE = ROOT / 'outputs/imagination_training/round56'
HERE.mkdir(parents=True, exist_ok=True)
db = HERE / 'fixture.sqlite3'
with sqlite3.connect(db) as conn:
    conn.execute('CREATE TABLE IF NOT EXISTS expenses(category TEXT, amount INTEGER)')
    if not conn.execute('SELECT count(*) FROM expenses').fetchone()[0]:
        conn.executemany('INSERT INTO expenses VALUES (?,?)', [('food',100),('food',200),('book',50)])
(HERE / 'sample.md').write_text('첫 문단입니다.\n\n둘째 문단입니다.\n')
cases = []
def add(name, intent, code, expected=None, check_only=False):
    cases.append(dict(name=name, intent=intent, code='#!ibl edition=2\n'+code,
                      expected=expected, check_only=check_only))

add('T01', '가계부 DB에서 분류별 합계를 구하고 큰 순서로 보여 주세요.', f'''
$원본=[sense:sqlite]{{path:{json.dumps(str(db))},query:"SELECT category, amount FROM expenses"}}
$집계=[table:groupby]{{items:$원본.items,by:"category",agg:{{total:["sum","amount"]}}}}
$집계.items >> [table:sort]{{by:"total",descending:true}}
''', [{'category':'food','total':300},{'category':'book','total':50}])
add('T02', '매물별 가격과 관심 목록을 연결하고 관심 없는 매물도 보존해 주세요.', '''
$매물=[{id:"a",price:300},{id:"b",price:200}]
$관심=[{id:"a",memo:"역세권"}]
$결합=[table:join]{left:$매물,right:$관심,on:"id",how:"left",defaults:{memo:"미검토"}}
$결합.items >> [table:select]{columns:["id","memo"]}
''', [{'id':'a','memo':'역세권'},{'id':'b','memo':'미검토'}])
add('T03', '영상별 팁 목록을 펼치되 영상 ID를 각 팁에 붙여 주세요.', '''
$영상=[{id:"v1",tips:[{text:"단축키"},{text:"자동화"}]},{id:"v2",tips:[]}]
$팁=[table:flatten]{items:$영상,field:"tips",keep:["id"]}
$팁.items >> [table:select]{columns:["id","text"]}
''', [{'id':'v1','text':'단축키'},{'id':'v1','text':'자동화'}])
add('T04', '서로 다른 두 출처의 기사 ID 이름을 맞추고 중복 기사를 합쳐 주세요.', '''
$첫=[table:rename]{items:[{article_id:"a",title:"첫 기사"}],map:{article_id:"id"}}
$합=[table:merge]{left:$첫.items,right:[{id:"a",title:"중복"},{id:"b",title:"둘째"}],by:"id"}
$합.items >> [table:select]{columns:["id"]}
''', [{'id':'a'},{'id':'b'}])
add('T05', '폴더의 자료 목록에서 마크다운을 읽어 파일별 글자 수를 세어 주세요.', f'''
$자료=[self:list]{{path:{json.dumps(str(HERE))},pattern:"sample.md"}}
$자료 >> [table:each]{{parallel:2}}{{
  $문서=[self:read]{{path:$it.path}}
  return {{name:$it.name,chars:len($문서.text)}}
}}
''', [{'name':'sample.md','chars':20}])
add('T06', '분석한 숫자 목록을 JSON으로 저장하고 다시 읽어 그대로 보존됐는지 확인해 주세요.', f'''
$목록=[{{id:"007",amount:3500}},{{id:"b",amount:0}}]
$저장=[self:write]{{path:{json.dumps(str(HERE / 'IT56_roundtrip.json'))},content:json($목록)}}
$읽음=[self:read]{{path:{json.dumps(str(HERE / 'IT56_roundtrip.json'))}}}
return $읽음
''')
add('T07', '지원사업 세 건의 점수를 합산하고 총점이 10 이상인지 판정해 주세요.', '''
$합=[table:reduce]{items:[{score:2},{score:3},{score:7}],init:0,step:"acc + score",as:"total"}
return {total:$합.value,passed:$합.value>=10}
''', {'total':12,'passed':True})
add('T08', '오늘 날짜와 오전·오후 기준을 읽어 보고서 제목을 만들어 주세요.', '''
$날짜=[self:time]{format:"%Y-%m-%d"}
$시=[self:time]{format:"%H"}
return {date:$날짜,hour:$시}
''')
add('T09', '수량이 0인 항목은 실패로 남기면서 다른 품목의 단가 계산을 계속해 주세요.', '''
$계산=[{id:"a",price:100,count:2},{id:"b",price:300,count:0},{id:"c",price:90,count:3}] >> [table:each]{parallel:3,on_error:"collect"}{return {id:$it.id,unit:$it.price/$it.count}}
$계산 >> [table:each]{[if:is_ok($it)]{return unwrap($it)}[else]{return {id:"b",error:error_of($it).message}}}
''')
add('T10', '입금 목록이 비어 있으면 다른 목록을 대신 쓰지 말고 합계 0으로 보여 주세요.', '''
$입금=[] ?? [{amount:999}]
return {count:len($입금),sum:reduce($입금,0,($누적,$행)=>$누적+$행.amount)}
''', {'count':0,'sum':0})
add('T11', '매일 오전 9시 읽기 작업을 예약하는 문장이 올바른지 검사해 주세요.', '''
[self:schedule]{repeat:"daily",time:"09:00",do:"#!ibl edition=2\\n[self:time]{}"}
''', check_only=True)
add('T12', '조건을 만족하면 요약 메일을 보낼 문장을 검사해 주세요.', '''
$건수=3
[if:$건수>0]{[others:channel_send]{channel_type:"email",to:"나",subject:"상상훈련 검수",body:f"새 항목 ${건수}건"}}
''', check_only=True)

for case in cases:
    for mode in ('check','execute'):
        if case['check_only'] and mode=='execute':
            continue
        payload=dict(code=case['code'],edition=2,project_id='컨텐츠',origin='training',check=mode=='check')
        (HERE / f"{case['name']}_{mode}_request.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2))
(HERE/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
print(f'Prepared {len(cases)} tasks, {len((HERE/"sample.md").read_text())} sample characters.')
