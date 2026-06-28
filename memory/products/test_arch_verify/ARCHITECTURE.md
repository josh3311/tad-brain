# AI Invoice Chaser — Architecture Plan
Generated: 2026-06-27T22:59:41.042725

## MVP Scope
User uploads CSV of unpaid invoices. System generates 3 tone variations (friendly, firm, urgent) for each using OpenAI. Contractor previews and manually sends via email.

## Target User
Small contractor, 1-5 employees

## Files

### main.py
CLI tool that reads unpaid invoices from CSV, generates human-sounding follow-up emails via OpenAI API, and logs them for manual send.

## Data Model
Invoice object with (client_name, invoice_id, amount, days_overdue, email). Follow-up object with (invoice_id, email_body, tone_index). CSV input format: client_name,email,invoice_id,amount,days_overdue.

## Done Criteria
User can (1) load CSV file, (2) generate follow-ups for all invoices in <10 seconds, (3) view and copy generated emails, (4) see success/error logs per invoice.