"""Apply the individually reviewed round-81 lessons, preserving source/history.

Default is read-only. --apply prepares local vectors, makes an online backup,
then updates code/provenance/FTS/vectors in one transaction. No tool execution.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts')]
import boot_paths  # noqa: E402,F401
import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime
from ibl_edition import source_edition
from verify_repair import verify

HERE = Path(__file__).resolve().parent
RESET = {'success_count':0,'fail_count':0,'bypass_count':0,'avg_ms':-1.0,'avg_tokens':-1.0}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def revise(old, review):
    provenance = old.get('provenance') or {}
    provenance = json.loads(provenance) if isinstance(provenance,str) else dict(provenance)
    provenance.setdefault('corpus_versions', []).append({
        'edition':source_edition(old['ibl_code']), 'code':old['ibl_code'],
        'intent':old['intent'], 'sha256':digest(old['ibl_code']),
        'observations':{k:old[k] for k in RESET if k in old}})
    provenance['corpus_review'] = {'edition':2, 'decision':'repair',
        'reason':'81회차: 명시 순서·items·값 참조·콜백·실패 중단 계약을 의도별 재검토',
        'review_sha256':digest((HERE/'corpus_review.json').read_text()),
        'fixture_verified':True, 'runtime_success_claimed':False, 'external_execution':'not_run'}
    return {**old, 'ibl_code':review['after'], 'intent':review['intent'],
            'provenance':provenance, 'updated_at':datetime.now().isoformat(), **RESET,
            'signature':'', 'returns':''}


def main(apply=False):
    proof = verify()
    reviews = json.loads((HERE/'corpus_review.json').read_text())
    dbpath = ROOT/'data/ibl_usage.db'
    with sqlite3.connect(dbpath.resolve().as_uri()+'?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row
        rows = {r['id']:dict(r) for r in conn.execute('SELECT * FROM ibl_examples')}
    pending = []
    for r in reviews:
        old=rows[r['id']]
        if old['ibl_code']==r['after'] and old['intent']==r['intent']:
            continue
        if old['ibl_code'] not in (r['before'], r['after']) or old['intent']!=r['intent_before'] or old.get('alias'):
            raise ValueError('review/source conflict: '+str(r['id']))
        pending.append(r)
    report={'reviewed':len(reviews),'fixture_checks':len(proof['checks']),'pending':len(pending),'applied':False}
    if not apply:
        print(json.dumps(report));return
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    from ibl_usage_db import IBLUsageDB, _signature_of, _tree_refresh
    indexer=object.__new__(IBLUsageDB)
    if not indexer._load_model_sync():raise RuntimeError('local embedding model unavailable')
    vectors=indexer._generate_embeddings_batch([indexer._prepare_search_text(r['intent'],r['after']) for r in pending])
    if len(vectors)!=len(pending):raise RuntimeError('vectors not ready')
    backup=ROOT/'data/_backups'/datetime.now().strftime('%Y-%m-%d_imagination81_remaining_%H%M%S')
    backup.mkdir(parents=True)
    with sqlite3.connect(dbpath.resolve().as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(backup/'ibl_usage.db') as target:
        source.backup(target)
    (backup/'corpus_review.json').write_text((HERE/'corpus_review.json').read_text())
    conn=indexer._get_vec_connection()
    if conn is None:raise RuntimeError('vector connection unavailable')
    try:
        conn.execute('BEGIN IMMEDIATE')
        for r,vector in zip(pending,vectors):
            old=dict(conn.execute('SELECT * FROM ibl_examples WHERE id=?',(r['id'],)).fetchone())
            if old['ibl_code'] not in (r['before'], r['after']) or old['intent']!=r['intent_before']:
                raise ValueError('concurrent change: '+str(r['id']))
            new=revise(old,r)
            new['signature']=_signature_of(new['ibl_code'])
            new['provenance']=json.dumps(new['provenance'],ensure_ascii=False)
            columns=['ibl_code','intent','signature','returns','provenance','updated_at',*RESET]
            if 'edition' in old:new['edition']=2;columns.append('edition')
            conn.execute('UPDATE ibl_examples SET '+','.join(k+'=?' for k in columns)+' WHERE id=?',
                         [new[k] for k in columns]+[r['id']])
            conn.execute('DELETE FROM ibl_examples_vec WHERE rowid=?',(r['id'],))
            conn.execute('INSERT INTO ibl_examples_vec(rowid,embedding) VALUES (?,?)',(r['id'],vector))
            actual=conn.execute('SELECT embedding FROM ibl_examples_vec WHERE rowid=?',(r['id'],)).fetchone()[0]
            assert bytes(actual)==bytes(vector)
        conn.execute("INSERT INTO ibl_examples_fts(ibl_examples_fts, rank) VALUES ('integrity-check', 1)")
        conn.commit()
    except BaseException:
        conn.rollback();raise
    finally:conn.close()
    # Exact mirrors in trainer input files retain their own original metadata.
    mirror_count=0
    by_code={r['before']:r for r in reviews}
    for path in sorted((ROOT/'data/training').glob('*.json')):
        original=path.read_text()
        try:data=json.loads(original)
        except ValueError:continue
        if not isinstance(data,list):continue
        changed=False
        for i,row in enumerate(data):
            if not isinstance(row, dict):continue
            r=by_code.get(row.get('ibl_code'))
            if r is None:
                r=next((r for r in reviews if row.get('ibl_code')==r['after']
                        and row.get('intent')==r['intent_before'] and r['intent']!=r['intent_before']), None)
            if r is None:continue
            updated=revise(row,{**r,'intent':r['intent'] if row.get('intent')==r['intent_before'] else row.get('intent','')})
            updated['edition']=2;data[i]=updated;changed=True;mirror_count+=1
        if changed:
            (backup/path.name).write_text(original)
            if path.read_text()!=original:raise ValueError('training file changed: '+path.name)
            path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    _tree_refresh(*(rows[r['id']].get('topic','') for r in pending),strict=True)
    report.update(applied=True,pending=0,db_rows=len(pending),training_mirrors=mirror_count,
                  backup=str(backup.relative_to(ROOT)),vector_content_verified=len(pending),fts_integrity='ok')
    application=HERE/'corpus_application.json'
    history=json.loads(application.read_text()) if application.exists() else {}
    previous=history.get('applications', [history] if history else [])
    report['applications']=previous + [dict(report)]
    report['total_db_rows']=len(reviews)
    report['db_revision_operations']=sum(x.get('db_rows',0) for x in report['applications'])
    report['total_training_mirrors']=sum(x.get('training_mirrors',0) for x in report['applications'])
    application.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');args=p.parse_args();main(args.apply)
