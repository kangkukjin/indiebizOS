"""Live singleton-list checks and aggregate training-origin health evidence."""
import datetime
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def execute(code):
    request = {'code': '#!ibl edition=2\n'+code, 'edition': 2,
               'project_id': '컨텐츠', 'origin': 'training'}
    proc = subprocess.run(['curl', '-sS', '--max-time', '60',
        'http://127.0.0.1:8765/ibl/execute', '-H', 'Content-Type: application/json',
        '--data-binary', '@-'], input=json.dumps(request), text=True,
        capture_output=True, check=True)
    return {'request': request, 'response': json.loads(proc.stdout)}


def main():
    observations = []
    for code, expected in [('return [true]', [True]), ('return [false]', [False]),
                           ('return [null]', [None]),
                           ('$fs=[abs]; $f=$fs[0]; return $f(-7)', 7)]:
        row = execute(code)
        result = row['response'].get('result', row['response'])
        row['expected'] = expected
        row['passed'] = result.get('success') is True and result.get('value') == expected
        observations.append(row)
    (HERE/'parser_after.json').write_text(json.dumps(observations, ensure_ascii=False, indent=2)+'\n')
    assert all(row['passed'] for row in observations), observations
    # File birth time is the first authoring response, minus one minute to
    # include the beginning of that request. Local action timestamps use KST.
    start = datetime.datetime.fromtimestamp((HERE/'authoring.json').stat().st_birthtime)
    start = (start-datetime.timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S')
    query = f"select source, count(*) as n from action_health where datetime(timestamp) >= datetime('{start}') group by source"
    code = '[sense:sqlite]{path:"~workspace/data/world_pulse.db",query:'+json.dumps(query)+'}'
    health = execute(code)
    (HERE/'health_response.json').write_text(json.dumps(health, ensure_ascii=False, indent=2)+'\n')
    print('singleton live checks: 4/4; health evidence saved')


if __name__ == '__main__':
    main()
