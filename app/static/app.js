const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (d) => (d ? new Date(/([zZ]|[+-]\d\d:?\d\d)$/.test(d) ? d : d + "Z").toLocaleString() : "—");

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {}, ...opts });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.add("hidden"), 3500);
}

/* ---------- dialog box (replaces alert / confirm / prompt) ---------- */
// Resolves to: true/false (confirm), the typed text or null (input), or undefined (message).
function showDialog({ title = "", text = "", okText = "OK", cancelText = "Cancel", cancel = false,
                      input = null, danger = false, error = false } = {}) {
  const dlg = $("#msgDlg");
  if (dlg.open) dlg.close();
  $("#msgTitle").textContent = title;
  $("#msgText").textContent = text;
  $("#msgText").classList.toggle("hidden", !text);
  $("#msgOk").textContent = okText;
  $("#msgOk").classList.toggle("danger", danger);
  $("#msgCancel").textContent = cancelText;
  $("#msgCancel").classList.toggle("hidden", !cancel && input === null);
  $("#msgInputWrap").classList.toggle("hidden", input === null);
  $("#msgInputLabel").textContent = input?.label ?? "";
  $("#msgInput").value = input?.value ?? "";
  $("#msgInput").placeholder = input?.placeholder ?? "";
  dlg.classList.toggle("error", error);
  dlg.returnValue = "";
  dlg.showModal();
  (input !== null ? $("#msgInput") : $("#msgOk")).focus();
  return new Promise((resolve) => {
    dlg.addEventListener("close", () => {
      const ok = dlg.returnValue === "ok";
      if (input !== null) resolve(ok ? $("#msgInput").value : null);
      else if (cancel) resolve(ok);
      else resolve();
    }, { once: true });
  });
}
const showError = (err, title = "Something went wrong") =>
  showDialog({ title, text: err?.message ?? String(err), error: true });
const askConfirm = (title, text, opts = {}) => showDialog({ title, text, cancel: true, ...opts });
const askText = (title, text, input) => showDialog({ title, text, input, okText: "Continue" });

/* ---------- tabs ---------- */
$$(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  $$(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + name));
  ({ leads: loadLeads, bills: loadBills, drafts: loadDrafts, activity: loadActivity, agent: loadSettings, settings: loadSettings })[name]?.();
  try { localStorage.setItem("tab", name); } catch {}
}

/* ---------- leads ---------- */
let STATUSES = [];
let statusSel = "";
async function loadStats() {
  const s = await api("/api/stats");
  STATUSES = s.statuses;
  const sf = $("#statusFilter");
  if (sf.options.length === 1) STATUSES.forEach((x) => sf.add(new Option(x, x)));
  const cards = [["", "All leads", s.total], ...STATUSES.filter((x) => s.by_status[x]).map((x) => [x, x, s.by_status[x]])];
  $("#stats").innerHTML = cards.map(([k, l, n]) => `<div class="stat ${k === statusSel ? "sel" : ""}" data-k="${esc(k)}"><div class="n">${n}</div><div class="l">${esc(l)}</div></div>`).join("");
  $$("#stats .stat").forEach((c) => c.addEventListener("click", () => { statusSel = c.dataset.k; sf.value = statusSel; loadLeads(); }));
  const b = $("#draftBadge"); b.textContent = s.pending_drafts; b.classList.toggle("hidden", !s.pending_drafts);
}
async function loadLeads() {
  await loadStats();
  const q = $("#search").value.trim();
  const params = new URLSearchParams(); if (statusSel) params.set("status", statusSel); if (q) params.set("q", q);
  const leads = await api("/api/leads?" + params);
  $("#emptyLeads").classList.toggle("hidden", leads.length > 0);
  $("#leadTable tbody").innerHTML = leads.map((l) => `
    <tr data-id="${l.id}">
      <td><strong>${esc(l.name || l.email)}</strong>${l.pending_drafts ? ' <span class="badge">draft</span>' : ""}<div class="muted small">${esc(l.name ? l.email : "")}${l.company ? " · " + esc(l.company) : ""}</div></td>
      <td><span class="pill ${esc(l.status)}" data-s="${esc(l.status)}">${esc(l.status)}</span></td>
      <td><div class="clip" title="${esc(l.last_message_sent)}">${esc(l.last_message_sent) || "—"}</div></td>
      <td><div class="clip">${esc(l.meeting_details) || "—"}</div></td>
      <td><div class="clip" title="${esc(l.next_action)}">${esc(l.next_action) || "—"}</div></td>
      <td class="small muted">${fmt(l.updated_at)}</td>
    </tr>`).join("");
  $$("#leadTable tbody tr").forEach((tr) => tr.addEventListener("click", () => openLead(tr.dataset.id)));
}
let searchT;
$("#search").addEventListener("input", () => { clearTimeout(searchT); searchT = setTimeout(loadLeads, 250); });
$("#statusFilter").addEventListener("change", (e) => { statusSel = e.target.value; loadLeads(); });

