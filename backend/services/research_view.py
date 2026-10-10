"""프로젝트 신원만 바인딩한 선언형 연구 화면."""
import json
from pathlib import Path
import yaml


def manifest(project_uid, name):
    path = Path(__file__).resolve().parents[2] / 'data/instruments/templates/research.yaml'
    raw = yaml.safe_load(path.read_text(encoding='utf-8'))
    # 신원은 서버에서 생성한 UUID. 사용자 이름은 실행 코드에 넣지 않는다.
    data = json.loads(json.dumps(raw, ensure_ascii=False).replace('__PROJECT_REF__', project_uid))
    data['name'] = name
    for mode in data.get('modes', []):
        mode['edition'] = 2
    return data
