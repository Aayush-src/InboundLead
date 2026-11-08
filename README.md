# Inbound Lead Agent

An AI sales agent that watches your inbox, reads replies from leads, updates their pipeline status, and writes (or sends) replies with the goal of booking calls and closing deals. It runs on Claude (Opus 5.5).

**Stack:** Python 3.11 · FastAPI · SQLite (SQLModel) · APScheduler · a model layer that works with any provider (Claude, OpenAI, Gemini, local Ollama and others) · IMAP/SMTP with an app password · a single-page web UI with no build step.

## Quick start

New to this? Follow **[guide.md](guide.md)**. It walks through everything step by step, including installing Python and Git, getting a Gmail app password and getting an AI API key.

You need **Python 3.11 or newer** and **Git**. Pick the commands for your system.

### Windows (PowerShell)

```powershell
git clone https://github.com/Aayush-src/InboundLead.git
cd InboundLead
copy .env.example .env                                    # then edit .env: notepad .env
python -m venv .venv                                      # first time only
.\.venv\Scripts\python -m pip install -r requirements.txt  # first time only
python main.py                                            # open http://127.0.0.1:8000
```

If `python` isn't found, try `py` instead (for example `py -m venv .venv` and `py main.py`).

### macOS (Terminal)

```bash
git clone https://github.com/Aayush-src/InboundLead.git
cd InboundLead
cp .env.example .env                                      # then edit .env: open -e .env
python3 -m venv .venv                                     # first time only
.venv/bin/python -m pip install -r requirements.txt       # first time only
python3 main.py                                           # open http://127.0.0.1:8000
```

### Linux (Ubuntu / Debian / Fedora / Arch …)

```bash
# first time only: install Python, venv and Git if you don't have them
sudo apt install python3 python3-venv python3-pip git     # Ubuntu / Debian / Mint
# sudo dnf install python3 python3-pip git                # Fedora / RHEL
# sudo pacman -S python python-pip git                    # Arch / Manjaro

git clone https://github.com/Aayush-src/InboundLead.git
cd InboundLead
cp .env.example .env                                      # then edit .env: nano .env
python3 -m venv .venv                                     # first time only
.venv/bin/python -m pip install -r requirements.txt       # first time only
python3 main.py                                           # open http://127.0.0.1:8000
```

**On every system:**
- In `.env`, fill in `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD` and the API key for **one** AI provider (for example `ANTHROPIC_API_KEY`). You can also enter these in the app instead.
- `python main.py` automatically uses the `.venv`, so you never need to activate it. Developers who prefer to activate it can run `uvicorn main:app --reload` after activating (`.\.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` on macOS/Linux).
- Keep the terminal open while you use the app. Press **Ctrl + C** to stop it.
- To update later, run `git pull`, then run the `pip install` line again.

### First-time setup in the browser

1. **Mailbox & Schedule**: enter your email and app password, click **Save settings**, then **Test login**. Pick how often to check the inbox (every 5 minutes up to once a day) and turn on **Run automatically on this schedule**. Optionally, turn on the **AI privacy check** so only senders you list are ever read by the AI.
2. **Agent**: pick your AI **Provider**, add the API key if it isn't in `.env`, and click **Test model**. Then describe who the agent is acting for: role, company, what you sell, pricing, FAQs, goal, tone, booking link and signature. The agent only states facts you give it here.
3. **Leads**: drop your Excel or CSV file on the page. **Email** is the only required column. Columns like Name, Company, Lead Status, Last Message Sent and Meeting Details are recognised automatically, and any other columns are kept.
4. Click **Check inbox now**, or wait for the schedule. Replies show up in **Approvals** for you to edit and send. To skip review, turn on **Auto-send replies**.
5. **Export to Excel** downloads the updated sheet. It includes the status, last message sent and received, last contacted and reply dates, meeting details, sentiment, the AI summary, the next action, notes, and your original extra columns.

## Writing emails & follow-ups

The agent doesn't only reply. It also writes new emails and follows up in the same thread when a lead goes quiet.

