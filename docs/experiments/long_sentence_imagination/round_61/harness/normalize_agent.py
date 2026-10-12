"""Rename result fields for the shared oracle. No value calculation or imputation."""
import json
import shutil
from prepare import OUT, write

for case in ['base','missing']:
    src=OUT/'agent'/case/'out';dest=OUT/'agent'/case/'normalized'
    d=json.loads((src/'result.json').read_text());c=d['counts']
    adapted={'summary':{'raw':c['raw_event_rows'],'unique':c['unique_events'],
        'excluded':c['excluded_by_latest_selection'],'matched':c['status']['일치'],
        'different':c['status']['차이'],'unknown':c['status']['미확인']},
        'rows':[{**r,'known':r['confirmed_net'],'missing':len(r['unknown_qty_ids']),
                 'difference':r['diff_counted_minus_expected'],'ids':r['evidence_ids']} for r in d['rows']],
        'unknown_events':d['unknown_qty_events'],
        'unregistered':[{**r,'known':r['confirmed_net'],'missing':len(r['unknown_qty_ids']),
                         'ids':r['evidence_ids']} for r in d['unregistered_combinations']],
        'failed_sources':[{'name':r['file']} for r in d['missing_files']]}
    write(dest/'result.json',adapted);shutil.copyfile(src/'report.md',dest/'report.md')
