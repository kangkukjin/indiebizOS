import json,sys
R=sys.argv[1]; B=R+'/ai/base/runs/'; V=R+'/ai/variant/runs/'
b=json.load(open(B+'results_base.json')); v=json.load(open(V+'results_variant.json'))
def idx(r): return {(x['question_id'],x['method']):x for x in r['results']}
bi,vi=idx(b),idx(v)
rows=[]
for k in sorted(vi):
    bt=[d if isinstance(d,str) else d.get('doc_id',d.get('id')) for d in bi[k]['top_docs']] if k in bi else None
    vt=[d if isinstance(d,str) else d.get('doc_id',d.get('id')) for d in vi[k]['top_docs']]
    rows.append({"q":k[0],"method":k[1],"base_top":bt,"variant_top":vt,"same":bt==vt,"answer_field":vi[k]['answer']})
pb=json.load(open(B+'passage_ranks.json'))['rows']; pv=json.load(open(V+'passage_ranks_variant.json'))['rows']
pr=[]
for x,y in zip(pb,pv):
    pr.append({"q":x['question_id'],"doc":x['doc'],"anchor_base":x['anchor'],"anchor_variant":y['anchor'],**{m:[x[m],y[m]] for m in ('bm25_ws','bm25_ko','dense_ko','rrf_bm25ko_dense')}})
json.dump({"top_docs":rows,"passage_ranks_base_vs_variant":pr,"eval_base":b.get('evaluation_against_self_qrels'),"eval_variant":v.get('evaluation_against_self_qrels')},open(R+'/ai/variant/compare_base_variant.json','w'),ensure_ascii=False,indent=1)
for r in rows:
    if not r['same'] or r['q'] in('Q04','Q05','Q06'): print(r['q'],r['method'],r['base_top'],'->',r['variant_top'],'' if r['same'] else 'CHANGED')
print('changed count',sum(not r['same'] for r in rows),'/',len(rows))
for p in pr: print(p)
