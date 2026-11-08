"""IMAP fetch + SMTP send using an app password."""
from __future__ import annotations

import email
import imaplib
import io
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

MAX_BODY_CHARS = 20000
MAX_ATTACHMENT_CHARS = 15000


@dataclass
class IncomingEmail:
    uid: bytes
    message_id: str
    from_email: str
    from_name: str
    subject: str
    body: str
    date: datetime | None
    references: str
    is_bulk: bool
    attachments: list = field(default_factory=list)  # [(filename, extracted_text)]
    reply_to: str = ""

    def attachment_text(self) -> str:
        return "\n\n".join(f"[Attachment: {n}]\n{t}" for n, t in self.attachments if t)


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "div", "li", "tr"):
            self.parts.append("\n")


def _html_to_text(html: str) -> str:
    p = _HTMLText()
    p.feed(html)
    return re.sub(r"\n{3,}", "\n\n", "".join(p.parts)).strip()


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:10]).strip()
    except Exception:
        return ""  # encrypted / scanned PDFs: filename is still recorded


def _attachments_of(msg: email.message.Message) -> list[tuple[str, str]]:
    out = []
    for part in msg.walk():
        fname = part.get_filename()
        if not fname:
            continue
        fname = _decode(fname)
        data = part.get_payload(decode=True) or b""
        ctype = part.get_content_type()
        if ctype == "application/pdf" or fname.lower().endswith(".pdf"):
            text = _pdf_text(data)
        elif ctype.startswith("text/") or fname.lower().endswith((".txt", ".csv")):
            text = data.decode(part.get_content_charset() or "utf-8", errors="replace")
        else:
            text = ""
        out.append((fname, text[:MAX_ATTACHMENT_CHARS]))
    return out


def _body_of(msg: email.message.Message) -> str:
    plain, html = None, None
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_maintype() == "multipart" or part.get_filename() \
                or part.get("Content-Disposition", "").startswith("attachment"):
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if part.get_content_type() == "text/plain" and plain is None:
            plain = text
        elif part.get_content_type() == "text/html" and html is None:
            html = text
    body = plain if plain else _html_to_text(html or "")
    return body.strip()[:MAX_BODY_CHARS]


def _read_uids_to_fetch(conn: imaplib.IMAP4_SSL, since: str, read_from: set[str],
                        skip_ids: set[str]) -> list[bytes]:
    """UIDs of already-read messages that come from `read_from` and aren't in `skip_ids`.

    Only headers are fetched here, so scanning read mail stays cheap.
    """
    typ, data = conn.uid("search", None, f'(SEEN SINCE "{since}")')
    if typ != "OK" or not data or not data[0]:
        return []
    uids = data[0].split()
    keep: list[bytes] = []
    for i in range(0, len(uids), 200):
        typ, rows = conn.uid("fetch", b",".join(uids[i:i + 200]),
                             "(UID BODY.PEEK[HEADER.FIELDS (FROM MESSAGE-ID)])")
        if typ != "OK":
            continue
        for row in rows:
            if not isinstance(row, tuple):
                continue
            m = re.search(rb"UID (\d+)", row[0])
            if not m:
                continue
            hdr = email.message_from_bytes(row[1])
            addr = parseaddr(_decode(hdr.get("From")))[1].lower()
            mid = (hdr.get("Message-ID") or "").strip()
            if addr in read_from and mid not in skip_ids:
                keep.append(m.group(1))
    return keep


def fetch_unread(host: str, port: int, user: str, password: str, since_days: int,
                 read_from: set[str] | None = None,
                 skip_ids: set[str] | None = None) -> tuple[imaplib.IMAP4_SSL, list[IncomingEmail]]:
    """Returns the open connection (so the caller can mark processed mail as read) and messages to process.

    That is all unread mail, plus already-read mail from `read_from` (known leads) whose
    Message-ID isn't in `skip_ids`, so a reply you opened on your phone still gets handled.
    """
    conn = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context())
    conn.login(user, password)
    conn.select("INBOX")
    since = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
    typ, data = conn.uid("search", None, f'(UNSEEN SINCE "{since}")')
    out: list[IncomingEmail] = []
    uids = data[0].split() if typ == "OK" and data and data[0] else []
    if read_from:
        seen = set(uids)
        uids += [u for u in _read_uids_to_fetch(conn, since, read_from, skip_ids or set()) if u not in seen]
    for uid in uids:
        # BODY.PEEK keeps the message unread unless we explicitly mark it
        typ, msg_data = conn.uid("fetch", uid, "(BODY.PEEK[])")
        if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        name, addr = parseaddr(_decode(msg.get("From")))
        try:
            date = parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
        except (TypeError, ValueError):
            date = None
        is_bulk = bool(
            msg.get("List-Unsubscribe") or msg.get("List-Id")
            or (msg.get("Auto-Submitted", "no").lower() != "no")
            or msg.get("Precedence", "").lower() in ("bulk", "list", "junk")
            or re.search(r"no-?reply|mailer-daemon|postmaster|notifications?@", addr or "", re.I)
        )
        out.append(IncomingEmail(
            uid=uid,
            message_id=(msg.get("Message-ID") or "").strip(),
            from_email=(addr or "").lower(),
            from_name=name,
            subject=_decode(msg.get("Subject")),
            body=_body_of(msg),
            date=date,
            references=" ".join(filter(None, [msg.get("References", ""), msg.get("Message-ID", "")])).strip(),
            is_bulk=is_bulk,
            attachments=_attachments_of(msg),
            reply_to=parseaddr(_decode(msg.get("Reply-To")))[1].lower(),
        ))
    return conn, out


def mark_seen(conn: imaplib.IMAP4_SSL, uid: bytes) -> None:
    conn.uid("store", uid, "+FLAGS", "(\\Seen)")


def send_email(*, host: str, port: int, user: str, password: str, sender_name: str, to: str,
               subject: str, body: str, in_reply_to: str = "", references: str = "") -> str:
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, user)) if sender_name else user
    msg["To"] = to
    msg["Subject"] = subject
    domain = user.split("@")[-1] if "@" in user else None
    msg_id = make_msgid(domain=domain)
    msg["Message-ID"] = msg_id
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to
    msg.set_content(body)

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls(context=ctx)
            s.login(user, password)
            s.send_message(msg)
    return msg_id


def test_connection(host: str, port: int, user: str, password: str) -> None:
    conn = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context())
    try:
        conn.login(user, password)
    finally:
        try:
            conn.logout()
        except Exception:
            pass
