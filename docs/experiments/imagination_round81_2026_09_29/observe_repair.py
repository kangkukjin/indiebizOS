"""Observe existing local media read results; persist keys only, never personal rows."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'backend'),str(ROOT/'scripts')]
import boot_paths  # noqa: E402,F401
import importlib.util
import json
import time
from ibl_shape_sweep import _shape, OUT
from ibl_edition import source_context


def module(package,name='handler'):
    path=ROOT/'data/packages/installed/tools'/package/(name+'.py')
    spec=importlib.util.spec_from_file_location('observe81_'+package.replace('-','_')+'_'+name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def main():
    envs={}
    lecture=module('lecture_workspace')
    listed=json.loads(lecture._lecture_list({}))
    envs['self:lecture#list']=listed
    if listed.get('items'):
        envs['self:lecture#load']=json.loads(lecture._lecture_load({'lecture_id':listed['items'][0]['lecture_id']}))
    envs['self:photo']=module('photo-manager')._query_photos({'has_gps':True,'limit':5})
    radio=module('radio','tool_radio')
    envs['sense:radio#korean']=json.loads(radio.get_korean_radio())
    envs['limbs:radio_favorite#list']=json.loads(radio.get_radio_favorites())
    music=module('music-player')
    envs['self:music#library']=music._library({'limit':5})
    web=module('web-builder')
    envs['engines:web_site#list']=web._h_site_list({},None)
    envs['engines:web_component@kind=components']=web._h_web_catalog({'kind':'components'},None)
    envs['engines:web_component@kind=sections']=web._h_web_catalog({'kind':'sections'},None)
    with source_context(2):
        envs['engines:image_read#critic']=module('media_producer','vision_read').critique_image(
            {'image_path':'/nonexistent_fixture.png','intent':'fixture','prescreen':'blank'},'.')
    prior=json.loads(OUT.read_text()) if OUT.exists() else {'shapes':{}}
    observations={}
    for key,value in envs.items():
        if isinstance(value,str):value=json.loads(value)
        if value.get('success') is False:raise RuntimeError('observation failed: '+key)
        kind,keys,more=_shape(value)
        if not keys:continue
        entry={'kind':kind,'keys':keys,'observed':time.strftime('%Y-%m-%d'),'source':'fixture',**({'more':more} if more else {})}
        prior['shapes'][key]=entry;observations[key]=entry
    prior['updated']=time.strftime('%Y-%m-%dT%H:%M:%S')
    OUT.write_text(json.dumps(prior,ensure_ascii=False,indent=1)+'\n')
    Path(__file__).with_name('repair_observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2)+'\n')
    print('Observed',len(observations),'shapes; personal rows not saved')


if __name__=='__main__':main()
