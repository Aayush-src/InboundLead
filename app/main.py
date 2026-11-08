"""FastAPI app: REST API + static UI."""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# override=True: this project's .env wins over same-named Windows/user environment variables
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.responses import FileResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlmodel import Session, func, select  # noqa: E402

from . import agent, bills, guard, llm, mail, notices, worker  # noqa: E402
from .db import (BILL_STATUSES, LEAD_STATUSES, ActivityLog, Bill, BillNotice, Lead, log, Message, engine, find_lead, get_settings, init_db,  # noqa: E402
                 resolved_email, resolved_password, utcnow)
from .excel_io import export_leads, import_leads  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    worker.scheduler.start()
    worker.apply_schedule()
    yield
    worker.scheduler.shutdown(wait=False)


app = FastAPI(title="Inbound Lead Agent", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def db():
    with Session(engine) as s:
        yield s


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


# ---------- settings ----------
class SettingsIn(BaseModel):
    email_address: str = ""
    app_password: Optional[str] = None  # None/"" = keep existing
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    sender_name: str = ""
    agent_role: str = ""
    company_name: str = ""
    company_context: str = ""
    goal: str = ""
    tone: str = ""
    meeting_link: str = ""
    signature: str = ""
    check_interval_minutes: int = 60
    scheduler_enabled: bool = False
    auto_send: bool = False
    accept_new_leads: bool = True
    lookback_days: int = 3
    followup_enabled: bool = False
    followup_after_days: int = 3
    followup_max: int = 3
    auto_outreach: bool = False
    llm_allowlist_enabled: bool = False
    llm_allowlist: str = ""
    bill_tracking: bool = True
    bill_ack_enabled: bool = False
    bill_ack_statuses: str = "Received,Processed,Paid"
    bill_ack_auto_send: bool = False
    llm_provider: str = "anthropic"
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: Optional[str] = None  # None/"" = keep existing
    clear_llm_api_key: bool = False


def _settings_out(st) -> dict:
    d = st.model_dump()
    d.pop("app_password")
    d["has_llm_key"] = bool(d.pop("llm_api_key"))
    d["email_address"] = d["email_address"] or resolved_email(st)
    d["has_password"] = bool(resolved_password(st))
    d["next_run_at"] = worker.next_run_time()
    return d


@app.get("/api/settings")
def read_settings(s: Session = Depends(db)):
    return _settings_out(get_settings(s))


@app.put("/api/settings")
def save_settings(body: SettingsIn, s: Session = Depends(db)):
    st = get_settings(s)
    data = body.model_dump()
    pwd = data.pop("app_password")
    if pwd:
        st.app_password = pwd.replace(" ", "")
    key = data.pop("llm_api_key")
    if data.pop("clear_llm_api_key"):
        st.llm_api_key = ""
    elif key:
        st.llm_api_key = key.strip()
    if data["llm_provider"] not in llm.PROVIDERS:
        raise HTTPException(400, f"Unknown provider {data['llm_provider']}")
    data["check_interval_minutes"] = max(1, data["check_interval_minutes"])
    data["followup_after_days"] = min(60, max(1, data["followup_after_days"]))
    data["followup_max"] = min(10, max(1, data["followup_max"]))
    for k, v in data.items():
        setattr(st, k, v)
    s.add(st)
    s.commit()
    s.refresh(st)
    worker.apply_schedule()
    return _settings_out(st)


@app.post("/api/settings/test")
async def test_mailbox(s: Session = Depends(db)):
    st = get_settings(s)
    try:
        await run_in_threadpool(mail.test_connection, st.imap_host, st.imap_port,
                                resolved_email(st), resolved_password(st))
    except Exception as e:
        raise HTTPException(400, f"Login failed: {e}")
    return {"ok": True}


# ---------- model / provider ----------
@app.get("/api/llm/providers")
def llm_providers():
    return [{"id": k, "label": p.label, "default_model": p.default_model, "base_url": p.base_url,
             "key_env": p.key_env, "needs_key": p.needs_key, "env_key_present": bool(p.key_env and os.getenv(p.key_env))}
            for k, p in llm.PROVIDERS.items()]


@app.post("/api/llm/test")
async def llm_test(s: Session = Depends(db)):
    st = get_settings(s)
    try:
        cfg = agent.llm_config(st)
        name = await run_in_threadpool(llm.test, cfg)
    except Exception as e:
        raise HTTPException(400, f"{type(e).__name__}: {e}")
    return {"ok": True, "provider": cfg.provider, "model": cfg.model, "reply": name}


# ---------- leads ----------
@app.get("/api/leads")
def list_leads(status: Optional[str] = None, q: Optional[str] = None, s: Session = Depends(db)):
    stmt = select(Lead).order_by(Lead.updated_at.desc())
    if status:
        stmt = stmt.where(Lead.status == status)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where((func.lower(Lead.email).like(like)) | (func.lower(Lead.name).like(like))
                          | (func.lower(Lead.company).like(like)))
    leads = s.exec(stmt).all()
    pending = dict(s.exec(select(Message.lead_id, func.count()).where(Message.direction == "draft")
                          .group_by(Message.lead_id)).all())
    return [{**l.model_dump(), "pending_drafts": pending.get(l.id, 0)} for l in leads]


@app.get("/api/stats")
def stats(s: Session = Depends(db)):
    rows = dict(s.exec(select(Lead.status, func.count()).group_by(Lead.status)).all())
    drafts = s.exec(select(func.count()).select_from(Message).where(Message.direction == "draft")).one() \
        + s.exec(select(func.count()).select_from(BillNotice).where(BillNotice.state == "draft")).one()
    return {"total": sum(rows.values()), "by_status": rows, "pending_drafts": drafts, "statuses": LEAD_STATUSES}


class LeadPatch(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    status: Optional[str] = None
    meeting_details: Optional[str] = None
    notes: Optional[str] = None
    next_action: Optional[str] = None


@app.get("/api/leads/{lead_id}")
def lead_detail(lead_id: int, s: Session = Depends(db)):
    lead = s.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404)
    msgs = s.exec(select(Message).where(Message.lead_id == lead_id, Message.direction != "discarded")
                  .order_by(Message.created_at)).all()
    return {"lead": lead.model_dump(), "messages": [m.model_dump() for m in msgs]}


@app.patch("/api/leads/{lead_id}")
def patch_lead(lead_id: int, body: LeadPatch, s: Session = Depends(db)):
    lead = s.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(lead, k, v)
    lead.updated_at = utcnow()
    s.add(lead)
    s.commit()
    return lead.model_dump()


@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: int, s: Session = Depends(db)):
    lead = s.get(Lead, lead_id)
    if lead:
        for m in s.exec(select(Message).where(Message.lead_id == lead_id)).all():
            s.delete(m)
        s.delete(lead)
        s.commit()
    return {"ok": True}