- **One lead:** open a lead and use **Write an email**. Pick *Next email* (a first email, or a follow-up if you've written before), *First email*, *Follow-up in the thread* or *Custom* (the AI follows your instructions). The draft appears in the conversation, where you can edit it, save it, send it or discard it.
- **Anyone:** **New email** on the Leads tab writes to any address. If the address is new, it's added as a lead.
- **In bulk:** **Write first emails to New leads** drafts an intro for every New lead you've never emailed (up to 25 at a time). The drafts wait in **Approvals**.
- **Automatic follow-ups** (Mailbox & Schedule → *Writing & follow-ups*): after *N* days without a reply, each scheduled run drafts a follow-up as a reply in the existing thread (`In-Reply-To`/`References`), so it shows up in the same conversation. You set the maximum number of follow-ups, and the last one politely closes the loop. The count resets when the lead replies, and any unsent follow-up is discarded at that point. Leads that are Won, Lost, Not Interested or have a meeting scheduled are skipped. Leads imported with a *Last Message Sent* and *Last Contacted* date are followed up too.
- **Automatic first emails:** optionally, every New lead you've never emailed gets a first email drafted on the next run.
- Scheduled follow-ups and first emails are sent straight away only if **Auto-send** is on. Emails you write by hand always stay as drafts until you click Send. You can write to any address. If a lead isn't on the AI allow-list, the AI never sees anything they wrote, only your own sent emails and the details you entered.
## Bill & receipt tracking

When **Track bills** is on (in Mailbox & Schedule), each inbox check also looks for invoices, bills, receipts, payment confirmations, reminders, statements, credit notes and purchase orders. It checks these even from no-reply senders, and it reads text inside PDF attachments.

- The AI only looks at emails that contain billing words, so the inbox check doesn't call the model for every newsletter.
- For each bill it records the vendor, invoice number, amount, currency, issue and due dates, and status, with a history of every status change.
- **Statuses:** Received → Processed → Paid, plus Overdue, Disputed and Cancelled.
  - A new invoice starts as **Received**.
  - A later receipt or payment confirmation with the same invoice number from the same sender moves it to **Paid**.
  - A late reminder never moves a Paid bill backwards.
  - Unpaid bills past their due date become **Overdue** automatically.
- In the **Bills** tab you can change a status (for example, mark a bill Processed), fix the amount or due date, add notes, and **Export to Excel**.
- Scanned PDFs that are only images have no text to read. The model then sees just the filename and the email body.

### Vendor confirmations

Turn on **Email vendors a confirmation when a bill is…** and tick the statuses that should trigger one: Received, Processed, Paid, Disputed or Cancelled.

- **When:** a new invoice triggers a "we've received it" email. When you change a bill's status, an email for the new status is written if you ticked that status. If the vendor told *you* the status (their own receipt), nothing is echoed back.
- **Who:** the email goes to the vendor's Reply-To address, or the sender if there isn't one, in the original invoice thread. No-reply addresses are skipped, and the bill's history notes why.
- **Wording:** your selected model writes it using your company name, tone and signature, and it may only state facts from the bill. If the model is unavailable, a plain template is used.
- **Review:** confirmations wait in **Approvals** unless **Auto-send vendor confirmations** is on. An email is never sent twice automatically.
- **Manual:** each bill has a **Send confirmation** button.

## Choosing the AI model

The app isn't tied to one model. Open **Agent → AI model**, pick a provider, and click **Test model**.

| Provider | Key in `.env` | Notes |
|---|---|---|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | The default. Uses the native SDK. |
| OpenAI, Gemini, Groq, OpenRouter, DeepSeek, Mistral | `OPENAI_API_KEY`, `GEMINI_API_KEY`, … | Uses the OpenAI-compatible API. |
| Ollama / LM Studio | none | Runs locally and free. Start the model server first. |
| Custom | `LLM_API_KEY` (optional) | Any OpenAI-compatible URL, such as Azure, Together, vLLM or a proxy. |

Leave **Model** blank to use the provider's default, or type any model name the provider serves. For providers other than Claude, the app asks for strict JSON-schema output first. If the endpoint doesn't support that, it falls back to plain JSON mode and then to prompt-only JSON, and it remembers what worked. Every answer is checked against the schema, and the model gets one chance to fix invalid JSON.
To add a provider, add one line to `PROVIDERS` in `app/llm.py`.

## How it works

- The agent only reads **unread** mail from the last N days, and it fetches with `BODY.PEEK`, so emails it skips stay unread.
- Mail from your own address is ignored. So are newsletters and automated mail (List-Unsubscribe, Auto-Submitted, no-reply). Duplicates are skipped by Message-ID.
- Mail from unknown senders becomes a new lead only if Claude judges it sales-relevant. You can turn this off.
- Replies keep the thread together through `In-Reply-To` and `References`, so they land in the same conversation.
- The app saves the lead status, sentiment, meeting details, summary and next action after every email.

## Gmail app password

Turn on 2-Step Verification, go to https://myaccount.google.com/apppasswords, and create a password. Use `imap.gmail.com:993` and `smtp.gmail.com:465` (the defaults).
For Outlook or Microsoft 365, use `outlook.office365.com:993` and `smtp.office365.com:587`, but note that many tenants have turned off app passwords.
