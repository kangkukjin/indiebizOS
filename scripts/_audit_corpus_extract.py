#!/usr/bin/env python3
"""감사용: 노드별 코퍼스 액션→파라미터 키/예시 추출 (실제 IBL 파서 사용).
사용: python scripts/_audit_corpus_extract.py <node>   # 예: sense
출력: 액션별 {코퍼스 param 키 빈도, op 값 분포, 예시 intent 3개}
"""
import sys, json, os, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
import ibl_parser  # type: ignore

node_filter = sys.argv[1] if len(sys.argv) > 1 else None
files = [
    'data/training/ibl_training_balanced_20260516.json',
    'data/training/ibl_distilled.json',
]
entries = []
for f in files:
    p = os.path.join(os.path.dirname(__file__), '..', f)
    if os.path.exists(p):
        entries += json.load(open(p))

# action -> {params: Counter, ops: Counter, examples: []}
data = collections.defaultdict(lambda: {'params': collections.Counter(), 'ops': collections.Counter(), 'examples': [], 'count': 0})

for e in entries:
    code = e.get('ibl_code', '')
    intent = e.get('intent', '')
    try:
        parsed = ibl_parser.parse(code)
    except Exception:
        continue
    # parsed may be a list of statements / nested; walk for node:action dicts
    def walk(obj):
        out = []
        if isinstance(obj, dict):
            if '_node' in obj and 'action' in obj:
                out.append(obj)
            for v in obj.values():
                out += walk(v)
        elif isinstance(obj, list):
            for v in obj:
                out += walk(v)
        return out
    for st in walk(parsed):
        nd, act = st.get('_node'), st.get('action')
        if node_filter and nd != node_filter:
            continue
        key = f"{nd}:{act}"
        params = st.get('params', {}) or {}
        d = data[key]
        d['count'] += 1
        for pk in params:
            d['params'][pk] += 1
        if 'op' in params:
            d['ops'][str(params['op'])] += 1
        if len(d['examples']) < 3:
            d['examples'].append({'intent': intent[:70], 'code': code[:120]})

for key in sorted(data):
    d = data[key]
    print(f"\n### {key}  (코퍼스 {d['count']}건)")
    print("  params:", dict(d['params'].most_common()))
    if d['ops']:
        print("  ops:", dict(d['ops'].most_common()))
    for ex in d['examples']:
        print(f"    예: {ex['intent']}  ->  {ex['code']}")
