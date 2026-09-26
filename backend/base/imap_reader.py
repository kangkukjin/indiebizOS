"""Account-bound, read-only IMAP over TLS for channel_read.

IMAP_EMAIL/HOST/PORT/USERNAME/PASSWORD configure one additional account.
Gmail remains the existing provider for other configured identities. Credentials
never enter results, exception messages, reprs, or protocol debug logs.
"""
import email
import imaplib
import os
import re
import shlex
import ssl
from datetime import date
from email import policy
from html import unescape
from pathlib import Path


def dotenv_values(path, **kwargs):
    """Load desktop configuration only when present; env-only bodies need no dotenv."""
    if not path.is_file():
        return {}
    try:
        from dotenv import dotenv_values as read_values
    except ImportError:
        raise MailReadError("config", "이 몸에서 .env 설정을 읽을 수 없습니다.") from None
    return read_values(path, **kwargs)


class MailReadError(Exception):
    """Only fixed, credential-free diagnostics cross the channel boundary."""

    def __init__(self, stage, message):
        self.stage = stage
        super().__init__(message)


def configured_reader(account):
    """Return a reader only for the exact configured account; never fall back on failure."""
    root = Path(os.environ.get("INDIEBIZ_BASE_PATH") or Path(__file__).resolve().parents[2])
    values = dotenv_values(root / ".env", interpolate=False)
    keys = ("IMAP_EMAIL", "IMAP_HOST", "IMAP_PORT", "IMAP_USERNAME", "IMAP_PASSWORD")
    config = {key: values.get(key, os.environ.get(key)) for key in keys}
    address = (config.get("IMAP_EMAIL") or "").strip()
    # vj-ok: 메일 계정 신원의 프로토콜 식별자 대조이며 사용자 데이터 조건 판정이 아니다.
    if not account or not address or account.strip().casefold() != address.casefold():
        return None
    if not config.get("IMAP_HOST") or not config.get("IMAP_PASSWORD"):
        raise MailReadError("configuration", "IMAP_HOST/IMAP_PASSWORD 설정이 필요합니다.")
    try:
        port = int(config.get("IMAP_PORT") or 993)
        if not 1 <= port <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        raise MailReadError("configuration", "IMAP_PORT 설정이 올바르지 않습니다.") from None
    return IMAPReader(config["IMAP_HOST"], port,
                      config.get("IMAP_USERNAME") or address, config["IMAP_PASSWORD"])


def search_criteria(query):
    """Translate an explicit Gmail subset, rejecting unsupported syntax before login.

    AND only: plain text, from:, to:, subject:, after:/before: YYYY-MM-DD
    or YYYY/MM/DD, is:unread/read. Dates use IMAP calendar-day semantics:
    after is SINCE (inclusive), before is exclusive. Gmail-only operators,
    Boolean/group/negation syntax are deliberately rejected, never ignored.
    """
    if query is None or query == "":
        return b"ALL"
    if not isinstance(query, str) or any(ord(c) < 32 or ord(c) == 127 for c in query):
        raise MailReadError("query", "검색어에 제어 문자를 사용할 수 없습니다.")
    try:
        tokens = shlex.split(query)
    except ValueError:
        raise MailReadError("query", "검색어의 따옴표가 닫히지 않았습니다.") from None
    terms = []
    for token in tokens:
        if token in ("OR", "AND", "NOT") or token.startswith("-") or any(c in token for c in "(){}"):
            raise MailReadError("query", "일반 IMAP 검색은 OR/NOT/괄호/부정 문법을 지원하지 않습니다.")
        key, sep, value = token.partition(":")
        if not sep:
            key, value = "text", token
        key = key.lower()
        if key in ("text", "from", "to", "subject") and value:
            quoted = value.replace("\\", "\\\\").replace('"', '\\"')
            terms.append(f'{key.upper()} "{quoted}"')
        elif key in ("after", "before") and value:
            try:
                d = date.fromisoformat(value.replace("/", "-"))
            except ValueError:
                raise MailReadError("query", "검색 날짜는 YYYY-MM-DD 또는 YYYY/MM/DD입니다.") from None
            months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
            operator = "SINCE" if key == "after" else "BEFORE"
            terms.append(f'{operator} {d.day:02d}-{months[d.month - 1]}-{d.year:04d}')
        elif key == "is" and value in ("unread", "read"):
            terms.append("UNSEEN" if value == "unread" else "SEEN")
        else:
            raise MailReadError("query", "일반 IMAP 검색 지원: 일반 텍스트, from:, to:, subject:, after:, before:, is:unread/read. Gmail 전용 문법은 지원하지 않습니다.")
    return (" ".join(terms) or "ALL").encode("utf-8")


