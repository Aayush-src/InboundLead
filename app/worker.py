"""Inbox processing loop + scheduler."""
from __future__ import annotations

import json
import threading
from datetime import timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session, select

from . import agent, bills, guard, llm, mail
from .db import (Lead, Message, engine, find_lead, get_settings, log, resolved_email,
                 resolved_password, utcnow)

_run_lock = threading.Lock()
scheduler = BackgroundScheduler(daemon=True)
JOB_ID = "inbox-check"


def send_draft(session: Session, draft: Message, subject: str | None = None, body: str | None = None) -> None:
    """Send a stored draft and convert it to an outbound message."""
    st = get_settings(session)
    lead = session.get(Lead, draft.lead_id)
    draft.subject = subject if subject is not None else draft.subject
    draft.body = body if body is not None else draft.body
    msg_id = mail.send_email(
        host=st.smtp_host, port=st.smtp_port, user=resolved_email(st), password=resolved_password(st),
        sender_name=st.sender_name, to=lead.email, subject=draft.subject, body=draft.body,
        in_reply_to=draft.in_reply_to, references=draft.references,
    )
    draft.direction = "outbound"
    draft.message_id = msg_id
    draft.created_at = utcnow()
    lead.last_message_sent = draft.body
    lead.last_contacted_at = utcnow()
    if lead.status == "New":
        lead.status = "Contacted"
    lead.updated_at = utcnow()
    session.add_all([draft, lead])
    session.commit()
    what = {"outreach": "first email", "followup": "follow-up", "custom": "email"}.get(draft.kind, "reply")
    log(f"Sent {what} to {lead.email}: {draft.subject}")


# ---------- outbound: first emails, follow-ups, custom emails ----------
STOP_FOLLOWUP = {"Won", "Lost", "Not Interested", "Meeting Scheduled"}
MAX_COMPOSE_PER_RUN = 25  # bounds model cost per scheduled run


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def thread_of(session: Session, lead: Lead) -> list[Message]:
    return session.exec(select(Message).where(Message.lead_id == lead.id,
                                              Message.direction.in_(["inbound", "outbound"]))
                        .order_by(Message.created_at)).all()


def has_pending_draft(session: Session, lead: Lead) -> bool:
    return session.exec(select(Message.id).where(Message.lead_id == lead.id,
                                                 Message.direction == "draft")).first() is not None


def followups_since_reply(history: list[Message]) -> int:
    n = 0
    for m in reversed(history):
        if m.direction == "inbound":
            break
        if m.kind == "followup":
            n += 1
    return n


def _thread_headers(history: list[Message]) -> tuple[str, str, str]:
    """(subject, in_reply_to, references) to continue the latest thread, or blanks for a new one."""
    last = next((m for m in reversed(history) if m.message_id), None)
    if last is None:
        return "", "", ""
    refs: list[str] = []
    for token in f"{last.references} {last.message_id}".split():
        if token not in refs:
            refs.append(token)
    subj = last.subject or ""
    if subj and not subj.lower().startswith("re:"):
        subj = f"Re: {subj}"
    return subj, last.message_id, " ".join(refs[-20:])


def compose_draft(session: Session, lead: Lead, kind: str, instructions: str = "",
                  in_thread: bool = True, auto: bool = False) -> Message:
    """Have the agent write an outbound email for a lead and store it as a draft.

    kind: outreach (first email) | followup (same thread, no reply yet) | custom (instructions decide).
    Drafts are sent straight away only when `auto` is set and auto-send is on.
    """
    st = get_settings(session)
    history = thread_of(session, lead)
    n = followups_since_reply(history) + 1 if kind == "followup" else 0
    email_ = agent.compose_email(st, lead, history, kind, instructions, followup_n=max(n, 1))

    subject, in_reply_to, references = ("", "", "")
    if kind != "outreach" and in_thread:
        subject, in_reply_to, references = _thread_headers(history)
    label = {"outreach": "First email", "followup": f"Follow-up #{n}", "custom": "Custom email"}[kind]
    draft = Message(lead_id=lead.id, direction="draft", kind=kind,
                    subject=subject or email_.subject.strip() or f"Following up, {lead.name or lead.email}",
                    body=email_.body.strip(), in_reply_to=in_reply_to, references=references,
                    analysis_json=json.dumps({"intent": label, "summary": email_.angle,
                                              "instructions": instructions.strip()}))
    session.add(draft)
    session.commit()
    session.refresh(draft)
    if auto and st.auto_send:
        send_draft(session, draft)
    else:
        log(f"{label} drafted for {lead.email}: {draft.subject}")
    return draft


