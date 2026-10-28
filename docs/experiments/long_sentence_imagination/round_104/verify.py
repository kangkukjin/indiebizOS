import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "outputs/long_sentence_imagination/2026-10-28_104회차"
def main(actual,ledger=None):
 expected=json.loads((BASE/'harness/expected.json').read_text());checks=0
 for k in ['total_cost','hold_count']:assert actual[k]==expected[k],k
 for x,y in zip(actual['libraries'],expected['libraries']):
  for k in ['library','label','total_cost','ready']:assert x[k]==y[k],(k,x.get(k),y[k])
  assert len(x['lines'])==200
  rows={r['item']:r for r in x['lines']}
  for row in y['lines']:
   for k,v in row.items():assert rows[row['item']][k]==v,(y['library'],row['item'],k,rows[row['item']][k],v);checks+=1
 if ledger:
  receipts=[json.loads(s) for s in Path(ledger).read_text().splitlines()];assert len(receipts)==3
  assert len({r['receipt'] for r in receipts})==3
  for receipt,lib in zip(receipts,actual['libraries']):
   body=receipt['request'];assert body['library']==lib['library'];assert body['lines']==lib['lines'];assert body['total_cost']==lib['total_cost']
 return checks

def region(a):
 e=json.loads((BASE/'harness/variant_expected.json').read_text());checks=0
 assert a['transfer_cost']==e['transfer_cost']
 for x,y in zip(a['transfers'],e['transfers']):
  for k,v in y.items():assert x[k]==v,(k,x,y)
 assert len(a['transfers'])==len(e['transfers'])
 for mode in ['base','with_transfer']:
  for policy in ['deadline','budget']:
   x=a[mode][policy];y=e[mode][policy];assert x['total_cost']==y['total_cost'],(mode,policy,x['total_cost'],y['total_cost'])
   for lx,ly in zip(x['libraries'],y['libraries']):
    for k in ['library','total_cost','over_budget']:assert lx[k]==ly[k],(mode,policy,k)
    assert len(lx['lines'])==200;rows={r['item']:r for r in lx['lines']}
    for row in ly['lines']:
     for k,v in row.items():assert rows[row['item']][k]==v,(mode,policy,ly['library'],row['item'],k,rows[row['item']][k],v);checks+=1
 return checks
