"""Freeze source records and synthetic inputs; no training solution here."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(os.environ.get('R62_OUT', str(ROOT / 'outputs/long_sentence_imagination/2026-10-12_62회차'))).resolve()
DOC = ROOT / 'docs/experiments/long_sentence_imagination/round_62'

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) if not isinstance(value, str) else value)

CONTRACT = '''공개 판정 계약
입력 history/는 실제 종료된 54~61회차의 사본이고 synthetic/은 가상 자료다. 둘의 성과·비용을 합치지 마.
synthetic/runs.json은 실행 목록이다. 정확한 run_id로 동일 내용은 한 번만, 다른 내용은 충돌로 보존한다. 충돌한 실행의 실행 상태는 충돌이다.
requirements.json의 각 실행에는 C1,C2,C3가 있다. artifacts/<run_id>.json에 조건별 실제 true/false 값과 revision이 있고 checks/<run_id>.json에 판정 증거가 있다.
조건 충족은 실제 값 true와 같은 revision의 검수 passed=true가 모두 있어야 한다. 실제 값 false 또는 현 판본 검수 false는 미충족. 원천 부재/판본 불일치/모순이면 미검증. 조건 ID와 원천 경로·판본을 보존한다.
달성=3조건 모두 충족, 부분 달성=일부 충족이나 전부 아님, 미달=충족0이며 미충족이 하나 이상, 미검증=충족/미충족 모두0. 검사 통과, 실행 상태, 달성은 독립 칸이다. 실행 상태 충돌은 근거가 분명한 조건별 달성 판정을 덮어쓰지 않는다.
events_*.json의 총 2400행을 처리한다. kind=billable만 비용이다. event_id가 같은 동일 내용은 1회, 다른 내용은 충돌로 제외하고 ID를 남긴다. summary는 비용 합산에서 제외한다. 토큰 null은 0으로 확정하지 마.
각 실행의 observed_input/output은 충돌 없는 과금 이벤트의 확인된 성분 합계, missing_input/output은 그 성분이 null인 이벤트 개수다. conflict_event_ids가 있거나 누락 성분이 있으면 해당 실행 total_input/output은 null이다. 모든 고유 실행에 대해 표를 만든다. 수정/재실행 실행은 원래 실행과 분리한다.
후보3개와 선택 이유, 실행 전 고정한 과제·완료조건을 task.md에 먼저 저장하고, 판정표 verdicts.json과 읽을 수 있는 report.md를 저장 후 재독 확인한다. verdicts.json에는 runs 배열을 두고 run_id, validation, execution, outcome, conditions, observed_input, observed_output, missing_input, missing_output, conflict_event_ids, total_input, total_output을 포함한다. conditions에는 id,state(충족/미충족/미검증), artifact_revision,evidence_revision,source를 둔다. 다른 정보 추가 가능.
report.md에는 24개 고유 실행 표, 상태별 수, 비용의 관측·미상 구분, 실제 기록과 연결한 후보3개, 다음 과제1개, 변경/재사용 내역을 포함한다. 다음 과제는 시작하지 않는다. 시스템 코드/설정 수정·관용구 등록·외부 발신 금지.
'''

def main():
    src=OUT/'source'
    if src.exists():
        raise SystemExit('Existing source snapshot: choose a fresh R62_OUT; never overwrite evidence.')
    src.mkdir(parents=True)
    refs=[]
    for n in range(54,62):
        p=ROOT/f'docs/experiments/long_sentence_imagination/round_{n}/report.md'
        text=p.read_text()
        write(src/f'history/round_{n}.md',text)
        refs.append({'id':n,'path':f'history/round_{n}.md','original':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    write(src/'history/index.json',{'sources':refs})
    runs=[]; requirements=[]; events=[]
    for i in range(24):
        rid=f'SYN-R{i:02d}'; typ=i%8
        run={'run_id':rid,'training_id':f'SYN-T{i//2:02d}','validation':'passed','execution':'failed' if typ in (1,6) else 'succeeded','phase':'repair' if typ==7 else 'initial','parent_run':f'SYN-R{i-1:02d}' if typ==7 else None}
        runs.append(run)
        requirements.extend({'run_id':rid,'id':f'C{k}','description':f'必須結果{k}が正しい'} for k in range(1,4))
        # Normalized observations are synthetic evidence, not precomputed verdicts.
        vals={f'C{k}':(False if typ in (1,6) else not(typ==2 and k==2)) for k in range(1,4)}
        if typ!=3:
            write(src/f'synthetic/artifacts/{rid}.json',{'run_id':rid,'revision':'v1','values':vals})
            write(src/f'synthetic/checks/{rid}.json',{'run_id':rid,'revision':'v1','checks':{k:bool(v) for k,v in vals.items()}})
        ev=[]
        for j in range(98):
            ev.append({'event_id':f'{rid}-E{j:03d}','run_id':rid,'kind':'summary' if j==97 else 'billable','input': None if typ==4 and j==10 else 100+i+j,'output':None if typ==4 and j==11 else 10+j})
        ev.append(dict(ev[1],input=999) if typ==5 else dict(ev[1]))
        ev.append(dict(ev[0]));events.extend(ev)
    runs.append(dict(runs[0])); runs.append(dict(runs[5],execution='failed'))
    write(src/'synthetic/runs.json',runs);write(src/'synthetic/requirements.json',requirements)
    for n in range(4):write(src/f'synthetic/events_{n}.json',events[n*600:(n+1)*600])
    write(src/'contract.txt',CONTRACT)
    write(src/'manifest.json',{'history':refs,'runs':'synthetic/runs.json','requirements':'synthetic/requirements.json','events':[f'synthetic/events_{n}.json' for n in range(4)],'contract':'contract.txt','revision':'base'})
    for who in ('trainer','agent'):
        shutil.copytree(src,OUT/who/'input',dirs_exist_ok=True)
        (OUT/who/'out').mkdir(parents=True,exist_ok=True)
    write(OUT/'start.json',{'started':'2026-10-12T20:00:00+09:00','deadline':'2026-10-12T21:00:00+09:00','head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'status':subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True)})
    design=(ROOT/'docs/LONG_SENTENCE_META_TRAINING_DESIGN_2026_10_12.md').read_text()
    request='\n'.join(line[2:] for line in design.splitlines() if line.startswith('> '))
    request+='\n\n'+CONTRACT+f'\n입력: {OUT}/agent/input\n출력: {OUT}/agent/out\n다른 실행자의 trainer/source/runs/harness/정답/설계 보고서에 접근하지 마. 공개 교재/계약은 조회 가능. 이번 요청은 기본 실행만이며 변경 입력은 다음 요청에서 제공한다. 실제 사례는 최근 종료 8개 회차다. 시간 상한 20분이며 내부 훈련을 다른 AI에 위임하지 마.'
    write(OUT/'agent_base_request.json',{'message':request,'origin':'training','background':True})
    write(OUT/'task.md','# 62회차 — 훈련 자체의 설계·실행·판정\n\n시작 2026-10-12 20:00 KST, 상한 60분(21:00). 수리는 모든 훈련 종료 확인 뒤 별도.\n\n'+request.replace(str(OUT),'$ROUND')+'\n\n변형: SYN-R03/R11/R19의 누락 산출물·검수를 추가하고 SYN-R00의 같은 경로 산출물·검수를 v2(C2=false)로 교체한다. 나머지 입력은 불변. 기본과 변형의 전 실행·조건·비용을 독립 Python oracle로 대조한다. 훈련자는 입력 생성 내용과 기대를 아는 운영자 겸임이므로 시스템 AI와 같은 눈가림 조건이 아님을 밝힌다. 내부 구현은 아직 읽지 않았고 공개 교재·describe·기존 HTTP 전송 방식만 참조했다.\n')
    if not (DOC/'task.md').exists():
        shutil.copy2(OUT/'task.md',DOC/'task.md')
    print({'events':len(events),'unique_runs':24,'sources':len(refs),'out':str(OUT)})
if __name__=='__main__':main()
