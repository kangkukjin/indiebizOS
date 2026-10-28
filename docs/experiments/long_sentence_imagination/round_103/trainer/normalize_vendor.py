import json,sys
args=json.load(sys.stdin)
rows=[]
for item in args['items']:
 row=dict(item)
 for k in ['pack','pack_price','shipping']:row[k]=int(row[k])
 if row['pack']<=0:raise ValueError('positive pack required')
 row['unit_price']=row['pack_price']/row['pack']
 if row['unit_price'].is_integer():row['unit_price']=int(row['unit_price'])
 rows.append(row)
print(json.dumps(rows,ensure_ascii=False))
