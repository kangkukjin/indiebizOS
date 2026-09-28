"""읽기 전용 census: 핸들러 op 함수가 입력 dict에서 읽는 키 vs tool.json input_schema (판본 2 허용 키)."""
import ast, json, sys
from pathlib import Path
BASE=Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
import yaml
nodes=yaml.safe_load(open(BASE/'data/ibl_nodes.yaml'))
nodes=nodes.get('nodes',nodes)
tool2act={}
for n,nd in nodes.items():
    for a,c in (nd.get('actions') or {}).items():
        if isinstance(c,dict) and c.get('router')=='handler' and c.get('tool') and not c.get('open_params'):
            tool2act.setdefault(c['tool'],[]).append((n,a,c))
UNIV={'op','target','project_id','scope','criteria'}
rows=[]
for tj in (BASE/'data/packages/installed/tools').glob('*/tool.json'):
    pkg=tj.parent
    try: d=json.load(open(tj))
    except Exception: continue
    tools=d if isinstance(d,list) else d.get('tools',[d])
    schema={t.get('name'):set(((t.get('input_schema') or {}).get('properties') or {}).keys()) for t in tools if isinstance(t,dict)}
    h=pkg/'handler.py'
    if not h.exists(): continue
    src=h.read_text(); tree=ast.parse(src)
    funcs={f.name:f for f in ast.walk(tree) if isinstance(f,ast.FunctionDef)}
    disp=None
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_OP_DISPATCHERS' for t in node.targets):
            disp=node.value
    if not isinstance(disp,ast.Dict): continue
    for k,v in zip(disp.keys,disp.values):
        if not isinstance(k,ast.Constant) or not isinstance(v,ast.Dict): continue
        tool=k.value
        if tool not in tool2act or tool not in schema or not schema[tool]: continue
        allowed=set(schema[tool])|UNIV
        for n,a,c in tool2act[tool]:
            tk=c.get('target_key');
            if tk: allowed.add(tk)
            for can,alts in (c.get('aliases') or {}).items():
                allowed.add(can); allowed.update(alts or [])
        for opk,fv in zip(v.keys,v.values):
            fname=getattr(fv,'id',None) or getattr(fv,'attr',None)
            f=funcs.get(fname)
            if not f or not f.args.args: continue
            p=f.args.args[0].arg
            read=set()
            for node in ast.walk(f):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in('get','pop') and isinstance(node.func.value,ast.Name) and node.func.value.id==p and node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str):
                    read.add(node.args[0].value)
                if isinstance(node,ast.Subscript) and isinstance(node.value,ast.Name) and node.value.id==p and isinstance(node.slice,ast.Constant) and isinstance(node.slice.value,str):
                    read.add(node.slice.value)
            miss=sorted(read-allowed)
            if miss:
                rows.append({'pkg':pkg.name,'tool':tool,'actions':[f'{n}:{a}' for n,a,_ in tool2act[tool]],'op':getattr(opk,'value',None),'missing':miss})
print(json.dumps(rows,ensure_ascii=False,indent=0))
print('ops_with_missing',len(rows),'tools',len({r['tool'] for r in rows}), file=sys.stderr)