/* ---------- upload ---------- */
const dz = $("#dropzone");
$("#browse").addEventListener("click", (e) => { e.preventDefault(); $("#fileInput").click(); });
$("#fileInput").addEventListener("change", (e) => e.target.files[0] && upload(e.target.files[0]));
["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
dz.addEventListener("drop", (e) => e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]));
async function upload(file) {
  const fd = new FormData(); fd.append("file", file);
  $("#importResult").textContent = "Importing…";
  try {
    const r = await api("/api/leads/import", { method: "POST", body: fd });
    $("#importResult").innerHTML = `<span style="color:var(--ok)">✓ ${r.created} new, ${r.updated} updated${r.skipped ? `, ${r.skipped} skipped (no valid email)` : ""}</span>`;
    loadLeads();
  } catch (e) { $("#importResult").innerHTML = `<span style="color:var(--danger)">${esc(e.message)}</span>`; }
  $("#fileInput").value = "";
}

/* ---------- lead drawer ---------- */
let currentLead = null;
async function openLead(id) {
  const { lead, messages } = await api("/api/leads/" + id);
  currentLead = lead;
  $("#dTitle").textContent = lead.name || lead.email;
  $("#dSub").textContent = [lead.email, lead.company, lead.sentiment && "sentiment: " + lead.sentiment].filter(Boolean).join(" · ");
  $("#dStatus").innerHTML = STATUSES.map((s) => `<option ${s === lead.status ? "selected" : ""}>${esc(s)}</option>`).join("");
  $("#dMeeting").value = lead.meeting_details; $("#dNotes").value = lead.notes;
  $("#dSummary").innerHTML = lead.summary ? `<strong>Agent summary:</strong> ${esc(lead.summary)}${lead.next_action ? `<br><strong>Next:</strong> ${esc(lead.next_action)}` : ""}` : "";
  $("#cHint").textContent = ""; $("#cInstr").value = "";
  renderThread(messages);
  $("#drawer").classList.remove("hidden");
}
const KIND_LABEL = { reply: "reply", outreach: "first email", followup: "follow-up", custom: "email" };
function renderThread(messages) {
  $("#dThread").innerHTML = messages.length ? messages.map((m) => m.direction === "draft" ? `
    <div class="msg draft" data-id="${m.id}"><div class="h">DRAFT ${esc(KIND_LABEL[m.kind] || "reply")} · not sent yet${m.in_reply_to ? " · in this thread" : " · new thread"}</div>
      <input class="subj" value="${esc(m.subject)}">
      <textarea class="body" rows="8">${esc(m.body)}</textarea>
      <div class="actions"><button class="btn primary send">Send</button><button class="btn save">Save edits</button><button class="btn danger discard">Discard</button></div></div>` : `
    <div class="msg ${m.direction}"><div class="h">${m.direction === "inbound" ? "From lead" : "Sent " + esc(KIND_LABEL[m.kind] || "")} · ${fmt(m.created_at)} · ${esc(m.subject)}</div>
    <div class="b">${esc(m.body)}</div></div>`).join("") : '<p class="muted small">No emails recorded yet. Use <strong>Write with AI</strong> above to start.</p>';
  $$("#dThread .msg.draft").forEach((el) => {
    const id = el.dataset.id;
    const edits = () => JSON.stringify({ subject: $(".subj", el).value, body: $(".body", el).value });
    $(".send", el).addEventListener("click", async (e) => {
      e.target.disabled = true;
      try { await api(`/api/drafts/${id}/send`, { method: "POST", body: edits() }); toast("Sent ✓"); openLead(currentLead.id); loadLeads(); }
      catch (err) { showError(err); e.target.disabled = false; }
    });
    $(".save", el).addEventListener("click", async () => { try { await api(`/api/drafts/${id}`, { method: "PUT", body: edits() }); toast("Draft saved"); } catch (err) { showError(err); } });
    $(".discard", el).addEventListener("click", async () => { await api(`/api/drafts/${id}/discard`, { method: "POST" }); openLead(currentLead.id); loadStats(); });
  });
}
$("#cWrite").addEventListener("click", async (e) => {
  const kind = $("#cKind").value, instructions = $("#cInstr").value;
  if (kind === "custom" && !instructions.trim()) { showDialog({ title: "Instructions needed", text: "Tell the AI what the email should say." }); return; }
  e.target.disabled = true; $("#cHint").textContent = "Writing…";
  try {
    await api("/api/compose", { method: "POST", body: JSON.stringify({ lead_id: currentLead.id, kind, instructions }) });
    $("#cHint").textContent = "Draft ready below. Edit it, then Send.";
    $("#cInstr").value = "";
    const { messages } = await api("/api/leads/" + currentLead.id); renderThread(messages);
    $$("#dThread .msg.draft").at(-1)?.scrollIntoView({ behavior: "smooth", block: "center" });
    loadLeads();
  } catch (err) { $("#cHint").textContent = ""; showError(err, "Couldn't write the email"); }
  e.target.disabled = false;
});

