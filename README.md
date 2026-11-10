# Kudi

**Get paid in dollars. Know your Naira.**

Kudi (Hausa for money) is a PayPal AI hackathon project for Nigerian freelancers. Paste an invoice or a
chat message, get a PayPal sandbox payment link, and read a plain-English
breakdown of what the client pays, what PayPal keeps, and what you actually
take home, including a mid-market Naira estimate.

This is a standalone app. It is not part of wagmi_tracker or the NEAR agent.

**Live demo:** [https://kudi-jbhc.onrender.com](https://kudi-jbhc.onrender.com) (free Render plan; the first load can take about a minute). The earlier URL [https://naira-pay-agent.onrender.com](https://naira-pay-agent.onrender.com) stays up as an alias.

**Example:** `Logo design for Sarah, 150 USD, due Friday`

On that invoice, a Nigerian account receiving an international payment is
charged PayPal's official fee of 4.90% plus a $0.30 fixed fee, which is $7.65.
The freelancer would receive $142.35 in PayPal. PayPal does not settle in
Nigerian Naira. The app then shows a mid-market Naira equivalent and the time
of that rate in WAT.

## What it does

1. Reads a messy invoice or WhatsApp-style message and pulls out the client,
   the work, the amount and currency, and the due date.
2. Creates a shareable PayPal **sandbox** checkout link with the Orders v2 API.
   If sandbox keys are not set, it runs in mock mode so the UI and tests still
   work.
3. Explains official PayPal receiving fees for a Nigerian merchant account, and
   a rough Naira equivalent from a free mid-market FX rate.

If the invoice is in Naira, the checkout link is created in USD at the
mid-market rate, because PayPal does not settle in NGN. That is stated clearly
in the app.

## Official fees (not invented)

Receiving fees come from PayPal's official Nigeria seller fee page:

- https://www.paypal.com/ng/business/paypal-business-fees
- Last updated on that page: 28 October 2026
- Retrieved for this project: 10 November 2026

For a Nigerian account receiving an international commercial payment the official
rate is **4.90% plus a fixed fee** in the currency received (for USD the fixed
fee is **$0.30**). See [docs/fees-source.md](docs/fees-source.md) for the full
tables used in the app, including later conversion (3.0%) and partner
withdrawal (2.0% + $1.50) fees, which are explained separately and are not
quietly subtracted from the main "you receive" figure.

Mid-market FX is **not** PayPal's conversion rate. The primary source is
[open.er-api.com](https://open.er-api.com), with
[Frankfurter](https://api.frankfurter.app) as a fallback. The rate time is shown
in Africa/Lagos (WAT).

## How the "AI" step works

The default parser is a **rule-based invoice reader**. It does not need an API
key, it is deterministic, and it is covered by tests. That was chosen so the
demo keeps working without a paid model, and so judges can run it from the
readme alone.

If you set `OPENAI_API_KEY` or `GROQ_API_KEY`, the same parse can be refined by
an OpenAI-compatible model. The rule-based result is still used as the base,
and a model failure never blocks the app.

The PayPal Agent Toolkit was not required by the official rules and is not used
here, because it needs a function-calling model. This project calls the PayPal
Orders v2 API directly, which is the most reliable way to get a shareable
sandbox checkout link.

## Setup

Python 3.11 or newer is enough.

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # optional, add sandbox keys when you have them
python -m app.server
```

Open http://localhost:8000. The app listens on `0.0.0.0` and uses the `PORT`
environment variable (Render sets this for you). Default port is 8000.

### Sandbox keys

1. Create a free account at [PayPal Developer](https://developer.paypal.com).
2. Open Apps & Credentials, stay on the Sandbox tab, and create an app.
3. Copy the Client ID and Secret into `.env` as `PAYPAL_CLIENT_ID` and
   `PAYPAL_CLIENT_SECRET`.
4. Restart the server. The mode pill should change from "Demo mode" to
   "PayPal sandbox".

If either key is missing, the app stays in mock mode. Live / production mode is
refused. Keys are never logged, printed, or committed. Do not put them in the
repo.

### Tests

```bash
python -m pytest
```

### Render

A [render.yaml](render.yaml) Blueprint is included. Create a free web service
from this repo, then add `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` in the
Render dashboard. Do not deploy until you have reviewed the app.

## Examples

| Paste this | What you should see |
| --- | --- |
| `Logo design for Sarah, 150 USD, due Friday` | Client Sarah, $150, due the coming Friday, PayPal fee $7.65, you receive $142.35 |
| `Website redesign for Chidi, ₦450,000, due 20 November` | Converted to a USD checkout at the mid-market rate, with a NGN disclaimer |
| An invoice that says bill to, description, total, and due date | The same fields, ready to edit before the link is created |

## Hackathon notes

- Devpost: https://paypalaihackathon.devpost.com
- Deadline: Thursday 12 November 2026, 12:00 pm Pacific Time, which is
  **Wednesday 12 November 2026, 9:00 pm WAT**
- Required: meaningful use of PayPal (sandbox) and of AI, a working demo, a
  public repo with an open-source license, a text description, and a YouTube
  demo video under 3 minutes
- The PayPal Agent Toolkit is not required. Any AI tool is allowed.
- Sponsor prize: Best Use of Render (this repo ships with `render.yaml`)
- Nigeria is eligible. Standard excluded countries do not include Nigeria.

The repo is public and the live demo is up. Registration and the Devpost
submission still wait for the project owner.

## License

MIT. See [LICENSE](LICENSE). This project uses the PayPal sandbox API. It is
not a PayPal product.
