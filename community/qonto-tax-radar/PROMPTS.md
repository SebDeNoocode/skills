# 💬 Example prompts — qonto-tax-radar

Invoke with `/qonto-tax-radar <your request>`, or explicitly ask for a Qonto tax pre-audit. Do not invoke for general tax questions unrelated to the user's Qonto account.

## Getting started
- "Run my tax pre-audit"
- "Am I ready for a tax audit?"

## Going further
- "What would a tax inspector flag in my accounts this year?"
- "Focus on VAT: what am I deducting without a receipt on file?"
- "Review this year's restaurants, travel and gifts like an auditor would"
- "Any personal-looking spending booked as business expenses?"
- "Extend the screening to 24 months and price my worst-case exposure"
- "Re-run the pre-audit and compare with the last report — did my grade improve?"

## Chain it
Each handoff below requires a separate explicit user request.

- "Recover the receipts behind the red flags" — hand the list over to `qonto-receipt-hunter`
- "Double-check my duplicate charges in depth" — dig further with `qonto-supplier-detective`
- "Now prepare a clean handoff for my accountant with these findings" — continue with `qonto-accountant-handoff`
