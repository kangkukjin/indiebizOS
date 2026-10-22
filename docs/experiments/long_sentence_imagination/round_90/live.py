"""Finite HTTP transport and fixture preparation; business calculation stays in IBL/AI."""
import argparse
import datetime
import hashlib
import json
import shutil
import sqlite3
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-22_90회차'
BASE = ROOT / 'outputs/long_sentence_imagination/2026-10-22_89회차'
ROLES = ['총괄', '자료', '비용', '일정', '운영']


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def api(path, body=None, timeout=55):
    req = urllib.request.Request('http://127.0.0.1:8765' + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def deadline():
    end = datetime.datetime.fromisoformat(json.loads((OUT/'start.json').read_text())['deadline'])
    assert datetime.datetime.now().astimezone() < end, 'Training budget expired'


def project(lane):
    return 'L90_' + lane


def policy(turn):
    return dict(budget=6000000 if turn == 1 else 3200000, deadline='2026-11-20',
                cancel_optional=turn > 1, external_saas=turn == 1, face=turn == 1)


def prepare():
    assert not OUT.exists()
    for name in ['runs', 'reference', 'trainer', 'ai', 'snapshots']:
        (OUT/name).mkdir(parents=True)
    for lane in ['trainer', 'ai']:
        shutil.copytree(BASE/'reference/initial_inputs', OUT/lane/'inputs')
    save(OUT/'start.json', dict(start='2026-10-22T14:39:00+09:00',
        deadline='2026-10-22T15:39:00+09:00',
        head=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()))
    functions = (HERE.parent/'round_89/functions_v3.ibl').read_text()
    (HERE/'functions.ibl').write_text(functions)
    ledger = ROOT/'docs/LONG_SENTENCE_IMAGINATION_LEDGER.md'
    body = ledger.read_text()
    pos = body.index('## 89회차')
    body = body[:pos] + ('## 90회차 — 에이전트 위임·재위임·조건 전달 (2026-10-22, 시작)\n\n'
        '14:39 시작·훈련 상한15:39. 사용자 설계 승인 및 발견 수리 요청. '
        '[사전 과제](experiments/long_sentence_imagination/round_90/task.md). '
        '모든 작업 종료·회수 뒤 수리 적용.\n\n') + body[pos:]
    ledger.write_text(body)
    print(OUT)


def create(lane):
    deadline()
    target = OUT/'runs'/f'{lane}_agents.json'
    assert not target.exists()
    save(OUT/'runs'/f'{lane}_project.json', api('/projects', {'name': project(lane)}))
    agents = {}
    for role in ROLES:
        result = api(f'/projects/{project(lane)}/agents', {
            'name': role, 'allowed_nodes': ['self','table','others'],
            'role': '지정된 합성 자료를 검토하는 훈련 에이전트다. 작업 지시의 입력·출력·제약·완료 조건을 지키고 한국어로 답한다. '
                    '실제 외부 발송·배포·구매·예약·운영 설정 변경을 하지 않는다. '
                    '이전 문맥을 추측하지 말고 전달받은 경로·판본·조건·근거로 수행한다.'})
        agents[role] = result['agent']
        save(target, agents)
        save(OUT/'runs'/f'{lane}_{role}_start.json', api(f'/projects/{project(lane)}/agents/{agents[role]["id"]}/start', {}))
    print(json.dumps(agents, ensure_ascii=False))


def describe(lane):
    result = api('/ibl/execute', {'code':'','describe':['others:delegate','self:task','self:read','self:write'],
        'edition':2, 'project_id':project(lane), 'origin':'training'})
    save(OUT/'runs'/f'{lane}_contracts.json', result)
    print(json.dumps(result, ensure_ascii=False)[:16000])


def ibl(lane, label):
    deadline()
    path = OUT/'runs'/f'{lane}_{label}_request.json'
    request = json.loads(path.read_text())
    request.update(edition=2, project_id=project(lane), origin='training')
    check = api('/ibl/execute', {**request,'check':True})
    save(OUT/'runs'/f'{lane}_{label}_check.json', check)
    if not check.get('ok'):
        print(json.dumps(check, ensure_ascii=False)[:6000]); return
    result = api('/ibl/execute', {**check['execute_args'], 'origin':'training', 'project_id':project(lane)}, timeout=55)
    save(OUT/'runs'/f'{lane}_{label}_result.json', result)
    print(json.dumps(result, ensure_ascii=False)[:6000])


def request(turn):
    root = OUT/'ai'
    scope = (f'\n输入/입력: {root/"inputs"}. 모든 산출물·보조 프로그램은 {root/f"T{turn}"} 안에만 써 줘. '
        f'자신과 같은 팀의 이전 산출물({root})은 재사용해도 돼. '
        '다른 실행자의 trainer/reference/runs/snapshots와 docs/experiments는 읽지 마. '
        '다른 프로젝트 기억이나 해법을 쓰지 마. 실제 외부 발송·배포·예약·구매·설정 변경은 하지 마. '
        '합성 자료다. JSON 상세 결과와 한국어 검토서를 저장하고 다시 읽어 검증해 줘. '
        '실제 위임 관계·접수증·입력 판본·시간·근거를 남겨 줘. 불필요한 전체 보고서 재작성/재실행은 피해 줘.')
    tasks = {
        1: '자료실 이전 자료 1800건과 작업72개, 담당자 검증 영수증을 검토해서 개통 가능 여부와 남은 조치를 정리해 줘. '
           '자료 검증·비용·일정 검토는 이 프로젝트의 다른 에이전트들에게 실제로 나누어 맡기고, '
           '담당 에이전트가 필요한 운영조건 검토를 다른 에이전트에게 다시 맡기는 과정도 포함해 줘. '
           '자료의 보완 목록은 필요한 검토가 끝나는 대로 먼저 만들고, 최종 보고서에는 예산·자료 상태·필수 작업 완료를 함께 반영해 줘. '
           '담당자의 완료 주장만 있고 검증 근거가 없으면 완료로 세지 말고, 자료 누락·결과 미도착은 미확인으로 남겨 줘. '
           '모든 위임에 필요한 원래 요구·제약을 전달하고 결과의 출처·판본을 보존해 줘. '
           '늦는 작업은 접수증으로 이어받고 중복 위임하지 마. 기한 준수에 필요한 달력·가용 인력 정보가 없으면 확정하지 마.',
        2: '예산을 320만원으로 줄이고 W6전체·외부SaaS·얼굴자동분류를 제외할게. 개인정보·접근성·전량검증·11월20일기한은 유지해. '
           '원자료는 바뀌지 않았으므로 이전 자료 판정은 재사용하고, 필요한 비용·일정·운영조건 변경은 해당 에이전트에게 다시 맡겨 줘. '
           '새 위임마다 변경 정책과 기존의 유지할 제약을 전달해 줘. 필수 작업을 취소하거나 기준을 낮추지 마. '
           '이전 파일을 보존하고 새 결과를 저장해 줘.',
        3: 'records.json이 새 판본으로 교체됐어. 누락은 실패와 구분해 미확인으로 남겨 줘. T2정책 유지. '
           '영향받는 담당에게만 재검토를 맡기고 다른 결과와 변하지 않은 행 판정은 재사용해 줘.',
        4: 'records.json의 누락 자료가 복구됐어. T2정책 유지. 바뀐 부분과 의존 결과만 갱신하고 다른 담당의 결과는 재사용해 줘. '
           '최종 검토 완료와 실제 개통 가능을 구분해 줘.'}
    return tasks[turn] + scope


def submit(turn):
    deadline()
    ticket = OUT/'runs'/f'ai_T{turn}_accepted.json'
    assert not ticket.exists(), 'Recover existing ticket'
    if turn > 1:
        prior=json.loads((OUT/'runs'/f'ai_T{turn-1}_result.json').read_text())
        assert prior['state'] in ('succeeded','failed','cancelled') and prior.get('pending_children',0)==0
    if turn in (3,4):
        data=json.loads((BASE/'reference/initial_inputs/records.json').read_text())
        data['version']=turn-1
        if turn==3: data['items']=data['items'][:-1]
        save(OUT/'ai/inputs/records.json',data)
    (OUT/'ai'/f'T{turn}').mkdir(exist_ok=True)
    agents=json.loads((OUT/'runs/ai_agents.json').read_text())
    body={'command':request(turn),'origin':'training','background':True}
    save(OUT/'runs'/f'ai_T{turn}_request.json',body)
    result=api(f'/projects/{project("ai")}/agents/{agents["총괄"]["id"]}/command',body)
    save(ticket,result)
    print(json.dumps(result,ensure_ascii=False))


def poll(turn):
    ticket=json.loads((OUT/'runs'/f'ai_T{turn}_accepted.json').read_text())
    result=api(ticket['status_url']+'?wait=20')
    terminal=result.get('state') in ('succeeded','failed','cancelled','interrupted')
    save(OUT/'runs'/(f'ai_T{turn}_'+('result.json' if terminal else 'latest.json')), result)
    print(json.dumps(result,ensure_ascii=False)[:6500])


def stop(lane):
    agents=json.loads((OUT/'runs'/f'{lane}_agents.json').read_text())
    for role,agent in agents.items():
        result=api(f'/projects/{project(lane)}/agents/{agent["id"]}/stop',{})
        save(OUT/'runs'/f'{lane}_{role}_stop.json',result)
    print('stopped',lane)


def cleanup(lane):
    """Recover every owned task, cancel unfinished work, and stop idle runners."""
    agents=json.loads((OUT/'runs'/f'{lane}_agents.json').read_text())
    db=sqlite3.connect(f'file:{ROOT/"projects"/project(lane)/"conversations.db"}?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    records=[dict(r) for r in db.execute('select task_id,delegated_to,status,parent_task_id from tasks')]
    save(OUT/'runs'/f'{lane}_cleanup_rows.json',records)
    terminal={'succeeded','failed','cancelled','interrupted'}
    final=[]
    for row in records:
        agent=next(a['id'] for a in agents.values() if row['delegated_to'] in (a['id'],a['name']))
        route=f'/projects/{project(lane)}/agents/{agent}/tasks/{row["task_id"]}'
        before=api(route)
        save(OUT/'runs'/f'cleanup_{row["task_id"]}_before.json',before)
        if before.get('state') not in terminal:
            ref={'kind':'delegation','task_id':row['task_id'],'owner':project(lane)}
            result=api('/ibl/execute',{'code':'[self:task]{op:"cancel",ref:$ref}',
                'inputs':{'ref':ref},'edition':2,'project_id':project(lane),'origin':'training'})
            save(OUT/'runs'/f'cleanup_{row["task_id"]}_cancel.json',result)
        after=api(route+'?wait=20')
        save(OUT/'runs'/f'cleanup_{row["task_id"]}_after.json',after)
        final.append({'task_id':row['task_id'],'agent':row['delegated_to'],
                      'state':after.get('state'),'pending_children':after.get('pending_children')})
    # Re-scan: a running parent may have submitted another child while being cancelled.
    known={r['task_id'] for r in records}
    remaining=[dict(r) for r in db.execute('select task_id,delegated_to,status,parent_task_id from tasks') if r['task_id'] not in known]
    db.close()
    save(OUT/'runs'/f'{lane}_cleanup_summary.json',{'tasks':final,'new_tasks':remaining})
    print(json.dumps({'tasks':final,'new_tasks':remaining},ensure_ascii=False))
    if not remaining and all(r['state'] in terminal for r in final):
        stop(lane)
        save(OUT/'runs/cleanup_health.json',api('/health'))
    else:
        print('Re-run cleanup to recover remaining work; runners not yet stopped.')


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('action');p.add_argument('label',nargs='?',default='trainer');p.add_argument('extra',nargs='?')
    args=p.parse_args()
    if args.action=='prepare': prepare()
    elif args.action=='create': create(args.label)
    elif args.action=='describe': describe(args.label)
    elif args.action=='ibl': ibl(args.label,args.extra)
    elif args.action=='submit': submit(int(args.label))
    elif args.action=='poll': poll(int(args.label))
    elif args.action=='stop': stop(args.label)
    elif args.action=='cleanup': cleanup(args.label)