def decode_message(raw, uid):
    message = email.message_from_bytes(raw, policy=policy.default)
    part = message.get_body(preferencelist=("plain", "html"))
    body = ""
    if part is not None:
        try:
            body = part.get_content()
        except (LookupError, UnicodeError):
            body = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
        if part.get_content_type() == "text/html":
            body = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", "", body)
            body = unescape(re.sub(r"<[^>]*>", " ", body))
    return {"id": uid.decode("ascii"), "subject": str(message.get("Subject", "")),
            "from": str(message.get("From", "")), "date": str(message.get("Date", "")),
            "snippet": " ".join(body.split())[:200], "body": body}


class IMAPReader:
    def __init__(self, host, port, username, password):
        self.host, self.port = host, port
        self._username, self._password = username, password
        self.total = 0

    def get_messages(self, query=None, max_results=10):
        criteria = search_criteria(query)
        if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= 100:
            raise MailReadError("query", "max_results는 1~100 정수여야 합니다.")
        client = None
        stage = "tls"
        try:
            client = imaplib.IMAP4_SSL(self.host, self.port,
                                      ssl_context=ssl.create_default_context(), timeout=20)
            client.debug = 0
            stage = "authentication"
            client.login(self._username, self._password)
            stage = "mailbox"
            status, _ = client.select("INBOX", readonly=True)
            if status != "OK":
                raise MailReadError(stage, "IMAP 수신함을 읽기 전용으로 열지 못했습니다.")
            stage = "search"
            status, data = client.uid("search", "CHARSET", "UTF-8", criteria)
            if status != "OK":
                raise MailReadError(stage, "IMAP 서버가 검색을 거절했습니다(UTF-8 검색 지원 확인 필요).")
            ids = (data[0] or b"").split()
            self.total = len(ids)
            stage = "fetch"
            messages = []
            for uid in reversed(ids[-max_results:]):
                status, data = client.uid("fetch", uid, "(BODY.PEEK[])")
                if status != "OK":
                    raise MailReadError(stage, "IMAP 메시지 조회에 실패했습니다.")
                raw = next((row[1] for row in data if isinstance(row, tuple) and isinstance(row[1], bytes)), None)
                if raw is None:
                    raise MailReadError(stage, "IMAP 응답에 메시지 본문이 없습니다.")
                messages.append(decode_message(raw, uid))
            return messages
        except MailReadError:
            raise
        except Exception:
            messages = {"tls": "IMAP TLS 연결에 실패했습니다.",
                        "authentication": "IMAP 인증이 거절되었습니다. 계정과 앱 비밀번호의 연결을 확인하세요.",
                        "mailbox": "IMAP 수신함 열기에 실패했습니다.",
                        "search": "IMAP 검색에 실패했습니다.",
                        "fetch": "IMAP 메시지 조회 또는 MIME 해석에 실패했습니다."}
            raise MailReadError(stage, messages[stage]) from None
        finally:
            if client is not None:
                try:
                    client.logout()
                except Exception:
                    pass  # Cleanup cannot replace the credential-free primary diagnostic.
