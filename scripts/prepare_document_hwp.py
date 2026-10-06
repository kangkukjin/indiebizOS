#!/usr/bin/env python3
"""Build the pinned MIT RHWP runtime for offline document editing.

본 제품은 한컴의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다.
Run with Node >=22.12 on PATH. Generated assets ship inside backend/static.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.request

VERSION = '0.8.6'
SOURCE_SHA = 'f371dba65718fe3493f27e65c293dcbf3542f71276d6cb68f815bcbc2cf0ae05'
CORE_SHA = '4e1f5aeceed38f72cade226b291977f35a9bf76da0f4f4138d1ae5113f6b1933'
DEST = ROOT / 'backend/static/rhwp'
HOST = ROOT / 'backend/static/document_hwp'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def asset_hashes(directory):
    return {p.relative_to(directory).as_posix(): sha(p)
            for p in sorted(directory.rglob('*')) if p.is_file()}


def download(url, path, expected):
    if not path.exists():
        temporary = path.with_suffix('.download')
        urllib.request.urlretrieve(url, temporary)
        temporary.replace(path)
    if sha(path) != expected:
        raise ValueError(f'Archive hash mismatch: {path}')


def extract(archive, destination, select, strip=0):
    with tarfile.open(archive) as source:
        for item in source:
            if not select(item.name):
                continue
            name = '/'.join(item.name.split('/')[strip:])
            if not name:
                continue
            path = (destination / name).resolve()
            if not path.is_relative_to(destination.resolve()):
                raise ValueError('Archive path escapes build root')
            if item.isdir():
                path.mkdir(parents=True, exist_ok=True)
            elif item.isfile():
                path.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(item) as src, path.open('wb') as dst:
                    shutil.copyfileobj(src, dst)
            # Symlinked fonts are copied explicitly from the licensed font root.


def check():
    manifest = json.loads((DEST / 'indiebiz-build.json').read_text(encoding='utf-8'))
    if manifest['version'] != VERSION:
        raise ValueError('RHWP version mismatch')
    for name, expected in manifest['files'].items():
        if sha(DEST / name) != expected:
            raise ValueError(f'RHWP asset changed: {name}')
    for name in ('host.html', 'host.js'):
        if sha(HOST / name) != manifest['files'][name]:
            raise ValueError('Rebuild RHWP host assets after changing host source')
    for path in (HOST / 'licenses').iterdir():
        if path.is_file() and sha(path) != manifest['files'].get('licenses/' + path.name):
            raise ValueError('Rebuild RHWP license assets after changing notices')
    print(f'RHWP {VERSION}: local assets verified')


def patch_save_guard(source):
    # Pinpoint patch to the embed export API; preserve the upstream editor.
    main = source / 'rhwp-studio/src/main.ts'
    text = main.read_text(encoding='utf-8')
    for format in ('Hwp', 'Hwpx'):
        before = f"async export{format}() {{\n      await initPromise;\n      return wasm.export{format}();\n    }}"
        after = f"""async export{format}() {{
      await initPromise;
      // IndieBiz: refuse a reported lossy serialization before host persistence.
      const artifact = wasm.export{format}WithReport();
      if (artifact.contentLoss.count > 0) {{
        throw new Error('원본 저장 중 내용 손실이 감지되어 중단했습니다: ' + JSON.stringify(artifact.contentLoss.losses));
      }}
      return artifact.bytes;
    }}"""
        if after not in text:
            if text.count(before) != 1:
                raise ValueError('Pinned RHWP embed export contract changed')
            text = text.replace(before, after)
    main.write_text(text, encoding='utf-8', newline='\n')


def install(source):
    if 'IndieBiz: refuse a reported lossy serialization' not in (source / 'rhwp-studio/src/main.ts').read_text(encoding='utf-8'):
        raise ValueError('Build the RHWP host save guard before installation')
    output = source / 'rhwp-studio/dist'
    stage = DEST.with_name('rhwp-stage')
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(output, stage, ignore=shutil.ignore_patterns('samples', 'sw.js', 'workbox-*', 'registerSW.js', 'manifest.webmanifest', 'Cafe24*.woff2', 'Happiness*.woff2'))
    index = stage / 'index.html'
    text = re.sub(r'<script id="vite-plugin-pwa:register-sw"[^>]*></script>', '', index.read_text(encoding='utf-8'))
    text = re.sub(r'<link rel="manifest"[^>]*>', '', text)
    index.write_text(text, encoding='utf-8', newline='\n')
    for name in ('host.html', 'host.js'):
        shutil.copy2(HOST / name, stage / name)
    shutil.copytree(HOST / 'licenses', stage / 'licenses')
    sdk = ROOT / 'frontend/node_modules/@rhwp/editor'
    (stage / 'sdk').mkdir(exist_ok=True)
    for name in ('index.js', 'transport.js', 'document-agent-contract.js'):
        shutil.copy2(sdk / name, stage / 'sdk' / name)
    (stage / 'core').mkdir(exist_ok=True)
    shutil.copy2(source / 'pkg/rhwp.js', stage / 'core/rhwp.mjs')
    for name in ('LICENSE', 'THIRD_PARTY_LICENSES.md'):
        shutil.copy2(source / name, stage / name)
    manifest = {'version': VERSION, 'source_sha256': SOURCE_SHA, 'core_sha256': CORE_SHA,
                'external_webfonts': False, 'reported_loss_guard': True,
                'files': asset_hashes(stage)}
    (stage / 'indiebiz-build.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    if DEST.exists():
        shutil.rmtree(DEST)
    stage.replace(DEST)
    check()


def install_dependencies(studio):
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if npm is None:
        raise FileNotFoundError('npm is required to build RHWP; install Node.js and add it to PATH')
    subprocess.run([npm, 'ci', '--ignore-scripts'], cwd=studio, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--source', type=Path, help='Already extracted pinned source tree')
    parser.add_argument('--install-built', action='store_true', help='Install an already built tree supplied by --source')
    args = parser.parse_args()
    if args.check:
        check(); return
    cache = ROOT / 'build/rhwp'
    cache.mkdir(parents=True, exist_ok=True)
    source = args.source
    if source is None:
        archive, core = cache / 'source.tar.gz', cache / 'core.tgz'
        download(f'https://codeload.github.com/edwardkim/rhwp/tar.gz/refs/tags/v{VERSION}', archive, SOURCE_SHA)
        download(f'https://registry.npmjs.org/@rhwp/core/-/core-{VERSION}.tgz', core, CORE_SHA)
        prefix = f'rhwp-{VERSION}/'
        selected = ('rhwp-studio/', 'rhwp-shared/', 'assets/fonts/', 'npm/editor/', 'npm/hwpctrl-ocx/', 'scripts/', 'LICENSE', 'THIRD_PARTY_LICENSES.md')
        extract(archive, cache, lambda name: name.startswith(tuple(prefix + p for p in selected)))
        source = cache / f'rhwp-{VERSION}'
        extract(core, source / 'pkg', lambda name: name.startswith('package/'), strip=1)
    if not args.install_built:
        patch_save_guard(source)
        studio = source / 'rhwp-studio'
        fonts = studio / 'public/fonts'
        if fonts.is_symlink():
            fonts.unlink()
        shutil.copytree(source / 'assets/fonts', fonts, dirs_exist_ok=True)
        install_dependencies(studio)
        env = {**os.environ, 'RHWP_DISABLE_EXTERNAL_WEBFONTS': '1'}
        subprocess.run(['node', 'node_modules/vite/bin/vite.js', 'build', '--base=/documents/hwp-assets/'], cwd=studio, env=env, check=True)
    install(source)


if __name__ == '__main__':
    main()
