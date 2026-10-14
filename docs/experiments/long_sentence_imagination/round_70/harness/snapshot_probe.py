"""Production cache/IBL facade, isolated SQLite, synthetic fetch boundary."""
import json
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/'backend'))
import boot_paths  # noqa: E402
import warehouse_feed as wf  # noqa: E402
import warehouse_ops as wo  # noqa: E402

HERE=Path(__file__).resolve().parents[1]
label=sys.argv[1]
with tempfile.TemporaryDirectory(prefix='warehouse70-') as tmp:
    wf.DB_PATH=Path(tmp)/'warehouse.db'
    base='https://synthetic.invalid'
    facts={'scope':'production cache and warehouse_op, temporary DB, synthetic fetch'}
    facts['unpolled']=wo.warehouse_op({'op':'browse','url':base})
    wf._fetch_with_auth=lambda *_: ({'files':[]},'native')
    facts['empty_poll']=wo.warehouse_op({'op':'poll','url':base})
    facts['confirmed_empty']=wo.warehouse_op({'op':'browse','url':base})
    wf._fetch_with_auth=lambda *_: ({'files':[{'name':'folder/event.json','mtime':'2026-10-15','bytes':12}]},'native')
    facts['seed_poll']=wo.warehouse_op({'op':'poll','url':base})
    facts['seed_browse']=wo.warehouse_op({'op':'browse','url':base,'path':'folder'})
    def unavailable(*_):raise RuntimeError('503 synthetic unavailable')
    wf._fetch_with_auth=unavailable
    facts['failed_poll']=wo.warehouse_op({'op':'poll','url':base})
    facts['stale_browse']=wo.warehouse_op({'op':'browse','url':base,'path':'folder'})
    wf._fetch_with_auth=lambda *_: ({'files':[],'truncated':True},'native')
    facts['partial_poll']=wo.warehouse_op({'op':'poll','url':base})
    facts['partial_browse']=wo.warehouse_op({'op':'browse','url':base,'path':'folder'})
(HERE/'evidence'/f'snapshot-{label}.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2))
print(json.dumps(facts,ensure_ascii=False))
