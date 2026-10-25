#!/usr/bin/env python3
"""One-shot, resumable retirement using existing catalog/calendar/trigger owners.

Default: prepare and validate without writes. --apply requires the desktop
runtime to be STOPPED. Source/history revisions are never edited in place.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: E402,F401
import argparse
import copy
import json
import uuid

import function_store as store
from ibl_edition import source_edition
from ibl_edition1_candidates import candidates

BATCH = 'ibl-edition1-retirement-2026-10-25'
RENAMES = {'AI시대 보고서 출처 뉴스 갱신': 'AI시대출처뉴스갱신'}


def read_json(path):
    return json.loads(path.read_text())


def migrated_source(source):
    """Only reviewed literal leaf calls, not a runtime transpiler."""
    if source_edition(source) == 2:
        return source
    from ibl_v2_parser import parse
    from ibl_v2_ir import Node
    body = parse(source).data['statements']
    if len(body) != 1 or body[0].kind != 'call':
        raise ValueError('구판 복합 소비자는 개별 이관이 필요합니다.')
    call = body[0].data
    if call.get('node') == 'self' and call.get('action') == 'workflow':
        values = {key: value.data.get('value') for key,value in call['params'].data['fields'].items() if value.kind=='literal'}
        if values == {'op':'run','workflow_id':'AI시대_보고서_출처_뉴스_갱신'}:
            return '#!ibl edition=2\n[fn:AI시대출처뉴스갱신]{}'
        raise ValueError('검토되지 않은 workflow 참조입니다.')
    if (call.get('node'),call.get('action')) not in {('self','script'),('others','delegate')}:
        raise ValueError('검토되지 않은 구판 잎 소비자입니다.')
    def literal(node):
        if isinstance(node, Node):
            if node.kind not in {'literal','record','list'}:
                raise ValueError('동적 소비자는 개별 이관이 필요합니다.')
            literal(node.data)
        elif isinstance(node, dict):
            for value in node.values(): literal(value)
        elif isinstance(node, (tuple,list)):
            for value in node: literal(value)
        elif isinstance(node,str) and '$' in node:
            raise ValueError('문자열 치환 소비자는 개별 이관이 필요합니다.')
    literal(call['params'].data['fields'])
    fields = call['params'].data['fields']
    if call.get('node') == 'others' and fields.get('mode') and fields['mode'].data.get('value') == 'workflow':
        raise ValueError('중첩 위임 프로그램은 개별 이관이 필요합니다.')
    return '#!ibl edition=2\n' + source


def prepare(base):
    from function_library import definitions
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    view, index = store.snapshot(), store.catalog()
    native = candidates()
    additions, retirements, mappings = [], [], []
    for old in view['records'].values():
        if old.get('edition') != 1 or old.get('state') != 'active':
            continue
        name = RENAMES.get(old['name'],old['name'])
        current = store.resolve(name,edition=2,view=view)
        if current is None:
            source = native[name]
            fid = uuid.uuid5(uuid.NAMESPACE_URL, BATCH+':'+old['function_id']).hex
            record = {'schema':1,'scope_id':index['scope_id'],'function_id':fid,
                      'name':name,'edition':2,'source':source,'source_hash':store.digest(source),
                      'description':old.get('description',''),'origin':old.get('origin','user'),
                      'provenance':{'migration':BATCH,'previous':store.reference(old),
                                    'runtime_success_claimed':False}}
            from function_migration import _body_hash
            record['installation_source_hash'] = _body_hash(record)
            additions.append({'record':record,'expected_revision':None,'state':'active','legacy_ids':[]})
            current = {**record,'revision':store.digest(record),'state':'active'}
        # State-only retirement preserves the original immutable revision/hash.
        original = store.revision(old['function_id'],old['revision'])
        original.pop('revision')
        retirements.append({'record':original,'expected_revision':old['revision'],
                            'state':'retired','legacy_ids':old.get('legacy_ids',[])})
        mappings.append({'old':store.reference(old),'new':store.reference(current),
                         'disposition':'existing_native' if name not in native else 'native_migration'})
    projected = copy.deepcopy(view)
    for change in additions:
        r=change['record'];projected['records'][r['function_id']]={**r,'revision':store.digest(r),'state':'active'}
    for change in retirements:
        projected['records'][change['record']['function_id']]['state']='retired'
    library,registry=definitions(projected),load_registry()
    for name, source in library.items():
        plan=compile_program(source,registry,definitions=library)
        if plan.issues:
            raise ValueError(f'{name}: {plan.issues}')
    files=[]
    for relative,key in [('data/calendar_events.json','events'),('data/event_triggers.json','triggers')]:
        path=base/relative
        if not path.exists(): continue
        before=read_json(path); after=copy.deepcopy(before);changed=[]
        for row in after[key]:
            if not row.get('enabled',True): continue
            payload=row.get('action_params',{}) if key=='events' else row
            source=payload.get('pipeline')
            if source is None: continue
            if not isinstance(source,str):
                raise ValueError(f'{relative}/{row["id"]}: 구판 단계 배열은 개별 이관해야 합니다.')
            updated=migrated_source(source)
            if updated != source:
                payload['pipeline']=updated
                payload.pop('edition',None)
                changed.append(row['id'])
            plan=compile_program(updated,registry,payload.get('inputs') or {},definitions=library)
            if plan.issues: raise ValueError(f'{relative}/{row["id"]}: {plan.issues}')
        if changed:
            files.append({'path':relative,'before_hash':store.digest(before),
                          'after_hash':store.digest(after),'before':before,'after':after,'ids':changed})
    return {'batch':BATCH,'generation':view['generation'],'catalog_hash':store.digest(index),
            'additions':additions,'retirements':retirements,'files':files,'mappings':mappings,
            'native_count':len(library),'stages':[]}


def stopped(base):
    state=base/'data/restart_control/state.json'
    if not state.exists() or read_json(state).get('phase')!='STOPPED':
        raise ValueError('라이브 런타임을 먼저 drain 후 정상 정지해야 합니다.')


def save_owner(base, entry):
    """Owner serialization plus CAS; never restore unrelated newer content."""
    path=base/entry['path']
    current=read_json(path)
    digest=store.digest(current)
    if digest==entry['after_hash']: return
    if digest!=entry['before_hash']:
        raise ValueError(f'소비자가 변경됐습니다: {entry["path"]}')
    if entry['path'].endswith('calendar_events.json'):
        import calendar_manager as owner
        if owner.CALENDAR_CONFIG_PATH.resolve()!=path.resolve(): raise ValueError('캘린더 소유 경로 불일치')
        manager=owner.CalendarManagerBase()
        with owner._SAVE_LOCK:
            if store.digest(manager._load_config())!=entry['before_hash']: raise ValueError('캘린더 CAS 충돌')
            manager.config=entry['after']
            manager._save_config()
    else:
        import trigger_engine as owner
        if owner.TRIGGERS_PATH.resolve()!=path.resolve(): raise ValueError('트리거 소유 경로 불일치')
        with owner._TRIGGERS_LOCK:
            if store.digest(owner.load_triggers())!=entry['before_hash']: raise ValueError('트리거 CAS 충돌')
            owner._save_triggers(entry['after'])


def apply(base, backup):
    stopped(base)
    path=backup/'retirement-batch.json'
    if path.exists():
        plan=read_json(path)
    else:
        plan=prepare(base)
        backup.mkdir(parents=True,exist_ok=True)
        store._atomic(path,json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    if 'retired' in plan['stages']:
        return plan
    def stage(name):
        if name not in plan['stages']: plan['stages'].append(name)
        store._atomic(path,json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    with store.transaction():
        stopped(base)
        index=store.catalog()
        if 'published' not in plan['stages']:
            if BATCH+':publish' not in index.get('requests',{}) and store.digest(index)!=plan['catalog_hash']:
                raise ValueError('함수 원장 CAS 충돌')
            metadata={**index.get('migration',{}),'edition1_retirement':{'batch':BATCH,'complete':False}}
            store.publish(plan['additions'],expected_generation=plan['generation'],migration=metadata,
                          request_id=BATCH+':publish')
            stage('published')
        for entry in plan['files']:
            stopped(base)
            save_owner(base,entry)
            stage(entry['path'])
        if 'retired' not in plan['stages']:
            index=store.catalog()
            metadata={**index.get('migration',{}),'edition1_retirement':{
                'batch':BATCH,'complete':True,'mapping':plan['mappings']}}
            store.publish(plan['retirements'],expected_generation=index['generation'],migration=metadata,
                          request_id=BATCH+':retire')
            stage('retired')
    return plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    base=Path(__file__).resolve().parents[1]
    backup=base/'data/_backups/2026-10-25_ibl_edition1_retirement'
    plan=apply(base,backup) if args.apply else prepare(base)
    print(json.dumps({'batch':BATCH,'native_count':plan['native_count'],
        'new_functions':len(plan['additions']),'retiring_functions':len(plan['retirements']),
        'consumers':{f['path']:f['ids'] for f in plan['files']},'stages':plan['stages']},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
