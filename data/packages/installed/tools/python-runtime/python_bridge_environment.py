"""Environment identity without importing candidate libraries."""
import hashlib
from common.value_semantics import text_match
import importlib.metadata as metadata
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


def fingerprint():
    h = hashlib.sha256(sys.version.encode())
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata.get('Name', '')):
        h.update((dist.metadata.get('Name', '') + '=' + dist.version).encode())
        base = Path(dist._path)
        for name in ('METADATA', 'RECORD', 'direct_url.json'):
            path = base / name
            if path.is_file():
                st = path.stat()
                h.update(f'{path}:{st.st_size}:{st.st_mtime_ns}'.encode())
        direct = dist.read_text('direct_url.json')
        if direct:
            entry = json.loads(direct)
            if entry.get('dir_info', {}).get('editable'):
                root = Path(unquote(urlparse(entry['url']).path))
                for path in sorted(root.rglob('*.py')):
                    if '.venv' not in path.parts and '.git' not in path.parts:
                        h.update(str(path).encode()); h.update(path.read_bytes())
    for path in sorted(Path(__file__).parent.glob('*.py')):
        h.update(path.read_bytes())
    return h.hexdigest()


def modules(query='', offset=0, limit=50):
    rows = []
    for name in sorted(sys.stdlib_module_names):
        if not query or text_match('contains', name, query):
            rows.append({'distribution': 'stdlib', 'version': sys.version.split()[0],
                         'module': name, 'import_verified': False})
    for name, distributions in sorted(metadata.packages_distributions().items()):
        if query and not text_match('contains', name + ' ' + ' '.join(distributions), query):
            continue
        rows.append({'module': name, 'distributions': [
            {'name': dist, 'version': metadata.version(dist)} for dist in distributions], 'import_verified': False})
    return {'items': rows[offset:offset + limit], 'total': len(rows), 'offset': offset,
            'next_offset': offset + limit if len(rows) > offset + limit else None,
            'scope': 'installed_metadata_candidates'}
