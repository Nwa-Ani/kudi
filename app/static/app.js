const els = {
  invoice: document.getElementById("invoice"),
  parseBtn: document.getElementById("parse-btn"),
  createBtn: document.getElementById("create-btn"),
  quoteBtn: document.getElementById("quote-btn"),
  copyBtn: document.getElementById("copy-btn"),
  payBtn: document.getElementById("pay-btn"),
  review: document.getElementById("review"),
  result: document.getElementById("result"),
  composeError: document.getElementById("compose-error"),
  reviewError: document.getElementById("review-error"),
  warnings: document.getElementById("warnings"),
  parseSource: document.getElementById("parse-source"),
  modePill: document.getElementById("mode-pill"),
  client: document.getElementById("field-client"),
  items: document.getElementById("field-items"),
  amount: document.getElementById("field-amount"),
  currency: document.getElementById("field-currency"),
  dueLabel: document.getElementById("field-due-label"),
  totals: document.getElementById("totals"),
  explain: document.getElementById("explain"),
  source: document.getElementById("source"),
  linkBox: document.getElementById("link-box"),
  approveUrl: document.getElementById("approve-url"),
  mockNote: document.getElementById("mock-note"),
  resultTitle: document.getElementById("result-title"),
  resultMode: document.getElementById("result-mode"),
};

let dueDateIso = null;

function showError(node, message) {
  if (!message) {
    node.hidden = true;
    node.textContent = "";
    return;
  }
  node.hidden = false;
  node.textContent = message;
}

function setBusy(button, busy, idleLabel) {
  if (idleLabel) button.dataset.label = idleLabel;
  if (!button.dataset.label) button.dataset.label = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? "Working..." : button.dataset.label;
}

async function getJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok && !data.error) {
    throw new Error("The server could not complete that request.");
  }
  return data;
}

async function loadStatus() {
  try {
    const data = await getJson("/api/status");
    const mode = data.mode || "mock";
    els.modePill.textContent = mode === "sandbox" ? "PayPal sandbox" : "Demo mode";
    els.modePill.classList.remove("mock", "sandbox");
    els.modePill.classList.add(mode === "sandbox" ? "sandbox" : "mock");
  } catch (err) {
    els.modePill.textContent = "Offline";
  }
}

function fillParse(parsed) {
  els.client.value = parsed.client || "";
  els.items.value = parsed.items || "";
  els.amount.value = parsed.amount || "";
  const currency = parsed.currency || "USD";
  if (![...els.currency.options].some((opt) => opt.value === currency)) {
    const option = document.createElement("option");
    option.value = currency;
    option.textContent = currency;
    els.currency.appendChild(option);
  }
  els.currency.value = currency;
  els.dueLabel.value = parsed.due_date_label || "";
  dueDateIso = parsed.due_date || null;
  if (parsed.warnings && parsed.warnings.length) {
    els.warnings.hidden = false;
    els.warnings.textContent = parsed.warnings.join(" ");
  } else {
    els.warnings.hidden = true;
    els.warnings.textContent = "";
  }
  if (els.parseSource) {
    if (parsed.source === "rules+llm") {
      els.parseSource.hidden = false;
      els.parseSource.textContent = "Read by AI, with the rule-based parser as a fallback.";
    } else if (parsed.source === "rules") {
      els.parseSource.hidden = false;
      els.parseSource.textContent = "Read by the rule-based parser.";
    } else {
      els.parseSource.hidden = true;
      els.parseSource.textContent = "";
    }
  }
  els.review.classList.remove("hidden");
  els.review.scrollIntoView({ behavior: "smooth", block: "start" });
}

function payloadFromForm() {
  return {
    client: els.client.value.trim() || null,
    items: els.items.value.trim() || null,
    amount: els.amount.value.trim(),
    currency: els.currency.value,
    due_date: dueDateIso,
    due_date_label: els.dueLabel.value.trim() || null,
    text: els.invoice.value,
  };
}

function addTotalCard(label, value, className, note) {
  const div = document.createElement("div");
  div.className = "total-card" + (className ? " " + className : "");
  const span = document.createElement("span");
  span.textContent = label;
  const strong = document.createElement("strong");
  strong.textContent = value;
  div.append(span, strong);
  if (note) {
    const sub = document.createElement("span");
    sub.textContent = note;
    div.appendChild(sub);
  }
  els.totals.appendChild(div);
}

