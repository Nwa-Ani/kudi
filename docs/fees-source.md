# Official PayPal fee source

This project does not invent fee percentages. The numbers used in the app were
copied from PayPal's official Nigeria seller fee page.

- Page: https://www.paypal.com/ng/business/paypal-business-fees
- Last updated on that page: 28 October 2026
- Retrieved for this project: 10 November 2026, Africa/Lagos (WAT)

The same tables were also visible at:

- https://pep.paypal.com/ng/business/paypal-business-fees
- https://securepayments.paypal.com/ng/business/paypal-business-fees

## Receiving international commercial payments

Nigeria (NG) is listed in the seller group AO, BF, BH, BJ, CD, CI, CM, DZ, ET,
FJ, GA, GN, JO, KG, MG, NA, NC, NG, OM, PF, PW, RW, SA, SL, TG, TJ, TM, TN, TZ,
UG, ZM, and ZW. For buyers in all markets the rate is:

**4.90% + a fixed fee**

## Fixed fee for commercial transactions (based on currency received)

| Currency | Fee |
| --- | --- |
| Australian dollar | 0.30 AUD |
| Brazilian real | 0.60 BRL |
| Canadian dollar | 0.30 CAD |
| Czech koruna | 10.00 CZK |
| Danish krone | 2.60 DKK |
| Euro | 0.35 EUR |
| Hong Kong dollar | 2.35 HKD |
| Hungarian forint | 90.00 HUF |
| Israeli new shekel | 1.20 ILS |
| Japanese yen | 40.00 JPY |
| Malaysian ringgit | 2.00 MYR |
| Mexican peso | 4.00 MXN |
| New Taiwan dollar | 10.00 TWD |
| New Zealand dollar | 0.45 NZD |
| Norwegian krone | 2.80 NOK |
| Philippine peso | 15.00 PHP |
| Polish zloty | 1.35 PLN |
| Russian ruble | 10.00 RUB |
| Singapore dollar | 0.50 SGD |
| Swedish krona | 3.25 SEK |
| Swiss franc | 0.55 CHF |
| Thai baht | 11.00 THB |
| UK pounds sterling | 0.20 GBP |
| US dollar | 0.30 USD |

Nigerian Naira (NGN) is not in this receiving fixed-fee table. PayPal does not
settle a Nigerian merchant account in NGN, so this app converts a Naira invoice
to USD before creating a checkout link.

## Currency conversion (if funds are later converted)

From "Converting balance, transfers, and payments received into another
currency", Middle East & Africa (this list includes Nigeria): **3.0%** above
the base exchange rate.

## Withdrawals through a third-party partner

Nigeria is listed under "Withdrawals through third party service providers":
**2.0% + 1.50 USD**, plus whatever the partner charges.

## What the app does and does not deduct

The main "you receive" figure subtracts only the official international
receiving fee (4.90% + the fixed fee). Conversion and partner withdrawal fees
are explained separately, because they apply only if the freelancer later
converts or cashes out.
