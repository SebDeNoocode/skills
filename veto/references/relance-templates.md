# Reminder (relance) templates

Adapt tone to lateness. Always personalize: client name, invoice number,
amount, due date, days overdue. Draft in the client's locale. The user
sends — never send autonomously.

## Level 1 — Friendly (1–14 days overdue)

**FR:**
> Objet : Facture {number} — petit rappel
>
> Bonjour {name},
>
> Sauf erreur de notre part, la facture {number} de {amount} €, échue le
> {due_date}, ne nous est pas encore parvenue. Il s'agit sans doute d'un
> simple oubli. Vous pouvez la régler directement ici : {payment_link}
>
> N'hésitez pas à revenir vers moi en cas de question.
> Bien cordialement, {user_name}

**EN:**
> Subject: Invoice {number} — gentle reminder
>
> Hi {name}, just a quick note: invoice {number} for €{amount} was due on
> {due_date} and appears unpaid. You can settle it here: {payment_link}.
> If payment is already on its way, please disregard this message.
> Best, {user_name}

## Level 2 — Firm (15–30 days overdue)

**FR:**
> Objet : Facture {number} — relance n°2
>
> Bonjour {name},
>
> Malgré notre précédent rappel, la facture {number} de {amount} €, échue
> le {due_date}, demeure impayée à ce jour ({days_late} jours de retard).
>
> Conformément à nos conditions, des pénalités de retard (au taux de
> {penalty_rate}) ainsi que l'indemnité forfaitaire de recouvrement de 40 €
> sont applicables. Nous vous remercions de procéder au règlement sous
> 8 jours : {payment_link}
>
> Cordialement, {user_name}

## Level 3 — Formal notice / mise en demeure (30+ days)

**FR:**
> Objet : MISE EN DEMEURE — Facture {number}
>
> {name},
>
> Malgré nos relances des {reminder_dates}, la facture {number} de
> {amount} €, échue le {due_date}, reste impayée.
>
> Par la présente, nous vous mettons en demeure de régler la somme de
> {amount} € majorée des pénalités de retard ({penalties} €) et de
> l'indemnité forfaitaire de 40 €, sous 8 jours à compter de la réception
> de ce courrier.
>
> À défaut, nous nous réservons le droit d'engager toute procédure de
> recouvrement utile, sans autre avis préalable.
>
> {user_name} — envoi recommandé avec accusé de réception conseillé

## Escalation guidance

- `{penalty_rate}` is the invoice's contractual late-payment rate (read it
  from the invoice terms, or ask the user). Never paste a hardcoded semester
  figure — the reference rate changes.
- Always compute `{penalties}` with the deterministic validator:
  `python3 scripts/validate_fr.py penalty <amount_ttc> <days_late> <annual_rate_percent>`,
  and show the calculation to the user.
- Level 3 should be sent by registered mail (recommandé AR) — remind the
  user; the email draft is a courtesy copy.
- If a client disputes the invoice, stop the escalation and flag for human
  resolution.