function renderResult(data, withLink) {
  const explanation = data.explanation || {};
  const checkout = data.checkout;
  const naira = explanation.naira || {};
  els.result.classList.remove("hidden");
  els.totals.innerHTML = "";
  addTotalCard("Client pays", explanation.client_pays || "");
  addTotalCard("PayPal fee", explanation.paypal_fee || "");
  addTotalCard("You receive", explanation.you_receive || "", "takehome");
  if (naira.available) {
    addTotalCard(
      "Naira estimate",
      naira.net_ngn || "",
      "naira",
      naira.rate_time_wat ? "Mid-market, " + naira.rate_time_wat : "Mid-market guide"
    );
  } else {
    addTotalCard("Naira estimate", "Unavailable", "naira", "Mid-market rate is not available right now");
  }

  els.explain.innerHTML = "";
  (explanation.paragraphs || [explanation.plain] || []).forEach((text) => {
    if (!text) return;
    const p = document.createElement("p");
    p.textContent = text;
    els.explain.appendChild(p);
  });

  els.source.innerHTML = "";
  if (explanation.source_url) {
    els.source.append("Fees cited from ");
    const a = document.createElement("a");
    a.href = explanation.source_url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = "PayPal's Nigeria seller fee page";
    els.source.append(a);
    if (explanation.source_updated) {
      els.source.append(", last updated " + explanation.source_updated + ".");
    }
  }

  if (withLink && checkout && checkout.approve_url) {
    els.linkBox.classList.remove("hidden");
    els.approveUrl.value = checkout.approve_url;
    if (els.payBtn) {
      els.payBtn.hidden = false;
      els.payBtn.href = checkout.approve_url;
    }
    els.resultTitle.textContent = "Your payment link";
    els.resultMode.textContent = checkout.mode === "sandbox" ? "PayPal sandbox" : "Demo mode";
    els.resultMode.className = "pill " + (checkout.mode === "sandbox" ? "sandbox" : "mock");
    els.mockNote.hidden = checkout.mode !== "mock";
  } else {
    els.linkBox.classList.add("hidden");
    if (els.payBtn) {
      els.payBtn.hidden = true;
      els.payBtn.removeAttribute("href");
    }
    els.resultTitle.textContent = "Fee preview";
    els.resultMode.textContent = data.mode === "sandbox" ? "PayPal sandbox" : "Demo mode";
    els.resultMode.className = "pill " + (data.mode === "sandbox" ? "sandbox" : "mock");
  }
  els.result.scrollIntoView({ behavior: "smooth", block: "start" });
}

els.parseBtn.addEventListener("click", async () => {
  showError(els.composeError, "");
  const text = els.invoice.value.trim();
  if (!text) {
    showError(els.composeError, "Paste an invoice or a short chat message first.");
    return;
  }
  setBusy(els.parseBtn, true);
  try {
    const data = await getJson("/api/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    fillParse(data.parse || {});
    if (!data.ok) {
      showError(els.reviewError, (data.parse && data.parse.warnings && data.parse.warnings.at(-1)) || "I could not find an amount yet.");
    } else {
      showError(els.reviewError, "");
    }
  } catch (err) {
    showError(els.composeError, err.message || "Something went wrong while reading the invoice.");
  } finally {
    setBusy(els.parseBtn, false, "Read invoice");
  }
});

async function submitQuote(createLink) {
  showError(els.reviewError, "");
  if (!els.amount.value.trim()) {
    showError(els.reviewError, "Add an amount before continuing.");
    return;
  }
  const button = createLink ? els.createBtn : els.quoteBtn;
  setBusy(button, true);
  try {
    const data = await getJson(createLink ? "/api/create-link" : "/api/quote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payloadFromForm()),
    });
    if (!data.ok) {
      showError(els.reviewError, data.error || "The payment link could not be created.");
      if (data.explanation) renderResult(data, false);
      return;
    }
    renderResult(data, createLink);
  } catch (err) {
    showError(els.reviewError, err.message || "The request failed.");
  } finally {
    setBusy(button, false, createLink ? "Create payment link" : "Preview fees only");
  }
}

els.createBtn.addEventListener("click", () => submitQuote(true));
els.quoteBtn.addEventListener("click", () => submitQuote(false));

els.copyBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(els.approveUrl.value);
    els.copyBtn.textContent = "Copied";
    setTimeout(() => {
      els.copyBtn.textContent = "Copy link";
    }, 1500);
  } catch (err) {
    els.approveUrl.select();
    document.execCommand("copy");
  }
});

if (els.payBtn) {
  els.payBtn.addEventListener("click", (event) => {
    if (!els.payBtn.href || els.payBtn.getAttribute("href") === "#") {
      event.preventDefault();
    }
  });
}

document.getElementById("examples").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-example]");
  if (!button) return;
  els.invoice.value = button.getAttribute("data-example");
  els.invoice.focus();
});

loadStatus();
