"""Discovery belongs to the registered Python library script."""
import sys
import importlib.metadata as metadata
from pathlib import Path
from common.value_semantics import text_match
from python_environment_lock import fingerprint as environment_fingerprint

def fingerprint():
    return environment_fingerprint(Path(__file__).parent)


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
