#!/usr/bin/env python3
"""파일 등록용 후보 사전집. 기존 빌더의 수집·병합·파생·삼각 검증을 재사용한다."""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: E402,F401
import yaml
from iblbuild_common import NODE_ORDER, CATALOG_HEADER
from iblbuild_derive import (collect_package_fragments, merge_fragments, serialize_nodes_document,
                             derive_tool_json_docs, derive_package_meta, derive_fixtures,
                             derive_phone_manifest, derive_shell_shadow)
from iblbuild_validators import validate
from iblbuild_params_check import validate_impl_reads


def compile_candidate(root: Path, incoming: Path, output: Path):
    with tempfile.TemporaryDirectory(prefix='ibl-catalog-') as work:
        candidate = Path(work)
        (candidate / 'data').mkdir()
        for name in ('ibl_nodes_src', 'api_registry.yaml', 'vocabulary_policy.yaml', 'guides'):
            src = root / 'data' / name
            if src.exists():
                (candidate / 'data' / name).symlink_to(src, target_is_directory=src.is_dir())
        (candidate / 'backend').symlink_to(Path(__file__).resolve().parents[1] / 'backend', target_is_directory=True)
        for location in ('installed', 'not_installed'):
            for kind in ('tools', 'extensions'):
                target = candidate / 'data/packages' / location / kind
                target.mkdir(parents=True)
                source = root / 'data/packages' / location / kind
                if source.exists():
                    for p in source.iterdir():
                        if p.is_dir() and not p.name.startswith('.'):
                            (target / p.name).symlink_to(p, target_is_directory=True)
        pid = json.loads((incoming / 'manifest.json').read_text())['id']
        dest = candidate / 'data/packages/not_installed/tools' / pid
        if dest.exists():
            raise ValueError('묶음 ID 충돌')
        shutil.copytree(incoming, dest)
        src = candidate / 'data/ibl_nodes_src'
        if src.exists():
            text = (src / 'meta.yaml').read_text() + '\nnodes:\n'
            text += ''.join((src / f'{node}.yaml').read_text() for node in NODE_ORDER)
            data = yaml.safe_load(text)
        else:
            # 배포에 편집 소스가 없으면 현 사전집에서 기존 패키지 소유분만 회수하고 재병합한다.
            data = yaml.safe_load((root / 'data/ibl_nodes.yaml').read_text())
            current, issues = collect_package_fragments(root, yaml)
            if issues:
                raise ValueError('; '.join(issues))
            for _, node, actions in current:
                for action in actions:
                    data['nodes'][node]['actions'].pop(action, None)
        fragments, issues = collect_package_fragments(candidate, yaml)
        issues += merge_fragments(data, fragments)
        tool_docs, tool_issues = derive_tool_json_docs(candidate, yaml)
        issues += tool_issues
        # 삼각 검증은 새 묶음의 파생 tool.json을 포함해 읽는다.
        for path, content in tool_docs.items():
            if path.parent == dest:
                if path.exists() and json.loads(path.read_text()) != json.loads(content):
                    raise ValueError('동봉 tool.json이 어휘 정의와 다릅니다')
                path.write_text(content)
        issues += validate(data, candidate)
        issues += validate_impl_reads(data, candidate)
        # 용례의 낱말 존재 확인은 후보 사전집을 기준으로 한다(아직 활성화하지 않는다).
        import re
        for example in json.loads((dest / 'examples.json').read_text()):
            for node, action in re.findall(r'\[([a-z_]+):([a-z_0-9]+)\]', example['ibl_code']):
                if action not in data.get('nodes', {}).get(node, {}).get('actions', {}):
                    issues.append(f'용례에 보유하지 않은 어휘: {node}:{action}')
        if issues:
            raise ValueError('; '.join(issues))
        expected = tool_docs.get(dest / 'tool.json')
        if expected is None:
            raise ValueError('ibl_actions.yaml에 tool_json 원본이 필요합니다')
        if (dest / 'tool.json').exists() and json.loads((dest / 'tool.json').read_text()) != json.loads(expected):
            raise ValueError('동봉 tool.json이 어휘 정의의 파생 결과와 다릅니다')
        output.mkdir(parents=True, exist_ok=True)
        (output / 'tool.json').write_text(expected)
        (output / 'ibl_nodes.yaml').write_text(serialize_nodes_document(CATALOG_HEADER, data, yaml))
        derived = {'package_meta.json': derive_package_meta(candidate), 'ibl_fixtures.json': derive_fixtures(data),
                   'phone_manifest.json': derive_phone_manifest(data, candidate), 'shell_shadow.json': derive_shell_shadow(data)}
        for name, value in derived.items():
            (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--incoming', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    try:
        compile_candidate(args.root.resolve(), args.incoming.resolve(), args.output.resolve())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