/* ---------- new email + bulk first emails ---------- */
$("#newEmail").addEventListener("click", () => { $("#newForm").reset(); $("#newHint").textContent = ""; $("#newDlg").showModal(); });
$("#newForm").addEventListener("submit", async (e) => {
  if (e.submitter?.value !== "write") return;
  e.preventDefault();
  const f = e.target.elements, btn = $("#newWrite");
  btn.disabled = true; $("#newHint").textContent = "Writing…";
  try {
    const d = await api("/api/compose", { method: "POST", body: JSON.stringify({ email: f.email.value, name: f.name.value, company: f.company.value, kind: f.instructions.value.trim() ? "custom" : "auto", instructions: f.instructions.value }) });
    $("#newDlg").close(); loadLeads(); openLead(d.lead_id);
  } catch (err) { $("#newHint").textContent = ""; showError(err, "Couldn't write the email"); }
  btn.disabled = false;
});
$("#bulkOutreach").addEventListener("click", async (e) => {
  const instructions = await askText("Write first emails",
    "The AI will write a first email for every lead with status New that you have never emailed. They wait in Approvals (nothing is sent unless Auto-send is on).",
    { label: "Anything the AI should mention? (optional)", placeholder: "e.g. we now offer SEO packages" });
  if (instructions === null) return;
  e.target.disabled = true; const label = e.target.textContent; e.target.textContent = "Writing…";
  try {
    const r = await api("/api/compose/bulk", { method: "POST", body: JSON.stringify({ status: "New", instructions }) });
    showDialog({ title: "First emails", text: r.written ? `Wrote ${r.written} first email(s)${r.failed ? `, ${r.failed} failed (see Activity)` : ""}${r.skipped_limit ? `, ${r.skipped_limit} left for the next batch` : ""}. Review them in Approvals.` : "No New leads waiting for a first email." });
    loadLeads();
  } catch (err) { showError(err); }
  e.target.disabled = false; e.target.textContent = label;
});
$("#dClose").addEventListener("click", () => $("#drawer").classList.add("hidden"));
$("#dSave").addEventListener("click", async () => {
  try {
    await api("/api/leads/" + currentLead.id, { method: "PATCH", body: JSON.stringify({ status: $("#dStatus").value, meeting_details: $("#dMeeting").value, notes: $("#dNotes").value }) });
    toast("Lead saved"); loadLeads();
  } catch (err) { showError(err); }
});
$("#dDelete").addEventListener("click", async () => {
  if (!(await askConfirm("Delete lead?", `Delete ${currentLead.email} and its email history? This can't be undone.`, { okText: "Delete", danger: true }))) return;
  try {
    await api("/api/leads/" + currentLead.id, { method: "DELETE" });
    $("#drawer").classList.add("hidden"); loadLeads();
  } catch (err) { showError(err); }
});

