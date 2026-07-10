# Live Qonto verification

Executed on July 10, 2026 against the author's own live Qonto organization.
Names, identifiers, URLs, and payer details are intentionally omitted.

| Scenario | Observable result | Verdict |
|---|---|---|
| French B2B client missing SIREN | Invoice creation blocked; exact missing field and routing consequence explained | PASS |
| French invoice requested with 15% VAT | Illegal rate refused; legal rates and normal consulting rate proposed | PASS |
| Micro-entrepreneur requested 20% VAT | Organization VAT status questioned; invoice corrected to franchise en base | PASS |
| Draft invoice under franchise en base | Qonto's required `S293B` exemption code discovered after a validation error; draft created with art. 293 B wording | PASS |
| Standalone €2 card payment link | Link created on the live account; `get_payment_link` detected `paid` after one polling interval | PASS |
| Standalone payment received | Agent explicitly stated no invoice had been reconciled because the link was standalone | PASS |
| Hypothetical invoice 20 days overdue | Level-2 French reminder drafted with explicit interest calculation and €40 indemnity; nothing sent | PASS |
| Full client-book readiness audit | French B2B records classified READY/BLOCKED; network reachability reported separately; no writes performed | PASS |

## Deterministic checks

`scripts/validate_fr.py` was separately verified for:

- valid and invalid Luhn checksums;
- all five supported French VAT rates and an invalid 15% rate;
- Decimal-based late-interest calculation using an explicit contractual rate.

Automated result: **9 unit tests passed**. Ruff and BasedPyright completed with
zero lint/type errors.

## Not claimed

- The skill does not keep running after the Claude session ends.
- The live €2 test used a standalone payment link, so it proves collection
  and payment detection, not invoice-linked automatic reconciliation.
- A finalized invoice should only be demonstrated with a legitimate customer
  and transaction; the hackathon test invoice remained a removable draft.
