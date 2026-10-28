"""Convert package prices to per-unit prices without truncating money."""
import json
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import boot_paths  # noqa: E402,F401
from common.value_semantics import comparison_number, decimal_json_number  # noqa: E402


def number(value, name, *, optional=False):
    if optional and (value is None or isinstance(value, str) and not value.strip()):
        return None
    parsed = comparison_number(value)
    if parsed is None:
        raise ValueError(f'{name}: finite number required')
    return parsed


def json_number(value):
    if value is None:
        return None
    integer = int(value)
    return integer if value == integer else decimal_json_number(value)


def normalize(args):
    rows = []
    for item in args['items']:
        row = dict(item)
        pack = number(row['pack'], 'pack')
        if pack <= 0 or pack != int(pack):
            raise ValueError('positive integer pack required')
        price = number(row['pack_price'], 'pack_price', optional=True)
        shipping = number(row['shipping'], 'shipping')
        row['pack'] = int(pack)
        row['pack_price'] = json_number(price)
        row['shipping'] = json_number(shipping)
        # Decimal prices retain their decimal spelling through division.
        # Integer inputs use Decimal too, so the shared JSON boundary can reject
        # unrepresentable per-unit precision instead of silently rounding it.
        unit_price = None if price is None else Decimal(str(price)) / int(pack)
        row['unit_price'] = json_number(unit_price)
        rows.append(row)
    return rows


if __name__ == '__main__':
    print(json.dumps(normalize(json.load(sys.stdin)), ensure_ascii=False, allow_nan=False))
