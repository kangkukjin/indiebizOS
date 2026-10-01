"""Round-16 harness; original execution is preserved at commit 987c85a9.

L16-3 repair: partial warm rollback is forbidden. Run seed -> warm -> cold in
isolated fixtures (cold needs its own seed without warm results). Warm must pass preflight against the seed snapshot and
postflight native-session continuity. A failed comparison never becomes valid
merely because its output is correct. The original round-16 warm stays invalid.
"""
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

import requests
from fixture import ROOT, WORK, HERE, dump


def config():
    return json.loads((WORK/'control.json').read_text())


def run(name):
    if name == 'warm':
        warm_preflight()
    c=config(); actor='baseline' if name=='baseline' else 'seed'
    pid=c['project']['id']; aid=c['agents'][actor]['id']
    base=f'http://127.0.0.1:8765/projects/{pid}/agents/{aid}'
    if name in ('baseline','seed'):
        r=requests.post(base+'/start',timeout=120); r.raise_for_status()
    prompt=(HERE/f'prompt_{name}.txt').read_text()
    t=time.time(); dump(WORK/f'{name}_started.json',dict(started_epoch=t,actor=aid))
    r=requests.post(base+'/command',json=dict(command=prompt,origin='training'),timeout=2500)
    (WORK/f'{name}_response.json').write_text(r.text)
    dump(WORK/f'{name}_elapsed.json',dict(elapsed_s=time.time()-t,http_status=r.status_code))
    if name == 'warm':
        seed = json.loads((WORK/'seed_snapshot.json').read_text())
        current = own_sessions(c)
        valid = r.status_code == 200 and current['codex_sessions.json'] == seed['sessions']['codex_sessions.json']
        dump(WORK/'warm_context_check.json', dict(valid=valid, expected=seed['sessions'],
             actual=current, reason='' if valid else 'native session changed; exclude warm comparison'))
    print(name,r.status_code,r.text[:300],flush=True)


def own_session_key(key, c):
    prefix=c['project']['id']+':'+c['agents']['seed']['id']+'@rehearsal'
    return key==prefix or key.startswith(prefix+'#')


def actor_messages(db, name):
    aid=db.execute('SELECT id FROM agents WHERE name=?',(name,)).fetchone()[0]
    return [r[0] for r in db.execute('SELECT id FROM messages WHERE from_agent_id=? OR to_agent_id=?',(aid,aid))]



def own_sessions(c):
    result = {}
    for filename in ('codex_sessions.json', 'codex_session_sizes.json'):
        obj = json.loads((ROOT/'data'/filename).read_text())
        result[filename] = {k: v for k, v in obj.items() if own_session_key(k, c)}
    return result


def comparison_state(path):
    """Read-only logical state of the dedicated fixture, including pursuit history."""
    with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as db:
        tables = ('messages', 'tasks', 'pursuit', 'pursuit_event', 'pursuit_turn')
        return {name: db.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall()
                for name in tables}


def warm_preflight():
    """Reject changed state before sending a model request; never roll it back."""
    if (WORK/'cold_started.json').exists() or (WORK/'isolation_cold.json').exists():
        raise RuntimeError('warm must run immediately after seed, before cold; no partial rollback')
    c = config()
    seed = json.loads((WORK/'seed_snapshot.json').read_text())
    backup = ROOT/'data/_backups/2026-10-01_lsi16_seed/conversations.db'
    if comparison_state(Path(c['project']['path'])/'conversations.db') != comparison_state(backup):
        raise RuntimeError('seed messages/tasks/pursuit state changed; exclude warm comparison')
    if not seed['sessions']['codex_sessions.json'] or own_sessions(c) != seed['sessions']:
        raise RuntimeError('seed native session state changed; exclude warm comparison')
    if any(Path(path).read_text() != text for path, text in seed['lineages'].items()):
        raise RuntimeError('seed reference lineage changed; exclude warm comparison')


