"""Conservative value relations at transformation and display boundaries.

A producer declaration is a candidate, not a proof. Relations are checked
against the current value every time; equal display content never certifies
source identity, completion or effect reuse. Exhaustion leaves both values.
"""

def _legacy_fields(value, *, max_chars=200000, max_rows=4096):
    if not isinstance(value, dict):
        return ()
    display, rows = value.get('_display'), value.get('items')
    fields = display.get('mirror_fields') if isinstance(display, dict) else None
    if not isinstance(fields, list) or not isinstance(rows, list) or len(rows) > max_rows:
        return ()
    pieces, size = [], 0
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('text'), str):
            return ()
        size += len(row['text']) + 2
        if size > max_chars:
            return ()
        pieces.append(row['text'])
    # Only exact ordered paragraph projections are proofs. Do not strip, sort, remove titles,
    # compare prefixes or use hashes as equality: selection/order are meaning.
    representations = [(sep, sep + sep.join(pieces) + sep) for sep in ('\n', '\n\n')]
    return tuple(k for k in fields if isinstance(k, str) and k != 'items'
                 and isinstance(value.get(k), str) and len(value[k]) <= max_chars
                 and any(sep + value[k] + sep in text for sep, text in representations))


def mirrored_text_relations(value, *, max_chars=200000, max_rows=4096):
    """Finite top-level paths only; structured declarations require exact joins."""
    result = {k: 'items' for k in _legacy_fields(value, max_chars=max_chars, max_rows=max_rows)}
    display = value.get('_display') if isinstance(value, dict) else None
    fields = display.get('mirror_fields') if isinstance(display, dict) else None
    if not isinstance(fields, list) or len(fields) > 64:
        return result
    for spec in fields:
        if not isinstance(spec, dict) or set(spec) != {'field', 'collection', 'text_field', 'separator'}:
            continue
        field, collection, text_field, sep = (spec[k] for k in ('field', 'collection', 'text_field', 'separator'))
        if not all(isinstance(k, str) and k and len(k) <= 128 for k in (field, collection, text_field)):
            continue
        if field == collection or not isinstance(sep, str) or len(sep) > 8:
            continue
        text, rows = value.get(field), value.get(collection)
        if (not isinstance(text, str) or not text or len(text) > max_chars
                or not isinstance(rows, list) or not 0 < len(rows) <= max_rows):
            continue
        pieces, size = [], 0
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get(text_field), str):
                break
            size += len(row[text_field]) + len(sep)
            if size > max_chars + len(sep):
                break
            pieces.append(row[text_field])
        if len(pieces) == len(rows) and sep.join(pieces) == text:
            result[field] = collection
    return result


def mirrored_text_fields(value, **limits):
    return tuple(mirrored_text_relations(value, **limits))


def invalidate_display_relations(value):
    """After a transform, preserve only declarations true of the current value."""
    display = value.get('_display') if isinstance(value, dict) else None
    if not isinstance(display, dict) or 'mirror_fields' not in display:
        return value
    valid = mirrored_text_relations(value)
    declarations = display['mirror_fields']
    kept = [d for d in declarations if
            isinstance(d, str) and d in valid or
            isinstance(d, dict) and isinstance(d.get('field'), str) and
            mirrored_text_relations({**value, '_display': {'mirror_fields': [d]}}).get(d['field'])
            == d.get('collection') and d.get('collection') is not None] if isinstance(declarations, list) else []
    return {**value, '_display': {**display, 'mirror_fields': kept}}
