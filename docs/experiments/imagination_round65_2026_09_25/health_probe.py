"""Observe aggregate health provenance for this rehearsal without editing it."""
import datetime
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def main():
    start = datetime.datetime.fromtimestamp((HERE/'authoring.json').stat().st_birthtime)
    start = (start - datetime.timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S')
    query = f"select source, count(*) as n from action_health where datetime(timestamp) >= datetime('{start}') group by source"
    request = dict(code='#!ibl edition=2\n[sense:sqlite]{path:"~workspace/data/world_pulse.db",query:'+json.dumps(query)+'}',
                   edition=2, project_id='컨텐츠', origin='training')
    response = subprocess.run(['curl','-sS','--max-time','60',
        'http://127.0.0.1:8765/ibl/execute','-H','Content-Type: application/json','--data-binary','@-'],
        input=json.dumps(request), text=True, capture_output=True, check=True)
    result = json.loads(response.stdout)
    (HERE/'health_response.json').write_text(json.dumps(dict(request=request,response=result),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result.get('result',result).get('value'),ensure_ascii=False))


if __name__ == '__main__':
    main()