@app.post("/api/leads/import")
async def upload_leads(file: UploadFile = File(...), s: Session = Depends(db)):
    if not file.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(400, "Upload an .xlsx, .xls or .csv file")
    try:
        return import_leads(s, file.filename, await file.read())
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/leads.xlsx")
def download_leads(s: Session = Depends(db)):
    name = f"leads_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return Response(export_leads(s),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- bills ----------
def _bill_out(b: Bill) -> dict:
    return {**b.model_dump(exclude={"history_json"}), "history": b.history}


@app.get("/api/bills")
def list_bills(status: Optional[str] = None, q: Optional[str] = None, s: Session = Depends(db)):
    stmt = select(Bill).order_by(Bill.received_at.desc())
    if status:
        stmt = stmt.where(Bill.status == status)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Bill.vendor).like(like) | func.lower(Bill.invoice_number).like(like)
                          | func.lower(Bill.sender_email).like(like) | func.lower(Bill.description).like(like))
    return [_bill_out(b) for b in s.exec(stmt).all()]


@app.get("/api/bills/stats")
def bill_stats(s: Session = Depends(db)):
    counts = dict(s.exec(select(Bill.status, func.count()).group_by(Bill.status)).all())
    open_totals: dict[str, float] = {}
    for b in s.exec(select(Bill).where(Bill.status.in_(["Received", "Processed", "Overdue", "Disputed"]))).all():
        if b.amount:
            open_totals[b.currency or "?"] = open_totals.get(b.currency or "?", 0) + b.amount
    return {"total": sum(counts.values()), "by_status": counts, "open_totals": open_totals,
            "statuses": BILL_STATUSES}


