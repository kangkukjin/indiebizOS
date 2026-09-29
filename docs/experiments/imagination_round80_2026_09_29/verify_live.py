"""Read-only live smoke checks. Store assertions and counts, never private rows."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
import boot_paths  # noqa: E402,F401
import json
import requests


def run(code, check=False):
    response=requests.post('http://127.0.0.1:8765/ibl/execute',json={
        'code':'#!ibl edition=2\n'+code,'edition':2,'check':check,
        'project_id':'컨텐츠','origin':'training','agent_id':'IT80_repair','task_id':'IT80_repair'},timeout=90)
    response.raise_for_status()
    return response.json()


def main():
    checks=[]
    for name,code in [
        ('blog_snapshot','return [self:blog]{op:"latest"}'),
        ('feed_zero','return [others:feed]{op:"read",limit:0}'),
        ('neighbor_projection','return [others:neighbor]{op:"list"}'),
        ('bulletin_posts','$b=[others:bulletin]{op:"status"}; return $b.items >> [table:each] { return [others:bulletin]{op:"detail",board_id:$it.id} }'),
        ('unknown_category','return [self:blog]{op:"posts",category:"IT80_NONEXISTENT_CATEGORY"}')]:
        result=run(code); value=result.get('value')
        if name=='unknown_category':assert result.get('success') is False
        else:assert result.get('success') is True,(name,result.get('error'))
        if name=='blog_snapshot':assert value['source']=='local_snapshot' and 'as_of' in value and 'stale' in value
        if name=='feed_zero':assert value['items']==[]
        if name=='neighbor_projection':assert all(not set(r)&{'portal_key','portal_pw','portal_login_id','warehouse_key'} for r in value['items'])
        if name=='bulletin_posts':assert all(v['items']==v['posts'] and 'board' in v for v in value)
        checks.append({'case':name,'passed':True})
    for code in ['[others:publish]{title:"fixture",content:"fixture",dry_run:true}',
                 '[others:feed]{op:"post",content:"fixture",preview:true}',
                 '[others:delegate]{agent_id:"fixture",message:"fixture",mode:"sinc"}']:
        result=run(code,True)
        assert result.get('status')=='invalid'
        checks.append({'case':'unsupported_argument','passed':True,'codes':[r['code'] for r in result.get('issues',[])]})
    report={'checks':checks,'external_publications':0,'paid_model_calls':0}
    Path(__file__).with_name('repair_live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(len(checks),'live checks passed')


if __name__=='__main__':main()
