"""104회차: 금액 문자열/소수/미확인 값이 조달 수량과 비용을 바꾸지 않는다."""
import boot_paths  # noqa: F401
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_script(name, args):
    return subprocess.run(
        [sys.executable, str(ROOT / 'data/scripts' / name)],
        input=json.dumps(args), text=True, capture_output=True, check=False,
    )


@pytest.mark.parametrize('kind', ['rows', 'jsonl'])
def test_fractional_money_and_unknown_prices_survive_normalization(kind):
    rows = [
        {'item': 'alias', 'quantity': '3', 'pack': '2', 'unit_price': 70.5},
        {'item': 'K', 'unit_price': '70.5', 'shipping': '80.5'},
        {'item': 'K', 'unit_price': ''},
        {'item': 'K', 'unit_price': None},
        {'item': 'K', 'unit_price': '  '},
    ]
    result = run_script('ls102_normalize.py', {
        'kind': kind,
        'payload': rows if kind == 'rows' else '\n'.join(map(json.dumps, rows)),
        'aliases': {'alias': 'K'},
    })
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    assert [r['unit_price'] for r in actual] == [70.5, 70.5, None, None, None]
    assert actual[0]['item'] == 'K'
    assert actual[0]['quantity'] == 3 and actual[0]['pack'] == 2
    assert actual[1]['shipping'] == 80.5
    # 3 required units in packs of 2: old int conversion undercharged by 2.
    assert 4 * actual[0]['unit_price'] == 282


@pytest.mark.parametrize('field', ['quantity', 'available', 'reserved', 'pack'])
def test_fractional_inventory_units_are_rejected_instead_of_truncated(field):
    result = run_script('ls102_normalize.py', {
        'kind': 'rows', 'payload': [{field: 2.5}], 'aliases': {},
    })
    assert result.returncode != 0 and 'integer unit required' in result.stderr


@pytest.mark.parametrize('value', ['NaN', 'Infinity', True, 'unknown'])
def test_invalid_money_is_not_a_zero_price(value):
    result = run_script('ls102_normalize.py', {
        'kind': 'rows', 'payload': [{'unit_price': value}], 'aliases': {},
    })
    assert result.returncode != 0 and 'finite number required' in result.stderr


def test_package_and_shipping_keep_fractions_and_unknown_package_price():
    result = run_script('ls103_normalize.py', {'items': [
        {'pack': '5', 'pack_price': '677.5', 'shipping': '80.5', 'source': 'D'},
        {'pack': 5, 'pack_price': 677.5, 'shipping': 80.5},
        {'pack': '5', 'pack_price': '', 'shipping': '80.5'},
        {'pack': '5', 'pack_price': None, 'shipping': '80.5'},
    ]})
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)
    assert [r['unit_price'] for r in rows] == [135.5, 135.5, None, None]
    assert rows[0]['source'] == 'D'
    assert 5 * rows[0]['unit_price'] + rows[0]['shipping'] == 758


@pytest.mark.parametrize('pack', [0, -1, 2.5, '2.5', True])
def test_package_size_must_be_a_positive_integer(pack):
    result = run_script('ls103_normalize.py', {
        'items': [{'pack': pack, 'pack_price': 100, 'shipping': 0}],
    })
    assert result.returncode != 0
    assert 'positive integer pack required' in result.stderr or 'finite number required' in result.stderr


def test_unrepresentable_unit_price_is_rejected_instead_of_rounded():
    result = run_script('ls103_normalize.py', {
        'items': [{'pack': 3, 'pack_price': 1, 'shipping': 0}],
    })
    assert result.returncode != 0 and '정밀도를 잃습니다' in result.stderr


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
