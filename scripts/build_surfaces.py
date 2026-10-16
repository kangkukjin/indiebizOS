#!/usr/bin/env python3
"""한 원본에서 불변 화면 판본 생성. --activate일 때만 운영 포인터를 교체한다."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
from surface_assets import asset_sources, source_build  # noqa: E402


def fingerprint(assets):
    return hashlib.sha256(json.dumps(assets, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def inputs():
    return {name: p.read_bytes() for name, p in asset_sources().items()}


def hashes(data):
    return {name: hashlib.sha256(value).hexdigest() for name, value in data.items()}


def render_all():
    from launcher_surface_remote import launcher_html
    from launcher_surface_phone import phone_html
    from launcher_lite import LAUNCHER_LITE_HTML, lite_display
    from member_shell import member_html
    from member_app_frame import frame_html
    from surface_display import member_display, launcher_display
    from launcher_surface_remote import remote_display
    pages = dict(remote=launcher_html(), phone=phone_html(), lite=LAUNCHER_LITE_HTML,
                 member=member_html(), browser=member_html(browser=True),
                 desktop=member_html(desktop=True), frame=frame_html())
    displays = {
        'lite': lite_display(),
        'member': member_display(member_html(display=False), 'member'),
        'browser': member_display(member_html(browser=True, display=False), 'browser'),
        'desktop': member_display(member_html(desktop=True, display=False), 'desktop'),
        'remote': remote_display(),
        'phone': launcher_display(phone_html(display=False), 'phone'),
    }
    for surface, value in displays.items():
        pages['display/' + surface + '/display.json'] = json.dumps(value, ensure_ascii=False)
    pages['display/owner/display.json'] = subprocess.check_output(
        ['node', str(ROOT / 'frontend/scripts/owner-display.mjs')], cwd=ROOT, text=True)
    return pages


def artifact_name(name):
    return name if name.endswith('.json') else name + '.html'


def build(store, activate=False, check=False, expected=None):
    data = inputs()
    digests = hashes(data)
    with source_build():
        pages = render_all()
    manifest = dict(format='indiebiz-surfaces-1', state=1,
                    assets=digests, pages=hashes({artifact_name(k): v.encode() for k, v in pages.items()}))
    version = fingerprint(manifest)
    if expected and version != expected:
        raise ValueError('검사한 화면 판본과 라이브 입력이 다릅니다 — 활성화하지 않습니다')
    manifest['version'] = version
    directory = store / version
    if hashes(inputs()) != digests:
        raise RuntimeError('빌드 중 화면 원본이 변경됐습니다. 최신 입력으로 다시 빌드하세요')
    if check:
        for name, digest in digests.items():
            if hashlib.sha256((directory / 'assets' / name).read_bytes()).hexdigest() != digest:
                raise ValueError('생성 화면 자산 불일치: ' + name)
        if json.loads((directory / 'manifest.json').read_text()) != manifest:
            raise ValueError('생성 화면 매니페스트 불일치')
        for name, value in pages.items():
            if (directory / artifact_name(name)).read_text() != value:
                raise ValueError('생성 화면 불일치: ' + name)
        return version
    store.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.candidate-', dir=store))
    try:
        for name, value in data.items():
            target = stage / 'assets' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        for name, value in pages.items():
            output = stage / artifact_name(name)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(value, encoding='utf-8')
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
        if directory.exists():
            build(store, check=True)
        else:
            stage.rename(directory)
        if activate:
            if hashes(inputs()) != digests:
                raise RuntimeError('활성화 직전 원본 변경 감지 — 후보를 활성화하지 않습니다')
            pointer = store / 'active.json'
            previous = json.loads(pointer.read_text()).get('version') if pointer.exists() else None
            fd, temporary = tempfile.mkstemp(prefix='.active-', dir=store)
            with os.fdopen(fd, 'w') as stream:
                json.dump(dict(version=version, previous=previous), stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, pointer)
        return version
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, default=ROOT / 'frontend/dist-surfaces')
    parser.add_argument('--activate', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--expect', help='검증한 판본 지문; 다르면 활성화 금지')
    parser.add_argument('--inputs', action='store_true')
    args = parser.parse_args()
    if args.inputs:
        print(json.dumps([str(p.relative_to(ROOT)) for p in asset_sources().values()]))
    else:
        print(build(args.store, activate=args.activate, check=args.check, expected=args.expect))
