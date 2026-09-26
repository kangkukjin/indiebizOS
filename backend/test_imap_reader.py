"""IMAP integration tests: all credentials and messages are synthetic, no network."""
import boot_paths  # noqa: F401
import imaplib
import ssl
from email.message import EmailMessage
from types import SimpleNamespace

import pytest
import channel_engine as channel
import imap_reader as mail


@pytest.fixture
def config(monkeypatch):
    values = {"IMAP_EMAIL": "owner@example.net", "IMAP_HOST": "imap.example.net",
              "IMAP_USERNAME": "login", "IMAP_PORT": "993", "IMAP_PASSWORD": "test-secret"}
    # 다른 시험의 dotenv 로딩이나 실제 실행 환경으로 폴백하지 않게 격리한다.
    for key in values:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(mail, "dotenv_values", lambda *a, **kw: values)
    return values


class FakeIMAP:
    def __init__(self, raw, fail=None, ids=b"1 2 3"):
        self.raw, self.fail, self.ids = raw, fail, ids
        self.calls = []
        self.debug = 0

    def login(self, username, password):
        self.calls.append(("login",))
        if self.fail == "authentication":
            raise imaplib.IMAP4.error("server echoed test-secret")
        assert (username, password) == ("login", "test-secret")
        return "OK", []

    def select(self, mailbox, readonly=False):
        self.calls.append(("select", mailbox, readonly))
        return ("NO" if self.fail == "mailbox" else "OK"), [b"3"]

    def uid(self, command, *args):
        self.calls.append((command, *args))
        if command == "search":
            return ("NO" if self.fail == "search" else "OK"), [self.ids]
        assert command == "fetch" and args[1] == "(BODY.PEEK[])"
        if self.fail == "fetch":
            return "NO", []
        return "OK", [(b"BODY[]", self.raw), b")"]

    def logout(self):
        self.calls.append(("logout",))


@pytest.fixture
def protocol(monkeypatch, config):
    msg = EmailMessage()
    msg["Subject"] = "한글 제목"
    msg["From"] = "보낸 사람 <sender@example.org>"
    msg["Date"] = "Sat, 26 Sep 2026 05:00:00 +0000"
    msg.set_content("한글 본문 " + "a" * 600)
    msg.add_alternative("<p>다른 HTML 본문</p>", subtype="html")
    msg.add_attachment(b"hidden attachment", maintype="application", subtype="octet-stream", filename="test.bin")
    fake = FakeIMAP(msg.as_bytes())

    def connect(host, port, ssl_context, timeout):
        assert host == "imap.example.net" and port == 993 and timeout == 20
        assert ssl_context.check_hostname and ssl_context.verify_mode == ssl.CERT_REQUIRED
        return fake

    monkeypatch.setattr(mail.imaplib, "IMAP4_SSL", connect)
    return fake


def test_account_binding_and_incomplete_config(config):
    assert isinstance(mail.configured_reader("OWNER@example.net"), mail.IMAPReader)
    assert mail.configured_reader("other@example.net") is None
    assert mail.configured_reader(None) is None
    config.pop("IMAP_PASSWORD")
    with pytest.raises(mail.MailReadError, match="IMAP_PASSWORD"):
        mail.configured_reader("owner@example.net")


@pytest.mark.parametrize("value", ["bad", "0", "65536"])
def test_invalid_port(config, value):
    config["IMAP_PORT"] = value
    with pytest.raises(mail.MailReadError):
        mail.configured_reader("owner@example.net")


def test_readonly_mime_newest_first_and_truncation(protocol):
    out = channel._channel_read("email", {"max_results": 2}, {"email": "owner@example.net"})
    assert out["success"] and out["readonly"] and out["provider"] == "imap"
    assert out["total"] == 3 and out["count"] == 2 and out["truncated"]
    assert [m["id"] for m in out["items"]] == ["3", "2"]
    first = out["items"][0]
    assert first["subject"] == "한글 제목"
    assert first["body"].startswith("한글 본문") and first["body_truncated"]
    assert "hidden attachment" not in first["body"]
    assert ("select", "INBOX", True) in protocol.calls
    assert protocol.calls[-1] == ("logout",)
    assert not any(c[0] in ("store", "expunge", "close", "send") for c in protocol.calls)


@pytest.mark.parametrize("search", [False, True])
def test_requested_selection_passes_ibl_boundary(protocol, search):
    from ibl_v2_adapters import decode_envelope
    from ibl_v2_ir import Fault

    fn = channel._channel_search if search else channel._channel_read
    params = {"max_results": 2, **({"query": "subject:test"} if search else {})}
    out = fn("email", params, {"email": "owner@example.net"})
    value, evidence = decode_envelope(out, {"value_path": "/items"})
    assert [row["subject"] for row in value] == ["한글 제목", "한글 제목"]
    assert evidence["markers"]["truncations"] == [
        {"scope": "selection", "unit": "messages", "retained": 2,
         "total": 3, "parameter": "max_results"}]
    if not search:
        assert all(row["body_truncated"] for row in value)
    # 실제 원천 누락을 선택 범위 표지로 숨기지 않는다.
    out["truncations"].append({"scope": "source", "unit": "messages", "omitted": 1})
    with pytest.raises(Fault, match="불완전"):
        decode_envelope(out, {"value_path": "/items"})