def _followup_due(st, lead: Lead, history: list[Message]) -> str | None:
    """Which email this lead is due, if any: 'outreach', 'followup' or None."""
    if lead.status in STOP_FOLLOWUP:
        return None
    now = utcnow()
    wait = timedelta(days=max(1, st.followup_after_days))
    if not history:
        if lead.last_message_sent and lead.last_contacted_at:  # emailed outside the app (imported sheet)
            if st.followup_enabled and followups_since_reply(history) < st.followup_max \
                    and now - _aware(lead.last_contacted_at) >= wait:
                return "followup"
            return None
        if st.auto_outreach and lead.status == "New" and not lead.last_message_sent:
            return "outreach"
        return None
    last = history[-1]
    if last.direction != "outbound" or not st.followup_enabled:
        return None  # their move is handled by the inbox check
    if followups_since_reply(history) >= st.followup_max:
        return None
    return "followup" if now - _aware(last.created_at) >= wait else None


def run_followups(session: Session) -> dict[str, int]:
    """Draft (or send, with auto-send) first emails and follow-ups that are due."""
    st = get_settings(session)
    counts = {"outreach": 0, "followup": 0, "error": 0}
    if not (st.followup_enabled or st.auto_outreach):
        return counts
    done = 0
    for lead in session.exec(select(Lead).order_by(Lead.updated_at)).all():
        if done >= MAX_COMPOSE_PER_RUN:
            break
        if has_pending_draft(session, lead):
            continue
        kind = _followup_due(st, lead, thread_of(session, lead))
        if not kind:
            continue
        try:
            compose_draft(session, lead, kind, auto=True)
            counts[kind] += 1
        except llm.LLMConfigError as e:
            log(f"Model not configured: {e}", "error")
            counts["error"] += 1
            break
        except Exception as e:
            session.rollback()
            counts["error"] += 1
            log(f"Could not write {kind} for {lead.email}: {e!r}", "error")
        done += 1
    return counts


def _process_one(session: Session, st, em: mail.IncomingEmail, own_email: str) -> str:
    if em.from_email == own_email.lower():
        return "skip-self"
    # Pre-LLM check: non-allow-listed senders never reach the model (mail is left unread)
    if not guard.is_allowed(st, em.from_email):
        return "blocked"
    if em.message_id and session.exec(select(Message).where(Message.message_id == em.message_id)).first():
        return "skip-duplicate"

    # 1) bills / invoices / receipts (runs even for no-reply & automated senders)
    bill_seen = bills.already_recorded(session, em.message_id)
    bill_new = False
    if st.bill_tracking and not bill_seen and bills.looks_financial(em):
        x = bills.extract(st, agent.llm_config(st), em)
        if x.is_financial_document:
            bills.record(session, st, em, x)
            bill_new = True

    # 2) sales / lead handling
    result = _process_lead(session, st, em)
    if result.startswith("skip"):
        if bill_new:
            return "bill"
        if bill_seen:
            return "skip-duplicate"
    return result


def _process_lead(session: Session, st, em: mail.IncomingEmail) -> str:
    lead = find_lead(session, em.from_email)
    if lead is None and (em.is_bulk or not st.accept_new_leads):
        return "skip-unknown"
    if em.is_bulk and lead is None:
        return "skip-bulk"

    history = []
    if lead:
        history = session.exec(select(Message).where(Message.lead_id == lead.id,
                                                     Message.direction.in_(["inbound", "outbound"]))
                               .order_by(Message.created_at)).all()

    full_body = f"{em.body}\n\n{em.attachment_text()}".strip()
    decision = agent.analyse_email(st, lead, history, em.from_email, em.subject, full_body)

    if lead is None:
        if not decision.is_sales_relevant:
            return "skip-irrelevant"
        lead = Lead(email=em.from_email, name=decision.lead_name or em.from_name,
                    company=decision.lead_company, status="New")
        session.add(lead)
        session.commit()
        session.refresh(lead)
        log(f"New inbound lead: {lead.email}")

    session.add(Message(lead_id=lead.id, direction="inbound", subject=em.subject, body=em.body,
                        message_id=em.message_id, references=em.references,
                        analysis_json=decision.model_dump_json()))
    # They replied, so any unsent follow-up / first email is now out of date
    for stale in session.exec(select(Message).where(Message.lead_id == lead.id, Message.direction == "draft",
                                                    Message.kind.in_(["followup", "outreach"]))).all():
        stale.direction = "discarded"
        session.add(stale)
    lead.last_message_received = em.body[:2000]
    lead.last_reply_at = utcnow()
    if decision.is_sales_relevant:
        lead.status = decision.new_status
        lead.sentiment = decision.sentiment
        lead.summary = decision.summary
        lead.next_action = decision.next_action
        lead.name = lead.name or decision.lead_name or em.from_name
        lead.company = lead.company or decision.lead_company
        if decision.meeting_details:
            lead.meeting_details = decision.meeting_details
    lead.updated_at = utcnow()
    session.add(lead)
    session.commit()

    if not (decision.is_sales_relevant and decision.should_reply and decision.reply_body.strip()):
        return "analysed"

    subject = decision.reply_subject or (em.subject if em.subject.lower().startswith("re:") else f"Re: {em.subject}")
    draft = Message(lead_id=lead.id, direction="draft", subject=subject, body=decision.reply_body,
                    in_reply_to=em.message_id, references=em.references,
                    analysis_json=decision.model_dump_json())
    session.add(draft)
    session.commit()
    session.refresh(draft)
    if st.auto_send:
        send_draft(session, draft)
        return "replied"
    log(f"Draft ready for approval: {lead.email} — {subject}")
    return "drafted"


