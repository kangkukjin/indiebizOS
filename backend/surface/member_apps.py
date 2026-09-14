"""회원 앱은 원격 런처의 선언형 계기에서 파생. 실행 잎은 매번 다시 검사한다."""
import copy
import re
from pathlib import Path

import yaml
from member_profile import visible
from ibl_registry import load_nodes_installed


def catalogue():
    from api_launcher_web import _derive_instruments
    from runtime_utils import get_base_path
    import principal
    import limb_keys
    device = limb_keys.get_by_device(principal.current().device_id) or {}
    browser = (device.get('env') or {}).get('client') == 'web'
    nodes = load_nodes_installed().get('nodes', {})
    allowed = {f'{n}:{a}' for n, nc in nodes.items() for a, ac in nc.get('actions', {}).items() if visible(n, a, ac)}
    source_ids = set()
    for nc in nodes.values():
        for name, ac in nc.get('actions', {}).items():
            app = ac.get('app') or {}
            if app:
                source_ids.add(app.get('instrument') or name)
    # 허브의 개인 독립 앱·경로·설정은 회원 카탈로그에 합치지 않는다.
    candidates = [i for i in _derive_instruments(include_standalone=False)['instruments'] if i['id'] in source_ids]
    path = Path(get_base_path()) / 'data' / 'member_apps.yaml'
    candidates += yaml.safe_load(path.read_text()) if path.exists() else []
    def clean(obj):
        if isinstance(obj, list):
            return [v for x in obj if (v := clean(x)) is not None]
        if not isinstance(obj, dict):
            return obj
        if obj.get('web_only') and not browser:
            return None
        if obj.get('renderer', '').startswith('custom:'):
            return None
        for key, value in obj.items():
            if key in ('action', 'options_action') and isinstance(value, str):
                refs = re.findall(r'\[([a-z_]+:[a-z_]+)\]', value)
                if not refs or any(q not in allowed for q in refs):
                    return None
            if isinstance(value, str) and ('%BASE%' in value or '~workspace' in value
                    or re.search(r'/(Users|home)/|[A-Z]:\\', value)
                    or (key in ('action', 'options_action') and re.search(r'@\w+', value))):
                return None
        result = {k: v for k, x in obj.items() if (v := clean(x)) is not None}
        # 비공개 버튼을 지운 뒤 빈 탭/앱을 남기지 않는다.
        if 'modes' in obj and not result.get('modes'):
            return None
        if 'buttons' in obj and not result.get('buttons') and not result.get('action') and not result.get('request'):
            return None
        return result
    instruments = []
    for source in candidates:
        app = clean(copy.deepcopy(source))
        if app and (app.get('modes') or app.get('action') or app.get('request')):
            instruments.append(app)
    return {'success': True, 'instruments': instruments, 'open_words': sorted(allowed)}
