"""Locate retained producer replies in FailureViews without interpreting their truth.

These are attributed tool results, not successful partial values or effect proofs.
Never decode text/stdout, inspect wire duplicates, or infer a completed goal.
"""
from itertools import islice


def collect(value, limit=8):
    rows, visited, omitted = [], 0, 0
    incomplete = False
    excluded = {'value_wire', 'partial_wire', 'source_map', 'evidence', 'recordings',
                'output', 'stdout', 'stderr', 'text', 'content', 'tool_result'}

    def walk(obj, path):
        nonlocal visited, omitted, incomplete
        visited += 1
        if visited > 1000 or len(path) > 16:
            incomplete = True
            return
        if isinstance(obj, dict):
            details = obj.get('details')
            if (isinstance(obj.get('code'), str) and isinstance(obj.get('kind'), str)
                    and isinstance(details, dict) and isinstance(details.get('tool_result'), dict)
                    and '$model_tool_failure' not in details['tool_result']):
                if len(rows) < limit:
                    rows.append((path + ['details', 'tool_result'], obj))
                else:
                    omitted += 1
            children = ((key, child) for key, child in obj.items() if key not in excluded)
        elif isinstance(obj, list):
            children = enumerate(obj)
        else:
            return
        for key, child in children:
            if visited >= 1000:
                incomplete = True
                break
            walk(child, path + [key])

    walk(value, [])
    return rows, {'omitted': omitted, 'scan_incomplete': incomplete}


def fields(value, limit=32):
    """Shape only. A field called 'saved' or 'verified' is not evaluated here."""
    shown, chars = [], 0
    for key in islice(value, limit):
        chars += len(str(key))
        if chars > 1000:
            break
        shown.append(key)
    return {'fields': shown, 'fields_omitted': len(value) - len(shown)}
