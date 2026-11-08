"""Vendor confirmation emails for bills: "we received / processed / paid your invoice"."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from . import llm, mail
from .db import Bill, BillNotice, Settings, log, resolved_email, resolved_password, utcnow

NOREPLY = re.compile(r"no-?reply|do-?not-?reply|donotreply|mailer-daemon|notifications?@|bounce", re.I)

# Statuses a confirmation makes sense for, and what each one tells the vendor.
MEANING = {
    "Received": "we have received their invoice/bill and it is in our accounts queue for review",
    "Processed": "their invoice has been reviewed and approved, and is scheduled for payment",
    "Paid": "we have made the payment for this invoice",
    "Disputed": "we have a query about this invoice and will be in touch with details",
    "Cancelled": "we have recorded this invoice as cancelled/void on our side",
}
ACKABLE = list(MEANING)


class AckEmail(BaseModel):
    subject: str = Field(description="Email subject. Keep 'Re: <original subject>' threading if an original subject is given.")
    body: str = Field(description="Plain-text email body including greeting and sign-off.")


def _facts(bill: Bill) -> str:
    amt = f"{bill.currency} {bill.amount:,.2f}".strip() if bill.amount else "(not recorded)"
    return (f"vendor: {bill.vendor}\ninvoice number: {bill.invoice_number or '(none)'}\n"
            f"description: {bill.description}\namount: {amt}\nissue date: {bill.issue_date}\n"
            f"due date: {bill.due_date}\noriginal email subject: {bill.source_subject}")


def _subject(bill: Bill) -> str:
    s = bill.source_subject or f"Invoice {bill.invoice_number}".strip()
    return s if s.lower().startswith("re:") else f"Re: {s}"


def _template(st: Settings, bill: Bill, status: str) -> AckEmail:
    ref = f"invoice {bill.invoice_number}" if bill.invoice_number else "your recent invoice"
    amt = f" for {bill.currency} {bill.amount:,.2f}".replace("  ", " ") if bill.amount else ""
    lines = {
        "Received": f"Thank you, we have received {ref}{amt} and it is now with our accounts team for review.",
        "Processed": f"Just to let you know, {ref}{amt} has been approved and is scheduled for payment.",
        "Paid": f"We have made the payment for {ref}{amt}. Please allow a few days for it to reach your account.",
        "Disputed": f"We have a query about {ref}{amt} and will be in touch shortly with the details.",
        "Cancelled": f"We have recorded {ref} as cancelled on our side.",
    }
    sign = st.signature or st.sender_name or st.company_name or ""
    return AckEmail(subject=_subject(bill), body=f"Hello,\n\n{lines[status]}\n\nBest regards,\n{sign}".strip())


def _compose(st: Settings, bill: Bill, status: str) -> AckEmail:
    system = f"""You write short accounts-payable confirmation emails on behalf of {st.company_name or 'our company'}.
Tone: {st.tone or 'polite, brief, professional'}.
State only the facts you are given. Never promise payment dates, amounts or terms that are not in the facts.
No markdown, no placeholders like [Name]. 2-4 sentences plus greeting and sign-off.
Sign off with exactly this signature:
{st.signature or st.sender_name or st.company_name or ''}"""
    user = (f"<bill>\n{_facts(bill)}\n</bill>\n\n"
            f"Write an email telling the vendor that {MEANING[status]}. Subject should be: {_subject(bill)}")
    from .agent import llm_config  # local import to avoid a cycle
    from . import guard
    if not guard.is_allowed(st, bill.sender_email):  # bill details stay out of the model
        return _template(st, bill, status)
    try:
        return llm.generate_structured(llm_config(st), system, user, AckEmail)
    except Exception as e:  # model down / not configured: still send something sensible
        log(f"Confirmation for {bill.vendor} used the template ({type(e).__name__}: {e})", "warn")
        return _template(st, bill, status)


def recipient(bill: Bill) -> str:
    for addr in (bill.reply_to_email, bill.sender_email):
        if addr and not NOREPLY.search(addr):
            return addr
    return ""


def create(session: Session, st: Settings, bill: Bill, status: str, *, manual: bool = False) -> BillNotice | None:
    """Create (and maybe auto-send) a confirmation. Returns None when one isn't appropriate."""
    if status not in ACKABLE:
        return None
    if not manual:
        wanted = {s.strip() for s in st.bill_ack_statuses.split(",") if s.strip()}
        if not st.bill_ack_enabled or status not in wanted:
            return None
    existing = session.exec(select(BillNotice).where(
        BillNotice.bill_id == bill.id, BillNotice.for_status == status,
        BillNotice.state.in_(["draft", "sent"]))).first()
    if existing and (existing.state == "draft" or not manual):
        return existing if manual else None  # never auto-send the same confirmation twice
    to = recipient(bill)
    if not to:
        msg = "No confirmation sent: vendor only uses a no-reply address"
        if not any(h.get("note") == msg for h in bill.history):
            bill.add_note(msg)
            session.add(bill)
            session.commit()
        return None

    email_ = _compose(st, bill, status)
    first_msg_id = (bill.message_ids.split() or [""])[0]
    notice = BillNotice(bill_id=bill.id, for_status=status, to_email=to, subject=email_.subject,
                        body=email_.body, in_reply_to=first_msg_id)
    session.add(notice)
    session.commit()
    session.refresh(notice)
    if st.bill_ack_auto_send and not manual:
        try:
            send(session, notice)
        except Exception as e:  # keep it as a draft so it can be retried from Approvals
            session.rollback()
            log(f"Could not send confirmation to {to}: {e}; left in Approvals", "error")
    else:
        log(f"Confirmation drafted for {bill.vendor} ({status}), waiting in Approvals")
    return notice


def send(session: Session, notice: BillNotice, subject: str | None = None, body: str | None = None) -> None:
    st = session.get(Settings, 1)
    bill = session.get(Bill, notice.bill_id)
    if subject is not None:
        notice.subject = subject
    if body is not None:
        notice.body = body
    notice.message_id = mail.send_email(
        host=st.smtp_host, port=st.smtp_port, user=resolved_email(st), password=resolved_password(st),
        sender_name=st.sender_name, to=notice.to_email, subject=notice.subject, body=notice.body,
        in_reply_to=notice.in_reply_to, references=notice.in_reply_to,
    )
    notice.state = "sent"
    notice.sent_at = utcnow()
    bill.add_note(f"Confirmation sent to {notice.to_email} ({notice.for_status})")
    session.add_all([notice, bill])
    session.commit()
    log(f"Sent {notice.for_status} confirmation to {notice.to_email}")
