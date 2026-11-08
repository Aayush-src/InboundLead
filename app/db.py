"""Database models and session helpers (SQLite via SQLModel)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'leads.db'}")

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


LEAD_STATUSES = [
    "New",
    "Contacted",
    "Engaged",
    "Meeting Scheduled",
    "Proposal Sent",
    "Negotiating",
    "Won",
    "Lost",
    "Not Interested",
    "Nurture",
]


class Settings(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)

    # Mailbox (app password)
    email_address: str = ""
    app_password: str = ""  # falls back to EMAIL_APP_PASSWORD / PASSWORD in .env
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    sender_name: str = ""

    # Agent persona / company context
    agent_role: str = "Sales Development Representative"
    company_name: str = ""
    company_context: str = ""  # what we sell, pricing, ICP, differentiators, FAQs
    goal: str = "Qualify the lead and book a discovery call."
    tone: str = "Warm, concise, professional"
    meeting_link: str = ""
    signature: str = ""

    # Automation
    check_interval_minutes: int = 60
    scheduler_enabled: bool = False
    auto_send: bool = False  # False = drafts wait for approval in the UI
    accept_new_leads: bool = True  # treat unknown senders as new inbound leads
    lookback_days: int = 3

    # Outbound writing: first emails + follow-ups in the same thread when a lead goes quiet
    followup_enabled: bool = False  # draft follow-ups automatically on each scheduled run
    followup_after_days: int = 3  # days of silence after our last email before following up
    followup_max: int = 3  # follow-ups per silence (resets when the lead replies)
    auto_outreach: bool = False  # draft a first email for "New" leads we have never emailed

    # Pre-LLM check: when enabled, only these senders' emails are ever sent to the model
    llm_allowlist_enabled: bool = False
    llm_allowlist: str = ""  # emails or @domains, comma/newline separated

    bill_tracking: bool = True  # detect invoices / bills / receipts in incoming mail
    bill_ack_enabled: bool = False  # email the vendor when a bill reaches one of bill_ack_statuses
    bill_ack_statuses: str = "Received,Processed,Paid"
    bill_ack_auto_send: bool = False  # False = confirmations wait in Approvals

    # LLM provider (see app/llm.py PROVIDERS)
    llm_provider: str = "anthropic"
    llm_model: str = ""  # blank = provider default
    llm_base_url: str = ""  # blank = provider default
    llm_api_key: str = ""  # blank = provider's env var

    last_run_at: Optional[datetime] = None
    last_run_summary: str = ""


class Lead(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str = ""
    company: str = ""
    status: str = "New"
    last_message_sent: str = ""
    last_message_received: str = ""
    last_contacted_at: Optional[datetime] = None
    last_reply_at: Optional[datetime] = None
    meeting_details: str = ""
    summary: str = ""
    next_action: str = ""
    sentiment: str = ""
    notes: str = ""
    extra_json: str = "{}"  # any extra Excel columns, preserved on export
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def extra(self) -> dict:
        try:
            return json.loads(self.extra_json or "{}")
        except json.JSONDecodeError:
            return {}


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: int = Field(index=True, foreign_key="lead.id")
    direction: str  # "inbound" | "outbound" | "draft" | "discarded"
    kind: str = "reply"  # reply | outreach | followup | custom
    subject: str = ""
    body: str = ""
    message_id: str = Field(default="", index=True)  # RFC822 Message-ID
    in_reply_to: str = ""
    references: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    analysis_json: str = ""  # agent analysis for the inbound mail that triggered this draft


BILL_STATUSES = ["Received", "Processed", "Paid", "Overdue", "Disputed", "Cancelled"]
BILL_DOC_TYPES = ["invoice", "bill", "receipt", "payment_confirmation", "payment_reminder",
                  "statement", "credit_note", "purchase_order", "other"]


class Bill(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    vendor: str = ""
    sender_email: str = Field(default="", index=True)
    reply_to_email: str = ""  # vendor's Reply-To, preferred for confirmations
    invoice_number: str = Field(default="", index=True)
    document_type: str = "invoice"
    description: str = ""
    amount: Optional[float] = None
    currency: str = ""
    issue_date: str = ""  # YYYY-MM-DD as written on the document
    due_date: str = ""
    status: str = "Received"
    summary: str = ""
    notes: str = ""
    source_subject: str = ""
    message_ids: str = ""  # space-separated Message-IDs of every email about this bill
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    history_json: str = "[]"  # [{at, status, note}]
    received_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def history(self) -> list:
        try:
            return json.loads(self.history_json or "[]")
        except json.JSONDecodeError:
            return []

    def set_status(self, status: str, note: str = "") -> None:
        if status == self.status and self.history:
            return
        h = self.history
        h.append({"at": utcnow().isoformat(), "status": status, "note": note})
        self.history_json = json.dumps(h)
        self.status = status
        self.updated_at = utcnow()

    def add_note(self, note: str) -> None:
        h = self.history
        h.append({"at": utcnow().isoformat(), "status": self.status, "note": note})
        self.history_json = json.dumps(h)
        self.updated_at = utcnow()


class BillNotice(SQLModel, table=True):
    """A confirmation email to a vendor about one of their bills."""
    id: Optional[int] = Field(default=None, primary_key=True)
    bill_id: int = Field(index=True, foreign_key="bill.id")
    for_status: str  # the bill status this confirms (Received / Processed / Paid …)
    to_email: str
    subject: str = ""
    body: str = ""
    state: str = "draft"  # draft | sent | discarded
    in_reply_to: str = ""
    message_id: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    sent_at: Optional[datetime] = None


class ActivityLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow)
    level: str = "info"
    message: str = ""


def _add_missing_columns() -> None:
    """Tiny auto-migration: add columns introduced after a table was first created."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                ddl_type = col.type.compile(dialect=engine.dialect)
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                if isinstance(default, bool):
                    default = int(default)
                dflt = f" DEFAULT {default!r}" if default is not None else ""
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl_type}{dflt}'))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()
    with Session(engine) as s:
        if not s.get(Settings, 1):
            s.add(Settings(id=1))
            s.commit()


def get_settings(session: Session) -> Settings:
    st = session.get(Settings, 1)
    if st is None:
        st = Settings(id=1)
        session.add(st)
        session.commit()
        session.refresh(st)
    return st


def log(message: str, level: str = "info") -> None:
    with Session(engine) as s:
        s.add(ActivityLog(message=message, level=level))
        s.commit()
    try:
        print(f"[{level}] {message}")
    except UnicodeEncodeError:  # Windows consoles with a legacy code page
        print(f"[{level}] {message}".encode("ascii", "replace").decode())


def resolved_password(st: Settings) -> str:
    return st.app_password or os.getenv("EMAIL_APP_PASSWORD") or os.getenv("PASSWORD", "")


def resolved_email(st: Settings) -> str:
    return st.email_address or os.getenv("EMAIL_ADDRESS", "")


def find_lead(session: Session, email: str) -> Optional[Lead]:
    return session.exec(select(Lead).where(Lead.email == email.strip().lower())).first()
