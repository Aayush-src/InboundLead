# Inbound Lead Agent: Setup Guide

This guide takes you from nothing to a working AI sales assistant that reads your email, keeps track of your leads, and writes replies for you to approve. You don't need any technical background. Follow the steps in order and don't skip any.

**Time needed:** about 30–45 minutes the first time.

**What you'll need:**
- A computer running Windows 10/11, macOS or Linux (Ubuntu, Debian, Fedora, Mint, Arch…)
- A Gmail account (the one your leads email you at)
- A mobile phone (Google uses it to confirm it's you)
- A credit or debit card for the AI service (most charge a few cents per email; one option is free)

---

## Contents
1. [Install Python](#step-1-install-python)
2. [Install Git](#step-2-install-git)
3. [Download the app](#step-3-download-the-app)
4. [Install the app's parts](#step-4-install-the-apps-parts)
5. [Get your Gmail app password](#step-5-get-your-gmail-app-password)
6. [Get an AI key](#step-6-get-an-ai-key)
7. [Put your passwords in the settings file](#step-7-put-your-passwords-in-the-settings-file)
8. [Start the app](#step-8-start-the-app)
9. [Set the app up in your browser](#step-9-set-the-app-up-in-your-browser)
10. [Daily use](#step-10-daily-use)
11. [Stopping and starting again](#step-11-stopping-and-starting-again)
12. [When something goes wrong](#when-something-goes-wrong)
13. [Keeping things safe](#keeping-things-safe)

---

## Before you start: how to open the "terminal"

A few steps ask you to type commands. You type them into a window called the **terminal**.

**Windows**
1. Press the **Windows key** on your keyboard (the one with the Windows logo).
2. Type `powershell`.
3. Click **Windows PowerShell**. A blue or black window opens. That's the terminal.

**Mac**
1. Press **Command (⌘) + Space** to open the search bar.
2. Type `terminal`.
3. Press **Enter**. A white or black window opens. That's the terminal.

**Linux**
1. Press **Ctrl + Alt + T**. On most systems (Ubuntu, Mint, Debian…) the terminal opens straight away.
2. If nothing happens, open your apps menu, search for `terminal` and click it.

**How to run a command:** copy the grey command text from this guide, click inside the terminal, paste it (Windows: right-click; Mac: **⌘ + V**; Linux: **Ctrl + Shift + V**) and press **Enter**.

> **Linux only:** commands starting with `sudo` ask for **your computer's login password**. Nothing appears on screen while you type it, not even dots. That's normal. Type it and press **Enter**. Wait until the terminal stops printing text before you type the next one.

> **Tip:** Lines in this guide that start with `#` are notes for you. You don't type those.

---

## Step 1: Install Python

Python is the language the app is written in. Your computer needs it to run the app.

**Windows**
1. Go to **https://www.python.org/downloads/**.
2. Click the big yellow **Download Python 3.x** button (any version 3.11 or newer is fine).
3. Open the downloaded file.
4. ⚠️ **Important:** at the bottom of the first screen, **tick the box "Add python.exe to PATH"**. If you miss this, nothing later will work.
5. Click **Install Now** and wait for it to finish, then click **Close**.

**Mac**
1. Go to **https://www.python.org/downloads/**.
2. Click **Download Python 3.x** (3.11 or newer).
3. Open the downloaded file and click **Continue** / **Agree** / **Install** until it's done.

**Linux**

Most Linux systems already have Python. Install it (plus the extra pieces the app needs) with the line for your system:

```
# Ubuntu / Debian / Mint / Pop!_OS
sudo apt update && sudo apt install -y python3 python3-venv python3-pip

# Fedora / RHEL / CentOS
sudo dnf install -y python3 python3-pip

# Arch / Manjaro
sudo pacman -S --needed python python-pip
```

> Not sure which one you have? Try the Ubuntu line first. If it says `apt: command not found`, try the Fedora line, then the Arch line.

**Check it worked.** Open a **new** terminal (close the old one first) and run:

```
# Windows
python --version

# Mac and Linux
python3 --version
```

You should see something like `Python 3.12.4`. You need **3.11 or newer**. If you see an error, see [When something goes wrong](#when-something-goes-wrong).

---

## Step 2: Install Git

Git is the tool that downloads ("clones") the app's code.

**Windows**
1. Go to **https://git-scm.com/download/win**.
2. The download starts by itself. Open the file.
3. Click **Next** on every screen (the default choices are fine), then **Install**, then **Finish**.

**Mac**
1. Open the terminal and run:
   ```
   git --version
   ```
2. If a box pops up offering to install "command line developer tools", click **Install** and wait. If it prints a version number, Git is already installed.

**Linux**
```
# Ubuntu / Debian / Mint / Pop!_OS
sudo apt install -y git

# Fedora / RHEL / CentOS
sudo dnf install -y git

# Arch / Manjaro
sudo pacman -S --needed git
```

**Check it worked.** Open a **new** terminal and run `git --version`. You should see something like `git version 2.45.1`.

> **Don't want to use Git?** Go to **https://github.com/Aayush-src/InboundLead**, click the green **Code** button, then **Download ZIP**. Unzip it into your **Documents** folder, rename the folder from `InboundLead-main` to `InboundLead`, open a terminal, run `cd ~/Documents/InboundLead`, and skip to Step 4.

---

## Step 3: Download the app

We'll put the app in your **Documents** folder.

```
# Windows, Mac and Linux, the same commands:
cd ~/Documents
git clone https://github.com/Aayush-src/InboundLead.git
cd InboundLead
```

> The project's page is **https://github.com/Aayush-src/InboundLead**.

You now have a folder **Documents → InboundLead** with the app inside.

> **Linux:** if `cd ~/Documents` says *No such file or directory*, run `mkdir -p ~/Documents` first, then try again.

---

## Step 4: Install the app's parts

The app needs some extra pieces. We put them in a private box called a "virtual environment" (`.venv`) so they don't mess with anything else on your computer.

Make sure your terminal is still inside the `InboundLead` folder (if you closed it, run `cd ~/Documents/InboundLead` first). Then:

**Windows**
```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

**Mac and Linux**
```
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

This takes 1–3 minutes and prints a lot of text. That's normal. It's finished when you see `Successfully installed …` and you can type again.

---

## Step 5: Get your Gmail app password

The app needs permission to read and send email from your Gmail. **Don't use your normal Gmail password.** Google gives you a special 16-letter "app password" just for this app. You can cancel it any time without changing your real password.

### 5a. Turn on 2-Step Verification (Google requires it for app passwords)
1. Go to **https://myaccount.google.com/security** and sign in.
2. Find **"How you sign in to Google"** and click **2-Step Verification**.
3. If it says **On**, skip to 5b. If it says **Off**, click **Turn on 2-Step Verification** and follow the steps. Google texts a code to your phone and you type it in.

### 5b. Create the app password
1. Go to **https://myaccount.google.com/apppasswords** (sign in again if asked).
2. In **App name**, type `Inbound Lead Agent`.
3. Click **Create**.
4. A yellow box shows a 16-letter code like `abcd efgh ijkl mnop`.
5. **Copy it now and keep it somewhere safe.** Google only shows it once. If you lose it, delete it on the same page and make a new one.

> **Can't find the App passwords page?** It's usually because 2-Step Verification isn't on yet (go back to 5a). Work or school Google accounts sometimes have it disabled by the administrator. Ask them, or use a personal Gmail.

### 5c. IMAP
Gmail now has IMAP (the way apps read your mail) turned on for everyone, so you don't have to do anything. If your Gmail settings ever show an **"Enable IMAP"** option under *Settings → See all settings → Forwarding and POP/IMAP*, make sure it's on.

> **Using Outlook, Yahoo or another provider?** The app supports any provider with IMAP and an app password. You'll change the IMAP/SMTP server names in Step 9. Gmail is the easiest and best tested, so start with it if you can.

---

## Step 6: Get an AI key

The app uses an AI service to read and write emails. You only need **one** of these. Pick one:

| Option | Cost | Best for |
|---|---|---|
| **A. Anthropic (Claude)**: the default | Pay as you go, a few cents per email | Best writing quality. Recommended. |
| **B. OpenAI (ChatGPT)** | Pay as you go | If you already have an OpenAI account |
| **C. Google Gemini** | Has a free tier | Trying it out for free |
| **D. Groq** | Has a free tier | Free and very fast, simpler writing |

### A. Anthropic (Claude), recommended
1. Go to **https://console.anthropic.com** and click **Sign up** (you can sign in with Google). It may send you to **platform.claude.com**. That's the same thing.
2. Go to **Billing** (or **Plans & Billing**), add a card and buy a small amount of credit (e.g. $5). That lasts a long time.
3. Click **API Keys** in the menu, then **Create Key**. Name it `Inbound Lead Agent`, then click **Create**.
4. Copy the key. It starts with `sk-ant-`. **It's only shown once.**

### B. OpenAI
1. Go to **https://platform.openai.com** and sign up or sign in.
2. Go to **Settings → Billing**, add a card and some credit.
3. Go to **https://platform.openai.com/api-keys** and click **Create new secret key**.
4. Copy the key. It starts with `sk-`.

### C. Google Gemini (free tier)
1. Go to **https://aistudio.google.com/apikey** and sign in with Google.
2. Click **Create API key** (pick or create a project if asked).
3. Copy the key. It starts with `AIza`.

### D. Groq (free tier)
1. Go to **https://console.groq.com/keys** and sign up.
2. Click **Create API Key**, give it a name, then click **Submit**.
3. Copy the key. It starts with `gsk_`.

> **Treat the key like a password.** Anyone who has it can spend your credit. Never post it online or send it in a chat.

---

## Step 7: Put your passwords in the settings file

The app reads your email address, app password and AI key from a file called `.env`. We'll make it from the example file.

**Windows**
```
copy .env.example .env
notepad .env
```

**Mac**
```
cp .env.example .env
open -e .env
```

**Linux**
```
cp .env.example .env
nano .env
```
`nano` is a simple editor inside the terminal. Use the arrow keys to move around and just type. (Prefer a normal window? Try `gedit .env` or `gnome-text-editor .env` instead.)

A text editor opens. Fill in these lines (no spaces around `=`, no quote marks):

```
EMAIL_ADDRESS=yourname@gmail.com
EMAIL_APP_PASSWORD=abcdefghijklmnop
```

Then put your AI key on the line for the service you chose in Step 6, and **only that one**:

```
ANTHROPIC_API_KEY=sk-ant-...        # if you picked A
OPENAI_API_KEY=sk-...               # if you picked B
GEMINI_API_KEY=AIza...              # if you picked C
GROQ_API_KEY=gsk_...                # if you picked D
```

**Save** the file (**Ctrl + S** on Windows, **⌘ + S** on Mac) and close the editor. In `nano` on Linux: press **Ctrl + O**, then **Enter** to save, then **Ctrl + X** to close.

> You can also type all of these into the app's screens later (Step 9) instead. The `.env` file is just the easiest way. The `.env` file stays on your computer and is never uploaded to GitHub.

---

## Step 8: Start the app

In the terminal, inside the `InboundLead` folder:

```
# Windows
python main.py

# Mac and Linux
python3 main.py
```

After a few seconds you'll see a line like:

```
Uvicorn running on http://127.0.0.1:8000
```

Now open your web browser (Chrome, Edge, Safari, Firefox…) on the **same computer** and go to:

### **http://127.0.0.1:8000**

You should see the **Inbound Lead Agent** page. 🎉

> ⚠️ **Leave the terminal window open.** The terminal *is* the app running. If you close it, the app stops. You can minimise it.

---

## Step 9: Set the app up in your browser

The page has tabs along the top. Set them up in this order.

### 9a. Mailbox & Schedule tab
1. Click **Mailbox & Schedule**.
2. Under **Mailbox (app password)**:
   - **Email address**: your Gmail address (already filled if you used `.env`).
   - **App password**: leave blank if you used `.env`, or paste the 16-letter code from Step 5.
   - **IMAP host / port, SMTP host / port**: leave as they are for Gmail (`imap.gmail.com` 993, `smtp.gmail.com` 465).

     For Outlook, use `outlook.office365.com` 993 and `smtp.office365.com` 587. For Yahoo, use `imap.mail.yahoo.com` 993 and `smtp.mail.yahoo.com` 465.
3. Click **Save settings** (bottom of the page), then click **Test login**. You want to see **✓ Login OK**. If you get an error, see [troubleshooting](#when-something-goes-wrong).
4. Under **Automation**, choose how often to check email (for example every 15 minutes) and tick **Run automatically on this schedule**. Click **Save settings**.

Leave **Auto-send replies** **off** for now. With it off, the AI only writes drafts and **nothing is sent until you click Send**.

### 9b. Agent tab: tell the AI who it works for
1. Click **Agent**.
2. Under **AI model**:
   - **Provider**: pick the service from Step 6 (Anthropic, OpenAI, Google Gemini or Groq).
   - **Model**: leave blank to use the recommended one.
   - **API key**: leave blank if you put it in `.env`, otherwise paste it here.
   - Click **Save agent**, then click **Test model**. You want a success message.
3. Under **Who is the agent acting as?**, fill everything in. **The AI only says things you write here**, so be specific:
   - **Agent role**: e.g. `Sales assistant`
   - **Company name**: your business name
   - **Company context**: your services, prices, common questions and answers
   - **Goal**: e.g. `Book a 20-minute call`
   - **Tone**: e.g. `Friendly, short, professional`
   - **Meeting / booking link**: your Calendly or similar link, if you have one
   - **Sender display name** and **Email signature**
4. Click **Save agent**.

### 9c. Choose which emails the AI may read (recommended)
Back on **Mailbox & Schedule**, find **AI privacy check**:
- Tick **Only send emails from these senders to the AI**.
- In **Allowed senders**, put one per line: either a full address (`client@company.com`) or a whole company (`@company.com`).

Emails from anyone not on the list (banks, shops, newsletters, personal mail) are **never shown to the AI**. They're skipped and stay unread in Gmail. You can still *write* to anyone. The list only controls which incoming emails the AI reads.

Click **Save settings**.

### 9d. Leads tab: add your leads
1. Click **Leads**.
2. Drag your Excel or CSV file of leads onto the dotted box (or click **browse**).
   - The only column you **must** have is **Email**.
   - Columns named **Name**, **Company**, **Lead Status**, **Last Message Sent**, **Meeting Details** and **Notes** are picked up automatically. Any other columns are kept too.
3. Your leads appear in the table.

You can also add one person at a time with **✉ New email**.

---

## Step 10: Daily use

| You want to… | Do this |
|---|---|
| Check for new replies right now | Click **Check inbox now** (top right). |
| See what the AI wrote | Open the **Approvals** tab. Read each draft, edit it if you like, then click **Send**, **Save** or **Discard**. |
| Write to one lead | Click the lead's row, pick what to write under **Write an email**, then click **Write with AI**. |
| Write to someone new | **Leads** tab → **✉ New email**. |
| Email all new leads | **Leads** tab → **Write first emails to New leads**. Drafts go to Approvals. |
| Turn on automatic follow-ups | **Mailbox & Schedule** → **Writing & follow-ups**. Set the days to wait and the number of follow-ups. |
| Get your sheet back | **Leads** tab → **Export to Excel**. |
| See what happened | **Activity** tab. |

**Good to know:**
- The app finds replies even if you already opened them on your phone.
- Once you trust the drafts, you can turn on **Auto-send replies** so replies go out without you. Most people keep it off.

---

## Step 11: Stopping and starting again

**To stop:** click in the terminal window and press **Ctrl + C**, or just close the window.

**To start again later** (after restarting your computer, for example):

```
# Windows
cd ~/Documents/InboundLead
python main.py

# Mac and Linux
cd ~/Documents/InboundLead
python3 main.py
```

Then open **http://127.0.0.1:8000** again. All your leads and settings are still there.

> The app only checks email **while it's running**. If your computer is off or the terminal is closed, nothing is checked until you start it again.

**Getting updates** (when a new version is published):
```
cd ~/Documents/InboundLead
git pull
# Windows:
.venv\Scripts\python -m pip install -r requirements.txt
# Mac and Linux:
.venv/bin/python -m pip install -r requirements.txt
```

---

## When something goes wrong

| Problem | Fix |
|---|---|
| `python is not recognized` (Windows) | Python wasn't added to PATH. Run the Python installer again, choose **Modify**, then **Next**, and tick **Add Python to environment variables**. Then open a **new** terminal. |
| `python3: command not found` (Mac) | Install Python again from python.org (Step 1), then open a new terminal. |
| `python3: command not found` (Linux) | Run the install line for your system from Step 1. |
| `The virtual environment was not created successfully because ensurepip is not available` (Linux) | Run `sudo apt install -y python3-venv` (on Ubuntu you may need the exact version, e.g. `python3.12-venv`), delete the half-made folder with `rm -rf .venv`, and redo Step 4. |
| `Python 3.10` or older shown (Linux) | Your system's Python is too old. On Ubuntu run `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.12 python3.12-venv`, then use `python3.12` instead of `python3` in Step 4. |
| `Permission denied` (Mac / Linux) | Don't put `sudo` in front of the app's commands. Only the install lines in Steps 1–2 need `sudo`. If you already did, delete the `.venv` folder (`rm -rf .venv`) and redo Step 4 without `sudo`. |
| `git is not recognized` / `git: command not found` | Install Git (Step 2), then open a **new** terminal. Or use **Download ZIP** instead. |
| `Virtual environment not found` | You skipped Step 4. Run it from inside the `InboundLead` folder. |
| `No such file or directory: requirements.txt` | You're in the wrong folder. Run `cd ~/Documents/InboundLead` first. |
| **Test login** says *Invalid credentials* / *Application-specific password required* | You used your normal Gmail password. Use the 16-letter app password from Step 5, and check the email address is spelled right. |
| **Test login** fails on a work or school account | The administrator may block app passwords. Ask them, or use a personal Gmail. |
| The AI test says the key is missing or invalid | Check the key is pasted completely (no spaces) next to the right provider, and that **Provider** on the Agent tab matches the key. Restart the app after editing `.env`. |
| The AI says *credit balance too low* / *quota exceeded* | Add credit in that service's Billing page, or switch to Gemini or Groq. |
| A reply shows as **blocked** | The sender isn't in **Allowed senders** (Step 9c). Add them, or `@theircompany.com`. |
| A reply isn't picked up at all | It's older than **Look back (days) for unread mail** (Mailbox & Schedule → Inbox handling), or it's in Spam or Promotions. The app reads the main Inbox only. |
| The page won't open | The terminal running the app was closed. Start it again (Step 11). Use exactly `http://127.0.0.1:8000`. |
| `Address already in use` / port 8000 busy | The app is already running in another terminal window. Use that one, or close it and start again. |

Still stuck? Open the **Activity** tab. It lists every check, error and email with a plain-English message. Copy that message when you ask for help.

---

## Keeping things safe

- **Never share** your `.env` file, your app password or your AI key. They're private, like your bank PIN.
- The `.env` file, your leads database (`data/` folder) and your spreadsheets are listed in `.gitignore`, so they're **never uploaded to GitHub**, even if you publish the code.
- To cut off the app's access to your email at any time, go to **https://myaccount.google.com/apppasswords** and delete the "Inbound Lead Agent" password. Your real Gmail password doesn't change.
- To cut off AI access, delete the key in the AI service's **API Keys** page.
- Keep **Auto-send off** until you've read enough drafts to trust them.