/* ---------- bills ---------- */
let BILL_STATUSES = [];
let billStatusSel = "";
const money = (a, c) => (a == null || a === 0 ? "—" : `${c ? esc(c) + " " : ""}${Number(a).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
async function loadBills() {
  const st = await api("/api/bills/stats");
  BILL_STATUSES = st.statuses;
  const sf = $("#billStatusFilter");
  if (sf.options.length === 1) BILL_STATUSES.forEach((x) => sf.add(new Option(x, x)));
  const cards = [["", "All bills", st.total], ...BILL_STATUSES.filter((x) => st.by_status[x]).map((x) => [x, x, st.by_status[x]])];
  $("#billStats").innerHTML = cards.map(([k, l, n]) => `<div class="stat ${k === billStatusSel ? "sel" : ""}" data-k="${esc(k)}"><div class="n">${n}</div><div class="l">${esc(l)}</div></div>`).join("");
  $$("#billStats .stat").forEach((c) => c.addEventListener("click", () => { billStatusSel = c.dataset.k; sf.value = billStatusSel; loadBills(); }));
  const totals = Object.entries(st.open_totals);
  $("#openTotals").textContent = totals.length ? "Open (not paid): " + totals.map(([c, a]) => money(a, c === "?" ? "" : c)).join(" · ") : "";

  const params = new URLSearchParams();
  if (billStatusSel) params.set("status", billStatusSel);
  const q = $("#billSearch").value.trim(); if (q) params.set("q", q);
  const rows = await api("/api/bills?" + params);
  $("#emptyBills").classList.toggle("hidden", rows.length > 0);
  $("#billTable tbody").innerHTML = rows.map((b) => `
    <tr data-id="${b.id}">
      <td><strong>${esc(b.vendor)}</strong><div class="muted small">${esc(b.description || b.sender_email)}</div></td>
      <td>${esc(b.invoice_number) || "—"}</td>
      <td class="small">${esc(b.document_type.replace(/_/g, " "))}</td>
      <td class="num">${money(b.amount, b.currency)}</td>
      <td class="small">${esc(b.due_date) || "—"}</td>
      <td><span class="pill ${esc(b.status)}">${esc(b.status)}</span></td>
      <td class="small muted">${fmt(b.received_at)}</td>
    </tr>`).join("");
  $$("#billTable tbody tr").forEach((tr) => tr.addEventListener("click", () => openBill(rows.find((b) => String(b.id) === tr.dataset.id))));
}
let billSearchT;
$("#billSearch").addEventListener("input", () => { clearTimeout(billSearchT); billSearchT = setTimeout(loadBills, 250); });
$("#billStatusFilter").addEventListener("change", (e) => { billStatusSel = e.target.value; loadBills(); });

let currentBill = null;
function openBill(b) {
  currentBill = b;
  $("#bTitle").textContent = `${b.vendor}${b.invoice_number ? " · #" + b.invoice_number : ""}`;
  $("#bSub").textContent = [b.sender_email, b.document_type.replace(/_/g, " "), b.issue_date && "issued " + b.issue_date].filter(Boolean).join(" · ");
  $("#bStatus").innerHTML = BILL_STATUSES.map((s) => `<option ${s === b.status ? "selected" : ""}>${esc(s)}</option>`).join("");
  $("#bDue").value = /^\d{4}-\d{2}-\d{2}$/.test(b.due_date) ? b.due_date : "";
  $("#bAmount").value = b.amount ?? ""; $("#bCurrency").value = b.currency; $("#bNotes").value = b.notes;
  $("#bSummary").innerHTML = b.summary ? `<strong>Latest:</strong> ${esc(b.summary)}<br><span class="small muted">Subject: ${esc(b.source_subject)}</span>` : "";
  $("#bHistory").innerHTML = [...b.history].reverse().map((h) => `<li><time>${fmt(h.at)}</time><span><span class="pill ${esc(h.status)}">${esc(h.status)}</span> ${esc(h.note)}</span></li>`).join("");
  $("#bNoticeHint").textContent = "";
  $("#billDrawer").classList.remove("hidden");
}
$("#bClose").addEventListener("click", () => $("#billDrawer").classList.add("hidden"));
$("#bSave").addEventListener("click", async () => {
  const body = { status: $("#bStatus").value, notes: $("#bNotes").value, currency: $("#bCurrency").value.toUpperCase(), due_date: $("#bDue").value };
  if ($("#bAmount").value !== "") body.amount = +$("#bAmount").value;
  try { openBill(await api("/api/bills/" + currentBill.id, { method: "PATCH", body: JSON.stringify(body) })); toast("Bill saved"); loadBills(); }
  catch (e) { showError(e); }
});
$("#bNotice").addEventListener("click", async (e) => {
  e.target.disabled = true; $("#bNoticeHint").textContent = "Writing confirmation…";
  try {
    await api(`/api/bills/${currentBill.id}/notice`, { method: "POST" });
    $("#bNoticeHint").innerHTML = `Draft ready — review and send it in <a href="#" id="toApprovals">Approvals</a>.`;
    $("#toApprovals").addEventListener("click", (ev) => { ev.preventDefault(); $("#billDrawer").classList.add("hidden"); showTab("drafts"); });
    loadStats();
  } catch (err) { $("#bNoticeHint").textContent = ""; showError(err, "Couldn't write the confirmation"); }
  e.target.disabled = false;
});
$("#bDelete").addEventListener("click", async () => {
  if (!(await askConfirm("Delete bill?", `Delete this bill from ${currentBill.vendor}? This can't be undone.`, { okText: "Delete", danger: true }))) return;
  try {
    await api("/api/bills/" + currentBill.id, { method: "DELETE" });
    $("#billDrawer").classList.add("hidden"); loadBills();
  } catch (err) { showError(err); }
});

