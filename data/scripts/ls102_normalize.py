"""Normalize row formats/units; preserve fractional money and unknown prices."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import boot_paths  # noqa: E402,F401
from common.value_semantics import comparison_number, decimal_json_number  # noqa: E402


def number(value, name, *, integer=False):
    """Use the shared numeric semantics; integer units must never be truncated."""
    if value is None or isinstance(value, str) and not value.strip():
        return None
    parsed = comparison_number(value)
    if parsed is None:
        raise ValueError(f'{name}: finite number required')
    integral = int(parsed)
    if integer and parsed != integral:
        raise ValueError(f'{name}: integer unit required')
    if parsed == integral:
        return integral
    return decimal_json_number(parsed)


def normalize(args):
    payload = args['payload']
    if args['kind'] == 'jsonl':
        payload = [json.loads(line) for line in payload.splitlines() if line.strip()]
    aliases = args.get('aliases', {})
    rows = []
    for row in payload:
        normalized = dict(row)
        if 'item' in normalized:
            normalized['item'] = aliases.get(normalized['item'], normalized['item'])
        for name in ['quantity', 'available', 'reserved', 'pack', 'unit_price', 'shipping']:
            if name in normalized:
                normalized[name] = number(
                    normalized[name], name,
                    integer=name in {'quantity', 'available', 'reserved', 'pack'},
                )
        rows.append(normalized)
    return rows


if __name__ == '__main__':
    print(json.dumps(normalize(json.load(sys.stdin)), ensure_ascii=False, allow_nan=False))
