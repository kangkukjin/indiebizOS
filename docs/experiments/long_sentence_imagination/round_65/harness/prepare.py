"""Prepare identical public fixtures and transport requests; no remote execution."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[5]
HERE=Path(__file__).parent
OUT=ROOT/'outputs/long_sentence_imagination/2026-10-14_65회차'
PC='guestpc-70e163471313'
PYTHON='C:/Users/kyungho/AppData/Local/Programs/Python/Python312/python.exe'
REMOTE='C:/Users/kyungho/indiebiz-training/tv1-setup/65'

def save(p,value):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
 names=['서울','東京','🌱','한 글','가나다','大阪','🧪','강릉','京都','작업 A','💡','끝']
 rows=[{'id':f'{i:02d}','name':n,'value':i} for i,n in enumerate(names,1)]
 settings={'factor':1,'output':'old-output','user_note':'보존할 메모 🌱','unknown_setting':{'keep':True}}
 api='''# 시험 앱 인터페이스
Python 표준 라이브러리만 사용한다. 각 명령은 독립 원시 작업이다.
`python sample_app.py hash` → 현재 settings.json SHA256 (한 줄).
`patch --expected HASH --factor N --output DIR` → 지문 일치 때 지정 필드만 갱신; 불일치 exit 23, 쓰기 없음. 원본은 data/_backups/2026-10-14_tv1_setup/HASH.json.
`process` → 현재 설정으로 input/sample.json을 처리해 OUTPUT/result.json. `process --empty` → OUTPUT/empty.json.
`port --port N` → free exit0 / occupied exit24.
`start --port N --nonce NAME --ttl SECONDS` → 이번 Python으로 독립 시험 서비스. bind 성공 후 신원 파일 service-NAME.json. 자동 종료 상한 있음.
`health --nonce NAME` → 응답 nonce/PID/루트/시작시각을 신원 파일과 대조.
`stop --nonce NAME` → 신원 대조 뒤 이 시험 서비스만 종료, 포트 닫힘 확인.
`snapshot` → 설정·파일 해시·처리/변경/서비스 사건·실행파일 JSON.
`restore --expected HASH` → 백업을 restored-copy.json에 복원하고 SHA256 확인. 실제 settings는 변경하지 않음.
입출력은 UTF-8. 설치·포트선택·변경계획·재시도·결과판정·보고는 실행자가 수행한다.
'''
 assets={'sample_app.py':(HERE/'sample_app.py').read_text(),'APP.md':api,'settings.json':json.dumps(settings,ensure_ascii=False,indent=2),'input/sample.json':json.dumps(rows,ensure_ascii=False,indent=2),'protected/user-note.txt':'사용자가 남긴 원문 東京 🌱\n','protected/old-output.txt':'이전 산출물 보존\n'}
 allassets=[]
 for who,port in [('trainer',19865),('agent',19875)]:
  rd=f'{REMOTE}/{who}/자료 작업'
  req={'pc':PC,'remote_root':rd,'python':PYTHON,'python_version':'3.12.10','factor':2,'output':'out-a','ports':[port,port+1,port+2],'blocker_nonce':who+'-blocker','expected_count':12,'keep_fields':['user_note','unknown_setting']}
  public=assets|{'requirements.json':json.dumps(req,ensure_ascii=False,indent=2)}
  manifest={n:hashlib.sha256(v.encode()).hexdigest() for n,v in public.items()}
  public['input/manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2)
  for name,content in public.items():
   p=OUT/who/'input'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content,encoding='utf-8')
   allassets.append({'path':rd+'/'+name,'content':content})
  save(OUT/who/'context.json',{'pc':PC,'rd':rd,'python':PYTHON,'port':port,'tag':'r65-'+who,'out':str(OUT/who)})
 save(OUT/'upload.request.json',{'code':'#!ibl edition=2\n$assets >> [table:each]{parallel:2} { return [limbs:guestpc]{op:"write",limb:$pc,path:$it.path,content:$it.content} }','origin':'training','inputs':{'pc':PC,'assets':allassets}})
 save(OUT/'oracle.json',{'rows':rows,'settings':settings,'basic_total':156,'variant_total':234,'base_hash':hashlib.sha256(assets['settings.json'].encode()).hexdigest()})

if __name__=='__main__':main()