/* ---------- drafts ---------- */
async function loadDrafts() {
  const drafts = await api("/api/drafts");
  loadStats();
  $("#draftList").innerHTML = drafts.length ? drafts.map((d) => {
    const a = d.analysis || {};
    return `<div class="card draft" data-id="${d.id}">
      <div class="meta"><div><strong>${esc(d.lead.name || d.lead.email)}</strong> <span class="muted small">${esc(d.lead.email)}</span>
        <div class="small muted">Intent: ${esc(a.intent || "—")} · Sentiment: ${esc(a.sentiment || "—")} · Status → <span class="pill" data-s="${esc(a.new_status)}">${esc(a.new_status || d.lead.status)}</span></div></div>
        <div class="small muted">${fmt(d.created_at)}</div></div>
      ${a.summary ? `<div class="summary">${esc(a.summary)}</div>` : ""}
      <input class="subj" value="${esc(d.subject)}">
      <textarea class="body" rows="9">${esc(d.body)}</textarea>
      <div class="actions"><button class="btn primary send">Send</button><button class="btn danger discard">Discard</button><button class="btn ghost view">View thread</button></div>
    </div>`;
  }).join("") : '<div class="card empty">No replies waiting for approval.</div>';
  $$("#draftList .draft").forEach((el) => {
    const id = el.dataset.id;
    $(".send", el).addEventListener("click", async (e) => {
      e.target.disabled = true;
      try { await api(`/api/drafts/${id}/send`, { method: "POST", body: JSON.stringify({ subject: $(".subj", el).value, body: $(".body", el).value }) }); toast("Sent ✓"); loadDrafts(); }
      catch (err) { showError(err); e.target.disabled = false; }
    });
    $(".discard", el).addEventListener("click", async () => { await api(`/api/drafts/${id}/discard`, { method: "POST" }); loadDrafts(); });
    $(".view", el).addEventListener("click", () => openLead(drafts.find((d) => String(d.id) === id).lead.id));
  });
  loadNotices();
}

