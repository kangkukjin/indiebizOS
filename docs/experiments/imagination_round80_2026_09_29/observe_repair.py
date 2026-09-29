"""Read local producers and persist field names only, with no personal values."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
import boot_paths  # noqa: E402,F401
import importlib.util
import json
import time
from types import SimpleNamespace
from ibl_shape_sweep import _shape, OUT


def module(package, name='handler'):
    path=ROOT/'data/packages/installed/tools'/package/(name+'.py')
    spec=importlib.util.spec_from_file_location('observe80_'+package.replace('-','_')+'_'+name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def main():
    envs={}
    blog=module('blog')
    for op in ('posts','latest'):
        envs['self:blog#'+op]=json.loads(blog.execute({'op':op,'limit':1},SimpleNamespace(tool_name='blog_op')))
    bulletin=module('bulletin')
    boards=json.loads(bulletin._status({}))
    envs['others:bulletin#status']=boards
    if boards['items']:
        envs['others:bulletin#detail']=json.loads(bulletin._detail({'board_id':boards['items'][0]['id']}))
    family=module('family-news')
    for op in ('status','comments','uploads'):
        envs['others:family_news#'+op]=json.loads(getattr(family,'_fn_'+op)({}))
    business=module('business')
    from business_manager import BusinessManager
    bm=BusinessManager()
    envs['others:neighbor#list']=json.loads(business._nb_list(bm,{}))
    inbox=json.loads(business._msg_inbox(bm,{}))
    envs['others:messages#inbox']=inbox
    if inbox['items']:
        row=next((r for r in inbox['items'] if r.get('is_neighbor')),None)
        if row:envs['others:messages#thread']=json.loads(business._msg_thread(bm,{'neighbor_id':row['id']}))
    envs['self:webapp#status']=module('system_essentials','webapp_registry').op_status({})
    prior=json.loads(OUT.read_text())
    observations={}
    for key,value in envs.items():
        if value.get('success') is False:raise RuntimeError('observation failed: '+key)
        kind,keys,more=_shape(value)
        if not keys:continue
        assert not set(keys)&{'portal_key','portal_pw','warehouse_key','portal_login_id'}
        entry={'kind':kind,'keys':keys,'observed':time.strftime('%Y-%m-%d'),'source':'fixture',**({'more':more} if more else {})}
        prior['shapes'][key]=entry;observations[key]=entry
    prior['updated']=time.strftime('%Y-%m-%dT%H:%M:%S')
    OUT.write_text(json.dumps(prior,ensure_ascii=False,indent=1)+'\n')
    Path(__file__).with_name('repair_observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2)+'\n')
    print('Observed',len(observations),'shapes; no personal rows persisted')


if __name__=='__main__':main()
