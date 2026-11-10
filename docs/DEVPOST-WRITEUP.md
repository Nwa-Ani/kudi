# Devpost write-up (draft, not submitted)

Project: Kudi
Tagline: Get paid in dollars. Know your Naira.
Live demo: https://kudi-jbhc.onrender.com
Code: https://github.com/Nwa-Ani/naira-pay-agent
Builder: Nwa-Ani (@heisevo)

Do not paste this onto Devpost until the project owner says to submit.

## Inspiration

Nigerian freelancers are often paid in dollars, euros, or pounds through PayPal,
then have to guess what will actually land after fees, and what that is worth
in Naira. PayPal does not settle in NGN, official receiving fees are easy to
misread, and invoices still arrive as messy WhatsApp messages. I wanted a
small agent, named Kudi (Hausa for money), that turns that chat into a
checkout link and a plain-English take-home figure, built for someone
working from Nigeria.

## What it does

A freelancer pastes an invoice or a short chat message, for example
"Logo design for Sarah, 150 USD, due Friday". The agent reads the client, the
work, the amount and currency, and the due date. After a quick review step, it
creates a PayPal sandbox checkout link with the Orders v2 API.

It then explains, in plain English:

- what the client is asked to pay
- PayPal's official fee for a Nigerian account receiving an international payment
- what the freelancer would receive in PayPal
- a mid-market Naira estimate, with the rate time shown in WAT (Africa/Lagos)

If the invoice is in Naira, the checkout is created in USD at the mid-market
rate, because PayPal does not settle in NGN. The app says that clearly.
Conversion and partner withdrawal fees that may apply later are explained
separately, not silently subtracted from the main "you receive" figure.

The hosted demo runs in PayPal sandbox only. No live payments are taken.

## How we built it

The app is a FastAPI service with a single-page front end, hosted on Render.

Invoice reading is a rule-based parser. It handles chat-style lines, labelled
invoice fields, currency symbols including naira, relative dates such as
"due Friday", and day-first numeric dates common in Nigeria. Dates are
resolved in Africa/Lagos. The parser needs no API key, so judges can run the
demo from the readme alone. If an OpenAI-compatible key is set, the same parse
can be refined by a model, and a model failure never blocks the app.

Checkout links come from the PayPal Orders v2 sandbox API. If sandbox keys are
missing, the app runs in mock mode so the UI and tests still work. Live or
production mode is refused.

Receiving fees are copied from PayPal's official Nigeria seller fee page
(https://www.paypal.com/ng/business/paypal-business-fees, last updated 28
October 2026). For a Nigerian account receiving an international commercial
payment the official rate is 4.90% plus a fixed fee in the currency received
($0.30 for USD). Mid-market FX uses open.er-api.com, with Frankfurter as a
fallback.

## Tools used

- PayPal Orders v2 API (sandbox) for the shareable checkout link
- A rule-based invoice parser, with an optional OpenAI-compatible model if a
  key is set
- FastAPI, Python, and a static front end
- open.er-api.com and Frankfurter for mid-market FX
- Render, for hosting the public demo
- pytest for parser, fee math, FX fallback, mock checkout, and API tests

The PayPal Agent Toolkit was not required by the official rules and is not
used here, because it needs a function-calling model. The project calls the
Orders v2 API directly.

## Challenges

Official fees had to be taken from the Nigeria seller fee page, not guessed.
PayPal does not settle in NGN, so a Naira invoice needs a clear USD conversion
path and a disclaimer. Mid-market Naira figures must not be mistaken for a
bank credit. The parser also had to work on messy, unlabelled chat text
without requiring a paid model, so the demo stays reliable for judges.

## Accomplishments

We shipped a working end-to-end prototype: paste an invoice, review the
fields, create a real PayPal sandbox checkout, and read a cited fee breakdown
plus a Naira estimate. The $150 USD example is charged the official $7.65
receiving fee, so the freelancer would receive $142.35 in PayPal. The project
is public, MIT licensed, tested, and hosted on Render, which also puts it in
contention for Best Use of Render.

## What's next

A production version would add a freelancer's own PayPal payout settings, a
saved client list, and a clearer cash-out path that still keeps official
PayPal fees separate from bank or partner charges. I would also like to
support more invoice formats and a short history of links sent, still without
asking website users to connect a wallet or share a live PayPal login.

## YouTube demo (draft)

Title:
Kudi: Get paid in dollars. Know your Naira.

Description:
Kudi helps a Nigerian freelancer turn a messy invoice or
chat message into a PayPal sandbox payment link, then explains official PayPal
fees and a mid-market Naira estimate in plain English.

Live demo: https://kudi-jbhc.onrender.com
Source code: https://github.com/Nwa-Ani/naira-pay-agent

In this demo I paste "Logo design for Sarah, 150 USD, due Friday", review the
details, and create a PayPal sandbox checkout. PayPal's official fee for a
Nigerian account receiving an international payment is 4.90% plus a $0.30
fixed fee, which is $7.65 on this invoice, so the freelancer would receive
$142.35. PayPal does not settle in NGN. The app shows a mid-market Naira
equivalent and the time of that rate in WAT.

This is an independent project. It uses the PayPal sandbox. It is not a
PayPal product. No live payments are taken.

Built for the PayPal AI Hackathon on Devpost.