async function loadNotices() {
  const rows = await api("/api/bill-notices");
  $("#noticeList").innerHTML = rows.length ? rows.map((n) => `
    <div class="card draft" data-id="${n.id}">
      <div class="meta"><div><strong>${esc(n.bill.vendor)}</strong>${n.bill.invoice_number ? ` <span class="muted small">#${esc(n.bill.invoice_number)}</span>` : ""}
        <div class="small muted">To ${esc(n.to_email)} · confirms <span class="pill ${esc(n.for_status)}">${esc(n.for_status)}</span> · ${money(n.bill.amount, n.bill.currency)}</div></div>
        <div class="small muted">${fmt(n.created_at)}</div></div>
      <input class="subj" value="${esc(n.subject)}">
      <textarea class="body" rows="7">${esc(n.body)}</textarea>
      <div class="actions"><button class="btn primary send">Send</button><button class="btn danger discard">Discard</button></div>
    </div>`).join("") : '<div class="card empty">No vendor confirmations waiting.</div>';
  $$("#noticeList .draft").forEach((el) => {
    const id = el.dataset.id;
    $(".send", el).addEventListener("click", async (e) => {
      e.target.disabled = true;
      try { await api(`/api/bill-notices/${id}/send`, { method: "POST", body: JSON.stringify({ subject: $(".subj", el).value, body: $(".body", el).value }) }); toast("Confirmation sent ✓"); loadNotices(); loadStats(); }
      catch (err) { showError(err); e.target.disabled = false; }
    });
    $(".discard", el).addEventListener("click", async () => { await api(`/api/bill-notices/${id}/discard`, { method: "POST" }); loadNotices(); loadStats(); });
  });
}

/* ---------- settings ---------- */
const BOOL = ["scheduler_enabled", "auto_send", "followup_enabled", "auto_outreach", "accept_new_leads", "bill_tracking", "bill_ack_enabled", "bill_ack_auto_send", "llm_allowlist_enabled"];
const ACK_STATUSES = ["Received", "Processed", "Paid", "Disputed", "Cancelled"];
const NUM = ["imap_port", "smtp_port", "check_interval_minutes", "lookback_days", "followup_after_days", "followup_max"];
let SETTINGS = {};
async function loadSettings() {
  SETTINGS = await api("/api/settings");
  for (const form of [$("#agentForm"), $("#settingsForm")]) {
    for (const el of form.elements) {
      if (!el.name || el.name === "app_password" || el.name === "llm_api_key") continue;
      if (BOOL.includes(el.name)) el.checked = !!SETTINGS[el.name];
      else if (el.name === "check_interval_minutes" && ![...el.options].some((o) => +o.value === SETTINGS[el.name])) {
        el.add(new Option(`${SETTINGS[el.name]} minutes`, SETTINGS[el.name])); el.value = SETTINGS[el.name];
      } else el.value = SETTINGS[el.name] ?? "";
    }
  }
  const chosen = (SETTINGS.bill_ack_statuses || "").split(",").map((x) => x.trim());
  $("#ackStatuses").innerHTML = ACK_STATUSES.map((x) => `<label><input type="checkbox" class="ackst" value="${x}" ${chosen.includes(x) ? "checked" : ""}> ${x}</label>`).join("");
  await loadProviders();
  $("#llmProvider").value = SETTINGS.llm_provider || "anthropic";
  updateProviderHints();
  $("#pwdHint").textContent = SETTINGS.has_password ? "✓ An app password is saved (or loaded from .env)" : "No app password set yet";
  renderRunStatus();
}
let PROVIDERS = null;
async function loadProviders() {
  if (PROVIDERS) return;
  PROVIDERS = await api("/api/llm/providers");
  const sel = $("#llmProvider");
  PROVIDERS.forEach((p) => sel.add(new Option(p.label, p.id)));
  sel.addEventListener("change", () => {
    // switching provider: clear model/base URL so the new provider's defaults apply
    $("#llmModel").value = ""; $("#llmBaseUrl").value = "";
    updateProviderHints();
  });
}
function updateProviderHints() {
  const p = PROVIDERS.find((x) => x.id === $("#llmProvider").value) || PROVIDERS[0];
  $("#llmModel").placeholder = p.default_model || "model name (required)";
  $("#llmBaseUrl").placeholder = p.base_url || "https://your-endpoint/v1 (required)";
  $("#baseUrlWrap").classList.toggle("hidden", p.id === "anthropic");
  const saved = SETTINGS.has_llm_key && SETTINGS.llm_provider === p.id;
  $("#keyHint").textContent = saved ? "✓ A key is saved for this provider"
    : p.env_key_present ? `✓ Using ${p.key_env} from .env`
    : p.needs_key ? `Required — paste it here or set ${p.key_env} in .env`
    : "Not needed for local models (optional for custom endpoints)";
}
$("#testLlm").addEventListener("click", async () => {
  $("#llmResult").textContent = "Testing… (save first if you changed the model)";
  try {
    const r = await api("/api/llm/test", { method: "POST" });
    $("#llmResult").innerHTML = `<span style="color:var(--ok)">✓ ${esc(r.provider)} / ${esc(r.model)} responded</span>`;
  } catch (e) { $("#llmResult").innerHTML = `<span style="color:var(--danger)">${esc(e.message)}</span>`; }
});
function renderRunStatus() {
  const parts = [];
  if (SETTINGS.last_run_at) parts.push("Last check " + fmt(SETTINGS.last_run_at));
  if (SETTINGS.scheduler_enabled && SETTINGS.next_run_at) parts.push("next " + new Date(SETTINGS.next_run_at).toLocaleTimeString());
  else parts.push("schedule off");
  $("#runStatus").textContent = parts.join(" · ");
  $("#scheduleInfo").textContent = SETTINGS.last_run_summary ? "Last run: " + SETTINGS.last_run_summary : "";
}
async function saveSettings(e) {
  e.preventDefault();
  const body = { ...SETTINGS };
  delete body.has_password; delete body.has_llm_key; delete body.next_run_at; delete body.last_run_at; delete body.last_run_summary; delete body.id;
  if ($("#ackStatuses", e.target)) body.bill_ack_statuses = $$(".ackst:checked", e.target).map((x) => x.value).join(",");
  for (const el of e.target.elements) {
    if (!el.name) continue;
    body[el.name] = BOOL.includes(el.name) ? el.checked : NUM.includes(el.name) ? +el.value : el.value;
  }
  try {
    SETTINGS = await api("/api/settings", { method: "PUT", body: JSON.stringify(body) });
    for (const n of ["app_password", "llm_api_key"]) { const f = e.target.elements[n]; if (f) f.value = ""; }
    $(".saved", e.target).textContent = "Saved ✓"; setTimeout(() => ($(".saved", e.target).textContent = ""), 2500);
    loadSettings();
  } catch (err) { showError(err); }
}
$("#agentForm").addEventListener("submit", saveSettings);
$("#settingsForm").addEventListener("submit", saveSettings);
$("#testConn").addEventListener("click", async () => {
  $("#testResult").textContent = "Testing… (save first if you changed credentials)";
  try { await api("/api/settings/test", { method: "POST" }); $("#testResult").innerHTML = '<span style="color:var(--ok)">✓ Login OK</span>'; }
  catch (e) { $("#testResult").textContent = ""; showError(e, "Mailbox login failed"); }
});

$("#runFollowups").addEventListener("click", async (e) => {
  e.preventDefault();
  $("#followupResult").textContent = "Working… (save settings first if you changed them)";
  try {
    const r = await api("/api/followups/run", { method: "POST" });
    $("#followupResult").textContent = `Wrote ${r.followup} follow-up(s), ${r.outreach} first email(s)${r.error ? `, ${r.error} failed (see Activity)` : ""}.`;
    loadStats();
  } catch (err) { $("#followupResult").textContent = ""; showError(err); }
});

/* ---------- run + activity ---------- */
$("#runNow").addEventListener("click", async (e) => {
  e.target.disabled = true; e.target.textContent = "Checking…";
  try { const r = await api("/api/run", { method: "POST" }); showDialog({ title: "Inbox checked", text: r.summary }); }
  catch (err) { showError(err); }
  e.target.disabled = false; e.target.textContent = "Check inbox now";
  loadSettings(); loadLeads();
  if ($("#tab-bills").classList.contains("active")) loadBills();
});
async function loadActivity() {
  const rows = await api("/api/activity");
  $("#activityList").innerHTML = rows.map((r) => `<li class="${esc(r.level)}"><time>${fmt(r.created_at)}</time><span>${esc(r.message)}</span></li>`).join("") || '<li class="muted">Nothing yet.</li>';
}

/* ---------- boot ---------- */
let startTab = "leads";
try { startTab = localStorage.getItem("tab") || "leads"; } catch {}
loadSettings().then(() => showTab(startTab));
setInterval(() => { loadStats().catch(() => {}); api("/api/settings").then((s) => { SETTINGS = s; renderRunStatus(); }).catch(() => {}); }, 30000);
