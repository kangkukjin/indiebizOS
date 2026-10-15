"""회원 공통 모델·기어. 첫 사용 때 중앙 값을 복사하고 이후 독립 저장한다."""
import copy
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from contextvars import ContextVar

_scope = ContextVar('member_model_settings', default=None)
lock = threading.RLock()


def selected():
    forced = _scope.get()
    if forced is not None:
        return forced
    from member_runtime import is_member
    return is_member()


@contextmanager
def scope(enabled=True):
    token = _scope.set(enabled)
    try:
        yield
    finally:
        _scope.reset(token)


def path():
    import model_resolver as M
    return M._data_path() / 'member_models.json'


def save(value):
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix='member_models.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load():
    # 한 턴의 분류·실행·감독은 같은 설정을 쓴다. 편집은 다음 턴에 반영한다.
    from member_runtime import current
    state = current() if _scope.get() is None and selected() else None
    if state is not None:
        with lock:
            if 'model_settings' not in state:
                state['model_settings'] = _load()
            return copy.deepcopy(state['model_settings'])
    return _load()


def _load():
    import model_resolver as M
    with lock:
        target = path()
        if target.exists():
            value = json.loads(target.read_text(encoding='utf-8'))
            if not isinstance(value.get('gear'), dict) or not isinstance(value.get('models'), dict):
                raise ValueError('회원 모델 설정을 읽지 못했습니다')
            return value
        with scope(False):
            gear = copy.deepcopy(M._load_gear())
            # 주인 프로젝트의 핀·역할 프롬프트는 회원에게 복제하지 않는다.
            gear['overrides'] = {}
            models = {}
            for tier, filename in M._DEFAULT_GEAR['tiers'].items():
                fallback = M._data_path() / 'unconscious_ai_config.json' if tier == '경량' else None
                config = M.read_model_config(M._data_path() / filename,
                                            M.default_model_config(tier), fallback_path=fallback, strict=True)
                models[tier] = {k: v for k, v in config.items() if k in (
                    'provider', 'model', 'enabled', 'providerModels', 'input_modalities')}
                models[tier]['apiKey'] = ''
            value = {'gear': gear, 'models': models}
            save(value)
            return value


def save_gear(gear):
    with lock:
        value = load()
        value['gear'] = gear
        save(value)
