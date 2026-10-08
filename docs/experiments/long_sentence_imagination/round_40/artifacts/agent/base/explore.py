
import json,sys,openpyxl,collections
b=sys.argv[1]
inv=json.load(open(b+'/invoices.json',encoding='utf-8-sig'))
pur=json.load(open(b+'/purchases.json',encoding='utf-8-sig'))
print(type(inv),len(inv),inv[:3])
print(collections.Counter(type(i['amount']).__name__ for i in inv))
print(collections.Counter((i['client_id'],i['client']) for i in inv))
ids=[i['id'] for i in inv]; print('dup ids',[k for k,v in collections.Counter(ids).items() if v>1])
print('issued range',min(i['issued'] for i in inv),max(i['issued'] for i in inv))
print(set(len(i['issued']) for i in inv), set(len(i['due']) for i in inv))
print(len(pur),pur[:3]); print(collections.Counter(p['date'][:7] for p in pur))
print(collections.Counter((p['vendor_id'],p['vendor']) for p in pur))
print(collections.Counter(type(p['amount']).__name__ for p in pur))
wb=openpyxl.load_workbook(b+'/payroll_2026-09.xlsx',data_only=False)
for ws in wb:
  print('SHEET',ws.title,ws.max_row,ws.max_column)
  for r in ws.iter_rows(values_only=True): print(r)
