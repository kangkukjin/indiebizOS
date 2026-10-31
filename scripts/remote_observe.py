#!/usr/bin/env python3
"""Bounded, read-only facts for choosing a remote maintenance method.

No deletion advice, thresholds or repair policy. Paths are explicit; inaccessible
or unvisited files are reported as unknown, never counted as zero-size evidence.
"""
import os
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parents[1] / 'backend'
if not (_backend / 'boot_paths.py').is_file() and os.environ.get('INDIEBIZ_UPDATE_ROOT'):
    _backend = Path(os.environ['INDIEBIZ_UPDATE_ROOT']) / 'backend'
sys.path.insert(0, str(_backend))
import boot_paths  # noqa: E402,F401

import argparse
import json
import shutil
import stat
import time


def linked(path):
    value = path.lstat()
    return stat.S_ISLNK(value.st_mode) or bool(getattr(value, 'st_file_attributes', 0) & 1024)


def path_facts(path, *, max_entries=20000, seconds=2):
    path = Path(os.path.abspath(path))
    out = {'path': str(path), 'observed_at': time.time(), 'exists': path.exists(),
           'bytes': 0, 'files': 0, 'complete': True, 'errors': [], 'children': []}
    parent = path
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    try:
        usage = shutil.disk_usage(parent)
        out['volume'] = {'measured_at_path': str(parent), 'total_bytes': usage.total, 'free_bytes': usage.free}
    except OSError as exc:
        out['volume'] = {'error': str(exc)}
    if not out['exists']:
        out['bytes'] = None
        return out
    groups, stack, visited = {}, [path], 0
    deadline = time.monotonic() + seconds
    while stack:
        if visited >= max_entries or time.monotonic() >= deadline:
            out.update(complete=False, stopped_reason='observation_budget')
            break
        current = stack.pop()
        visited += 1
        try:
            if linked(current):
                out['complete'] = False
                out['errors'].append({'path': str(current), 'reason': 'link_not_followed'})
                continue
            value = current.stat()
            if current == path:
                out.update(modified_at=value.st_mtime, kind='directory' if current.is_dir() else 'file')
            if current.is_dir():
                # Bound discovery too, including very wide directories.
                with os.scandir(current) as entries:
                    for entry in entries:
                        if len(stack) + visited >= max_entries:
                            out.update(complete=False, stopped_reason='observation_budget')
                            break
                        stack.append(Path(entry.path))
            else:
                out['bytes'] += value.st_size
                out['files'] += 1
                name = current.relative_to(path).parts[0] if current != path else current.name
                row = groups.setdefault(name, {'name': name, 'bytes': 0, 'files': 0, 'latest_modified_at': 0})
                row['bytes'] += value.st_size
                row['files'] += 1
                row['latest_modified_at'] = max(row['latest_modified_at'], value.st_mtime)
        except OSError as exc:
            out['complete'] = False
            if len(out['errors']) < 10:
                out['errors'].append({'path': str(current), 'reason': str(exc)})
    out['children'] = sorted(groups.values(), key=lambda x: x['bytes'], reverse=True)[:20]
    out['size_kind'] = 'file_lengths' if out['complete'] else 'observed_lower_bound'
    receipt = path.with_name(path.name + '.artifact.json')
    try:
        if receipt.is_file() and not linked(receipt) and receipt.stat().st_size <= 65536:
            evidence = json.loads(receipt.read_text(encoding='utf-8'))
            if not isinstance(evidence, dict):
                raise ValueError('artifact receipt must be an object')
            s = path.stat()
            out['provenance'] = {'receipt': str(receipt), 'data': evidence,
                                 'matches_size_mtime': evidence.get('bytes') == s.st_size
                                 and evidence.get('mtime_ns') == s.st_mtime_ns}
    except (OSError, ValueError) as exc:
        out['provenance'] = {'error': str(exc)}
    return out


def process_facts(root, process_name='IndieBiz'):
    try:
        import psutil
    except ImportError as exc:
        return {'items': [], 'unobserved_processes': None, 'observed_at': time.time(),
                'error': str(exc)}
    rows, unknown = [], 0
    for process in psutil.process_iter(['pid', 'name']):
        try:
            exe = process.exe()
            cwd = process.cwd()
            relevant = (process_name.casefold() in (process.info['name'] or '').casefold()
                        or process_name.casefold() in {part.casefold() for part in Path(exe).parts}
                        or Path(exe).is_relative_to(root) or Path(cwd).is_relative_to(root))
            if not relevant:
                continue
            args = process.cmdline()
            data = [a.split('=', 1)[1] for a in args if a.startswith('--user-data-dir=')]
            code = [a for a in args if Path(a).name in ('api.py', 'restart_controller.py', 'restart_child.py')]
            row = {'pid': process.pid, 'born': process.create_time(), 'name': process.info['name'],
                   'executable': exe, 'cwd': cwd, 'code_entries': code, 'data_paths_from_args': data,
                   'executable_in_checkout': Path(exe).is_relative_to(root),
                   'cpu_seconds': sum(process.cpu_times()[:2])}
            try:
                io = process.io_counters()
                row['io_bytes'] = {'read': io.read_bytes, 'write': io.write_bytes}
            except (AttributeError, psutil.Error):
                row['io_bytes'] = None
            rows.append(row)
        except (psutil.Error, OSError, ValueError):
            unknown += 1
    return {'items': rows, 'unobserved_processes': unknown, 'observed_at': time.time()}


def observe(root, paths=(), *, process_name='IndieBiz', processes=True):
    root = Path(root).resolve()
    return {'schema': 'remote-observation/1', 'observed_at': time.time(),
            'checkout': str(root), 'scope': 'requested paths and matching processes; no cleanup decision',
            'paths': [path_facts(p) for p in (paths or [root])],
            'processes': process_facts(root, process_name) if processes else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--path', type=Path, action='append', default=[])
    parser.add_argument('--process-name', default='IndieBiz')
    args = parser.parse_args()
    print(json.dumps(observe(args.root, args.path, process_name=args.process_name), ensure_ascii=False))


if __name__ == '__main__':
    main()
