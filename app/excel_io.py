"""Excel / CSV import and export for leads."""
from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone

import pandas as pd
from sqlmodel import Session, select

from .db import Lead, find_lead, utcnow

# normalized header -> Lead field
ALIASES = {
    "email": "email", "emailaddress": "email", "mail": "email", "emailid": "email", "contactemail": "email",
    "name": "name", "fullname": "name", "contactname": "name", "leadname": "name", "firstname": "name",
    "company": "company", "companyname": "company", "organization": "company", "organisation": "company",
    "business": "company", "account": "company",
    "status": "status", "leadstatus": "status", "stage": "status",
    "lastmessagesent": "last_message_sent", "lastmessage": "last_message_sent", "lastemail": "last_message_sent",
    "lastemailsent": "last_message_sent", "lastmessageset": "last_message_sent", "lastsent": "last_message_sent",
    "lastmessagereceived": "last_message_received", "lastreply": "last_message_received",
    "meetingdetails": "meeting_details", "meeting": "meeting_details", "meetinginfo": "meeting_details",
    "meetingtime": "meeting_details", "meetingdate": "meeting_details",
    "notes": "notes", "note": "notes", "comments": "notes", "remarks": "notes",
    "summary": "summary", "nextaction": "next_action", "nextstep": "next_action",
    "lastcontacted": "last_contacted_at", "lastcontactedat": "last_contacted_at", "lastcontact": "last_contacted_at",
}
EXPORT_COLUMNS = [
    ("Email", "email"), ("Name", "name"), ("Company", "company"), ("Lead Status", "status"),
    ("Last Message Sent", "last_message_sent"), ("Last Message Received", "last_message_received"),
    ("Last Contacted", "last_contacted_at"), ("Last Reply", "last_reply_at"),
    ("Meeting Details", "meeting_details"), ("Sentiment", "sentiment"), ("AI Summary", "summary"),
    ("Next Action", "next_action"), ("Notes", "notes"),
]
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(h).lower())


def _clean(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
        return ""
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.strftime("%Y-%m-%d %H:%M")
    return str(v).strip()


def import_leads(session: Session, filename: str, content: bytes) -> dict:
    if filename.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    else:
        df = pd.read_excel(io.BytesIO(content))

    mapping: dict[str, str] = {}
    for col in df.columns:
        field = ALIASES.get(_norm(col))
        if field and field not in mapping.values():
            mapping[col] = field
    if "email" not in mapping.values():
        raise ValueError(f"No email column found. Columns seen: {list(df.columns)}")

    created = updated = skipped = 0
    for _, row in df.iterrows():
        data = {field: _clean(row[col]) for col, field in mapping.items()}
        extra = {str(c): _clean(row[c]) for c in df.columns if c not in mapping}
        email = data.pop("email", "").lower()
        m = EMAIL_RE.search(email)
        if not m:
            skipped += 1
            continue
        email = m.group(0)

        lc = data.pop("last_contacted_at", "")
        lead = find_lead(session, email)
        if lead is None:
            lead = Lead(email=email)
            created += 1
        else:
            updated += 1
        for k, v in data.items():
            if v:
                setattr(lead, k, v)
        if lc:
            try:
                ts = pd.to_datetime(lc)
                lead.last_contacted_at = (ts.tz_localize("UTC") if ts.tzinfo is None else ts).to_pydatetime()
            except (ValueError, TypeError):
                pass
        merged = {**lead.extra, **{k: v for k, v in extra.items() if v}}
        lead.extra_json = json.dumps(merged)
        lead.updated_at = utcnow()
        session.add(lead)
    session.commit()
    return {"created": created, "updated": updated, "skipped": skipped,
            "mapped_columns": {str(k): v for k, v in mapping.items()}}


def export_leads(session: Session) -> bytes:
    leads = session.exec(select(Lead).order_by(Lead.updated_at.desc())).all()
    extra_keys: list[str] = []
    for l in leads:
        for k in l.extra:
            if k not in extra_keys:
                extra_keys.append(k)
    rows = []
    for l in leads:
        row = {}
        for label, attr in EXPORT_COLUMNS:
            v = getattr(l, attr)
            row[label] = v.astimezone().strftime("%Y-%m-%d %H:%M") if isinstance(v, datetime) else v
        for k in extra_keys:
            row[k] = l.extra.get(k, "")
        rows.append(row)
    df = pd.DataFrame(rows, columns=[c for c, _ in EXPORT_COLUMNS] + extra_keys)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name="Leads")
        ws = xw.sheets["Leads"]
        ws.freeze_panes = "A2"
        for col in ws.columns:
            width = max(len(str(c.value or "")) for c in col[:200])
            ws.column_dimensions[col[0].column_letter].width = min(max(12, width + 2), 60)
    return buf.getvalue()
