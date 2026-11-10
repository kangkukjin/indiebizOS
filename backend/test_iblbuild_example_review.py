"""Reviewed marketplace examples preserve scope and notification conditions."""
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest


EXAMPLES = json.loads((Path(__file__).resolve().parents[1]
                      / "data/guides/examples/used_market.json").read_text())


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda ex: str(ex["id"]))
def test_reviewed_examples_compile_with_current_contracts(example):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program

    plan = compile_program(example["ibl_code"], load_registry())
    assert not plan.issues, plan.report()


@pytest.mark.parametrize("example_id,inclusive", [(3701, False), (4094, True)])
@pytest.mark.parametrize("prices", [[], [None], [99999], [100000], [100001],
                                   [None, 100001, 99999, 100000]])
def test_reviewed_price_alerts_require_known_price_and_correct_bound(
        example_id, inclusive, prices):
    from ibl_v2_adapters import Adapter, load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime

    registry = load_registry()
    rows = [{"title": f"매물{i}", "price": price} for i, price in enumerate(prices)]
    notifications, searches = [], []

    def search(rt, args):
        searches.append(args)
        return {"items": rows}

    def notify(rt, args):
        notifications.append(args["message"])
        return {"success": True}

    registry["sense:used"] = Adapter(registry["sense:used"].contract, search)
    registry["self:notify_user"] = Adapter(registry["self:notify_user"].contract, notify)
    code = next(ex["ibl_code"] for ex in EXAMPLES if ex["id"] == example_id)
    result = Runtime(compile_program(code, registry)).run()
    assert result["success"], result
    assert searches == [{"source": "danggeun", "query": "자전거", "region": "역삼동"}]
    expected = [f"{r['title']} {r['price']}원" for r in rows if r["price"] is not None
                and (r["price"] <= 100000 if inclusive else r["price"] < 100000)]
    assert notifications == expected


@pytest.mark.parametrize("example", EXAMPLES[:5], ids=lambda ex: str(ex["id"]))
def test_reviewed_search_examples_preserve_source_scope(example):
    from ibl_v2_adapters import Adapter, load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from ibl_v2_ir import unpack

    value = {"items": [], "scanned": 200, "unlocated": 200,
             "truncations": [{"scope": "source", "reason": "scan_limit"}],
             "note": "지역 전체의 매물 부재를 뜻하지 않습니다."}
    registry = load_registry()
    registry["sense:used"] = Adapter(registry["sense:used"].contract, lambda rt, args: value)
    result = Runtime(compile_program(example["ibl_code"], registry)).run()
    assert result["success"], result
    assert unpack(result["value_wire"]["data"]) == value

