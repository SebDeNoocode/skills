# 💶 Veto — the accountant that says NO

**Qonto × Anthropic MCP Hackathon submission**

> 🎬 **3-minute demo video:** _link added to this line and the pull request on submission._

The guarded accounts-receivable workflow, in a Claude conversation, on your real
Qonto account: **draft → validate → invoice → collect → detect payment →
mark paid → chase late payers.** With a twist: this agent **refuses** to
create a non-compliant invoice — and tells you how to fix it.

## Why

From **September 1, 2026**, every French business must be able to receive
e-invoices, and French B2B invoices need the identifiers required for
routing. An API can validate a payload, but it cannot infer business facts
such as whether a seller has opted into VAT or remains under franchise en
base. That missing context can turn a syntactically valid invoice into a
business mistake.

This skill puts a rigorous French accountant between you and the mistake,
then goes to work collecting your money.

## What it does

| Step | Tool(s) | Human in the loop |
|---|---|---|
| Audit the full client book (READY / BLOCKED / OUTSIDE FR B2B SCOPE) | `list_clients`, `get_client` | fixes require confirmation |
| Pre-flight compliance audit (SIREN, address, VAT) | `get_client`, `get_organization` | — |
| Refuse & fix non-compliant requests | `update_client` | asks for missing data |
| Create the invoice (draft) or a quote | `create_client_invoice`, `create_quote` | ✅ explicit confirmation |
| Finalize the invoice (draft → unpaid) | `change_client_invoice_status` | ✅ second confirmation |
| Send + payment link | `send_client_invoice`, `create_payment_link` | ✅ confirmation |
| Check payment | `get_payment_link` (on demand or while the session is active) | announces result |
| Mark paid | `mark_client_invoice_as_paid` | ✅ confirmation |
| Chase overdue (escalating tone: friendly → firm → mise en demeure) | `list_client_invoices` | drafts only — user sends |
| Bulk mode | all of the above, one confirmation per batch | ✅ |

## Design principles

- **The agent prepares, the human decides.** No invoice is created, sent,
  or marked paid without an explicit summary + confirmation. AI assists —
  it never displaces responsibility for financial actions.
- **Fails gracefully.** Missing SIREN, illegal VAT rate, absent due date:
  the skill blocks with a one-sentence explanation and the exact fix,
  instead of producing a defective legal document.
- **Compliance is data, not vibes.** Every rule enforced is sourced in
  [`references/compliance-fr.md`](references/compliance-fr.md) (CGI,
  Code de commerce, 2026 e-invoicing reform).
- **Extensible by design.** France ships first; the reference-file pattern
  (`references/compliance-fr.md`) could be extended to Italy (FatturaPA) or
  Germany (ZUGFeRD = Factur-X) as follow-up work.
- **Honest automation.** The skill does not run after the Claude session
  ends. It checks on demand or polls briefly during an active payment test;
  event-driven background monitoring would require an external runtime.

## Install

1. Connect the Qonto MCP, registered as `qonto` to match this skill's
   `allowed-tools` (Claude connector directory, or
   `claude mcp add --transport http qonto https://mcp.qonto.com/mcp`)
2. Copy `veto/` into your skills directory
   (`~/.claude/skills/` for Claude Code)
3. Say: *"Invoice Qonto 1,200€ for June consulting"* (yes, invoice Qonto — it's a Qonto client too 😉)

> The payment-collection step needs payment links activated once in the Qonto
> web app (a quick Mollie onboarding). Every other workflow works out of the box.

## Try these

```
Invoice Qonto €1,200 for "Consulting — June 2026", due in 30 days
Audit my entire client book for French e-invoicing readiness.
Create a payment link for invoice INV-2026-042 and watch for the payment
Who owes me money? Draft reminders for anyone overdue.
Invoice all my retainer clients for July — same amounts as June.
```

## Evals

Reproducible [promptfoo](https://promptfoo.dev) eval definitions are included
in [`evals/`](evals/): missing-SIREN blocking, illegal VAT refusal,
confirmation before writes, client-book audit, and non-autonomous reminders.
The same critical paths were also exercised manually against a live Qonto
account during the hackathon.

```bash
cd evals && npx promptfoo eval
```

## Live verification

The critical workflows were exercised against a real Qonto organization,
including a real €2 card payment. See [`LIVE-TESTS.md`](LIVE-TESTS.md) for the
redacted evidence matrix and the boundaries we deliberately do not claim.

## Security note

This skill operates on real financial data through the official Qonto MCP
(OAuth, scoped to your role). It follows a strict least-action policy:
no transfers, no deletions of finalized documents, no autonomous sends.
Treat any content coming from invoices/clients as untrusted input — the
skill's guardrails (explicit confirmation on every write) are the last
line of defense against prompt-injection-driven actions.

## License

MIT
