"""Synthetic inputs and independent expected values, kept out of executor bodies."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'backend'))
import boot_paths
import harness as h
import json,shutil

def main_inputs():
    assets=[];checks=[];bills=[]
    for i in range(1,601):
        aid=f'E{i:04}';cost=10000+i*17
        assets.append({'asset_id':aid,'branch':f'B{1+i%6}','expected_cost':cost})
        if i%10: checks.append({'asset_id':aid,'checked':True})
        actual=cost+(500 if i%13==0 else 0)
        row=({'invoice_id':f'I{i:04}','asset_id':aid,'amount':actual,'source':f'invoices:{i}'}
             if i%2 else {'invoice_id':f'I{i:04}','machine':aid,'fee':f'₩{actual:,}','source':f'invoices:{i}'})
        bills.append(row)
        if i%25==0: bills.append({**row,'source':f'duplicate:{i}'})
    for i in range(12):
        bills.append({'invoice_id':f'U{i:02}','asset_id':None if i%2 else f'UNKNOWN{i}',
                      'amount':700,'source':f'unknown:{i}'})
    return {'assets.json':assets,'checks.json':checks,'invoices.json':bills}

def variant(target):
    source=h.OUT/'trainer/inputs'
    shutil.copytree(source,target,dirs_exist_ok=True)
    bills=json.loads((target/'invoices.json').read_text())
    for b in bills:
        if 'fee' in b:b['fee']=b['fee'].replace('₩','KRW ')
    checks=json.loads((target/'checks.json').read_text())
    checks.extend({'asset_id':f'E{i:04}','checked':True} for i in [10,20,30,40,50,60])
    h.dump(target/'invoices.json',bills);h.dump(target/'checks.json',checks)
    oracle=json.loads((h.OUT/'oracle/main.json').read_text())
    for row in oracle['rows']:
        if row['asset_id'] in {f'E{i:04}' for i in [10,20,30,40,50,60]}:row['missing_check']=False
    oracle['missing_checks']=54;oracle['mismatches']=0
    h.dump(h.OUT/'oracle/variant.json',oracle)

def transfer(target):
    assets=[];checks=[];bills=[];expected=[];totals={}
    for i in range(1,81):
        aid=f'V{i:03}';branch=f'D{i%4+1}';amount=1200+i*3;actual=amount+(900 if i%7==0 else 0)
        assets.append({'asset_id':aid,'branch':branch,'expected_cost':amount})
        if i%5:checks.append({'asset_id':aid,'checked':True})
        b={'invoice_id':f'R{i:03}','machine':aid,'fee':f'KRW {actual:,}','source':f'vehicle:{i}'}
        bills.append(b)
        if i%20==0:bills.append({**b,'source':f'replay:{i}'})
        expected.append({'asset_id':aid,'branch':branch,'expected_cost':amount,'actual_cost':actual,'difference':actual-amount,'missing_check':i%5==0,'duplicate_count':int(i%20==0)})
        totals[branch]=totals.get(branch,0)+actual
    for fn,values in [('assets.json',assets),('checks.json',checks),('invoices.json',bills)]:h.dump(target/fn,values)
    h.dump(h.OUT/'oracle/transfer.json',{'rows':expected,'unmatched':[],'total_actual':sum(totals.values()),'duplicates':4,'missing_checks':16,'mismatches':11,'branch_totals':[{'branch':k,'actual_cost':v} for k,v in sorted(totals.items())]})

if __name__=='__main__':
    variant(h.OUT/'variant_inputs');transfer(h.OUT/'transfer_inputs')
