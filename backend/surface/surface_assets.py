"""불변 화면 판본의 자산 읽기. 소스 저장과 운영 활성화를 구분한다."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import re

_ROOT = Path(__file__).resolve().parents[2]
_SOURCE = _ROOT / 'frontend/surfaces'
_STORE = Path(os.environ.get('INDIEBIZ_UI_STORE', Path(os.environ.get('INDIEBIZ_BASE_PATH', _ROOT)) / 'frontend/dist-surfaces'))
_build_sources = ContextVar('surface_build_sources', default=False)
_snapshot = ContextVar('surface_snapshot', default=None)
_cache = {}
_reads = ContextVar('surface_input_reads', default=None)
STATIC_INPUTS = ('app_render_core.js', 'member_app_requests.js',
                 'member_browser_store.js', 'member_browser_files.js',
                 'member_browser_runtime.js', 'member_browser_boot.js')


def asset_sources():
    """이름 → 정본 경로. 빌드·패키징·검사 선택기의 공통 입력 집합."""
    sources = {p.relative_to(_SOURCE).as_posix(): p for p in _SOURCE.rglob('*')
               if p.is_file() and p.suffix in {'.html', '.js', '.css', '.json'}}
    sources.update({'static/' + name: _ROOT / 'backend/static' / name for name in STATIC_INPUTS})
    # Owner JSX is compiled into a display-only module; every compiler input is sealed.
    for path in (_ROOT / 'frontend/i18n/remote.json', _ROOT / 'backend/static/ui_i18n/remote.json'):
        if path.is_file():
            sources['i18n/remote.json'] = path
            break
    owner = _ROOT / 'frontend'
    for path in (owner / 'src').rglob('*'):
        if path.is_file() and path.suffix in {'.ts', '.tsx', '.css', '.json'}:
            sources['owner-input/' + path.relative_to(owner).as_posix()] = path
    for name in ('package-lock.json', 'scripts/owner-display.mjs', 'scripts/ui-compiler.mjs',
                 'scripts/ui-static-values.mjs', 'i18n/catalog.json', 'i18n/runtime.mjs', 'electron/preload.js'):
        path = owner / name
        if path.is_file():
            sources['owner-input/' + name] = path
    for path in (_ROOT / 'backend/surface').glob('*.py'):
        if path.stem.startswith(('launcher_', 'member_', 'surface_')):
            sources['composition/' + path.name] = path
    return dict(sorted(sources.items()))


def source_files():
    return list(asset_sources().values())


def _baseline():
    # 최초 설치물은 한 번만 읽는다. 수정 중 소스를 요청마다 섞지 않는다.
    if 'baseline' not in _cache:
        _cache['baseline'] = {name: p.read_text(encoding='utf-8') for name, p in asset_sources().items()}
    return _cache['baseline']


def current_snapshot():
    pointer = _STORE / 'active.json'
    if not pointer.is_file():
        return _baseline()
    selection = json.loads(pointer.read_text(encoding='utf-8'))
    try:
        return _version_snapshot(selection['version'])
    except (ValueError, KeyError, OSError):
        if not selection.get('previous'):
            raise
        return _version_snapshot(selection['previous'])


def _version_snapshot(version):
    if not re.fullmatch(r'[0-9a-f]{64}', version):
        raise ValueError('화면 판본 식별자 오류')
    if version not in _cache:
        directory = _STORE / version
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('version') != version or manifest.get('format') != 'indiebiz-surfaces-1':
            raise ValueError('화면 판본 매니페스트 오류')
        assets = {}
        for name, digest in manifest['assets'].items():
            if name.startswith('/') or '..' in Path(name).parts:
                raise ValueError('화면 자산 경로 오류')
            data = (directory / 'assets' / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError('화면 자산 지문 불일치: ' + name)
            assets[name] = data.decode('utf-8')
        expected = hashlib.sha256(json.dumps({k: v for k, v in manifest.items() if k != 'version'}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if expected != version:
            raise ValueError('화면 판본 지문 불일치')
        _cache[version] = assets
    return _cache[version]


@contextmanager
def asset_snapshot():
    """한 응답의 모든 조각이 같은 판본을 사용한다."""
    token = _snapshot.set(_snapshot.get() or (None if _build_sources.get() else current_snapshot()))
    try:
        yield
    finally:
        _snapshot.reset(token)


@contextmanager
def source_build():
    token = _build_sources.set(True)
    try:
        yield
    finally:
        _build_sources.reset(token)


@contextmanager
def track_reads():
    reads = set()
    token = _reads.set(reads)
    try:
        yield reads
    finally:
        _reads.reset(token)


def read_asset(name):
    if _reads.get() is not None:
        _reads.get().add(name)
    if name.startswith('/') or '..' in Path(name).parts:
        raise ValueError('화면 자산 경로 오류')
    if _build_sources.get():
        return asset_sources()[name].read_text(encoding='utf-8')
    return (_snapshot.get() or current_snapshot())[name]


def render_template(name, **slots):
    """명시된 @@slot@@만 대입한다. 삽입한 JS/사용자 값은 재해석하지 않는다."""
    template = read_asset(name)
    required = set(re.findall(r'@@([a-z_]+)@@', template))
    if required != set(slots):
        raise ValueError(f'{name}: missing={required - set(slots)}, extra={set(slots) - required}')
    return re.sub(r'@@([a-z_]+)@@', lambda match: slots[match[1]], template)


def read_artifact(name):
    """Only activated, fingerprint-checked build products are served to installed hosts."""
    if name.startswith('/') or '..' in Path(name).parts:
        raise ValueError('화면 산출물 경로 오류')
    selection = json.loads((_STORE / 'active.json').read_text(encoding='utf-8'))
    error = None
    for version in (selection.get('version'), selection.get('previous')):
        if not version:
            continue
        try:
            _version_snapshot(version)
            directory = _STORE / version
            manifest = json.loads((directory / 'manifest.json').read_text())
            content = (directory / name).read_bytes()
            if hashlib.sha256(content).hexdigest() != manifest['pages'][name]:
                raise ValueError('화면 산출물 지문 불일치')
            return content
        except (ValueError, KeyError, OSError) as exc:
            error = exc
    raise ValueError('사용 가능한 화면 판본이 없습니다') from error
