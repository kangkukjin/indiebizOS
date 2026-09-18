"""Synthetic receipt wording; private notification originals stay outside git."""
import importlib.util
import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, PKG / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def modules(tmp_path, monkeypatch):
    sync = load("finance_sync")
    storage = load("finance_storage")
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(storage, "FILES_DIR", str(tmp_path / "files"))
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "finance.db"))
    monkeypatch.setattr(storage, "DEFAULT_OWNER", "test-owner")
    monkeypatch.setitem(sys.modules, "finance_sync", sync)
    monkeypatch.setitem(sys.modules, "finance_storage", storage)
    handler = load("handler")
    return sync, storage, handler


def record(body, title="알림", pkg="gov.cheongju.cjpay"):
    return {"pkg": pkg, "ts": 1789700000000,
            "android.title": title, "android.bigText": body}


@pytest.mark.parametrize("city", ["청주", "다른시"])
def test_receipt_is_income_and_idempotent(modules, city):
    sync, storage, handler = modules
    body = (f"{city} 결제시 인센티브가 지급 되었습니다.\n"
            f"{city} 결제시 인센티브 123원이 지급되었습니다. "
            "최종 인센티브잔액 456원 당월 인센티브 누적 적립금액 789원")
    rec = record(body, "인센티브 지급")
    row = sync._record_to_row(rec)
    assert row["type"] == "income"
    assert row["amount"] == 123
    assert row["parsed"] == 1
    assert len(storage.merge_synced_rows([row])) == 1
    before = storage.get_transactions()[0]
    assert before["tx_type"] == "income"
    assert body in before["note"]
    # Different transport whitespace / duplicate post must keep the same identity.
    repeated = sync._record_to_row({**rec, "ts": rec["ts"] + 10,
                                   "android.bigText": body.replace("\n", "  ")})
    assert repeated["ext_id"] == row["ext_id"]
    assert storage.merge_synced_rows([repeated]) == []
    assert storage.get_transactions() == [before]
    summary = storage.get_summary(month=before["occurred_at"][:7])
    assert summary["income"] == 123
    assert summary["expense"] == 0
    assert summary["by_source"] == {}
    assert handler._tx_items([before])[0]["kind"] == "수입"
    assert handler._tx_points([before]) == []
    assert storage.get_transactions(tx_type="expense") == []


@pytest.mark.parametrize("body", [
    "인센티브 123원 지급 예정입니다. 결제하면 받을 수 있습니다.",
    "결제시 인센티브 123원이 지급됩니다.",
    "결제시 인센티브 123원이 지급되지 않았습니다.",
    "인센티브 123원 지급 완료 예정",
    "(광고) 결제시 인센티브 123원이 지급되었습니다.",
])
def test_notices_are_not_transactions(modules, body):
    sync, storage, _ = modules
    assert sync._record_to_row(record(body, "인센티브 지급 안내")) == {}


@pytest.mark.parametrize("title,body,kind,amount", [
    ("결제 완료", "테스트가게에서 9,000원 결제. 인센티브 300원 사용", "approve", 9000),
    ("결제 완료", "테스트가게에서 9,000원 결제. 인센티브 300원 지급 예정", "approve", 9000),
    ("결제 취소", "테스트가게에서 9,000원 결제 취소", "cancel", 9000),
    ("환불", "테스트가게에서 9,000원 환불", "cancel", 9000),
    ("충전 완료", "50,000원 충전 완료", "charge", 50000),
    ("하나카드 승인", "9,000원 일시불 테스트상점 승인", "approve", 9000),
])
def test_existing_payment_contracts(modules, title, body, kind, amount):
    sync, storage, handler = modules
    row = sync._record_to_row(record(body, title))
    assert row["type"] == kind
    assert row["amount"] == amount
    inserted = storage.merge_synced_rows([row])
    if kind == "charge":
        assert inserted == []
        assert storage.get_transactions() == []
        return
    tx = storage.get_transactions()[0]
    assert tx["tx_type"] == "expense"
    assert tx["amount"] == (-amount if kind == "cancel" else amount)
    assert storage.merge_synced_rows([row]) == []


def test_receipt_uses_receipt_amount_not_balance(modules):
    sync, _, _ = modules
    row = sync._record_to_row(record(
        "잔액 9,999원. 인센티브 123원이 지급되었습니다.", "지급"))
    assert (row["type"], row["amount"]) == ("income", 123)


def test_income_survives_collection_and_handler(modules, monkeypatch):
    import json
    sync, storage, handler = modules
    raw = json.dumps({"pkg": "gov.cheongju.cjpay", "posted_at": 1789700000000,
                      "title": "인센티브 지급",
                      "text": "결제시 인센티브 123원이 지급되었습니다."})
    recs = sync._records_from_capture(raw)
    monkeypatch.setattr(sync, "_local_capture_path", lambda: None)
    monkeypatch.setattr(sync, "_adb", lambda: "adb")
    from types import SimpleNamespace
    monkeypatch.setattr(sync.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout=b"device"))
    monkeypatch.setattr(sync, "_read_phone_capture", lambda: recs)
    response = json.loads(handler.sync_finance_from_phone({}))
    assert response["success"] and response["new"] == 1
    assert storage.get_transactions()[0]["tx_type"] == "income"
    assert json.loads(handler.sync_finance_from_phone({}))["new"] == 0
