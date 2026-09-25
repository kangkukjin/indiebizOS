"""Reviewed, source-specific rewrites; deliberately not a general transpiler."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import re
HERE = Path(__file__).resolve().parent

def save(name, code):
    (HERE/'current'/f'{name}.ibl').write_text('#!ibl edition=2\n'+code.strip()+'\n')
def old(name):
    return (HERE/'original'/f'{name}.ibl').read_text()

# Preserve queries, schemas and lengthy AI instructions verbatim. Change only
# the reviewed dataflow sites: union/dedup/AI return envelopes, native tables lists.
code=old('news')
code=re.sub(r'\[table:filter\]\{where: "(date|label) (>=|!=|==) ([^"]+)"\}',
            lambda m:'[table:filter]{where:($r)=>$r.'+m[1]+m[2]+'"'+m[3]+'"}',code)
code=code.replace('[table:union]', '[table:union]{} >> [fn:rows]{}')
code=re.sub(r'(\[table:dedup\]\{[^}]*\})',r'\1 >> [fn:rows]{}',code)
code=code.replace(' >> [table:filter]{where:($r)=>$r.label', ' >> [fn:rows]{} >> [table:filter]{where:($r)=>$r.label')
code=code.replace('$논문 >>', '$논문.items >>')
code=code.replace('$예약 = [sense:search]', '$예약원문 = [sense:search]')
code=code.replace('limit: 6} >> [table:filter]', 'limit: 6}\n$예약 = $예약원문.items >> [table:filter]')
code=code.replace('[on_error: null] $앤스로픽 = [sense:crawl]{url: "https://www.anthropic.com/news", op: "links"} >> [table:take]{n: 30}',
'''$앤스로픽 = []
[try] { $링크 = [sense:crawl]{url:"https://www.anthropic.com/news",op:"links"}; $앤스로픽=$링크.items >> [table:take]{n:30} }
[catch] { $앤스로픽=[{error:$error.message}] }''')
save('news','[def:rows]($r){return $r.items}\n'+code)

save('housing','''
$전세거래 = $molit_apt >> [table:filter]{where:($r)=>$r.계약유형=="전세" and $r.보증금>=20000 and $r.보증금<=40000}
$전세큰집 = $전세거래 >> [table:filter]{where:($r)=>$r.전용면적>=76}
$전세집계 = $전세거래 >> [table:groupby]{by:"아파트명",agg:{건수:["count","보증금"],평균보증금:["avg","보증금"],평균면적:["avg","전용면적"]}}
$전세단지 = $전세집계.items >> [table:sort]{by:"건수",descending:true} >> [table:take]{n:8}
$매매대상 = $molit_trade >> [table:filter]{where:($r)=>$r.전용면적>=76 and $r.전용면적<=90}
$매매집계 = $매매대상 >> [table:groupby]{by:"법정동",agg:{건수:["count","price"],평균가:["avg","price"]}}
$매매84 = $매매집계.items >> [table:sort]{by:"건수",descending:true} >> [table:take]{n:6}
$상권원문 = [sense:commercial]{lat:36.7849,lng:126.4503,radius:1500}
$상권집계 = $상권원문.items >> [table:groupby]{by:"category"}
$상권 = $상권집계.items >> [table:sort]{by:"count",descending:true} >> [table:take]{n:10}
$전세단지 & $매매84 >> [table:union]{}
''')
code=old('rotation').replace('$q >>','$q.items >>').replace('where: "visits == 0"','where:($r)=>$r.visits==0').replace('where: "verdict == 관심"','where:($r)=>$r.verdict=="관심"').replace('desc: true','descending:true')
code=code.replace('$recent = [self:file_find]', '$files = [self:file_find]').replace('} >> [table:sort]{by: "name"','}\n$recent = $files.items >> [table:sort]{by: "name"').replace('[table:union]','[table:union]{}')
save('rotation',code)
code=old('shops')
code=code.replace('$sg >>','$sg.items >>').replace('$ss >>','$ss.items >>').replace('desc: true','descending:true')
lines=code.splitlines()
for i in (2,3):
 a,b=lines[i].split(' >> [table:sort]');lines[i]=f'$g{i} = '+a+f'\n$g{i}.items >> [table:sort]'+b
for i in (4,5):
 a,b=lines[i].split(' >> [table:select]');lines[i]=f'$p{i} = '+a+f'\n$p{i}.items >> [table:select]'+b
save('shops','\n'.join(lines))
save('stocks',old('stocks').replace('$cpi >>','$cpi.items >>').replace('fields:', 'columns:'))

code=old('forex')
# The old each only called the clock to recover input rows. Keep those calls and
# explicitly return each input; the computed percentages remain identical.
code=re.sub(r', do: "\[self:time\]", keep: \[[^]]+\]\}', '} { [self:time]{}; return $it }',code)
code=re.sub(r'set: \{"([^"]+)": "round\(\(최근 - 시작\) / 시작 \* 100, 2\)"\}',lambda m:'set:($r)=>{"'+m[1]+'":round(($r.최근-$r.시작)/$r.시작*100,2)}',code)
code=code.replace('[table:union]', '[table:union]{} >> [fn:rows]{}')
code=code.replace('[sense:search]{source:', '$뉴스=[sense:search]{source:').replace('type: "news"} >>', 'type: "news"}\n$뉴스.items >>')
save('forex','[def:rows]($r){return $r.items}\n'+code)

for name in ('videos','enterprise'):
 code=old(name)
 code=code.replace('[table:union]', '[table:union]{}')
 # Insert explicit envelope extraction at each boundary.
 code=code.replace(' >> [table:dedup]', ' >> [table:dedup]')
 prefix=code[:code.index('$정보 =')]
 prefix=re.sub(r' >> \[table:filter\]\{where: \{field: "video_id", op: "not_in", value: "\$\{원장.items.\*.id\}"\}\}', '', prefix)
 code=prefix+'''
$기존ID=$원장.items >> [table:each]{return $it.id}
$대상=$검색.items >> [table:filter]{where:($r)=>not ($r.video_id in $기존ID)}
$처리=$대상 >> [table:take]{n:70} >> [table:each]{parallel:4,on_error:"collect"}{[sense:video]{op:"info",video_id:$it.video_id}}
$성공=$처리 >> [table:each]{mode:"flat_map"}{ [if:is_ok($it)]{ $v=unwrap($it); return $v.items } [else]{return []} }
$신선=$성공 >> [table:filter]{where:($r)=>$r.upload_date>="2026-03-11"} >> [table:sort]{by:"view_count",descending:true} >> [table:select]{columns:["video_id","title","uploader","view_count","duration","upload_date","url"]}
$신선 >> [table:take]{n:40}
'''
 if name=='enterprise':code=code.replace('n:70','n:60').replace('n:40','n:45')
 save(name,code)

src=old('transcripts')
schema=re.search("schema: '([^']*)'",src)[1]; criteria=re.search("criteria: '([^']*)'",src)[1]
save('transcripts',src.splitlines()[0]+'''
$선정=$심사 >> [table:filter]{where:($r)=>$r.selected==true} >> [table:take]{n:4}
$처리=$선정 >> [table:each]{parallel:2,on_error:"collect"}{
  $영상=$it
  $자막=[sense:video]{op:"transcript",video_id:$영상.video_id}
  $팁=[self:struct]{text:$자막.text,schema:"'''+schema+'",grounded:true,criteria:"'+criteria+'''"}
  $팁.items >> [table:compute]{set:($r)=>{title:$영상.title,uploader:$영상.uploader,url:$영상.url,video_id:$영상.video_id,view_count:$영상.view_count,duration:$영상.duration,upload_date:$영상.upload_date,reason:$영상.reason}}
}
$후보팁=$처리 >> [table:each]{mode:"flat_map"}{ [if:is_ok($it)]{return unwrap($it)} [else]{return []} }
$후보팁 >> [table:select]{columns:["video_id","title","tip","timestamp"]}
''')

save('ledger','''
[self:ledger]{op:"append",path:$ledger_path,target:"covered",items_file:$covered_path}
$팁수=$절제 >> [table:groupby]{by:"video_id",agg:{n:["count","tip"]}}
$선정행=[table:join]{left:$선정,right:$팁수,on:"video_id"}
$선정행.items >> [table:take]{n:4} >> [table:each]{mode:"effect"}{
 [self:ledger]{op:"upsert",path:$ledger_path,target:"covered",key:"id",item:{id:$it.video_id,title:$it.title,channel:$it.uploader,date:"2026-09-06",upload_date:$it.upload_date,topic:"평가",verdict:f"tips_${$it.n}"}}
}
[self:ledger]{op:"append",path:$ledger_path,target:"recent_topics",item:{date:"2026-09-06",topic:"평가"},max_items:10}
$기록=[self:ledger]{path:$ledger_path,op:"select",target:"covered",fields:["id","verdict"],where:{date:"2026-09-06"}}
$기록.items >> [table:groupby]{by:"verdict"}
'''.replace('${$it.n}','${it.n}'))

code=old('sources')
code=code.replace('do:"[sense:crawl]{url:$it.url}"}', '}{[sense:crawl]{url:$it.url}}')
# Previous each concatenated crawl rows. Keep the old flat result explicitly.
code=code.replace('$초록=[table:each]', '$초록봉투=[table:each]').replace('; $추가검색 & $초록', '; $초록=$초록봉투 >> [table:each]{mode:"flat_map"}{return $it.items}; $추가검색 & $초록 >> [table:union]{}')
save('sources',code)
code=old('reinforce').replace('as:"q",do:"[sense:search]{source:\'ddg\',query:$q.q,limit:4}"}', 'mode:"flat_map"}{ $r=[sense:search]{source:"ddg",query:$it.q,limit:4}; return $r.items }')
save('reinforce',code)

# Legacy multi-statement calls exposed intermediate results. Edition 2 returns
# one value, so retain the independent business outputs in a named record.
code=(HERE/'current'/'shops.ibl').read_text()
code=code.replace('$g2.items >>','$상권1=$g2.items >>').replace('$g3.items >>','$상권2=$g3.items >>')
code=code.replace('$p4.items >>','$병원=$p4.items >>').replace('$p5.items >>','$도서관=$p5.items >>')
code+='return {shops:[$상권1,$상권2],hospitals:$병원,libraries:$도서관}\n'
(HERE/'current'/'shops.ibl').write_text(code)
code=(HERE/'current'/'forex.ibl').read_text()
lines=code.splitlines()
for i,name in [(2,'연간'),(3,'구간'),(4,'주가'),(6,'뉴스선택')]:lines[i]='$'+name+'='+lines[i]
code='\n'.join(lines)+'\nreturn {year:$연간,period:$구간,quotes:$주가,news:$뉴스선택}\n'
(HERE/'current'/'forex.ibl').write_text(code)
code=(HERE/'current'/'stocks.ibl').read_text().replace('$cpi.items >>','$뉴스선택=$cpi.items >>')
code+='return {stocks:$종목,news:$뉴스선택}\n'
(HERE/'current'/'stocks.ibl').write_text(code)
