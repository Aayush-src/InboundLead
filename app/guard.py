"""Pre-LLM sender check: only allow-listed addresses may have their email content sent to the model.

The check runs in two places:
  1. worker._process_one, before anything else: blocked mail is skipped and left unread.
  2. Inside every function that builds a model prompt from an email (agent.analyse_email,
     bills.extract, notices._compose) as a second line of defence, so a new code path
     can't accidentally bypass it.

Writing TO a lead is never blocked: agent.compose_email just leaves the lead's own emails
out of the prompt when they aren't allow-listed.
"""
from __future__ import annotations

import re

from .db import Settings


class SenderBlocked(Exception):
    """Raised when an email from a non-allow-listed address would be sent to the model."""


def parse(raw: str) -> list[str]:
    return [x.strip().lower() for x in re.split(r"[,\s;]+", raw or "") if x.strip()]


def is_allowed(st: Settings, address: str) -> bool:
    if not st.llm_allowlist_enabled:
        return True
    addr = (address or "").strip().lower()
    if not addr:
        return False
    for entry in parse(st.llm_allowlist):
        if entry.startswith("@"):
            if addr.endswith(entry):
                return True
        elif addr == entry:
            return True
    return False


def check(st: Settings, address: str) -> None:
    if not is_allowed(st, address):
        raise SenderBlocked(f"{address or '(unknown sender)'} is not on the AI allow-list")
