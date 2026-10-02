# Labeling guide

Version: 1

Every case in the golden dataset is labelled by these rules. If you change a rule,
bump the version above and start a new dataset version, because old labels may no
longer follow the new rule.

## Categories

- **billing**: money on an existing account. Charges, refunds, invoices, receipts,
  payment methods, plan upgrades or downgrades, credits.
- **technical**: something in the product is broken or behaving wrongly. Errors, bugs,
  outages, slowness, integrations and API problems.
- **account**: who the customer is and whether they can get in. Login and lockouts,
  passwords, email or profile changes, team members, opening or closing an account.
- **general**: everything else. Product questions, feature requests, feedback and praise,
  pre-sales questions, legal and security documents.

## Tie-break rules

1. Label by what the customer wants us to **do**, not by the words they use.
   An outage email asking for a service credit is billing.
2. If there are several asks, pick the one that, once done, resolves the rest.
   "Delete my account and stop charging me" is account: closing the account stops the charges.
3. Can't get in because of their credentials or lockout: account.
   Gets kicked out or blocked because the product misbehaves: technical.
4. Prices and discounts before someone is a customer: general.
   Prices on an account they already pay for: billing.
5. If an email is too vague to tell, label it by the most likely reading, tag it
   `ambiguous`, and explain your reasoning in `notes`.

## Summaries

6. One sentence, in English, even if the email is in another language.
7. Say what the customer wants, in plain words. 5 to 40 words.
8. Only include facts that are in the email. Never invent order numbers, dates or names.

## Difficulty

- **easy**: one clear ask, the obvious category is correct.
- **medium**: needs a careful read (typos, very short, mild ambiguity, jargon).
- **hard**: a reasonable person could pick a different category without these rules,
  or the tone hides the meaning (sarcasm).
