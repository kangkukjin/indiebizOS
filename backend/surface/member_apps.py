"""회원 앱은 원격 런처의 선언형 계기에서 파생. 실행 잎은 매번 다시 검사한다."""
import copy
import re
from pathlib import Path

import yaml
from member_profile import visible
from ibl_registry import load_nodes_installed


def catalogue(local_apps=None):
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
    if local_apps:
        import json
        if not isinstance(local_apps, list) or len(json.dumps(local_apps)) > 256000 or len(local_apps) > 30:
            raise ValueError('내 앱 파일의 크기 또는 앱 수를 확인하세요')
        for local in local_apps:
            if not isinstance(local, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', str(local.get('id', ''))):
                raise ValueError('내 앱 이름을 확인하세요')
            # 로컬 앱은 회원 IBL 선언만 제공. 서버 조사 절차/프롬프트를 등록하지 않는다.
            def requests(value):
                if isinstance(value, dict):
                    return 'request' in value or any(requests(v) for v in value.values())
                return isinstance(value, list) and any(requests(v) for v in value)
            if requests(local):
                raise ValueError('내 앱은 공개 기능의 앱 동작으로 작성하세요')
            candidates.append({**local, 'id': 'local_' + local['id']})
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
            if (key == 'action' or key.endswith('_action')) and isinstance(value, str):
                refs = re.findall(r'\[([a-z_]+:[a-z_]+)\]', value)
                if not refs or any(q not in allowed for q in refs):
                    return None
            if isinstance(value, str) and ('%BASE%' in value or '~workspace' in value
                    or re.search(r'/(Users|home)/|[A-Z]:\\', value)
                    or ((key == 'action' or key.endswith('_action')) and re.search(r'@\w+', value))):
                return None
        result = {k: v for k, x in obj.items() if (v := clean(x)) is not None}
        # 비공개 버튼을 지운 뒤 빈 탭/앱을 남기지 않는다.
        if 'modes' in obj and not result.get('modes'):
            return None
        if 'buttons' in obj and not result.get('buttons') and not result.get('action') and not result.get('request'):
            return None
        return result
    instruments = []
    candidates = list({app['id']: app for app in candidates}.values())
    for source in candidates:
        app = clean(copy.deepcopy(source))
        if app and (app.get('modes') or app.get('action') or app.get('request')):
            for mode in app.get('modes', []):
                action_id = f"{app['id']}:{mode.get('id', 'main')}"
                if browser and (mode.get('request') or mode.get('action')):
                    mode['client_action_id'] = action_id
                for i, button in enumerate(mode.get('buttons', [])):
                    if browser and (button.get('request') or button.get('action')):
                        button['client_action_id'] = f"{action_id}:button:{i}"
            instruments.append(app)
    return {'success': True, 'instruments': instruments, 'open_words': sorted(allowed)}


def web_catalogue(local_apps=None):
    from member_app_actions import compile_apps
    result = catalogue(local_apps) if local_apps else catalogue()
    result['instruments'], _ = compile_apps(result['instruments'])
    return result


def resolve_request(action_id, args, local_apps=None):
    from member_app_actions import compile_apps, resolve
    result = catalogue(local_apps) if local_apps else catalogue()
    _, registry = compile_apps(result['instruments'])
    return resolve(registry, action_id, args)