class BillPatch(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    due_date: Optional[str] = None
    vendor: Optional[str] = None
    invoice_number: Optional[str] = None


@app.patch("/api/bills/{bill_id}")
def patch_bill(bill_id: int, body: BillPatch, s: Session = Depends(db)):
    b = s.get(Bill, bill_id)
    if not b:
        raise HTTPException(404)
    data = body.model_dump(exclude_none=True)
    status = data.pop("status", None)
    if status and status not in BILL_STATUSES:
        raise HTTPException(400, f"Status must be one of {BILL_STATUSES}")
    changed = bool(status) and status != b.status
    if status:
        b.set_status(status, "Changed manually")
    for k, v in data.items():
        setattr(b, k, v)
    b.updated_at = utcnow()
    s.add(b)
    s.commit()
    s.refresh(b)
    if changed:  # e.g. you mark it Processed / Paid → confirm to the vendor (if enabled)
        try:
            notices.create(s, get_settings(s), b, status)
        except Exception as e:
            s.rollback()
            log(f"Confirmation for bill {b.id} failed: {e}", "error")
        s.refresh(b)
    return _bill_out(b)


@app.post("/api/bills/{bill_id}/notice")
def manual_notice(bill_id: int, s: Session = Depends(db)):
    """'Send confirmation' button: drafts a confirmation for the bill's current status."""
    b = s.get(Bill, bill_id)
    if not b:
        raise HTTPException(404)
    if b.status not in notices.ACKABLE:
        raise HTTPException(400, f"No confirmation for status '{b.status}'")
    if not notices.recipient(b):
        raise HTTPException(400, "This vendor only uses a no-reply address")
    n = notices.create(s, get_settings(s), b, b.status, manual=True)
    return n.model_dump()


@app.get("/api/bill-notices")
def list_notices(s: Session = Depends(db)):
    rows = s.exec(select(BillNotice, Bill).join(Bill, Bill.id == BillNotice.bill_id)
                  .where(BillNotice.state == "draft").order_by(BillNotice.created_at.desc())).all()
    return [{**n.model_dump(), "bill": {"id": b.id, "vendor": b.vendor, "invoice_number": b.invoice_number,
                                        "amount": b.amount, "currency": b.currency, "status": b.status}}
            for n, b in rows]


class NoticeEdit(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


@app.post("/api/bill-notices/{notice_id}/send")
async def send_notice(notice_id: int, edit: NoticeEdit, s: Session = Depends(db)):
    n = s.get(BillNotice, notice_id)
    if not n or n.state != "draft":
        raise HTTPException(404, "Draft not found")
    try:
        await run_in_threadpool(notices.send, s, n, edit.subject, edit.body)
    except Exception as e:
        raise HTTPException(500, f"Send failed: {e}")
    return {"ok": True}


@app.post("/api/bill-notices/{notice_id}/discard")
def discard_notice(notice_id: int, s: Session = Depends(db)):
    n = s.get(BillNotice, notice_id)
    if n and n.state == "draft":
        n.state = "discarded"
        s.add(n)
        s.commit()
    return {"ok": True}


@app.delete("/api/bills/{bill_id}")
def delete_bill(bill_id: int, s: Session = Depends(db)):
    b = s.get(Bill, bill_id)
    if b:
        s.delete(b)
        s.commit()
    return {"ok": True}


@app.get("/api/bills.xlsx")
def download_bills(s: Session = Depends(db)):
    name = f"bills_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return Response(bills.export_xlsx(s),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- drafts ----------
@app.get("/api/drafts")
def list_drafts(s: Session = Depends(db)):
    rows = s.exec(select(Message, Lead).join(Lead, Lead.id == Message.lead_id)
                  .where(Message.direction == "draft").order_by(Message.created_at.desc())).all()
    out = []
    for m, l in rows:
        analysis = json.loads(m.analysis_json) if m.analysis_json else {}
        out.append({**m.model_dump(), "lead": {"id": l.id, "email": l.email, "name": l.name,
                                               "company": l.company, "status": l.status},
                    "analysis": analysis})
    return out


class DraftEdit(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


@app.post("/api/drafts/{msg_id}/send")
async def approve_draft(msg_id: int, edit: DraftEdit, s: Session = Depends(db)):
    m = s.get(Message, msg_id)
    if not m or m.direction != "draft":
        raise HTTPException(404, "Draft not found")
    try:
        await run_in_threadpool(worker.send_draft, s, m, edit.subject, edit.body)
    except Exception as e:
        raise HTTPException(500, f"Send failed: {e}")
    return {"ok": True}


@app.post("/api/drafts/{msg_id}/discard")
def discard_draft(msg_id: int, s: Session = Depends(db)):
    m = s.get(Message, msg_id)
    if m and m.direction == "draft":
        m.direction = "discarded"
        s.add(m)
        s.commit()
    return {"ok": True}


# ---------- writing emails ----------
COMPOSE_KINDS = ("auto", "outreach", "followup", "custom")


class ComposeIn(BaseModel):
    lead_id: Optional[int] = None
    email: str = ""  # or: write to an address, adding it as a lead if it's new
    name: str = ""
    company: str = ""
    kind: str = "auto"  # auto = first email if we never wrote to them, else a follow-up
    instructions: str = ""
    in_thread: bool = True  # continue the latest thread (custom emails)


def _compose(s: Session, lead: Lead, kind: str, instructions: str, in_thread: bool) -> Message:
    if kind == "auto":
        kind = "followup" if worker.thread_of(s, lead) or lead.last_message_sent else "outreach"
    if kind == "custom" and not instructions.strip():
        raise HTTPException(400, "Say what the email should be about")
    try:
        return worker.compose_draft(s, lead, kind, instructions, in_thread=in_thread)
    except guard.SenderBlocked as e:
        raise HTTPException(400, f"{e}. Add it to the AI allow-list to write to this lead.")
    except (llm.LLMConfigError, llm.LLMRefused, ValueError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/compose")
async def compose(body: ComposeIn, s: Session = Depends(db)):
    if body.kind not in COMPOSE_KINDS:
        raise HTTPException(400, f"kind must be one of {COMPOSE_KINDS}")
    if body.lead_id:
        lead = s.get(Lead, body.lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
    else:
        addr = body.email.strip().lower()
        if not mail.parseaddr(addr)[1] or "@" not in addr:
            raise HTTPException(400, "Enter a valid email address")
        lead = find_lead(s, addr)
        if lead is None:
            lead = Lead(email=addr, name=body.name.strip(), company=body.company.strip())
            s.add(lead)
            s.commit()
            s.refresh(lead)
            log(f"Lead added for a new email: {addr}")
    draft = await run_in_threadpool(_compose, s, lead, body.kind, body.instructions, body.in_thread)
    return {**draft.model_dump(), "lead_id": lead.id}


class BulkComposeIn(BaseModel):
    status: str = "New"
    instructions: str = ""


@app.post("/api/compose/bulk")
async def compose_bulk(body: BulkComposeIn, s: Session = Depends(db)):
    """First emails for every lead with this status that we have never emailed and has no draft waiting."""
    leads = [l for l in s.exec(select(Lead).where(Lead.status == body.status)).all()
             if not l.last_message_sent and not worker.thread_of(s, l) and not worker.has_pending_draft(s, l)]
    if not leads:
        return {"written": 0, "failed": 0, "skipped_limit": 0}
    st = get_settings(s)
    todo = leads[:worker.MAX_COMPOSE_PER_RUN]
    written = failed = 0
    for lead in todo:
        try:
            await run_in_threadpool(worker.compose_draft, s, lead, "outreach", body.instructions)
            written += 1
        except llm.LLMConfigError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            s.rollback()
            failed += 1
            log(f"Could not write first email for {lead.email}: {e!r}", "error")
    return {"written": written, "failed": failed, "skipped_limit": len(leads) - len(todo)}


@app.post("/api/followups/run")
async def followups_now():
    def go():
        with Session(engine) as s2:
            return worker.run_followups(s2)
    return await run_in_threadpool(go)


@app.put("/api/drafts/{msg_id}")
def save_draft(msg_id: int, edit: DraftEdit, s: Session = Depends(db)):
    m = s.get(Message, msg_id)
    if not m or m.direction != "draft":
        raise HTTPException(404, "Draft not found")
    if edit.subject is not None:
        m.subject = edit.subject
    if edit.body is not None:
        m.body = edit.body
    s.add(m)
    s.commit()
    return m.model_dump()


# ---------- runs ----------
@app.post("/api/run")
async def run_now():
    return {"summary": await run_in_threadpool(worker.check_inbox)}


@app.get("/api/activity")
def activity(s: Session = Depends(db)):
    return s.exec(select(ActivityLog).order_by(ActivityLog.id.desc()).limit(100)).all()
