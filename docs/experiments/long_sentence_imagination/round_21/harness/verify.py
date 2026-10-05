"""Independent source slices and minimal chunk counts; never re-runs IBL."""
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[5]
OUT=ROOT/'outputs/long_sentence_imagination/2026-10-05_21회차'


def verify(folder, size, documents=None, queries=None):
    if documents is None:
        documents=json.loads((OUT/'input/documents.json').read_text())['documents']
        queries=json.loads((OUT/'input/queries.json').read_text())
    index=json.loads((folder/'index.json').read_text())
    report=json.loads((folder/'report.json').read_text())
    expected_chunks=[];stats=[]
    for doc in documents:
        text=doc['text'];n=len(text)
        count=0 if n==0 else 1+max(0,math.ceil((n-size)/(size-64)))
        pieces=[]
        for i in range(count):
            start=i*(size-64);end=min(start+size,n)
            pieces.append(dict(doc_id=doc['id'],index=i,start=start,end=end,chars=end-start,text=text[start:end]))
        expected_chunks+=pieces
        chars=sum(p['chars'] for p in pieces)
        stats.append(dict(id=doc['id'],source_chars=n,chunks=count,chunk_chars=chars,duplicate_chars=chars-n))
    assert index['chunks']==expected_chunks
    agent='settings' in index
    actual_stats=[dict(id=r['doc_id'],source_chars=r['original_chars'],chunks=r['chunk_count'],chunk_chars=r['chunk_chars'],duplicate_chars=r['duplicate_chars']) if agent else {k:r[k] for k in stats[0]} for r in index['documents']]
    assert actual_stats==stats
    expected_queries=[dict(query=q,documents=[d['id'] for d in documents if q in d['text']]) for q in queries]
    actual_queries=[dict(query=r['query'],documents=r['doc_ids']) for r in report['search_results']] if agent else report['queries']
    assert actual_queries==expected_queries
    totals=report['totals'] if agent else report
    assert totals['documents']==len(documents) and totals['chunks']==len(expected_chunks)
    assert totals['original_chars' if agent else 'source_chars']==sum(r['source_chars'] for r in stats)
    assert totals['chunk_chars']==sum(r['chunk_chars'] for r in stats)
    assert totals['duplicate_chars']==sum(r['duplicate_chars'] for r in stats)
    assert report['validation']['passed'] if agent else report['verified']
    return {'documents':len(documents),'chunks':len(expected_chunks),'source_chars':sum(r['source_chars'] for r in stats),'all_fields_equal':True}


if __name__=='__main__':
    result={}
    for folder,size in [('trainer/index_base',512),('trainer/index_variant',777),('agent/base',512),('agent/variant',777),('trainer/base_after',512),('trainer/variant_after',777),('trainer/record_after',512),('trainer/record_variant_after',777)]:
        path=OUT/folder
        if (path/'index.json').is_file():
            result[folder]=verify(path,size)
    (ROOT/'docs/experiments/long_sentence_imagination/round_21/evidence/validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