def check_inbox() -> str:
    if not _run_lock.acquire(blocking=False):
        return "A check is already running."
    try:
        with Session(engine) as session:
            st = get_settings(session)
            if st.bill_tracking:
                bills.mark_overdue(session)
            user, pwd = resolved_email(st), resolved_password(st)
            if not user or not pwd:
                return "Email address / app password not configured."
            try:
                # Also pick up replies from known leads that were already opened (e.g. on a phone).
                # Blocked leads are left out so their mail is never pulled in again.
                read_from = {e for e in session.exec(select(Lead.email)).all()
                             if e and guard.is_allowed(st, e)}
                skip_ids = {m for m in session.exec(select(Message.message_id)
                                                    .where(Message.message_id != "")).all() if m}
                conn, emails = mail.fetch_unread(st.imap_host, st.imap_port, user, pwd, st.lookback_days,
                                                 read_from=read_from, skip_ids=skip_ids)
            except Exception as e:
                log(f"IMAP error: {e}", "error")
                return f"IMAP error: {e}"

            counts: dict[str, int] = {}
            try:
                for em in emails:
                    try:
                        result = _process_one(session, st, em, user)
                    except guard.SenderBlocked as e:  # second line of defence
                        session.rollback()
                        result = "blocked"
                        log(f"Blocked before AI: {e}", "warn")
                    except agent.AgentRefused as e:
                        result = "refused"
                        log(f"Agent declined email from {em.from_email}: {e}", "warn")
                    except llm.LLMConfigError as e:
                        log(f"Model not configured: {e}", "error")
                        counts["error"] = counts.get("error", 0) + 1
                        break  # every email would fail the same way
                    except Exception as e:
                        session.rollback()
                        result = "error"
                        log(f"Failed processing {em.from_email}: {e!r}", "error")
                    counts[result] = counts.get(result, 0) + 1
                    # Leave unrelated / failed mail unread so you still see it (and errors get retried).
                    if result in ("analysed", "drafted", "replied", "bill", "skip-duplicate"):
                        mail.mark_seen(conn, em.uid)
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass

            summary = f"{len(emails)} emails checked — " + (", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "nothing to do")
            fu = run_followups(session)
            if fu["outreach"] or fu["followup"] or fu["error"]:
                summary += (f" · wrote {fu['outreach']} first email(s), {fu['followup']} follow-up(s)"
                            + (f", {fu['error']} failed" if fu["error"] else ""))
            st = get_settings(session)
            st.last_run_at = utcnow()
            st.last_run_summary = summary
            session.add(st)
            session.commit()
            log(summary)
            return summary
    finally:
        _run_lock.release()


def apply_schedule() -> None:
    with Session(engine) as session:
        st = get_settings(session)
        enabled, minutes = st.scheduler_enabled, max(1, st.check_interval_minutes)
    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)
    if enabled:
        scheduler.add_job(check_inbox, "interval", minutes=minutes, id=JOB_ID,
                          max_instances=1, coalesce=True)
        log(f"Scheduler on: checking inbox every {minutes} min")


def next_run_time():
    job = scheduler.get_job(JOB_ID)
    return job.next_run_time if job else None
