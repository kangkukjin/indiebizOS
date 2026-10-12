"""Deterministic synthetic inputs; oracle never given to the system AI."""
import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-12_61회차'
DOC = Path(__file__).resolve().parents[1]

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))

def main():
    stock, events = [], []
    for index in range(240):
        sku = f'P{index // 2:03}'
        warehouse = ['서울|A', '부산'][index % 2]
        stock.append(dict(sku=sku, warehouse=warehouse, opening=100+index, counted=0))
        for seq in range(12):
            n=index*12+seq
            events.append(dict(id=f'E{n:04}', version=1, sku=sku, warehouse=warehouse,
                kind=['입고','출고','반품'][seq%3], qty=seq%5+1))
    for n in range(0,2880,97):
        events.append({**events[n], 'version':2, 'qty':7})
    events += [dict(e) for e in events[:40]]
    for n in [55,166,277,388,499]:
        events[n]['qty']=None
    events += [dict(id='U1',version=1,sku='미등록',warehouse='부산',kind='입고',qty=3),
               dict(id='U2',version=1,sku='미등록',warehouse='서울|A',kind='출고',qty=2)]
    # Canonically equivalent NFD keys appear in real macOS exports.
    for n in range(7,len(events),23):
        events[n]['warehouse']=unicodedata.normalize('NFD',events[n]['warehouse'])
    latest={}
    for e in events:
        if e['id'] not in latest or e['version']>latest[e['id']]['version']:
            latest[e['id']]=e
    movement={}
    for e in latest.values():
        key=(e['sku'],unicodedata.normalize('NFC',e['warehouse']))
        info=movement.setdefault(key,{'known':0,'missing':0,'ids':[]})
        info['ids'].append(e['id'])
        if e['qty'] is None: info['missing']+=1
        else: info['known']+=e['qty']*(-1 if e['kind']=='출고' else 1)
    for index,row in enumerate(stock):
        row['counted']=row['opening']+movement[(row['sku'],row['warehouse'])]['known']+(index%9==0)*2
    batches=[events[n::4] for n in range(4)]
    for case in ['base','missing']:
        for who in ['trainer','agent']:
            dest=OUT/who/case/'input'
            write(dest/'stock.json',stock)
            write(dest/'manifest.json',{'files':[f'events_{n}.json' for n in range(4)]})
            for n,batch in enumerate(batches):
                if case=='missing' and n==2: continue
                write(dest/f'events_{n}.json',batch)
    write(OUT/'oracle_source.json', {'stock':stock,'events':events})
    task='''창고 재고를 대조해 줘. manifest.json에 적힌 네 전표 파일을 모두 읽고, 같은 id의 전표는 version이 가장 큰 한 건만 사용해. 같은 최신판이 반복돼도 한 건이다. 원본 행수, 고유 전표수, 최신판 선택으로 제외된 행수를 알려 줘. sku와 warehouse의 조합으로 묶으며 유니코드 NFC/NFD 표기만 다른 창고는 같은 곳이다. 입고와 반품은 더하고 출고는 뺀다. qty null은 0으로 확정하지 말고 수량 미상 전표 id를 남겨 줘. stock.json의 모든 품목·창고를 보존하여 기초재고, 확인된 순증감, 실사재고, 예상재고, 실사-예상 차이, 상태(일치/차이/미확인)를 작성해. 수량 미상이 끼면 예상재고와 차이는 null이고 상태는 미확인이다. 등록되지 않은 조합의 전표도 별도 목록으로 보존해. 전표 파일 하나라도 읽지 못하면 읽은 자료로 확인된 순증감은 계산하되 모든 예상재고·차이는 null, 상태는 미확인으로 두고 누락 파일을 명시해. 모든 계산 행에 사용한 최신 전표 id 목록으로 근거를 연결해. 결과는 result.json과 사람이 읽을 수 있는 한국어 report.md로 저장하고 저장 후 재독 확인해. 보고서에는 전체 건수, 세 상태별 건수와 품목별 수치 표, 미상 전표와 미등록 조합 및 누락 파일이 있어야 해. 실제 재고·다른 파일을 수정하지 마.'''
    (DOC/'task.md').write_text('# 61회차 과제 — 2026-10-12 19:41 KST\n\n'+task+'\n\n합성 240 품목×창고, 2,952 원시 전표, 최신판/중복과 NFD 표기. 기본과 events_2.json 부재 변형을 같은 프로그램으로 실행한다. 독립 기대값은 harness의 표준 Python 집계로 별도 대조한다. 시스템 AI에는 요청문·입출력 경로만 전달하며 trainer/harness/정답 열람을 금지한다. 전건 행·합계·근거 ID·재독·보고서 존재/표 내용을 사전 완료 조건으로 고정한다. 내부 구현은 최초 작성에 읽지 않았다. 교재 ibl_composition(_tools), describe 6개를 사용한다.\n\n분해: 읽기 함수는 파일명/성공 여부/행을 보존; 최신판 선택→복합키 집계는 순수 계산; stock과 full join 후 미등록 분리; 출력/재독은 마지막 효과다. 훈련 상한60분, 후속 수리 시간 별도.\n')
    for case in ['base','missing']:
        message=task+f'\n입력: {OUT}/agent/{case}/input\n출력: {OUT}/agent/{case}/out\n다른 실행자의 trainer/harness/drafts·정답을 참조하지 마. 너 자신의 결과는 재사용해도 된다.'
        if case=='missing': message='조건이 바뀌었어. 새 입력 사본은 전표 파일 하나가 빠져 있어. 읽을 수 있는 자료만으로 다시 대조해 줘.\n'+message
        write(OUT/f'ai_{case}_request.json', {'message':message,'origin':'training','background':True})

if __name__=='__main__': main()