def test_search_utf8_and_currency(protocol):
    out = channel._channel_search("email", {"query": 'subject:"한글 제목" is:unread'}, {"email": "owner@example.net"})
    assert out["success"] and out["items"] == out["messages"]
    assert ("search", "CHARSET", "UTF-8", 'SUBJECT "한글 제목" UNSEEN'.encode()) in protocol.calls


@pytest.mark.parametrize("query", ["label:important", "has:attachment", "a OR b", "-from:a", "(x)", "in:sent", "bad\r\nLOGOUT", 'subject:"unfinished', "after:bad"])
def test_unsupported_query_before_auth(protocol, query):
    out = channel._channel_search("email", {"query": query}, {"email": "owner@example.net"})
    assert not out["success"] and out["stage"] == "query"
    assert protocol.calls == []


def test_date_and_literal_escape():
    assert mail.search_criteria("from:a to:b after:2026/09/01 before:2026-10-01 is:read") == b'FROM "a" TO "b" SINCE 01-Sep-2026 BEFORE 01-Oct-2026 SEEN'
    assert mail.search_criteria('"hello world"') == b'TEXT "hello world"'
    assert mail.search_criteria('subject:\'a"b\'') == b'SUBJECT "a\\"b"'


@pytest.mark.parametrize("stage", ["authentication", "mailbox", "search", "fetch"])
def test_failures_no_retry_no_fallback_no_secret(protocol, monkeypatch, stage):
    protocol.fail = stage
    monkeypatch.setattr(channel, "_get_gmail_client", lambda **kw: pytest.fail("IMAP must never fall back"))
    out = channel._channel_read("email", {}, {"email": "owner@example.net"})
    assert not out["success"] and out["stage"] == stage
    assert "test-secret" not in str(out)
    assert protocol.calls.count(("login",)) == 1
    assert protocol.calls[-1] == ("logout",)


def test_env_only_body_needs_no_dotenv(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def without_dotenv(name, *args, **kwargs):
        if name == "dotenv":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_dotenv)
    assert mail.dotenv_values(tmp_path / "missing.env") == {}
    path = tmp_path / "config.env"
    path.write_text("IMAP_EMAIL=owner@example.net\n")
    with pytest.raises(mail.MailReadError) as caught:
        mail.dotenv_values(path)
    assert caught.value.stage == "config"


def test_tls_failure_sanitized(config, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("test-secret")
    monkeypatch.setattr(mail.imaplib, "IMAP4_SSL", fail)
    out = channel._channel_read("email", {}, {"email": "owner@example.net"})
    assert out["stage"] == "tls" and "test-secret" not in str(out)


def test_empty_inbox(protocol):
    protocol.ids = b""
    out = channel._channel_read("email", {}, {"email": "owner@example.net"})
    assert out["success"] and out["items"] == [] and out["total"] == 0


@pytest.mark.parametrize("limit", [0, -1, 101, True, "10"])
def test_bad_limit_before_auth(protocol, limit):
    out = channel._channel_read("email", {"max_results": limit}, {"email": "owner@example.net"})
    assert out["stage"] == "query" and protocol.calls == []


def test_html_only_mime():
    msg = EmailMessage()
    msg.set_content("<style>secret</style><p>안녕 &amp; world</p><script>bad()</script>", subtype="html")
    body = mail.decode_message(msg.as_bytes(), b"1")["body"]
    assert "안녕 & world" in body and "bad()" not in body and "secret" not in body


@pytest.mark.parametrize("search", [False, True])
def test_gmail_original_query_and_account(config, monkeypatch, search):
    calls = []
    def get_messages(**kw):
        calls.append(kw)
        return [{"id": "gmail-id", "subject": "test", "body": "body"}]
    def factory(email):
        assert email == "someone@gmail.com"
        return SimpleNamespace(get_messages=get_messages)
    monkeypatch.setattr(channel, "_get_gmail_client", factory)
    query = "label:important has:attachment" if search else None
    fn = channel._channel_search if search else channel._channel_read
    out = fn("email", {"query": query, "max_results": 7}, {"email": "someone@gmail.com"})
    assert out["success"] and out["provider"] == "gmail"
    assert calls == [{"query": query, "max_results": 7}]
    assert out["items"][0]["id"] == "gmail-id"


def test_system_account_routing_and_identity_gate(protocol, tmp_path):
    identity = channel._resolve_agent_identity("email", {"account": "owner@example.net"}, str(tmp_path), "system_ai")
    assert identity["email"] == "owner@example.net"
    assert channel._channel_read("email", {}, identity)["provider"] == "imap"
    denied = channel._resolve_agent_identity("email", {"account": "owner@example.net"}, str(tmp_path))
    assert "error" in denied


def test_nostr_read_unchanged(monkeypatch):
    monkeypatch.setattr(channel, "_get_indienet", lambda: SimpleNamespace(fetch_dms=lambda **kw: [{"id": "dm"}]))
    assert channel._channel_read("nostr", {}, {})["items"] == [{"id": "dm"}]


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
