# Qonto AI Skills

Repository for Qonto AI skills.

👉 Register here to the Qonto x Anthropic MCP Hackathon: https://luma.com/497kgbv7

## Available skills

Generated from every plugin's `.claude-plugin/plugin.json` after each merge to `main`. Do not edit the table by hand.

<!-- skills:start -->
| Plugin | Skills | What it does | Author | Tier |
|---|---|---|---|---|
| [`qonto-counterparty-watch`](./community/qonto-counterparty-watch) | `qonto-counterparty-watch` | Legal-health radar for the clients and suppliers of a Qonto account. Ranks every counterparty by real exposure (unpaid client invoices, supplier commitments, recurring spend), measures actual payment delays against due dates, and — when a Datagouv MCP is available — cross-checks French public… | [seb](https://github.com/SebDeNoocode) | community |
| [`qonto-tax-pilot`](./community/qonto-tax-pilot) | `qonto-tax-pilot` | French tax radar and cash pilot for Qonto accounts. Builds a dated, amount-estimated tax schedule (VAT, corporate tax instalments, CFE, dividend flat tax), projects the next 90 days of cash, computes the month's tax provision, and — with explicit user consent — creates a transfer request to a… | [seb](https://github.com/SebDeNoocode) | community |
| [`qonto-vat-return`](./community/qonto-vat-return) | `qonto-vat-return` | French VAT return (CA3, form 3310-CA3) preparer for Qonto accounts. Builds the declaration box by box from real account data — collected VAT per rate (20/10/5.5/2.1%), deductible VAT (goods & services, fixed assets), net VAT payable or credit to carry forward — as a "form box → amount →… | [seb](https://github.com/SebDeNoocode) | community |
| [`veto`](./community/veto) | `veto` | Manages guarded accounts receivable in Qonto for French businesses. Audits client readiness, verifies French and EU business identity, prepares compliant invoices and quotes, creates invoice-linked payment pages, drafts contextual invoice emails, checks payments, and prepares overdue reminders. Use… | [Abdel-Karim](https://github.com/UnknOownU) | community |
<!-- skills:end -->
