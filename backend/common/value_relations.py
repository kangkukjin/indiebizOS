"""Conservative value relations at transformation and display boundaries.

A producer declaration is a candidate, not a proof. Relations are checked
against the current value every time; equal display content never certifies
source identity, completion or effect reuse. Exhaustion leaves both values.
"""

def mirrored_text_fields(value, *, max_chars=200000, max_rows=4096):
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


def invalidate_display_relations(value):
    """After a transform, keep only relations true of its new rows."""
    display = value.get('_display') if isinstance(value, dict) else None
    if not isinstance(display, dict) or 'mirror_fields' not in display:
        return value
    out = dict(value)
    out['_display'] = {**display, 'mirror_fields': list(mirrored_text_fields(value))}
    return out