def snapshot():
    c=config(); aid=c['agents']['seed']['id']; name=c['agents']['seed']['name']
    db=sqlite3.connect(Path(c['project']['path'])/'conversations.db')
    backup=ROOT/'data/_backups/2026-10-01_lsi16_seed'; backup.mkdir(parents=True,exist_ok=True)
    dst=sqlite3.connect(backup/'conversations.db'); db.backup(dst); dst.close()
    v=dict(messages=actor_messages(db,name),sessions={},lineages={})
    for filename in ('codex_sessions.json','codex_session_sizes.json'):
        p=ROOT/'data'/filename; obj=json.loads(p.read_text())
        v['sessions'][filename]={k:x for k,x in obj.items() if own_session_key(k,c)}
    pulse=sqlite3.connect('file:'+str(ROOT/'data/world_pulse.db')+'?mode=ro',uri=True)
    ep=pulse.execute('SELECT id FROM episode_log WHERE agent=? ORDER BY id DESC LIMIT 1',(name,)).fetchone()[0]
    event=json.loads(pulse.execute("SELECT data FROM trajectory_event WHERE episode_id=? AND kind='supervision.turn.opened' LIMIT 1",(ep,)).fetchone()[0])
    store=Path(event['store']); key=json.loads((store/'lineage.json').read_text())['key']
    ledger=store.parent.parent/'supervision_lineage'/f'{key}.jsonl'
    v['lineages'][str(ledger)]=ledger.read_text(); v['episode']=ep; v['store']=str(store)
    assert v['messages'] and v['sessions']['codex_sessions.json'],v
    dump(WORK/'seed_snapshot.json',v)
    print(json.dumps(v,ensure_ascii=False),flush=True)


def switch(condition):
    assert condition in ('cold','warm','restore')
    if condition == 'warm':
        raise RuntimeError('partial warm rollback is unsafe; run warm directly after seed')
    if condition == 'cold' and (WORK/'warm_started.json').exists():
        raise RuntimeError('cold needs an independent seed without warm results')
    c=config(); v=json.loads((WORK/'seed_snapshot.json').read_text())
    aid=c['agents']['seed']['id']; name=c['agents']['seed']['name']
    db=sqlite3.connect(Path(c['project']['path'])/'conversations.db')
    ids=actor_messages(db,name)
    if condition!='restore':
        for filename,seed in v['sessions'].items():
            p=ROOT/'data'/filename; obj=json.loads(p.read_text())
            current={k:x for k,x in obj.items() if own_session_key(k,c)}
            dump(WORK/f'before_{condition}_{filename}',current)
            obj={k:x for k,x in obj.items() if k not in current}
            if condition=='warm':obj.update(seed)
            p.write_text(json.dumps(obj,ensure_ascii=False,indent=2))
    for mid in ids:
        active=condition=='restore' or (condition=='warm' and mid in v['messages'])
        db.execute('UPDATE messages SET contact_type=? WHERE id=?',('rehearsal' if active else 'lsi16_hidden',mid))
    db.commit()
    if condition=='warm':
        hidden=ROOT/'data/_backups/2026-10-01_lsi16_cold_isolation'
        hidden.mkdir(parents=True,exist_ok=True)
        moved={}
        for filename in ('cold','cold_response.json','cold_elapsed.json','cold_started.json'):
            source=WORK/filename; target=hidden/filename
            assert source.exists() and not target.exists(),(source,target)
            source.rename(target); moved[str(source)]=str(target)
        dump(WORK/'cold_hidden_files.json',moved)
    if condition=='restore' and (WORK/'cold_hidden_files.json').exists():
        for source,target in json.loads((WORK/'cold_hidden_files.json').read_text()).items():
            assert not Path(source).exists(),source
            Path(target).rename(source)
    for path,seed in v['lineages'].items():
        p=Path(path)
        if condition=='warm':
            (WORK/'cold_lineage.jsonl').write_text(p.read_text()); p.write_text(seed)
        if condition=='restore' and (WORK/'cold_lineage.jsonl').exists():
            cold=(WORK/'cold_lineage.jsonl').read_text().splitlines()
            live=p.read_text().splitlines(); rows=list(dict.fromkeys(cold+live));p.write_text('\n'.join(rows)+'\n')
    dump(WORK/f'isolation_{condition}.json',dict(condition=condition,at=time.time(),message_ids=ids,
         seed_message_ids=v['messages'],native_seed_keys=list(v['sessions']['codex_sessions.json'])))
    print('switched',condition,flush=True)


if __name__=='__main__':
    op=sys.argv[1]
    if op=='run':run(sys.argv[2])
    elif op=='snapshot':snapshot()
    elif op=='switch':switch(sys.argv[2])
