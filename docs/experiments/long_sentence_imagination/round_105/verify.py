"""Independent report comparison. Does not import the implementation under test."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'backend'))
import boot_paths
import json,hashlib
OUT=Path(__file__).resolve().parents[4]/'outputs/long_sentence_imagination/2026-11-01_105회차'
FIELDS=['asset_id','branch','expected_cost','actual_cost','difference','missing_check','duplicate_count']
def verify(report,oracle):
    actual=json.loads(report.read_text());expected=json.loads(oracle.read_text());errors=[]
    if not isinstance(actual,dict):return {'passed':False,'errors':['not object']}
    rows=actual.get('rows',[])
    if len(rows)!=len(expected['rows']):errors.append(f'row count {len(rows)} != {len(expected["rows"])}')
    for n,(a,e) in enumerate(zip(rows,expected['rows'])):
        for field in FIELDS:
            if a.get(field)!=e[field]:errors.append(f'row {n} {field}: {a.get(field)!r} != {e[field]!r}')
    for key in ['total_actual','duplicates','missing_checks','mismatches','unmatched']:
        if actual.get(key)!=expected[key]:errors.append('mismatch: '+key)
    if 'branch_totals' in expected and actual.get('branch_totals')!=expected['branch_totals']:errors.append('mismatch: branch_totals')
    return {'passed':not errors,'rows_checked':len(expected['rows']),'cells_checked':len(expected['rows'])*len(FIELDS),'errors':errors[:30],'error_count':len(errors),'report_sha256':hashlib.sha256(report.read_bytes()).hexdigest(),'oracle_sha256':hashlib.sha256(oracle.read_bytes()).hexdigest()}
if __name__=='__main__':
    result=verify(Path(sys.argv[1]),Path(sys.argv[2]));print(json.dumps(result,ensure_ascii=False,indent=2))
    if len(sys.argv)>3:Path(sys.argv[3]).write_text(json.dumps(result,ensure_ascii=False,indent=2))
